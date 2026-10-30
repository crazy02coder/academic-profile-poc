"""Kişisel kütüphane (favori makaleler ve akademisyenler) ve konu araması.

Konu araması genel web'e değil, doğrudan akademik kaynaklara gider: OpenAlex, Crossref,
Semantic Scholar, OpenAIRE (DergiPark, üniversite arşivleri) ve TR Dizin paralel sorgulanır, sonuçlar DOI/başlıkla tek satırda birleştirilir. Türkçe
sorgu Gemini ile İngilizceye de çevrilir (model yoksa yalnız Türkçe aranır).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time

import httpx

from .config import CONTACT_MAIL, OPENALEX_PARAMS, ROOT, USER_AGENT
from . import trsources
from .text import clean, doi_key, fold, title_key

FAV_PATH = ROOT / "data" / "favorites.json"
OPENALEX = "https://api.openalex.org"
CROSSREF = "https://api.crossref.org"
S2 = "https://api.semanticscholar.org/graph/v1"
_SEARCH_CACHE: dict[str, tuple[float, dict]] = {}
SEARCH_TTL = 1800


def paper_key(p: dict) -> str:
    doi = doi_key(p.get("doi") or "")
    if doi:
        return "doi:" + doi
    return "t:" + hashlib.sha1(f"{title_key(p.get('title') or '')}|{p.get('year') or ''}".encode()).hexdigest()[:16]


# ------------------------------------------------------------------------ favoriler
def _load() -> dict:
    if FAV_PATH.exists():
        try:
            return json.loads(FAV_PATH.read_text())
        except ValueError:
            pass
    return {"papers": [], "people": []}


def _save(data: dict):
    FAV_PATH.parent.mkdir(parents=True, exist_ok=True)
    FAV_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=1))


def favorites() -> dict:
    return _load()


PAPER_FIELDS = ("title", "year", "venue", "doi", "url", "authors", "type", "citations", "abstract", "sources",
                "source", "job_id", "pid", "person")
PERSON_FIELDS = ("name", "title", "institution", "department", "photo", "chat_id", "job_id", "papers", "email")


def add_paper(p: dict) -> dict:
    data = _load()
    item = {k: p.get(k) for k in PAPER_FIELDS if p.get(k) not in (None, "", [])}
    item["abstract"] = (item.get("abstract") or "")[:1500]
    item["key"] = paper_key(item)
    item["added"] = time.strftime("%Y-%m-%d %H:%M")
    data["papers"] = [x for x in data["papers"] if x["key"] != item["key"]] + [item]
    _save(data)
    return item


def remove_paper(key: str) -> bool:
    data = _load()
    before = len(data["papers"])
    data["papers"] = [x for x in data["papers"] if x["key"] != key]
    _save(data)
    return len(data["papers"]) < before


def add_person(p: dict) -> dict:
    data = _load()
    item = {k: p.get(k) for k in PERSON_FIELDS if p.get(k) not in (None, "", [])}
    item["key"] = p.get("job_id") or fold(f"{p.get('name')} {p.get('institution')}")
    item["added"] = time.strftime("%Y-%m-%d %H:%M")
    data["people"] = [x for x in data["people"] if x["key"] != item["key"]] + [item]
    _save(data)
    return item


def remove_person(key: str) -> bool:
    data = _load()
    before = len(data["people"])
    data["people"] = [x for x in data["people"] if x["key"] != key]
    _save(data)
    return len(data["people"]) < before


# ---------------------------------------------------------------------- konu araması
def _abstract(inv: dict | None) -> str:
    if not inv:
        return ""
    return " ".join(w for _, w in sorted((pos, w) for w, ps in inv.items() for pos in ps))


async def _openalex(client, q: str, n: int) -> list[dict]:
    r = await client.get(f"{OPENALEX}/works", params={
        "search": q, "per-page": n, **OPENALEX_PARAMS,
        "select": "id,doi,display_name,publication_year,primary_location,authorships,cited_by_count,type,"
                  "abstract_inverted_index,language"})
    r.raise_for_status()
    out = []
    for w in r.json().get("results", []):
        loc = w.get("primary_location") or {}
        out.append({"title": clean(w.get("display_name")), "year": w.get("publication_year"),
                    "doi": doi_key(w.get("doi") or ""), "venue": clean((loc.get("source") or {}).get("display_name") or ""),
                    "authors": [n for a in w.get("authorships") or [] if (n := (a.get("author") or {}).get("display_name"))][:12],
                    "abstract": _abstract(w.get("abstract_inverted_index"))[:1500], "citations": w.get("cited_by_count"),
                    "type": w.get("type") or "", "language": w.get("language") or "",
                    "url": w.get("doi") or loc.get("landing_page_url") or w["id"], "source": "openalex"})
    return out


async def _crossref(client, q: str, n: int) -> list[dict]:
    r = await client.get(f"{CROSSREF}/works", params={
        "query.bibliographic": q, "rows": n, "mailto": CONTACT_MAIL,
        "select": "DOI,title,author,issued,container-title,abstract,URL,is-referenced-by-count,type"})
    r.raise_for_status()
    out = []
    for it in r.json().get("message", {}).get("items", []):
        year = ((it.get("issued") or {}).get("date-parts") or [[None]])[0][0]
        out.append({"title": clean((it.get("title") or [""])[0]), "year": year, "doi": doi_key(it.get("DOI")),
                    "venue": clean((it.get("container-title") or [""])[0]),
                    "authors": [clean(f"{a.get('given', '')} {a.get('family', '')}") for a in it.get("author") or []][:12],
                    "abstract": clean(re.sub(r"<[^>]+>", " ", it.get("abstract") or ""))[:1500],
                    "citations": it.get("is-referenced-by-count"), "type": it.get("type") or "",
                    "url": it.get("URL") or "", "source": "crossref"})
    return out


async def _semantic(client, q: str, n: int) -> list[dict]:
    r = await client.get(f"{S2}/paper/search", params={
        "query": q, "limit": n, "fields": "title,year,venue,authors,abstract,externalIds,citationCount,url"})
    if r.status_code == 429:
        return []  # anahtarsız paylaşımlı kota; diğer kaynaklar yeter
    r.raise_for_status()
    out = []
    for d in r.json().get("data") or []:
        out.append({"title": clean(d.get("title")), "year": d.get("year"), "doi": doi_key((d.get("externalIds") or {}).get("DOI")),
                    "venue": clean(d.get("venue") or ""), "authors": [a.get("name", "") for a in d.get("authors") or []][:12],
                    "abstract": clean(d.get("abstract") or "")[:1500], "citations": d.get("citationCount"),
                    "type": "", "url": d.get("url") or "", "source": "semantic_scholar"})
    return out


async def _translate(q: str, llm) -> str:
    if llm is None or not llm.available or q.isascii():
        return ""
    data = await llm.json(
        f"Akademik literatür araması için şu Türkçe konuyu kısa bir İngilizce arama ifadesine çevir: {q}",
        {"type": "object", "properties": {"en": {"type": "string"}}, "required": ["en"]}, timeout=20, fast=True)
    en = clean((data or {}).get("en"))
    return en if en and fold(en) != fold(q) else ""


def _merge(rows: list[dict]) -> list[dict]:
    """DOI ya da başlık aynıysa tek satır; eksik alanlar diğer kaynaklardan tamamlanır."""
    out: dict[str, dict] = {}
    alias: dict[str, str] = {}
    for r in rows:
        if not r["title"] or len(r["title"]) < 6:
            continue
        keys = [k for k in ("doi:" + r["doi"] if r["doi"] else "", "t:" + title_key(r["title"])) if k]
        hit = next((alias[k] for k in keys if k in alias), None)
        if hit is None:
            hit = keys[0]
            out[hit] = {**r, "sources": [r["source"]]}
        else:
            cur = out[hit]
            for f in ("doi", "venue", "abstract", "year", "url", "type"):
                if not cur.get(f) and r.get(f):
                    cur[f] = r[f]
            if (r.get("citations") or 0) > (cur.get("citations") or 0):
                cur["citations"] = r["citations"]
            if r["source"] not in cur["sources"]:
                cur["sources"].append(r["source"])
        for k in keys:
            alias.setdefault(k, hit)
    return list(out.values())


def _relevance(p: dict, terms: list[str]) -> float:
    title, abstract = fold(p["title"]), fold(p.get("abstract") or "")
    hits = sum(3 * (t in title) + (t in abstract) for t in terms)
    return hits + 0.6 * len(p["sources"]) + min(3.0, (p.get("citations") or 0) ** 0.25)


async def topic_search(q: str, llm=None, n: int = 25) -> dict:
    q = clean(q)
    hit = _SEARCH_CACHE.get(fold(q))
    if hit and time.time() - hit[0] < SEARCH_TTL:
        return hit[1]
    started = time.time()
    en = await _translate(q, llm)
    queries = [q] + ([en] if en else [])
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        calls = [(name, fn(client, query, n)) for query in queries
                 for name, fn in (("OpenAlex", _openalex), ("Crossref", _crossref), ("Semantic Scholar", _semantic),
                                  ("OpenAIRE", trsources.openaire_topic))]
        # TR Dizin ulusal dizin: Türkçe sorgu yeterli (İngilizce başlıklı Türk makaleleri de dizinde)
        calls.append(("TR Dizin", trsources.trdizin_topic(client, q, n)))
        results = await asyncio.gather(*(c for _, c in calls), return_exceptions=True)
    rows, status = [], {}
    for (name, _), res in zip(calls, results):
        if isinstance(res, Exception):
            status.setdefault(name, f"erişilemedi ({type(res).__name__})")
            continue
        rows.extend(res)
        status[name] = status.get(name) if isinstance(status.get(name), int) else 0
        status[name] += len(res)
    terms = [t for t in fold(" ".join(queries)).split() if len(t) > 2]
    papers = sorted(_merge(rows), key=lambda p: -_relevance(p, terms))
    for p in papers:
        p["key"] = paper_key(p)
    out = {"query": q, "english": en, "papers": papers, "sources": status, "elapsed": round(time.time() - started, 1)}
    if papers:
        _SEARCH_CACHE[fold(q)] = (time.time(), out)
    return out
