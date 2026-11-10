"""Arşiv katının açık kitapları.

Kaynaklar (hepsi açık erişim, anahtar gerekmez):
- OAPEN Library ve DOAB: OAI-PMH hasadı. Eski REST arayüzleri IP izin listesiyle kapalı; atlatılmaz.
- OpenStax: CMS API'sindeki yayındaki ders kitapları.
- Open Textbook Library: textbooks.json sayfaları.
- TÜBA Açık Ders: site haritasındaki ders sayfaları (robots.txt izin veriyor), haftalık PDF notları.
Her kaynak haftada bir hasat edilip diskte tutulur. Sayfa açılışı hasadı en fazla birkaç saniye bekler,
bitmeyen hasat arka planda sürer ve bir sonraki açılışta raflara gelir.
"""
from __future__ import annotations
import asyncio
import html
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urljoin, urlsplit
import httpx
from .config import ROOT
from .library_common import CATEGORY_MAP, atomic_json, clean_title
from .org_assets import public_client

CACHE = ROOT / "data/cache/oa_books"
TTL = 7 * 86400
UA = {"User-Agent": "AkademikIz/1.0 (acik erisim kitap katalogu; haftalik hasat)"}
TEXT_HOSTS = {"www.gutenberg.org", "gutenberg.org"}
OAI = "{http://www.openarchives.org/OAI/2.0/}"
LANGS = {"eng", "en", "tur", "tr"}
TASKS: dict[str, asyncio.Task] = {}

SOURCES = {
    "oapen": {"name": "OAPEN", "url": "https://library.oapen.org/"},
    "doab": {"name": "DOAB", "url": "https://www.doabooks.org/"},
    "openstax": {"name": "OpenStax", "url": "https://openstax.org/"},
    "otl": {"name": "Open Textbook Library", "url": "https://open.umn.edu/opentextbooks/"},
    "tuba": {"name": "TÜBA Açık Ders", "url": "https://acikders.tuba.gov.tr/"},
}

# ------------------------------------------------------------------ kategori
WORDS = {
    "muhendislik": "engineering computer computing software programming algorithm algorithms electronics electrical mechanical robotics technology manufacturing "
                   "mühendislik bilgisayar yazılım algoritma algoritmalara elektrik elektronik makine optoelektronik",
    "tip": "medicine medical nursing anatomy physiology pharmacology clinical disease health healthcare "
           "tıp sağlık hemşirelik anatomi fizyoloji hastalık",
    "temel": "mathematics math algebra calculus statistics statistical physics chemistry biology biological astronomy geology ecology quantum "
             "matematik cebir analiz istatistik istatistiksel fizik fiziği kimya biyoloji jeoloji ekoloji topoloji kuantum mekanik mekaniği termodinamik petroloji",
    "hukuk": "economics economic economy accounting finance financial business management marketing law legal entrepreneurship "
             "iktisat iktisadi ekonometri ekonomi finans finansal işletme muhasebe pazarlama hukuk yatırım",
    "sosyal": "sociology psychology political politics anthropology society social gender media communication philosophy policy "
              "sosyoloji psikoloji siyaset siyasal antropoloji felsefe felsefesi iletişim toplum kamu",
    "tarih": "history historical archaeology medieval ancient "
             "tarih tarihi tarihine arkeoloji antik uygarlığı",
    "sanat": "art arts music literature literary poetry film theatre language linguistics architecture "
             "edebiyat sanat sanatı müzik dil mimarlığı heykel",
    "egitim": "education educational teaching pedagogy learning teacher college success "
              "eğitim öğretim",
    "klasikler": "fiction novel novels stories classics",
}
_WORD_SETS = {k: set(v.split()) for k, v in WORDS.items()}


def guess(text: str) -> str:
    words = re.findall(r"[^\W\d_]+", str(text).casefold())
    scores = {k: sum(w in s for w in words) for k, s in _WORD_SETS.items()}
    key = max(scores, key=scores.get)
    return key if scores[key] else "genel"


