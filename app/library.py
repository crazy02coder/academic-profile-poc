"""Kişisel kütüphane (favori makaleler ve akademisyenler) ve konu araması.

Konu araması genel web'e değil, doğrudan akademik kaynaklara gider: OpenAlex, Crossref,
Semantic Scholar, OpenAIRE (DergiPark, üniversite arşivleri) ve TR Dizin paralel sorgulanır, sonuçlar DOI/başlıkla tek satırda birleştirilir. Türkçe
sorgu Gemini ile İngilizceye de çevrilir (model yoksa yalnız Türkçe aranır).
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import re
import time
import uuid

import httpx

from .config import CONTACT_MAIL, OPENALEX_PARAMS, ROOT, USER_AGENT
from . import publication_status, quartiles, trsources, wos, wos_publications, wos_verification
from .text import clean, doi_key, fold, name_score, name_tokens, title_key

FAV_PATH = ROOT / "data" / "favorites.json"
OPENALEX = "https://api.openalex.org"
CROSSREF = "https://api.crossref.org"
S2 = "https://api.semanticscholar.org/graph/v1"
_SEARCH_CACHE: dict[str, tuple[float, dict]] = {}
SEARCH_TTL = 1800
_TOPIC_JOBS: dict[str, dict] = {}
_TOPIC_TASKS: dict[str, asyncio.Task] = {}
WOS_TOPIC_LIMIT = 20
WOS_TOPIC_BUDGET = 90
WOS_QUEUE_TIMEOUT = 20


def paper_key(p: dict) -> str:
    doi = doi_key(p.get("doi") or "")
    if doi:
        return "doi:" + doi
    return "t:" + hashlib.sha1(f"{title_key(p.get('title') or '')}|{p.get('year') or ''}".encode()).hexdigest()[:16]


# ------------------------------------------------------------------------ favoriler
def _load() -> dict:
    if FAV_PATH.exists():
        try:
            data = json.loads(FAV_PATH.read_text())
            for kind in ("papers", "people", "universities", "firms"):
                data.setdefault(kind, [])
            return data
        except ValueError:
            pass
    return {"papers": [], "people": [], "universities": [], "firms": []}


def _save(data: dict):
    FAV_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = FAV_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    tmp.replace(FAV_PATH)


def favorites() -> dict:
    return _load()


PAPER_FIELDS = ("pdf", "topic", "reason", "is_oa", "title", "year", "venue", "doi", "url", "authors", "type", "citations", "abstract", "sources",
                "source", "wos", "jcr", "quartile", "citations_by_source", "abstract_source", "abstract_url",
                "publication_kind", "publication_status", "job_id", "pid", "person")
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


def update_person(key: str, p: dict):
    """Favorideki akademisyenin özetini (fotoğraf, yayın sayısı…) yenilenen profile göre günceller."""
    data = _load()
    for x in data["people"]:
        if x["key"] == key:
            x.update({k: p[k] for k in PERSON_FIELDS if p.get(k) not in (None, "", [])})
            _save(data)


def remove_person(key: str) -> bool:
    data = _load()
    before = len(data["people"])
    data["people"] = [x for x in data["people"] if x["key"] != key]
    _save(data)
    return len(data["people"]) < before


def add_org(kind: str, org: dict) -> dict:
    if kind not in {"universities", "firms"} or not org.get("id") or not org.get("name"):
        raise ValueError("Geçerli bir kurum seçin.")
    data = _load()
    item = {k: org[k] for k in ("id", "name", "home", "domain", "cities", "sectors", "centers") if k in org}
    item.update(key=str(org["id"]), added=time.strftime("%Y-%m-%d %H:%M"))
    data[kind] = [x for x in data[kind] if x["key"] != item["key"]] + [item]
    _save(data)
    return item


def remove_org(kind: str, key: str) -> bool:
    if kind not in {"universities", "firms"}:
        raise ValueError("Geçersiz kurum türü.")
    data = _load()
    before = len(data[kind])
    data[kind] = [x for x in data[kind] if x["key"] != key]
    _save(data)
    return len(data[kind]) < before


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


def _same_topic_paper(a: dict, b: dict) -> bool:
    """DOI'siz başlık eşleşmesinde yayın türü, yıl ve tam yazar kanıtı gerekir."""
    kind = publication_status.kind(a)
    if kind in ('Diğer', 'Türü belirtilmemiş') or kind != publication_status.kind(b):
        return False
    if not a.get('year') or str(a['year']) != str(b.get('year') or ''):
        return False
    return any(len(name_tokens(x)) >= 2 and len(name_tokens(y)) >= 2 and name_score(x, y) >= .85
               for x in a.get('authors') or [] for y in b.get('authors') or [])


