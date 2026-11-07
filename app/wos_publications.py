"""WoS yayınlarını arayüzden toplar; kimlik kanıtı olmayan ad eşleşmelerini reddeder.

Scrapling oturumu çağıran tarafından sağlanır. Kayıtlar mevcut kaynak şemasını
kullanır; birleştirme, kalıcı kayıt ve profil önbelleği çağırana aittir.
"""
from __future__ import annotations

import asyncio
import inspect
import re
from contextvars import ContextVar
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from scrapling import Selector

from . import wos, wos_verification
from .sources import record
from .text import clean, doi_key, fold, title_key

BASE = 'https://www.webofscience.com'
SEARCH = BASE + '/wos/woscc/basic-search'
MAX_RECORDS = 80
BUDGET_SECONDS = 240
ORCID = re.compile(r'\b\d{4}-\d{4}-\d{4}-\d{3}[\dXx]\b')
RID = re.compile(r'\b[A-Z]{1,5}-\d{3,7}-\d{4}\b')
_VERIFICATION_SNAPSHOT = ContextVar('wos_verification_snapshot', default=None)


class PublicationProgressError(Exception):
    """Doğrulanmış kaydı yayımlama hatası ağ/ayrıştırma hatası sayılmaz."""


def _texts(sel, css: str) -> list[str]:
    return list(dict.fromkeys(clean(n.get_all_text(separator=' ', strip=True)) for n in sel.css(css)
                              if clean(n.get_all_text(separator=' ', strip=True))))


def _first(sel, css: str) -> str:
    values = _texts(sel, css)
    return values[0] if values else ''


def _full_name(value: str) -> str:
    parts = [p for p in fold(value).split() if p not in {'prof', 'dr', 'doc', 'assoc', 'phd'}]
    return ' '.join(sorted(parts)) if len(parts) >= 2 and all(len(p) > 1 for p in parts) else ''


def _compatible_name(value: str, name: str) -> bool:
    """Tam ad yoksa yalnız eski yayın eşleşmesini doğrulamak için soyad + baş harfi."""
    if _full_name(value) and _full_name(value) == _full_name(name):
        return True
    expected = fold(name).split()
    got = fold(value).split()
    return bool(len(expected) >= 2 and len(got) >= 2 and expected[-1] in got
                and any(p == expected[0][0] for p in got))


def _checked_page(html: str, url: str):
    parsed = urlparse(url)
    if parsed.hostname != 'www.webofscience.com':
        raise wos.AccessUnavailable('WoS giriş sayfasına yönlendirdi.')
    sel = Selector(html)
    text = clean(sel.get_all_text(separator=' ', ignore_tags=('script', 'style', 'noscript'))).lower()
    if 'verify you are human' in text:
        hcaptcha = bool(sel.css('iframe[src*="hcaptcha.com/"]'))
        error = wos.AccessUnavailable('WoS hCaptcha ile insan doğrulaması istiyor.' if hcaptcha
                                      else 'WoS bu ağda insan doğrulaması istiyor.')
        error.access_detail = 'hcaptcha' if hcaptcha else 'human_verification'
        raise error
    if any(s in text for s in ('sign in to continue', 'access denied', 'unusual traffic')):
        raise wos.AccessUnavailable('WoS erişimi doğrulanamadı.')
    return sel


