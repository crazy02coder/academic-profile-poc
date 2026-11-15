"""Orta Doğu Teknik Üniversitesi — Academic Catalog (catalog.metu.edu.tr).

Yapı (sayfalar ISO-8859-9, yalnız İngilizce):
  fac_inst.php?fac_inst=<fakülte>                 fakültenin bölümleri (program.php?fac_prog=<bölüm> bağlantıları)
  program.php?fac_prog=<bölüm>                    lisans müfredatı: her yarıyıl ayrı tablo ("First Semester" …)
  prog_courses.php?prog=<bölüm>                   bölümün verdiği bütün dersler (seçmeliler ve lisansüstü dahil)
  course.php?prog=<bölüm>&course_code=<7 hane>    ders: künye + "Course Content"; amaç ve öğrenme çıktıları
                                                  odtusyllabus.metu.edu.tr/get.php?package=… iframe'lerinde (UTF-8)
"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import urljoin

from . import base

DOMAINS = ("metu.edu.tr",)
PARALLEL = 6
BASE = "https://catalog.metu.edu.tr/"
ENCODING = "iso-8859-9"

# Lisans programı olan fakülteler (fac_inst kimliği → Türkçe ad). Enstitüler, Yabancı Diller Yüksekokulu (600),
# Rektörlüğe bağlı bölümler (650) ve Kuzey Kıbrıs Kampusu (995-998, ayrı kurum) alınmaz.
FACULTIES = {
    100: "Mimarlık Fakültesi",
    200: "Fen Edebiyat Fakültesi",
    300: "İktisadi ve İdari Bilimler Fakültesi",
    400: "Eğitim Fakültesi",
    500: "Mühendislik Fakültesi",
}

# Site yalnız İngilizce ad verir: fac_prog kimliği → Türkçe adlar (ilk ad YÖK'teki program adı).
TURKISH = {
    120: ["Mimarlık"], 121: ["Şehir ve Bölge Planlama"], 125: ["Endüstriyel Tasarım", "Endüstri Ürünleri Tasarımı"],
    238: ["Biyoloji"], 219: ["Moleküler Biyoloji ve Genetik"], 234: ["Kimya"], 240: ["Tarih"], 236: ["Matematik"],
    241: ["Felsefe"], 230: ["Fizik"], 233: ["Psikoloji"], 232: ["Sosyoloji"], 246: ["İstatistik"],
    312: ["İşletme"], 311: ["İktisat"], 314: ["Uluslararası İlişkiler"], 310: ["Siyaset Bilimi ve Kamu Yönetimi"],
    316: ["İşletme (UOLP-SUNY Binghamton)"], 315: ["Küresel ve Uluslararası İlişkiler (UOLP-SUNY Binghamton)"],
    411: ["Okul Öncesi Öğretmenliği", "Okul Öncesi Eğitimi"], 412: ["Fen Bilgisi Öğretmenliği", "Fen Bilgisi Eğitimi"],
    413: ["İlköğretim Matematik Öğretmenliği", "İlköğretim Matematik Eğitimi"],
    421: ["Fizik Öğretmenliği", "Fizik Eğitimi"], 422: ["Kimya Öğretmenliği", "Kimya Eğitimi"],
    423: ["Matematik Öğretmenliği", "Matematik Eğitimi"], 450: ["İngilizce Öğretmenliği", "Yabancı Diller Eğitimi"],
    451: ["İngilizce Öğretmenliği (UOLP-SUNY New Paltz)"],
    430: ["Bilgisayar ve Öğretim Teknolojileri Öğretmenliği", "Bilgisayar ve Öğretim Teknolojileri Eğitimi"],
    454: ["Eğitim Bilimleri"], 453: ["Beden Eğitimi ve Spor Öğretmenliği", "Beden Eğitimi ve Spor"],
    572: ["Havacılık ve Uzay Mühendisliği"], 563: ["Kimya Mühendisliği"], 562: ["İnşaat Mühendisliği"],
    571: ["Bilgisayar Mühendisliği"], 575: ["Bilgisayar Mühendisliği (Türkiye-Azerbaycan Üniversitesi)"],
    567: ["Elektrik-Elektronik Mühendisliği"], 561: ["Mühendislik Bilimleri"], 560: ["Çevre Mühendisliği"],
    573: ["Gıda Mühendisliği"], 564: ["Jeoloji Mühendisliği"], 568: ["Endüstri Mühendisliği"],
    569: ["Makina Mühendisliği"], 570: ["Metalurji ve Malzeme Mühendisliği"], 565: ["Maden Mühendisliği"],
    566: ["Petrol ve Doğal Gaz Mühendisliği"],
}

_ORDINALS = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth"]
# Yarıyıl başlığı düz metindir ve hemen ardından o yarıyılın tablosu gelir.
_SEMESTER = re.compile(r"(%s)\s+Semester\s*<table[^>]*>(.*?)</table>" % "|".join(_ORDINALS), re.I | re.S)
# Ders künyesindeki etiketler (iki nokta üst üstesiz) → arayüzde gösterilecek Türkçe karşılığı.
_LABELS = {
    "METU Credit (Theoretical-Laboratory hours/week)": "Kredi (teori-lab. saat/hafta)", "ECTS Credit": "AKTS",
    "Department": "Bölüm", "Language of Instruction": "Öğretim dili", "Level of Study": "Düzey",
    "Course Coordinator": "Koordinatör", "Offered Semester": "Verildiği dönem",
}


def _parse_programs(text: str, faculty: str) -> list[dict]:
    """Fakülte sayfasındaki bölümler; `faculty` Türkçe fakülte adı."""
    rows = []
    for link in base.parse(text).xpath('//a[contains(@href, "program.php?fac_prog=")]'):
        match = re.search(r"fac_prog=(\d+)", link.get("href"))
        name = base.txt(link)
        if not match or not name:
            continue
        prog = int(match[1])
        rows.append({"name": name, "faculty": faculty, "url": f"{BASE}program.php?fac_prog={prog}",
                     "aliases": TURKISH.get(prog, []), "prog": prog})
    return rows


def _rows(table_html: str, url: str):
    """Ders tablosunun satırları: (kod, ad, kredi, akts, ders adresi, kümeden_seçmeli_mi). Kodu olmayan satır
    ("TECHNICAL ELECTIVE" gibi seçmeli yuvası) kod='' ile gelir."""
    in_set = False  # "Any 1 of the following set .." satırından alt çizgiye kadar: seçenekli dersler
    for tr in base.parse(f"<table>{table_html}</table>").xpath("//tr"):
        cells = tr.xpath("./td")
        if len(cells) == 1:
            if re.search(r"of the following set", base.txt(cells[0]), re.I):
                in_set = True
            elif "border-top" in (cells[0].get("style") or ""):
                in_set = False
            continue
        if len(cells) < 6 or cells[0].xpath(".//b"):
            continue
        code, name = base.txt(cells[0]), base.txt(cells[1])
        href = (cells[0].xpath(".//a/@href") or [""])[0]
        if not code and not name:
            continue
        yield code, name, base.txt(cells[2]), base.txt(cells[5]), urljoin(url, href) if href else "", in_set


def _parse_plan(text: str, url: str) -> list[dict]:
    """program.php: yarıyıl tabloları → ders kayıtları."""
    items = []
    for match in _SEMESTER.finditer(text):
        label = base.period(_ORDINALS.index(match[1].lower()) + 1)
        for code, name, credit, ects, link, in_set in _rows(match[2], url):
            if code:
                kind = "Seçmeli (seçenekli ders kümesi)" if in_set else "Zorunlu"
                items.append(base.course(code, name, label, ects=ects, credit=credit, kind=kind, url=link, source=url))
            else:  # seçmeli yuvası: "TECHNICAL ELECTIVE", "FREE ELECTIVE" …
                items.append(base.course("", name, label, ects=ects, kind="Seçmeli", source=url))
    return items


def _parse_department_courses(text: str, url: str, skip=()) -> list[dict]:
    """prog_courses.php: bölümün müfredatta adı geçmeyen lisans dersleri (seçmeli havuzu). ODTÜ'de ders numarası
    5 ve üstü rakamla başlıyorsa (CENG5xx, CENG7xx) lisansüstüdür; onlar alınmaz."""
    start = text.find("<table", max(text.find("Courses given by"), 0))
    end = text.find("</table>", start)
    if start < 0 or end < 0:
        return []
    items, seen = [], set(skip)
    for code, name, credit, ects, link, _ in _rows(text[start:end], url):
        digits = re.search(r"\d+", code)
        if not code or code in seen or not digits or digits[0][0] not in "1234":
            continue
        seen.add(code)
        items.append(base.course(code, name, base.period(elective=True), ects=ects, credit=credit, kind="Bölüm dersi",
                                 url=link, source=url))
    return items


def _parse_syllabus(text: str) -> tuple[str, list[str]]:
    """odtusyllabus iframe'i → (satır satır metin, madde listesi)."""
    nodes = base.parse(text).xpath('//span[contains(@class, "cke_rich_text")]')
    if not nodes:
        return "", []
    return base.lines(nodes[0]), [base.txt(li) for li in nodes[0].xpath(".//li") if base.txt(li)]


