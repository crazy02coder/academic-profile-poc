"""Akademik İz — FastAPI uygulaması: iş hattı, SSE canlı log ve profil sohbeti."""
from __future__ import annotations

import asyncio
import base64
import copy
import logging
import re
import json
import time
import uuid

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Literal

from . import rea, recipes, org_assets, student_view, student_assistant, uni_facts, firm_facts, reading
from .consensus import save_run, verify_papers, verify_profile
from .net import fetch_static
from .analysis import analyze
from . import history as history_store
from .chat import MODES, Knowledge, answer
from .paper import detail as paper_detail
import os
from urllib.parse import urlparse

from .config import ROOT, chromium_executable, redact
from .text import detect_title, fold, word_match
from .dedup import resolve
from .discover import Profile, llm_enrich, locate, registrable
from . import ai_settings
from .llm import LLM, list_models
from .sources import crossref_works, openalex_by_doi, openalex_works, orcid_works, scholar_works, yok_works
import httpx

from . import directory, firms, industry, library, patents, profile_refresh, publication_status, quartiles, trsources, unit_publications, wos, wos_enrichment, wos_verification, yokdir

from .library_routes import router as library_router

app = FastAPI(title="Akademik İz")
app.include_router(library_router)
from .tools_routes import router as tools_router  # noqa: E402
app.include_router(tools_router)
logger = logging.getLogger(__name__)
app.add_middleware(CORSMiddleware, allow_origin_regex=r"http://127\.0\.0\.1(:\d+)?|http://localhost(:\d+)?",
                   allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


@app.middleware("http")
async def no_stale_assets(request: Request, call_next):
    """Arayüz dosyaları her açılışta ETag ile doğrulanır: güncelleme sonrası tarayıcı eski app.js'i kullanmaz."""
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache"
    return response
JOBS: dict[str, dict] = {}

STEPS = [  # arayüz kendi sade aşamalarını gösterir; bu liste /api/jobs yanıtında bilgi amaçlı döner
    ("rea", "Site yapısı çözümleniyor (tersine mühendislik)"),
    ("scrape", "Site sayfa sayfa taranıyor"),
    ("crawl", "Site sayfa sayfa taranıyor"),
    ("yok", "Akademik kaynaklardan yayınlar toplanıyor"),
    ("publications", "Akademik kaynaklardan yayınlar toplanıyor"),
    ("dedup", "Veriler birleştiriliyor ve doğrulanıyor"),
    ("verify", "Veriler birleştiriliyor ve doğrulanıyor"),
    ("analysis", "Yapay zekâ modeli hazırlanıyor"),
]


class JobIn(BaseModel):
    url: str = Field(default="", max_length=2000)  # kurum sitesi: isteğe bağlı, YÖK adayından bulunur
    name: str = Field(min_length=2, max_length=160)
    yok_url: str = Field(default="", max_length=600)  # YÖK aramasında seçilen kişinin profili
    university: str = Field(default="", max_length=200)
    department: str = Field(default="", max_length=200)
    email: str = Field(default="", max_length=200)


class ChatIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    chat_id: str = ""
    mode: str = "auto"  # auto | rag | cag | hybrid


class StudentMessageIn(BaseModel):
    model_config = {"extra": "forbid"}
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class StudentChatIn(BaseModel):
    model_config = {"extra": "forbid"}
    question: str = Field(min_length=1, max_length=1000)
    messages: list[StudentMessageIn] = Field(default_factory=list, max_length=10)
    section: str | None = Field(default=None, max_length=30)
    faculty: str = Field(default="", max_length=200, pattern=r"^[^\x00-\x1f<>:{}\[\]\\]*$")
    department: str = Field(default="", max_length=200, pattern=r"^[^\x00-\x1f<>:{}\[\]\\]*$")


class RefreshIn(BaseModel):
    sections: list[str] | None = Field(default=None, max_length=12)
    sources: list[str] | None = Field(default=None, max_length=12)


def _emit(job: dict, event: dict):
    event["t"] = round(time.time() - job["started"], 1)
    job["events"].append(event)


def _slim_records(records) -> list[dict]:
    """Canlı listeye giden hafif yayın kaydı (birleştirme/doğrulama sonra yapılır)."""
    out = []
    for r in records or []:
        if isinstance(r, dict) and r.get("title"):
            out.append({k: r.get(k) for k in ("title", "year", "venue", "doi", "source", "type")})
    return out[:600]


def _slim_profile(profile) -> dict:
    p = profile.to_dict()
    return {"name": p.get("name") or profile.query_name, "title": p.get("title"), "institution": p.get("institution"),
            "department": p.get("department"), "photo": (p.get("yok") or {}).get("photo") or p.get("photo")}


SITE_TIMEOUT = 60  # YÖK adayı seçildiyse kurum sitesi yalnız zenginleştirme: fotoğraf, ilgi alanı, profil bağlantısı


async def _locate(data: JobIn, name: str, log, llm) -> tuple[Profile, dict]:
    """Kurum sitesi adımı (Scrapling + REA). Kişi YÖK'ten seçildiyse süre sınırlı; site okunamazsa YÖK'le devam edilir."""
    if not data.yok_url:
        return await locate(data.url.strip(), name, log, llm)
    profile, report = Profile(query_name=name, name=data.name), {"start_url": data.url, "strategy": ["yok"], "rea": None,
                                                                 "crawl": {"pages": 0}, "walls": [], "recipe": {"events": []}}
    if data.url:
        try:
            profile, report = await asyncio.wait_for(locate(data.url, name, log, llm), SITE_TIMEOUT)
        except Exception as exc:  # noqa: BLE001
            await log("scrape", "warning", f"Kurum sitesi okunamadı ({type(exc).__name__}); YÖK ile devam ediliyor.")
    else:
        await log("scrape", "warning", "Kurum sitesi bulunamadı; profil YÖK ve açık kaynaklardan hazırlanıyor.")
    profile.name = profile.name or data.name
    profile.links["yok"] = data.yok_url
    # YÖK satırındaki kurum yolu: site söylemediyse bu kullanılır, söylediyse ikinci kaynak olarak doğrular.
    profile.set("institution", data.university, "yok", data.yok_url)
    profile.set("department", data.department, "yok", data.yok_url)
    return profile, report


async def pipeline(job: dict, data: JobIn):
    async def log(step: str, status: str, message: str):
        _emit(job, {"type": "log", "step": step, "status": status, "message": message})

    llm = await LLM().probe()
    job["llm"] = llm
    await log("scrape", "running", f"Ortam: REA {'✓' if rea.available() else '✗'} · "
                                   f"Chromium {'✓' if chromium_executable() else '✗'} · LLM: {llm.label()}")
    try:
        report: dict = {}
        yok_rea = None
        name = re.sub(r"^[\s\"“”'‘’]+|[\s\"“”'‘’]+$", "", data.name)
        if data.yok_url and not data.url:
            data = data.model_copy(update={"url": await yokdir.person_site(data.university, data.email)})
        profile, report = await _locate(data, name, log, llm)
        await log("scrape", "done" if profile.found else "warning",
                  f"{profile.name or data.name} · {profile.get('title', 'unvan ?')} · "
                  f"{profile.get('department', 'bölüm ?')}")
        if not any(e.get("step") == "crawl" for e in job["events"]):
            await log("crawl", "done", "Gezinmeye gerek kalmadı: kişi başlangıç sayfasında veya hafızada bulundu.")
        if profile.links.get("orcid"):
            profile.observe("orcid", profile.links["orcid"], "university", profile.source_url)
        # Canlı profil: kimlik bulununca kart açılır, yayınlar kaynak kaynak eklenir (sonuç gelince tam profile geçilir)
        live_pending = {"YÖK", "OpenAlex", "Crossref", "ORCID", "Scholar", "TR Dizin", "OpenAIRE", "Tez Merkezi"}
        _emit(job, {"type": "partial", "profile": _slim_profile(profile), "pending": sorted(live_pending)})

        def announce(label):
            def done(task):
                live_pending.discard(label)
                recs = []
                if not task.cancelled() and task.exception() is None:
                    res = task.result()
                    recs = res[0] if isinstance(res, tuple) else res
                _emit(job, {"type": "partial", "source": label, "records": _slim_records(recs), "pending": sorted(live_pending)})
            return done

        # YÖK'ü beklemeyenler hemen başlar: Scholar ve Tez Merkezi yalnız adı kullanır; TR Dizin ve OpenAIRE sayfaları
        # şimdi çeker, kişiyle eşleştirmeyi YÖK'ün netleştirdiği ad/ORCID gelince (identity_ready) yapar.
        identity_ready = asyncio.Event()
        scholar_task = asyncio.create_task(scholar_works(profile, log))
        early = [asyncio.create_task(trsources.trdizin_works(profile, log, identity_ready)),
                 asyncio.create_task(trsources.openaire_works(profile, log, identity_ready)),
                 asyncio.create_task(trsources.tez_works(profile, log))]
        scholar_task.add_done_callback(announce("Scholar"))
        for label, task in zip(("TR Dizin", "OpenAIRE", "Tez Merkezi"), early):
            task.add_done_callback(announce(label))

        # Faz A: kimlik çözümleme + YÖK yayınları (ORCID burada netleşebilir)
        await log("yok", "running", "YÖK Akademik: Scrapling StealthySession açılıyor, REA CDP ile bağlanacak.")
        yok_records = []
        try:
            yok_records, yok_rea = await asyncio.wait_for(yok_works(profile, log), timeout=150)
            await log("yok", "done", f"YÖK: {len(yok_records)} kayıt.")
        except Exception as exc:  # noqa: BLE001
            yok_records = []
            await log("yok", "warning", f"YÖK atlandı ({type(exc).__name__}); akış devam ediyor.")
        finally:
            identity_ready.set()
            live_pending.discard("YÖK")
            _emit(job, {"type": "partial", "source": "YÖK", "records": _slim_records(yok_records),
                        "profile": _slim_profile(profile), "pending": sorted(live_pending)})

        # Faz B: açık API'ler + Scholar paralel
        await log("publications", "running", "Paralel: OpenAlex, Crossref, ORCID, TR Dizin, OpenAIRE (DergiPark, üniversite "
                                             "arşivleri), YÖK Tez Merkezi; Scholar best-effort.")
        # YÖK unvan/bölümü çoğu zaman verir; sayfa metninden LLM tamamlaması yalnız hâlâ eksik kalanlar için,
        # API sorgularıyla paralel çalışır.
        labels = ("OpenAlex", "Crossref", "ORCID", "Scholar", "TR Dizin", "OpenAIRE", "Tez Merkezi")
        api_tasks = [asyncio.create_task(c) for c in (openalex_works(profile, log), crossref_works(profile, log),
                                                      orcid_works(profile, log))]
        for label, task in zip(("OpenAlex", "Crossref", "ORCID"), api_tasks):
            task.add_done_callback(announce(label))
        tasks = await asyncio.gather(*api_tasks, scholar_task, *early, llm_enrich(profile, llm, log),
                                     return_exceptions=True)
        tasks = tasks[:len(labels)]
        records = list(yok_records)
        meta = {}
        for label, res in zip(labels, tasks):
            if isinstance(res, Exception):
                msg = "Scholar erişilemedi, OpenAlex kullanıldı." if label == "Scholar" else \
                    f"{label} erişilemedi ({type(res).__name__})."
                await log("publications", "warning", msg)
                continue
            recs, m = res if isinstance(res, tuple) else (res, None)
            records.extend(recs)
            if m:
                meta[label.lower()] = m
        report["sources_meta"] = meta
        sch = meta.get("scholar") or {}
        if sch.get("affiliation"):
            aff = sch["affiliation"]
            profile.observe("title", detect_title(aff), "scholar", profile.links.get("scholar", ""))
            inst = next((part.strip() for part in aff.split(",") if "Univers" in part or "Üniversite" in part), "")
            profile.observe("institution", inst, "scholar", profile.links.get("scholar", ""))
        if sch.get("interests"):
            profile.observe("interests", sch["interests"], "scholar", profile.links.get("scholar", ""))
        if not profile.get("interests") and meta.get("scholar", {}).get("interests"):
            profile.set("interests", meta["scholar"]["interests"], "scholar", profile.links.get("scholar", ""))
        try:
            records.extend(await openalex_by_doi(records, profile.name or profile.query_name, log))
        except Exception as exc:  # noqa: BLE001
            await log("publications", "warning", f"OpenAlex DOI ile tamamlama atlandı ({type(exc).__name__}).")
        await log("publications", "done", f"{len(records)} ham kayıt toplandı.")

        await log("dedup", "running", "Dil tespiti (langdetect + Türkçe karakter sezgisi), DOI/başlık/çapraz dil eşleştirme…")
        papers, stats = await resolve(records, profile.name or profile.query_name, llm, log)
        await log("dedup", "done", f"{stats['raw']} ham kayıt → {stats['unique']} benzersiz yayın "
                                   f"(DOI {stats['doi']}, birebir başlık {stats['exact']}, bulanık {stats['fuzzy']}, "
                                   f"TR↔EN {stats['cross_lang']}).")

        # Doğrulama: kaynaklar arası uzlaşı + ardışık çalıştırmalar
        domain = registrable(urlparse(data.url).hostname or "")
        fact_key = f"{recipes.person_key(profile.query_name)}@{domain}"
        await log("verify", "running", "Aynı bilgi farklı kaynaklardan / önceki çalıştırmalardan geldi mi kontrol ediliyor…")
        verification, history = verify_profile(profile, fact_key, [])
        paper_ver = verify_papers(papers, history)
        icon = {"doğrulandı": "✓", "tek kaynak": "·", "çelişki": "⚠", "değişti": "↻"}
        parts = [f"{k} {icon.get(v['status'], '')}{v['status']} ({'+'.join(v['sources'])}, {v['runs_seen']}. kez)"
                 for k, v in verification.items() if k != "interests"]
        await log("verify", "running", "Profil: " + "; ".join(parts))
        if paper_ver["previous_runs"]:
            await log("verify", "running", f"Önceki çalıştırmaya göre: +{paper_ver['new']} yeni, −{paper_ver['removed']} "
                                           f"kaybolan yayın ({paper_ver['previous_runs']} çalıştırmalık geçmiş).")
        await log("verify", "done", f"{paper_ver['verified']}/{len(papers)} yayın doğrulandı "
                                    f"(≥2 kaynak: {paper_ver['multi_source']}, önceki çalıştırmada da görülen dahil).")

        prof = profile.to_dict()
        # Yapay zekâ analizi isteğe bağlı: profil hemen açılır, kullanıcı "Analiz et" deyince /analyze çalışır.
        analysis = {"mode": "pending" if papers else "unavailable", "summary": "", "areas": [], "methods": [],
                    "timeline": []}
        langs = {}
        for p in papers:
            for name in p["language_names"]:
                langs[name] = langs.get(name, 0) + 1
        by_source = {}
        for r in records:
            by_source[r["source"]] = by_source.get(r["source"], 0) + 1
        result = {
            "profile": prof, "publications": papers, "raw_count": stats["raw"], "unique_count": stats["unique"],
            "dedup": stats, "analysis": analysis, "paper_verification": paper_ver, "languages": langs, "by_source": by_source,
            "recon": {**report, "yok_rea": yok_rea}, "llm": llm.label(),
            "summary": f"{prof['name']} için {stats['raw']} ham kayıt ve {stats['unique']} benzersiz yayın derlendi."
                       if papers else
                       "Akış tamamlandı ancak kimliği doğrulanabilen yayın bulunamadı.",
            "elapsed": round(time.time() - job["started"], 1),
        }
        result["industry"] = industry.collaborations(papers, prof)
        result["industry_v"] = industry.VERSION
        if result["industry"]:
            await log("verify", "done", f"Sanayi iş birlikleri: {len(result['industry'])} firma "
                                        f"({sum(e['official'] for e in result['industry'])} resmi Ar-Ge/Tasarım Merkezi).")
        result["input"] = data.model_dump()
        # Yenileme, daha önce doğrulanan WoS yayınlarını ve kaynaklarını kaybetmez.
        if cached_wos := wos_enrichment.cached(prof, allow_stale=True):
            if cached_wos.get("records"):
                wos_enrichment.apply(result, cached_wos["records"], cached_wos)
        result["paper_verification"] = verify_papers(result["publications"], history)
        save_run(fact_key, history, verification, result["publications"])
        prev = job.get("refresh")
        if not prev and (same := history_store.find_same(prof)):
            prev = {"job_id": same["job_id"], "chat_id": same["id"]}
            await log("verify", "done", "Bu akademisyenin kaydı zaten vardı; yeni kayıt açılmadı, mevcut kayıt güncellendi.")
        if prev:  # yenileme: kayıt kimliği, sohbet geçmişi ve favori korunur
            result["job_id"] = prev["job_id"]
            result["chat_id"] = history_store.refresh(prev.get("chat_id") or "", prev["job_id"], result)["id"]
            if prev["job_id"] in JOBS:
                JOBS[prev["job_id"]]["result"] = result
            KB_CACHE.pop(prev["job_id"], None)
            y = prof.get("yok") or {}
            library.update_person(prev["job_id"], {
                "name": prof.get("name"), "title": prof.get("title"), "institution": prof.get("institution"),
                "department": prof.get("department"), "photo": y.get("photo"), "email": y.get("email"),
                "chat_id": result["chat_id"], "papers": result["unique_count"]})
        else:
            result["job_id"] = job["id"]
            result["chat_id"] = history_store.create(job["id"], result)["id"]
        quartiles.annotate(result.get("publications") or [])
        wos.annotate(result.get("publications") or [])
        publication_status.annotate(result.get("publications") or [])
        job["result"] = result
        history_store.save_result(result["job_id"], result)
        # Yalnız kullanıcının başlattığı tam toplama sırasında WoS işi oluştur.
        # Kayıtlı profilin açılması artık salt durum okumasıdır.
        if job.get("wos", True):
            await start_wos(result["job_id"], retry=bool(prev))
        _emit(job, {"type": "result", "data": result})
    except Exception as exc:  # noqa: BLE001
        _emit(job, {"type": "error", "message": f"İş tamamlanamadı: {type(exc).__name__}: {redact(str(exc))[:200]}"})
    finally:
        job["done"] = True
        _emit(job, {"type": "end"})


@app.get("/")
async def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/kutuphane")
async def library_page():
    """3B kütüphane: incelenen makaleler, kaydedilenler, konular ve gündem; yeni sekmede açılır."""
    return FileResponse(ROOT / "static" / "library.html", headers={"Cache-Control": "no-cache"})


def _wos_activity() -> dict:
    """Read local task registries without creating a scan or opening WoS."""
    active_jobs = sum(not task.done() for tasks in (wos.TASKS, library._TOPIC_TASKS)
                      for task in tasks.values())
    pending_jobs = sum(1 for job in JOBS.values()
                       if job.get("expects_wos") and not job["done"] and not job["task"].done())
    pending_jobs += sum(not task.done() for task in unit_publications.TASKS.values())
    return {"active_jobs": active_jobs, "pending_jobs": pending_jobs}


@app.get("/api/health")
async def health():
    llm = await LLM().probe()
    return {"rea": rea.available(), "chromium": bool(chromium_executable()), "llm": llm.label(),
            "llm_ready": llm.available, "steps": STEPS, "patents": patents.enabled(),
            "wos_activity": {**_wos_activity(),
                             "waiting_verifications": len(wos_verification.get_active().get("items", []))}}


class AiSettingsIn(BaseModel):
    provider: str
    key: str = ""
    clear_key: bool = False
    model: str = ""
    fast_model: str = ""
    embed_model: str = ""
    base_url: str = ""


@app.get("/api/settings/ai")
async def ai_settings_get():
    return ai_settings.public()


@app.post("/api/settings/ai")
async def ai_settings_save(body: AiSettingsIn):
    try:
        ai_settings.save(body.provider, body.key, body.clear_key, body.model, body.fast_model, body.embed_model, body.base_url)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    # Yeni sağlayıcı hemen geçerli; gömme vektörleri modele özgü olduğundan sohbet bilgi tabanları da yeniden kurulur.
    _LLM_CACHE.update(llm=None, at=0.0)
    KB_CACHE.clear()
    llm = await _llm()
    return {**ai_settings.public(), "ready": llm.available, "label": llm.label()}


@app.post("/api/settings/ai/models")
async def ai_settings_models(body: AiSettingsIn):
    """Girilen bilgilerle bağlanıp model listesini getirir; hiçbir şey kaydetmez."""
    if body.provider not in ai_settings.PROVIDERS:
        raise HTTPException(422, "Bilinmeyen sağlayıcı.")
    try:
        default = ai_settings.PROVIDERS[body.provider]["base_url"]
        url = ai_settings.clean_url(body.base_url) if body.base_url.strip() or not default else default
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    key = ai_settings.key_for_test(body.provider, body.key.strip(), url)
    if body.provider != "custom" and not key:
        return {"ok": False, "error": "Anahtar girilmedi.", "models": []}
    try:
        names = await list_models(body.provider, url, key)
    except httpx.HTTPStatusError as exc:
        code = exc.response.status_code
        return {"ok": False, "models": [], "error": "Anahtar geçersiz ya da yetkisiz." if code in (401, 403) else f"Sunucu HTTP {code} döndürdü."}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "models": [], "error": f"Bağlanılamadı ({type(exc).__name__})."}
    return {"ok": True, "models": names or [], "error": ""}