def parse_record(html: str, url: str) -> dict | None:
    """Yalnız full-record alanlarını oku; yazar tablosunda boş ad hücresi önceki adı sürdürür."""
    source_url = wos.record_url(url)
    sel = _checked_page(html, url)
    if not source_url:
        return None
    title = _first(sel, '[data-ta^="FullRTa-fullRecordtitle-"]')
    if not title:
        return None
    authors = [s.strip(' ()') for s in _texts(sel, '[data-ta^="SumAuthTa-FrAuthStandard-author-"]')]
    if not authors:
        authors = _texts(sel, '[data-ta^="SumAuthTa-DisplayName-author-"]')
    identifiers = []
    for table in sel.css('table'):
        if not table.css('[data-ta="AidTa-ContribNameTitle"]'):
            continue
        last_name = ''
        for row in table.css('tr'):
            name = _first(row, '[data-ta^="AidTa-ContribName-"]')
            last_name = name or last_name
            if not last_name:
                continue
            ids = _texts(row, '[data-ta^="AidTa-ContribNameRid-"]')
            orcid_text = ' '.join(_texts(row, '.mat-column-orcid, [data-ta^="AidTa-ContribNameOrcid-"]'))
            rids = list(dict.fromkeys(r for text in ids for r in RID.findall(text)))
            orcids = list(dict.fromkeys(x.upper() for x in ORCID.findall(orcid_text)))
            if rids or orcids:
                identifiers.append({'name': last_name, 'researcher_ids': rids, 'orcids': orcids})
    affiliations = _texts(sel, '[data-ta^="FRAOrgTa-RepOrgEnhancedName"], [data-ta^="FRAOrgTa-OrgEnhancedName"], '
                               '[data-ta^="FRAOrgTa-RepAddressFull"], [data-ta^="FRAOrgTa-AddressFull"]')
    # Liste tüm yazarların kurumlarını içerebilir; yeni kayıt kabulünde tam adla birlikte kullanılır.
    indexes = _texts(sel, '[data-ta^="FullRRPTa-edition"]')
    doi = doi_key(_first(sel, '[data-ta="FullRTa-DOI"]'))
    year_text = _first(sel, '[data-ta="FullRTa-pubdate"]')
    year = re.search(r'\b(?:19|20)\d{2}\b', year_text)
    doc_types = _texts(sel, '[data-ta^="FullRTa-doctype-"]')
    types = ' '.join(doc_types).lower()
    kind = 'conference-paper' if 'proceeding' in types else 'review' if 'review' in types else 'article' if 'article' in types else types
    venue = _first(sel, '.summary-source-title, a[cdxanalyticscategory="wos-recordCard_Journal_Info"]')
    abstract = _first(sel, '[data-ta="FullRTa-abstract-basic"]')
    issn = []
    for node in sel.css('[data-ta]'):
        if 'issn' in node.attrib.get('data-ta', '').lower() and 'label' not in node.attrib.get('data-ta', '').lower():
            issn.extend(re.findall(r'\b\d{4}-\d{3}[\dXx]\b', node.get_all_text()))
    citation_text = _first(sel, '[data-ta="FullRRPTa-citationsCount"]')
    if not citation_text:
        for node in sel.css('[data-ta^="FullRRPTa-citationsLabel"]'):
            citation_text = clean(node.parent.get_all_text(separator=' ')); break
    citation = re.search(r'\b[\d,]+\b', citation_text)
    accession = source_url.rsplit('/', 1)[-1]
    value = record('wos', source_id=accession, title=title, year=year[0] if year else None, doi=doi,
                   venue=venue, authors=authors, abstract=abstract, url=source_url,
                   citations=int(citation[0].replace(',', '')) if citation else None, type=kind,
                   labels=indexes, issn=list(dict.fromkeys(issn)))
    value['wos'] = {'url': source_url, 'accession': accession, 'indexes': indexes,
                    'author_identifiers': identifiers, 'affiliations': affiliations,
                    'document_types': doc_types, 'checked_at': datetime.now(timezone.utc).isoformat()}
    if doi:
        jcr = wos.parse_record(html, source_url, value)
        if jcr:
            value['jcr'] = jcr
    return value


