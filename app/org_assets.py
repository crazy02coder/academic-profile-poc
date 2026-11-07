"""Kurum kayıtlarından bulunan logoları sınırlı, önbellekli ve yerel olarak sunar."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import ipaddress
import json
import re
import socket
import ssl
import time
import xml.etree.ElementTree as ET
from html import escape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx
import certifi

from . import firms, industry, yokdir
from .config import OPENALEX_PARAMS, ROOT, USER_AGENT
from .net import augmented_bundle, repaired_bundle, soft_404
from .discover import registrable
from .text import fold

CACHE = ROOT / "data" / "organization-logos"
_LIMIT = asyncio.Semaphore(3)
_INFLIGHT: dict[str, asyncio.Task] = {}
MAX_BYTES = 2_000_000
MAX_HTML_BYTES = 6_000_000
LOGO_VERSION = 4
POSITIVE_TTL = 30 * 86400
NEGATIVE_TTL = 10 * 60
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
_TLS_REPAIR = asyncio.Lock()


def public_client(**kwargs) -> httpx.AsyncClient:
    """Kök güveni ve hostname denetimi açık; projenin tamamlanmış ara zincirini kullan."""
    context = ssl.create_default_context(cafile=certifi.where())
    if bundle := augmented_bundle():
        context.load_verify_locations(cafile=bundle)
    return httpx.AsyncClient(verify=context, **kwargs)


async def public_url(url: str) -> bool:
    try:
        p = urlsplit(url)
        if p.scheme not in {"http", "https"} or not p.hostname or p.username or p.password or p.port not in (None, 80, 443):
            return False
        addresses = await asyncio.to_thread(socket.getaddrinfo, p.hostname, p.port or 443, type=socket.SOCK_STREAM)
        return bool(addresses) and all(ipaddress.ip_address(a[4][0]).is_global for a in addresses)
    except (OSError, ValueError):
        return False


async def read_public(client, url: str, max_bytes: int = MAX_BYTES, *, repair_tls: bool = True) -> tuple[bytes, str, str]:
    for _ in range(5):
        if not await public_url(url):
            raise ValueError("Public http(s) URL required")
        try:
            async with client.stream("GET", url, follow_redirects=False) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get("location", ""))
                    continue
                response.raise_for_status()
                chunks, size = [], 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError("Response too large")
                    chunks.append(chunk)
                return b"".join(chunks), response.headers.get("content-type", "").split(";")[0].lower(), str(response.url)
        except httpx.ConnectError as exc:
            if not repair_tls or "certificate_verify_failed" not in str(exc).lower():
                raise
            # Aynı sitede görülen eksik zincir logo ve öğrenci rehberinde ortak onarılır.
            try:
                async with _TLS_REPAIR:
                    await asyncio.to_thread(repaired_bundle, url)
            except Exception:
                raise exc
            async with public_client(timeout=client.timeout, headers=dict(client.headers)) as repaired:
                return await read_public(repaired, url, max_bytes, repair_tls=False)
    raise ValueError("Too many redirects")


async def fetch_home_page(client, home: str, max_bytes: int = MAX_HTML_BYTES) -> tuple[bytes, str, str]:
    """Kayıtlı kurumun aynı alan adında www / çıplak HTTPS ana sayfasını bul."""
    parsed = urlsplit(home)
    host = parsed.hostname or ""
    candidates = [home]
    alternate = host[4:] if host.startswith("www.") else "www." + host if host == registrable(host) else ""
    if alternate and parsed.scheme == "https" and not parsed.port:
        candidates.append(parsed._replace(netloc=alternate).geturl())
    failure = ValueError("Kurum ana sayfası okunamadı.")
    for url in candidates:
        try:
            body, mime, final = await read_public(client, url, max_bytes)
            if "html" not in mime or soft_404(body.decode("utf-8", errors="replace")):
                raise ValueError("Kurum adresi bir HTML ana sayfası döndürmedi.")
            return body, mime, final
        except (httpx.HTTPError, ValueError, OSError) as exc:
            failure = exc
    raise failure


class LogoParser(HTMLParser):
    def __init__(self, base, company=None):
        super().__init__()
        self.base, self.images, self.inline_images = base, [], []
        self.company = company
        self.identity, self.brand_labels = [], []
        self.jsonld_parts = None
        self.stack = []
        self.svg_parts = None
        self.svg_tags = []
        self.svg_depth = 0
        self.svg_rank = 0

    def _add(self, value, rank):
        value = (value or "").strip()
        if not value or value.startswith("#"):
            return
        try:
            url = urljoin(self.base, value)
            if urlsplit(url).scheme in {"http", "https"}:
                self.images.append((rank, url))
        except ValueError:
            pass

    def _sources(self, d, rank):
        # Lazy loaders commonly keep a transparent placeholder in src.
        for key in ("data-src", "data-lazy-src", "data-original", "data-lazy", "src"):
            value = d.get(key, "")
            if not re.search(r"(?:placeholder|spacer|blank\.(?:gif|png)|loading\.(?:gif|svg))", value, re.I):
                self._add(value, rank)
        for key in ("data-srcset", "srcset"):
            entries = []
            for part in d.get(key, "").split(","):
                fields = part.strip().split()
                if not fields or fields[0].startswith("data:"):
                    continue
                size = re.fullmatch(r"(\d+(?:\.\d+)?)[wx]", fields[-1]) if len(fields) > 1 else None
                entries.append((float(size[1]) if size else 0, fields[0]))
            for _, value in sorted(entries, reverse=True):
                self._add(value, rank)

    def handle_starttag(self, tag, attrs):
        # HTMLParser represents boolean/valueless attributes (e.g. <img alt>) as None.
        d = {key: value or "" for key, value in attrs}
        own_label = " ".join(d.get(key, "") for key in ("src", "data-src", "data-original", "srcset", "data-srcset", "alt", "title", "aria-label", "class", "id", "itemprop")).lower()
        context = " ".join(entry[1] for entry in self.stack[-5:])
        label = own_label + " " + context
        in_header = tag == "header" or any(entry[0] == "header" for entry in self.stack) or "header" in context
        in_footer = tag == "footer" or any(entry[0] == "footer" for entry in self.stack) or "footer" in label
        is_logo = bool(re.search(r"logo|navbar-brand|site-brand|amblem", label))
        excluded = bool(re.search(r"sponsor|partner|paydas|paydaş|yok[-_ ]logo|logo[-_ ]yok|yokak|kalite[-_ ]logo|middle-menu-home-icon", label))
        rank = 5 if in_footer else (0 if in_header else 2)
        if not excluded and is_logo:
            if tag in {"img", "source"}:
                self._sources(d, rank)
                self.brand_labels.extend(d.get(key, "") for key in ("alt", "title", "aria-label"))
            elif tag in {"object", "embed"}:
                self._add(d.get("data") or d.get("src"), rank)
        if tag == "meta":
            key = (d.get("property") or d.get("name") or d.get("itemprop") or "").lower()
            value = d.get("content", "")
            if key in {"og:site_name", "og:title", "application-name"}:
                self.identity.append(value)
            if key in {"logo", "og:logo"}:
                self._add(value, 1)
            elif key in {"og:image", "twitter:image"} and re.search(r"logo|amblem", value, re.I):
                # Sosyal paylaşım kartı/ürün fotoğrafı tek başına kurum logosu değildir.
                self._add(value, 6)
        if tag == "script" and d.get("type", "").lower().split(";")[0].strip() == "application/ld+json":
            self.jsonld_parts = []
        if tag == "link" and "icon" in d.get("rel", "").lower():
            self._add(d.get("href"), 8 if "apple-touch" in d["rel"].lower() else 9)
        # Keep inline brand SVGs; menu/search SVGs elsewhere in the header are ignored.
        if self.svg_parts is not None:
            self.svg_parts.append(self.get_starttag_text())
            original = re.match(r"<([^\s/>]+)", self.get_starttag_text())
            self.svg_tags.append(original[1] if original else tag)
            if tag == "svg":
                self.svg_depth += 1
        elif tag == "svg" and is_logo and not excluded:
            opening = self.get_starttag_text()
            if not d.get("xmlns"):
                opening = re.sub(r"<svg\b", '<svg xmlns="http://www.w3.org/2000/svg"', opening, count=1, flags=re.I)
            self.svg_parts, self.svg_depth, self.svg_rank = [opening], 1, rank
            self.svg_tags = ["svg"]
        if tag not in VOID_TAGS:
            self.stack.append((tag, " ".join(d.get(key, "") for key in ("class", "id", "aria-label")).lower()))

    def handle_endtag(self, tag):
        if tag == "script" and self.jsonld_parts is not None:
            try:
                self._jsonld(json.loads("".join(self.jsonld_parts)))
            except (ValueError, TypeError, RecursionError):
                pass
            self.jsonld_parts = None
        if self.svg_parts is not None:
            original = tag
            for i in range(len(self.svg_tags) - 1, -1, -1):
                if self.svg_tags[i].lower() == tag:
                    original = self.svg_tags[i]
                    del self.svg_tags[i:]
                    break
            self.svg_parts.append(f"</{original}>")
            if tag == "svg":
                self.svg_depth -= 1
                if not self.svg_depth:
                    data = "".join(self.svg_parts).encode("utf-8")
                    if len(data) <= MAX_BYTES:
                        self.inline_images.append((self.svg_rank, data))
                    self.svg_parts = None
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_startendtag(self, tag, attrs):
        # Preserve SVG self-closing path/use syntax instead of generating two end tags.
        capturing = self.svg_parts is not None
        if capturing and tag != "svg":
            self.svg_parts.append(self.get_starttag_text())
        else:
            self.handle_starttag(tag, attrs)
            if tag not in VOID_TAGS:
                if self.svg_parts is not None:
                    self.svg_parts[-1] = re.sub(r"/\s*>$", ">", self.svg_parts[-1])
                self.handle_endtag(tag)

    def handle_data(self, data):
        if self.jsonld_parts is not None:
            self.jsonld_parts.append(data)
        tags = {entry[0] for entry in self.stack}
        if "title" in tags or "h1" in tags:
            self.identity.append(data)
        if self.svg_parts is not None:
            self.svg_parts.append(escape(data, quote=False))
        if self.stack and self.stack[-1][0] == "script" and "brandImgUrl" in data:
            # Bazı CMS'ler ana marka görselini Angular aktarım verisinde tutar.
            # Bölüm logoları aynı veride bulunabildiğinden yalnız açıkça ana
            # sayfa alanında yayımlanan adayları kullan; ilk değeri kör seçme.
            state = data.replace(r"\&q;", '"').replace("&q;", '"').replace("&a;", "&")
            for match in re.finditer(r'"brandImgUrl"\s*:\s*("(?:\\.|[^"\\])*")', state):
                try:
                    value = json.loads(match[1])
                    if re.search(r"/(?:anasayfa|homepage|home)/", value, re.I):
                        self._add(value, 1)
                except (ValueError, TypeError):
                    continue

    def _jsonld(self, node, depth=0):
        if depth > 8:
            return
        if isinstance(node, list):
            for item in node[:80]:
                self._jsonld(item, depth + 1)
        elif isinstance(node, dict):
            types = node.get("@type") or []
            types = [types] if isinstance(types, str) else types
            if isinstance(types, list) and any(t in {"Organization", "Corporation", "LocalBusiness", "CollegeOrUniversity"} for t in types if isinstance(t, str)):
                names = [node.get("name"), node.get("legalName"), node.get("alternateName")]
                names = [name for name in names if isinstance(name, str)]
                if not self.company or any(_company_name_matches(name, self.company) for name in names):
                    self.identity.extend(names)
                    logo = node.get("logo")
                    if isinstance(logo, dict):
                        logo = logo.get("contentUrl") or logo.get("url") or logo.get("@id")
                    if isinstance(logo, str):
                        self._add(logo, 1)
            # Yayıncı/ana kurum düğümleri; ürün, yorum ve ortakların görsellerini toplama.
            for key in ("@graph", "publisher", "mainEntity", "mainEntityOfPage"):
                if key in node:
                    self._jsonld(node[key], depth + 1)


async def university_home(uid: str) -> str:
    uni = await yokdir._university(uid)
    if not uni:
        return ""
    async with yokdir._client() as client:
        return await yokdir._home_of(client, uni)


_WEBSITE_KEYS = {"url", "website", "website_url", "homepage", "homepage_url", "official_url", "web_url", "web", "web_adresi", "internet_adresi", "source_url"}
_THIRD_PARTY_HOSTS = {"google.com", "bing.com", "duckduckgo.com", "brave.com", "wikipedia.org", "wikimedia.org",
                      "openalex.org", "linkedin.com", "facebook.com", "instagram.com", "x.com", "twitter.com",
                      "youtube.com", "crunchbase.com", "bloomberg.com", "zoominfo.com", "trendyol.com", "hepsiburada.com"}
_REGISTRY_WEBSITES: tuple[float, dict] = (0, {})


def _metadata_urls(record: dict) -> list[str]:
    """Yalnız şirketin web/kaynak alanları; yayın, patent ve kişi bağlantıları değil."""
    urls = []
    for key, value in record.items():
        if key.lower() in _WEBSITE_KEYS and isinstance(value, str):
            value = value.strip()
            if value.startswith("www."):
                value = "https://" + value
            if value.startswith(("https://", "http://")):
                urls.append(value)
        elif key in {"source", "sources", "links"}:
            entries = value if isinstance(value, list) else [value]
            for item in entries[:8]:
                if isinstance(item, dict):
                    urls.extend(_metadata_urls({k: v for k, v in item.items() if k not in {"source", "sources", "links"}}))
                elif isinstance(item, str) and item.startswith(("https://", "http://")):
                    urls.append(item)
    return urls


def _stored_company_websites(group: dict) -> list[str]:
    global _REGISTRY_WEBSITES
    urls = _metadata_urls(group)
    try:
        mtime = industry.CENTERS_PATH.stat().st_mtime
        if _REGISTRY_WEBSITES[0] != mtime:
            rows = json.loads(industry.CENTERS_PATH.read_text()).get("centers", [])
            _REGISTRY_WEBSITES = (mtime, {r["name"]: _metadata_urls(r) for r in rows if isinstance(r, dict) and r.get("name")})
        for name in group["centers"]:
            urls.extend(_REGISTRY_WEBSITES[1].get(name, []))
    except (OSError, ValueError, TypeError):
        pass
    return list(dict.fromkeys(urls))[:4]


def _company_name_matches(value: str, group: dict) -> bool:
    return bool(value) and (industry.match(value) is group or fold(value.strip()) in {fold(n) for n in firms._names(group)})


def _company_candidate(url: str, group: dict, *, require_brand=True) -> bool:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower().rstrip(".")
        root = registrable(host)
        if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password or parsed.port not in {None, 80, 443}:
            return False
        if root in _THIRD_PARTY_HOSTS or re.search(r"\.(?:gov|edu|ac|bel)\.[a-z]{2}$", host):
            return False
        label = re.sub(r"[^a-z0-9]", "", fold(root.split(".")[0]))
        if re.search(r"servis|bayi|haber|sikayet|rehber|yedekparca", label):
            return False
        if not require_brand:
            return True
        brands = [re.sub(r"[^a-z0-9]", "", fold(name)) for name in firms._names(group)]
        # Arama sonucundaki alan adını doğrula; firma adından .com/.com.tr üretme.
        return any(len(brand) >= 3 and brand in label for brand in brands)
    except (ValueError, TypeError):
        return False


def _company_identity(parser: LogoParser, group: dict, *, trusted_domain="") -> bool:
    same_domain = trusted_domain and registrable(urlsplit(parser.base).hostname or "") == trusted_domain
    if not _company_candidate(parser.base, group, require_brand=not same_domain):
        return False
    labels = [label for label in parser.identity + parser.brand_labels if label.strip()]
    if any(re.search(r"yetkili servis|ozel servis|haberleri|firma rehberi|sikayet|bayi", fold(label)) for label in parser.identity):
        return False
    # İsim yalnız arama özetinde veya sayfa gövdesinde geçiyorsa kanıt sayılmaz.
    return any(_company_name_matches(label, group) for label in labels)


async def _company_search(group: dict) -> list[str]:
    from . import websearch

    # Merkezin şehri genel marka sitesini dışlayabiliyor; mevcut kısa marka/alias kullan.
    brand = min(firms._names(group), key=len)
    query = f'"{brand}" resmi web sitesi'
    tasks = [asyncio.create_task(websearch._ddgs_worker(query, backend)) for backend in ("brave", "duckduckgo")]
    rows = []
    try:
        # Mevcut DDGS işçisi genel sorguyu destekler; site_search alan adı gerektirir.
        async with asyncio.timeout(7):
            for finished in asyncio.as_completed(tasks):
                try:
                    batch = await finished
                    rows.extend(row for row in batch if _company_candidate(row.get("url", ""), group))
                    if rows:
                        break
                except (RuntimeError, ValueError, OSError):
                    continue
    except TimeoutError:
        pass
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    if not rows:
        # Mevcut sağlayıcı kendi hız/süre sınırı ve hata bekleme süresini korur.
        if "google" in websearch.provider_order():
            rows = await websearch._provider("google", query)
        if not any(_company_candidate(row.get("url", ""), group) for row in rows):
            rows = await websearch._provider("brave_page", query)
    candidates, seen = [], set()
    for row in rows:
        url = row.get("url", "")
        if not _company_candidate(url, group):
            continue
        parsed = urlsplit(url)
        home = parsed._replace(path="/", query="", fragment="").geturl()
        host = registrable(parsed.hostname or "")
        if host not in seen:
            seen.add(host)
            candidates.append(home)
        if len(candidates) == 3:
            break
    return candidates


async def _origin(kind: str, oid: str, client, previous=None) -> tuple[str, str, LogoParser | None]:
    if kind == "universities":
        return await university_home(oid), "", None
    group = firms._groups().get(oid)
    if not group:
        return "", "", None
    seen = set()

    async def verified_home(url, *, trusted=False):
        if not _company_candidate(url, group, require_brand=not trusted) or url in seen:
            return None
        seen.add(url)
        try:
            async with asyncio.timeout(9):
                body, _, final = await fetch_home_page(client, url)
                parser = LogoParser(final, company=group)
                parser.feed(body.decode("utf-8", errors="replace"))
                trusted_domain = registrable(urlsplit(url).hostname or "") if trusted else ""
                if _company_identity(parser, group, trusted_domain=trusted_domain):
                    return final, "", parser
        except (TimeoutError, httpx.HTTPError, ValueError, OSError):
            pass
        return None

    stored = _stored_company_websites(group)
    if previous and previous.get("home"):
        stored.insert(0, previous["home"])
    for url in stored[:4]:
        if found := await verified_home(url, trusted=bool(previous and url == previous.get("home"))):
            return found
    known = ""
    try:
        async with asyncio.timeout(5):
            response = await client.get(f"{firms.OPENALEX}/institutions", params={"search": group["name"],
                "filter": "country_code:TR", "per-page": 10, **OPENALEX_PARAMS})
            response.raise_for_status()
            institutions = response.json().get("results") or []
    except (TimeoutError, httpx.HTTPError, ValueError, OSError):
        institutions = []  # OpenAlex kotası/eksik kaydı firmanın kendi sitesini engellemez.
    for candidate in institutions:
        names = [candidate.get("display_name", ""), *(candidate.get("display_name_alternatives") or []), *(candidate.get("display_name_acronyms") or [])]
        if candidate.get("type") != "company" or not any(_company_name_matches(n, group) for n in names):
            continue
        known = candidate.get("image_url") or known
        if found := await verified_home(candidate.get("homepage_url") or "", trusted=True):
            return found[0], known, found[2]
    for url in await _company_search(group):
        if found := await verified_home(url):
            return found[0], known, found[2]
    return "", known, None


def _image_type(data: bytes, declared: str) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"\x00\x00\x01\x00"):
        return "image/x-icon"
    svg_document = re.match(br"\s*(?:<\?xml[^>]*>\s*)?<svg(?:\s|>)", data[:1000])
    if (declared == "image/svg+xml" or svg_document) and re.search(br"<svg(?:\s|>)", data[:1000]):
        # Harici dosya/kod içerebilen SVG'leri logo olarak sunma.
        if not re.search(br"<script|<foreignObject|<!ENTITY|<!DOCTYPE|\bon\w+\s*=|(?:href|url)\s*[=(]\s*[\"']?(?:https?:|//|javascript:)|\b(?:xlink:)?href\s*=\s*[\"'](?!#)", data, re.I):
            try:
                root = ET.fromstring(data)
                if root.tag in {"svg", "{http://www.w3.org/2000/svg}svg"}:
                    return "image/svg+xml"
            except ET.ParseError:
                pass  # Geçersiz/eksik SVG yerine sıradaki logo veya simgeyi dene.
    return ""


async def _collect(kind: str, oid: str, path, previous: dict | None = None) -> dict:
    result = {"at": time.time(), "version": LOGO_VERSION, "data": "", "type": "", "source": ""}
    async with _LIMIT:
        try:
            async with asyncio.timeout(45), public_client(timeout=10, headers={"User-Agent": USER_AGENT, "Accept-Language": "tr-TR,tr;q=0.9"}) as client:
                home, known, parser = await _origin(kind, oid, client, previous)
                candidates = []
                if home:
                    try:
                        final = home
                        if parser is None:
                            body, _, final = await fetch_home_page(client, home)
                            parser = LogoParser(final)
                            parser.feed(body.decode("utf-8", errors="replace"))
                        result["home"] = final
                        candidates.extend((rank, "url", url) for rank, url in parser.images)
                        candidates.extend((rank, "inline", image) for rank, image in parser.inline_images)
                        candidates.append((10, "url", urljoin(final, "/favicon.ico")))
                    except (httpx.HTTPError, ValueError) as exc:
                        result["reason"] = type(exc).__name__
                if known:
                    candidates.append((6, "url", known))
                if not candidates:
                    result.setdefault("reason", "NoVerifiedHomepageOrLogo")
                seen = set()
                for _, source_kind, value in sorted(candidates, key=lambda entry: entry[0]):
                    identity = (source_kind, value)
                    if identity in seen:
                        continue
                    seen.add(identity)
                    if len(seen) > 8:
                        break
                    try:
                        if source_kind == "inline":
                            body, declared, final = value, "image/svg+xml", home
                        else:
                            body, declared, final = await read_public(client, value)
                        mime = _image_type(body, declared)
                        if mime:
                            result.update(data=base64.b64encode(body).decode(), type=mime, source=final)
                            break
                    except (httpx.HTTPError, ValueError):
                        continue
        except (TimeoutError, httpx.HTTPError, ValueError, OSError) as exc:
            result["reason"] = type(exc).__name__
    if not result["data"] and previous and previous.get("data"):
        # An expired, valid logo remains usable during a temporary site outage.
        result = {**previous, "version": LOGO_VERSION, "retry_at": time.time()}
    CACHE.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(result))
    tmp.replace(path)
    return result


async def logo(kind: str, oid: str) -> dict:
    if kind not in {"universities", "firms"} or not re.fullmatch(r"[a-z0-9-]{1,180}", oid):
        return {}
    key = hashlib.sha256(f"{kind}:{oid}".encode()).hexdigest()
    path = CACHE / f"{key}.json"
    cached = None
    try:
        cached = json.loads(path.read_text())
        if not isinstance(cached, dict):
            cached = None
            raise ValueError("Invalid logo cache")
        now = time.time()
        if cached.get("data") and (now - cached["at"] < POSITIVE_TTL or now - cached.get("retry_at", 0) < NEGATIVE_TTL):
            return cached
        # Old negative cache entries came from the previous parser; retry once now.
        if not cached.get("data") and cached.get("version") == LOGO_VERSION and now - cached["at"] < NEGATIVE_TTL:
            return cached
    except (OSError, ValueError, KeyError):
        pass
    task = _INFLIGHT.get(key)
    if task is None:
        task = _INFLIGHT[key] = asyncio.create_task(_collect(kind, oid, path, cached))
        task.add_done_callback(lambda _: _INFLIGHT.pop(key, None))
    return await asyncio.shield(task)
