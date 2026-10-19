"""Kadro taraması: Scrapling Spider altyapısı + taramanın içinde REA tersine mühendisliği.

  * Scrapling Spider  — öncelikli kuyruk, URL tekilleştirme, robots.txt'ye uyum, eşzamanlı istek,
                        oturum yönetimi. Varsayılan oturum Chrome TLS taklidi yapan FetcherSession.
  * Duvar             — `is_blocked` bot duvarını tanır; `retry_blocked_request` isteği Scrapling'in
                        stealth tarayıcı oturumuna (Cloudflare çözücü açık) aktarır.
  * REA               — içeriği JavaScript ile gelen "ince" bir sayfaya rastlanırsa REA o sayfayı gerçek
                        tarayıcıda açar; render edilmiş DOM'da kişi aranır, gizli JSON yanıtlarındaki aynı
                        site linkleri spider'a yeni hedef olarak verilir.
  * Sayfalama         — kadro listesindeki ?page=2 … linkleri en yüksek öncelikle kuyruğa girer.
"""
from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import urljoin, urlparse

from scrapling.spiders import Request, Spider

from . import navigator, rea
from .net import TR_HEADERS, augmented_bundle, parse, wall_reason
from .text import name_in_text

MAX_REA_IN_CRAWL = 3
URL_IN_JSON = re.compile(r"https?://[^\s\"'<>]+")


def _json_links(obj, base: str, root: str, out: set, depth: int = 0):
    """REA'nın yakaladığı JSON gövdelerindeki aynı siteye ait linkler (menü/kadro API'leri)."""
    from .discover import registrable

    if depth > 8 or len(out) > 200:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and re.search(r"url|link|href|slug|path", str(k), re.I) and v.startswith(("/", "http")):
                full = urljoin(base, v)
                if registrable(urlparse(full).hostname or "") == root:
                    out.add(full)
            else:
                _json_links(v, base, root, out, depth + 1)
    elif isinstance(obj, list):
        for v in obj[:500]:
            _json_links(v, base, root, out, depth + 1)
    elif isinstance(obj, str):
        for m in URL_IN_JSON.findall(obj):
            if registrable(urlparse(m).hostname or "") == root:
                out.add(m)


