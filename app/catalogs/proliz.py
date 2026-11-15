"""Proliz OBS Bologna bilgi paketi (…/oibs/bologna/) — aynı yazılımı kullanan kurumların ortak ayrıştırıcısı.

Yapı (hepsi düz GET, oturum gerekmez; `base_url` "https://obs.kurum.edu.tr/oibs/bologna/" biçimindedir):
  unitSelection.aspx?type=lis&lang=tr        → fakülte başlıkları altında lisans programları (curUnit, curSunit)
  progCourses.aspx?lang=tr&curSunit=<no>     → programın bütün ders planı TEK sayfada (yarıyıl başlıkları, seçmeli
                                               grupları ve gruba bağlı gizli havuz satırları)
  progCourseDetails.aspx?curCourse=<no>&lang=tr → tek dersin içeriği (amaç, içerik, haftalık konular, çıktılar…)

Kurum modülü yalnız adresi verir:
    BASE = "https://obs.kurum.edu.tr/oibs/bologna/"
    async def programs(http): return await proliz.programs(http, BASE)
    courses, detail = proliz.courses, proliz.detail
"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import parse_qs, urljoin, urlsplit

from . import base

# Ders planı sayfası __VIEWSTATE ve satır içi stiller yüzünden çok büyük olabiliyor (FBU: 7,5 MB); Http'nin
# varsayılan 6 MB sınırı bu yüzden yükseltilir.
PAGE_LIMIT = 40_000_000

# Lisans listesinde görünen ama lisans programı olmayan kayıtlar: hazırlık sınıfları, ortak ders havuzu, yandal
# planları ve değişim anlaşması için açılmış başka üniversite kayıtları.
_NOT_PROGRAM = re.compile(r"haz[ıi]rl[ıi]k|preparatory|ortak dersler|common courses|yandal|minor\b|[çc]ift ?anadal"
                          r"|[üu]niversitesi$|university$", re.I)
_NOT_FACULTY = re.compile(r"yabanc[ıi] diller|foreign languages|haz[ıi]rl[ıi]k|ortak dersler|rekt[öo]rl[üu]k", re.I)
_SMALL = {"ve", "ile", "and", "of", "in", "for", "the"}
_TERM = re.compile(r"(\d+)\s*\.\s*(yar[ıi]y[ıi]l|d[öo]nem|semester|y[ıi]l|s[ıi]n[ıi]f|year)", re.I)
_COURSE_ID = re.compile(r"prolizOpenCourseDetails\((\d+)\)")
_EMPTY = {"", "-", "yok", "none"}


def _title(name: str, turkish: bool = True) -> str:
    """Tümü büyük harfle yazılmış adı düzeltir: 'BİLGİSAYAR MÜHENDİSLİĞİ (TÜRKÇE)' → 'Bilgisayar Mühendisliği
    (Türkçe)'. Türkçe adda I→ı, İ→i kuralı uygulanır; İngilizce adda uygulanmaz. Küçük harf içeren ad değişmez."""
    name = base.txt(name)
    if not name or name != name.upper():
        return name

    def word(match):
        w = (match[0].replace("İ", "i").replace("I", "ı") if turkish else match[0].replace("İ", "I")).lower()
        if w in _SMALL and match.start():
            return w
        first = {"i": "İ", "ı": "I"}.get(w[0]) if turkish else None
        return (first or w[0].upper()) + w[1:]

    return re.sub(r"[^\W\d_]+", word, name)


def _parse_units(text: str, page_url: str, turkish: bool = True) -> list[dict]:
    """unitSelection sayfası: her fakülte bir panel (başlıkta '#x<curUnit>' bağlantısı), altında program bağlantıları."""
    rows, faculty = [], ""
    for link in base.parse(text).xpath("//a[@href]"):
        href = link.get("href") or ""
        if href.startswith("#x"):
            faculty = _title(base.txt(link), turkish)
        elif "curOp=showPac" in href:
            query = parse_qs(urlsplit(href).query)
            sunit = (query.get("curSunit") or [""])[0]
            if sunit:
                rows.append({"name": _title(base.txt(link), turkish), "faculty": faculty, "sunit": sunit,
                             "url": urljoin(page_url, href)})
    return rows


def _parse_programs(text_tr: str, text_en: str, base_url: str) -> list[dict]:
    """Türkçe liste esas alınır; İngilizce listedeki ad (aynı curSunit) `aliases`a eklenir."""
    page = urljoin(base_url, "unitSelection.aspx?type=lis&lang=tr")
    english = {row["sunit"]: row["name"] for row in _parse_units(text_en, page, turkish=False)} if text_en else {}
    out = []
    for row in _parse_units(text_tr, page):
        if _NOT_PROGRAM.search(row["name"]) or _NOT_FACULTY.search(row["faculty"]):
            continue
        alias = english.get(row["sunit"], "")
        row["aliases"] = [alias] if alias and alias != row["name"] else []
        row["plan"] = urljoin(base_url, f"progCourses.aspx?lang=tr&curSunit={row['sunit']}")
        out.append(row)
    return out


async def programs(http, base_url: str) -> list[dict]:
    """Lisans programları — 2 istek (Türkçe ve İngilizce liste, paralel). İngilizce liste gelmezse adsız sürer."""
    async def english():
        try:
            return await http.text(urljoin(base_url, "unitSelection.aspx?type=lis&lang=en"))
        except Exception:  # noqa: BLE001 — İngilizce adlar yalnız eşlemeyi kolaylaştırır
            return ""
    text_tr, text_en = await asyncio.gather(http.text(urljoin(base_url, "unitSelection.aspx?type=lis&lang=tr")), english())
    return _parse_programs(text_tr, text_en, base_url)


