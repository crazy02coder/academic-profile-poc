"""Background unit publication collection through the normal person-profile flow.

The callback owns identity resolution, source collection and persistent profiles.
This module limits concurrency, exposes incremental snapshots and merges verified
person results without counting the same coauthored publication more than once.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import os
import re
import tempfile
import time
import uuid
from collections import Counter
from urllib.parse import parse_qs, urlparse

from .config import ROOT
from .text import doi_key, fold, title_key

CONCURRENCY = 2
CACHE_VERSION = 1
CACHE_DIR = ROOT / 'data' / 'unit_publications'
_LOG = logging.getLogger(__name__)
JOBS: dict[str, dict] = {}
TASKS: dict[str, asyncio.Task] = {}
PERSON_TASKS: dict[tuple[str, str], asyncio.Task] = {}  # (birim işi, kişi): tek kişi yenilemesi
_KEYS: dict[str, str] = {}
_PERSON_CACHE: dict[str, dict] = {}
_GATE = None
_GATE_LOOP = None
_SOURCE_ORDER = {'openalex': 0, 'crossref': 1, 'yok': 2, 'wos': 3, 'trdizin': 4,
                 'openaire': 5, 'orcid': 6, 'scholar': 7, 'tez': 8}
_ARTICLE_TYPES = {'article', 'journal-article', 'journal article', 'review'}
_GROUPS = {**dict.fromkeys(_ARTICLE_TYPES, 'journal'),
           **dict.fromkeys(('conference-paper', 'conference paper', 'proceedings-article',
                            'proceedings paper', 'proceedings'), 'conference'),
           'posted-content': 'preprint', 'preprint': 'preprint', 'dataset': 'dataset',
           'data-set': 'dataset', 'software': 'software', 'book': 'book',
           'book-chapter': 'chapter', 'book chapter': 'chapter', 'dissertation': 'thesis', 'thesis': 'thesis'}


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def _hash(value) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()[:24]


def person_key(person: dict, institution: str, domain: str) -> str:
    links = person.get('links') or {}
    urls = [person.get(k) or '' for k in ('yok_url', 'url', 'profile_url')] + [links.get('yok') or '']
    yok = person.get('yok_id') or next((q.get('authorId', q.get('authorGuidId', ['']))[0]
                                     for q in (parse_qs(urlparse(u).query) for u in urls)
                                     if 'authorId' in q or 'authorGuidId' in q), '')
    orcid = re.search(r'\d{4}-\d{4}-\d{4}-\d{3}[\dXx]', str(person.get('orcid') or links.get('orcid') or ''))
    if yok:
        return 'yok:' + str(yok).upper()
    if orcid:
        return 'orcid:' + orcid[0].upper()
    # Name remains part of URL identity: directory links sometimes target one shared listing.
    return 'person:' + _hash([fold(person.get('name') or ''), person.get('url') or '',
                             fold(institution), domain.lower(), fold(person.get('department') or '')])


def _sources(paper: dict) -> list[str]:
    return sorted(set(paper.get('sources') or [paper.get('source')]) - {None, ''},
                  key=lambda value: (_SOURCE_ORDER.get(value, 99), value))


def _authors_match(left: list[str], right: list[str]) -> bool:
    def parts(name):
        bits = fold(name).split()
        if ',' in name and len(bits) > 1:
            bits = bits[1:] + bits[:1]
        return bits
    for a in left:
        aa = parts(a)
        for b in right:
            bb = parts(b)
            if len(aa) < 2 or len(bb) < 2 or aa[-1] != bb[-1]:
                continue
            if aa[0] == bb[0] or (aa[0][0] == bb[0][0] and min(len(aa[0]), len(bb[0])) == 1):
                return True
    return False


def _title_keys(paper: dict) -> set[str]:
    return {title_key(v) for v in [paper.get('title') or '',
            *(v.get('title') or '' for v in paper.get('variants') or [])] if v}


def _fallback_keys(paper: dict) -> set[tuple]:
    kind = _GROUPS.get(str(paper.get('type') or '').lower().strip())
    year = paper.get('year')
    if not kind or not year:
        return set()
    return {(title, str(year), kind) for title in _title_keys(paper)}


def _unique(values: list) -> list:
    seen, out = set(), []
    for value in values:
        key = _json(value)
        if key not in seen:
            seen.add(key); out.append(value)
    return out


def aggregate(results: dict[str, dict], people: dict[str, dict]) -> list[dict]:
    """Deterministic DOI-first union; ambiguous title matches stay separate."""
    rows = []
    for identity, result in sorted(results.items()):
        person = people[identity]
        for paper in result.get('publications') or []:
            if paper.get('title'):
                rows.append((identity, person, result, paper))
    rows.sort(key=lambda row: (not bool(doi_key(row[3].get('doi'))),
                              _SOURCE_ORDER.get(row[3].get('source'), 99),
                              doi_key(row[3].get('doi')), title_key(row[3].get('title') or ''),
                              row[0], str(row[3].get('id') or '')))
    papers, by_doi, by_title = [], {}, {}
    for identity, person, result, original in rows:
        incoming = copy.deepcopy(original)
        doi = doi_key(incoming.get('doi'))
        match = by_doi.get(doi) if doi else None
        if match is None:
            possible = set()
            for key in _fallback_keys(incoming):
                possible.update(by_title.get(key, set()))
            candidates = [i for i in sorted(possible)
                          if not (doi and doi_key(papers[i].get('doi')) and doi != doi_key(papers[i].get('doi')))
                          and _authors_match(incoming.get('authors') or [], papers[i].get('authors') or [])]
            if len(candidates) == 1:
                match = candidates[0]
        ref = {'person_key': identity, 'name': person.get('name') or '',
               'job_id': result.get('job_id'), 'chat_id': result.get('chat_id'), 'pid': original.get('id')}
        provenance = {**ref, **{k: copy.deepcopy(original[k]) for k in
                     ('source', 'source_id', 'sources', 'title', 'year', 'type', 'doi', 'url', 'venue',
                      'citations', 'citations_by_source', 'wos', 'jcr', 'quartile', 'publication_status',
                      'abstract_source', 'abstract_url') if k in original}}
        if match is None:
            match = len(papers)
            incoming['sources'] = _sources(incoming)
            incoming['unit_authors'] = [person.get('name') or '']
            incoming['profile_refs'] = [ref]
            incoming['unit_provenance'] = [provenance]
            papers.append(incoming)
        else:
            current = papers[match]
            current['sources'] = _sources({'sources': current['sources'] + _sources(incoming)})
            current['unit_authors'] = sorted(set(current['unit_authors']) | {person.get('name') or ''}, key=fold)
            current['profile_refs'] = _unique(current['profile_refs'] + [ref])
            current['unit_provenance'] = _unique(current['unit_provenance'] + [provenance])
            for field, value in incoming.items():
                if field in ('id', 'sources', 'unit_authors', 'profile_refs', 'unit_provenance'):
                    continue
                if not current.get(field) and value not in (None, '', [], {}):
                    current[field] = value
            for field in ('authors', 'variants', 'languages', 'language_names', 'labels', 'issn', 'orgs'):
                if isinstance(current.get(field), list) and isinstance(incoming.get(field), list):
                    current[field] = _unique(current[field] + incoming[field])
            # One publication contributes one citation count, not one per unit author.
            values = [p.get('citations') for p in (current, incoming)
                      if isinstance(p.get('citations'), int) and not isinstance(p.get('citations'), bool)]
            if values:
                current['citations'] = max(values)
            for field in ('wos', 'jcr', 'quartile'):
                if incoming.get(field) and (not current.get(field) or
                        str(incoming[field].get('checked_at') or '') > str(current[field].get('checked_at') or '')):
                    current[field] = incoming[field]
            status = incoming.get('publication_status') or {}
            if status.get('code') not in (None, 'unknown') and (current.get('publication_status') or {}).get('code') in (None, 'unknown'):
                current['publication_status'] = status
        current = papers[match]
        if current.get('doi'):
            by_doi[doi_key(current['doi'])] = match
        for key in _fallback_keys(current):
            by_title.setdefault(key, set()).add(match)
    for paper in papers:
        identity = ('doi', doi_key(paper.get('doi'))) if paper.get('doi') else (
            'record', title_key(paper['title']), paper.get('year'), paper.get('type'),
            sorted(fold(a) for a in paper.get('authors') or []), paper.get('source_id') or '',
            sorted((ref['person_key'], str(ref.get('pid') or '')) for ref in paper['profile_refs']))
        paper['key'] = 'unit:' + _hash(identity)
        paper['id'] = 'U' + _hash(identity)
    return sorted(papers, key=lambda p: (-(p.get('year') or 0), fold(p['title']), p['key']))


def _metrics(result: dict) -> dict:
    papers = [p for p in result.get('publications') or [] if p.get('title')]
    citations = [p['citations'] for p in papers if isinstance(p.get('citations'), int) and not isinstance(p['citations'], bool)]
    return {'publication_count': len(papers),
            'article_count': sum(str(p.get('type') or '').lower() in _ARTICLE_TYPES for p in papers),
            'citations': sum(citations) if citations or not papers else None,
            'sources': sorted({s for p in papers for s in _sources(p)}),
            'job_id': result.get('job_id'), 'chat_id': result.get('chat_id')}


def _valid(result) -> bool:
    return isinstance(result, dict) and isinstance(result.get('profile'), dict) and isinstance(result.get('publications'), list)


def seed(person: dict, result: dict, institution: str, domain: str) -> None:
    """Expose saved profiles without requiring another network collection."""
    if _valid(result):
        _PERSON_CACHE[person_key(person, institution, domain)] = copy.deepcopy(result)


def snapshot(job_id: str) -> dict | None:
    job = JOBS.get(job_id)
    if not job:
        return None
    if job.get('_dirty'):
        job['papers'] = aggregate(job['_results'], job['_people'])
        job['by_source'] = dict(Counter(s for p in job['papers'] for s in p.get('sources') or []))
        job['_dirty'] = False
    return copy.deepcopy({k: v for k, v in job.items() if not k.startswith('_')})


def _active(jid: str) -> bool:
    task = TASKS.get(jid)
    return (task is not None and not task.done()) or any(
        j == jid and not t.done() for (j, _), t in PERSON_TASKS.items())


def _unit_key(unit: str) -> str:
    # The caller supplies a full route identity, not a faculty/department label.
    return _hash(unit)


def _persist(job: dict) -> None:
    """Replace one complete cache document; a failed write keeps the prior file."""
    temporary = None
    try:
        data = {'version': CACHE_VERSION, 'unit': job['unit'],
                'snapshot': snapshot(job['job_id']),
                'people': job['_people'], 'results': job['_results']}
        data['snapshot'].pop('cache_error', None)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=CACHE_DIR,
                                         prefix='.unit-', suffix='.tmp', delete=False) as handle:
            temporary = handle.name
            json.dump(data, handle, ensure_ascii=False, default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, CACHE_DIR / f"{_unit_key(job['unit'])}.json")
    except (OSError, TypeError, ValueError) as exc:
        # Cache failure must not discard already collected publications or expose
        # filesystem paths/source response bodies in the API error message.
        _LOG.warning('Unit publication cache could not be written (%s)', type(exc).__name__)
        job['cache_error'] = 'Sonuç diske kaydedilemedi; bu oturumdaki kayıt korunuyor.'
    else:
        job.pop('cache_error', None)
        job['_persisted'] = True
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _interrupted(job: dict) -> None:
    """A persisted/inactive running job is evidence to show, never to auto-retry."""
    known = bool(job.get('_results') or job.get('papers'))
    job['status'] = 'partial' if known else 'cancelled'
    job['cached'] = True
    job['finished_at'] = time.time()
    job['interrupted'] = True
    note = 'Önceki toplama tamamlanmadı; devam etmek için Tekrar tara kullanın.'
    if note not in job['warnings']:
        job['warnings'].append(note)
    for staff in job['staff']:
        if staff.get('status') in ('pending', 'running'):
            staff['status'] = 'cancelled'
            if staff.get('name') and staff['name'] not in job['missing']:
                job['missing'].append(staff['name'])


def _unreadable_cache(unit: str) -> dict:
    """An existing unreadable record also requires an explicit retry."""
    jid = uuid.uuid4().hex[:12]
    return {'job_id': jid, 'status': 'error', 'unit': unit, 'institution': '', 'domain': '',
            'papers': [], 'people': 0, 'total_people': 0, 'completed': 0, 'matched': 0,
            'missing': [], 'errors': ['Kayıtlı birim sonucu okunamadı; Tekrar tara ile yenileyin.'],
            'warnings': [], 'staff': [], 'by_source': {}, 'cached': True,
            'cache_error': 'Kayıt dosyası okunamıyor veya sürümü desteklenmiyor.',
            '_people': {}, '_results': {}, '_dirty': False, '_persisted': True}


def cached_unit(unit: str) -> dict | None:
    """Return an active job or an indefinitely saved unit, with no network work."""
    key = _unit_key(unit)
    jid = _KEYS.get(key)
    if jid not in JOBS:
        # Jobs created before the permanent cache keyed on both roster and unit.
        # Reuse those in-memory results too, without needing their old key formula.
        matching = [(job_id, job) for job_id, job in JOBS.items() if job.get('unit') == unit]
        if matching:
            jid, _ = max(matching, key=lambda item: (
                item[0] in TASKS and not TASKS[item[0]].done(), item[1].get('started_at', 0)))
            _KEYS[key] = jid
    if jid in JOBS:
        job = JOBS[jid]
        if _active(jid):
            return snapshot(jid)
        if job['status'] == 'running':
            _interrupted(job)
            _persist(job)
        job['cached'] = True
        if not job.get('_persisted'):
            _persist(job)
        return snapshot(jid)
    path = CACHE_DIR / f'{key}.json'
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return None
    except (OSError, ValueError, UnicodeError):
        job = _unreadable_cache(unit)
    else:
        try:
            if not isinstance(data, dict) or data.get('version') != CACHE_VERSION or data.get('unit') != unit:
                raise ValueError('unsupported cache')
            saved, people, results = data['snapshot'], data['people'], data['results']
            if not isinstance(saved, dict) or saved.get('unit') != unit:
                raise ValueError('invalid snapshot')
            if not isinstance(saved.get('job_id'), str) or not saved['job_id']:
                raise ValueError('invalid job identity')
            if not isinstance(people, dict) or not isinstance(results, dict):
                raise ValueError('invalid person results')
            if any(not isinstance(p, dict) for p in people.values()) or any(
                    identity not in people or not _valid(result) for identity, result in results.items()):
                raise ValueError('invalid person result')
            for field in ('papers', 'staff', 'missing', 'errors', 'warnings'):
                if not isinstance(saved.get(field), list):
                    raise ValueError('invalid snapshot list')
            for field in ('people', 'total_people', 'completed', 'matched'):
                if not isinstance(saved.get(field), int) or isinstance(saved[field], bool) or saved[field] < 0:
                    raise ValueError('invalid snapshot count')
            if not isinstance(saved.get('by_source'), dict):
                raise ValueError('invalid source counts')
            if any(not isinstance(row, dict) for row in saved['papers'] + saved['staff']):
                raise ValueError('invalid snapshot row')
            if saved.get('status') not in ('running', 'done', 'partial', 'error', 'cancelled'):
                raise ValueError('invalid snapshot status')
            job = {k: v for k, v in saved.items() if not k.startswith('_')}
            job.update(_people=people, _results=results, _dirty=False, _persisted=True, cached=True)
            if job['status'] == 'running':
                _interrupted(job)
        except (KeyError, TypeError, ValueError):
            job = _unreadable_cache(unit)
    jid = job['job_id']
    if jid in JOBS:
        # A corrupt/stale file must not replace a different unit's live job.
        jid = job['job_id'] = uuid.uuid4().hex[:12]
    JOBS[jid] = job
    _KEYS[key] = jid
    return snapshot(jid)


def start(people: list[dict], institution: str, domain: str, unit: str, collect_person,
          *, refresh: bool = False, collect: bool | None = None) -> dict:
    """Birimi açar. collect=False: ağ taraması yok; kadro adları ve sistemde kayıtlı profiller gösterilir,
    kaydı olmayanlar "idle" kalır (kişi başına Yenile ya da birim için Tekrar tara ile taranır)."""
    collect = refresh if collect is None else collect
    previous = cached_unit(unit)
    if previous and _active(previous['job_id']):
        return previous
    previous_results = JOBS[previous['job_id']]['_results'] if previous else {}
    distinct = {}
    for person in people:
        if person.get('name'):
            distinct.setdefault(person_key(person, institution, domain), copy.deepcopy(person))
    key = _unit_key(unit)
    jid = uuid.uuid4().hex[:12]
    staff, results = [], {}
    for identity, person in distinct.items():
        row = {**person, 'person_key': identity, 'status': 'pending', 'publication_count': None,
               'article_count': None, 'citations': None, 'sources': [], 'job_id': None, 'chat_id': None,
               'cached': False, 'warnings': []}
        known = _PERSON_CACHE.get(identity) or previous_results.get(identity)
        if _valid(known):
            results[identity] = copy.deepcopy(known)
            row.update(_metrics(known), cached=True, warnings=list(known.get('collection_warnings') or []))
        staff.append(row)
    use_saved_profiles = not collect
    JOBS[jid] = {'job_id': jid, 'status': 'running', 'unit': unit, 'institution': institution,
                 'domain': domain, 'papers': [], 'people': len(distinct), 'total_people': len(distinct),
                 'completed': 0, 'matched': len(results), 'missing': [], 'errors': [], 'warnings': [], 'staff': staff,
                 'cached': bool(results) or bool(previous),
                 'by_source': {}, 'started_at': time.time(), '_people': distinct,
                 '_results': results, '_dirty': True}
    _KEYS[key] = jid
    if use_saved_profiles:
        job = JOBS[jid]
        for row in staff:
            if row['cached']:
                row['status'] = 'partial' if row['warnings'] else 'done'
                job['warnings'].extend({'person_key': row['person_key'], 'name': row['name'], 'message': message}
                                       for message in row['warnings'])
            else:
                row['status'] = 'idle'  # taranmadı; kullanıcı Yenile ile başlatır
        job['completed'] = len(results)
        job['idle'] = sum(row['status'] == 'idle' for row in staff)
        job['status'] = 'partial' if job['warnings'] else 'done'
        job['finished_at'] = time.time()
        _persist(job)
        return snapshot(jid)
    _persist(JOBS[jid])
    TASKS[jid] = asyncio.create_task(_run(jid, collect_person))
    return snapshot(jid)


def _gate() -> asyncio.Semaphore:
    global _GATE, _GATE_LOOP
    loop = asyncio.get_running_loop()
    if _GATE_LOOP is not loop:
        _GATE, _GATE_LOOP = asyncio.Semaphore(CONCURRENCY), loop
    return _GATE


async def _collect_one(job: dict, staff: dict, collect_person, *, count: bool = True):
    identity = staff['person_key']
    person = job['_people'][identity]
    staff['status'] = 'running'
    for bucket in (job['missing'],):
        while person['name'] in bucket:
            bucket.remove(person['name'])
    job['errors'] = [e for e in job['errors'] if not (isinstance(e, dict) and e.get('person_key') == identity)]
    job['warnings'] = [w for w in job['warnings'] if not (isinstance(w, dict) and w.get('person_key') == identity)]

    def update(value, final=False):
        if not _valid(value):
            return
        # Empty intermediate/failed stages must not blank an existing profile.
        previous = job['_results'].get(identity)
        warnings = list(value.get('collection_warnings') or [])
        if not value['publications'] and previous and previous.get('publications') and (not final or warnings):
            if final:
                staff.update(_metrics(previous), cached=True, warnings=warnings)
                job['_results'][identity]['collection_warnings'] = warnings
            return
        job['_results'][identity] = copy.deepcopy(value)
        staff.update(_metrics(value), cached=False)
        staff['warnings'] = warnings
        job['_dirty'] = True
        job['matched'] = len(job['_results'])

    try:
        value = await collect_person(person, job['institution'], job['domain'], on_update=update)
        if not _valid(value):
            staff['status'] = 'missing'
            job['missing'].append(person['name'])
            if identity in job['_results']:
                staff['cached'] = True
        else:
            update(value, final=True)
            _PERSON_CACHE[identity] = copy.deepcopy(job['_results'][identity])
            staff['status'] = 'partial' if staff['warnings'] else 'done'
            job['warnings'].extend({'person_key': identity, 'name': person['name'], 'message': message}
                                   for message in staff['warnings'])
    except asyncio.CancelledError:
        staff['status'] = 'cancelled'
        raise
    except Exception as exc:
        staff['status'] = 'error'
        job['missing'].append(person['name'])
        job['errors'].append({'person_key': identity, 'name': person['name'], 'error': type(exc).__name__})
        if identity in job['_results']:
            staff['cached'] = True
    finally:
        if count:
            job['completed'] += 1
        job['idle'] = sum(row.get('status') == 'idle' for row in job['staff'])
        _persist(job)


def _final_status(job: dict) -> str:
    return ('partial' if (job['missing'] or job['warnings']) and job['_results'] else
            'error' if job['missing'] else 'done')


async def _run(jid: str, collect_person):
    job = JOBS[jid]
    pending = iter(job['staff'])
    gate = _gate()

    async def worker():
        for staff in pending:
            async with gate:
                await _collect_one(job, staff, collect_person)

    try:
        await asyncio.gather(*(worker() for _ in range(min(CONCURRENCY, len(job['staff'])))))
        job['status'] = _final_status(job)
    except asyncio.CancelledError:
        job['status'] = 'cancelled'
        for staff in job['staff']:
            if staff['status'] in ('pending', 'running'):
                staff['status'] = 'cancelled'
        raise
    finally:
        job['finished_at'] = time.time()
        job['cached'] = True
        _persist(job)
        TASKS.pop(jid, None)


def refresh_person(job_id: str, person_key: str, collect_person) -> dict | None:
    """Birim içinde tek kişiyi tarar (kişi satırındaki Yenile). Diğer satırlar beklemez."""
    job = JOBS.get(job_id)
    if job is None:
        return None
    staff = next((row for row in job['staff'] if row.get('person_key') == person_key), None)
    if staff is None:
        return None
    key = (job_id, person_key)
    if key in PERSON_TASKS and not PERSON_TASKS[key].done():
        return snapshot(job_id)
    if staff.get('status') in ('idle', 'missing', 'error', 'cancelled'):
        job['completed'] = sum(row.get('status') in ('done', 'partial') for row in job['staff'])
    staff['status'] = 'pending'
    job['status'] = 'running'
    job['_dirty'] = True

    async def run():
        try:
            async with _gate():
                await _collect_one(job, staff, collect_person, count=False)
        finally:
            PERSON_TASKS.pop(key, None)
            job['completed'] = sum(row.get('status') in ('done', 'partial') for row in job['staff'])
            if not _active(job_id):
                job['status'] = _final_status(job) if any(r.get('status') != 'idle' for r in job['staff']) else 'done'
                job['finished_at'] = time.time()
            job['cached'] = True
            _persist(job)

    PERSON_TASKS[key] = asyncio.create_task(run())
    return snapshot(job_id)


async def close():
    singles = list(PERSON_TASKS.values())
    for task in singles:
        task.cancel()
    await asyncio.gather(*singles, return_exceptions=True)
    pending = list(TASKS.items())
    tasks = [task for _, task in pending]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    # A task cancelled before its coroutine first runs cannot execute its finally.
    for jid, task in pending:
        job = JOBS.get(jid)
        if job and job['status'] == 'running':
            _interrupted(job)
            _persist(job)
        if TASKS.get(jid) is task:
            TASKS.pop(jid, None)