@app.post("/api/jobs", status_code=202)
async def create_job(data: JobIn):
    data = data.model_copy(update={"url": data.url.strip(), "yok_url": data.yok_url.strip()})
    if data.url and not data.url.startswith(("http://", "https://")):
        raise HTTPException(422, "Geçerli bir http(s) bağlantısı girin.")
    if data.yok_url and not data.yok_url.startswith(yokdir.BASE + "/"):
        raise HTTPException(422, "Geçersiz YÖK bağlantısı.")
    if not data.url and not data.yok_url:
        raise HTTPException(422, "Önce akademisyeni arayıp seçin ya da kurum sitesi bağlantısı girin.")
    return _start(data)


@app.post("/api/jobs/{jid}/refresh", status_code=202)
async def refresh_job(jid: str, body: RefreshIn | None = None, *, wos: bool = True):
    """Seçilen bölümleri yeniler; gövdesiz eski istemciler tam yenileme yapabilir."""
    old = _result_for(jid)
    if not old:
        raise HTTPException(404, "Profil sonucu bulunamadı.")
    options = None
    if body and body.sections is not None:
        sections, sources = set(body.sections), set(body.sources if body.sources is not None else profile_refresh.SOURCES)
        if not sections or sections - profile_refresh.SECTIONS or sources - profile_refresh.SOURCES:
            raise HTTPException(422, "Geçerli veri bölümleri ve kaynaklar seçin.")
        if "publications" in sections and not sources:
            raise HTTPException(422, "Yayınlar için en az bir kaynak seçin.")
        options = {"sections": sections, "sources": sources}
    running = next((j for j in JOBS.values() if (j.get("refresh") or {}).get("job_id") == jid and not j["done"]), None)
    if running:
        return {"id": running["id"], "steps": STEPS}
    inp, prof = old.get("input") or {}, old["profile"]
    url = next((u for u in (inp.get("url"), prof.get("source_url"), (old.get("recon") or {}).get("start_url"))
                if isinstance(u, str) and u.startswith(("http://", "https://"))), "")
    yok_url = inp.get("yok_url") or (prof.get("links") or {}).get("yok") or ""
    if not url and not yok_url and options is None:
        raise HTTPException(422, "Bu kayıtta başlangıç bağlantısı yok; akademisyeni yeniden arayın.")
    data = JobIn(url=url, name=inp.get("name") or prof.get("name") or prof.get("query_name") or "", yok_url=yok_url,
                 university=inp.get("university") or "", department=inp.get("department") or "", email=inp.get("email") or "")
    return _start(data, {"job_id": jid, "chat_id": old.get("chat_id")}, options, wos=wos)


