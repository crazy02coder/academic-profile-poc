"""Scrapling tabanlı erişim katmanı.

Strateji merdiveni (her basamak bir öncekinin duvarına takıldığında devreye girer):
  1. Scrapling Fetcher  — curl_cffi ile Chrome TLS/HTTP2 parmak izi taklidi.
  2. Eksik TLS zinciri  — AIA (caIssuers) ile ara sertifika indirilir, doğrulama
                          KAPATILMADAN yeniden denenir.
  3. Scrapling StealthyFetcher — Patchright tabanlı gizli tarayıcı (418/403/429,
                          JS challenge, Cloudflare Turnstile için).
"""
from __future__ import annotations

import asyncio
import logging
import re
import ssl
import tempfile
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import certifi

from .config import CACHE_DIR

import scrapling.fetchers  # noqa: E402,F401 - logger'ı kurması için önce import edilir

logging.getLogger("scrapling").setLevel(logging.CRITICAL)

TR_HEADERS = {"Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.6,en;q=0.5"}

WALL_STATUSES = {401, 403, 405, 418, 429, 503}
WALL_MARKERS = re.compile(
    r"cf-browser-verification|challenge-platform|cf_chl_|just a moment\.\.\.|"
    r"attention required|g-recaptcha|hcaptcha|unusual traffic|sorry/index|"
    r"captcha|access denied|request blocked|bot detected|ddos-guard",
    re.I,
)


@dataclass
class Page:
    url: str
    status: int
    html: str
    via: str  # hangi basamakla alındı
    selector: object = None  # scrapling Selector/Response
    notes: list[str] = field(default_factory=list)


def wall_reason(status: int, html: str) -> str | None:
    """Sayfanın bir bot duvarı / engel olup olmadığını sezgisel olarak belirler."""
    if status in WALL_STATUSES:
        return f"HTTP {status}"
    head = html[:20000]
    if len(html) < 4000 and WALL_MARKERS.search(head):
        return "challenge sayfası"
    if re.search(r"<title>\s*(just a moment|attention required|access denied)", head, re.I):
        return "challenge sayfası"
    return None


SOFT_404 = re.compile(r"(?i)(aradığınız sayfa bulunamadı|sayfa bulunamadı|page not found|404 not found|"
                      r"the page you (?:are looking for|requested) (?:could not be found|does not exist)|"
                      r"sayfa mevcut değil|böyle bir sayfa yok)")


def soft_404(html: str) -> bool:
    """Genel yumuşak 404 tespiti: başlıkta ya da kısa gövdenin başında 'bulunamadı' ifadesi."""
    head = re.sub(r"<[^>]+>", " ", html[:200000])
    title = re.search(r"(?is)<title>(.*?)</title>", html[:20000])
    if title and SOFT_404.search(title.group(1)):
        return True
    text = re.sub(r"\s+", " ", head)
    return bool(SOFT_404.search(text)) and len(text) < 40000 and text.count(" ") < 4000


# --------------------------------------------------------------------------- TLS
_bundle_cache: dict[str, str] = {}
_GLOBAL_BUNDLE = CACHE_DIR / "ca-augmented.pem"  # certifi + keşfedilen tüm ara sertifikalar


def _aia_chain(host: str, port: int = 443, depth: int = 3) -> list[str]:
    """Sunucunun göndermediği ara sertifikaları AIA caIssuers üzerinden indirir.

    Yalnızca *eksik halkayı tamamlamak* için kullanılır; güven kararı yine
    certifi kök sertifikalarıyla curl tarafından verilir.
    """
    pem = ssl.get_server_certificate((host, port), timeout=10)
    chain: list[str] = []
    current = pem
    for _ in range(depth):
        with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as fh:
            fh.write(current)
            path = fh.name
        try:
            decoded = ssl._ssl._test_decode_cert(path)  # noqa: SLF001 - stdlib, cryptography gerektirmez
        finally:
            Path(path).unlink(missing_ok=True)
        issuers = decoded.get("caIssuers") or ()
        if not issuers or decoded.get("issuer") == decoded.get("subject"):
            break
        with urllib.request.urlopen(issuers[0], timeout=10) as resp:  # noqa: S310 - http AIA beklenen
            der = resp.read()
        if der.startswith(b"-----BEGIN"):
            current = der.decode()
        else:
            current = ssl.DER_cert_to_PEM_cert(der)
        chain.append(current)
    return chain


