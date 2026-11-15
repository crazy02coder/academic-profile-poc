"""Koç Üniversitesi — fakülte siteleri (WordPress, <fakülte>.ku.edu.tr).

Yapı: her fakülte sitesinin menüsünde bölümlerin "Ders Planı" ve "Ders Tanımları" sayfaları vardır. Ders planı
sayfası sekiz dönemi tek sayfada, dönem başına bir tablo olarak verir (Ders Kodu, Ders Adı, Tipi, Kredisi, Koşullar).
Ders tanımları üç biçimdedir: aranabilir kart listesi (?ss=<kod> tek dersi döndürür), Mühendislik'te tür başına alt
sayfalar (zorunlu-alan, alan-secmeli…), Hemşirelik'te tek sayfada açılır başlıklar. Tıp Fakültesi'nin ders planı
tablosu yoktur. Kredi Koç kredisidir; sayfalarda AKTS yer almaz.
"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import quote_plus, unquote, urljoin, urlsplit

from . import base

DOMAINS = ("ku.edu.tr",)

# site → (fakülte, tek programlı fakültede program adı, ders tanımı biçimi)
#   "search": kart listesi, ?ss=<kod> ile tek ders;  "pages": tanımlar düz sayfa(lar)da, ders başlığından bulunur
SITES = {
    "https://case.ku.edu.tr/": ("İktisadi ve İdari Bilimler Fakültesi", "", "search"),
    "https://eng.ku.edu.tr/": ("Mühendislik Fakültesi", "", "pages"),
    "https://science.ku.edu.tr/": ("Fen Fakültesi", "", "search"),
    "https://cssh.ku.edu.tr/": ("İnsani Bilimler ve Edebiyat Fakültesi", "", "search"),
    "https://law.ku.edu.tr/": ("Hukuk Fakültesi", "Hukuk", "search"),
    "https://nursing.ku.edu.tr/": ("Hemşirelik Fakültesi", "Hemşirelik", "pages"),
}
# Sitedeki bölüm adı → YÖK'teki / İngilizce karşılıkları.
_ALIASES = {
    "Ekonomi": ["İktisat", "Economics"],
    "İşletme": ["Business Administration"],
    "Uluslararası İlişkiler": ["International Relations"],
    "Bilgisayar Mühendisliği": ["Computer Engineering"],
    "Elektrik ve Elektronik Mühendisliği": ["Elektrik-Elektronik Mühendisliği", "Electrical and Electronics Engineering"],
    "Endüstri Mühendisliği": ["Industrial Engineering"],
    "Kimya ve Biyoloji Mühendisliği": ["Kimya-Biyoloji Mühendisliği", "Chemical and Biological Engineering"],
    "Makine Mühendisliği": ["Mechanical Engineering"],
    "Fizik": ["Physics"], "Kimya": ["Chemistry"], "Matematik": ["Mathematics"],
    "Moleküler Biyoloji ve Genetik": ["Molecular Biology and Genetics"],
    "Arkeoloji ve Sanat Tarihi": ["Archaeology and History of Art"],
    "Felsefe": ["Philosophy"], "Psikoloji": ["Psychology"], "Sosyoloji": ["Sociology"], "Tarih": ["History"],
    "Karşılaştırmalı Edebiyat": ["İngiliz Dili ve Karşılaştırmalı Edebiyat", "Comparative Literature"],
    "Medya ve Görsel Sanatlar": ["Media and Visual Arts"],
    "Hukuk": ["Law", "Hukuk Fakültesi"], "Hemşirelik": ["Nursing", "Hemşirelik Fakültesi"],
}
_CODE = re.compile(r"^[A-Z]{2,5} \d{3}[A-Z]?$")
_PLAN = re.compile(r"((?:lisans|lisans-programi)/)?ders-(?:plani|programi)/$")


async def programs(http) -> list[dict]:
    pages = await asyncio.gather(*(http.text(site) for site in SITES), return_exceptions=True)
    rows = []
    for site, text in zip(SITES, pages):
        if isinstance(text, str):
            rows.extend(_parse_programs(text, site))
    return rows


def _parse_programs(text: str, site: str) -> list[dict]:
    """Fakülte ana sayfasının menüsü: her "Ders Planı" bağlantısı bir lisans programıdır. Bölüm adı, bölümün kök
    adresine giden menü bağlantısının metnidir; ders tanımları aynı klasördeki ders-tanimlari/ sayfasıdır."""
    faculty, single, style = SITES[site]
    tree = base.parse(text)
    labels: dict[str, str] = {}
    for link in tree.xpath("//a[@href]"):
        title = link.xpath('.//span[contains(@class,"h3-item-title")]')  # Mühendislik menüsünde ad + açıklama birlikte
        label = base.txt(title[0] if title else link)
        href = urljoin(site, link.get("href"))
        if label and label not in {"Hakkında", "Hakkımızda"} and (href not in labels or len(label) < len(labels[href])):
            labels[href] = label
    rows, seen = [], set()
    for link in tree.xpath("//a[@href]"):
        url = urljoin(site, link.get("href"))
        if url in seen or not url.startswith(site) or not _PLAN.search(url):
            continue
        seen.add(url)
        root = _PLAN.sub("", url)
        name = single or labels.get(root, "")
        if not name:
            continue
        rows.append({"name": name, "faculty": faculty, "url": url, "aliases": _ALIASES.get(name, []),
                     "courses_url": re.sub(r"ders-(?:plani|programi)/$", "ders-tanimlari/", url), "style": style})
    return rows


async def courses(http, program) -> list[dict]:
    url = program["url"]
    return _parse_plan(await http.text(url), url, program.get("courses_url") or "", program.get("style") or "")


def _parse_plan(text: str, url: str, courses_url: str = "", style: str = "") -> list[dict]:
    """#accordionCurriculum içindeki her accordion-item bir dönemdir ("3. Dönem"). Seçmeli yuvalarında kod yerine
    havuz adı ("ALAN", "SEÇMELİ", "SOSC") yazar ve ders adı boştur; bunlar türüyle adlandırılır, içerik adresi almaz."""
    out = []
    for item in base.parse(text).xpath('//div[@id="accordionCurriculum"]//div[contains(@class,"accordion-item")]'):
        heading = base.txt((item.xpath('.//button[contains(@class,"accordion-button")]') or [None])[0])
        period = base.period(base.number(heading))
        for tr in item.xpath(".//table/tbody/tr"):
            cells = tr.xpath("./td")
            if len(cells) < 4:
                continue
            slot = cells[0].xpath('.//span[contains(@class,"me-2")]')  # havuz satırı: kod + açıklama balonu
            code = base.txt(slot[0] if slot else cells[0])
            name, kind, credit = base.txt(cells[1]), base.txt(cells[2]), base.txt(cells[3])
            if not code:
                continue
            link = ""
            if _CODE.match(code) and courses_url:
                link = f"{courses_url}?ss={quote_plus(code)}" if style == "search" else f"{courses_url}#{code.replace(' ', '-')}"
            out.append(base.course(code, name or kind or "Seçmeli", period, credit=credit, kind=kind, url=link, source=url))
    return out


async def detail(http, url) -> dict | None:
    parts = urlsplit(url)
    if parts.query.startswith("ss="):
        return _parse_card(await http.text(url), url)
    page, code = url.split("#")[0], unquote(parts.fragment).replace("-", " ")
    text = await http.text(page)
    found = _parse_detail(text, url, code)
    if found is None:
        # Mühendislik: tanımlar tür başına alt sayfalardadır (zorunlu-alan, alan-secmeli, ortak-cekirdek, cift-anadal).
        subs = [urljoin(page, h) for h in base.parse(text).xpath('//a[contains(@class,"elementor-cta__button")]/@href')]
        subs = [s for s in dict.fromkeys(subs) if s.startswith(page) and s != page]
        for sub in await asyncio.gather(*(http.text(s) for s in subs), return_exceptions=True):
            if isinstance(sub, str) and (found := _parse_detail(sub, url, code)) is not None:
                break
    return found


def _parse_card(text: str, url: str) -> dict | None:
    """Arama sonucu kartı: h4 ders kodu, açılır başlıkta ders adı, p.course-description tanım, <small>'larda
    "CASE - BUSAD" (fakülte - bölüm), düzey ve "Kredisi:3"."""
    want = unquote(urlsplit(url).query[3:]).replace("+", " ").strip()
    for card in base.parse(text).xpath('//div[contains(@class,"equal-height")][.//p[contains(@class,"course-description")]]'):
        code = base.txt((card.xpath('.//h4') or [None])[0])
        if code != want:
            continue
        name = base.txt((card.xpath('.//button[contains(@class,"accordion-button")]') or [None])[0])
        body = base.lines(card.xpath('.//p[contains(@class,"course-description")]')[0])
        info = []
        for small in (base.txt(s) for s in card.xpath(".//small")):
            if small.startswith("Kredisi"):
                info.append(("Kredi", small.split(":", 1)[-1]))
            elif " - " in small:
                info.append(("Birim", small))
            elif small:
                info.append(("Düzey" if small in {"Lisans", "Yüksek Lisans", "Doktora"} else "Koşul", small))
        return base.detail(url, f"{code} {name}", info=info, parts=[("Dersin içeriği", body)])
    return None


def _spaced(code: str) -> str:
    """"COMP100" → "COMP 100" (ders planındaki yazımla aynı)."""
    return code if " " in code else re.sub(r"(\d)", r" \1", code, count=1)


def _blocks(text: str) -> dict[str, dict]:
    """Düz tanım sayfasındaki dersler: kod → {"name", "info", "text"}.
    Mühendislik: art arda başlıklar ("COMP 100 – Ad", "Kredi: 3", "Ön koşul: …") ve ardından metin kutusu.
    Hemşirelik: açılır başlık "NURS 101 / AD", içinde tanım ve "Kredi: 3"."""
    tree, out = base.parse(text), {}
    head = re.compile(r"^([A-Z]{2,5} ?\d{3}[A-Z]?)\s*[–—/-]\s*(.+)$")
    for item in tree.xpath('//div[contains(@class,"elementor-toggle-item")]'):
        match = head.match(base.txt((item.xpath('.//a[contains(@class,"elementor-toggle-title")]') or [None])[0]))
        if not match:
            continue
        body = base.lines((item.xpath('.//div[contains(@class,"elementor-tab-content")]') or [None])[0])
        credit = re.search(r"Kredi:\s*([\d.,]+)", body)
        out[_spaced(match[1])] = {"name": match[2], "info": [("Kredi", credit[1])] if credit else [],
                         "text": re.sub(r"\s*Kredi:\s*[\d.,]+\s*$", "", body).strip()}
    current = None
    for node in tree.xpath('//h2[contains(@class,"elementor-heading-title")]'
                           '|//div[contains(@class,"elementor-widget-text-editor")]'):
        if node.tag == "h2":
            label = base.txt(node)
            if match := head.match(label):
                current = out.setdefault(_spaced(match[1]), {"name": match[2], "info": [], "text": ""})
            elif current is not None and ":" in label:
                key, value = (part.strip() for part in label.split(":", 1))
                if value and value not in {"-", "–"}:
                    current["info"].append((key, value))
        elif current is not None and not current["text"]:
            current["text"] = base.lines(node)
    return out


def _parse_detail(text: str, url: str, code: str) -> dict | None:
    block = _blocks(text).get(code)
    if not block or not block["text"]:
        return None
    return base.detail(url, f"{code} {block['name']}", info=block["info"], parts=[("Dersin içeriği", block["text"])])
