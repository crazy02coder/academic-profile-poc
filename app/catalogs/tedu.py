"""TED Üniversitesi — bölüm siteleri (Drupal, <bölüm>.tedu.edu.tr) ve ders izlenceleri (www.tedu.edu.tr).

Yapı: www.tedu.edu.tr/akademik fakülte → bölüm sitelerini listeler. Bölüm sitesinin "Öğretim Programı" sayfası boş
bir blok taşır; tarayıcı bloğu, sayfadaki drupalSettings.ajaxBlocks kaydını /program-ajax/custom adresine POST ederek
doldurur (önce /session/token'dan anonim CSRF jetonu alır). Yanıt sekiz yarıyıl tablosunun HTML'idir. Seçmeli
havuzları <bölüm>/courses/<havuz id> sayfalarıdır; dersin izlencesi www.tedu.edu.tr/<ders> sayfasıdır (İngilizce).
"""
from __future__ import annotations

import asyncio
import json
import re
from urllib.parse import urljoin, urlsplit

from . import base

DOMAINS = ("tedu.edu.tr",)
PARALLEL = 2  # site bağlantıları sık kesiyor
UNITS = "https://www.tedu.edu.tr/akademik"

# Eğitim Fakültesi siteleri anabilim dalı adıyla anılır; YÖK'teki program adları farklıdır.
_YOK = {
    "Rehberlik ve Psikolojik Danışmanlık": ["Guidance and Psychological Counseling"],
    "Matematik Eğitimi": ["İlköğretim Matematik Öğretmenliği", "Elementary Mathematics Education"],
    "Okul Öncesi Eğitimi": ["Okul Öncesi Öğretmenliği", "Early Childhood Education"],
    "Sınıf Eğitimi": ["Sınıf Öğretmenliği", "Primary Education"],
    "İngiliz Dili Eğitimi": ["İngilizce Öğretmenliği", "English Language Education"],
}


async def programs(http) -> list[dict]:
    return _parse_programs(await http.text(UNITS))


def _parse_programs(text: str) -> list[dict]:
    """Akademik birimler sayfası: <h3> fakülte, hemen ardındaki <ul> bölüm siteleri. Enstitü ve "Birim"ler alınmaz."""
    tree = base.parse(text)
    rows = []
    for head in tree.xpath("//blockquote//h3[a]"):
        faculty = base.txt(head)
        box = head.getnext()
        if not faculty.endswith("Fakültesi") or box is None or box.tag != "ul":
            continue
        for link in box.xpath("./li/a[@href]"):
            label = base.txt(link)
            if not re.search(r"(Bölümü|Anabilim Dalı)$", label):
                continue  # "Temel Bilimler Birimi" gibi program olmayan birimler
            # "Temel Eğitim Bölümü Okul Öncesi Eğitimi Anabilim Dalı" → "Okul Öncesi Eğitimi"
            name = re.sub(r"\s*(Anabilim Dalı|Bölümü)$", "", label)
            if label.endswith("Anabilim Dalı") and "Bölümü" in name:
                name = name.split("Bölümü", 1)[1]
            name = name.strip(" -")
            row = {"name": name, "faculty": faculty, "url": link.get("href").rstrip("/") + "/"}
            if name in _YOK:
                row["aliases"] = _YOK[name]
            rows.append(row)
    return rows


def _plan_page(text: str, home: str) -> str:
    """Bölüm ana sayfasındaki "Öğretim Programı" bağlantısı. Birden çok müfredat yılı varsa ("Öğretim Programı
    (2022)") yılsız olan, o da yoksa en yeni yıl seçilir."""
    best, rank = "", -1
    for link in base.parse(text).xpath("//a[@href]"):
        label = base.txt(link)
        if not label.startswith("Öğretim Programı"):
            continue
        year = re.search(r"\((\d{4})", label)
        score = 9999 if label == "Öğretim Programı" else int(year[1]) if year else 0
        if score > rank:
            best, rank = urljoin(home, link.get("href")), score
    return best


def _block(text: str) -> dict | None:
    """Sayfadaki drupalSettings'ten ders planı bloğunun kaydı: {"plugin_id": "tedu_program_block", "block_id",
    "bolum_id", "year"} — tarayıcının POST ettiği gövde budur."""
    match = re.search(r'<script type="application/json" data-drupal-selector="drupal-settings-json">(.*?)</script>', text, re.S)
    if not match:
        return None
    try:
        blocks = json.loads(match[1]).get("ajaxBlocks") or {}
    except ValueError:
        return None
    for block in blocks.values():
        if isinstance(block, dict) and block.get("plugin_id") == "tedu_program_block":
            return {key: str(value) for key, value in block.items()}
    return None


