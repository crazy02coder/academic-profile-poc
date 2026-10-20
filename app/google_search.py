"""Google araması: kalıcı Playwright oturumu, REA DOM yakalama, Scrapling ayrıştırma.

AI Overview her sorguda çıkmaz. Metni yalnızca doğrulanmamış bir ipucudur;
kanıt için atıf bağlantılarındaki asıl sayfalar kullanılır. CAPTCHA çözülmez.
"""
from __future__ import annotations

import asyncio
import os
import re
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from scrapling import Selector

from . import rea
from .text import clean, fold

_SESSION: dict = {"loop": None, "lock": None, "playwright": None, "browser": None,
                 "context": None, "endpoint": ""}
OVERVIEW_NAMES = {
    "ai overview", "ai overviews", "yapay zekaya genel bakis",
    "yapay zeka ile genel bakis", "yapay zeka ozeti", "yapay zeka bakisi",
    "yapay zeka ile olusturulmus genel bakis",
}
GOOGLE_HOST = re.compile(r"(^|\.)google\.(?:com|[a-z]{2}|com\.[a-z]{2}|co\.[a-z]{2})$")


class GoogleBlocked(RuntimeError):
    pass


def _external_url(href: str, base: str) -> str:
    try:
        url = urljoin(base, href)
        parsed = urlparse(url)
        if GOOGLE_HOST.search(parsed.hostname or "") and parsed.path == "/url":
            params = parse_qs(parsed.query)
            url = (params.get("q") or params.get("url") or [""])[0]
            parsed = urlparse(url)
    except (ValueError, TypeError):
        return ""
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or parsed.username or parsed.password:
        return ""
    if GOOGLE_HOST.search(host) or host.endswith((".gstatic.com", ".googleusercontent.com")):
        return ""
    return url


def _links(node, base: str, engine: str) -> list[dict]:
    rows = []
    for anchor in node.css("a[href]"):
        url = _external_url(anchor.attrib.get("href", ""), base)
        if url:
            rows.append({"url": url, "title": clean(anchor.get_all_text(separator=" "))[:180],
                         "engine": engine})
    return rows


def parse_results(html: str, url: str) -> dict:
    """Anlamsal başlıklar kullanılır; tüm sonuç sayfası Overview sayılmaz."""
    sel = Selector(html, url=url)
    result = {"overview": "", "overview_pending": False, "results": [], "status": "empty", "evidence_id": ""}
    host = urlparse(url).hostname or ""
    if host.startswith("consent.") or "/sorry/" in urlparse(url).path:
        raise GoogleBlocked("Google onay/bot kontrolü")
    visible = fold(clean(sel.get_all_text(separator=" ", ignore_tags=("script", "style", "noscript"))))
    if any(marker in visible for marker in (
            "our systems have detected unusual traffic", "sistemlerimiz bilgisayar aginizdan gelen",
            "before you continue to google")):
        raise GoogleBlocked("Google onay/bot kontrolü")

    # Numaralı/karma CSS sınıflarına bağlanmadan görünen Overview başlığını bul.
    candidates = list(sel.css('[data-attrid="AIOverview"], [data-attrid="SGE"], [data-aio]'))
    result["overview_pending"] = bool(candidates)
    for heading in sel.css('h1, h2, h3, [role="heading"], [aria-label]'):
        label = fold(clean(heading.attrib.get("aria-label") or heading.get_all_text(separator=" ")))
        if label not in OVERVIEW_NAMES:
            continue
        result["overview_pending"] = True
        node = heading.parent
        for _ in range(5):
            if node is None or node.tag in ("body", "html", "main") or node.attrib.get("id") in ("search", "rso", "main"):
                break
            text = clean(node.get_all_text(separator=" "))
            if len(text) > 12000:
                break
            if len(text) > len(label) + 40 and _links(node, url, "google_overview"):
                candidates.append(node)
                break
            node = node.parent
    for node in candidates:
        text = clean(node.get_all_text(separator=" ", ignore_tags=("script", "style", "noscript")))
        links = _links(node, url, "google_overview")
        if 40 <= len(text) <= 12000 and links:
            result.update(overview=text[:6000], overview_pending=False, results=links, status="overview")
            break

    # Overview yoksa normal arama sonuçları; menü/reklam/altbilgi linklerini alma.
    for heading in sel.css("h3"):
        anchors = heading.xpath("ancestor::a[@href][1]")
        if not anchors:
            continue
        target = _external_url(anchors[0].attrib["href"], url)
        if target:
            result["results"].append({"url": target, "title": clean(heading.get_all_text(separator=" "))[:180],
                                      "engine": "google"})
    seen, unique = set(), []
    for row in result["results"]:
        if row["url"] not in seen:
            seen.add(row["url"])
            unique.append(row)
    result["results"] = unique
    if result["results"] and result["status"] == "empty":
        result["status"] = "organic"
    return result