def _merge(rows: list[dict]) -> list[dict]:
    """DOI önceliklidir; çelişen DOI/yıl veya belirsiz başlık eşleşmesi birleştirilmez."""
    out, titles = [], []
    for raw in rows:
        r = copy.deepcopy(raw)
        r['title'] = clean(r.get('title') or '')
        r['doi'] = doi_key(r.get('doi') or '')
        if len(r['title']) < 6:
            continue
        if r.get('abstract'):
            r.setdefault('abstract_source', r.get('source') or '')
            r.setdefault('abstract_url', r.get('url') or '')
        title = title_key(r['title'])
        candidates = [i for i, p in enumerate(out) if r['doi'] and doi_key(p.get('doi')) == r['doi']]
        if not candidates and r.get('source_id'):
            candidates = [i for i, p in enumerate(out)
                          if p.get('source') == r.get('source') and p.get('source_id') == r['source_id']
                          and not (r['doi'] and p.get('doi') and r['doi'] != p['doi'])]
        if not candidates:
            candidates = [i for i, p in enumerate(out) if title in titles[i]
                          and not (r['doi'] and p.get('doi') and r['doi'] != p['doi'])
                          and _same_topic_paper(r, p)]
        hit = candidates[0] if len(candidates) == 1 else None
        if hit is None:
            hit = len(out)
            out.append({**r, 'sources': list(dict.fromkeys(r.get('sources') or [r.get('source')]))})
            titles.append({title})
        else:
            cur = out[hit]
            for f in ('doi', 'venue', 'year', 'url', 'type', 'authors', 'issn', 'date'):
                if not cur.get(f) and r.get(f):
                    cur[f] = r[f]
            if not cur.get('abstract') and r.get('abstract'):
                for f in ('abstract', 'abstract_source', 'abstract_url'):
                    cur[f] = r.get(f, '')
            if (r.get("citations") or 0) > (cur.get("citations") or 0):
                cur["citations"] = r["citations"]
            cur['sources'] = list(dict.fromkeys(cur['sources'] + (r.get('sources') or [r.get('source')])))
            for field in ('wos', 'jcr', 'quartile'):
                if r.get(field):
                    cur[field] = r[field]
            titles[hit].add(title)
        cur = out[hit]
        cur['sources'] = [s for s in cur['sources'] if s]
        if isinstance(r.get('citations'), int) and r.get('source'):
            cur.setdefault('citations_by_source', {})[r['source']] = r['citations']
    publication_status.annotate(out)
    return out


def _relevance(p: dict, terms: list[str]) -> float:
    title, abstract = fold(p["title"]), fold(p.get("abstract") or "")
    hits = sum(3 * (t in title) + (t in abstract) for t in terms)
    return hits + 0.6 * len(p["sources"]) + min(3.0, (p.get("citations") or 0) ** 0.25)


TOPIC_SOURCES = {"openalex", "crossref", "semantic_scholar", "openaire", "trdizin", "wos"}


async def topic_search(q: str, llm=None, n: int = 25, sources: set[str] | None = None) -> dict:
    q = clean(q)
    n = max(1, min(int(n), 50))
    selected = TOPIC_SOURCES if sources is None else sources & TOPIC_SOURCES
    cache_key = f'{fold(q)}:{n}:{",".join(sorted(selected))}'
    hit = _SEARCH_CACHE.get(cache_key)
    if hit and time.time() - hit[0] < SEARCH_TTL and hit[1].get('search_id') in _TOPIC_JOBS:
        job = _TOPIC_JOBS[hit[1]['search_id']]
        meta = job['wos']
        retryable = meta.get('status') in ('error', 'blocked') or meta.get('reason') in ('time_budget', 'collection_incomplete')
        if job['id'] not in _TOPIC_TASKS and (wos.needs_verification_retry(meta) or
                retryable and time.time() - meta.get('finished_at', 0) >= 300):
            job['wos'] = _pending_wos(min(n, WOS_TOPIC_LIMIT))
            _publish_topic(job)
            _TOPIC_TASKS[job['id']] = asyncio.create_task(_run_topic_wos(job))
        return copy.deepcopy(job['snapshot'])
    started = time.time()
    _prune_topics()
    try:
        en = await _translate(q, llm)
    except Exception:
        en = ''
    queries = [q] + ([en] if en else [])
    search_id = uuid.uuid4().hex[:16]
    job = {'id': search_id, 'cache_key': cache_key, 'started': started, 'query': q, 'english': en,
           'rows': [], 'wos_rows': [], 'sources': {}, 'base_ready': False,
           'terms': [t for t in fold(' '.join(queries)).split() if len(t) > 2],
           'revision': 0, 'wos': _pending_wos(min(n, WOS_TOPIC_LIMIT)) if 'wos' in selected else {'status': 'skipped'}}
    _TOPIC_JOBS[search_id] = job
    _publish_topic(job)
    if 'wos' in selected:
        _TOPIC_TASKS[search_id] = asyncio.create_task(_run_topic_wos(job))
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        calls = [(name, fn(client, query, n)) for query in queries
                 for key, name, fn in (("openalex", "OpenAlex", _openalex), ("crossref", "Crossref", _crossref),
                                      ("semantic_scholar", "Semantic Scholar", _semantic), ("openaire", "OpenAIRE", trsources.openaire_topic))
                 if key in selected]
        # TR Dizin ulusal dizin: Türkçe sorgu yeterli (İngilizce başlıklı Türk makaleleri de dizinde)
        if "trdizin" in selected:
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
    job.update(rows=rows, sources=status, base_ready=True)
    _publish_topic(job)
    return copy.deepcopy(job['snapshot'])


