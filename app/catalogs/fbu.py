"""Fenerbahçe Üniversitesi — Bilgi Paketi / Ders Kataloğu (ois.fbu.edu.tr/bilgipaketi/eobsakts). Düz GET, oturumsuz.

Yapı:
  akademik/tip/L/ln/tr                         → fakülte başlıkları (tr.head) altında lisans programları (program_kodu)
  ogrenimprogrami/program_kodu/<kod>/ln/tr     → öğretim planı TEK sayfada: yarıyıl başlıkları, zorunlu dersler,
                                                 seçmeli grubu satırları ve her grubun altında gizli ders havuzu
  ders/ders_id/<no>/program_kodu/<kod>/…/ln/tr → dersin içeriği (amaç, içerik, kazanımlar, haftalık plan, ölçme, iş yükü)

Not: obs.fbu.edu.tr/oibs/bologna (Proliz) aynı ders planını verir ama ders içerikleri orada boştur ("Kayıt Yok");
kurumun "Akademik Bilgi Paketi" bağlantısı da buraya çıkar, o yüzden Proliz yerine bu sistem okunur.
"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import urljoin

from . import base

DOMAINS = ("fbu.edu.tr", "fenerbahce.edu.tr")
BASE = "https://ois.fbu.edu.tr/bilgipaketi/eobsakts/"

_PROGRAM = re.compile(r"/programtanimi/program_kodu/(\w+)")
_COURSE = re.compile(r"/ders/ders_id/(\d+)/")
_TERM = re.compile(r"(\d+)\s*\.\s*(?:yar[ıi]y[ıi]l|semester)", re.I)


def _parse_units(text: str) -> list[tuple[str, str, str]]:
    """Program listesi: (program_kodu, ad, fakülte). Fakülte adı tr.head, programlar tr.rows satırlarındadır."""
    rows, faculty = [], ""
    for tr in base.parse(text).xpath("//tr[@class='head' or @class='rows']"):
        link = (tr.xpath(".//a[@href]") or [None])[0]
        if link is None:
            continue
        found = _PROGRAM.search(link.get("href"))
        if found:
            rows.append((found[1], base.txt(link), faculty))
        elif "fakulte_kodu" in link.get("href"):
            faculty = base.txt(link)
    return rows


def _parse_programs(text_tr: str, text_en: str = "") -> list[dict]:
    english = {code: name for code, name, _ in _parse_units(text_en)} if text_en else {}
    out = []
    for code, name, faculty in _parse_units(text_tr):
        alias = english.get(code, "")
        out.append({"name": name, "faculty": faculty, "code": code, "aliases": [alias] if alias and alias != name else [],
                    "url": urljoin(BASE, f"ogrenimprogrami/program_kodu/{code}/ln/tr")})
    return out


async def programs(http) -> list[dict]:
    """Lisans programları — 2 istek (Türkçe liste + İngilizce adlar, paralel)."""
    async def english():
        try:
            return await http.text(urljoin(BASE, "akademik/tip/L/ln/en"))
        except Exception:  # noqa: BLE001 — İngilizce adlar yalnız eşlemeyi kolaylaştırır
            return ""
    text_tr, text_en = await asyncio.gather(http.text(urljoin(BASE, "akademik/tip/L/ln/tr")), english())
    return _parse_programs(text_tr, text_en)


def _parse_plan(text: str, url: str) -> list[dict]:
    """Öğretim planı. Sütunlar: kod, ad, dil, ön koşul, teorik, pratik, kredi, AKTS.
    - tr.head 'N. Yarıyıl' dönemi açar,
    - ders bağlantısında '/h/<havuz no>/' varsa satır bir seçmeli havuzundandır (st/D alan, st/GS genel, st/MD
      multidisipliner seçmeli); aynı havuz her grupta yinelendiği için ders_id ile teklenir,
    - bağlantısı javascript:ShowHide(...) olan satır seçmeli grubudur (kod yok; kredi ve AKTS dolu): dönemde gösterilir."""
    out, pool, seen, period, group = [], [], set(), "", "Seçmeli"
    for tr in base.parse(text).xpath("//tr[@class='head' or @class='rows']"):
        cells = [base.txt(td) for td in tr.xpath("./td")]
        if tr.get("class") == "head":
            term = _TERM.search(" ".join(cells))
            if term:
                period = base.period(term[1])
            continue
        if len(cells) < 8:
            continue
        code, name, credit, ects = cells[0], cells[1], cells[6], cells[7]
        href = (tr.xpath(".//a/@href") or [""])[0]
        found = _COURSE.search(href)
        if not found:
            if "ShowHide" in href and name:
                group = name
                out.append(base.course("", name, period, ects=ects, credit=credit, kind="Seçmeli grubu", source=url))
            continue
        # Bağlantılar /bilgipaketi/index/ders/… biçimindedir ve /eobsakts/ders/…'e yönlenir; doğrudan o yazılır.
        link = urljoin(url, href.replace("/index/ders/", "/eobsakts/ders/"))
        if "/h/" in href:
            if found[1] not in seen:
                seen.add(found[1])
                pool.append(base.course(code, name, base.period(elective=True), ects=ects, credit=credit, kind=group, url=link))
        else:
            out.append(base.course(code, name, period, ects=ects, credit=credit, kind="Zorunlu", url=link))
    plain = {item["code"] for item in out if item["code"]}
    return out + [item for item in pool if item["code"] not in plain]


async def courses(http, program: dict) -> list[dict]:
    """Programın ders planı — 1 istek."""
    return _parse_plan(await http.text(program["url"]), program["url"])


def _section(tree, ident: str):
    """Başlığı <h3 id=…> olan bölümün tablosu."""
    found = tree.xpath(f"//h3[@id='{ident}']/following-sibling::table[1]")
    return found[0] if found else None


def _pairs(table) -> dict[str, object]:
    """'Etiket: | değer' satırları → {katlanmış etiket: değer hücresi}."""
    out = {}
    if table is not None:
        for tr in table.xpath("./tr|./tbody/tr"):
            cells = tr.xpath("./td")
            if len(cells) >= 2:
                out[base.fold(base.txt(cells[0]))] = cells[1]
    return out


def _parse_detail(text: str, url: str) -> dict | None:
    tree = base.parse(text)
    general = _pairs((tree.xpath("//table[@id='genelbilgi']") or [None])[0])

    def value(label: str, multiline: bool = False) -> str:
        node = general.get(label)
        return (base.lines(node) if multiline else base.txt(node)) if node is not None else ""

    # "Ders Kredileri" hücresinde iç tablo: Teorik, Pratik, Kredi, AKTS.
    credit_cell = general.get("ders kredileri")
    credits = [base.txt(td) for td in credit_cell.xpath(".//tr[@class='rows']/td")] if credit_cell is not None else []
    credits += [""] * (4 - len(credits))
    teachers = ", ".join(row for row in value("dersi veren ler", True).split("\n") if base.fold(row) != "ogretim elemani")
    info = [("Dil", value("ogretim dili")), ("Tür", value("dersin turu")), ("Yarıyıl", value("ders yariyili")),
            ("Teorik + Pratik", f"{credits[0]} + {credits[1]}" if credits[0] else ""), ("Kredi", credits[2]),
            ("AKTS", credits[3]), ("Ön koşul", value("ders kosulu")), ("Veriliş şekli", value("dersin verilis sekli")),
            ("Koordinatör", value("dersin koordinatoru")), ("Dersi verenler", teachers)]

    aims, sources = _pairs(_section(tree, "amac")), _pairs(_section(tree, "kaynaklar"))
    parts = [("Dersin amacı", base.lines(aims.get("dersin amaci"))), ("Dersin içeriği", base.lines(aims.get("dersin icerigi"))),
             ("Ders notları / kitaplar", base.lines(sources.get("ders notlari kitaplar"))),
             ("Diğer kaynaklar", base.lines(sources.get("diger kaynaklar")))]
    if parts[3][1] == parts[2][1]:
        parts.pop()

    # Kazanımlar: iç tabloda (table.table) tr.rows satırları, "1) …" numaralı.
    outcomes = [re.sub(r"^\d+\)\s*", "", base.txt(td)) for td in tree.xpath(
        "//h3[@id='kazanimlar']/following-sibling::table[1]//table//tr[@class='rows']/td[1]")]
    weeks = []
    table = _section(tree, "dersicerigi")
    for tr in (table.xpath(".//tr[@class='rows']") if table is not None else []):
        cells = [base.txt(td) for td in tr.xpath("./td")] + ["", ""]
        weeks.append((cells[0].rstrip(") "), cells[1], cells[2]))
    assessment = []
    table = _section(tree, "olcmedegerlendirme")
    for tr in (table.xpath(".//tr[@class='rows']") if table is not None else []):
        cells = tr.xpath("./td")
        # "YARIYIL İÇİ ÇALIŞMALARININ … KATKISI" özet satırlarının ilk hücresi td.head'dir; onlar etkinlik değildir.
        if len(cells) == 3 and "head" not in (cells[0].get("class") or ""):
            assessment.append((base.txt(cells[0]), base.txt(cells[2]), base.txt(cells[1])))
    hours = base.txt((tree.xpath("//h3[@id='akts']/following-sibling::table[1]//tr[@class='head']/td[last()]") or [None])[-1])
    workload = {"hours": hours, "ects": credits[3]} if base.number(hours) else None
    title = f"{value('ders kodu')} {value('ders ismi')}"
    if not any(body for _, body in parts) and not weeks and not outcomes and not assessment:
        return None
    return base.detail(url, title, info=info, parts=parts, weeks=weeks, outcomes=outcomes, assessment=assessment,
                       workload=workload)


async def detail(http, url: str) -> dict | None:
    """Tek dersin içeriği — 1 istek."""
    return _parse_detail(await http.text(url), url)
