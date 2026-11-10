"""Kamuya açık OA PDF keşfi; düz HTTP ve isteğe bağlı sınırlı tarayıcı yedeği."""
from __future__ import annotations
import asyncio
import hashlib
import html
import io
import json
import os
import re
import time
from urllib.parse import urljoin, urlsplit, quote
from urllib.robotparser import RobotFileParser
import httpx
from .config import ROOT, OPENALEX_PARAMS
from .org_assets import public_url, public_client, read_public
from .library_common import atomic_json

CACHE = ROOT / "data/cache/pdf_resolve"
UA = "AkademikIz/1.0"
HOSTS: dict[str, asyncio.Semaphore] = {}
ROBOTS: dict[str, tuple[float, RobotFileParser | None]] = {}
LOCKS: dict[str, asyncio.Lock] = {}

def host(url):
    return (urlsplit(url).hostname or "").lower()

async def robots_allowed(url: str) -> bool:
    origin = f"{urlsplit(url).scheme}://{urlsplit(url).netloc}"
    cached = ROBOTS.get(origin)
    if cached and time.time() - cached[0] < 3600:
        return cached[1] is not None and cached[1].can_fetch(UA, url)
    parser = RobotFileParser()
    try:
        if not await public_url(origin):
            return False
        async with public_client(timeout=12, headers={"User-Agent": UA}) as client:
            async with client.stream("GET", origin + "/robots.txt", follow_redirects=False) as response:
                if response.status_code == 404:
                    parser.parse([])
                elif response.status_code == 200:
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 512_000:
                            raise ValueError("robots sınırı")
                    parser.parse(raw.decode("utf-8", "replace").splitlines())
                else:
                    ROBOTS[origin] = (time.time(), None)
                    return False
        ROBOTS[origin] = (time.time(), parser)
        return parser.can_fetch(UA, url)
    except (httpx.HTTPError, ValueError, OSError):
        ROBOTS[origin] = (time.time(), None)
        return False

async def valid_pdf(url: str) -> str | None:
    for _ in range(4):
        if not await public_url(url) or not await robots_allowed(url):
            return None
        async with HOSTS.setdefault(host(url), asyncio.Semaphore(2)):
            try:
                async with public_client(timeout=12, headers={"User-Agent": UA, "Range": "bytes=0-1023"}) as client:
                    async with client.stream("GET", url, follow_redirects=False) as response:
                        if response.is_redirect:
                            url = urljoin(url, response.headers.get("location", ""))
                            continue
                        if response.status_code not in (200, 206):
                            return None
                        content = bytearray()
                        async for chunk in response.aiter_bytes(chunk_size=1024):
                            content.extend(chunk[:1024 - len(content)])
                            if len(content) >= 5:
                                break
                        if bytes(content).startswith(b"%PDF-") or "application/pdf" in response.headers.get("content-type", ""):
                            return url
                        return None
            except (httpx.HTTPError, ValueError, OSError):
                return None
    return None

def _plain_fetch(url: str):
    from scrapling.fetchers import Fetcher
    # Varsayılan Chrome kimliği ve tarayıcı başlıkları açıkça kapalı.
    response = Fetcher.get(url, timeout=12, impersonate=None, stealthy_headers=False,
                           headers={"User-Agent": UA}, follow_redirects=False, retries=0)
    return response.status, dict(response.headers), response.body

async def landing_links(url: str) -> list[str]:
    for _ in range(4):
        if not await public_url(url) or not await robots_allowed(url):
            return []
        async with HOSTS.setdefault(host(url), asyncio.Semaphore(2)):
            try:
                try:
                    status, headers, raw = await asyncio.to_thread(_plain_fetch, url)
                except (ImportError, ModuleNotFoundError):
                    async with public_client(timeout=12, headers={"User-Agent": UA}) as client:
                        async with client.stream("GET", url, follow_redirects=False) as response:
                            status, headers, raw = response.status_code, dict(response.headers), bytearray()
                            async for chunk in response.aiter_bytes():
                                raw.extend(chunk)
                                if len(raw) > 2_000_000:
                                    return []
                headers = {str(k).lower(): str(v) for k, v in headers.items()}
                if status in (301, 302, 303, 307, 308):
                    url = urljoin(url, headers.get("location", ""))
                    continue
                if status != 200 or len(raw) > 2_000_000:
                    return []
                text = bytes(raw).decode("utf-8", "replace") if not isinstance(raw, str) else raw
                if re.search(r"cf-chl-|challenge-platform|verify you are human|captcha|just a moment", text, re.I):
                    return []
                from html.parser import HTMLParser
                class Links(HTMLParser):
                    def __init__(self):
                        super().__init__(); self.links = []
                    def handle_starttag(self, tag, attrs):
                        a = dict(attrs)
                        target = a.get("href", "")
                        if tag == "meta" and a.get("name", "").lower() == "citation_pdf_url":
                            self.links.append(a.get("content", ""))
                        if tag == "link" and a.get("type") == "application/pdf":
                            self.links.append(target)
                        if tag == "a" and re.search(r"\.pdf(?:\?|$)|/download/article-file/|/article/download/", target, re.I):
                            self.links.append(target)
                parser = Links(); parser.feed(text)
                return list(dict.fromkeys(urljoin(url, html.unescape(u)) for u in parser.links if u))[:12]
            except Exception:
                return []
    return []

