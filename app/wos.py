"""WoS full-record sayfasındaki JCR çeyrekleri; SJR'den ayrı, DOI ile doğrulanmış.

Profil açılırken arka planda çalışır. Çeyrek yılı açıklanmıyorsa null kalır;
yayın yılı veya JCI yılı JCR yılı yerine kullanılmaz. Giriş/engel sayfaları
sonuç sayılmaz. Başarılı kayıtlar 7 gün, başarısız kontroller 15 dakika saklanır.
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
import re
import time
from contextlib import AsyncExitStack
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from scrapling import Selector
from scrapling.fetchers import AsyncStealthySession

from . import wos_verification
from .config import ROOT
from .text import clean, doi_key, fold

CACHE = ROOT / 'data' / 'wos'
RECORDS = Path(__file__).with_name('wos_records.json')
SUCCESS_TTL = 7 * 86400
FAILURE_TTL = 900
MANUAL_VERIFICATION_VERSION = 1
RUNS: dict[str, dict] = {}
TASKS: dict[str, asyncio.Task] = {}
_GATE = None
_GATE_LOOP = None
logger = logging.getLogger(__name__)


class AccessUnavailable(Exception):
    pass


def needs_verification_retry(entry: dict) -> bool:
    """Manuel panelden önceki insan doğrulama engelini bir kez yeniden kontrol et."""
    if not isinstance(entry, dict) or entry.get('status') not in ('blocked', 'partial', 'error'):
        return False
    version = entry.get('manual_verification_version')
    if isinstance(version, int) and version >= MANUAL_VERIFICATION_VERSION:
        return False
    reason = str(entry.get('reason') or '').lower()
    detail = str(entry.get('access_detail') or '').lower()
    # Kullanıcının iptal ettiği veya süresi dolan yeni panel otomatik açılmasın.
    if reason.startswith('manual_') or detail.startswith('manual_'):
        return False
    evidence = fold(' '.join(str(entry.get(key) or '') for key in ('reason', 'access_detail', 'message')))
    if detail in ('hcaptcha', 'human_verification', 'verification', 'verification_required') or \
            reason in ('hcaptcha', 'human_verification', 'verification_required') or \
            any(marker in evidence for marker in ('hcaptcha', 'human verification', 'human_verification',
                                                   'verify you are human', 'insan dogrulamasi')):
        return True
    publications = entry.get('publications')
    return isinstance(publications, dict) and needs_verification_retry(publications)


def record_url(value: str) -> str:
    """Seçilmiş WoS kayıt URL'leri dışında ağ hedefi kabul edilmez."""
    try:
        u = urlparse(unquote(value or ''))
        port = u.port
    except ValueError:
        return ''
    if u.scheme not in ('https', 'http') or u.hostname != 'www.webofscience.com' or u.username or u.password or port:
        return ''
    m = re.fullmatch(r'/wos/(?:woscc|alldb)/full-record/(WOS:\d+)', u.path)
    return f'https://www.webofscience.com/wos/woscc/full-record/{m[1]}' if m else ''


def eligible(p: dict) -> bool:
    return bool(doi_key(p.get('doi')) and p.get('type') in ('article', 'journal-article', 'review'))


def key(p: dict) -> str:
    return hashlib.sha256(doi_key(p.get('doi')).encode()).hexdigest()


def cached(p: dict) -> dict | None:
    try:
        entry = json.loads((CACHE / f'{key(p)}.json').read_text())
        if entry.get('doi') != doi_key(p.get('doi')):
            return None
        if needs_verification_retry(entry):
            return None
        ttl = SUCCESS_TTL if entry.get('status') == 'ok' else FAILURE_TTL
        if time.time() - entry['at'] < ttl:
            return entry
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def save(p: dict, entry: dict):
    entry['manual_verification_version'] = MANUAL_VERIFICATION_VERSION
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f'{key(p)}.json'
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps({'doi': doi_key(p.get('doi')), 'at': time.time(), **entry}, ensure_ascii=False))
    tmp.replace(path)