def thema(code: str) -> str:
    """EDItEUR Thema sınıf kodundan raf kategorisi."""
    c = code.upper()
    if c.startswith("JN"): return "egitim"
    if c.startswith(("K", "L")): return "hukuk"
    if c.startswith(("M", "VF")): return "tip"
    if c.startswith("N"): return "tarih"
    if c.startswith(("P", "R")): return "temel"
    if c.startswith(("T", "U")): return "muhendislik"
    if c.startswith(("A", "C", "D")): return "sanat"
    if c.startswith(("F", "X")): return "klasikler"
    if c.startswith(("J", "Q", "G")): return "sosyal"
    return "genel"


TUBA_CATS = {
    "temel-bilimler": "temel", "biyoloji": "temel", "ekoloji": "temel", "fizik": "temel", "kimya": "temel", "matematik": "temel", "yer-bilimleri": "temel",
    "muhendislik-bilimleri": "muhendislik", "muhendislik": "muhendislik",
    "antropoloji": "sosyal", "arastirma-yontemleri": "sosyal", "psikoloji": "sosyal", "sosyoloji": "sosyal", "felsefe": "sosyal",
    "siyaset-bilimi-ve-kamu-yonetimi": "sosyal", "sosyal-bilimler": "sosyal",
    "arkeoloji": "tarih", "tarih": "tarih", "turk-dili-ve-edebiyati": "sanat", "sanat": "sanat",
    "bilgi-ve-belge-yonetimi": "egitim", "egitim": "egitim", "iktisat": "hukuk", "isletme": "hukuk", "ekonomi": "hukuk", "hukuk": "hukuk",
    "saglik-bilimleri": "tip", "tip": "tip",
}
OPENSTAX_CATS = {"Science": "temel", "Math": "temel", "Business": "hukuk", "Social Sciences": "sosyal", "Nursing": "tip",
                 "Humanities": "sanat", "Computer Science": "muhendislik", "College Success": "egitim"}