async def _context():
    from playwright.async_api import async_playwright

    loop = asyncio.get_running_loop()
    if _SESSION["loop"] is not loop:
        _SESSION.update(loop=loop, lock=asyncio.Lock(), playwright=None, browser=None, context=None,
                        endpoint="")
    async with _SESSION["lock"]:
        if _SESSION["browser"] is not None and _SESSION["browser"].is_connected():
            return _SESSION["context"]
        await close()
        playwright = await async_playwright().start()
        _SESSION["playwright"] = playwright
        port = rea._free_port()
        try:
            browser = await playwright.chromium.launch(
                headless=True, timeout=5000,
                args=[f"--remote-debugging-port={port}", "--remote-debugging-address=127.0.0.1"])
            _SESSION["browser"] = browser
            context = await browser.new_context(locale="tr-TR")
            async def light_resources(route):
                if route.request.resource_type in ("image", "font", "media"):
                    await route.abort()
                else:
                    await route.continue_()
            await context.route("**/*", light_resources)
            _SESSION.update(context=context, endpoint=f"http://127.0.0.1:{port}")
            return context
        except BaseException:
            await close()
            raise


async def close():
    for key, method in (("context", "close"), ("browser", "close"), ("playwright", "stop")):
        obj = _SESSION.get(key)
        _SESSION[key] = None
        if obj is not None:
            try:
                await getattr(obj, method)()
            except Exception:
                pass


async def search(query: str, log=None) -> dict:
    """REA aramayı açıp dinamik DOM'u alır; Scrapling Overview ve atıfları çıkarır."""
    from playwright.async_api import TimeoutError as PlaywrightTimeout

    context = await _context()
    page = await context.new_page()
    try:
        url = "https://www.google.com/search?" + urlencode({"q": query, "hl": "tr"})
        rea_enabled = os.getenv("GOOGLE_REA_ENABLED", "1").lower() not in ("0", "false", "off")
        cap = None
        if rea_enabled and rea.available():
            if log:
                await log("REA: Google araması açılıyor, AI Overview ve kaynak bağlantıları yakalanıyor.")
            cdp = await context.new_cdp_session(page)
            try:
                target = (await cdp.send("Target.getTargetInfo"))["targetInfo"]["targetId"]
            finally:
                await cdp.detach()
            # REA boş sekmeyi doğrudan sorguya götürür. Önce Playwright ile aynı
            # aramayı açıp REA ile ikinci kez yükleme yapılmaz.
            cap = await rea.capture_connected(_SESSION["endpoint"], target, url, timeout=7, wait_ms=1100)
            if log:
                await log(f"REA Google: {'DOM alındı' if cap.dom else cap.error or 'sonuç yok'}"
                          + (f" · kanıt {cap.evidence_id[:16]}" if cap.evidence_id else ""))
        # CLI yoksa ya da hedefe ulaşamadan hata verdiyse aynı sekmede normal açılış.
        if not (cap and cap.dom) and page.url == "about:blank":
            response = await page.goto(url, wait_until="domcontentloaded", timeout=5000)
            if response is not None and response.status >= 400:
                raise GoogleBlocked(f"Google HTTP {response.status}")
            try:
                await page.locator('h3, [data-aio], [data-attrid="AIOverview"]').first.wait_for(
                    state="visible", timeout=1000)
            except PlaywrightTimeout:
                pass
        result = parse_results(cap.dom if cap and cap.dom else await page.content(),
                               (cap.final_url if cap and cap.final_url else page.url))
        result["rea_used"] = cap is not None
        result["evidence_id"] = cap.evidence_id if cap else ""
        if log:
            await log("Google AI Overview kaynakları bulundu; asıl sayfalarda doğrulanacak."
                      if result["overview"] else "Google AI Overview yok; normal sonuç bağlantıları kullanılacak.")
        return result
    finally:
        await page.close()