def existing_match(candidate: dict, existing: list[dict], name: str) -> dict | None:
    if not any(_compatible_name(author, name) for author in candidate.get('authors', [])):
        return None
    doi = doi_key(candidate.get('doi'))
    matches = []
    candidate_title = title_key(candidate.get('title', ''))
    for paper in existing:
        other_doi = doi_key(paper.get('doi'))
        if doi and other_doi:
            if doi == other_doi:
                matches.append(paper)
            continue
        titles = {title_key(paper.get('title', '')),
                  *(title_key(v.get('title', '')) for v in paper.get('variants') or [])}
        if candidate.get('year') and candidate.get('year') == paper.get('year') and \
                candidate_title and candidate_title in titles and \
                any(_compatible_name(author, name) for author in paper.get('authors', [])):
            matches.append(paper)
    return matches[0] if len(matches) == 1 else None


def _institution_tokens(value: str) -> set[str]:
    generic = {'university', 'universitesi', 'univ', 'technical', 'teknik', 'teknoloji', 'technology',
               'faculty', 'fakultesi', 'department', 'bolumu', 'institute', 'of', 'the', 'and'}
    return {x for x in fold(value).split() if len(x) >= 4 and x not in generic}


class Identity:
    def __init__(self, profile: dict, existing: list[dict]):
        self.name = profile.get('name') or profile.get('query_name') or ''
        self.full_name = _full_name(self.name)
        self.orcids = {x.upper() for x in ORCID.findall(str(profile.get('orcid') or '') + ' ' +
                                                       str((profile.get('links') or {}).get('orcid') or ''))}
        self.rids = set(RID.findall(str(profile.get('researcher_id') or '') + ' ' +
                                   str((profile.get('links') or {}).get('wos') or '')))
        self.existing = existing
        self.affiliations = [profile.get('institution') or '']
        for row in (profile.get('yok') or {}).get('career') or []:
            self.affiliations.append(row.get('place') or '')
        self.coauthors = set()
        for p in existing:
            if self.trusted(p) and any(_compatible_name(a, self.name) for a in p.get('authors', [])):
                self.coauthors.update(n for a in p.get('authors', []) if (n := _full_name(a)) and n != self.full_name)

    @staticmethod
    def trusted(p: dict) -> bool:
        sources = set(p.get('sources') or [p.get('source')]) - {None, ''}
        return bool(sources & {'yok', 'orcid', 'wos'} or len(sources) >= 2)

    def decide(self, p: dict) -> tuple[bool, str, dict | None]:
        match = existing_match(p, self.existing, self.name)
        rows = (p.get('wos') or {}).get('author_identifiers', [])
        # Kimlik yalnız hedef yazar satırından alınır; başka yazarın ORCID'si yeterli değildir.
        conflicting_orcid = False
        for row in rows:
            if not _compatible_name(row.get('name', ''), self.name):
                continue
            if self.orcids.intersection(row.get('orcids', [])):
                return True, 'orcid', match
            if self.rids.intersection(row.get('researcher_ids', [])):
                return True, 'researcher_id', match
            if self.orcids and row.get('orcids'):
                conflicting_orcid = True
        if match:
            return True, 'existing_doi' if doi_key(p.get('doi')) and doi_key(match.get('doi')) else 'existing_title_year_author', match
        if conflicting_orcid:
            return False, 'orcid_conflict', None
        if not self.full_name or not any(_full_name(a) == self.full_name for a in p.get('authors', [])):
            return False, 'author_not_verified', None
        if self.coauthors.intersection(_full_name(a) for a in p.get('authors', [])):
            return True, 'full_name_and_coauthor', None
        for affiliation in (p.get('wos') or {}).get('affiliations', []):
            observed = _institution_tokens(affiliation)
            if any((tokens := _institution_tokens(known)) and tokens <= observed for known in self.affiliations):
                return True, 'full_name_and_affiliation', None
        return False, 'author_not_verified', None

    def learn(self, p: dict, reason: str, matched: dict | None):
        # Tek kaynaklı mevcut kayıtlar kimlik genişletmek için kullanılmaz.
        if reason not in ('orcid', 'researcher_id') and not (matched and self.trusted(matched)):
            return
        for row in (p.get('wos') or {}).get('author_identifiers', []):
            if _full_name(row.get('name', '')) == self.full_name:
                self.rids.update(row.get('researcher_ids', []))
                self.orcids.update(row.get('orcids', []))
        self.affiliations.extend((p.get('wos') or {}).get('affiliations', []))
        self.coauthors.update(n for a in p.get('authors', []) if (n := _full_name(a)) and n != self.full_name)