def _start(data: JobIn, refresh: dict | None = None, options: dict | None = None, *, wos: bool = True) -> dict:
    for jid in [k for k, v in JOBS.items() if v["done"] and time.time() - v["started"] > 3600]:
        JOBS.pop(jid, None)
    jid = uuid.uuid4().hex[:12]
    job = {"id": jid, "events": [], "done": False, "started": time.time(), "result": None, "refresh": refresh,
           "input": data.model_dump(),
           "wos": wos,  # birim (toplu) taramasında WoS çalışmaz; kişi kendi profilinden başlatır
           "expects_wos": wos and (not options or ("publications" in options["sections"] and "wos" in options["sources"]))}
    JOBS[jid] = job
    job["task"] = asyncio.create_task(_selective_pipeline(job, options) if options else pipeline(job, data))
    return {"id": jid, "steps": STEPS}


async def _selective_pipeline(job: dict, options: dict):
    async def log(step, status, message):
        _emit(job, {"type": "log", "step": step, "status": status, "message": message})

    jid = job["refresh"]["job_id"]
    try:
        old = copy.deepcopy(_result_for(jid))
        llm = await _llm()
        job["llm"] = llm
        result = await profile_refresh.collect(old, options["sections"], options["sources"], llm, log)
        current = _result_for(jid)
        if not current or history_store.load_result(jid) is None:
            raise ValueError("Profil tarama sırasında silindi.")
        # Aynı anda süren WoS taramasının yeni kayıtları bir bölüm yenilemesinde kaybolmasın.
        if current.get("wos_revision") != old.get("wos_revision"):
            profile_refresh.merge_publications(result, current.get("publications") or [])
            for key in ("wos_revision", "wos_enrichment"):
                if key in current:
                    result[key] = current[key]
        result["elapsed"] = round(time.time() - job["started"], 1)
        result["chat_id"] = history_store.refresh(old.get("chat_id") or "", jid, result)["id"]
        history_store.save_result(jid, result)
        for existing in JOBS.values():
            if (existing.get("result") or {}).get("job_id") == jid:
                existing["result"] = result
        job["result"] = result
        KB_CACHE.pop(jid, None)
        PAPER_CACHE.pop(jid, None)
        p = result["profile"]
        library.update_person(jid, {"name": p.get("name"), "title": p.get("title"), "institution": p.get("institution"),
            "department": p.get("department"), "photo": (p.get("yok") or {}).get("photo"), "papers": result["unique_count"]})
        if job.get("wos", True) and "publications" in options["sections"] and "wos" in options["sources"]:
            await start_wos(jid, retry=True)
        await log("verify", "done", "Seçilen bilgiler güncellendi.")
        _emit(job, {"type": "result", "data": result})
    except Exception as exc:
        _emit(job, {"type": "error", "message": f"Yenileme tamamlanamadı: {type(exc).__name__}: {redact(str(exc))[:200]}"})
    finally:
        job["done"] = True
        _emit(job, {"type": "end"})


@app.post("/api/jobs/{jid}/industry")
async def industry_job(jid: str):
    """Sanayi iş birliklerini kayıtlı profilden yeniden hesaplar (Ar-Ge listesi güncellenince ya da eski profillerde)."""
    result = _result_for(jid)
    if not result:
        raise HTTPException(404, "Profil sonucu bulunamadı.")
    result["industry"] = industry.collaborations(result["publications"], result["profile"])
    result["industry_v"] = industry.VERSION
    history_store.save_result(jid, result)
    KB_CACHE.pop(jid, None)
    return {"industry": result["industry"], "industry_v": industry.VERSION, "centers": industry.centers_info()}


@app.post("/api/jobs/{jid}/analyze")
async def analyze_job(jid: str):
    """Yapay zekâ araştırma analizi (isteğe bağlı; sonuç profil kaydına yazılır)."""
    result = _result_for(jid)
    if not result:
        raise HTTPException(404, "Profil sonucu bulunamadı.")
    if not result["publications"]:
        raise HTTPException(422, "Yayın olmadığı için analiz yapılamaz.")

    async def quiet(*_):
        return None

    analysis = await analyze(result["publications"], result["profile"], await _llm(), quiet)
    result["analysis"] = analysis
    history_store.save_result(jid, result)
    if jid in JOBS and JOBS[jid].get("result") is not None:
        JOBS[jid]["result"] = result
    KB_CACHE.pop(jid, None)  # asistanın bilgi tabanı yeni analizle yeniden kurulsun
    return analysis


