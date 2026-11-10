"""Kütüphane v2; mevcut API yanıtlarından bağımsız, ek uçlar."""
from __future__ import annotations
import asyncio
import math
import os
import re
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import quote
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import FileResponse
from starlette.requests import Request as StarletteRequest
import httpx
from . import donations, pdf_resolve, oa_books, reading, library, history
from .config import OPENALEX_PARAMS

router = APIRouter(prefix="/api/library")

@router.get("/resolve-pdf")
async def resolve_pdf(doi: str = Query("", max_length=300), url: str = Query("", max_length=2000)):
    return await pdf_resolve.resolve(doi, url)

@router.get("/thumb")
async def thumb(doi: str = Query("", max_length=300), donation: str = ""):
    if donation:
        record = donations.get(donation)
        path = donations.FILES / f"{donation}.jpg"
    else:
        path = await pdf_resolve.thumbnail(doi) if doi else None
    if not path or not path.exists():
        raise HTTPException(404, "Küçük resim üretilemedi.")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})

@router.post("/donations")
async def add_donation(request: Request):
    # Multipart ayrıştırıcısının diske yazdığı geçici gövde de sınırlandırılır.
    maximum = donations.LIMIT + 256_000
    try:
        if int(request.headers.get("content-length", "0")) > maximum:
            raise HTTPException(413, "En fazla 40 MB PDF yükleyebilirsin.")
    except ValueError:
        raise HTTPException(400, "Geçersiz içerik boyutu") from None
    consumed = 0
    async def limited_receive():
        nonlocal consumed
        message = await request.receive()
        consumed += len(message.get("body", b""))
        if consumed > maximum:
            raise HTTPException(413, "En fazla 40 MB PDF yükleyebilirsin.")
        return message
    limited = StarletteRequest(request.scope, limited_receive)
    try:
        async with limited.form(max_files=1, max_fields=12, max_part_size=maximum) as form:
            file = form.get("file")
            if not file or not hasattr(file, "read"):
                raise HTTPException(400, "PDF dosyası gerekli.")
            fields = {key: str(form.get(key, "")) for key in ["title", "authors", "year", "category", "license", "note"]}
            return await donations.upload(file, fields, request.client.host if request.client else "local")
    except AssertionError:
        raise HTTPException(503, "PDF yüklemek için python-multipart kurulmalı.") from None

@router.get("/donations")
async def list_donations(cat: str = "", q: str = Query("", max_length=200), limit: int = Query(120, ge=1, le=500)):
    return {"items": await asyncio.to_thread(donations.list_items, cat, q, limit)}

@router.get("/donations/{value}")
async def get_donation(value: str):
    return donations.get(value)

@router.get("/donations/{value}/pdf")
async def donation_pdf(value: str):
    donations.get(value)
    path = donations.FILES / f"{value}.pdf"
    if not path.exists(): raise HTTPException(404)
    return FileResponse(path, media_type="application/pdf", headers={"Content-Disposition": "inline", "X-Content-Type-Options": "nosniff"})

@router.delete("/donations/{value}")
async def delete_donation(value: str, request: Request):
    return await donations.remove(value, request.headers.get("X-Owner-Token", ""))

@router.get("/jobs/{value}")
async def job(value: str):
    donations.ident(value)
    if value in donations.JOBS: return donations.JOBS[value]
    record = donations.get(value)
    return {"id": value, "status": record["status"] if record["status"] in {"done", "error"} else "error", "step": "İş tamamlandı" if record["status"] == "done" else "Sunucu yeniden başlatıldı; dosyayı kaldırıp tekrar yükleyebilirsin.", "progress": 100 if record["status"] == "done" else 0}

@router.get("/oa-books")
async def oa(cat: str = "genel", q: str = Query("", max_length=200), limit: int = Query(120, ge=1, le=120)):
    return {"items": await oa_books.books(cat, q, limit)}

@router.get("/oa-books/text")
async def oa_text(url: str = Query(..., max_length=2000)):
    try: return {"text": await oa_books.book_text(url)}
    except (ValueError, httpx.HTTPError): raise HTTPException(404, "Kitap metni alınamadı.") from None

