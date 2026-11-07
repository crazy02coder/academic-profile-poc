"""Doğrulanmış WoS yayınlarını mevcut profile kayıpsız ve yinelenmeden ekle."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import time
from collections import Counter

from rapidfuzz import fuzz

from .config import ROOT
from .text import LANG_NAMES, detect_language, doi_key, fold, title_key

CACHE = ROOT / 'data' / 'wos' / 'profiles'
SUCCESS_TTL = 86400
FAILURE_TTL = 900
UPDATE_FIELDS = ('publications', 'unique_count', 'raw_count', 'by_source',
                 'paper_verification', 'languages', 'summary')


def profile_key(profile: dict) -> str:
    links = profile.get('links') or {}
    identity = [fold(profile.get('name') or profile.get('query_name') or ''),
                profile.get('orcid') or links.get('orcid') or '',
                re.sub(r'.*authorId=([^&]+).*', r'\1', links.get('yok') or ''),
                fold(profile.get('institution') or '')]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


def is_checkpoint(report: dict | None) -> bool:
    """Incomplete progress preserves verified records but never suppresses collection."""
    return bool(report and (report.get('reason') == 'interrupted_checkpoint' or report.get('complete') is False))


def cached(profile: dict, *, allow_stale: bool = False) -> dict | None:
    from .wos import needs_verification_retry

    try:
        entry = json.loads((CACHE / f'{profile_key(profile)}.json').read_text())
        if not allow_stale and (is_checkpoint(entry) or needs_verification_retry(entry)):
            return None
        ttl = SUCCESS_TTL if entry.get('status') == 'done' else FAILURE_TTL
        if allow_stale or time.time() - entry['at'] < ttl:
            return entry
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def save(profile: dict, report: dict):
    from .wos import MANUAL_VERIFICATION_VERSION

    # Geçici erişim hatası önceden doğrulanmış kayıtları silmez. Her kaydın
    # kendi checked_at değeri korunur; yeni kontrol eski kanıtı yenilemiş sayılmaz.
    previous = cached(profile, allow_stale=True) or {}
    records = {r.get('source_id') or (r.get('wos') or {}).get('url'): r
               for r in previous.get('records') or []}
    records.update({r.get('source_id') or (r.get('wos') or {}).get('url'): r
                    for r in report.get('records') or []})
    report['records'] = list(records.values())
    report['manual_verification_version'] = MANUAL_VERIFICATION_VERSION
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f'{profile_key(profile)}.json'
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps({**report, 'at': time.time()}, ensure_ascii=False))
    tmp.replace(path)


def _titles(p: dict) -> set[str]:
    return {title_key(v) for v in [p.get('title') or '',
            *(v.get('title') or '' for v in p.get('variants') or [])] if v}


def _shared_authors(a: dict, b: dict) -> int:
    def parts(value):
        if ',' in value:
            family, given = value.split(',', 1)
            value = f'{given} {family}'
        return fold(value).split()
    matched = set()
    for a_name in a.get('authors') or []:
        x = parts(a_name)
        for index, b_name in enumerate(b.get('authors') or []):
            y = parts(b_name)
            if (len(x) >= 2 and len(y) >= 2 and x[-1] == y[-1] and
                    (x[0] == y[0] or min(len(x[0]), len(y[0])) == 1 and x[0][0] == y[0][0])):
                matched.add(index)
                break
    return len(matched)


def _profile_context(paper: dict, profile: dict) -> bool:
    """Yazar alanı boş YÖK kaydı ancak aynı seçilmiş kişi sayfasından geliyorsa eşleşir."""
    actual = re.search(r'authorId=([0-9A-Fa-f]+)', (paper.get('yok_context') or {}).get('profile_url') or '')
    expected = re.search(r'authorId=([0-9A-Fa-f]+)', (profile.get('links') or {}).get('yok') or '')
    return bool(actual and expected and actual[1].lower() == expected[1].lower())


def _same_kind(a: dict, b: dict) -> bool:
    def kind(p):
        value = p.get('type') or ''
        return {'journal-article': 'article', 'review': 'article', 'proceedings-article': 'conference-paper'}.get(value, value)
    return not kind(a) or not kind(b) or kind(a) == kind(b)


def _match(papers: list[dict], record: dict, profile: dict) -> tuple[dict | None, bool]:
    """Önce WoS kimliği/DOI, DOI eksikse başlık+yıl+yazar; belirsiz çifti atla."""
    doi = doi_key(record.get('doi'))
    accession = (record.get('wos') or {}).get('accession') or record.get('source_id')
    if any(accession and accession == (p.get('wos') or {}).get('accession') and
           doi and doi_key(p.get('doi')) and doi != doi_key(p.get('doi')) for p in papers):
        return None, True
    exact = [p for p in papers if
             (accession and accession == (p.get('wos') or {}).get('accession')) or
             (doi and doi_key(p.get('doi')) == doi)]
    if exact:
        return (exact[0], False) if len(exact) == 1 else (None, True)
    candidates = []
    for p in papers:
        other_doi = doi_key(p.get('doi'))
        if doi and other_doi and doi != other_doi:
            continue
        shared_authors = _shared_authors(record, p)
        author_match = shared_authors > 0 or (not p.get('authors') and _profile_context(p, profile)
                        and bool(p.get('venue')) and fold(p['venue']) == fold(record.get('venue') or ''))
        if (record.get('year') and record['year'] == p.get('year') and
                _titles(record) & _titles(p) and author_match and _same_kind(record, p)):
            candidates.append(p)
            continue
        # Yıl farkı/yazım hatası tek başına yeterli değil: aynı tür, en az iki
        # ortak yazar ve neredeyse birebir uzun özet gerekir. Farklı DOI yukarıda elenir.
        a, b = fold(record.get('abstract') or ''), fold(p.get('abstract') or '')
        if (record.get('year') and p.get('year') and abs(record['year'] - p['year']) <= 1
                and _same_kind(record, p) and shared_authors >= 2 and min(len(a), len(b)) >= 200
                and fuzz.ratio(a, b) >= 98
                and max((fuzz.ratio(x, y) for x in _titles(record) for y in _titles(p)), default=0) >= 96):
            candidates.append(p)
    return (candidates[0], False) if len(candidates) == 1 else (None, len(candidates) > 1)


def apply(result: dict, records: list[dict], report: dict | None = None) -> dict:
    """Kimlik doğrulamasından geçmiş kayıtlar içindir; mevcut P# ve alanlar korunur.

    Bir profil açıkken sıralama değişse de sohbet atıfları/favoriler eski yayını
    göstermeye devam eder. Yeni yayınlar yalnızca yeni P# kimliği alır.
    """
    papers = result.setdefault('publications', [])
    max_id = max((int(p['id'][1:]) for p in papers if re.fullmatch(r'P\d+', p.get('id', ''))), default=0)
    added = matched = rejected = 0
    for raw in records:
        if raw.get('source') != 'wos' or not raw.get('title') or not (raw.get('wos') or {}).get('url'):
            rejected += 1
            continue
        record = copy.deepcopy(raw)
        record['wos']['year'] = record.get('year')
        current, ambiguous = _match(papers, record, result.get('profile') or {})
        if ambiguous:
            rejected += 1
            continue
        lang, confidence = detect_language(record['title'], record.get('abstract') or '')
        variant = {'title': record['title'], 'lang': lang, 'source': 'wos'}
        if current is None:
            max_id += 1
            current = {**record, 'id': f'P{max_id}', 'sources': ['wos'],
                       'lang': lang, 'lang_conf': confidence, 'variants': [variant],
                       'languages': [lang], 'language_names': [LANG_NAMES.get(lang, lang)],
                       'runs_seen': 1, 'verified': False, 'is_new': True}
            papers.append(current)
            added += 1
        else:
            matched += 1
            current['sources'] = list(dict.fromkeys([*(current.get('sources') or [current.get('source')]), 'wos']))
            current['sources'] = [s for s in current['sources'] if s]
            current['wos'] = record['wos']
            for key in ('doi', 'venue', 'issn', 'abstract', 'year', 'date', 'url', 'type', 'authors'):
                if not current.get(key) and record.get(key):
                    current[key] = record[key]
                    if key == 'abstract':
                        current['abstract_source'] = 'wos'
                        current['abstract_url'] = record['wos']['url']
            if record.get('jcr'):
                current['jcr'] = record['jcr']
            if title_key(record['title']) not in _titles(current):
                current.setdefault('variants', []).append(variant)
            current['verified'] = len(current['sources']) >= 2 or bool(current.get('verified'))
        # WoS atıfları kaynağıyla saklanır; OpenAlex sayısının üzerine yazılmaz.
        if isinstance(record.get('citations'), int):
            current.setdefault('citations_by_source', {})['wos'] = record['citations']

    papers.sort(key=lambda p: (-(p.get('year') or 0), p.get('title') or ''))
    counts = result.setdefault('by_source', {})
    old_wos = counts.get('wos', 0)
    counts['wos'] = sum('wos' in (p.get('sources') or []) for p in papers)
    result['raw_count'] = max(0, result.get('raw_count', len(papers) - added) - old_wos) + counts['wos']
    result['unique_count'] = len(papers)
    result['languages'] = dict(Counter(lang for p in papers for lang in p.get('language_names') or []))
    verification = result.setdefault('paper_verification', {})
    verification.update(multi_source=sum(len(p.get('sources') or []) > 1 for p in papers),
                        verified=sum(bool(p.get('verified')) for p in papers),
                        new=sum(bool(p.get('is_new')) for p in papers))
    result.setdefault('dedup', {}).update(raw=result['raw_count'], unique=len(papers))
    result['summary'] = (f"{result.get('profile', {}).get('name', '')} için "
                         f"{result['raw_count']} ham kayıt ve {len(papers)} benzersiz yayın derlendi.")
    meta = {k: v for k, v in (report or {}).items() if k not in ('records', '_merge_totals')}
    prior = (report or {}).get('_merge_totals') or {}
    total_added = prior.get('added', 0) + added
    meta.update(added=total_added, new=total_added,
                matched=prior.get('matched', 0) + matched,
                merge_rejected=prior.get('merge_rejected', 0) + rejected)
    result['wos_enrichment'] = meta
    payload = {k: result.get(k) for k in UPDATE_FIELDS}
    result['wos_revision'] = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
    return {'added': added, 'matched': matched, 'rejected': rejected}


def publication_update(result: dict) -> dict:
    return {k: result.get(k) for k in UPDATE_FIELDS}