def result_links(html: str, url: str) -> tuple[list[str], bool]:
    sel = _checked_page(html, url)
    links = list(dict.fromkeys(v for node in sel.css('a[data-ta="summary-record-title-link"][href]')
                              if (v := wos.record_url(urljoin(BASE, node.attrib['href'])))))
    next_buttons = sel.css('button[data-ta="next-page-button"]')
    more = bool(next_buttons and 'disabled' not in next_buttons[0].attrib)
    return links, more


def result_count(html: str) -> int | None:
    value = _first(Selector(html), 'h1.search-info-title .brand-blue, [data-ta="parent-summary-link"] .tab-results-count')
    digits = re.sub(r'[^0-9]', '', value)
    return int(digits) if digits else None


async def _dismiss_cookies(page):
    # Bazı oturumlarda tercih merkezi kendiliğinden açılıyor. Yalnız gerekli
    # çerezlerle devam et; görünmeyen düğmeler için uzun bekleme başlatma.
    for css in ('#onetrust-reject-all-handler', '.save-preference-btn-handler',
                '.onetrust-close-btn-handler.banner-close-button'):
        button = page.locator(css).first
        if await button.count() and await button.is_visible():
            await button.click(timeout=3000)


async def _click(page, locator, *, navigation: bool = False):
    try:
        await locator.click(timeout=3000)
    except Exception:
        if navigation and await _verify(page):
            # Tıklama sorguyu göndermiş olabilir; doğrulama sonrası sonucu bekle.
            return False
        # Çerez katmanı ilk DOM yüklendikten sonra da gelebiliyor.
        await _dismiss_cookies(page)
        await locator.click(timeout=5000)
    return True


async def _verify(page) -> bool:
    """İnsan doğrulamasını canlı WoS sekmesinde tamamla; nedenini kaybetme."""
    try:
        handled = await wos_verification.handle(page)
        snapshot = _VERIFICATION_SNAPSHOT.get()
        if handled and snapshot is not None:
            snapshot['manual_verified'] = True
        return handled
    except wos_verification.VerificationUnavailable as exc:
        error = wos.AccessUnavailable(str(exc))
        error.reason = f'manual_{exc.reason}'
        error.access_detail = error.reason
        raise error from exc


async def _wait_page(page, expression: str, *, timeout: float, arg=None):
    """SPA beklerken beliren doğrulama kapısı aynı sekmede çözülebilsin."""
    async with wos_verification.time_budget(timeout / 1000):
        while True:
            await _verify(page)
            try:
                await page.wait_for_function(expression, arg=arg, timeout=500)
            except Exception as exc:
                if type(exc).__name__ != 'TimeoutError':
                    raise
            else:
                # İçerik DOM'da kalsa da önünde doğrulama katmanı bulunabilir.
                if not await _verify(page):
                    return


async def _wait_record(page):
    await _wait_page(page, """() =>
      document.querySelector('[data-ta^="FullRTa-fullRecordtitle-"]') ||
      /access denied|sign in to continue/i.test(document.body.innerText)
    """, timeout=20000)