class StaffSpider(Spider):
    name = "akademik-kadro"
    robots_txt_obey = True
    concurrent_requests = 8
    max_blocked_retries = 1
    logging_level = logging.WARNING

    def __init__(self, seeds: list[tuple[str, float]], person: str, root: str, max_pages: int, max_depth: int,
                 events: asyncio.Queue):
        self.seeds = seeds
        self.person = person
        self.root = root
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.events = events
        self.pages = 0
        self.rea_used = 0
        self.done = False
        self.allowed_domains = {root}
        super().__init__()

    # ----------------------------------------------------------------- oturumlar
    def configure_sessions(self, manager) -> None:
        from scrapling.fetchers import AsyncStealthySession, FetcherSession

        bundle = augmented_bundle()
        manager.add("default", FetcherSession(impersonate="chrome", stealthy_headers=True, headers=TR_HEADERS,
                                              timeout=15, retries=1, follow_redirects=True,
                                              **({"verify": bundle} if bundle else {})), default=True)
        manager.add("stealth", AsyncStealthySession(headless=True, network_idle=True, solve_cloudflare=True,
                                                    timeout=45000, block_webrtc=True, locale="tr-TR",
                                                    extra_headers=TR_HEADERS), lazy=True)

    async def is_blocked(self, response) -> bool:
        return bool(wall_reason(response.status, response.html_content or ""))

    async def retry_blocked_request(self, request, response):
        self.events.put_nowait({"bot": f"Bot koruması ({wall_reason(response.status, response.html_content or '')}) → "
                                       f"istek Scrapling stealth oturumuna aktarıldı: {request.url[:80]}"})
        request.sid = "stealth"
        return request

    async def start_requests(self):
        for url, score in self.seeds:
            yield Request(url, priority=int(score * 10), meta={"depth": 1})

    # ---------------------------------------------------------------------- ayrıştırma
    async def parse(self, response):
        from .discover import _link_score, _links, _visible_text

        if self.done:
            return
        self.pages += 1
        depth = response.meta.get("depth", 1)
        sel = response
        html = response.html_content or ""
        text = _visible_text(sel)
        if self.pages % 8 == 0:
            self.events.put_nowait({"progress": self.pages})

        if name_in_text(self.person, text) and navigator.is_person_hit(sel, text, self.person, response.url):
            self.done = True
            yield {"found": response.url, "html": html, "via": "scrapling.spider"}
            return

        # İçerik JavaScript ile geliyorsa: REA taramanın içinde devreye girer
        if len(text) < 500 and len(sel.css("script")) >= 5 and self.rea_used < MAX_REA_IN_CRAWL and rea.available():
            self.rea_used += 1
            self.events.put_nowait({"rea": f"İçerik JavaScript ile yükleniyor → REA sayfayı gerçek tarayıcıda açıp "
                                           f"ağ trafiğini çözümlüyor: {response.url[:80]}"})
            cap = await rea.recon(response.url, settle_ms=2500)
            if cap.ok and cap.dom:
                rsel = parse(cap.dom, cap.final_url or response.url)
                rtext = _visible_text(rsel)
                if name_in_text(self.person, rtext) and navigator.is_person_hit(rsel, rtext, self.person, response.url):
                    self.done = True
                    yield {"found": cap.final_url or response.url, "html": cap.dom, "via": "rea.render"}
                    return
                hidden: set[str] = set()
                for tx in cap.json_endpoints:
                    _json_links(tx.json(), response.url, self.root, hidden)
                if hidden:
                    self.events.put_nowait({"rea": f"REA gizli JSON yanıtlarında {len(hidden)} site linki buldu → spider'a eklendi."})
                for u in list(hidden)[:60]:
                    yield Request(u, priority=40, meta={"depth": depth + 1})
                sel, text = rsel, rtext  # linkleri render edilmiş DOM'dan da çıkar

        if self.pages >= self.max_pages:
            self.done = True
            self.pause()
            return

        if navigator.is_staff_page(text):
            for purl in navigator.pagination_links(sel, response.url):
                yield Request(purl, priority=100, meta={"depth": depth})
        if depth < self.max_depth:
            for url, ltext in _links(sel, response.url):
                score = _link_score(url, ltext, self.person, self.root)
                if score >= 2:
                    yield Request(url, priority=int((score - depth) * 10), meta={"depth": depth + 1})


async def crawl(seeds: list[tuple[str, float]], person: str, root: str, max_pages: int, max_depth: int, log,
                stop: asyncio.Event | None = None):
    """Spider'ı akış modunda çalıştırır; kişi bulununca veya `stop` sinyalinde nazikçe durdurur.

    Not: Scrapling'in akışından `break` ile çıkılmaz (iç anyio görev grubu farklı görevde kapanır);
    `pause()` çağrılır ve akışın kendiliğinden bitmesi beklenir.
    """
    from .discover import _visible_text

    events: asyncio.Queue = asyncio.Queue()
    spider = StaffSpider(seeds, person, root, max_pages, max_depth, events)
    result = None

    def halt():
        spider.done = True
        try:
            spider.pause()
            spider.pause()  # ikinci çağrı: uçuştaki istekleri beklemeden durdur
        except RuntimeError:
            pass

    async def watch_stop():
        if stop is not None:
            await stop.wait()
            halt()

    async def drain():
        while not events.empty():
            ev = events.get_nowait()
            if "progress" in ev:
                await log("crawl", "running", f"Scrapling Spider: {ev['progress']} sayfa tarandı.")
            elif "bot" in ev:
                await log("crawl", "running", ev["bot"])
            elif "rea" in ev:
                await log("rea", "running", ev["rea"])

    watcher = asyncio.create_task(watch_stop())
    try:
        async for item in spider.stream():
            await drain()
            if item.get("found") and result is None:
                sel = parse(item["html"], item["found"])
                result = (sel, item["found"], item["html"], _visible_text(sel))
                halt()
    finally:
        watcher.cancel()
        await drain()
    if stop is not None and stop.is_set() and result is None:
        return None, spider.pages, spider.rea_used
    await log("crawl", "done" if result else "warning",
              f"Scrapling Spider {spider.pages} sayfada " + (f"kişiyi buldu: {result[1]}" if result else "kişiyi bulamadı.")
              + (f" (REA {spider.rea_used} kez devreye girdi)" if spider.rea_used else ""))
    return result, spider.pages, spider.rea_used