def _pending_wos(limit: int) -> dict:
    return {'status': 'pending', 'total': None, 'checked': 0, 'limit': limit,
            'scope': 'first_results', 'truncated': False}


def _publish_topic(job: dict):
    papers = sorted(_merge(job['rows'] + job['wos_rows']), key=lambda p: -_relevance(p, job['terms']))
    quartiles.annotate([p for p in papers if not p.get('quartile')])
    for paper in papers:
        paper['key'] = paper_key(paper)
    status = dict(job['sources'])
    meta = job['wos']
    if meta['status'] == 'skipped':
        pass
    elif meta['status'] in ('pending', 'running'):
        status['WoS'] = 'aranıyor'
    elif job['wos_rows'] or meta['status'] in ('done', 'partial'):
        status['WoS'] = len(job['wos_rows'])
    else:
        status['WoS'] = 'sıra bekleme süresi doldu' if meta.get('reason') == 'queue_timeout' else 'erişilemedi'
    job['revision'] += 1
    job['snapshot'] = {'query': job['query'], 'english': job['english'], 'papers': papers, 'sources': status,
                       'elapsed': round(time.time() - job['started'], 1), 'search_id': job['id'],
                       'revision': job['revision'], 'wos': copy.deepcopy(meta)}
    if job.get('base_ready'):
        _SEARCH_CACHE[job['cache_key']] = (job['started'], job['snapshot'])


async def _collect_wos_topic(query: str, limit: int) -> dict:
    from scrapling.fetchers import AsyncStealthySession
    async with wos_verification.time_budget(WOS_TOPIC_BUDGET + 5):
        async with AsyncStealthySession(headless=True, network_idle=False, timeout=45000, max_pages=1) as session:
            return await wos_publications.collect_topic(query, session, limit=limit,
                                                        budget=WOS_TOPIC_BUDGET)


async def _run_topic_wos(job: dict):
    gate, acquired = wos.access_gate(), False
    try:
        async with wos_verification.time_budget(WOS_QUEUE_TIMEOUT):
            await gate.acquire()
        acquired = True
        job['wos']['status'] = 'running'
        _publish_topic(job)
        report = await _collect_wos_topic(job['english'] or job['query'], job['wos']['limit'])
        report['manual_verification_version'] = wos.MANUAL_VERIFICATION_VERSION
        previous = {p.get('source_id') or p.get('url'): p for p in job['wos_rows']}
        previous.update({p.get('source_id') or p.get('url'): p for p in report.get('records') or []})
        job['wos_rows'] = list(previous.values())
        job['wos'] = {k: v for k, v in report.items() if k != 'records'}
    except asyncio.TimeoutError:
        job['wos'].update(status='partial' if acquired else 'error', truncated=acquired,
                          reason='time_budget' if acquired else 'queue_timeout')
    except wos.AccessUnavailable as exc:
        job['wos'].update(status='blocked', reason=getattr(exc, 'reason', 'access_unavailable'),
                          message=str(exc), access_detail=getattr(exc, 'access_detail', 'unavailable'))
    except asyncio.CancelledError:
        job['wos'].update(status='error', reason='cancelled')
        raise
    except Exception as exc:
        job['wos'].update(status='error', reason='collection_failed', errors=[type(exc).__name__])
    finally:
        if acquired:
            gate.release()
        job['wos']['manual_verification_version'] = wos.MANUAL_VERIFICATION_VERSION
        job['wos']['finished_at'] = time.time()
        _publish_topic(job)
        _TOPIC_TASKS.pop(job['id'], None)


def topic_snapshot(search_id: str) -> dict | None:
    job = _TOPIC_JOBS.get(search_id)
    if not job or time.time() - job['started'] >= SEARCH_TTL:
        return None
    return copy.deepcopy(job['snapshot'])


def _prune_topics():
    for search_id, job in list(_TOPIC_JOBS.items()):
        if search_id not in _TOPIC_TASKS and time.time() - job['started'] >= SEARCH_TTL:
            _TOPIC_JOBS.pop(search_id, None)
            hit = _SEARCH_CACHE.get(job['cache_key'])
            if hit and hit[1].get('search_id') == search_id:
                _SEARCH_CACHE.pop(job['cache_key'], None)


async def close():
    tasks = list(_TOPIC_TASKS.values())
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    _TOPIC_TASKS.clear()