@router.get("/archive")
async def archive():
    return await oa_books.archive()

@router.get("/oa-sources")
async def oa_sources():
    return {"sources": oa_books.status()}

# ------------------------------------------------------------------ pencere dışı: saat ve hava
# Open-Meteo anahtarsız ve ücretsiz; yalnız sabit şehir koordinatı gider, kullanıcı bilgisi gitmez.
WEATHER_AT = (float(os.getenv("LIBRARY_WEATHER_LAT", "39.93")), float(os.getenv("LIBRARY_WEATHER_LON", "32.86")), os.getenv("LIBRARY_WEATHER_CITY", "Ankara"))
_WEATHER: dict = {}

def _weather_kind(code: int) -> str:
    if code in (95, 96, 99): return "storm"
    if code in (71, 73, 75, 77, 85, 86): return "snow"
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82): return "rain"
    if code in (45, 48): return "fog"
    if code == 3: return "overcast"
    if code in (1, 2): return "cloudy"
    return "clear"

@router.get("/weather")
async def weather():
    if _WEATHER.get("at", 0) > time.time() - 900:
        return _WEATHER["value"]
    lat, lon, city = WEATHER_AT
    try:
        async with httpx.AsyncClient(timeout=8, headers={"User-Agent": "AkademikIz/1.0"}) as client:
            r = await client.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": lat, "longitude": lon, "timezone": "Europe/Istanbul", "forecast_days": 1,
                "current": "temperature_2m,weather_code,is_day,cloud_cover,wind_speed_10m,precipitation", "daily": "sunrise,sunset"})
            r.raise_for_status()
            data = r.json()
        cur, daily = data.get("current") or {}, data.get("daily") or {}
        code = int(cur.get("weather_code") or 0)
        value = {"ok": True, "city": city, "code": code, "kind": _weather_kind(code), "temp": cur.get("temperature_2m"),
                 "is_day": bool(cur.get("is_day", 1)), "cloud": cur.get("cloud_cover"), "wind": cur.get("wind_speed_10m"),
                 "precip": cur.get("precipitation"), "sunrise": (daily.get("sunrise") or [""])[0], "sunset": (daily.get("sunset") or [""])[0]}
    except (httpx.HTTPError, ValueError, TypeError):
        value = {"ok": False, "city": city, "kind": "clear"}
    _WEATHER.update(at=time.time() if value["ok"] else time.time() - 600, value=value)
    return value

# ------------------------------------------------------------------ rehber kiosku: kişinin yayınları
@router.get("/person/{job_id}")
async def person(job_id: str, limit: int = Query(12, ge=1, le=40)):
    if not re.fullmatch(r"[A-Za-z0-9_-]{4,64}", job_id):
        raise HTTPException(404)
    result = await asyncio.to_thread(history.load_result, job_id)
    if not result:
        raise HTTPException(404, "Profil kaydı bulunamadı.")
    def num(v):
        try: return int(v or 0)
        except (TypeError, ValueError): return 0
    pubs = result.get("publications") or []
    rows = []
    for p in pubs:
        title = str(p.get("title") or "").strip()
        if not title:
            continue
        q = (p.get("quartile") or {}).get("q") if isinstance(p.get("quartile"), dict) else ""
        rows.append({"title": title, "year": str(p.get("year") or "")[:4], "venue": p.get("venue") or "", "doi": p.get("doi") or "",
                     "url": p.get("url") or "", "citations": num(p.get("citations")), "kind": p.get("publication_kind") or p.get("type") or "",
                     "quartile": q or "", "authors": [str(a) for a in (p.get("authors") or [])[:8]]})
    rows.sort(key=lambda r: (r["year"], r["citations"]), reverse=True)
    prof = result.get("profile") or {}
    kinds = {}
    for r in rows:
        if r["kind"]: kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    return {"total": len(rows), "citations": sum(r["citations"] for r in rows), "q1": sum(1 for r in rows if r["quartile"] == "Q1"),
            "kinds": sorted(kinds.items(), key=lambda kv: -kv[1])[:4], "department": prof.get("department") or "",
            "items": rows[:limit]}