@app.get("/api/jobs/{jid}/photo")
async def job_photo(jid: str):
    """Serve the largest stored original portrait, without upscaling thumbnails."""
    import io
    from PIL import Image
    result = _result_for(jid)
    profile = (result or {}).get("profile") or {}
    candidates = [profile.get("photo"), (profile.get("yok") or {}).get("photo")]
    best = None
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        match = re.fullmatch(r"data:(image/[a-z+]+);base64,(.+)", candidate, re.S)
        if not match:
            continue
        try:
            raw = base64.b64decode(match[2], validate=True)
            with Image.open(io.BytesIO(raw)) as portrait:
                area = portrait.width * portrait.height
            if best is None or area > best[0]:
                best = (area, raw, match[1])
        except (ValueError, OSError):
            continue
    if best is None:
        raise HTTPException(404)
    return Response(best[1], media_type=best[2], headers={"Cache-Control": "public, max-age=3600"})


@app.post("/api/jobs/{jid}/patents")
async def patents_job(jid: str):
    """Akademisyenin patentleri (EPO); sonuç profil kaydına yazılır. Anahtar yoksa {"enabled": false}."""
    if not patents.enabled():
        return {"enabled": False}
    result = _result_for(jid)
    if not result:
        raise HTTPException(404, "Profil sonucu bulunamadı.")
    prof = result["profile"]
    places = [prof.get("institution")] + [c.get("place") for c in (prof.get("yok") or {}).get("career") or []]
    try:
        found = await patents.person_patents(prof.get("name") or "", places)
    except patents.PatentError as exc:
        raise HTTPException(503, str(exc)) from None
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"EPO'ya ulaşılamadı ({type(exc).__name__}).") from None
    result["patents"], result["patents_v"] = found, patents.VERSION
    history_store.save_result(jid, result)
    return {"enabled": True, "patents": found, "patents_v": patents.VERSION}


@app.get("/api/jobs/{jid}/events")
async def events(jid: str, request: Request):
    job = JOBS.get(jid)
    if not job:
        raise HTTPException(404)

    async def stream():
        i = 0
        while True:
            if await request.is_disconnected():
                break
            while i < len(job["events"]):
                yield f"data: {json.dumps(job['events'][i], ensure_ascii=False, default=str)}\n\n"
                i += 1
            if job["done"] and i >= len(job["events"]):
                break
            await asyncio.sleep(0.2)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/recipes")
async def list_recipes():
    """REA'nın öğrendiği site tarifleri, sayfa parmak izleri ve değişiklik geçmişi."""
    out = []
    for st in recipes.all_stores():
        out.append({"domain": st["domain"], "replay": st["replay"],
                    "pages": [{k: v for k, v in p.items() if k != "skeleton"} for p in st["pages"].values()],
                    "people": st["people"], "events": st["events"][-20:]})
    return out


async def check_changes() -> list[dict]:
    """Bilinen tüm sayfaları Scrapling ile ucuzca yoklar; yapı değiştiyse REA ile yeniden öğrenir."""
    report = []
    for st in recipes.all_stores():
        for key, pg in list(st["pages"].items())[:15]:
            item = {"domain": st["domain"], "url": pg["url"]}
            try:
                page = await fetch_static(pg["url"], timeout=15)
                skeleton = recipes.dom_skeleton(page.selector)
                chk = recipes.check_page(st, pg["url"], skeleton)
                item.update(chk)
                if chk.get("drift"):
                    recipes.event(st, "drift", f"{pg['url']}: benzerlik %{chk['similarity']*100:.0f} (periyodik tarama)")
                    if rea.available():
                        cap = await rea.recon(pg["url"])
                        if cap.ok:
                            recipes.remember_page(st, pg["url"], skeleton, recipes.api_shape(cap), "", cap.evidence_id)
                            recipes.event(st, "relearned", f"{pg['url']} REA ile yeniden haritalandı")
                            item["relearned"] = True
                else:
                    recipes.remember_page(st, pg["url"], skeleton, None)
            except Exception as exc:  # noqa: BLE001
                item["error"] = type(exc).__name__
            report.append(item)
        recipes.save(st)
    return report


@app.post("/api/recipes/check")
async def recipes_check():
    return await check_changes()


@app.get("/api/wos/verification")
async def wos_verification_status(request: Request):
    if not wos_verification.same_origin(request, required=False):
        raise HTTPException(403, "Doğrulama paneli yalnız aynı uygulama üzerinden açılabilir.")
    return {**wos_verification.get_active(), **_wos_activity()}


@app.websocket("/api/wos/verification/{challenge_id}/stream")
async def wos_verification_stream(websocket: WebSocket, challenge_id: str):
    await wos_verification.stream(websocket, challenge_id)


@app.on_event("shutdown")
async def _close_browsers():
    from .net import close_stealth
    from .google_search import close as close_google

    await wos_verification.close()
    await unit_publications.close()
    tasks = list(_UNIT_PERSON_TASKS.values())
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    _UNIT_PERSON_TASKS.clear()
    _UNIT_PERSON_UPDATES.clear()
    await library.close()
    await wos.close()
    for task in [*org_assets._INFLIGHT.values(), *student_view.TASKS.values()]:
        task.cancel()
    await asyncio.gather(*list(org_assets._INFLIGHT.values()), *list(student_view.TASKS.values()), return_exceptions=True)
    await close_stealth()
    await close_google()


@app.on_event("startup")
async def _watcher():
    minutes = float(os.getenv("WATCH_INTERVAL_MIN", "0"))
    if minutes <= 0:
        return

    async def loop():
        while True:
            await asyncio.sleep(minutes * 60)
            try:
                await check_changes()
            except Exception:  # noqa: BLE001
                pass

    asyncio.create_task(loop())


KB_CACHE: dict[str, Knowledge] = {}


def _result_for(jid: str) -> dict | None:
    job = JOBS.get(jid)
    if job and job.get("result"):
        res = job["result"]
    else:
        try:
            res = history_store.load_result(jid)
        except ValueError:
            return None
    if res:
        quartiles.annotate(res.get("publications") or [])  # okuma anında: eski profiller yenilemeden çeyrek alır
        wos.annotate(res.get("publications") or [])
        publication_status.annotate(res.get("publications") or [])
    return res


@app.get("/api/jobs/{jid}/result")
async def job_result(jid: str):
    res = _result_for(jid)
    if not res:
        raise HTTPException(404)
    return res


@app.post("/api/jobs/{jid}/wos")
async def start_wos(jid: str, retry: bool = False):
    result = _result_for(jid)
    if not result:
        raise HTTPException(404)
    identity = wos_enrichment.profile_key(result["profile"])

    def persist(records, report):
        # Tarama sırasında yenileme/analiz yapılmış olabilir: güncel kayda ekle.
        if history_store.load_result(jid) is None:
            return None  # tarama sürerken silinen profili yeniden oluşturma
        current = _result_for(jid)
        if not current or wos_enrichment.profile_key(current["profile"]) != identity:
            return None
        wos_enrichment.apply(current, records, report)
        quartiles.annotate(current["publications"])
        wos.annotate(current["publications"])
        publication_status.annotate(current["publications"])
        history_store.save_result(jid, current)
        for job in JOBS.values():
            if (job.get("result") or {}).get("job_id") == jid:
                job["result"] = current
        if cid := current.get("chat_id"):
            if conv := history_store.load(cid):
                conv["papers"] = current["unique_count"]
                history_store.save(conv)
        library.update_person(jid, {"papers": current["unique_count"]})
        KB_CACHE.pop(jid, None)
        PAPER_CACHE.pop(jid, None)
        return current

    return wos.start(result, retry=retry, on_publications=persist)


@app.get("/api/jobs/{jid}/wos")
async def wos_status(jid: str):
    result = _result_for(jid)
    if not result:
        raise HTTPException(404)
    return wos.snapshot(result)


@app.post("/api/jobs/{jid}/chat")
async def chat(jid: str, body: ChatIn):
    result = _result_for(jid)
    if not result:
        raise HTTPException(404, "Önce bir profil oluşturun.")
    try:
        conv = history_store.load(body.chat_id) if body.chat_id else None
    except ValueError:
        conv = None
    if conv is None:
        conv = history_store.create(jid, result)
    llm = await _llm()
    kb = KB_CACHE.get(jid)
    if kb is None:
        kb = KB_CACHE[jid] = Knowledge(result)
    mode = body.mode if body.mode in MODES else "auto"

    async def stream():
        yield f"data: {json.dumps({'chat_id': conv['id']})}\n\n"
        yield f"data: {json.dumps({'stage': 'Yanıt hazırlanıyor…'}, ensure_ascii=False)}\n\n"
        queue: asyncio.Queue = asyncio.Queue(maxsize=64)
        meta: dict = {}

        async def stage(message: str):
            await queue.put({"stage": message})

        async def produce():
            text = ""
            try:
                # Embedding hazırlığı ve model üretimi aynı toplam bütçeyi paylaşır.
                async with asyncio.timeout(120):
                    async for piece in answer(kb, body.question, list(conv["messages"]), llm, mode, meta,
                                              on_stage=stage):
                        text += piece
                        await queue.put({"delta": piece})
                if not text.strip():
                    raise RuntimeError("Model boş cevap döndürdü.")
            except TimeoutError:
                meta["error"] = "Yanıt 120 saniye içinde tamamlanamadı. Model veya embedding hazırlığı zaman aşımına uğradı."
                logger.warning("Profil sohbeti zaman aşımına uğradı: iş %s", jid)
                await queue.put({"error": meta["error"]})
            except Exception as exc:  # noqa: BLE001
                meta["error"] = f"Sohbet tamamlanamadı: {type(exc).__name__}: {redact(str(exc))[:200]}"
                logger.exception("Profil sohbeti tamamlanamadı: iş %s", jid)
                await queue.put({"error": meta["error"]})
            try:
                # Eşzamanlı başka bir cevap kaydedildiyse geçmişini kaybetme.
                latest = history_store.load(conv["id"])
                if latest is not None:
                    latest["messages"].append({"role": "user", "content": body.question, "at": time.strftime("%H:%M")})
                    latest["messages"].append({"role": "assistant", "content": text or meta.get("error", ""),
                                               "meta": meta, "at": time.strftime("%H:%M")})
                    history_store.save(latest)
            except Exception:  # noqa: BLE001
                logger.exception("Sohbet geçmişi kaydedilemedi: iş %s", jid)
                await queue.put({"error": "Cevap geçmişe kaydedilemedi."})
            await queue.put({"done": True, "meta": meta})

        task = asyncio.create_task(produce())
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=5)
                except TimeoutError:
                    yield ": bekleniyor\n\n"
                    continue
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("done"):
                    break
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


