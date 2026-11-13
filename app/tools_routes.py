"""Araçlar: doçentlik/teşvik puan hesabı ve danışman bulucu."""
from __future__ import annotations
import asyncio
import re
import time
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
async def yok_person(name: str = Query(..., min_length=3, max_length=120), institution: str = Query("", max_length=200),
                     theses: bool = False, cached: bool = False):
    """`cached=true`: yalnız önbellek, YÖK'e hiç gitmez (sayfa açılışında). Canlı istek yalnız karttaki düğmeyle."""
    out = await advisors.lookup(name, institution, theses, cache_only=cached)
    until = yokdir.paused_until()
    out["paused_until"] = until if until > time.time() else 0
    if out["paused_until"] and not cached and out.get("error"):
        out["paused"] = True
    return out


@router.get("/yok-status")
async def yok_status():
    """Sigorta durumu: arayüz kalan süreyi gösterir."""
    until = yokdir.paused_until()
    return {"paused": until > time.time(), "paused_until": until, "remaining": max(0, int(until - time.time())),
            "rate": {"gap_seconds": yokdir.RATE_GAP, "per_minute": yokdir.RATE_PER_MIN}}


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


def _ids(person: dict) -> dict:
    """Karşılaştırılabilir kimlikler: OpenAlex yazar kimliği, ORCID, YÖK authorGuidId."""
    links = person.get("links") or {}
    yok = str(person.get("yok_id") or "") or (re.search(r"authorGuidId=([0-9A-Fa-f]+)", str(person.get("yok_url") or links.get("yok") or "")) or [None, ""])[1]
    orcid = str(person.get("orcid") or links.get("orcid") or "").rsplit("/", 1)[-1]
    return {k: v.upper() for k, v in (("openalex", str(person.get("openalex") or "").rsplit("/", 1)[-1]), ("orcid", orcid), ("yok", yok)) if v}


def _same_name(a: str, b: str) -> bool:
    """Adın tüm parçaları sırayla aynı; kısaltma ("M.") yalnız aynı harfle başlayan parçayla eşleşir."""
    x = [t.strip(".-") for t in fold(a).replace(".", ". ").split() if t.strip(".-")]
    y = [t.strip(".-") for t in fold(b).replace(".", ". ").split() if t.strip(".-")]
    if not x or not y or len(x) != len(y) or x[-1] != y[-1]:
        return False
    return all(p == q or (min(len(p), len(q)) == 1 and p[0] == q[0]) for p, q in zip(x, y))


def _same(a: dict | str, b: dict | str) -> bool:
    """Önce kimlik (ortak bir kimlik türü varsa kesin karar), yoksa adın tüm parçaları."""
    a = a if isinstance(a, dict) else {"name": a}
    b = b if isinstance(b, dict) else {"name": b}
    ia, ib = _ids(a), _ids(b)
    common = ia.keys() & ib.keys()
    if common:
        return any(ia[k] == ib[k] for k in common)
    return _same_name(a.get("name") or "", b.get("name") or "")


async def _openalex_coauthors(names: list[str]) -> tuple[set[str], list[str]]:
    """Yazarların OpenAlex'teki ortak yazarları (kimlik ve ad). Sıralı istekler: OpenAlex 429'a duyarlı."""
    from . import reading
    from .config import OPENALEX_PARAMS
    ids, people = set(), set()
    async with reading._client() as client:
        for name in names[:5]:
            try:
                r = await client.get(reading.OPENALEX + "/authors", params=OPENALEX_PARAMS | {"search": name, "per_page": 5})
                if r.status_code != 200:
                    continue
                author = next((a for a in r.json().get("results", []) if _same_name(a.get("display_name") or "", name)), None)
                if not author:
                    continue
                me = author["id"].rsplit("/", 1)[-1]
                r = await client.get(reading.OPENALEX + "/works", params=OPENALEX_PARAMS | {
                    "filter": f"author.id:{me}", "per_page": 200, "select": "authorships", "sort": "publication_date:desc"})
                if r.status_code != 200:
                    continue
                for w in r.json().get("results", []):
                    for a in w.get("authorships") or []:
                        who = a.get("author") or {}
                        aid = (who.get("id") or "").rsplit("/", 1)[-1]
                        if aid and aid != me:
                            ids.add(aid.upper()); people.add(who.get("display_name") or "")
            except (httpx.HTTPError, ValueError):
                continue
    return ids, sorted(p for p in people if p)


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
    advisor = {"name": name, "links": prof.get("links") or {}, "orcid": prof.get("orcid") or ""}
    coauthors = {fold(c.get("name") or "") for c in (prof.get("yok") or {}).get("collaborators") or []}
    for p in result.get("publications") or []:
        coauthors.update(fold(str(a)) for a in (p.get("authors") or [])[:12])
    coauthors.discard(""); coauthors.discard(fold(name))
    coauthor_list = sorted(coauthors)  # sıralı ve sınırsız: sonuç her çalışmada aynı
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
            if _same(a, advisor):
                continue
            own = bool(uni) and (fold(a.get("institution") or "") == fold(institution) or inside)
            if own != inside:
                continue
            out.append(a | {"coauthor": fold(a["name"]) in coauthors or any(_same_name(a["name"], c) for c in coauthor_list)})
        out.sort(key=lambda a: a["coauthor"])  # ortak yayını olan sona (hakemdeki gibi)
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
    co_ids, co_names = await _openalex_coauthors(names) if names else (set(), [])
    inst = {t for t in fold(institution).split() if t not in ("universitesi", "university")}
    items = []
    for a in found.get("items") or []:
        if any(_same(a, n) for n in names):
            continue
        tokens = set(fold(a.get("institution") or "").split())
        coauthor = str(a.get("openalex") or "").upper() in co_ids or any(_same_name(a["name"], c) for c in co_names)
        items.append(a | {"same_institution": bool(inst) and inst <= tokens, "coauthor": coauthor})
    items.sort(key=lambda a: (a["coauthor"], a["same_institution"]))  # çıkar çatışması olası adaylar sona
    return {"items": items[:20], "english": found.get("english", ""), "works": found.get("works", 0), "excluded": names,
            "coauthors_checked": bool(co_ids)}