def _frames(text: str) -> dict:
    """course.php içindeki iframe adresleri: {"courseObjectives": …, "courseLearningOutcomes": …}."""
    tree = base.parse(text)
    return {frame.get("id"): frame.get("src") for frame in tree.xpath("//iframe[@id and @src]")}


def _parse_detail(text: str, url: str, objectives: str = "", outcomes: str = "") -> dict | None:
    """course.php (+ isteğe bağlı amaç ve öğrenme çıktısı iframe gövdeleri) → ders içeriği."""
    tree = base.parse(text)
    title = base.txt((tree.xpath('//div[@id="navbar"]/following::h2[1]') or [None])[0])
    info = []
    for row in tree.xpath('//table[contains(@class, "course")]//tr[td[@class="course_php"]]'):
        cells = row.xpath("./td")
        label = _LABELS.get(base.txt(cells[0]).rstrip(":").strip())
        if label and len(cells) > 1:
            info.append((label, base.txt(cells[1])))
    content = ""
    for heading in tree.xpath("//h3"):
        if base.txt(heading).lower() == "course content":
            content = base.txt(heading.tail or "")
    aim, _ = _parse_syllabus(objectives) if objectives else ("", [])
    listed_text, listed = _parse_syllabus(outcomes) if outcomes else ("", [])
    if not listed and listed_text:  # madde imi kullanılmamış: her satır bir çıktı
        listed = [row for row in listed_text.split("\n") if not row.rstrip().endswith(":")]
    return base.detail(url, title, info=info, parts=[("Dersin amacı", aim), ("Dersin içeriği", content)], outcomes=listed)