async def _fetch(session, url: str, action=None, *, recover=None, settle_ms: int = 0) -> tuple[str, str]:
    """Scrapling gezinme sonrası DOM'u callback'te al; ilk yanıt HTML'i SPA'da eskidir."""
    snapshot = {}

    async def capture(page):
        token = _VERIFICATION_SNAPSHOT.set(snapshot)
        try:
            await _verify(page)
            if action:
                try:
                    await action(page)
                except wos.AccessUnavailable:
                    raise
                except Exception:
                    if not await _verify(page):
                        raise
                    # Gönderilmiş aramayı yeniden göndermeden kaldığı aşamayı bekle.
                    if recover:
                        await recover(page)
                    else:
                        raise
            else:
                await _wait_record(page)
            if settle_ms:
                await page.wait_for_timeout(settle_ms)
            if await _verify(page):
                if action and recover:
                    await recover(page)
                elif not action:
                    await _wait_record(page)
            snapshot['html'] = await page.content()
            snapshot['url'] = page.url
            if snapshot.get('manual_verified'):
                snapshot['wos_content'] = await page.evaluate("""() =>
                  [...document.querySelectorAll('input[data-ta="search-criteria-input"], a[data-ta="summary-record-title-link"], [data-ta^="FullRTa-fullRecordtitle-"]')]
                    .some(el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden')
                """)
        except Exception as exc:
            # Scrapling callback hatalarını loglayıp yutuyor; çağırana geri taşı.
            snapshot['error'] = exc
            try:
                snapshot['html'] = await page.content()
                snapshot['url'] = page.url
            except Exception:
                pass
        finally:
            _VERIFICATION_SNAPSHOT.reset(token)

    # Scrapling çözücüsü page_action öncesinde çalışır; Cloudflare engelini
    # arama formu/sonuçları okunmadan önce ele al. hCaptcha ayrı değerlendirilir.
    try:
        response = await session.fetch(url, network_idle=False, timeout=60000, wait=250,
                                       solve_cloudflare=True, page_action=capture)
    except Exception:
        if snapshot.get('error'):
            raise snapshot['error']
        raise
    if snapshot.get('error'):
        raise snapshot['error']
    html = snapshot.get('html') or response.html_content or ''
    final_url = snapshot.get('url') or str(response.url)
    # İlk kapı 403 döndürmüş olabilir; SPA doğrulamayı gezinmeden tamamlayabilir.
    # Yalnız gerçekten tamamlanmış handoff + görünür WoS içeriği bunu geçersiz kılar.
    recovered_forbidden = response.status == 403 and snapshot.get('manual_verified') and snapshot.get('wos_content')
    if response.status in (401, 403, 429) and not recovered_forbidden:
        raise wos.AccessUnavailable(f'WoS HTTP {response.status}')
    if response.status != 200 and not recovered_forbidden:
        raise RuntimeError(f'WoS HTTP {response.status}')
    _checked_page(html, final_url)
    return html, final_url


async def _wait_results(page):
    await _wait_page(page, """() =>
      document.querySelector('a[data-ta="summary-record-title-link"]') ||
      /no results found|found no results|no records found|did not return any results|no matching records|access denied|sign in to continue/i.test(document.body.innerText)
    """, timeout=30000)


async def _expand_results(page, limit: int = 50):
    """WoS ilk ekranda yalnız üç başlığı oluşturur; kalan kartlar kaydırılınca yüklenir."""
    for _ in range(50):
        if await _verify(page):
            await _wait_results(page)
        count = await page.locator('a[data-ta="summary-record-title-link"]').count()
        if count >= limit:
            return
        placeholders = page.locator('app-record.loading-cover')
        if not await placeholders.count():
            return
        await placeholders.first.scroll_into_view_if_needed(timeout=5000)
        await _wait_page(page, """previous =>
          document.querySelectorAll('a[data-ta="summary-record-title-link"]').length > previous ||
          !document.querySelector('app-record.loading-cover')
        """, arg=count, timeout=10000)


