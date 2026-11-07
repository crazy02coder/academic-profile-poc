"""Akademik İz — FastAPI uygulaması: iş hattı, SSE canlı log ve profil sohbeti."""
from __future__ import annotations

import asyncio
import base64
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

from . import rea, recipes
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

from . import directory, firms, industry, library, patents, publication_status, quartiles, trsources, unit_publications, wos, wos_enrichment, wos_verification, yokdir

app = FastAPI(title="Akademik İz")
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


def _emit(job: dict, event: dict):
    event["t"] = round(time.time() - job["started"], 1)
    job["events"].append(event)


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

        # YÖK'ü beklemeyenler hemen başlar: Scholar ve Tez Merkezi yalnız adı kullanır; TR Dizin ve OpenAIRE sayfaları
        # şimdi çeker, kişiyle eşleştirmeyi YÖK'ün netleştirdiği ad/ORCID gelince (identity_ready) yapar.
        identity_ready = asyncio.Event()
        scholar_task = asyncio.create_task(scholar_works(profile, log))
        early = [asyncio.create_task(trsources.trdizin_works(profile, log, identity_ready)),
                 asyncio.create_task(trsources.openaire_works(profile, log, identity_ready)),
                 asyncio.create_task(trsources.tez_works(profile, log))]

        # Faz A: kimlik çözümleme + YÖK yayınları (ORCID burada netleşebilir)
        await log("yok", "running", "YÖK Akademik: Scrapling StealthySession açılıyor, REA CDP ile bağlanacak.")
        try:
            yok_records, yok_rea = await asyncio.wait_for(yok_works(profile, log), timeout=150)
            await log("yok", "done", f"YÖK: {len(yok_records)} kayıt.")
        except Exception as exc:  # noqa: BLE001
            yok_records = []
            await log("yok", "warning", f"YÖK atlandı ({type(exc).__name__}); akış devam ediyor.")
        finally:
            identity_ready.set()

        # Faz B: açık API'ler + Scholar paralel
        await log("publications", "running", "Paralel: OpenAlex, Crossref, ORCID, TR Dizin, OpenAIRE (DergiPark, üniversite "
                                             "arşivleri), YÖK Tez Merkezi; Scholar best-effort.")
        # YÖK unvan/bölümü çoğu zaman verir; sayfa metninden LLM tamamlaması yalnız hâlâ eksik kalanlar için,
        # API sorgularıyla paralel çalışır.
        labels = ("OpenAlex", "Crossref", "ORCID", "Scholar", "TR Dizin", "OpenAIRE", "Tez Merkezi")
        tasks = await asyncio.gather(openalex_works(profile, log), crossref_works(profile, log),
                                     orcid_works(profile, log), scholar_task, *early, llm_enrich(profile, llm, log),
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
        _emit(job, {"type": "result", "data": result})
    except Exception as exc:  # noqa: BLE001
        _emit(job, {"type": "error", "message": f"İş tamamlanamadı: {type(exc).__name__}: {redact(str(exc))[:200]}"})
    finally:
        job["done"] = True
        _emit(job, {"type": "end"})


@app.get("/")
async def index():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/health")
async def health():
    llm = await LLM().probe()
    return {"rea": rea.available(), "chromium": bool(chromium_executable()), "llm": llm.label(),
            "llm_ready": llm.available, "steps": STEPS, "patents": patents.enabled()}


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
async def refresh_job(jid: str):
    """Kayıtlı profili kaynaklardan baştan toplar (yeni yayınlar, eksik fotoğraf, güncellenen ayrıştırma kodu)."""
    old = _result_for(jid)
    if not old:
        raise HTTPException(404, "Profil sonucu bulunamadı.")
    running = next((j for j in JOBS.values() if (j.get("refresh") or {}).get("job_id") == jid and not j["done"]), None)
    if running:
        return {"id": running["id"], "steps": STEPS}
    inp, prof = old.get("input") or {}, old["profile"]
    url = next((u for u in (inp.get("url"), prof.get("source_url"), (old.get("recon") or {}).get("start_url"))
                if isinstance(u, str) and u.startswith(("http://", "https://"))), "")
    yok_url = inp.get("yok_url") or (prof.get("links") or {}).get("yok") or ""
    if not url and not yok_url:
        raise HTTPException(422, "Bu kayıtta başlangıç bağlantısı yok; akademisyeni yeniden arayın.")
    data = JobIn(url=url, name=inp.get("name") or prof.get("name") or prof.get("query_name") or "", yok_url=yok_url,
                 university=inp.get("university") or "", department=inp.get("department") or "", email=inp.get("email") or "")
    return _start(data, {"job_id": jid, "chat_id": old.get("chat_id")})


def _start(data: JobIn, refresh: dict | None = None) -> dict:
    for jid in [k for k, v in JOBS.items() if v["done"] and time.time() - v["started"] > 3600]:
        JOBS.pop(jid, None)
    jid = uuid.uuid4().hex[:12]
    job = {"id": jid, "events": [], "done": False, "started": time.time(), "result": None, "refresh": refresh,
           "input": data.model_dump()}
    JOBS[jid] = job
    job["task"] = asyncio.create_task(pipeline(job, data))
    return {"id": jid, "steps": STEPS}


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
    """Profil fotoğrafı (YÖK): listelerde küçük resim; kayıtta yoksa 404, arayüz baş harfleri gösterir."""
    result = _result_for(jid)
    m = re.fullmatch(r"data:(image/[a-z+]+);base64,(.+)", ((result or {}).get("profile", {}).get("yok") or {}).get("photo") or "", re.S)
    if not m:
        raise HTTPException(404)
    return Response(base64.b64decode(m.group(2)), media_type=m.group(1), headers={"Cache-Control": "public, max-age=86400"})


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
    return wos_verification.get_active()


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
                    started = await refresh_job(result["job_id"])
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
                    started = _start(data)
                running = JOBS[started["id"]]
            await asyncio.shield(running["task"])
            result = running.get("result")
            if not result:
                message = next((e.get("message") for e in reversed(running["events"]) if e["type"] == "error"), None)
                raise RuntimeError(message or "Akademisyen profili toplanamadı.")
            source_warnings = [e["message"] for e in running["events"] if e.get("step") in {"yok", "publications"}
                               and e.get("status") == "warning"]
        publish(result)
        jid = result["job_id"]
        state = await start_wos(jid, retry=refresh)
        # Publication collection is sufficient. Per-journal JCR checks continue
        # in the shared profile task without holding up the entire unit.
        publication_revision = result.get("wos_revision")
        while state.get("status") == "running" and ("publications" not in state or
                state["publications"].get("complete") is False):
            await asyncio.sleep(1)
            if history_store.load_result(jid) is None:
                raise RuntimeError("Tarama sırasında akademisyen profili silindi.")
            current = _result_for(jid) or result
            state = wos.snapshot(current)
            if current.get("wos_revision") != publication_revision:
                publication_revision = current.get("wos_revision")
                publish(current)
        latest = _result_for(jid)
        if latest is None or history_store.load_result(jid) is None:
            raise RuntimeError("Tarama sırasında akademisyen profili silindi.")
        report = state.get("publications") or {}
        warnings = list(source_warnings)
        if state.get("status") in {"blocked", "error", "cancelled"} or report.get("status") in {"partial", "blocked", "error"}:
            warnings.append("WoS taraması tamamlanamadı; erişilen kaynakların yayınları gösteriliyor.")
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
    if saved is not None and (not body.refresh or saved.get("status") == "running"):
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
    return firms.firm_list(q[:100], sector[:120], city[:60], area[:120])


@app.get("/api/firms/{fid}")
async def firm_detail(fid: str, refresh: bool = False):
    """Firma → akademisyenler: OpenAlex/TR Dizin ortak yayınları ve çıkarılmış profillerdeki iş birlikleri."""
    if not re.fullmatch(r"[a-z0-9-]{1,80}", fid):
        raise HTTPException(422, "Geçersiz firma kimliği.")
    d = await firms.firm_detail(fid, refresh)
    if not d:
        raise HTTPException(404, "Firma resmi listede bulunamadı.")
    return d


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


@app.get("/api/universities/{uid}/faculty")
async def university_faculty(uid: str, name: str = ""):
    """Fakülte kadrosu ve bölümleri (kişilerin YÖK kurum yolundan). İlk açılış birkaç saniye, sonra önbellekten."""
    if not re.fullmatch(r"[a-z0-9-]{1,120}", uid) or not name:
        raise HTTPException(422, "Geçersiz istek.")
    d = await _directory_call(yokdir.faculty_detail(uid, name[:200]))
    if not d:
        raise HTTPException(502, "Bu birimin kadrosu YÖK'ten alınamadı. Biraz sonra tekrar deneyin.")
    return {**d, "people": _staff_metrics(d["people"], d["university"])}


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
    if saved is not None and (not body.refresh or saved.get("status") == "running"):
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
@app.get("/api/search")
async def topic_search(q: str = ""):
    if len(q.strip()) < 3:
        raise HTTPException(422, "En az 3 karakterlik bir konu yazın.")
    return await library.topic_search(q[:200], await _llm())


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