async def programs(http) -> list[dict]:
    """Beş fakülte sayfası paralel okunur (5 istek)."""
    ids = list(FACULTIES)
    pages = await asyncio.gather(*(http.text(f"{BASE}fac_inst.php?fac_inst={fid}", encoding=ENCODING) for fid in ids))
    return [row for fid, page in zip(ids, pages) for row in _parse_programs(page, FACULTIES[fid])]


async def courses(http, program) -> list[dict]:
    """Müfredat + bölümün ders listesi (2 paralel istek). Bölüm listesi okunamazsa yalnız müfredat döner."""
    prog = program.get("prog") or re.search(r"fac_prog=(\d+)", program.get("url") or "")[1]
    plan_url, list_url = f"{BASE}program.php?fac_prog={prog}", f"{BASE}prog_courses.php?prog={prog}"
    plan, listing = await asyncio.gather(http.text(plan_url, encoding=ENCODING), http.text(list_url, encoding=ENCODING),
                                         return_exceptions=True)
    if isinstance(plan, BaseException):
        raise plan
    items = _parse_plan(plan, plan_url)
    if items and isinstance(listing, str):
        items += _parse_department_courses(listing, list_url, skip={item["code"] for item in items})
    return items


async def detail(http, url) -> dict | None:
    """Ders sayfası + amaç ve öğrenme çıktısı iframe'leri (1 + 2 paralel istek)."""
    text = await http.text(url, encoding=ENCODING)
    frames = _frames(text)

    async def frame(name: str) -> str:
        src = frames.get(name)
        if not src:
            return ""
        try:
            return await http.text(src)
        except Exception:  # noqa: BLE001 — izlence yoksa künye ve içerik yine gösterilir
            return ""

    objectives, outcomes = await asyncio.gather(frame("courseObjectives"), frame("courseLearningOutcomes"))
    return _parse_detail(text, url, objectives, outcomes)