PAPER_CACHE: dict[str, dict] = {}


@app.get("/api/jobs/{jid}/papers/{pid}")
async def paper(jid: str, pid: str):
    """Yayına tıklanınca: Scrapling ile yayıncı sayfası + künye + Gemini Türkçe özet (SSE)."""
    result = _result_for(jid)
    item = next((p for p in (result or {}).get("publications", []) if p["id"] == pid), None)
    if not item:
        raise HTTPException(404)
    llm = await _llm()
    return _paper_stream(item, llm, PAPER_CACHE.setdefault(jid, {}), result.get("profile"), f"iş {jid}, yayın {pid}")


def _paper_stream(item: dict, llm, cache: dict, profile: dict | None, label: str) -> StreamingResponse:
    async def stream():
        queue: asyncio.Queue = asyncio.Queue(maxsize=64)

        async def produce():
            try:
                async with asyncio.timeout(180):
                    async for event in paper_detail(item, llm, cache, profile):
                        await queue.put(event)
            except TimeoutError:
                await queue.put({"error": "Yayın ayrıntısı 180 saniye içinde tamamlanamadı."})
            except Exception as exc:  # noqa: BLE001
                logger.exception("Yayın ayrıntısı alınamadı: %s", label)
                await queue.put({"error": f"Yayın ayrıntısı alınamadı: {type(exc).__name__}: {redact(str(exc))[:200]}"})
            await queue.put({"done": True})

        task = asyncio.create_task(produce())
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=5)
                except TimeoutError:
                    yield ": bekleniyor\n\n"
                    continue
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("done"):
                    break
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@app.get("/api/chats")
async def chats():
    return history_store.list_all()


@app.get("/api/chats/{cid}")
async def chat_get(cid: str):
    try:
        conv = history_store.load(cid)
    except ValueError:
        conv = None
    if not conv:
        raise HTTPException(404)
    return {"chat": conv, "result": _result_for(conv["job_id"])}


@app.delete("/api/chats/{cid}")
async def chat_delete(cid: str):
    try:
        conv = history_store.load(cid)
        ok = history_store.delete(cid)
    except ValueError:
        raise HTTPException(400) from None
    if not ok:
        raise HTTPException(404)
    # Profil sonucunu kullanan başka sohbet kalmadıysa onu da sil
    if conv and not any(c["job_id"] == conv["job_id"] for c in history_store.list_all()):
        history_store.delete_result(conv["job_id"])
        KB_CACHE.pop(conv["job_id"], None)
    return {"deleted": cid}


@app.delete("/api/chats")
async def chats_delete_all():
    for c in history_store.list_all():
        history_store.delete(c["id"])
        history_store.delete_result(c["job_id"])
    KB_CACHE.clear()
    return {"deleted": "all"}


# ------------------------------------------------------------------ ortak LLM (kısa süreli önbellek)
_LLM_CACHE: dict = {"at": 0.0, "llm": None}


async def _llm() -> LLM:
    if _LLM_CACHE["llm"] is None or time.time() - _LLM_CACHE["at"] > 300:
        _LLM_CACHE.update(llm=await LLM().probe(), at=time.time())
    return _LLM_CACHE["llm"]


# --------------------------------------------------------------- kurum dizini
_UNIT_PERSON_TASKS: dict[str, asyncio.Task] = {}
_UNIT_PERSON_UPDATES: dict[str, list] = {}


def _directory_identity(person: dict, institution: str = "") -> dict:
    links = dict(person.get("links") or {})
    url = person.get("yok_url") or person.get("url") or ""
    if url.startswith(yokdir.BASE + "/"):
        links["yok"] = url
    if person.get("orcid"):
        links["orcid"] = person["orcid"]
    return {"name": person.get("name") or "", "institution": person.get("university") or institution,
            "links": links}


def _directory_matches(person: dict, institution: str, profile: dict) -> bool:
    identity = _directory_identity(person, institution)
    if not history_store.same_person(identity, profile):
        return False
    # A common strong identifier is sufficient. Otherwise protect homonyms in
    # different departments or on different individual pages in the same school.
    for name, pattern in (("yok", history_store.YOK_ID_RE), ("orcid", history_store.ORCID_RE)):
        left = pattern.search(identity["links"].get(name) or "")
        right = pattern.search((profile.get("links") or {}).get(name) or (profile.get("orcid") if name == "orcid" else "") or "")
        if left and right:
            return left[0].upper() == right[0].upper()
    dept, other = fold(person.get("department") or ""), fold(profile.get("department") or "")
    if dept and other and dept not in other and other not in dept:
        return False
    url = person.get("site_url") or person.get("url") or ""
    old_url = profile.get("source_url") or ""
    if url and not url.startswith(yokdir.BASE + "/") and old_url:
        a, b = urlparse(url), urlparse(old_url)
        if a.path.strip("/") and b.path.strip("/") and (a.netloc, a.path.rstrip("/")) != (b.netloc, b.path.rstrip("/")):
            return False
    return True


def _staff_metrics(people: list[dict], institution: str = "") -> list[dict]:
    """Use saved profile counts; an uncollected profile has null counts, not zero."""
    known = []
    for chat in history_store.list_all():
        result = _result_for(chat["job_id"])
        if result:
            known.append((chat, result))
    rows = []
    for person in people:
        row = {**person, "publication_count": None, "article_count": None, "citations": None,
               "sources": [], "state": "pending"}
        matches = [(c, r) for c, r in known if _directory_matches(person, institution, r["profile"])]
        match = matches[0] if len(matches) == 1 else None
        if match:
            chat, result = match
            papers = result.get("publications") or []
            citations = [p["citations"] for p in papers if isinstance(p.get("citations"), int)]
            row.update(publication_count=len(papers),
                       article_count=sum(publication_status.kind(p) in {"Makale", "Derleme"} for p in papers),
                       citations=sum(citations) if citations or not papers else None,
                       sources=sorted({s for p in papers for s in p.get("sources") or [p.get("source")] if s}),
                       chat_id=chat["id"], job_id=result["job_id"], state="done")
        rows.append(row)
    return rows


def _start_unit_collection(people: list[dict], institution: str, domain: str, unit: str, *, refresh: bool = False) -> dict:
    known = [(chat, _result_for(chat["job_id"])) for chat in history_store.list_all()]
    for person in people:
        matches = [r for _, r in known if r and _directory_matches(person, institution, r["profile"])]
        if len(matches) == 1:
            unit_publications.seed(person, matches[0], institution, domain)
    async def collect(person, institution, domain, *, on_update=None):
        return await _collect_unit_person(person, institution, domain, on_update=on_update, refresh=refresh)

    return unit_publications.start(people, institution, domain, unit, collect, refresh=refresh)