def _parse_plan(text: str, url: str) -> list[dict]:
    """progCourses sayfası (grdBolognaDersler tablosu). Satır türleri:
    - yarıyıl başlığı ('3.Yarıyıl Ders Planı') ve sütun başlığı / 'Toplam AKTS' satırları,
    - ders satırı: onclick'te prolizOpenCourseDetails(<ders no>),
    - seçmeli grubu satırı (ders no yok, 'Grup Ders Adedi' dolu): yarıyılın AKTS yükünü taşır, dönemde gösterilir,
    - gruba bağlı havuz satırı (tr class'ında 'collapse_<grup no>'): aynı havuz her grupta yinelenir; bir kez,
      'Seçmeli dersler' altında verilir."""
    tree = base.parse(text)
    out, pool, seen, period = [], [], set(), ""
    for tr in tree.xpath("//table[@id='grdBolognaDersler']//tr"):
        cells = [base.txt(td) for td in tr.xpath("./td")]
        if len(cells) < 6:
            continue
        code, name, kind, ects = cells[1], cells[2], cells[4], cells[5]
        if not code:
            term = _TERM.search(name)
            if term:
                n, unit = int(term[1]), base.fold(term[2])
                # Yıllık planlarda ('2.Yıl', '2.Sınıf') yılın ilk dönemi yazılır.
                period = base.period(n) if unit in {"yariyil", "donem", "semester"} else base.period(year=n, term=1)
            continue
        found = _COURSE_ID.search(" ".join(tr.xpath(".//a/@onclick")))
        if "collapse_" in (tr.get("class") or ""):
            key = base.fold(f"{code} {name}")
            if found and key not in seen:
                seen.add(key)
                pool.append(base.course(code, name, base.period(elective=True), ects=ects, kind="Seçmeli",
                                        url=urljoin(url, f"progCourseDetails.aspx?curCourse={found[1]}&lang=tr")))
        elif found:
            out.append(base.course(code, name, period, ects=ects, kind=kind,
                                   url=urljoin(url, f"progCourseDetails.aspx?curCourse={found[1]}&lang=tr")))
        elif base.number(ects) is not None:  # sütun başlığı satırında AKTS hücresi sayı değildir
            out.append(base.course(code, name, period, ects=ects, kind="Seçmeli grubu", source=url))
    plain = {base.fold(item["title"]) for item in out}
    return out + [item for item in pool if base.fold(item["title"]) not in plain]


async def courses(http, program: dict) -> list[dict]:
    """Programın ders planı — 1 istek."""
    url = program["plan"]
    return _parse_plan(await http.text(url, limit=PAGE_LIMIT), url)


def _span(tree, ident: str):
    found = tree.xpath(f"//*[@id='{ident}']")
    return found[0] if found else None


def _grid(tree, ident: str) -> list[list[str]]:
    """ProlizMGrid tablosunun veri satırları (başlık ve toplam satırı hariç: veri satırlarında myid vardır)."""
    return [[base.txt(td) for td in tr.xpath("./td")] for tr in tree.xpath(f"//table[@id='{ident}']//tr[@myid]")]


def _parse_detail(text: str, url: str) -> dict | None:
    """progCourseDetails sayfası. Alanlar sabit kimliklidir (dlDers_<ALAN>Label_0); doldurulmamış derste hücreler
    boştur ya da 'Yok' yazar — o zaman None döner."""
    tree = base.parse(text)
    head = (_grid(tree, "grdDers") or [[]])[0]  # Yarıyıl, Kodu, Adı, T+U+L, Kredi, AKTS, güncelleme tarihi
    head += [""] * (7 - len(head))

    def field(name: str, multiline: bool = False) -> str:
        node = _span(tree, f"dlDers_{name}_0")
        value = base.lines(node) if multiline else base.txt(node)
        return "" if base.fold(value) in _EMPTY else value

    info = [("Dil", field("DILLabel")), ("Tür", field("TURLabel")), ("Öğretim şekli", field("OGRETIM_SEKLILabel")),
            ("T+U+L", head[3]), ("Kredi", head[4]), ("AKTS", head[5]), ("Ön koşul", field("DERS_ONKOSULLabel")),
            ("Koordinatör", field("DERS_KOORDINATORLabel")), ("Dersi verenler", field("DERS_VERENLabel"))]
    parts = [("Dersin amacı", field("AMACLabel", True)), ("Dersin içeriği", field("ICERIKLabel", True)),
             ("Yöntem ve teknikler", field("YONTEMTEKNIKLabel", True)), ("Kaynaklar", field("KAYNAKLARLabel", True)),
             ("Ders notları", field("DERS_NOTULabel", True))]
    weeks = [row[:3] for row in _grid(tree, "grdDersKonu") if len(row) >= 2]
    outcomes = [row[1] for row in _grid(tree, "grdOgrenmeCiktilari") if len(row) >= 2]
    assessment = [(row[0], row[2], row[1]) for row in _grid(tree, "grd_degerlendirme") if len(row) >= 3]
    # İş yükü tablosundaki "AKTS Kredisi" yuvarlanmamış olabiliyor (4,7333…); dersin künyesindeki AKTS yazılır.
    hours = base.txt(_span(tree, "grd_akts_lblAKTS_Top"))
    workload = {"hours": hours, "ects": head[5]} if base.number(hours) else None
    if not any(text for _, text in parts) and not weeks and not outcomes and not assessment:
        return None  # içerik girilmemiş: yalnız künye var, ders planındaki bilgiyi yinelemeye gerek yok
    return base.detail(url, f"{head[1]} {head[2]}", info=info, parts=parts, weeks=weeks, outcomes=outcomes,
                       assessment=assessment, workload=workload)


async def detail(http, url: str) -> dict | None:
    """Tek dersin içeriği — 1 istek."""
    return _parse_detail(await http.text(url), url)