def remember_publication(record: dict):
    """Profil önbelleğini okumak JCR verisinin kontrol tarihini yenilemez."""
    if not record.get('doi'):
        return
    checked = (record.get('wos') or {}).get('checked_at') or (record.get('jcr') or {}).get('checked_at')
    try:
        at = datetime.fromisoformat(checked).timestamp()
    except (ValueError, TypeError):
        return
    previous = cached(record)
    if previous and previous.get('at', 0) >= at:
        return
    value = {'status': 'ok', 'jcr': record['jcr']} if record.get('jcr') else \
            {'status': 'not_found', 'reason': 'no_jcr_data'}
    save(record, {**value, 'at': at})


def known_urls(p: dict) -> list[str]:
    try:
        known = json.loads(RECORDS.read_text())
    except (OSError, ValueError):
        known = {}
    values = [known.get(doi_key(p.get('doi')), ''), (p.get('wos') or {}).get('url'),
              p.get('wos_url'), p.get('url'), p.get('source_id')]
    return list(dict.fromkeys(u for v in values if (u := record_url(v))))


def parse_record(html: str, url: str, paper: dict) -> dict | None:
    """Yalnız JIF/JCR tablosunu oku; JCI metrikleri ve arama özetlerini alma."""
    source_url = record_url(url)
    if not source_url:
        raise AccessUnavailable('WoS giriş sayfasına yönlendirdi.')
    sel = Selector(html)
    visible = clean(sel.get_all_text(separator=' ', ignore_tags=('script', 'style', 'noscript')))
    if any(s in visible.lower() for s in ('sign in to continue', 'access denied', 'verify you are human')):
        raise AccessUnavailable('WoS erişimi doğrulanamadı.')
    nodes = sel.css('[data-ta="FullRTa-DOI"]')
    actual_doi = doi_key(nodes[0].get_all_text() if nodes else '')
    if not actual_doi or actual_doi != doi_key(paper.get('doi')):
        return None
    categories = []
    # WoS aynı paneli birden çok kez DOM'a koyabilir; kategori/çeyrek tek kayıt olur.
    for row in sel.css('tr'):
        names = row.css('[data-ta*="-JCR-category-name_"]')
        qs = row.css('[data-ta*="-JCR-quartile_"]')
        if not names or not qs:
            continue
        name = clean(names[0].get_all_text())
        q = clean(qs[0].get_all_text())
        ed = row.css('[data-ta*="-JCR-edition_"]')
        edition = clean(ed[0].get_all_text()) if ed else ''
        item = {'name': name, 'q': q, 'edition': edition}
        if name and re.fullmatch(r'Q[1-4]', q) and item not in categories:
            categories.append(item)
    if not categories:
        return None
    # Yıl yalnız açıkça etiketlenmiş JCR/JIF yıl düğümünden alınır.
    years = set()
    for node in sel.css('[data-ta*="-JCR-year"], [data-ta*="-JIF-year"]'):
        years.update(re.findall(r'\b(?:19|20)\d{2}\b', node.get_all_text()))
    return {'source': 'JCR', 'year': int(next(iter(years))) if len(years) == 1 else None,
            'categories': categories, 'url': source_url, 'doi': actual_doi,
            'journal': paper.get('venue', ''), 'checked_at': datetime.now(timezone.utc).isoformat()}


