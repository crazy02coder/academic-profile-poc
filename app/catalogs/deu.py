"""Dokuz Eylül Üniversitesi — Bilgi Paketi (debis.deu.edu.tr/ders-katalog; statik HTML, UTF-8).

  /ders-katalog/                          akademik yıl arşivi (en güncel yıl seçilir)
  /<yıl>/tr/tr-c3.html                    lisans programları ağacı (ul#onlisans): fakülte > … > bolum_<id>_tr.html
  /<yıl>/tr/bolum_<id>_tr.html            program sayfası: "N. Dönem" başlık satırlı tek ders tablosu
  /<yıl>/tr/tr_<birim>_<bolum>_<n>.html   ders sayfası: her başlık <h4 class="colored">, haftalık konular tablo

Ders planı tek istekte gelir (yıl ve program listesi 30 gün saklanır); ders içeriği dersin sayfasından tembel okunur.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from . import base

DOMAINS = ("deu.edu.tr",)
ROOT = "https://debis.deu.edu.tr/ders-katalog/"
_YEAR = re.compile(r"(\d{4})-(\d{4})/index\.html")
_SEMESTER = re.compile(r"^(\d{1,2})\s*\.\s*Dönem", re.I)
_TERMS = {"G": "Güz", "B": "Bahar", "H": "Her iki dönem"}  # seçmeli havuzundaki derslerin dönem harfi


def _latest_year(text: str) -> str:
    years = sorted({f"{m[1]}-{m[2]}" for m in _YEAR.finditer(text)})
    if not years:
        raise ValueError("DEÜ arşiv sayfasında akademik yıl bulunamadı")
    return years[-1]


def _parse_programs(text: str, base_url: str) -> list[dict]:
    tree = base.parse(text)
    root = (tree.xpath("//ul[@id='onlisans']") or [tree])[0]
    rows = []
    for anchor in root.xpath(".//a[@href]"):
        if not re.fullmatch(r"bolum_\d+_tr\.html", anchor.get("href").strip()):
            continue
        # En üst düzeydeki <li>'nin kendi metni fakülte adıdır.
        top = None
        for parent in anchor.iterancestors():
            if parent is root:
                break
            if parent.tag == "li":
                top = parent
        faculty = base.txt((top.text or "") + " ".join(child.tail or "" for child in top)) if top is not None else ""
        name = base.txt(anchor)
        if name:
            rows.append({"name": name, "faculty": faculty, "url": urljoin(base_url, anchor.get("href").strip())})
    return rows


async def programs(http) -> list[dict]:
    year = _latest_year(await http.text(ROOT))
    base_url = f"{ROOT}{year}/tr/"
    return _parse_programs(await http.text(urljoin(base_url, "tr-c3.html")), base_url)


def _parse_plan(text: str, url: str) -> list[dict]:
    tree = base.parse(text)
    items, semester, pool = [], "", False
    for row in tree.xpath("//tr"):
        cells = row.xpath("./td|./th")
        if len(cells) == 1:
            label = base.txt(cells[0])
            if match := _SEMESTER.match(label):
                semester, pool = match[1], False
            elif "SEÇ" in label.upper() and "DERS" in label.upper():
                semester, pool = "", True
            continue
        if len(cells) < 9 or cells[0].tag == "th":
            continue
        code, name = base.txt(cells[2]), base.txt(cells[3])
        if not code or not name or code.lower() == "ders kodu":
            continue
        link = cells[2].xpath(".//a[@href]")
        elective = pool or not semester
        term = _TERMS.get(base.txt(cells[0]).upper()[:1], "") if elective else ""
        items.append(base.course(code, name, base.period(elective=True) if elective else base.period(semester),
                                 ects=base.txt(cells[8]), kind=f"Seçmeli ({term})" if term else "",
                                 url=urljoin(url, link[0].get("href").strip()) if link else "", source=url))
    unique = {}
    for item in items:
        unique.setdefault((item["code"], item["period"]), item)
    return list(unique.values())


async def courses(http, program) -> list[dict]:
    return _parse_plan(await http.text(program["url"]), program["url"])


def _parse_detail(text: str, url: str) -> dict | None:
    tree = base.parse(text)
    sections = {}
    for heading in tree.xpath("//h4[contains(concat(' ', normalize-space(@class), ' '), ' colored ')]"):
        row = heading.xpath("ancestor::tr[1]")
        following = row[0].xpath("following-sibling::tr[1]") if row else []
        if base.txt(heading) and following:
            sections.setdefault(base.txt(heading), following[0])

    def node_of(*names):
        return next((node for title, node in sections.items() if any(_starts(title, name) for name in names)), None)

    def body(*names):
        text = base.lines(node_of(*names))
        return "" if base.fold(text) in {"yok", "ilan edilecektir.", "ilan edilecektir"} else text

    weeks = []
    for table in tree.xpath("//table"):
        rows = table.xpath("./tr|./tbody/tr")
        if not rows:
            continue
        head = [base.txt(c).lower() for c in rows[0].xpath("./td|./th")]
        if len(head) < 2 or not head[0].startswith("hafta") or "konu" not in head[1]:
            continue
        for row in rows[1:]:
            cells = row.xpath("./td")
            week = base.number(base.txt(cells[0])) if len(cells) >= 2 else None
            if week is not None:
                weeks.append((str(int(week)), base.txt(cells[1]) or (base.txt(cells[2]) if len(cells) > 2 else "")))
        break
    # Kazanımlar "sıra | 1. metin" satırlarıdır: son hücre alınır, baştaki numara atılır.
    box = node_of("Dersin Öğrenme Kazanımları")
    rows = box.xpath(".//tr[td]") if box is not None else []
    outcomes = [re.sub(r"^\d{1,2}\s*[.)]\s*", "", base.txt(row.xpath("./td")[-1])) for row in rows] \
        or [re.sub(r"^(?:\d{1,2}\s*[.)]?\s*)+", "", line) for line in body("Dersin Öğrenme Kazanımları").split("\n")]
    # Sayfa başındaki künye tablosu: Ders Kodu | Ders Adı | Ders Türü | D | U | L | AKTS
    head = {}
    for table in tree.xpath("//table"):
        cells = [[base.txt(c) for c in row.xpath("./td|./th")] for row in table.xpath("./tr|./tbody/tr")]
        if len(cells) >= 2 and cells[0][:2] == ["Ders Kodu", "Ders Adı"]:
            head = dict(zip(cells[0], cells[1]))
            break
    info = [("Türü", head.get("Ders Türü", "")), ("Dili", body("Dersin Öğretim Dili")), ("Koordinatör", body("Ders Koordinatörü")),
            ("Ön koşul", body("Dersin Önkoşulu"))]
    return base.detail(url, f"{head.get('Ders Kodu', '')} {head.get('Ders Adı', '')}".strip(), info=info, weeks=weeks,
                       outcomes=[o for o in outcomes if len(o) > 8],
                       parts=[("Dersin amacı", body("Dersin Amacı")), ("Öğretim yöntemleri", body("Öğrenme ve Öğretme")),
                              ("Değerlendirme", body("Değerlendirme Kriteri")), ("Kaynaklar", body("Ders İçin Önerilen Kaynaklar"))])


def _starts(title: str, name: str) -> bool:
    return base.fold(title).startswith(base.fold(name))


async def detail(http, url) -> dict | None:
    if "/ders-katalog/" not in url:
        return None
    return _parse_detail(await http.text(url), url)
