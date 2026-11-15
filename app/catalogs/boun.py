"""Boğaziçi Üniversitesi — Kayıt İşleri (registration.boun.edu.tr; klasik ASP, windows-1254).

Boğaziçi'nin HTML tabanlı bir Bologna ders paketi yoktur; herkese açık resmî kaynak dönemlik ders programıdır:
  POST /scripts/schdepsel.asp (semester=YYYY/YYYY-N)  bölüm kodları ve adları
  GET  /scripts/sch.asp?donem=…&kisaadi=…&bolum=…     bölümün o dönem açılan dersleri (kod, ad, kredi, AKTS)
  GET  /scripts/schedule/coursedescription.asp?…      dersin (varsa) öğretim elemanının yüklediği izlence PDF'i

Bu yüzden ders planı "dönem dönem müfredat" değil, bölümün son güz ve bahar dönemlerinde açtığı lisans dersleridir
(5xx ve üstü lisansüstü sayılır, alınmaz); dersler sınıfa göre gruplanır (kodun ilk rakamı). Ders planı iki istekte
gelir (güz + bahar); içerik izlence PDF'inden sezgisel olarak çıkarılır, PDF yüklenmemiş derste içerik yoktur.
"""
from __future__ import annotations

import asyncio
import io
import re
import time
from urllib.parse import parse_qs, quote, urljoin, urlsplit

from . import base

DOMAINS = ("boun.edu.tr", "bogazici.edu.tr")
BASE = "https://registration.boun.edu.tr"
DEPTS = f"{BASE}/scripts/schdepsel.asp"
TERMS = {"1": "Güz", "2": "Bahar"}
# Bölüm kodu → (YÖK'teki Türkçe program adları, fakülte). Site yalnız İngilizce ad verir.
_UNITS = {
    "CMPE": (["Bilgisayar Mühendisliği"], "Mühendislik Fakültesi"), "CHE": (["Kimya Mühendisliği"], "Mühendislik Fakültesi"),
    "CE": (["İnşaat Mühendisliği"], "Mühendislik Fakültesi"), "EE": (["Elektrik-Elektronik Mühendisliği"], "Mühendislik Fakültesi"),
    "IE": (["Endüstri Mühendisliği"], "Mühendislik Fakültesi"), "ME": (["Makine Mühendisliği"], "Mühendislik Fakültesi"),
    "CHEM": (["Kimya"], "Fen-Edebiyat Fakültesi"), "HIST": (["Tarih"], "Fen-Edebiyat Fakültesi"),
    "MATH": (["Matematik"], "Fen-Edebiyat Fakültesi"), "MBG": (["Moleküler Biyoloji ve Genetik"], "Fen-Edebiyat Fakültesi"),
    "PHIL": (["Felsefe"], "Fen-Edebiyat Fakültesi"), "PHYS": (["Fizik"], "Fen-Edebiyat Fakültesi"),
    "PSY": (["Psikoloji"], "Fen-Edebiyat Fakültesi"), "SOC": (["Sosyoloji"], "Fen-Edebiyat Fakültesi"),
    "TLL": (["Türk Dili ve Edebiyatı"], "Fen-Edebiyat Fakültesi"), "LL": (["İngiliz Dili ve Edebiyatı", "Batı Dilleri ve Edebiyatları"], "Fen-Edebiyat Fakültesi"),
    "TR": (["Çeviribilim", "Mütercim-Tercümanlık"], "Fen-Edebiyat Fakültesi"), "LING": (["Dilbilim"], "Fen-Edebiyat Fakültesi"),
    "EC": (["İktisat", "Ekonomi"], "İktisadi ve İdari Bilimler Fakültesi"), "AD": (["İşletme"], "İktisadi ve İdari Bilimler Fakültesi"),
    "POLS": (["Siyaset Bilimi ve Uluslararası İlişkiler"], "İktisadi ve İdari Bilimler Fakültesi"),
    "CET": (["Bilgisayar ve Öğretim Teknolojileri Öğretmenliği"], "Eğitim Fakültesi"),
    "GUID": (["Rehberlik ve Psikolojik Danışmanlık"], "Eğitim Fakültesi"), "FLED": (["İngilizce Öğretmenliği"], "Eğitim Fakültesi"),
    "PRED": (["Okul Öncesi Öğretmenliği"], "Eğitim Fakültesi"),
    "SCED": (["Fen Bilgisi Öğretmenliği", "Fizik Öğretmenliği", "Kimya Öğretmenliği"], "Eğitim Fakültesi"),
    "MAED": (["Matematik Öğretmenliği", "İlköğretim Matematik Öğretmenliği"], "Eğitim Fakültesi"),
    "INTT": (["Uluslararası Ticaret"], "Uygulamalı Bilimler Yüksekokulu"),
    "MIS": (["Yönetim Bilişim Sistemleri"], "Uygulamalı Bilimler Yüksekokulu"),
    "TA": (["Turizm İşletmeciliği"], "Uygulamalı Bilimler Yüksekokulu"), "LAW": (["Hukuk"], "Hukuk Fakültesi"),
}
_CODE = re.compile(r"^([A-ZÇĞİÖŞÜ&]+)\s*(\d[0-9A-Z]{1,3})\.(\d+)")
_DESC = re.compile(r"coursedescription\.asp\?course=([^&\"']+)&(?:amp;)?section=([^&\"']+)&(?:amp;)?term=([^\"']+)")