async def lookup(p: dict, session) -> dict:
    """Aynı WoS oturumunda önce DOI, ardından başlıkla kayıt keşfet.

    Çağıran _run arama + sayfa okumalarını insan doğrulaması hariç 90 saniyeyle sınırlar.
    En çok altı aday okunur; başlık aramasında da DOI birebir eşleşmek zorundadır.
    """
    from . import wos_publications

    seen = set()
    failure_reasons = set()
    search_unavailable = record_unavailable = truncated = False
    doi = doi_key(p.get('doi'))
    if not doi:
        return {'status': 'error', 'reason': 'doi_required'}

    async def read(url: str) -> dict | None:
        nonlocal record_unavailable
        if url in seen:
            return None
        seen.add(url)
        # JCR okuması da aynı canlı sekmede kullanıcı doğrulamasını bekleyebilir.
        try:
            html, final_url = await wos_publications._fetch(session, url, settle_ms=12000)
            value = parse_record(html, final_url, p)
        except AccessUnavailable:
            raise
        except Exception:
            logger.exception('WoS aday kaydı okunamadı: %s', url)
            record_unavailable = True
            return None
        if value:
            return {'status': 'ok', 'jcr': value}
        nodes = Selector(html).css('[data-ta="FullRTa-DOI"]')
        actual = doi_key(nodes[0].get_all_text() if nodes else '')
        if actual == doi:
            # Doğru yayın bulundu; aynı kayıt için başka keşif sorgusu gereksiz.
            return {'status': 'not_found', 'reason': 'no_jcr_data'}
        failure_reasons.add('record_doi_missing' if not actual else 'doi_mismatch')
        return None

    for url in known_urls(p)[:3]:
        if value := await read(url):
            return value

    # WoS çift tırnakla exact phrase arar; iç tırnağın backslash ile kaçırılması
    # belgelenmemiştir. Başlıktaki tırnak/wildcard işaretlerini sorguya taşımayız.
    special = '"“”„‟«»\\*?$'
    title = clean((p.get('title') or '').translate(str.maketrans({c: ' ' for c in special})))[:1000]
    queries = [('DOI', f'"{doi}"')] if not any(c in doi for c in special) else []
    if title:
        queries.append(('Title', f'"{title}"'))
    if not queries:
        return {'status': 'error', 'reason': 'unsupported_search_query'}
    for field, query in queries:
        if len(seen) >= 6:
            truncated = True
            break
        try:
            html, page_url = await wos_publications._search(session, field, query, max_results=3)
            urls, more = wos_publications.result_links(html, page_url)
            total = wos_publications.result_count(html)
            visible = clean(Selector(html).get_all_text(separator=' ', ignore_tags=('script', 'style', 'noscript')))
            empty = total == 0 or re.search(
                r'no results found|found no results|no records found|did not return any results|no matching records', visible, re.I)
            if not urls and not empty:
                search_unavailable = True
                continue
        except AccessUnavailable:
            raise
        except Exception:
            logger.exception('WoS doğrudan %s araması tamamlanamadı', field)
            search_unavailable = True
            continue
        candidates = [url for url in urls if url not in seen]
        selected = candidates[:min(3, 6 - len(seen))]
        truncated = truncated or more or len(candidates) > len(selected) or (total is not None and total > len(urls))
        for url in selected:
            if value := await read(url):
                return value
    if search_unavailable:
        return {'status': 'error', 'reason': 'search_unavailable'}
    if record_unavailable:
        return {'status': 'error', 'reason': 'record_unavailable'}
    if truncated:
        return {'status': 'error', 'reason': 'candidate_limit'}
    if 'doi_mismatch' in failure_reasons:
        return {'status': 'not_found', 'reason': 'doi_mismatch'}
    if 'record_doi_missing' in failure_reasons:
        return {'status': 'not_found', 'reason': 'record_doi_missing'}
    return {'status': 'not_found', 'reason': 'no_record_candidates'}


def annotate(papers: list[dict]):
    for p in papers:
        if eligible(p):
            entry = cached(p)
            p.pop('jcr', None)
            if entry and entry.get('jcr'):
                p['jcr'] = entry['jcr']


def snapshot(result: dict) -> dict:
    annotate(result.get('publications', []))
    state = RUNS.get(result['job_id'], {'status': 'idle', 'checked': 0, 'total': 0})
    response = {**state, 'items': {p['id']: p['jcr'] for p in result.get('publications', []) if p.get('jcr')}}
    if result.get('wos_revision'):
        from .wos_enrichment import publication_update
        response.update(revision=result['wos_revision'], publication_update=publication_update(result))
    return response