def _text(value: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", str(value or ""))).split())


# ------------------------------------------------------------------ OAI-PMH (OAPEN, DOAB)
def _oai_page(raw: bytes) -> tuple[list[dict], str]:
    root = ET.fromstring(raw)
    out = []
    for rec in root.iter(OAI + "record"):
        header = rec.find(OAI + "header")
        if header is not None and header.get("status") == "deleted":
            continue
        meta = rec.find(OAI + "metadata")
        if meta is None or not len(meta):
            continue
        fields: dict[str, list[tuple[str, dict]]] = {}
        for el in meta[0]:
            fields.setdefault(el.tag.rsplit("}", 1)[-1], []).append((" ".join((el.text or "").split()), el.attrib))
        out.append(fields)
    token = root.find(f".//{OAI}resumptionToken")
    return out, (token.text or "").strip() if token is not None else ""


def _from_oai(f: dict, source: str) -> dict | None:
    def values(key):
        return [t for t, _ in f.get(key, []) if t]
    title = clean_title((values("title") or [""])[0])
    lang = (values("language") or [""])[0].lower()[:3]
    if not title or (lang and lang not in LANGS):
        return None
    authors = values("creator") or [t for t, a in f.get("contributor", []) if t and a.get("type", "Author") in ("Author", "Editor")]
    codes, words = [], []
    for subject in values("subject"):
        if "::" in subject:
            codes.append(subject.rsplit("::", 1)[-1].split(" ", 1)[0])
        elif re.fullmatch(r"[A-Z]{1,6}", subject):
            codes.append(subject)
        else:
            words.append(subject)
    category = next((c for c in map(thema, codes) if c != "genel"), "") or guess(" ".join([title, *words]))
    dates = [t for t, a in f.get("date", []) if a.get("type") == "Issued"] or values("date")
    year = next((m[0] for d in dates if (m := re.search(r"\b(1[5-9]\d\d|20\d\d)\b", d))), "")
    urls = [t for t in values("identifier") if t.startswith("http")]
    handle = next((u for u in urls if "/handle/" in u), "")
    if source == "oapen":
        files = [t for t in values("source") if t.lower().endswith(".pdf")]
        pdf = f"{handle.replace('/handle/', '/bitstream/handle/')}/{quote(files[0])}" if handle and files else ""
    else:
        pdf = next((u for u in urls if urlsplit(u).path.lower().endswith(".pdf") or "library.oapen.org/bitstream" in u), "")
    link = handle if source == "oapen" else next((u for u in urls if "/handle/" not in u), "") or handle
    license_ = next((t for t, _ in f.get("licenseCondition", []) if t), "") or "Açık erişim · kaynak lisansına bakın"
    ident = handle.rsplit("/handle/", 1)[-1] or title[:60]
    return {"id": f"{source}:{ident}", "title": title, "authors": authors[:6], "year": year, "license": license_, "category": category,
            "source": SOURCES[source]["name"], "language": "tr" if lang in ("tur", "tr") else "en", "pdf": pdf, "url": link,
            "doi": (values("identifierdoi") or [""])[0], "publisher": (values("publisher") or [""])[0],
            "abstract": _text((values("description") or [""])[0])[:1500], "is_oa": True}


async def _oai(client: httpx.AsyncClient, source: str, base: str, params: dict, pages: int) -> list[dict]:
    items, token = [], ""
    for page in range(pages):
        query = {"verb": "ListRecords", "resumptionToken": token} if token else {"verb": "ListRecords", **params}
        response = await client.get(base, params=query)
        response.raise_for_status()
        records, token = await asyncio.to_thread(_oai_page, response.content)
        items += [x for x in (_from_oai(r, source) for r in records) if x]
        if not token:
            break
        await asyncio.sleep(1.0)  # OAI sunucularına nazik hasat
    return items


async def _oapen(client):
    since = (datetime.now(timezone.utc) - timedelta(days=400)).date().isoformat()
    return await _oai(client, "oapen", "https://library.oapen.org/oai/request",
                      {"metadataPrefix": "oai_dc", "set": "com_20.500.12657_5", "from": since}, 6)


async def _doab(client):
    since = (datetime.now(timezone.utc) - timedelta(days=150)).date().isoformat()
    return await _oai(client, "doab", "https://directory.doabooks.org/oai/request", {"metadataPrefix": "oai_dc", "from": since}, 4)


# ------------------------------------------------------------------ OpenStax
async def _openstax(client):
    response = await client.get("https://openstax.org/apps/cms/api/v2/pages/", params={
        "type": "books.Book", "limit": 250,
        "fields": "title,cover_url,high_resolution_pdf_url,book_subjects,book_state,webview_rex_link,description"})
    response.raise_for_status()
    out = []
    for b in response.json().get("items", []):
        meta = b.get("meta") or {}
        if b.get("book_state") != "live" or meta.get("locale", "en") != "en":
            continue
        title = clean_title(b.get("title"))
        subjects = [s.get("subject_name", "") for s in b.get("book_subjects") or []]
        category = guess(title)
        if category == "genel":
            category = next((OPENSTAX_CATS[s] for s in subjects if s in OPENSTAX_CATS), "genel")
        out.append({"id": f"openstax:{b.get('id')}", "title": title, "authors": ["OpenStax"], "year": str(meta.get("first_published_at", ""))[:4],
                    "license": "CC BY 4.0", "category": category, "source": "OpenStax", "language": "en",
                    "pdf": b.get("high_resolution_pdf_url") or "", "url": b.get("webview_rex_link") or meta.get("html_url", ""),
                    "cover": b.get("cover_url") or "", "abstract": _text(b.get("description"))[:1500], "is_oa": True})
    return out


# ------------------------------------------------------------------ Open Textbook Library
async def _otl(client, pages: int = 14):
    out = []
    for page in range(1, pages + 1):
        response = await client.get("https://open.umn.edu/opentextbooks/textbooks.json", params={"page": page})
        if response.status_code != 200:
            break
        rows = response.json().get("data") or []
        for b in rows:
            if b.get("language") not in LANGS:
                continue
            formats = b.get("formats") or []
            pdf = next((x.get("url") for x in formats if x.get("type") == "PDF" and x.get("url")), "")
            online = next((x.get("url") for x in formats if x.get("type") in ("Online", "eBook") and x.get("url")), "")
            subjects = [s.get("name", "") for s in b.get("subjects") or []]
            people = [" ".join(filter(None, [c.get("first_name"), c.get("last_name")])) for c in b.get("contributors") or []
                      if c.get("contribution") in ("Author", "Editor")]
            title = clean_title(b.get("title"))
            out.append({"id": f"otl:{b.get('id')}", "title": title, "authors": [p for p in people if p][:6], "year": str(b.get("copyright_year") or ""),
                        "license": b.get("license") or "Açık lisans", "category": guess(" ".join([title, *subjects])), "source": "Open Textbook Library",
                        "language": "tr" if b.get("language") in ("tur", "tr") else "en", "pdf": pdf, "url": online or b.get("url", ""),
                        "abstract": _text(b.get("description"))[:1500], "is_oa": True})
        if len(rows) < 10:
            break
        await asyncio.sleep(.5)
    return out


# ------------------------------------------------------------------ TÜBA Açık Ders
def _meta(page: str, name: str) -> str:
    m = re.search(rf'<meta (?:property|name)="{name}" content="([^"]*)"', page)
    return html.unescape(m[1]).strip() if m else ""


async def _tuba(client, limit: int = 120):
    sitemap = await client.get("https://acikders.tuba.gov.tr/sitemap.xml")
    sitemap.raise_for_status()
    urls = list(dict.fromkeys(re.findall(r"<loc>(https://acikders\.tuba\.gov\.tr/ders/[^<\s]+)</loc>", sitemap.text)))[:limit]
    slots = asyncio.Semaphore(2)

    async def course(url):
        async with slots:
            await asyncio.sleep(.3)
            try:
                response = await client.get(url)
            except httpx.HTTPError:
                return None
        if response.status_code != 200:
            return None
        page = response.text
        title = clean_title(_meta(page, "og:title").split(" — ")[0])
        if not title:
            return None
        description = _meta(page, "description")
        author = re.search(r"Yazar[ıi]\s*:\s*((?:(?:Prof|Doç|Dr|Öğr)\.\s*)*[A-ZÇĞİÖŞÜ][\w'’-]+(?:\s+[A-ZÇĞİÖŞÜ][\w'’-]+)?)", description)
        slug = re.search(r"kategori=([a-z0-9-]+)", page)
        pdfs = list(dict.fromkeys(urljoin(url, h) for h in re.findall(r'href="([^"]+?\.pdf)"', page, re.I)))
        pdfs = [p for p in pdfs if urlsplit(p).hostname == "acikders.tuba.gov.tr"][:40]
        text = re.sub(r"^Ders Notlar[ıi]n[ıi]n Yazar[ıi]\s*:\s*", "", description)
        category = TUBA_CATS.get(slug[1] if slug else "", "") or guess(f"{title} {text}")
        return {"id": "tuba:" + url.rsplit("/", 1)[-1], "title": title, "authors": [author[1]] if author else [], "year": "",
                "license": "TÜBA Açık Ders · kullanım şartlarına bakın", "category": category, "source": "TÜBA Açık Ders", "language": "tr",
                "pdf": pdfs[0] if pdfs else "", "parts": pdfs, "url": url, "abstract": text[:1500], "is_oa": True}

    return [x for x in await asyncio.gather(*(course(u) for u in urls)) if x]


HARVEST = {"oapen": _oapen, "doab": _doab, "openstax": _openstax, "otl": _otl, "tuba": _tuba}


# ------------------------------------------------------------------ önbellek ve hasat
def _load(source: str) -> dict:
    try:
        value = json.loads((CACHE / f"{source}.json").read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


async def _harvest(source: str):
    try:
        async with httpx.AsyncClient(timeout=30, headers=UA, follow_redirects=True) as client:
            items = await HARVEST[source](client)
        if items:
            await asyncio.to_thread(atomic_json, CACHE / f"{source}.json", {"at": time.time(), "items": items})
        else:
            raise ValueError("boş hasat")
    except Exception as exc:  # kaynak düşükse eski önbellek kalır; bir saat sonra yeniden denenir
        old = _load(source)
        await asyncio.to_thread(atomic_json, CACHE / f"{source}.json",
                                {"at": time.time() - TTL + 3600, "items": old.get("items", []), "error": type(exc).__name__})


def _refresh(source: str):
    task = TASKS.get(source)
    if task and not task.done():
        return task
    TASKS[source] = asyncio.create_task(_harvest(source))
    return TASKS[source]


async def catalog(wait: float = 12) -> list[dict]:
    """Tüm kaynakların birleşik kitap listesi. Eksik kaynakları en fazla `wait` saniye bekler."""
    pending = []
    for source in HARVEST:
        cached = _load(source)
        if time.time() - cached.get("at", 0) > TTL:
            task = _refresh(source)
            if not cached.get("items"):
                pending.append(task)
    if pending and wait > 0:
        await asyncio.wait(pending, timeout=wait)
    items, seen = [], set()
    for source in HARVEST:
        for item in _load(source).get("items", []):
            key = (item.get("doi") or "").lower() or re.sub(r"\W+", "", item["title"].casefold())
            if key and key not in seen:
                seen.add(key)
                items.append(item)
    return items


def status() -> list[dict]:
    out = []
    for key, spec in SOURCES.items():
        cached = _load(key)
        task = TASKS.get(key)
        out.append({"key": key, **spec, "count": len(cached.get("items", [])), "updating": bool(task and not task.done())})
    return out


def _mix(rows: list[dict]) -> list[dict]:
    """Türkçe önce; sonra kaynaklar sırayla, PDF'i olanlar öne."""
    groups: dict[str, list[dict]] = {}
    for row in sorted(rows, key=lambda r: (r.get("language") != "tr", not r.get("pdf"))):
        groups.setdefault(row["source"], []).append(row)
    out, lists = [], list(groups.values())
    while any(lists):
        for rows_ in lists:
            if rows_:
                out.append(rows_.pop(0))
    return sorted(out, key=lambda r: r.get("language") != "tr")


async def books(cat: str = "genel", q: str = "", limit: int = 120) -> list[dict]:
    pool = await catalog()
    if q:
        words = q.casefold().split()
        pool = [b for b in pool if all(w in f"{b['title']} {' '.join(b.get('authors', []))} {b.get('abstract', '')}".casefold() for w in words)]
    elif cat in CATEGORY_MAP:
        pool = [b for b in pool if b.get("category") == cat]
    return _mix(pool)[:limit]


async def book_text(url):
    # Her yönlendirme tekrar alan adı denetiminden geçer.
    for _ in range(4):
        p = urlsplit(url)
        if p.scheme not in {"http", "https"} or p.hostname not in TEXT_HOSTS or p.username or p.password:
            raise ValueError("Yalnız Gutenberg metin adresleri desteklenir.")
        async with public_client(timeout=15, headers={"User-Agent": "AkademikIz/1.0"}) as client:
            async with client.stream("GET", url, follow_redirects=False) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers.get("location", "")); continue
                response.raise_for_status()
                raw = bytearray()
                async for chunk in response.aiter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 5 * 1024 * 1024:
                        raise ValueError("Kitap metni 5 MB sınırını aşıyor.")
                value = raw.decode("utf-8-sig", "replace")
                if "html" in response.headers.get("content-type", ""):
                    from html.parser import HTMLParser
                    class Text(HTMLParser):
                        def __init__(self):
                            super().__init__(); self.parts = []; self.skip = 0
                        def handle_starttag(self, tag, attrs):
                            if tag in {"script", "style"}: self.skip += 1
                            if tag in {"p", "div", "br", "h1", "h2"}: self.parts.append("\n\n")
                        def handle_endtag(self, tag):
                            if tag in {"script", "style"}: self.skip = max(0, self.skip - 1)
                        def handle_data(self, data):
                            if not self.skip: self.parts.append(data)
                    parser = Text(); parser.feed(value); value = "".join(parser.parts)
                return value
    raise ValueError("Çok fazla yönlendirme.")


async def archive():
    from . import donations
    pool = await catalog()
    by_cat: dict[str, list[dict]] = {}
    for book in pool:
        by_cat.setdefault(book.get("category") if book.get("category") in CATEGORY_MAP else "genel", []).append(book)
    categories = []
    for key, spec in CATEGORY_MAP.items():
        donated = await asyncio.to_thread(donations.list_items, key, "", 120)
        categories.append({"key": key, "name": spec[0], "color": spec[1], "donations": donated,
                           "oa": _mix(by_cat.get(key, []))[:max(0, 120 - len(donated))]})
    categories.append({"key": "new", "name": "Bağışlar — Yeni Gelenler", "color": "#62534d",
                       "donations": await asyncio.to_thread(donations.list_items, "", "", 120), "oa": []})
    return {"categories": categories, "sources": status()}