async def _search(session, field: str, query: str, max_results: int = 50) -> tuple[str, str]:
    submitted = False
    replayed = False

    async def finish(page, *, verified: bool = False):
        nonlocal replayed
        if verified and not replayed:
            # Yalnız kapı tıklamadan önce açılmış ve aynı doldurulmuş form kalmışsa
            # tek kez gönder. Sonuç/başlamış yükleme varsa sorguyu tekrar çalıştırma.
            waiting_form = await page.evaluate("""query => {
              const input = document.querySelector('input[data-ta="search-criteria-input"]');
              const button = document.querySelector('button[data-ta="run-search"]');
              return location.pathname.replace(/\\/$/, '') === '/wos/woscc/basic-search' &&
                input && input.getClientRects().length && input.value === query &&
                button && button.getClientRects().length && !button.disabled &&
                !document.querySelector('a[data-ta="summary-record-title-link"], app-record.loading-cover');
            }""", query)
            if waiting_form:
                replayed = True
                await _click(page, page.locator('button[data-ta="run-search"]'), navigation=True)
        await _wait_results(page)
        await _expand_results(page, max_results)

    async def search(page):
        nonlocal submitted
        await _wait_page(page, """() =>
          !!document.querySelector('input[data-ta="search-criteria-input"]')
        """, timeout=20000)
        await _dismiss_cookies(page)
        for attempt in range(2):
            try:
                dropdown = page.locator('button[aria-label^="Select search field"]').first
                if await dropdown.get_attribute('aria-expanded') != 'true':
                    await _click(page, dropdown)
                await page.get_by_role('option', name=field, exact=True).click(timeout=3000)
                break
            except Exception:
                await _dismiss_cookies(page)
                if attempt:
                    raise
        await page.locator('input[data-ta="search-criteria-input"]').first.fill(query)
        # Tıklama olayından sonra kapı açılırsa aynı sorguyu iki kez çalıştırma.
        submitted = True
        clicked = await _click(page, page.locator('button[data-ta="run-search"]'), navigation=True)
        await finish(page, verified=clicked is False)

    async def recover(page):
        if not submitted:
            await search(page)
        else:
            await finish(page, verified=True)

    return await _fetch(session, SEARCH, search, recover=recover)


async def _next_page(session, url: str, max_results: int = 50) -> tuple[str, str]:
    submitted = False
    previous = None

    async def finish(page):
        await _wait_page(page, """previous => {
          const first = document.querySelector('a[data-ta="summary-record-title-link"]');
          return first && first.getAttribute('href') !== previous;
        }""", arg=previous, timeout=30000)
        await _expand_results(page, max_results)

    async def next_page(page):
        nonlocal submitted, previous
        await _wait_results(page)
        await _dismiss_cookies(page)
        first = page.locator('a[data-ta="summary-record-title-link"]').first
        previous = await first.get_attribute('href')
        await _verify(page)
        submitted = True
        await _click(page, page.locator('button[data-ta="next-page-button"]').first, navigation=True)
        await finish(page)

    async def recover(page):
        if submitted:
            await finish(page)
        else:
            await next_page(page)

    return await _fetch(session, url, next_page, recover=recover)


