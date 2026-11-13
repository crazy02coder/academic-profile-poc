"""Araçlar: doçentlik/teşvik puan hesabı ve danışman bulucu."""
from __future__ import annotations
import asyncio
import re
import httpx
from fastapi import APIRouter, HTTPException, Query
from . import academic_score, advisors, history, library, yokdir
from .text import fold, STOP
from .llm import LLM

router = APIRouter(prefix="/api/tools")


@router.get("/score/{job_id}")
async def score(job_id: str, year: int | None = Query(None, ge=2015, le=2100)):
    if not re.fullmatch(r"[A-Za-z0-9_-]{4,64}", job_id):
        raise HTTPException(404)
    result = await asyncio.to_thread(history.load_result, job_id)
    if not result:
        raise HTTPException(404, "Profil kaydı bulunamadı.")
    prof = result.get("profile") or {}
    return {"person": {k: prof.get(k) or "" for k in ("name", "title", "institution", "department")},
            "docentlik": academic_score.docentlik(result), "tesvik": academic_score.tesvik(result, year)}


@router.get("/advisors")
async def advisor_search(q: str = Query(..., min_length=3, max_length=400), uni: str = Query("", max_length=80), mode: str = "tez"):
    mode = "2209" if mode == "2209" else "tez"
    if mode == "2209" and not uni:
        raise HTTPException(422, "2209-A için kendi üniversiteni seç.")
    english = ""
    if not q.isascii():
        try:
            english = await asyncio.wait_for(library._translate(q, await LLM().probe()), 25)
        except Exception:  # noqa: BLE001  çeviri yoksa Türkçe metinle aranır
            english = ""
    try:
        return await advisors.find(q, uni, mode, english)
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Kaynağa ulaşılamadı ({type(exc).__name__}).") from None


@router.get("/yok-person")
async def yok_person(name: str = Query(..., min_length=3, max_length=120), institution: str = Query("", max_length=200), theses: bool = False):
    """Kartlar ekranda göründükçe tek tek çağrılır (asla toplu değil); önbellekte varsa YÖK'e gidilmez."""
    out = await advisors.lookup(name, institution, theses)
    out["paused_until"] = yokdir.paused_until() if out.get("paused") else 0
    return out


# ------------------------------------------------------------------ jüri ve hakem önerici
async def _experts(topic: str, uni: str = "") -> dict:
    """Uzun başlık/özetle arama: anlamlı kelimeler VEYA ile aranır, en çok kelimeyi karşılayan yayınlar öne gelir."""
    english = ""
    if not topic.isascii():
        try:
            english = await asyncio.wait_for(library._translate(topic[:300], await LLM().probe()), 25)
        except Exception:  # noqa: BLE001
            english = ""
    def loose(text):
        words = list(dict.fromkeys(w for w in re.findall(r"[^\W\d_]{4,}", text) if fold(w) not in STOP))[:9]
        return " OR ".join(words)
    return await advisors.find(loose(topic) or topic, uni, "tez", loose(english))


def _same(a: str, b: str) -> bool:
    x, y = fold(a).split(), fold(b).split()
    return bool(x and y) and x[-1] == y[-1] and x[0][:3] == y[0][:3]


@router.get("/jury")
async def jury(job_id: str = Query(..., max_length=64), topic: str = Query(..., min_length=5, max_length=400)):
    """Tez jürisi önerisi: tez konusunda yayın yapan öğretim üyeleri; danışmanın kendi üniversitesinden ve dışından ayrı listelenir."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{4,64}", job_id):
        raise HTTPException(404)
    result = await asyncio.to_thread(history.load_result, job_id)
    if not result:
        raise HTTPException(404, "Profil kaydı bulunamadı.")
    prof = result.get("profile") or {}
    name, institution = prof.get("name") or "", prof.get("institution") or ""
    coauthors = {fold(c.get("name") or "") for c in (prof.get("yok") or {}).get("collaborators") or []}
    for p in result.get("publications") or []:
        coauthors.update(fold(str(a)) for a in (p.get("authors") or [])[:12])
    try:
        uni = next((u for u in await yokdir.university_list() if fold(u["name"]) == fold(institution)), None)
    except httpx.HTTPError:
        uni = None
    try:
        wide = await _experts(topic)  # sırayla: OpenAlex eşzamanlı isteklerde 429 dönebiliyor
        local = await _experts(topic, uni["id"]) if uni else {"items": []}
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Kaynağa ulaşılamadı ({type(exc).__name__}).") from None
    def rows(items, inside):
        out = []
        for a in items:
            if _same(a["name"], name):
                continue
            own = bool(uni) and (fold(a.get("institution") or "") == fold(institution) or inside)
            if own != inside:
                continue
            out.append(a | {"coauthor": fold(a["name"]) in coauthors or any(_same(a["name"], c) for c in list(coauthors)[:400] if c)})
        return out[:8]
    inside = rows(local.get("items") or [], True)
    seen = {fold(a["name"]) for a in inside}
    outside = [a for a in rows(wide.get("items") or [], False) if fold(a["name"]) not in seen]
    return {"advisor": name, "institution": institution, "topic": topic, "inside": inside, "outside": outside,
            "english": wide.get("english", ""), "works": wide.get("works", 0)}


@router.get("/reviewers")
async def reviewers(q: str = Query(..., min_length=10, max_length=400), exclude: str = Query("", max_length=400), institution: str = Query("", max_length=160)):
    """Hakem önerisi: konuda yayın yapan akademisyenler; yazarlar çıkarılır, yazarla aynı kurumdakiler işaretlenir."""
    names = [n.strip() for n in exclude.split(",") if n.strip()]
    try:
        found = await _experts(q)
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Kaynağa ulaşılamadı ({type(exc).__name__}).") from None
    inst = {t for t in fold(institution).split() if t not in ("universitesi", "university")}
    items = []
    for a in found.get("items") or []:
        if any(_same(a["name"], n) for n in names):
            continue
        tokens = set(fold(a.get("institution") or "").split())
        items.append(a | {"same_institution": bool(inst) and inst <= tokens})
    items.sort(key=lambda a: a["same_institution"])
    return {"items": items[:20], "english": found.get("english", ""), "works": found.get("works", 0), "excluded": names}
