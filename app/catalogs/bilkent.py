"""Bilkent Üniversitesi — Online Academic Catalog (catalog.bilkent.edu.tr) + STARS ders izlencesi (stars.bilkent.edu.tr).

  catalog…/current/general/faculties.html   fakülte listesi (faculty/fNN.html; Hukuk doğrudan dep/d45.html)
  catalog…/current/faculty/fNN.html         fakültenin bölümleri (dep/dNN.html)
  catalog…/current/dep/dNN.html             bölüm sayfası: "UNDERGRADUATE PROGRAM" başlığı altında yıl (FIRST YEAR…) ve
                                            dönem (Autumn/Spring Semester) başlıklı ders tabloları; ardından lisansüstü
  stars…/syllabus/view/<BÖLÜM>/<NO>/        dersin herkese açık izlencesi: tanım, değerlendirme, öğrenme çıktıları,
                                            haftalık konular, iş yükü (ders yoksa "… is not a course.")

Site yalnız İngilizce ad verir; Türkçe program/fakülte adları aşağıdaki tablolardan gelir (İngilizce ad `aliases`ta).
Ders planı tek istekte gelir (bölüm sayfası); ders içeriği STARS izlencesinden tembel okunur.
"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import urljoin

from . import base

DOMAINS = ("bilkent.edu.tr",)
CATALOG = "https://catalog.bilkent.edu.tr/current/"
FACULTIES = CATALOG + "general/faculties.html"
SYLLABUS = "https://stars.bilkent.edu.tr/syllabus/view/{}/{}/"

# Katalogdaki fakülte kodu (faculty/fNN.html) → Türkçe ad. f90 "Interdisciplinary Programs" yalnız lisansüstüdür.
_FACULTY = {
    "f05": "Fen Fakültesi", "f10": "Mühendislik Fakültesi", "f17": "Uygulamalı Bilimler Fakültesi",
    "f20": "İnsani Bilimler ve Edebiyat Fakültesi", "f30": "İktisadi, İdari ve Sosyal Bilimler Fakültesi",
    "f35": "İşletme Fakültesi", "f38": "Eğitim Fakültesi", "f40": "Müzik ve Sahne Sanatları Fakültesi",
    "f70": "Güzel Sanatlar, Tasarım ve Mimarlık Fakültesi",
}
# Bölüm kodu (dep/dNN.html) → Türkçe program adı ve YÖK'te geçen öteki adlar. Tabloda olmayan bölüm İngilizce adıyla kalır.
_TURKISH = {
    "d01": ["Fizik"], "d02": ["Kimya"], "d03": ["Matematik"], "d04": ["Moleküler Biyoloji ve Genetik"],
    "d11": ["Bilgisayar Mühendisliği"], "d12": ["Elektrik-Elektronik Mühendisliği"], "d13": ["Endüstri Mühendisliği"],
    "d16": ["Makine Mühendisliği"], "d18": ["Bilgi Sistemleri ve Teknolojileri", "Bilgisayar Teknolojisi ve Bilişim Sistemleri"],
    "d19": ["Turizm ve Otel İşletmeciliği"], "d21": ["İngiliz Dili ve Edebiyatı"], "d22": ["Amerikan Kültürü ve Edebiyatı"],
    "d23": ["Arkeoloji"], "d25": ["Felsefe"], "d26": ["Türk Edebiyatı", "Türk Dili ve Edebiyatı"], "d31": ["İşletme"],
    "d32": ["İktisat"], "d33": ["Uluslararası İlişkiler"], "d34": ["Siyaset Bilimi ve Kamu Yönetimi"], "d35": ["Tarih"],
    "d41": ["Müzik"], "d42": ["Sahne Sanatları", "Tiyatro"], "d45": ["Hukuk"], "d70": ["Mimarlık"],
    "d71": ["İç Mimarlık ve Çevre Tasarımı"], "d72": ["Grafik Tasarım", "Grafik Tasarımı"], "d74": ["Güzel Sanatlar"],
    "d75": ["Kentsel Tasarım ve Peyzaj Mimarlığı", "Kentsel Tasarım ve Peyzaj Mimarisi"],
    "d77": ["İletişim ve Tasarım", "İletişim ve Tasarımı"],
    "d89": ["Mütercim ve Tercümanlık", "Mütercim-Tercümanlık", "İngilizce-Fransızca-Türkçe Mütercim ve Tercümanlık"],
    "d92": ["Psikoloji"],
}
# Derece programı olmayan birimler: müzik hazırlık okulu, yabancı diller, kültür-uygarlık (CCI) ve Türkçe birimleri.
_SERVICE = {"d07", "d17", "d28", "d95"}
_YEAR = {"FIRST": 1, "SECOND": 2, "THIRD": 3, "FOURTH": 4, "FIFTH": 5}
_DEPT = re.compile(r"dep/(d\d+)\.html", re.I)
_FAC = re.compile(r"faculty/(f\d+)\.html", re.I)


def _parse_faculties(text: str) -> list[tuple[str, str]]:
    """faculties.html → [(fakülte kodu ya da doğrudan bölüm kodu, adres)]."""
    out = []
    for link in base.parse(text).xpath("//a[@href]"):
        href = link.get("href")
        code = _FAC.search(href) or _DEPT.search(href)
        if code:
            out.append((code[1].lower(), urljoin(FACULTIES, href)))
    return out


def _program(code: str, english: str, faculty: str) -> dict:
    names = _TURKISH.get(code, [])
    return {"name": names[0] if names else english, "faculty": faculty, "url": f"{CATALOG}dep/{code}.html",
            "aliases": [english, *names[1:]] if names else []}


def _parse_faculty(text: str, code: str) -> list[dict]:
    """Fakülte sayfasındaki bölüm bağlantıları (dep/dNN.html)."""
    tree = base.parse(text)
    title = base.txt(next(iter(tree.xpath("//h2[not(ancestor::div[@class='header'])]")), None))
    faculty = _FACULTY.get(code) or title.title()
    out = []
    for link in tree.xpath("//a[@href]"):
        dept = _DEPT.search(link.get("href"))
        name = base.txt(link)
        if dept and name and dept[1].lower() not in _SERVICE:
            out.append(_program(dept[1].lower(), name, faculty))
    return out


async def programs(http) -> list[dict]:
    """Fakülte listesi + her fakültenin sayfası (paralel, ~10 istek). Lisansüstü-yalnız bölümler de listede kalır;
    onların sayfasında lisans ders planı olmadığından courses() boş döner."""
    entries = _parse_faculties(await http.text(FACULTIES))
    out = [_program("d45", "Law", "Hukuk Fakültesi") for code, _ in entries if code == "d45"]
    pages = [(code, url) for code, url in entries if code.startswith("f") and code != "f90"]
    texts = await asyncio.gather(*(http.text(url) for _, url in pages), return_exceptions=True)
    for (code, _), text in zip(pages, texts):
        if isinstance(text, str):
            out.extend(_parse_faculty(text, code))
    return list({row["url"]: row for row in out}.values())


def _syllabus(code: str) -> str:
    """'CS 101' → STARS izlence adresi; kod bu biçimde değilse ''."""
    match = re.fullmatch(r"([A-Za-z]{2,6})\s*(\d{2,4}[A-Za-z]?)", code.strip())
    return SYLLABUS.format(match[1].upper(), match[2]) if match else ""


def _parse_plan(text: str, url: str) -> list[dict]:
    """Bölüm sayfasının lisans ders planı. Başlıklar belge sırasıyla okunur: H2 "UNDERGRADUATE PROGRAM" açar,
    "GRADUATE/MINOR PROGRAM", "Master…", "Doctor…" kapatır; H4 yıl ve dönem verir. Sütunlar: kod, ad, ders saati,
    diğer saat, kredi, AKTS. Kodsuz satırlar ("Technical Electives (3)") seçmeli yer tutucusudur: dönemin yükünü
    gösterdiği için kodsuz ve içerik adressiz olarak alınır (seçmeli havuzunun ders listesi katalogda yoktur)."""
    tree = base.parse(text)
    items, seen = [], set()
    active, year, term, years = True, 0, 0, set()
    for node in tree.xpath("//h2|//h4|//tr[td/a[contains(@href, '/course/')]]"):
        if node.tag in {"h2", "h4"}:
            title = base.txt(node).upper()
            if node.tag == "h2" and "UNDERGRADUATE" in title:
                active, year, term = True, 0, 0
            elif "UNDERGRADUATE" not in title and re.search(r"GRADUATE|MINOR|MASTER|DOCTOR|PH\.?D", title):
                active = False
            elif title.split(" ")[0] in _YEAR and "YEAR" in title:
                year, term = _YEAR[title.split(" ")[0]], 0
                if year in years:
                    active = False  # aynı sayfada ikinci bir lisans planı (başka program) başlıyor: yalnız ilki alınır
                years.add(year)
            elif "SEMESTER" in title:
                term = 1 if re.search(r"AUTUMN|FALL", title) else 2 if "SPRING" in title else 0
            continue
        if not (active and year and term):
            continue
        cells = node.xpath("./td")
        if len(cells) < 6:
            continue
        code, name = base.txt(cells[0]), base.txt(cells[1])
        period = base.period(year=year, term=term)
        if not name or (code or name, period) in seen:
            continue
        seen.add((code or name, period))
        credit = base.txt(cells[4])
        items.append(base.course(code, name, period, ects=base.txt(cells[5]), credit="" if credit == "-" else credit,
                                 kind="" if code else "Seçmeli", url=_syllabus(code), source=url))
    return items


async def courses(http, program) -> list[dict]:
    return _parse_plan(await http.text(program["url"]), program["url"])


def _rows(table) -> list[list[str]]:
    return [[base.txt(td) for td in tr.xpath("./td")] for tr in table.xpath(".//tr[td]")]


def _parse_detail(text: str, url: str) -> dict | None:
    """STARS izlencesi: her alan bir <td> içinde <strong>Etiket:</strong> ile başlar; değer aynı hücrenin kalanıdır
    (düz metin, liste ya da 'bordered' tablo). Üstteki künye alanları (Department, Credits…) <div> içindedir."""
    tree = base.parse(text)
    box = next(iter(tree.xpath("//div[contains(@class, 'syllabusContainer')]")), None)
    if box is None:
        return None
    title = re.sub(r"^Syllabus of\s+", "", base.txt(next(iter(box.xpath(".//h1")), None)))
    if not title or "is not a course" in title:
        return None
    fields = {}
    for strong in box.xpath(".//strong"):
        holder = strong.getparent()
        label = base.txt(strong).rstrip(": ")
        if label and holder is not None:
            fields.setdefault(label, holder)

    def value(label: str) -> str:
        holder = fields.get(label)
        if holder is None:
            return ""
        body = base.lines(holder).split("\n")
        body[0] = body[0][len(base.txt(holder.xpath("./strong")[0])):] if body else ""
        result = "\n".join(row.strip() for row in body if row.strip() and row.strip() != "[download]")
        return "" if result in {"-", "None"} else result

    def table(label: str) -> list[list[str]]:
        holder = fields.get(label)
        return _rows(holder.xpath(".//table")[0]) if holder is not None and holder.xpath(".//table") else []

    info = [("Bölüm", value("Department")), ("Kredi", value("Credits")), ("Koordinatör", value("Course Coordinator")),
            ("Dönem", value("Semester")), ("Ders saati", value("Contact Hours")), ("Ön koşul", value("Prerequisite(s)")),
            ("Ders türü", value("Type of Course")), ("Öğretim yöntemi", value("Teaching Methods"))]
    parts = [("Dersin içeriği", value("Catalog Description")), ("Kaynaklar", value("Textbook and Other Required Material")),
             ("Final sınavına girme koşulu", value("Minimum Requirements to Qualify for the Final Exam")),
             ("Üretken yapay zekâ politikası", value("GenAI Policy"))]
    # Değerlendirme tablosu: sıra, tür, etiket, adet, toplam katkı (%)
    assessment = [(row[2] or row[1], row[4], row[3]) for row in table("Assessment Methods") if len(row) >= 5]
    outcomes = [row[0] for row in table("Course Learning Outcomes") if row]
    holder = fields.get("Weekly Syllabus")
    weeks = [(n, base.txt(li)) for n, li in enumerate(holder.xpath(".//ol/li"), 1)] if holder is not None else []
    workload = {}
    for row in table("ECTS - Workload Table"):
        if len(row) == 2 and row[0].startswith("Total Workload:"):
            workload["hours"] = row[1]
        elif len(row) == 2 and row[0].startswith("ECTS Credits"):
            workload["ects"] = row[1]
    return base.detail(url, title.replace(" - ", " ", 1), info=info, parts=parts, weeks=weeks, outcomes=outcomes,
                       assessment=assessment, workload=workload or None)


async def detail(http, url) -> dict | None:
    return _parse_detail(await http.text(url), url)