def augmented_bundle() -> str | None:
    return str(_GLOBAL_BUNDLE) if _GLOBAL_BUNDLE.exists() else None


def repaired_bundle(url: str) -> str:
    """Eksik ara sertifikayı ortak pakete ekler; tüm alt alan adları bundan yararlanır."""
    host = urlparse(url).hostname or ""
    if host in _bundle_cache:
        return _bundle_cache[host]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    chain = _aia_chain(host)
    if not chain:
        raise RuntimeError("AIA ile ara sertifika bulunamadı")
    current = _GLOBAL_BUNDLE.read_text() if _GLOBAL_BUNDLE.exists() else Path(certifi.where()).read_text()
    added = [c for c in chain if c.strip() not in current]
    if added:
        _GLOBAL_BUNDLE.write_text(current + "\n" + "\n".join(added))
    _bundle_cache[host] = str(_GLOBAL_BUNDLE)
    return str(_GLOBAL_BUNDLE)


def _is_cert_error(exc: Exception) -> bool:
    text = f"{type(exc).__name__} {exc}"
    return "Certificate" in text or "curl: (60)" in text or "SSL certificate" in text


# ----------------------------------------------------------------------- fetchers
async def fetch_static(url: str, log=None, timeout: int = 20) -> Page:
    """Scrapling AsyncFetcher (+ gerekirse AIA ile TLS onarımı)."""
    from scrapling.fetchers import AsyncFetcher

    host = urlparse(url).hostname or ""
    kwargs = dict(impersonate="chrome", stealthy_headers=True, timeout=timeout, retries=1, follow_redirects=True,
                  headers=TR_HEADERS)
    bundle = _bundle_cache.get(host) or augmented_bundle()
    if bundle:
        kwargs["verify"] = bundle
    try:
        resp = await AsyncFetcher.get(url, **kwargs)
    except Exception as exc:  # noqa: BLE001
        if not _is_cert_error(exc) or host in _bundle_cache:
            raise
        if log:
            await log("TLS zinciri eksik (sunucu ara sertifikayı göndermiyor) → AIA ile tamamlanıyor, doğrulama açık kalıyor.")
        kwargs["verify"] = await asyncio.to_thread(repaired_bundle, url)
        resp = await AsyncFetcher.get(url, **kwargs)
    return Page(url=str(resp.url), status=resp.status, html=resp.html_content or "", via="scrapling.fetcher", selector=resp)


def _stealth_sync(url: str, wait_selector: str | None = None, solve_cf: bool = False) -> Page:
    from scrapling.fetchers import StealthyFetcher

    kwargs = dict(headless=True, network_idle=True, timeout=30000 if not solve_cf else 60000, block_webrtc=True, hide_canvas=True,
                  locale="tr-TR", extra_headers=TR_HEADERS, solve_cloudflare=solve_cf)
    if wait_selector:
        kwargs["wait_selector"] = wait_selector
    resp = StealthyFetcher.fetch(url, **kwargs)
    return Page(url=str(resp.url), status=resp.status, html=resp.html_content or "",
                via="scrapling.stealthy+cloudflare" if solve_cf else "scrapling.stealthy", selector=resp)


_STEALTH: dict = {"session": None, "loop": None, "lock": None}


