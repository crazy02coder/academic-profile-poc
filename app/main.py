"""Akademik İz — FastAPI uygulaması: iş hattı, SSE canlı log ve profil sohbeti."""
from __future__ import annotations

import asyncio
import logging
import re
import json
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
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
from .text import detect_title
from .dedup import resolve
from .discover import llm_enrich, locate, registrable
from .llm import LLM
from .sources import crossref_works, openalex_works, orcid_works, scholar_works, yok_works
import httpx

from . import directory, firms, industry, library, patents, trsources

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
    url: str = Field(default="", max_length=2000)
    name: str = Field(min_length=2, max_length=160)


class ChatIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    chat_id: str = ""
    mode: str = "auto"  # auto | rag | cag | hybrid


def _emit(job: dict, event: dict):
    event["t"] = round(time.time() - job["started"], 1)
    job["events"].append(event)


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
        profile, report = await locate(data.url.strip(), name, log, llm)
        await log("scrape", "done" if profile.found else "warning",
                  f"{profile.name or data.name} · {profile.get('title', 'unvan ?')} · "
                  f"{profile.get('department', 'bölüm ?')}")
        if not any(e.get("step") == "crawl" for e in job["events"]):
            await log("crawl", "done", "Gezinmeye gerek kalmadı: kişi başlangıç sayfasında veya hafızada bulundu.")
        if profile.links.get("orcid"):
            profile.observe("orcid", profile.links["orcid"], "university", profile.source_url)

        # Scholar ORCID'e ihtiyaç duymaz ve en yavaş kaynaktır: YÖK'le aynı anda başlar.
        scholar_task = asyncio.create_task(scholar_works(profile, log))

        # Faz A: kimlik çözümleme + YÖK yayınları (ORCID burada netleşebilir)
        await log("yok", "running", "YÖK Akademik: Scrapling StealthySession açılıyor, REA CDP ile bağlanacak.")
        try:
            yok_records, yok_rea = await asyncio.wait_for(yok_works(profile, log), timeout=150)
            await log("yok", "done", f"YÖK: {len(yok_records)} kayıt.")
        except Exception as exc:  # noqa: BLE001
            yok_records = []
            await log("yok", "warning", f"YÖK atlandı ({type(exc).__name__}); akış devam ediyor.")

        # Faz B: açık API'ler + Scholar paralel
        await log("publications", "running", "Paralel: OpenAlex, Crossref, ORCID, TR Dizin, OpenAIRE (DergiPark, üniversite "
                                             "arşivleri), YÖK Tez Merkezi; Scholar best-effort.")
        # YÖK unvan/bölümü çoğu zaman verir; sayfa metninden LLM tamamlaması yalnız hâlâ eksik kalanlar için,
        # API sorgularıyla paralel çalışır.
        labels = ("OpenAlex", "Crossref", "ORCID", "Scholar", "TR Dizin", "OpenAIRE", "Tez Merkezi")
        tasks = await asyncio.gather(openalex_works(profile, log), crossref_works(profile, log),
                                     orcid_works(profile, log), scholar_task,
                                     trsources.trdizin_works(profile, log), trsources.openaire_works(profile, log),
                                     trsources.tez_works(profile, log), llm_enrich(profile, llm, log),
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
        save_run(fact_key, history, verification, papers)

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
        result["input"] = {"url": data.url, "name": data.name}
        prev = job.get("refresh")
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
            "llm_ready": llm.available, "steps": STEPS}


@app.post("/api/jobs", status_code=202)
async def create_job(data: JobIn):
    if not data.url.startswith(("http://", "https://")):
        raise HTTPException(422, "Geçerli bir http(s) akademik kadro linki girin.")
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
    if not url:
        raise HTTPException(422, "Bu kayıtta başlangıç bağlantısı yok; akademisyeni yeniden arayın.")
    data = JobIn(url=url, name=inp.get("name") or prof.get("name") or prof.get("query_name") or "")
    return _start(data, {"job_id": jid, "chat_id": old.get("chat_id")})


def _start(data: JobIn, refresh: dict | None = None) -> dict:
    for jid in [k for k, v in JOBS.items() if v["done"] and time.time() - v["started"] > 3600]:
        JOBS.pop(jid, None)
    jid = uuid.uuid4().hex[:12]
    job = {"id": jid, "events": [], "done": False, "started": time.time(), "result": None, "refresh": refresh}
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


@app.on_event("shutdown")
async def _close_browsers():
    from .net import close_stealth
    from .google_search import close as close_google

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
        return job["result"]
    try:
        return history_store.load_result(jid)
    except ValueError:
        return None


@app.get("/api/jobs/{jid}/result")
async def job_result(jid: str):
    res = _result_for(jid)
    if not res:
        raise HTTPException(404)
    return res


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
    job = JOBS.get(jid) or {}
    llm = job.get("llm") or await LLM().probe()
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
    job = JOBS.get(jid) or {}
    llm = job.get("llm") or await _llm()
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
class UnitIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    refresh: bool = False


class UnitPapersIn(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    level: str = Field(default="department", pattern="^(department|faculty)$")
    name: str = Field(default="", max_length=300)


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
    return await _directory_call(directory.staff(body.url, await _llm(), body.refresh))


@app.post("/api/directory/papers")
async def directory_papers(body: UnitPapersIn):
    """Bölüm ya da fakültedeki akademisyenlerin yayınları (OpenAlex hızlı liste)."""
    _check_url(body.url)
    llm = await _llm()
    domain = registrable(urlparse(body.url).hostname or "")

    async def run():
        people = (await directory.faculty_people(body.url, llm) if body.level == "faculty"
                  else (await directory.staff(body.url, llm))["items"])
        if not people:
            raise RuntimeError("Bu birimde akademisyen listesi bulunamadı.")
        out = await directory.unit_papers(people, domain, directory.load(domain).get("name", ""))
        return {**out, "people": len(people), "unit": body.name}

    return await _directory_call(run())


@app.get("/api/firms")
async def firm_list(q: str = "", sector: str = "", city: str = ""):
    """Resmi Ar-Ge / Tasarım Merkezi listesindeki firmalar (marka bazında gruplu)."""
    return firms.firm_list(q[:100], sector[:120], city[:60])


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
    known = {u["domain"]: u for u in directory.all_stores()}
    seen_people: dict[str, list] = {}
    for c in history_store.list_all():
        if c.get("institution"):
            seen_people.setdefault(c["institution"], []).append({"name": c["name"], "chat_id": c["id"],
                                                                 "title": c.get("title")})
    return {"directory": sorted(known.values(), key=lambda u: u["updated"], reverse=True),
            "from_profiles": [{"institution": k, "people": v} for k, v in sorted(seen_people.items())]}


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