async def collect(profile: dict, existing: list[dict], session, log=None, *, on_record=None, on_progress=None) -> dict:
    """En çok 80 kayıt/240 çalışma saniyesi; insan doğrulaması bekleme süresi hariç.

    Kısmi sonuçlar da doğrulanmış kayıtları içerir; bu fonksiyon dosya yazmaz.
    Her kabul edilen kayıtta kimlik kanıtının türü ``wos.identity_reason`` içindedir.
    """
    identity = Identity(profile, existing)
    report = {'status': 'done', 'records': [], 'matched': 0, 'new': 0, 'rejected': 0, 'reused': 0,
              'checked': 0, 'candidates': 0, 'truncated': False, 'queries': [], 'errors': []}
    visited = set()
    candidates = set()
    for p in existing:
        meta = p.get('wos') or {}
        url = wos.record_url(meta.get('url') or '')
        try:
            at = datetime.fromisoformat(meta.get('checked_at') or '')
            age = (datetime.now(timezone.utc) - at).total_seconds()
        except (ValueError, TypeError):
            continue
        if url and 0 <= age < 86400 and meta.get('identity_reason') and \
                any(_compatible_name(a, identity.name) for a in p.get('authors') or []):
            visited.add(url)
            identity.learn(p, meta['identity_reason'], p)
    report['reused'] = len(visited)

    async def notify(callback, *args):
        if callback:
            try:
                value = callback(*args)
                if inspect.isawaitable(value):
                    await value
            except Exception as exc:
                raise PublicationProgressError('WoS yayın ilerlemesi kaydedilemedi.') from exc

    async def emit(message):
        if log:
            value = log(message)
            if inspect.isawaitable(value):
                await value
        await notify(on_progress, report)

    async def read(url):
        if url in visited:
            return
        if report['checked'] >= MAX_RECORDS:
            report.update(status='partial', truncated=True, reason='record_limit')
            return
        visited.add(url)
        report['checked'] += 1
        await notify(on_progress, report)
        html, final_url = await _fetch(session, url)
        p = parse_record(html, final_url)
        if not p:
            report['rejected'] += 1
            await notify(on_progress, report)
            return
        accepted, reason, matched = identity.decide(p)
        if not accepted:
            report['rejected'] += 1
            await notify(on_progress, report)
            return
        p['wos']['identity_reason'] = reason
        identity.learn(p, reason, matched)
        report['records'].append(p)
        report['matched' if matched else 'new'] += 1
        # Kimlik kanıtı olmayan hiçbir aday kalıcı profile gönderilmez.
        await notify(on_record, p, report)
        await notify(on_progress, report)

    async def run():
        # Önce kaynaklı mevcut kayıtlar: hedef yazarın RID'sini aynı DOI veya
        # DOI'siz başlık+yıl+yazar eşleşmesinden öğrenmek aramayı daraltır.
        hints = []
        for p in sorted(existing, key=lambda p: not Identity.trusted(p)):
            values = [(p.get('wos') or {}).get('url'), (p.get('jcr') or {}).get('url'), *wos.known_urls(p)]
            hints.extend(u for v in values if (u := wos.record_url(v or '')) and u not in hints)
        for url in hints[:4]:
            try:
                await read(url)
            except (wos.AccessUnavailable, PublicationProgressError):
                raise
            except Exception as exc:
                report['errors'].append(type(exc).__name__)

        identifier_query = ' OR '.join(sorted(identity.orcids) + sorted(identity.rids))
        queries = [('Author Identifiers', identifier_query)] if identifier_query else []
        name = fold(identity.name).split()
        if len(name) >= 2:
            queries.append(('Author', f'{name[-1]} {name[0][0]}*'))
        if not queries:
            report.update(status='error', reason='profile_identity_missing')
            return
        for field, query in queries:
            result_pages = set()
            query_meta = {'field': field, 'query': query, 'total': None, 'discovered': 0}
            report['queries'].append(query_meta)
            query_candidates = set()
            await emit(f'WoS: {field} alanında yayınlar aranıyor.')
            try:
                html, page_url = await _search(session, field, query)
                query_meta['total'] = result_count(html)
                while True:
                    links, more = result_links(html, page_url)
                    signature = tuple(links)
                    if signature in result_pages:
                        if more:
                            report.update(status='partial', truncated=True, reason='pagination_repeated')
                        break
                    result_pages.add(signature)
                    candidates.update(links)
                    query_candidates.update(links)
                    query_meta['discovered'] = len(query_candidates)
                    report['candidates'] = len(candidates)
                    for url in links:
                        try:
                            await read(url)
                        except (wos.AccessUnavailable, PublicationProgressError):
                            raise
                        except Exception as exc:
                            report['errors'].append(type(exc).__name__)
                        if report.get('reason') == 'record_limit':
                            return
                    if not more:
                        if query_meta['total'] is not None and len(query_candidates) < query_meta['total']:
                            report.update(status='partial', truncated=True, reason='results_not_fully_loaded')
                        break
                    if report['checked'] >= MAX_RECORDS:
                        report.update(status='partial', truncated=True, reason='record_limit')
                        return
                    html, page_url = await _next_page(session, page_url)
            except (wos.AccessUnavailable, PublicationProgressError):
                raise
            except Exception as exc:
                report['errors'].append(type(exc).__name__)
                continue
        if report['errors']:
            report.update(status='partial' if report['records'] else 'error', reason='collection_incomplete')

    try:
        async with wos_verification.time_budget(BUDGET_SECONDS):
            await run()
    except asyncio.TimeoutError:
        report.update(status='partial', truncated=True, reason='time_budget')
    except wos.AccessUnavailable as exc:
        report.update(status='partial' if report['records'] else 'blocked', reason=getattr(exc, 'reason', 'access_unavailable'),
                      message=str(exc), access_detail=getattr(exc, 'access_detail', 'unavailable'))
    except PublicationProgressError:
        raise
    except Exception as exc:
        report['errors'].append(type(exc).__name__)
        report.update(status='partial' if report['records'] else 'error', reason='collection_failed')
    await emit(f"WoS: {len(report['records'])} yayın doğrulandı ({report['new']} yeni, {report['matched']} mevcut).")
    return report