async def _stealth_session():
    """Tek, kalıcı Scrapling AsyncStealthySession: tarayıcı her sayfa için yeniden açılmaz (≈3–4 sn kazanç)."""
    from scrapling.fetchers import AsyncStealthySession

    loop = asyncio.get_running_loop()
    if _STEALTH["loop"] is not loop:
        _STEALTH.update(session=None, loop=loop, lock=asyncio.Lock())
    async with _STEALTH["lock"]:
        if _STEALTH["session"] is None:
            sess = AsyncStealthySession(headless=True, network_idle=True, timeout=30000, block_webrtc=True,
                                        hide_canvas=True, locale="tr-TR", extra_headers=TR_HEADERS, max_pages=4)
            await sess.start()
            _STEALTH["session"] = sess
    return _STEALTH["session"]


async def close_stealth():
    sess = _STEALTH.get("session")
    _STEALTH["session"] = None
    if sess is not None:
        try:
            await sess.close()
        except Exception:  # noqa: BLE001
            pass


async def fetch_stealth(url: str, wait_selector: str | None = None, solve_cf: bool = False) -> Page:
    try:
        sess = await _stealth_session()
        kw = {"solve_cloudflare": solve_cf, "timeout": 60000 if solve_cf else 30000}
        if wait_selector:
            kw["wait_selector"] = wait_selector
        resp = await sess.fetch(url, **kw)
        return Page(url=str(resp.url), status=resp.status, html=resp.html_content or "",
                    via="scrapling.stealthy+cloudflare" if solve_cf else "scrapling.stealthy", selector=resp)
    except Exception:  # noqa: BLE001 - oturum bozulduysa sıfırla, tek seferlik tarayıcıyla dene
        await close_stealth()
        return await asyncio.to_thread(_stealth_sync, url, wait_selector, solve_cf)


_PAGE_CACHE: dict[str, tuple[float, "Page"]] = {}
PAGE_TTL = 300  # sn — aynı sayfa birkaç dakika içinde tekrar istenirse ağa çıkılmaz


async def fetch_smart(url: str, log=None, allow_stealth: bool = True, allow_cloudflare: bool = False) -> Page:
    import time as _t

    hit = _PAGE_CACHE.get(url)
    if hit and _t.time() - hit[0] < PAGE_TTL:
        return hit[1]
    page = await _fetch_smart(url, log, allow_stealth, allow_cloudflare)
    if page.status < 400 and soft_404(page.html):
        page.status = 404  # "200" dönüp "sayfa bulunamadı" diyen sayfalar (eski arama indeksi, silinmiş içerik)
    if page.status < 400 and not wall_reason(page.status, page.html):
        if len(_PAGE_CACHE) > 500:
            _PAGE_CACHE.clear()
        _PAGE_CACHE[url] = (_t.time(), page)
    return page


async def _fetch_smart(url: str, log=None, allow_stealth: bool = True, allow_cloudflare: bool = False) -> Page:
    """Merdiven: statik → (duvar ise) stealth. Duvarlar loglanır, akış kırılmaz."""
    page: Page | None = None
    try:
        page = await fetch_static(url, log=log)
        reason = wall_reason(page.status, page.html)
        if not reason:
            return page
        if log:
            await log(f"Duvar tespit edildi ({reason}) → Scrapling StealthyFetcher (Patchright) devreye giriyor.")
    except Exception as exc:  # noqa: BLE001
        if log:
            await log(f"Statik erişim başarısız ({type(exc).__name__}) → gizli tarayıcı deneniyor.")
    if not allow_stealth:
        if page:
            return page
        raise RuntimeError("statik erişim başarısız")
    stealth = await fetch_stealth(url)
    reason = wall_reason(stealth.status, stealth.html)
    if reason and allow_cloudflare:
        if log:
            await log(f"Stealth sonrası hâlâ duvar ({reason}) → Cloudflare/Turnstile çözücüyle son deneme (yavaş).")
        stealth = await fetch_stealth(url, solve_cf=True)
        reason = wall_reason(stealth.status, stealth.html)
    if reason and page is not None:
        stealth.notes.append(f"stealth sonrası hâlâ {reason}")
    return stealth


def parse(html: str, url: str):
    from scrapling.parser import Selector

    return Selector(html, url=url)
