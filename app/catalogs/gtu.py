"""Gebze Teknik Üniversitesi — Proliz OBS Bologna bilgi paketi (obs.gtu.edu.tr/oibs/bologna).

Yapı (oturum/çerez gerekmez, hepsi düz GET):
  unitSelection.aspx?type=lis&lang=tr              → fakülte panelleri altında lisans programları (curUnit, curSunit)
  progCourses.aspx?lang=tr&curSunit=<program>      → programın bütün ders planı tek sayfada (yarıyıl başlıkları,
                                                     seçmeli grupları ve gizli satırlarda grubun dersleri; 1-2 MB)
  progCourseDetails.aspx?curCourse=<ders>&lang=tr  → dersin bilgi formu (amaç, içerik, değerlendirme, iş yükü, çıktılar)
Eski paket (abl.gtu.edu.tr/ects) arşivdir; sayfaları güncel bilgi için buraya yönlendirir.
"""
from __future__ import annotations

import re

from . import base

DOMAINS = ("gtu.edu.tr",)
ROOT = "https://obs.gtu.edu.tr/oibs/bologna/"
UNITS = ROOT + "unitSelection.aspx?type=lis&lang=tr"
_EMPTY = {"", "-", "yok", "tba", "veri yok"}  # doldurulmamış alanlara sistemin/hocaların yazdığı değerler


def _program_name(raw: str) -> str:
    """'X (En Az %30 İngilizce)' → 'X (%30 İngilizce)'; '(%100 İngilizce)' → '(İngilizce)'; '(Türkçe)' atılır."""
    name = re.sub(r"\s*\(\s*", " (", base.txt(raw))
    name = re.sub(r"\(En Az %(\d+) İngilizce\)", r"(%\1 İngilizce)", name)
    name = name.replace("(%100 İngilizce)", "(İngilizce)").replace("(Türkçe)", "")
    return base.txt(name.replace(" Ve ", " ve "))


def _parse_programs(text: str) -> list[dict]:
    out = []
    for panel in base.parse(text).xpath("//div[contains(@class,'panel-default')]"):
        faculty = base.txt(panel.xpath("string(.//*[contains(@class,'panel-title')])"))
        if "fakülte" not in faculty.lower() and "yüksekokul" not in faculty.lower():
            continue  # "Rektörlüğe Bağlı Bölümler": ortak ders havuzları, program değil
        for link in panel.xpath(".//a[contains(@href,'curSunit=')]"):
            href = link.get("href") or ""
            unit, sunit = re.search(r"curUnit=(\w+)", href), re.search(r"curSunit=(\d+)", href)
            name = _program_name(base.txt(link))
            if not sunit or not name:
                continue
            out.append({"name": name, "faculty": faculty, "sunit": sunit[1],
                        "url": f"{ROOT}index.aspx?lang=tr&curOp=showPac&curUnit={unit[1] if unit else ''}&curSunit={sunit[1]}"})
    return out


def _cell(row, key: str) -> str:
    """Ders planı satırındaki alan: kimliği 'grdBolognaDersler_<key>_<n>' olan span ya da bağlantı."""
    return base.txt(row.xpath(f"string(.//*[contains(@id,'_{key}_')])"))


def _parse_plan(text: str, url: str) -> list[dict]:
    """Zorunlu dersler yarıyılına, seçmeli gruplarının dersleri "Seçmeli dersler"e yazılır (grup adı türde kalır)."""
    out, seen = [], set()
    semester, group = "", ""
    for row in base.parse(text).xpath("//table[@id='grdBolognaDersler']//tr"):
        code, name = _cell(row, "lblDersKod") or _cell(row, "btnDersKod"), _cell(row, "lblDersAd")
        head = re.match(r"(\d+)\s*\.\s*Yarıyıl", name)
        if head and not code:
            semester, group = base.period(head[1]), ""
            continue
        if not code or not name:
            continue
        opened = re.search(r"prolizOpenCourseDetails\((\d+)\)", " ".join(row.xpath(".//a/@onclick")))
        option = "collapse" in (row.get("class") or "").split()  # gizli satır: üstündeki seçmeli grubunun dersi
        if not opened:
            if row.xpath(".//*[contains(@class,'expandCollapse')]"):
                group = name  # seçmeli grubu satırı ("Technical Elective"); kendisi ders değil
            continue
        kind = (f"Seçmeli · {group}" if group else "Seçmeli") if option else _cell(row, "Label5")
        period = base.period(elective=True) if option or kind.lower().startswith("seçmeli") else semester
        if (code, period) in seen:
            continue
        seen.add((code, period))
        hours = _cell(row, "Label3")  # T+U+L; girilmemiş derslerde "0+0+0"
        out.append(base.course(code, name, period, ects=_cell(row, "lblAKTS"), credit="" if hours == "0+0+0" else hours,
                               kind=kind, url=f"{ROOT}progCourseDetails.aspx?curCourse={opened[1]}&lang=tr", source=url))
    return out


