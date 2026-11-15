"""Karadeniz Teknik Üniversitesi — Ders Bilgi Paketi (katalog.ktu.edu.tr/DersBilgiPaketi).

Yapı:
  www.ktu.edu.tr/tr/katalog                       → tüm programlar; "Lisans" sekmesinde fakülte → bölüm bağlantıları (pid)
  …/generalinfo.aspx?pid=<pid>&lang=1             → program sayfası (bağlantı olarak verilir)
  …/semester.aspx?pid=<pid>&lang=1&sid=<yıl*10>   → bir yılın dersleri (Güz + Bahar, seçmeli havuzlarıyla); menüde diğer yıllar
  …/course.aspx?pid=<pid>&lang=1&dbid=<id>        → dersin içerik sayfası (amaç, içerik, haftalar, kazanımlar, ölçme)
Ders planı yıl sayısı kadar istekte gelir (4 yıllık programda 4; ilki menüyü verir, kalanı paralel).
"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import urljoin

from . import base

DOMAINS = ("ktu.edu.tr",)
LIST = "https://www.ktu.edu.tr/tr/katalog"
ROOT = "https://katalog.ktu.edu.tr/DersBilgiPaketi/"

_LOWER = {"ve", "ile"}


def _text(body: bytes) -> str:
    """Sayfalar UTF-8'dir ama liste sayfasında tek tük bozuk bayt bulunur; base.decode bu durumda bütün sayfayı
    windows-1254 sayıp Türkçe harfleri bozardı, o yüzden bozuk bayt yerine � konur."""
    return body.decode("utf-8", errors="replace")


def _title(value: str) -> str:
    """'İKTİSADİ VE İDARİ BİLİMLER' → 'İktisadi ve İdari Bilimler' (Türkçe büyük/küçük harf kuralıyla)."""
    out = []
    for n, word in enumerate(value.split()):
        low = word.replace("İ", "i").replace("I", "ı").lower()
        if n and low in _LOWER:
            out.append(low)
            continue
        # Kelime içindeki ayraçlardan sonra da büyük harf: "Elektrik-Elektronik", "Kaynakları/Teknolojileri".
        out.append(re.sub(r"(^|[-/(.])([^\W\d_])", lambda m: m[1] + {"i": "İ", "ı": "I"}.get(m[2], m[2].upper()), low))
    return " ".join(out)


def _parse_programs(text: str) -> list[dict]:
    """"Lisans" sekmesi: fakülte başlığı (div.fw-bold) altında 'BÖLÜM ADI BÖLÜMÜ / PROGRAM - %30 İngilizce' bağlantıları.
    Program adı çoğunlukla boştur (bölümün tek programı); doluysa ve bölümden farklıysa program adı esas alınır."""
    tree = base.parse(text)
    # Sekme düğmesinin hedefi (#v-pills-messages) sabit kabul edilmez; "Lisans" yazan düğmeden bulunur.
    target = tree.xpath('//button[@data-bs-toggle="pill"][normalize-space()="Lisans"]/@data-bs-target')
    pane = tree.xpath(f'//div[@id="{target[0].lstrip("#")}"]') if target else []
    out = []
    for block in pane[0].xpath('.//li[contains(@class, "list-group-item")]') if pane else []:
        faculty = _title(base.txt((block.xpath('.//div[contains(@class, "fw-bold")]') or [None])[0]))
        for link in block.xpath('.//a[contains(@href, "generalinfo.aspx")]'):
            pid = re.search(r"[?&]pid=(\d+)", link.get("href"))
            unit, _, rest = base.txt(link).partition("/")
            if not pid or not unit.strip():
                continue
            # "- %100 İngilizce", "- %30 İngilizce", "- %100 Rusça": öğretim dili eki.
            lang = re.search(r"-\s*%\s*(\d+)\s+(\S+)\s*$", rest)
            program = _title(rest[:lang.start()] if lang else rest)
            unit = _title(re.sub(r"(\s+BÖLÜMÜ)+\s*$", "", unit.strip()))
            name, aliases = (program, [unit]) if program and base.fold(program) != base.fold(unit) else (unit, [])
            if name == "Genel Tıp":  # YÖK'teki ad "Tıp"
                name, aliases = "Tıp", ["Genel Tıp"]
            suffix = f" ({lang[2]})" if lang and lang[1] == "100" else f" (%{lang[1]} {lang[2]})" if lang else ""
            row = {"name": name + suffix, "faculty": faculty, "pid": pid[1], "url": f"{ROOT}generalinfo.aspx?pid={pid[1]}&lang=1"}
            if aliases:
                row["aliases"] = [alias + suffix for alias in aliases]
            out.append(row)
    return out


def _years(text: str, pid: str) -> list[int]:
    """Menüdeki yıl bağlantıları: sid=10 → 1. yıl, sid=20 → 2. yıl…"""
    found = {int(sid) // 10 for sid in re.findall(rf"semester\.aspx\?pid={pid}&(?:amp;)?lang=1&(?:amp;)?sid=(\d+)", text)}
    return sorted(year for year in found if 1 <= year <= 7)


def _tail_group(name: str) -> str:
    """Adın sonundaki dengeli parantezin içi: 'Ağ Güvenliği(Teknik(bölüm) Seçmeli)' → 'Teknik(bölüm) Seçmeli'."""
    if not name.endswith(")"):
        return ""
    depth = 0
    for at in range(len(name) - 1, -1, -1):
        depth += (name[at] == ")") - (name[at] == "(")
        if depth == 0:
            return name[at + 1:-1] if at else ""
    return ""


def _parse_plan(text: str, url: str, year: int) -> list[dict]:
    """Bir yılın tablosu (#bilgehan): 'Güz Dönemi' / 'Bahar Dönemi' başlık satırları, altında zorunlu dersler ve kodsuz
    seçmeli yuvaları ('Teknik Seçmeli - I'); 'Seçmeli Dersler' satırından sonra o dönemin havuzu gelir, ders adının
    sonunda yuvanın adı parantez içindedir: 'Derin Öğrenme(Teknik Seçmeli (3-4-5))'."""
    out, seen = [], set()
    when, pool, slots = "", False, []
    for row in base.parse(text).xpath('//table[@id="bilgehan"]//tr'):
        cells = [base.txt(td) for td in row.xpath("./td")]
        if len(cells) == 1:
            head = cells[0]
            if "Dönemi" in head:  # "Güz ve Bahar Dönemi" (yıllık dersler) yılın ilk dönemine yazılır
                when, pool, slots = base.period(year=year, term=2 if head.startswith("Bahar") else 1), False, []
            elif head.startswith("Seçmeli"):
                pool = True
            continue
        if len(cells) < 6 or cells[0] == "Kodu" or not cells[1]:
            continue
        code, name, ects, hours, kind, lang = cells[:6]
        href = (row.xpath("./td[1]//a/@href") or [""])[0]
        link = urljoin(url, href) if code and re.search(r"dbid=\d", href) else ""
        if pool:
            group = _tail_group(name)
            if group and (group in slots or "seçmeli" in group.lower()):
                name, kind = name[: -len(group) - 2].strip(), f"{kind} · {group}"
            key, place = code or name, base.period(elective=True)
        else:
            if not code:
                slots.append(name)
            key, place = (code or name, when), when
        if key in seen:
            continue
        seen.add(key)
        kind = " · ".join(x for x in (kind, lang) if x)
        out.append(base.course(code, name, place, ects=ects, credit=hours if re.search(r"\d", hours) else None, kind=kind,
                               url=link, source=url))
    return out


_INFO = {"Yıl / Yarıyıl": "Dönem", "Yazılım Şekli": "Ders türü", "Ön Koşul": "Ön koşul", "Eğitim Sistemi": "Eğitim sistemi",
         "Dersin Süresi": "Süre", "Öğretim Üyesi": "Öğretim üyesi", "Diğer Öğretim Üyesi": "Diğer öğretim üyesi",
         "Öğretim Dili": "Öğretim dili"}
_SECTIONS = {"Dersin Amacı:": "aim", "Ders İçeriği": "content", "Öğrenim Kazanımları": "outcomes",
             "Haftalık Detaylı Ders Planı": "weeks", "Ders Kitabı / Malzemesi": "books", "İlave Kaynak": "books",
             "Ölçme Yöntemi": "marks", "Öğrenci Çalışma Yükü": "load"}


def _parse_detail(text: str, url: str) -> dict | None:
    """Ders sayfası art arda gelen table.sample tablolarıdır: ilk tablo başlık (kod, ad, D+U+L, AKTS) ve künye,
    sonrakiler bölüm başlığı satırı + içerik satırları. Satırlar tek akış olarak okunur."""
    rows = [[base.txt(td) for td in tr.xpath("./td")] for tr in base.parse(text).xpath('//table[@class="sample"]//tr')]
    rows = [row for row in rows if any(row)]
    if not rows or len(rows[0]) < 2:
        return None
    code, name = rows[0][0], rows[0][1]
    ects = base._num(re.sub(r"^\D*", "", rows[0][-1])) if "AKTS" in rows[0][-1] else ""
    info, parts, weeks, outcomes, marks, books = [], [], [], [], [], []
    hours, section = "", ""
    for cells in rows[1:]:
        head = cells[0]
        if head in _SECTIONS:
            section = _SECTIONS[head]
            continue
        if section == "" and head in _INFO and len(cells) > 1:
            info.append((_INFO[head], cells[1]))
        elif section == "aim" and len(cells) == 1:
            parts.append(("Dersin amacı", head))
        elif section == "content" and len(cells) == 1:
            parts.append(("Dersin içeriği", head))
        elif section == "outcomes" and head.startswith("ÖK") and len(cells) > 1:
            outcomes.append(cells[1])
        elif section == "weeks" and head.startswith("Hafta ") and len(cells) > 1:
            weeks.append((head.split()[-1], cells[1], cells[2] if len(cells) > 2 else ""))
        elif section == "books" and head.isdigit() and len(cells) > 1 and cells[1]:
            books.append(cells[1])
        elif section == "marks" and len(cells) >= 5 and head != "Yöntem":
            marks.append((head, cells[-1]))
        elif section == "load" and head.startswith("Toplam"):
            hours = base._num(cells[-1])
    if ects:
        info.insert(0, ("AKTS", ects))
    if len(rows[0]) > 2 and re.search(r"\d", rows[0][2]):
        info.insert(1 if ects else 0, ("Ders+Uygulama+Lab", rows[0][2]))
    if books:
        parts.append(("Kaynaklar", "\n".join(books)))
    workload = {"hours": hours, "ects": ects} if hours else None
    return base.detail(url, f"{code} {name}", info=info, parts=parts, weeks=weeks, outcomes=outcomes, assessment=marks,
                       workload=workload)


async def programs(http) -> list[dict]:
    """Tüm lisans programları; tek istek."""
    return _parse_programs(_text(await http.raw(LIST)))


async def courses(http, program) -> list[dict]:
    """1. yıl sayfası menüden yıl sayısını da verir; kalan yıllar paralel istenir."""
    pid = str(program["pid"])
    link = lambda year: f"{ROOT}semester.aspx?pid={pid}&lang=1&sid={year * 10}"  # noqa: E731
    first = _text(await http.raw(link(1)))
    years = [year for year in _years(first, pid) if year != 1]
    rest = await asyncio.gather(*(http.raw(link(year)) for year in years))
    out = _parse_plan(first, link(1), 1)
    for year, body in zip(years, rest):
        out += _parse_plan(_text(body), link(year), year)
    # Aynı seçmeli birden çok yılın havuzunda geçebilir.
    seen, unique = set(), []
    for item in out:
        key = (item["code"] or item["name"], item["period"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    pools = base.period(elective=True)
    unique.sort(key=lambda item: item["period"] == pools)  # dönem dersleri önce, seçmeli havuzları sonda (sıra korunur)
    return unique


async def detail(http, url) -> dict | None:
    return _parse_detail(_text(await http.raw(url)), url)
