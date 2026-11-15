"""TOBB Ekonomi ve Teknoloji Üniversitesi — bölüm sayfaları + ABYS ders bilgi paketi (etu.edu.tr).

Yapı:
  www.etu.edu.tr/tr/akademik                          → fakülte kutuları altında bölümler (/tr/bolum/<kısa ad>)
  www.etu.edu.tr/tr/bolum/<kısa ad>/ders-mufredati    → lisans müfredatı: yıl / GÜZ-BAHAR-YAZ dönemi başlıkları altında
                                                        ders tabloları (elle düzenlenen sayfa; bölümden bölüme tek büyük
                                                        tablo ya da dönem başına tablo). Ders kodu ABYS sayfasına bağlıdır.
  www.etu.edu.tr/tr/bolum/<kısa ad>/ders-icerikleri   → bölümün zorunlu/seçmeli derslerinin kısa içerikleri (seçmeli havuzu)
  abys.etu.edu.tr/public/lesson.jsp?program=&lesson=  → dersin bilgi formu (tanım, amaç, çıktılar, haftalık çizelge,
                                                        değerlendirme, iş yükü)
TOBB ETÜ'de yılda üç dönem vardır: dönem numarası (yıl-1)*3 + (güz 1, bahar 2, yaz 3); ortak eğitim dönemleri dahil 11 dönem.
"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import urljoin, urlsplit

from . import base

DOMAINS = ("etu.edu.tr",)
SITE = "https://www.etu.edu.tr"
_TERMS = {"güz": 1, "bahar": 2, "yaz": 3}
_CODE = r"[A-ZÇĞİÖŞÜ]{2,5}\s?\d{2,3}[A-ZÇĞİÖŞÜ]?(?:-[A-ZÇĞİÖŞÜ])?"  # "BİL 113", "FİZ 101L", "İKT 103-İ"
_HEADS = {"h1", "h2", "h3", "h4", "h5", "p", "strong", "b", "td", "th"}


def _lower(text: str) -> str:
    return text.replace("İ", "i").replace("I", "ı").lower()


def _content(tree):
    """Sayfanın elle yazılan içerik alanı (menü ve haber kutuları dışarıda kalır)."""
    return tree.xpath("//div[contains(@class,'wysi-icerik')]")


def _parse_programs(text: str) -> list[dict]:
    out = []
    for box in base.parse(text).xpath("//li[contains(@class,'fakulte-listesi__item')][.//h2]"):
        faculty = base.txt(box.xpath("string(.//h2)"))
        if "fakülte" not in faculty.lower():
            continue  # enstitüler ve Yabancı Diller Bölümü
        for link in box.xpath(".//a[starts-with(@href,'/tr/bolum/')]"):
            name = re.sub(r"\bMüh\.", "Mühendisliği", base.txt(link))
            if not name or "yandal" in name.lower():
                continue
            name = re.sub(r"\s+Fakültesi$", "", name)  # "Tıp Fakültesi" → "Tıp"
            slug = link.get("href").rstrip("/").rsplit("/", 1)[-1]
            out.append({"name": name, "faculty": faculty, "slug": slug, "url": f"{SITE}/tr/bolum/{slug}/ders-mufredati"})
    return out


def _parse_plan(text: str, url: str) -> list[dict]:
    """Müfredat sayfasındaki ilk (güncel) müfredat. Sütunlar "Ders Kodu | Ders Adı | Kredi Sayısı | AKTS" başlık
    satırından okunur (bazı bölümlerde AKTS sütunu yoktur)."""
    out, seen = [], set()
    year, term = 0, 0
    credit_at, ects_at = 2, 3
    for root in _content(base.parse(text)):
        for node in root.iter():
            if node.tag in _HEADS:
                head = _lower(base.txt(node))[:40]
                if (found := re.match(r"(\d)\s*\.\s*yıl", head)):
                    if int(found[1]) < year:
                        return out  # yıl başa döndü: eski girişliler için ikinci müfredat başlıyor
                    year, term = int(found[1]), 0
                elif (found := re.match(r"(güz|bahar|yaz)\s+dönemi", head)):
                    term = _TERMS[found[1]]
                continue
            if node.tag != "tr":
                continue
            cells = [base.txt(cell) for cell in node.xpath("./td|./th")]
            heads = [_lower(cell) for cell in cells]
            if heads and heads[0].startswith("ders kodu"):
                credit_at = next((i for i, cell in enumerate(heads) if "kredi" in cell), -1)
                ects_at = next((i for i, cell in enumerate(heads) if "akts" in cell), -1)
                continue
            if len(cells) < 3 or not cells[0] or heads[0].startswith("toplam"):
                continue
            credit = cells[credit_at] if 0 <= credit_at < len(cells) else ""
            ects = cells[ects_at] if 0 <= ects_at < len(cells) else ""
            if base.number(credit) is None and base.number(ects) is None:
                continue
            code, name = cells[0], cells[1].rstrip("* ")
            period = base.period((year - 1) * 3 + term) if year and term else ""
            if not name or (code, period) in seen:
                continue
            seen.add((code, period))
            link = next((href for href in node.xpath(".//a/@href") if "lesson.jsp" in href), "")
            slot = not link and "seçmeli" in name.lower()  # "Bölüm Seçmeli Dersi I": seçmeli yeri, belirli bir ders değil
            out.append(base.course(code, name, period, ects=ects, credit=credit,
                                   kind="Seçmeli" if slot else "Zorunlu" if link else "", url=link, source=url))
    return out


def _parse_contents(text: str) -> list[dict]:
    """Ders içerikleri sayfası: {"code", "name", "credit", "ects", "text", "section"}. İki yazım görülür:
    tabloda [kod | ad | önkoşul | "3 Kredi"] satırı + altında tek hücreli içerik satırı; ya da
    <p><strong>KOD - Ad (kredi / AKTS / dil)</strong><br>içerik</p>."""
    out, section, last = [], "", None
    for root in _content(base.parse(text)):
        for node in root.iter():
            if node.tag == "tr":
                cells = [base.txt(cell) for cell in node.xpath("./td|./th")]
                if len(cells) >= 2 and re.fullmatch(_CODE, cells[0]) and cells[1]:
                    last = {"code": cells[0], "name": cells[1], "credit": (re.findall(r"\d+", cells[-1]) or [""])[0] if len(cells) > 2 else "",
                            "ects": None, "text": "", "section": section}
                    out.append(last)
                elif len(cells) == 1 and last is not None and not last["text"] and len(cells[0]) > 30:
                    last["text"] = cells[0]
                continue
            if node.tag not in {"h2", "h3", "h4", "p"}:
                continue
            whole, strong = base.txt(node), base.txt(node.xpath("string(.//strong[1])"))
            found = re.match(rf"({_CODE})\s*[-–]\s*(.+?)\s*\(\s*(\d+)\s*/\s*(\d+)[^)]*\)$", strong)
            if found:
                last = {"code": found[1], "name": found[2], "credit": found[3], "ects": found[4],
                        "text": whole[len(strong):].strip(), "section": section}
                out.append(last)
            elif whole and len(whole) < 80 and (node.tag != "p" or whole == strong) and not node.xpath("ancestor::table"):
                section, last = whole, None  # ara başlık: "Bölüm Seçmeli Dersleri", "Servis Dersleri"…
    return out


def _labelled(tree) -> dict:
    """Bilgi formundaki başlık satırı (kalın etiketler) → hemen altındaki değer satırı."""
    out = {}
    for row in tree.xpath("//div[contains(@class,'row')][div/b]"):
        nxt = row.getnext()
        values = nxt.xpath("./div") if nxt is not None and nxt.tag == "div" else []
        for label, value in zip(row.xpath("./div/b"), values):
            text = base.lines(value) or base.txt(value)
            out[base.txt(label)] = "" if text.strip() in {"", "-"} else text
    return out


def _parse_detail(text: str, url: str) -> dict | None:
    tree = base.parse(text)
    code, name = base.txt(tree.xpath("string(//h1)")), base.txt(tree.xpath("string(//p[contains(@class,'lead')])"))
    field = _labelled(tree)
    if not code or not field:
        return None
    outcomes = [re.sub(r"^\d+\s*[.)]\s*", "", row) for row in field.get("Ders Çıktıları", "").split("\n")]
    weeks = [(found[1], found[2]) for row in field.get("Referans Ders Çizelgesi", "").split("\n")
             if (found := re.match(r"(\d+)\s*\.\s*Hafta\s*:\s*(.+)", row, re.I))]
    assessment, hours, ects = [], "", ""
    for table in tree.xpath("//table"):
        title = base.txt(table.xpath("string(.//tr[1])"))
        rows = [[base.txt(cell) for cell in tr.xpath("./td|./th")] for tr in table.xpath(".//tr")]
        if "Değerlendirme" in title:
            assessment = [(row[0], row[2], row[1]) for row in rows if len(row) == 3 and row[0]]
        elif "İş Yükü" in title:
            for row in rows:
                if row and row[0] == "Toplam İş Yükü":
                    hours = row[-1]
                elif row and row[0] == "Dersin AKTS Kredisi":
                    ects = row[-1]
    info = [("Dersi veren", field.get("Dersi Veren Fakülte \\ Bölüm", "")), ("Kredi", field.get("Kredi", "")),
            ("AKTS", field.get("AKTS", "")), ("Ders türü", field.get("Ders Türü", "")),
            ("Öğretim dili", field.get("Öğretim Dili", "")), ("Ön koşullar", field.get("Ön Koşullar", "").replace("\n", " "))]
    parts = [("Dersin amacı", field.get("Ders Amaçları", "")), ("Dersin içeriği", field.get("Ders Tanımı", "")),
             ("Kaynaklar", field.get("Ders Kitapları ve/veya Kaynaklar", ""))]
    if not weeks:  # çizelge "N. Hafta:" biçiminde değilse metin olarak gösterilir
        parts.append(("Ders çizelgesi", field.get("Referans Ders Çizelgesi", "")))
    return base.detail(url, f"{code} {name}", info=info, parts=parts, weeks=weeks, outcomes=outcomes,
                       assessment=assessment, workload={"hours": hours, "ects": ects} if hours else None)


async def programs(http) -> list[dict]:
    return _parse_programs(await http.text(f"{SITE}/tr/akademik"))


async def courses(http, program) -> list[dict]:
    """Müfredat ve ders içerikleri sayfaları birlikte istenir (2 istek). Müfredat dönemlik planı, içerik sayfası
    plana girmeyen seçmeli dersleri (içerikleri kayda gömülü) verir."""
    base_url = f"{SITE}/tr/bolum/{program['slug']}/"
    plan_url, contents_url = base_url + "ders-mufredati", base_url + "ders-icerikleri"
    plan_text, contents_text = await asyncio.gather(http.text(plan_url), http.text(contents_url), return_exceptions=True)
    if isinstance(plan_text, BaseException):
        raise plan_text
    items = _parse_plan(plan_text, plan_url)
    if not items:
        # Bazı bölümlerde müfredat başka adla yayımlanır (Hukuk: "ders-mufredati-ingilizce"); bölüm menüsünden bulunur.
        for href in base.parse(plan_text).xpath("//a[contains(@href,'/ders-mufredati')]/@href"):
            other = urljoin(plan_url, href)
            if "/tr/bolum/" in urlsplit(other).path and other.rstrip("/") != plan_url:
                items = _parse_plan(await http.text(other), other)
                if items:
                    break
    if isinstance(contents_text, BaseException):
        return items
    known = {item["code"].replace(" ", "") for item in items}
    for row in _parse_contents(contents_text):
        key = row["code"].replace(" ", "")
        if key in known or "seçmeli" not in _lower(row["section"]):
            continue
        known.add(key)
        items.append(base.course(row["code"], row["name"], base.period(elective=True), ects=row["ects"], credit=row["credit"],
                                 kind="Seçmeli", source=contents_url, content=row["text"]))
    return items


async def detail(http, url) -> dict | None:
    return _parse_detail(await http.text(url), url)