def _weeks_from_content(content: str) -> list[tuple]:
    """Konu tablosu boşken içerik alanına "1. hafta: … 2. hafta: …" diye yazılmış haftalık plan."""
    return [(n, topic.strip()) for n, topic in re.findall(r"(\d+)\.\s*hafta\*?\s*:\s*(.*?)(?=\d+\.\s*hafta|\Z)", content, re.S | re.I)]


def _parse_detail(text: str, url: str) -> dict | None:
    tree = base.parse(text)

    def field(key: str) -> str:
        value = base.lines(next(iter(tree.xpath(f"//span[@id='dlDers_{key}Label_0']")), None))
        return "" if value.strip().lower() in _EMPTY else value

    head = [base.txt(td) for td in tree.xpath("//table[@id='grdDers']//tr[td][1]/td")]
    if len(head) < 3:
        return None  # "Kayıt Yok": dersin bilgi formu doldurulmamış
    content = field("ICERIK")
    weeks = [(cells[0], cells[1], cells[2] if len(cells) > 2 else "")
             for cells in ([base.txt(td) for td in tr.xpath("./td")] for tr in tree.xpath("//table[@id='grdDersKonu']//tr[td]"))
             if len(cells) >= 2 and cells[1].lower() not in _EMPTY]
    if not weeks:
        weeks = _weeks_from_content(content)
    outcomes = [cells[1] for cells in ([base.txt(td) for td in tr.xpath("./td")]
                                       for tr in tree.xpath("//table[starts-with(@id,'grdOgrenmeCiktilari')]//tr[td]"))
                if len(cells) == 2 and cells[0].isdigit()]
    assessment = []
    for tr in tree.xpath("//table[@id='grd_degerlendirme']//tr"):
        name = base.txt(tr.xpath("string(.//span[contains(@id,'lblCalismaTip_')])"))
        if name:
            assessment.append((name, base.txt(tr.xpath("string(.//span[contains(@id,'lblDS_Katki_')])")),
                               base.txt(tr.xpath("string(.//span[contains(@id,'lblDS_Sayi_')])"))))
    hours = base.txt(tree.xpath("string(//span[@id='grd_akts_lblAKTS_Top'])"))
    ects = base.txt(tree.xpath("string(//span[@id='grd_akts_lblAKTS_Sonuc'])"))
    info = [("Dersin dili", field("DIL")), ("Dersin türü", field("TUR")), ("T+U+L", head[3] if len(head) > 3 else ""),
            ("Kredi", head[4] if len(head) > 4 else ""), ("AKTS", head[5] if len(head) > 5 else ""),
            ("Ön koşullar", field("DERS_ONKOSUL")), ("Koordinatör", field("DERS_KOORDINATOR")),
            ("Dersi verenler", field("DERS_VEREN"))]
    parts = [("Dersin amacı", field("AMAC")), ("Dersin içeriği", "" if weeks and _weeks_from_content(content) else content),
             ("Yöntem ve teknikler", field("YONTEMTEKNIK")), ("Kaynaklar", field("KAYNAKLAR")), ("Ders notları", field("DERS_NOTU"))]
    return base.detail(url, f"{head[1]} {head[2]}", info=info, parts=parts, weeks=weeks, outcomes=outcomes,
                       assessment=assessment, workload={"hours": hours, "ects": ects} if hours else None)


async def programs(http) -> list[dict]:
    return _parse_programs(await http.text(UNITS))


async def courses(http, program) -> list[dict]:
    url = f"{ROOT}progCourses.aspx?lang=tr&curSunit={program['sunit']}"
    return _parse_plan(await http.text(url), program.get("url") or url)


async def detail(http, url) -> dict | None:
    return _parse_detail(await http.text(url), url)