async def collect_topic(query: str, session, *, limit: int = 20, budget: float = 90) -> dict:
    """Konu sonuçlarının ilk sınırlı bölümünü gerçek full-record sayfalarından oku.

    Bu sonuçlar bir kişiye atfedilmez. Profil toplayıcısının kimlik doğrulaması
    değişmez; konu keşfi kendi kapsamı ve kaynak sayfalarıyla döner.
    """
    query = clean(query)[:200]
    limit = max(1, min(int(limit), 20))
    report = {'status': 'done', 'records': [], 'query': query, 'field': 'Topic',
              'scope': 'first_results', 'limit': limit, 'total': None, 'checked': 0,
              'candidates': 0, 'rejected': 0, 'truncated': False, 'errors': []}
    if not query:
        report.update(status='error', reason='empty_query')
        return report
    visited, pages = set(), set()

    async def run():
        html, page_url = await _search(session, 'Topic', query, max_results=limit)
        report['total'] = result_count(html)
        while True:
            links, more = result_links(html, page_url)
            signature = tuple(links)
            if signature in pages:
                report.update(status='partial', truncated=True, reason='pagination_repeated')
                return
            pages.add(signature)
            for url in links:
                if url in visited:
                    continue
                if report['checked'] >= limit:
                    report.update(status='partial', truncated=True, reason='record_limit')
                    return
                visited.add(url)
                report['candidates'] = len(visited)
                report['checked'] += 1
                try:
                    record_html, final_url = await _fetch(session, url)
                    p = parse_record(record_html, final_url)
                    if p:
                        p['wos']['discovery'] = {'field': 'Topic', 'query': query}
                        report['records'].append(p)
                    else:
                        report['rejected'] += 1
                except wos.AccessUnavailable:
                    raise
                except Exception as exc:
                    report['errors'].append(type(exc).__name__)
            total = report['total']
            if report['checked'] >= limit and (more or total is None or report['checked'] < total):
                report.update(status='partial', truncated=True, reason='record_limit')
                return
            if not more:
                if total is not None and len(visited) < total:
                    report.update(status='partial', truncated=True, reason='results_not_fully_loaded')
                return
            html, page_url = await _next_page(session, page_url, max_results=limit - report['checked'])

    try:
        async with wos_verification.time_budget(min(float(budget), 90)):
            await run()
        if report['errors']:
            report.update(status='partial' if report['records'] else 'error', reason='collection_incomplete')
    except asyncio.TimeoutError:
        report.update(status='partial', truncated=True, reason='time_budget')
    except wos.AccessUnavailable as exc:
        report.update(status='partial' if report['records'] else 'blocked', reason=getattr(exc, 'reason', 'access_unavailable'),
                      message=str(exc), access_detail=getattr(exc, 'access_detail', 'unavailable'))
    except Exception as exc:
        report['errors'].append(type(exc).__name__)
        report.update(status='partial' if report['records'] else 'error', reason='collection_failed')
    return report