async def resolve(doi: str = "", url: str = "") -> dict:
    doi = re.sub(r"^https?://(?:dx\.)?doi.org/", "", doi, flags=re.I).strip()[:300]
    key = hashlib.sha256(f"{doi}|{url}".encode()).hexdigest()
    path = CACHE / f"{key}.json"
    async with LOCKS.setdefault(key, asyncio.Lock()):
        try:
            record = json.loads(path.read_text())
            if time.time() - record["at"] < (604800 if record.get("pdf") else 3600):
                return record
        except (OSError, ValueError, KeyError):
            pass
        candidates, landing, oa = [], [], False
        if doi:
            async with httpx.AsyncClient(timeout=12, headers={"User-Agent": UA}) as client:
                try:
                    response = await client.get(f"https://api.openalex.org/works/https://doi.org/{quote(doi, safe='')}", params=OPENALEX_PARAMS)
                    if response.status_code == 200:
                        work = response.json(); oa = bool((work.get("open_access") or {}).get("is_oa"))
                        for loc in [work.get("best_oa_location") or {}, *(work.get("locations") or [])]:
                            if loc.get("is_oa") or loc == work.get("best_oa_location"):
                                candidates.append(loc.get("pdf_url")); landing.append(loc.get("landing_page_url"))
                except (httpx.HTTPError, ValueError):
                    pass
                # Sadece ayrı servis hesabı; kullanıcı ya da OpenAlex iletişim adresi kullanılmaz.
                email = os.environ.get("UNPAYWALL_EMAIL", "").strip()
                if email:
                    try:
                        response = await client.get(f"https://api.unpaywall.org/v2/{quote(doi, safe='')}", params={"email": email})
                        if response.status_code == 200:
                            for loc in response.json().get("oa_locations") or []:
                                candidates.append(loc.get("url_for_pdf")); landing.append(loc.get("url_for_landing_page"))
                    except (httpx.HTTPError, ValueError):
                        pass
        if url and (oa or re.search(r"(^|\.)(dergipark.org.tr|arxiv.org|oapen.org)$", host(url)) or re.search(r"/(?:ojs|handle|xmlui|dspace)/", url)):
            landing.append(url)
        for candidate in dict.fromkeys(filter(None, candidates)):
            found = await valid_pdf(candidate)
            if found:
                result = {"pdf": found, "is_oa": True, "at": time.time()}; atomic_json(path, result); return result
        for page in dict.fromkeys(filter(None, landing)):
            links = await landing_links(page)
            for candidate in links:
                found = await valid_pdf(candidate)
                if found:
                    result = {"pdf": found, "is_oa": True, "at": time.time()}; atomic_json(path, result); return result
        result = {"pdf": None, "at": time.time(), "detail": "Açık erişim PDF bulunamadı"}
        atomic_json(path, result); return result

def render_thumb(source, output):
    import pypdfium2 as pdfium
    document = pdfium.PdfDocument(source)
    try:
        page = document[0]
        try:
            bitmap = page.render(scale=360 / max(page.get_width(), 1))
            try:
                image = bitmap.to_pil().convert("RGB")
                output.parent.mkdir(parents=True, exist_ok=True); image.save(output, "JPEG", quality=82)
            finally:
                bitmap.close()
        finally:
            page.close()
    finally:
        document.close()

async def thumbnail(doi: str):
    path = CACHE / (hashlib.sha256(doi.encode()).hexdigest() + ".jpg")
    if path.exists():
        return path
    result = await resolve(doi)
    if not result.get("pdf"):
        return None
    from .reading import pdf
    try:
        raw, _ = await pdf(result["pdf"])
        await asyncio.to_thread(render_thumb, raw, path)
        return path
    except (ImportError, ValueError, OSError):
        return None