_RECOMMEND = {}
@router.get("/for-you")
async def for_you(recent: str = Query("", max_length=2000)):
    chats, favorites = await asyncio.gather(asyncio.to_thread(history.list_all), asyncio.to_thread(library.favorites))
    signals = {}
    def add(topic, weight, reason, at=None):
        if isinstance(topic, dict): topic = topic.get("display_name") or topic.get("name") or ""
        if not isinstance(topic, str) or len(topic.strip()) < 3: return
        age = 0
        try:
            if at: age = max(0, (datetime.now(timezone.utc) - datetime.fromisoformat(str(at).replace("Z", "+00:00")).replace(tzinfo=timezone.utc)).total_seconds() / 86400)
        except ValueError: pass
        key = topic.strip()[:160]; score = weight * 2 ** (-age / 30)
        old = signals.get(key, (0, reason)); signals[key] = (old[0] + score, reason if score > old[0] else old[1])
    for chat in chats:
        for interest in chat.get("interests") or []:
            add(interest, 3, f"İncelediğin {chat.get('name', 'akademisyen')}: {interest}", chat.get("updated"))
    for paper in favorites.get("papers", []):
        add(paper.get("topic"), 2, f"Kaydettiğin ‘{paper.get('title', '')}’ yayınıyla aynı konu", paper.get("added"))
    for topic in recent.split(",")[:20]: add(topic, 1, f"Son aradığın: {topic}")
    best = sorted(signals, key=lambda key: -signals[key][0])[:5]
    key = tuple((t, signals[t][1]) for t in best)
    cached = _RECOMMEND.get(key)
    if cached and time.time() - cached[0] < 1800: return cached[1]
    async def works(topic):
        since = (datetime.now(timezone.utc) - timedelta(days=730)).date().isoformat()
        async with reading._client() as client:
            params = OPENALEX_PARAMS | {"filter": f"institutions.country_code:TR,from_publication_date:{since}", "search": topic, "per_page": 8, "sort": "cited_by_count:desc"}
            if topic.startswith("T") and topic[1:].isdigit():
                params.pop("search"); params["filter"] += f",primary_topic.id:{topic}"
            r = await client.get(reading.OPENALEX + "/works", params=params); r.raise_for_status()
            result = [reading._work(w) | {"reason": signals[topic][1], "is_oa": bool((w.get("open_access") or {}).get("is_oa"))} for w in r.json().get("results", [])]
            return sorted(result, key=lambda x: not x["is_oa"])
    results = await asyncio.gather(*(works(t) for t in best), return_exceptions=True)
    items, seen = [], set()
    for rank in range(8):
        for rows in results:
            if isinstance(rows, Exception) or len(rows) <= rank: continue
            row = rows[rank]; identifier = row.get("doi") or row["title"]
            if identifier not in seen: items.append(row); seen.add(identifier)
    try: rising = await reading.trending(15)
    except Exception: rising = []
    words = {word.lower() for t in best for word in t.split() if len(word) > 3}
    fields = {item.get("field_id") for item in items if item.get("field_id")}
    topic_fields = {}
    if fields and rising:
        try:
            async with reading._client() as client:
                response = await client.get(reading.OPENALEX + "/topics", params=OPENALEX_PARAMS | {"filter": "id:" + "|".join(row["id"] for row in rising), "per_page": 50})
                if response.status_code == 200:
                    topic_fields = {r["id"].rsplit("/", 1)[-1]: (r.get("field") or {}).get("id", "").rsplit("/", 1)[-1] for r in response.json().get("results", [])}
        except (httpx.HTTPError, ValueError):
            pass
    rising = [r for r in rising if not words or topic_fields.get(r["id"]) in fields or any(w in (r.get("name", "") + " " + r.get("name_tr", "")).lower() for w in words)]
    result = {"items": items[:18], "rising": rising, "interests": best, "empty": not best, "message": "Birkaç akademisyen incele veya yayın kaydet; burası sana göre dolsun" if not best else ""}
    _RECOMMEND[key] = (time.time(), result)
    return result