async def courses(http, program) -> list[dict]:
    home = program["url"]
    page = _plan_page(await http.text(home), home)
    if not page:
        return []
    block = _block(await http.text(page))
    if not block:
        return []
    origin = "{0.scheme}://{0.netloc}".format(urlsplit(page))
    # Anonim CSRF jetonu oturum çerezine bağlıdır; önbellekten okunmaz (ttl=0).
    token = (await http.text(origin + "/session/token", ttl=0)).strip()
    reply = await http.json(origin + "/program-ajax/custom?_wrapper_format=drupal_ajax",
                            data={**block, "_drupal_ajax": "1"},
                            headers={"X-CSRF-Token": token, "X-Requested-With": "XMLHttpRequest"})
    html = "".join(cmd.get("data") or "" for cmd in reply if isinstance(cmd, dict) and cmd.get("command") == "insert")
    items, pools = _parse_plan(html, page)
    pages = await asyncio.gather(*(http.text(url) for url in pools), return_exceptions=True)
    seen = {item["code"] for item in items}
    for url, text in zip(pools, pages):
        if isinstance(text, str):
            for item in _parse_pool(text, url):
                if item["code"] not in seen:
                    seen.add(item["code"])
                    items.append(item)
    return items


def _parse_plan(html: str, url: str) -> tuple[list[dict], list[str]]:
    """XHR yanıtındaki table.program-table'lar: başlık "Yarıyıl N", sütunlar Kod, Ders İsmi, T, P, L, K, AKTS.
    Kod bağlantısı /courses/<id> ise satır bir seçmeli havuzudur ("Bölüm Seçmeli Dersleri"); havuz adresleri
    ayrıca döner. "FREE" (serbest seçmeli) havuzu üniversitenin tüm derslerini içerdiğinden alınmaz."""
    items, pools = [], []
    for table in base.parse(html).xpath('//table[contains(@class,"program-table")]'):
        semester = base.number(base.txt((table.xpath("./thead/tr[1]/th") or [None])[0]))
        period = base.period(semester)
        for tr in table.xpath("./tbody/tr[not(contains(@class,'summary'))]"):
            cells = [base.txt(td) for td in tr.xpath("./td")]
            if len(cells) < 7 or not cells[0]:
                continue
            code, name, t, p, lab, credit, ects = cells[:7]
            href = (tr.xpath("./td[1]//a/@href") or [""])[0]
            hours = f"{credit} ({t}+{p}+{lab})"
            if re.search(r"/courses/\d+", href):
                if code != "FREE" and href not in pools:
                    pools.append(href)
                items.append(base.course(code, name, period, ects=ects, credit=hours, kind="Seçmeli", source=href))
            else:
                items.append(base.course(code, name, period, ects=ects, credit=hours, url=href, source=url))
    return items, pools


def _parse_pool(text: str, url: str) -> list[dict]:
    """Seçmeli havuzu sayfası: tek tablo; ilk hücre "CMPE 252 : C Programlama" bağlantısı, sonra T, P, L, K, AKTS."""
    out = []
    for tr in base.parse(text).xpath('//div[contains(@class,"course-profiles")]//table/tbody/tr'):
        cells = [base.txt(td) for td in tr.xpath("./td")]
        if len(cells) < 6 or ":" not in cells[0]:
            continue
        code, name = (part.strip() for part in cells[0].split(":", 1))
        href = (tr.xpath("./td[1]//a/@href") or [""])[0]
        out.append(base.course(code, name, base.period(elective=True), ects=cells[5],
                               credit=f"{cells[4]} ({cells[1]}+{cells[2]}+{cells[3]})", kind="Seçmeli", url=href, source=url))
    return out


async def detail(http, url) -> dict | None:
    return _parse_detail(await http.text(url), url)


# İzlence sayfasındaki etiketler (İngilizce) → ders kartındaki karşılıkları.
_INFO = {"Credit Hours/ ECTS Credits": "Kredi / AKTS", "Level": "Düzey", "Year of Study": "Yıl", "Semester": "Dönem",
         "Type of Course": "Tür", "Mode of Delivery": "Öğretim biçimi", "Language of Instruction": "Dil",
         "Pre-requisite / Co-requisite": "Ön koşul", "Course Coordinator": "Koordinatör"}
_PARTS = {"Catalog Description": "Dersin içeriği", "Course Objectives": "Dersin amacı"}


def _parse_detail(text: str, url: str) -> dict | None:
    """article.sap-course-page içindeki her section.row: solda <strong> etiket, sağda değer."""
    fields = {}
    for row in base.parse(text).xpath('//article[contains(@class,"sap-course-page")]//section[contains(@class,"row")]'):
        cols = row.xpath('./div[contains(@class,"col-md-6")]')
        if len(cols) == 2:
            fields[base.txt(cols[0]).rstrip(": ")] = cols[1]
    if not fields:
        return None
    get = lambda key: base.txt(fields.get(key))  # noqa: E731
    title = " ".join(x for x in (get("Course Code & Number"), get("Course Title")) if x)
    info = [(label, get(key)) for key, label in _INFO.items()]
    parts = [(label, base.lines(fields[key])) for key, label in _PARTS.items() if key in fields]
    outcomes = []
    node = fields.get("Course Learning Outcomes")
    if node is not None:
        outcomes = [base.txt(li) for li in node.xpath(".//li")]
        if not outcomes:
            # Liste yoksa satırlar; "Upon successful completion…" giriş cümlesi çıktı değildir.
            rows = base.lines(node).split("\n")
            outcomes = [row for row in rows if row and not re.match(r"(?i)upon suc", row)]
    for key, node in fields.items():
        if key not in _INFO and key not in _PARTS and key not in {"Course Code & Number", "Course Title", "Course Learning Outcomes"}:
            parts.append((key, base.lines(node)))
    return base.detail(url, title, info=info, parts=parts, outcomes=outcomes)