async def _collect_unit_person(person: dict, institution: str, domain: str, *, on_update=None, refresh: bool = False) -> dict:
    """Reuse the individual-profile pipeline and its persisted WoS enrichment.

    A person shared by two units is collected once. Existing profiles keep their
    chat, favorites and sources. First results arrive before WoS finishes.
    """
    identity = _directory_identity(person, institution)
    key = unit_publications.person_key(person, institution, domain)
    subscribers = _UNIT_PERSON_UPDATES.setdefault(key, [])
    if on_update:
        subscribers.append(on_update)

    def publish(result):
        for callback in list(_UNIT_PERSON_UPDATES.get(key, [])):
            callback(result)

    async def collect():
        source_warnings = []
        known = [_result_for(c["job_id"]) for c in history_store.list_all()]
        matches = [r for r in known if r and _directory_matches(person, institution, r["profile"])]
        result = matches[0] if len(matches) == 1 else None
        if result is not None:
            publish(result)
        if result is None or refresh:
            running = next((job for job in JOBS.values() if not job["done"] and job.get("input")
                            and unit_publications.person_key(
                                {**job["input"], "url": job["input"].get("yok_url") or job["input"].get("url")},
                                job["input"].get("university") or institution, domain) == key), None)
            if running is None:
                if result is not None:
                    started = await refresh_job(result["job_id"], wos=False)
                else:
                    yok_url = identity["links"].get("yok") or ""
                    url = person.get("site_url") or (person.get("url") if not yok_url else "") or ""
                    if not url and not yok_url and domain:
                        url = f"https://{domain}/"
                    if not url and not yok_url:
                        raise RuntimeError("Kişinin profil veya kurum bağlantısı bulunamadı.")
                    data = JobIn(name=person["name"], url=url, yok_url=yok_url,
                                 university=identity["institution"], department=person.get("department") or "",
                                 email=person.get("email") or "")
                    started = _start(data, wos=False)
                running = JOBS[started["id"]]
            await asyncio.shield(running["task"])
            result = running.get("result")
            if not result:
                message = next((e.get("message") for e in reversed(running["events"]) if e["type"] == "error"), None)
                raise RuntimeError(message or "Akademisyen profili toplanamadı.")
            source_warnings = [e["message"] for e in running["events"] if e.get("step") in {"yok", "publications"}
                               and e.get("status") == "warning"]
        publish(result)
        # Toplu taramada WoS yok: kişinin açık kaynak profili bitince yeri hemen boşalır.
        latest = _result_for(result["job_id"])
        if latest is None or history_store.load_result(result["job_id"]) is None:
            raise RuntimeError("Tarama sırasında akademisyen profili silindi.")
        warnings = list(source_warnings)
        return {**latest, "collection_warnings": warnings}

    task = _UNIT_PERSON_TASKS.get(key)
    if task is None:
        task = asyncio.create_task(collect())
        _UNIT_PERSON_TASKS[key] = task
    try:
        return await asyncio.shield(task)
    finally:
        if on_update in subscribers:
            subscribers.remove(on_update)
        if task.done() and _UNIT_PERSON_TASKS.get(key) is task:
            _UNIT_PERSON_TASKS.pop(key, None)
            if _UNIT_PERSON_UPDATES.get(key) is subscribers:
                _UNIT_PERSON_UPDATES.pop(key, None)


class UnitIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    refresh: bool = False


class UnitPapersIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    level: str = Field(default="department", pattern="^(department|faculty)$")
    name: str = Field(default="", max_length=300)
    refresh: bool = False


def _check_url(url: str):
    if not url.startswith(("http://", "https://")):
        raise HTTPException(422, "Geçerli bir http(s) adresi girin.")


async def _directory_call(coro):
    try:
        return await asyncio.wait_for(coro, timeout=150)
    except TimeoutError:
        raise HTTPException(504, "Site zamanında yanıt vermedi; biraz sonra tekrar deneyin.") from None
    except RuntimeError as exc:
        raise HTTPException(502, redact(str(exc))) from None


@app.post("/api/directory/faculties")
async def directory_faculties(body: UnitIn):
    _check_url(body.url)
    return await _directory_call(directory.faculties(body.url, await _llm(), body.refresh))


@app.post("/api/directory/departments")
async def directory_departments(body: UnitIn):
    _check_url(body.url)
    return await _directory_call(directory.departments(body.url, await _llm(), body.refresh))


@app.post("/api/directory/staff")
async def directory_staff(body: UnitIn):
    _check_url(body.url)
    data = await _directory_call(directory.staff(body.url, await _llm(), body.refresh))
    institution = directory.load(registrable(urlparse(body.url).hostname or "")).get("name", "")
    return {**data, "items": _staff_metrics(data["items"], institution)}


@app.post("/api/directory/papers")
async def directory_papers(body: UnitPapersIn):
    """Kayıtlı birimi göster; yalnız ilk açılışta veya açık yenilemede tara."""
    _check_url(body.url)
    unit = f"site:{body.level}:{body.url}"
    saved = unit_publications.cached_unit(unit)
    if saved is not None and saved.get("status") == "running":
        return _unit_publication_result(saved)
    llm = await _llm()
    domain = registrable(urlparse(body.url).hostname or "")

    async def run():
        people = (await directory.faculty_people(body.url, llm) if body.level == "faculty"
                  else (await directory.staff(body.url, llm))["items"])
        if not people:
            raise RuntimeError("Bu birimde akademisyen listesi bulunamadı.")
        institution = directory.load(domain).get("name", "")
        return _unit_publication_result(_start_unit_collection(people, institution, domain, unit, refresh=body.refresh))

    return await _directory_call(run())


@app.get("/api/firms")
async def firm_list(q: str = "", sector: str = "", city: str = "", area: str = ""):
    """Resmi Ar-Ge / Tasarım Merkezi listesindeki firmalar (marka bazında gruplu)."""
    return await asyncio.to_thread(firms.firm_list, q[:100], sector[:120], city[:60], area[:120])


@app.get("/api/firms/{fid}")
async def firm_detail(fid: str, refresh: bool = False, quick: bool = False):
    """Firma → akademisyenler: OpenAlex/TR Dizin ortak yayınları ve çıkarılmış profillerdeki iş birlikleri."""
    if not re.fullmatch(r"[a-z0-9-]{1,80}", fid):
        raise HTTPException(422, "Geçersiz firma kimliği.")
    d = await firms.firm_snapshot(fid, refresh) if quick else await firms.firm_detail(fid, refresh)
    if not d:
        raise HTTPException(404, "Firma resmi listede bulunamadı.")
    return d


class FirmChatIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    messages: list[dict] = Field(default_factory=list, max_length=10)


@app.get("/api/firms/{fid}/facts")
async def firm_facts_route(fid: str, refresh: bool = False):
    """Firma künyesi: kuruluş, çalışan, ciro, merkez, sektör (Vikipedi/Wikidata) ve resmî Ar-Ge listesi."""
    if not re.fullmatch(r"[a-z0-9-]{1,80}", fid):
        raise HTTPException(422, "Geçersiz firma kimliği.")
    d = await firm_facts.facts(fid, refresh)
    if not d:
        raise HTTPException(404, "Firma resmi listede bulunamadı.")
    return d


@app.post("/api/firms/{fid}/chat")
async def firm_chat(fid: str, body: FirmChatIn):
    if not re.fullmatch(r"[a-z0-9-]{1,80}", fid):
        raise HTTPException(422, "Geçersiz firma kimliği.")
    msgs = [{"role": str(m.get("role", ""))[:12], "content": str(m.get("content", ""))[:1500]} for m in body.messages]
    return await firm_facts.answer(fid, _llm, body.question.strip(), msgs)


@app.get("/api/firms/{fid}/patents")
async def firm_patents(fid: str, refresh: bool = False):
    """Firmanın başvuru sahibi olduğu patentler (EPO Open Patent Services)."""
    if not re.fullmatch(r"[a-z0-9-]{1,80}", fid):
        raise HTTPException(422, "Geçersiz firma kimliği.")
    d = await firms.firm_patents(fid, refresh)
    if d is None:
        raise HTTPException(404, "Firma resmi listede bulunamadı.")
    return d


@app.get("/api/patents/description")
async def patent_description(n: list[str] = Query(default=[])):
    """Bir patent ailesinin açıklama metni (EP/WO tam metni); yayın numaraları: "WO2017030512 A1"."""
    numbers = [x for x in n[:12] if re.fullmatch(r"[A-Z]{2}\d{4,14} ?[A-Z]\d?", x)]
    if not numbers:
        raise HTTPException(422, "Geçersiz patent numarası.")
    if not patents.enabled():
        raise HTTPException(503, "EPO anahtarı tanımlı değil.")
    try:
        return await patents.description(numbers)
    except patents.PatentError as exc:
        raise HTTPException(503, str(exc)) from None
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"EPO'ya ulaşılamadı ({type(exc).__name__}).") from None


@app.get("/api/patents/document")
async def patent_document(n: list[str] = Query(default=[])):
    """Patent ailesinin özgün belgesi (taranmış sayfa sayısı); sayfalar /api/patents/page/… ile gelir."""
    numbers = [x for x in n[:12] if re.fullmatch(r"[A-Z]{2}\d{4,14} ?[A-Z]\d?", x)]
    if not numbers:
        raise HTTPException(422, "Geçersiz patent numarası.")
    if not patents.enabled():
        raise HTTPException(503, "EPO anahtarı tanımlı değil.")
    try:
        return await patents.document(numbers)
    except patents.PatentError as exc:
        raise HTTPException(503, str(exc)) from None
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"EPO'ya ulaşılamadı ({type(exc).__name__}).") from None


@app.get("/api/patents/page/{pub}/{n}.png")
async def patent_page(pub: str, n: int):
    if not re.fullmatch(r"[A-Z]{2}\d{4,14}[A-Z]\d?", pub) or not 1 <= n <= 500:
        raise HTTPException(422, "Geçersiz sayfa.")
    if not patents.enabled():
        raise HTTPException(503, "EPO anahtarı tanımlı değil.")
    try:
        png = await patents.page(pub, n)
    except patents.PatentError as exc:
        raise HTTPException(404 if "bulunamadı" in str(exc) else 503, str(exc)) from None
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"EPO'ya ulaşılamadı ({type(exc).__name__}).") from None
    return Response(png, media_type="image/png", headers={"Cache-Control": "public, max-age=604800"})


@app.get("/api/firms/{fid}/teydeb")
async def firm_teydeb(fid: str, refresh: bool = False):
    """Firmanın TÜBİTAK TEYDEB tamamlanmış projeleri (PRODİS, Açık Bilim)."""
    if not re.fullmatch(r"[a-z0-9-]{1,80}", fid):
        raise HTTPException(422, "Geçersiz firma kimliği.")
    d = await firms.firm_teydeb(fid, refresh)
    if d is None:
        raise HTTPException(404, "Firma resmi listede bulunamadı.")
    return d


@app.get("/api/tubitak/ardeb")
async def tubitak_ardeb(q: str = ""):
    if len(q.strip()) < 3:
        raise HTTPException(422, "En az 3 karakter yazın.")
    return await firms.tubitak_ardeb(q.strip()[:120])