def _parse_departments(text: str, term: str) -> list[tuple[str, str, str]]:
    """[(bölüm kodu, İngilizce ad, o dönemin ders programı adresi)]"""
    out = []
    for anchor in base.parse(text).xpath("//a[@href]"):
        href = anchor.get("href")
        if "sch.asp?" not in href.lower():
            continue
        query = parse_qs(urlsplit(href).query, encoding="cp1254")
        code = (query.get("kisaadi") or [""])[0].strip()
        name = (query.get("bolum") or [base.txt(anchor)])[0].strip()
        if code:
            out.append((code, name, f"{BASE}/scripts/sch.asp?donem={term}&kisaadi={quote(code, safe='')}"
                                    f"&bolum={quote(name, safe='', encoding='cp1254')}"))
    return out


def _parse_schedule(text: str) -> list[dict]:
    rows = []
    for row in base.parse(text).xpath("//tr[starts-with(@class, 'schtd')]"):
        cells = row.xpath("./td")
        match = _CODE.match(base.txt(cells[0]).upper()) if len(cells) >= 5 else None
        if not match:
            continue
        prefix, number, _section = match.groups()
        from lxml import html as html_tree
        link = _DESC.search(html_tree.tostring(cells[1], encoding="unicode"))
        rows.append({"code": f"{prefix} {number}", "number": number, "name": base.txt(cells[2]),
                     "credit": base.txt(cells[3]), "ects": base.txt(cells[4]),
                     "url": f"{BASE}/scripts/schedule/coursedescription.asp?course={link[1]}&section={link[2]}&term={link[3]}" if link else ""})
    return rows


def _candidate_terms() -> list[str]:
    """Son iki akademik yılın güz ve bahar dönemleri, yeniden eskiye (hangisinin yayımlandığı sitede yoklanır)."""
    now = time.localtime()
    start = now.tm_year if now.tm_mon >= 8 else now.tm_year - 1
    return [f"{year}/{year + 1}-{semester}" for semester in ("1", "2") for year in (start, start - 1)]


async def programs(http) -> list[dict]:
    lists = await asyncio.gather(*(http.text(DEPTS, data={"semester": term}) for term in _candidate_terms()),
                                 return_exceptions=True)
    found: dict[str, dict] = {}
    for term, text in zip(_candidate_terms(), lists):
        if isinstance(text, Exception):
            continue
        for code, name, url in _parse_departments(text, term):
            if code not in _UNITS:
                continue  # lisans programı olmayan birim (enstitü, ortak dersler)
            names, faculty = _UNITS[code]
            row = found.setdefault(code, {"name": names[0], "faculty": faculty, "aliases": [*names[1:]], "code": code,
                                          "url": f"{BASE}/scripts/sch.asp?kisaadi={quote(code, safe='')}", "terms": {}})
            if "THESIS" not in name.upper():
                if name.title() not in row["aliases"]:
                    row["aliases"].append(name.title())
                # Her yarıyıl için en yeni yıl önce gelir; courses() ders bulduğu ilk yılı kullanır.
                row["terms"].setdefault(term.rsplit("-", 1)[-1], []).append(url)
    return list(found.values())


async def courses(http, program) -> list[dict]:
    async def term_rows(urls):
        for url in urls:  # en yeni yıl; o yıl henüz yayımlanmadıysa bir önceki
            try:
                rows = _parse_schedule(await http.text(url, encoding="windows-1254"))
            except Exception:  # noqa: BLE001
                rows = []
            if rows:
                return rows
        return []

    semesters = [s for s in TERMS if program.get("terms", {}).get(s)]
    results = await asyncio.gather(*(term_rows(program["terms"][s]) for s in semesters))
    merged: dict[str, dict] = {}
    for semester, rows in zip(semesters, results):
        for row in rows:
            if row["number"][0] not in "1234":  # 5xx ve üstü lisansüstü
                continue
            entry = merged.setdefault(row["code"], {**row, "terms": []})
            if TERMS[semester] not in entry["terms"]:
                entry["terms"].append(TERMS[semester])
            entry["url"] = entry["url"] or row["url"]
            entry["ects"] = entry["ects"] or row["ects"]
    return [base.course(code, row["name"], f"{row['number'][0]}. sınıf dersleri", ects=row["ects"], credit=row["credit"],
                        kind="/".join(row["terms"]), url=row["url"], source=program["url"])
            for code, row in sorted(merged.items(), key=lambda kv: (kv[1]["number"][0], kv[0]))]