def access_gate():
    """Profil ve konu taramaları aynı WoS tarayıcı sırasını paylaşır."""
    global _GATE, _GATE_LOOP
    loop = asyncio.get_running_loop()
    if _GATE_LOOP is not loop:
        _GATE, _GATE_LOOP = asyncio.Lock(), loop
    return _GATE


async def _run(result: dict, retry: bool, on_publications=None):
    from . import wos_enrichment, wos_publications

    jid = result['job_id']
    state = RUNS[jid]
    papers = sorted((p for p in result.get('publications', []) if eligible(p)), key=lambda p: not bool(known_urls(p)))
    applied_records = set()
    merge_totals = {'added': 0, 'matched': 0, 'merge_rejected': 0}

    def record_key(record):
        return record.get('source_id') or (record.get('wos') or {}).get('url') or doi_key(record.get('doi'))

    def progress(report):
        meta = {k: v for k, v in report.items() if k != 'records'}
        meta.update(status='running', complete=False, phase='publications',
                    merge_totals=dict(merge_totals))
        state.update(status='running', phase='publications', publications=meta)
        for field in ('checked', 'candidates', 'matched', 'new', 'rejected'):
            state[field] = report.get(field, 0)

    async def publish(records, report):
        nonlocal result
        for record in records:
            remember_publication(record)
        metadata = {**report, '_merge_totals': dict(merge_totals)}
        if on_publications:
            updated = on_publications(records, metadata)
            if inspect.isawaitable(updated):
                updated = await updated
            if updated is None:
                raise asyncio.CancelledError()  # Silinmiş/değişmiş profili yeniden oluşturma.
            result = updated
        else:
            wos_enrichment.apply(result, records, metadata)
        current = result.get('wos_enrichment') or {}
        for field in merge_totals:
            merge_totals[field] = current.get(field, merge_totals[field])
        applied_records.update(record_key(record) for record in records)

    async def checkpoint(record, report):
        saved = {**report, 'records': list(report['records']), 'status': 'partial',
                 'reason': 'interrupted_checkpoint', 'complete': False}
        # Süreç burada kesilse bile doğrulanmış yayın diskte kalır. Profil
        # güncellemesi başarısızsa sonraki açılış bu kayıtları geri yükleyebilir.
        wos_enrichment.save(result['profile'], saved)
        await publish([record], saved)
        progress(report)

    try:
        # Tek tarayıcı işi: aynı anda açılan profiller WoS'a yük bindirmez.
        async with access_gate():
            async with AsyncExitStack() as stack:
                session = None
                # WoS tam bir yayın kaynağıdır; konferanslar da bu aşamada toplanır.
                # Çeyrek sorgusu bundan ayrı ve yalnız uygun dergi yayınları içindir.
                if (result.get('profile') or {}).get('name'):
                    report = wos_enrichment.cached(result['profile'])
                    if report is None or retry and report.get('status') != 'done':
                        state['phase'] = 'publications'
                        previous = wos_enrichment.cached(result['profile'], allow_stale=True) or {}
                        if previous.get('records'):
                            await publish(previous['records'], {**previous, 'complete': False})
                        progress({'checked': 0, 'candidates': 0, 'matched': 0, 'new': 0, 'rejected': 0})
                        session = await stack.enter_async_context(AsyncStealthySession(
                            headless=True, network_idle=False, timeout=45000, max_pages=1))
                        try:
                            async with wos_verification.time_budget(300):
                                report = await wos_publications.collect(result['profile'],
                                    result.get('publications') or [], session,
                                    on_record=checkpoint, on_progress=progress)
                        except wos_publications.PublicationProgressError as exc:
                            logger.exception('WoS yayın kontrol noktası kaydedilemedi')
                            state.update(status='error', message=str(exc))
                            return
                        except AccessUnavailable as exc:
                            report = {'status': 'blocked', 'records': [],
                                      'reason': getattr(exc, 'reason', 'access_unavailable'),
                                      'message': str(exc), 'access_detail': getattr(exc, 'access_detail', 'unavailable')}
                        except Exception as exc:
                            logger.exception('WoS yayınları toplanamadı')
                            report = {'status': 'error', 'records': [], 'reason': type(exc).__name__}
                        report['complete'] = True
                        wos_enrichment.save(result['profile'], report)
                    else:
                        report = {**report, 'complete': True}
                    records = report.get('records') or []
                    remaining = [record for record in records if record_key(record) not in applied_records]
                    # Canlı akışta uygulanmış yayınlar yeniden eklenmez; boş delta
                    # yalnız son raporun profil üzerindeki durumunu tamamlar.
                    await publish(remaining, report)
                    publication_meta = {k: v for k, v in report.items() if k != 'records'}
                    publication_meta.update(merge_totals, new=merge_totals['added'])
                    state['publications'] = publication_meta
                    if report.get('status') == 'blocked' or report.get('reason') == 'access_unavailable' or \
                            str(report.get('reason') or '').startswith('manual_'):
                        state.update(status='blocked', message=report.get('message') or 'WoS erişimi sağlanamadı.',
                                     reason=report.get('reason', 'access_unavailable'),
                                     access_detail=report.get('access_detail', 'unavailable'))
                        return
                    papers = sorted((p for p in result.get('publications', []) if eligible(p)),
                                    key=lambda p: not bool(known_urls(p)))
                    state.update(total=len(papers), checked=0, phase='quartiles')
                for p in papers:
                    entry = cached(p)
                    if entry is None or retry and entry.get('status') != 'ok':
                        try:
                            if session is None:
                                session = await stack.enter_async_context(AsyncStealthySession(
                                    headless=True, network_idle=False, timeout=45000, max_pages=1))
                            async with wos_verification.time_budget(90):
                                entry = await lookup(p, session)
                        except AccessUnavailable as exc:
                            entry = {'status': 'blocked', 'message': str(exc),
                                     'reason': getattr(exc, 'reason', 'access_unavailable'),
                                     'access_detail': getattr(exc, 'access_detail', 'unavailable')}
                            save(p, entry)
                            state.update(entry)
                            return
                        except Exception:
                            logger.exception('WoS kontrolü tamamlanamadı: %s', doi_key(p.get('doi')))
                            entry = {'status': 'error'}
                        save(p, entry)
                        await asyncio.sleep(0.5)
                    if entry.get('status') == 'blocked':
                        state.update(status='blocked',
                                     message=entry.get('message') or 'WoS erişimi sağlanamadı. Ağ/oturum değiştiyse tekrar deneyin.',
                                     reason=entry.get('reason', 'access_unavailable'),
                                     access_detail=entry.get('access_detail', 'unavailable'))
                        return
                    state['checked'] += 1
                    if entry.get('status') == 'error':
                        state['errors'] += 1
                state['status'] = 'done'
    except asyncio.CancelledError:
        state['status'] = 'cancelled'
        raise
    except Exception:
        logger.exception('WoS arka plan işi başarısız')
        state.update(status='error', message='WoS kontrolü tamamlanamadı. Tekrar deneyebilirsiniz.')
    finally:
        state['finished_at'] = time.time()
        TASKS.pop(jid, None)


def start(result: dict, retry: bool = False, on_publications=None) -> dict:
    from . import wos_enrichment

    jid = result['job_id']
    if jid not in TASKS:
        state = RUNS.get(jid, {})
        interrupted = wos_enrichment.is_checkpoint(state.get('publications')) and \
            wos_enrichment.is_checkpoint(wos_enrichment.cached(result.get('profile') or {}, allow_stale=True))
        if not retry and not interrupted and not needs_verification_retry(state) and \
                time.time() - state.get('finished_at', 0) < FAILURE_TTL:
            return snapshot(result)
        RUNS[jid] = {'status': 'running', 'checked': 0, 'errors': 0,
                     'manual_verification_version': MANUAL_VERIFICATION_VERSION,
                     'total': sum(eligible(p) for p in result.get('publications', []))}
        TASKS[jid] = asyncio.create_task(_run(result, retry, on_publications))
    return snapshot(result)


async def close():
    tasks = list(TASKS.values())
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