@app.get("/api/tubitak/teydeb")
async def tubitak_teydeb(q: str = ""):
    if len(q.strip()) < 3:
        raise HTTPException(422, "En az 3 karakter yazın.")
    return await firms.tubitak_teydeb(q.strip()[:120])


@app.get("/api/topics/trending")
async def topics_trending(cat: str = ""):
    """Türkiye gündemi: son 12 ayda en hızlı büyüyen konular (OpenAlex). cat verilirse o alanın gündemi."""
    if cat and cat not in reading.CATEGORIES:
        raise HTTPException(404, "Kategori bulunamadı.")
    try:
        return {"items": await reading.trending(12 if cat else 14, llm=await LLM().probe(), cat=cat)}
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"OpenAlex'e ulaşılamadı ({type(exc).__name__}).") from None


@app.get("/api/topic-works")
async def topic_works(id: str = "", q: str = ""):
    """Raftaki bir konu kitabının içi: gündem konusu (OpenAlex kimliği) ya da aranmış konu (metin)."""
    q = q.strip()[:160]
    en = ""
    if q and not id and not q.isascii():
        try:
            en = await asyncio.wait_for(library._translate(q, await LLM().probe()), 25)
        except Exception:  # noqa: BLE001  çeviri yoksa Türkçe metinle aranır
            en = ""
    try:
        return await reading.topic_works(id, q, en)
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"OpenAlex'e ulaşılamadı ({type(exc).__name__}).") from None


@app.get("/api/reading")
async def reading_categories():
    return {"items": reading.categories()}


@app.get("/api/reading/{cat}")
async def reading_shelf(cat: str):
    """Okuma köşesi rafı: alanda Türkiye adresli, açık erişimli, çok atıf alan güncel yayınlar."""
    try:
        d = await reading.shelf(cat)
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"OpenAlex'e ulaşılamadı ({type(exc).__name__}).") from None
    if not d:
        raise HTTPException(404, "Raf bulunamadı.")
    return d


@app.get("/api/paper/brief")
async def paper_brief(doi: str = ""):
    """Kütüphane okuma sayfası: özet ve yazar–kurum listesi (Türk üniversiteleri eşlenmiş)."""
    if not doi or len(doi) > 300:
        raise HTTPException(422, "DOI gerekli.")
    try:
        abstract, items = await asyncio.gather(reading.abstract_of(doi), reading.authorships(doi))
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"OpenAlex'e ulaşılamadı ({type(exc).__name__}).") from None
    return {"abstract": abstract, "items": items}


@app.get("/api/paper/authors")
async def paper_authors(doi: str = ""):
    """Makalenin yazarları ve kurumları; Türk üniversiteleri üniversite sayfasına bağlanır."""
    if not doi or len(doi) > 300:
        raise HTTPException(422, "DOI gerekli.")
    try:
        return {"items": await reading.authorships(doi)}
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"OpenAlex'e ulaşılamadı ({type(exc).__name__}).") from None


@app.get("/api/pdf")
async def pdf_reader(url: str = "", doi: str = ""):
    """Uygulama içi okuyucu için PDF: yalnız herkese açık adres; kapalıysa aynı DOI'nin açık erişim kopyası."""
    if len(url) > 2000 or len(doi) > 300 or not (url or doi):
        raise HTTPException(422, "Geçersiz istek.")
    try:
        raw, final = await reading.pdf(url, doi)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from None
    return Response(raw, media_type="application/pdf", headers={
        "Content-Disposition": "inline", "X-Source-Url": final[:500], "Cache-Control": "private, max-age=3600"})


@app.get("/api/universities")
async def universities():
    """YÖK'teki tüm üniversiteler; incelenen akademisyenler kurum adına göre yanlarında."""
    try:
        unis = await yokdir.university_list()
        tokens = await patents._universities()
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"YÖK'e ulaşılamadı ({type(exc).__name__}).") from None
    people: dict[str, list] = {}
    for c in history_store.list_all():
        uni = patents._university_of(c.get("institution") or "", tokens)
        if uni:
            people.setdefault(uni, []).append({"name": c["name"], "chat_id": c["id"], "title": c.get("title")})
    return {"items": [{"id": u["id"], "name": u["name"], "people": people.get(u["raw"], [])} for u in unis]}


@app.get("/api/universities/{uid}")
async def university(uid: str):
    """Üniversitenin fakülteleri (YÖK kurum dizini; kurum sitesi bağlantısı gerekmez)."""
    if not re.fullmatch(r"[a-z0-9-]{1,120}", uid):
        raise HTTPException(422, "Geçersiz üniversite.")
    try:
        d = await yokdir.university_detail(uid)
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"YÖK'e ulaşılamadı ({type(exc).__name__}).") from None
    if not d:
        raise HTTPException(404, "Üniversite YÖK listesinde bulunamadı.")
    return d


@app.get("/api/universities/{uid}/student")
async def university_student(uid: str, refresh: bool = False, section: str | None = None,
                             faculty: str = Query(default="", max_length=200),
                             department: str = Query(default="", max_length=200)):
    if section is not None and section not in student_view.GROUPS:
        raise HTTPException(422, "Geçerli bir öğrenci bilgisi başlığı seçin.")
    if not re.fullmatch(r"[a-z0-9-]{1,120}", uid) or not await yokdir._university(uid):
        raise HTTPException(404, "Üniversite bulunamadı.")
    # Model bağlantısı yalnız yeni bir başlık gerçekten taranacaksa hazırlanır.
    return await student_view.get(uid, _llm, refresh, section=section, faculty=faculty, department=department)


@app.get("/api/universities/{uid}/student/preview")
async def university_student_preview(uid: str, url: str):
    """Öğrenci bakışındaki resmî bağlantının içerik özeti (yalnız kurum alan adı)."""
    if not re.fullmatch(r"[a-z0-9-]{1,120}", uid) or len(url) > 2000:
        raise HTTPException(422, "Geçersiz istek.")
    try:
        return await student_view.preview(uid, url)
    except (ValueError, httpx.HTTPError, OSError, asyncio.TimeoutError) as exc:
        raise HTTPException(422, str(exc)[:200] or "Bağlantı okunamadı.") from None


@app.get("/api/universities/{uid}/student/program")
async def university_student_program(uid: str, url: str):
    """OIBS Bologna program profili, mezun iş alanları ve üst kademe bilgisi (yalnız kurum alan adı)."""
    if not re.fullmatch(r"[a-z0-9-]{1,120}", uid) or len(url) > 2000:
        raise HTTPException(422, "Geçersiz istek.")
    try:
        return await student_view.program(uid, url)
    except (ValueError, httpx.HTTPError, OSError, asyncio.TimeoutError) as exc:
        raise HTTPException(422, str(exc)[:200] or "Program bilgisi okunamadı.") from None


@app.post("/api/universities/{uid}/student/chat")
async def university_student_chat(uid: str, body: StudentChatIn):
    if not body.question.strip():
        raise HTTPException(422, "Öğrenci asistanına bir soru yazın.")
    if body.section is not None and body.section not in student_view.GROUPS:
        raise HTTPException(422, "Geçerli bir öğrenci bilgisi başlığı seçin.")
    if not re.fullmatch(r"[a-z0-9-]{1,120}", uid):
        raise HTTPException(404, "Üniversite bulunamadı.")
    try:
        university = await asyncio.wait_for(yokdir._university(uid), 12)
    except (TimeoutError, httpx.HTTPError):
        return student_assistant.unavailable("Üniversite kaydı şu anda doğrulanamıyor. Lütfen biraz sonra tekrar deneyin.")
    if not university:
        raise HTTPException(404, "Üniversite bulunamadı.")
    return await student_assistant.answer(
        uid, university, _llm, question=body.question.strip(),
        messages=[message.model_dump() for message in body.messages], section=body.section,
        faculty=body.faculty, department=body.department)


@app.get("/api/universities/{uid}/summary")
async def university_summary(uid: str):
    """Önizleme kartı için fakülte/bölüm sayıları (bölümler yalnız taranmış fakültelerden)."""
    if not re.fullmatch(r"[a-z0-9-]{1,120}", uid):
        raise HTTPException(422, "Geçersiz üniversite.")
    try:
        d = await yokdir.unit_summary(uid)
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"YÖK'e ulaşılamadı ({type(exc).__name__}).") from None
    if not d:
        raise HTTPException(404, "Üniversite YÖK listesinde bulunamadı.")
    return d


@app.get("/api/universities/{uid}/facts")
async def university_facts(uid: str, refresh: bool = False):
    """Kurum künyesi: kimlik (Vikipedi/Wikidata), kadro sayıları (YÖK Akademik), araştırma (OpenAlex)."""
    if not re.fullmatch(r"[a-z0-9-]{1,120}", uid):
        raise HTTPException(422, "Geçersiz üniversite.")
    d = await uni_facts.facts(uid, refresh)
    if not d:
        raise HTTPException(404, "Üniversite YÖK listesinde bulunamadı.")
    return d


@app.get("/api/universities/{uid}/staff-counts")
async def university_staff_counts(uid: str):
    """YÖK Akademik kadro sayıları (toplam ve unvan); büyük üniversitelerde ilk okuma yarım dakikayı bulabilir."""
    if not re.fullmatch(r"[a-z0-9-]{1,120}", uid):
        raise HTTPException(422, "Geçersiz üniversite.")
    try:
        d = await uni_facts.staff_counts(uid)
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, f"YÖK Akademik okunamadı ({type(exc).__name__}).") from None
    if not d:
        raise HTTPException(404, "Üniversite YÖK listesinde bulunamadı.")
    return d