# --- izlence PDF'i sezgileri
_HEAD = re.compile(r"^\s*(?:\d+[.)]\s*)?((?:course\s+)?(?:catalog(?:ue)?\s+)?description|course\s+content|(?:course\s+)?objectives?|"
                   r"aims?(?:\s+of\s+the\s+course)?|course\s+(?:summary|overview)|overview|dersin\s+amacı|"
                   r"ders(?:in)?\s+(?:içeriği|tanımı)|amaç|içerik)\s*[:\-–]?\s*(.*)$", re.I)
_STOP = re.compile(r"^\s*(?:\d+[.)]\s*)?(text\s*books?|references?|readings?|required|recommended|grading|evaluation|assessment|"
                   r"prerequisites?|instructors?|teaching\s+assist\w*|assistants?|office|schedule|weekly|week\b|course\s+outline|"
                   r"outline|tentative|polic(?:y|ies)|attendance|exams?|midterms?|learning\s+outcomes|outcomes|materials?|"
                   r"kaynak\w*|değerlendirme|ön\s*koşul\w*|hafta\w*|lecture\s+hours|class\s+hours|web\s*(?:site|page)|e-?mail|"
                   r"credits?|ects|important\s+note)", re.I)
_WEEK_A = re.compile(r"^\s*(?:week|hafta|wk\.?)\s*[#:\-]?\s*(\d{1,2})\b\s*[:.\-–)]*\s*(.*)$", re.I)
_WEEK_B = re.compile(r"^\s*(\d{1,2})\s*[.)]?\s*(?:week|hafta)\b\s*[:.\-–)]*\s*(.*)$", re.I)
_NUMBERED = re.compile(r"^\s*(\d{1,2})\s*[.)\-–:]?\s+(\S.*)$")


def _parse_syllabus(text: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Serbest biçimli izlence metninden ([(başlık, metin)], [(hafta, konu)])."""
    rows = [line.strip() for line in text.splitlines() if line.strip()]
    parts, index = [], 0
    while index < len(rows) and len(parts) < 2:
        match = _HEAD.match(rows[index])
        if not match or not (len(rows[index]) <= 90 or ":" in rows[index][:40]):
            index += 1
            continue
        heading, buffer = match[1].lower(), [match[2].strip()] if match[2].strip() else []
        index += 1
        while index < len(rows) and sum(map(len, buffer)) < 1500 and len(buffer) < 25:
            if _STOP.match(rows[index]) or _HEAD.match(rows[index]) or _WEEK_A.match(rows[index]):
                break
            buffer.append(rows[index])
            index += 1
        body = base.txt(" ".join(buffer))
        label = "Dersin amacı" if re.search(r"objective|aim|amaç|amacı", heading) else "Dersin içeriği"
        if len(body) >= 30 and label not in [p[0] for p in parts]:
            parts.append((label, body[:2000]))
    weeks: dict[int, str] = {}
    for position, line in enumerate(rows):
        match = _WEEK_A.match(line) or _WEEK_B.match(line)
        if not match:
            continue
        topic = match[2].strip()
        if not topic and position + 1 < len(rows) and not (_WEEK_A.match(rows[position + 1]) or _WEEK_B.match(rows[position + 1])):
            topic = rows[position + 1]
        if 1 <= int(match[1]) <= 16 and topic:
            weeks.setdefault(int(match[1]), topic)
    if len(weeks) < 4:
        # Yedek: "Week | Topic" başlıklı tablo; satırlar 1, 2, 3… ile başlar.
        weeks = {}
        for position, line in enumerate(rows):
            if len(line) > 70 or not re.search(r"\b(week|hafta)\b", line, re.I):
                continue
            candidate, expected = {}, 1
            for follower in rows[position + 1: position + 90]:
                match = _NUMBERED.match(follower)
                if match and int(match[1]) == expected:
                    candidate[expected] = match[2]
                    expected += 1
                    if expected > 16:
                        break
            if len(candidate) > len(weeks):
                weeks = candidate
    return parts, [(str(n), topic) for n, topic in sorted(weeks.items())] if len(weeks) >= 4 else []


def _pdf_link(text: str, url: str) -> str:
    for anchor in base.parse(text).xpath("//a[@href]"):
        if anchor.get("href").lower().split("?")[0].endswith(".pdf"):
            return urljoin(url, anchor.get("href"))
    return ""


def _pdf_text(raw: bytes) -> str:
    from pypdf import PdfReader
    return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(raw)).pages[:10])


async def detail(http, url) -> dict | None:
    if "coursedescription.asp" not in url:
        return None
    pdf = _pdf_link(await http.text(url, encoding="windows-1254"), url)
    if not pdf:
        return None
    text = await asyncio.to_thread(_pdf_text, await http.raw(pdf, limit=8_000_000))
    parts, weeks = _parse_syllabus(text)
    return base.detail(url, "", parts=parts, weeks=weeks)