@app.get("/api/universities/{uid}/roles")
async def university_roles(uid: str, name: str = ""):
    """Fakültede süren idari görevler (dekan, bölüm başkanı); yalnız önbellekteki kadro için."""
    if not re.fullmatch(r"[a-z0-9-]{1,120}", uid) or not name or len(name) > 200:
        raise HTTPException(422, "Geçersiz istek.")
    d = await uni_facts.faculty_roles(uid, name)
    if d is None:
        raise HTTPException(404, "Üniversite YÖK listesinde bulunamadı.")
    return d


@app.get("/api/universities/{uid}/faculty")
async def university_faculty(uid: str, name: str = "", metrics: bool = True):
    """Fakülte kadrosu ve bölümleri (kişilerin YÖK kurum yolundan). İlk açılış birkaç saniye, sonra önbellekten."""
    if not re.fullmatch(r"[a-z0-9-]{1,120}", uid) or not name:
        raise HTTPException(422, "Geçersiz istek.")
    d = await _directory_call(yokdir.faculty_detail(uid, name[:200]))
    if not d:
        raise HTTPException(502, "Bu birimin kadrosu YÖK'ten alınamadı. Biraz sonra tekrar deneyin.")
    # Öğrenci dizini için bütün kayıtlı profillerin yayın/atıf metriklerini okumaya gerek yok.
    return {**d, "people": _staff_metrics(d["people"], d["university"]) if metrics else d["people"]}


class YokPapersIn(BaseModel):
    uid: str = Field(max_length=120)
    faculty: str = Field(max_length=200)
    department: str | None = Field(default=None, max_length=200)  # None: tüm fakülte
    refresh: bool = False


@app.post("/api/universities/papers")
async def university_papers(body: YokPapersIn):
    """Kayıt varsa ağ taraması yapmadan döner; yenileme kullanıcı isteğiyle başlar."""
    unit = f"{body.uid}|{body.faculty}|{body.department if body.department is not None else '*'}"
    saved = unit_publications.cached_unit(unit)
    if saved is not None and saved.get("status") == "running":
        return _unit_publication_result(saved)

    async def run():
        fac = await yokdir.faculty_detail(body.uid, body.faculty)
        if not fac:
            raise RuntimeError("Bu birimin kadrosu YÖK'ten alınamadı.")
        people = [p for p in fac["people"] if body.department is None or p["department"] == body.department]
        if not people:
            raise RuntimeError("Bu birimde akademisyen listesi bulunamadı.")
        return _unit_publication_result(_start_unit_collection(people, fac["university"], fac["domain"], unit, refresh=body.refresh))

    return await _directory_call(run())


def _unit_publication_result(data: dict) -> dict:
    quartiles.annotate(data["papers"])
    wos.annotate(data["papers"])
    publication_status.annotate(data["papers"])
    return data


@app.post("/api/units/papers/{job_id}/people/{person_key:path}")
async def unit_person_refresh(job_id: str, person_key: str):
    """Birimdeki tek kişiyi tarar (satırdaki Yenile düğmesi); WoS çalışmaz."""
    async def collect(person, institution, domain, *, on_update=None):
        return await _collect_unit_person(person, institution, domain, on_update=on_update, refresh=True)

    data = unit_publications.refresh_person(job_id, person_key[:200], collect)
    if data is None:
        raise HTTPException(404, "Birim ya da kişi bulunamadı; birimi yeniden açın.")
    return _unit_publication_result(data)


@app.get("/api/units/papers/{job_id}")
async def unit_papers_status(job_id: str):
    data = unit_publications.snapshot(job_id)
    if data is None:
        raise HTTPException(404, "Birim taraması bulunamadı; birimi yeniden açın.")
    return _unit_publication_result(data)


@app.get("/api/people/search")
async def people_search(q: str = ""):
    """YÖK'te ad araması: aynı adlı kişiler seçim için. Tarayıcı açmaz, ~1-2 sn."""
    if len(fold(q)) < 3:
        raise HTTPException(422, "En az 3 harf yazın.")
    try:
        return {"items": await yokdir.search_people(q[:120])}
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"YÖK'e ulaşılamadı ({type(exc).__name__}). Biraz sonra tekrar deneyin.") from None


@app.get("/api/overview")
async def overview():
    """Ana sayfa sayaçları."""
    try:
        unis = len(await yokdir.university_list())
    except httpx.HTTPError:
        unis = 0
    return {"universities": unis, "firms": firms.firm_list().get("total", 0), "profiles": len(history_store.list_all())}


@app.get("/api/lookup")
async def lookup(q: str = ""):
    """Ana sayfa arama kutusu: üniversite, firma ve incelenmiş akademisyen önerileri (yalnız yerel listeler)."""
    fq = fold(q[:100])
    if len(fq) < 2:
        return {"people": [], "universities": [], "firms": []}
    try:
        unis = await yokdir.university_list()
    except httpx.HTTPError:
        unis = []
    # Adı sorguyla başlayanlar öne; her gruptan birkaç öneri yeter, asıl arama aşağıdaki eylemlerle yapılır.
    starts = lambda x: not fold(x["name"]).startswith(fq)
    people = [c for c in history_store.list_all() if word_match(q[:100], c.get("name") or "")][:4]
    unis = sorted((u for u in unis if word_match(q[:100], u["name"])), key=starts)[:4]
    found = sorted(firms.firm_list(q[:100])["items"], key=starts)[:3]
    return {"people": [{k: c.get(k) for k in ("id", "job_id", "name", "title", "institution")} for c in people],
            "universities": [{"id": u["id"], "name": u["name"]} for u in unis],
            "firms": [{"id": f["id"], "name": f["name"], "cities": f["cities"][:2]} for f in found]}


# ------------------------------------------------------------------ favoriler
class FavIn(BaseModel):
    item: dict


@app.get("/api/favorites")
async def favorites_get():
    return library.favorites()


@app.post("/api/favorites/papers")
async def favorites_add_paper(body: FavIn):
    if not body.item.get("title"):
        raise HTTPException(422, "Başlık gerekli.")
    return library.add_paper(body.item)


@app.delete("/api/favorites/papers/{key:path}")
async def favorites_del_paper(key: str):
    return {"deleted": library.remove_paper(key)}


@app.post("/api/favorites/people")
async def favorites_add_person(body: FavIn):
    if not body.item.get("name"):
        raise HTTPException(422, "Ad gerekli.")
    return library.add_person(body.item)


@app.delete("/api/favorites/people/{key:path}")
async def favorites_del_person(key: str):
    return {"deleted": library.remove_person(key)}


# ------------------------------------------------------------------ konu araması
@app.post("/api/favorites/{kind}")
async def favorites_add_org(kind: str, body: FavIn):
    if kind not in {"universities", "firms"}:
        raise HTTPException(404)
    oid = str(body.item.get("id") or "")
    if kind == "universities":
        item = next((u for u in await yokdir.university_list() if u["id"] == oid), None)
    else:
        group = firms._groups().get(oid)
        item = firms._public(oid, group) if group else None
    if not item:
        raise HTTPException(404, "Kurum kaydı bulunamadı.")
    return library.add_org(kind, item)


@app.delete("/api/favorites/{kind}/{key:path}")
async def favorites_del_org(kind: str, key: str):
    if kind not in {"universities", "firms"}:
        raise HTTPException(404)
    return {"deleted": library.remove_org(kind, key)}


@app.get("/api/organization-logo/{kind}/{oid}")
async def organization_logo(kind: str, oid: str):
    entry = await org_assets.logo(kind, oid)
    if not entry.get("data"):
        return Response(status_code=404, headers={"Cache-Control": "private, max-age=600"})
    return Response(base64.b64decode(entry["data"]), media_type=entry["type"], headers={
        "Cache-Control": "public, max-age=604800", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox"})


@app.get("/api/search")
async def topic_search(q: str = "", sources: str | None = None):
    if len(q.strip()) < 3:
        raise HTTPException(422, "En az 3 karakterlik bir konu yazın.")
    selected = None if sources is None else {x.strip() for x in sources.split(",") if x.strip()}
    if selected is not None and (not selected or selected - library.TOPIC_SOURCES):
        raise HTTPException(422, "En az bir geçerli yayın kaynağı seçin.")
    return await library.topic_search(q[:200], await _llm(), sources=selected)


@app.get("/api/search/{search_id}")
async def topic_search_status(search_id: str):
    data = library.topic_snapshot(search_id)
    if data is None:
        raise HTTPException(404, "Arama sonucu bulunamadı; aramayı yeniden başlatın.")
    return data


class PaperIn(BaseModel):
    paper: dict


GENERIC_PAPER_CACHE: dict = {}


@app.post("/api/paper")
async def paper_any(body: PaperIn):
    """Arama sonucu ya da favorideki bir yayının ayrıntısı (profil işine bağlı olmadan)."""
    p = body.paper
    if not p.get("title"):
        raise HTTPException(422, "Başlık gerekli.")
    item = {"id": library.paper_key(p), "title": p["title"], "doi": p.get("doi") or "", "url": p.get("url") or "",
            "year": p.get("year"), "venue": p.get("venue") or "", "authors": p.get("authors") or [],
            "abstract": p.get("abstract") or "", "source": p.get("source") or "akademik kaynak"}
    return _paper_stream(item, await _llm(), GENERIC_PAPER_CACHE, None, f"yayın {item['id']}")
