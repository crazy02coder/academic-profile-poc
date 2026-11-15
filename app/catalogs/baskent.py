"""Başkent Üniversitesi — Bilgi Paketi (bilgipaketi.baskent.edu.tr; sunucuda üretilen HTML).

  /tr/akademik/lisans             section.fac-group (fakülte) > ul.prog-list > li.indent-N > a.prow (program)
  /tr/program/<id>/katalog        div.kt-term > h3.kt-term__title ("Üçüncü Yarıyıl (Güz)") + table.kt-table
  /tr/program/<id>/ders/<dersId>  article.course > table.ctable--detail (th → td), dl.course-facts

Ders planı tek istekte gelir (katalog sayfası); ders içeriği dersin sayfasından tembel okunur.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from . import base

DOMAINS = ("baskent.edu.tr",)
BASE = "https://bilgipaketi.baskent.edu.tr"
LIST = f"{BASE}/tr/akademik/lisans"
_ORDINALS = {"birinci": 1, "ikinci": 2, "ucuncu": 3, "dorduncu": 4, "besinci": 5, "altinci": 6, "yedinci": 7,
             "sekizinci": 8, "dokuzuncu": 9, "onuncu": 10, "on birinci": 11, "on ikinci": 12}
_ORDINAL = re.compile(r"^(on birinci|on ikinci|" + "|".join(k for k in _ORDINALS if " " not in k) + r")\s+yariyil")


def _cls(name: str) -> str:
    return f"contains(concat(' ', normalize-space(@class), ' '), ' {name} ')"


def _term(title: str) -> str:
    """'Üçüncü Yarıyıl (Güz)' → '3. dönem'; '3. Yarıyıl' → '3. dönem'; seçmeli grup başlığı → 'Seçmeli dersler'."""
    low = base.fold(title)
    if match := _ORDINAL.match(low):
        return base.period(_ORDINALS[match[1]])
    if match := re.match(r"^(\d{1,2})\s*\.\s*yariyil", low):
        return base.period(match[1])
    # Dönem dışı gruplar: seçmeli havuzları tek başlıkta toplanır; diğerleri ("Üniversite Zorunlu Dersleri") adıyla kalır.
    return base.period(elective=True) if re.search(r"sec(?:meli|imlik)", low) else base.txt(title)


def _indent(item) -> int:
    match = re.search(r"indent-(\d+)", item.get("class") or "")
    return int(match[1]) if match else 0


def _parse_programs(text: str) -> list[dict]:
    tree = base.parse(text)
    rows = []
    for group in tree.xpath(f"//section[{_cls('fac-group')}]"):
        title = group.xpath(f".//*[{_cls('fac-group__title')}]")
        faculty = base.txt(title[0]) if title else ""
        items = group.xpath(f".//ul[{_cls('prog-list')}]/li")
        if not items and title and title[0].xpath(".//a[@href]"):
            items = [title[0]]  # alt programı olmayan birim (tek programlı fakülte)
        for index, item in enumerate(items):
            anchor = item.xpath(".//a[contains(@href, '/program/')]")
            if not anchor or not re.search(r"/program/\d+", anchor[0].get("href")):
                continue
            if index + 1 < len(items) and _indent(items[index + 1]) > _indent(item):
                continue  # "… Bölümü" düğümü: asıl müfredat altındaki programlarda
            name = anchor[0].xpath(f".//*[{_cls('prow__name')}]")
            rows.append({"name": base.txt(name[0] if name else anchor[0]), "faculty": faculty,
                         "url": urljoin(BASE, anchor[0].get("href").split("?")[0].rstrip("/"))})
    return [row for row in rows if row["name"]]


async def programs(http) -> list[dict]:
    return _parse_programs(await http.text(LIST))


def _parse_plan(text: str, url: str) -> list[dict]:
    tree = base.parse(text)
    items = []
    for block in tree.xpath(f"//div[{_cls('kt-term')}]"):
        title = base.txt((block.xpath(f".//*[{_cls('kt-term__title')}]") or [None])[0])
        term = _term(title)
        for row in block.xpath(f".//table[{_cls('kt-table')}]//tbody/tr"):
            code_cell, name_cell = row.xpath(f"./td[{_cls('kt-code')}]"), row.xpath(f"./td[{_cls('kt-name')}]")
            if not code_cell or not name_cell or not base.txt(code_cell[0]):
                continue
            numbers = row.xpath(f"./td[{_cls('kt-num')}]")
            link = code_cell[0].xpath(".//a[@href]")
            items.append(base.course(base.txt(code_cell[0]), base.txt(name_cell[0]), term,
                                     ects=base.txt(numbers[-1]) if numbers else None,
                                     kind=title if term == base.period(elective=True) else "",
                                     url=urljoin(BASE, link[0].get("href")) if link else "", source=url))
    unique = {}
    for item in items:
        unique.setdefault((item["code"], item["period"]), item)
    return list(unique.values())


async def courses(http, program) -> list[dict]:
    url = f"{program['url']}/katalog"
    return _parse_plan(await http.text(url), url)


def _parse_detail(text: str, url: str) -> dict | None:
    tree = base.parse(text)
    rows = {}
    for row in tree.xpath(f"//table[{_cls('ctable--detail')}]/tbody/tr|//table[{_cls('ctable--detail')}]/tr"):
        head, value = row.xpath("./th"), row.xpath("./td")
        if head and value:
            rows.setdefault(base.txt(head[0]), value[0])
    facts = {}
    for item in tree.xpath(f"//dl[{_cls('course-facts')}]/div"):
        label, value = item.xpath("./dt"), item.xpath("./dd")
        if label and value:
            facts[base.txt(label[0])] = base.txt(value[0])

    def body(*names):
        for label, cell in rows.items():
            if any(base.fold(label).startswith(base.fold(name)) for name in names):
                return base.lines(cell)
        return ""

    weeks = []
    plan = next((cell for label, cell in rows.items() if base.fold(label).startswith("ders icerigi")), None)
    for row in plan.xpath(".//table//tr") if plan is not None else []:
        cells = row.xpath("./td")
        week = base.number(base.txt(cells[0])) if len(cells) >= 2 else None
        if week is not None:
            weeks.append((str(int(week)), base.txt(cells[1])))
    outcomes = [re.sub(r"^\d{1,2}\s*[.)]\s*", "", line) for line in body("Öğrenme Kazanımları", "Öğrenme Çıktıları").split("\n")]
    title = base.txt((tree.xpath(f"//article[{_cls('course')}]//*[{_cls('content-head__title')}]") or [None])[0])
    info = [(label, facts.get(label) or body(label)) for label in ("Dersin Dili", "Dersin Türü", "Ön Koşul", "Yarıyıl")]
    return base.detail(url, title, info=info, weeks=weeks, outcomes=[o for o in outcomes if len(o) > 8],
                       parts=[("Dersin amacı", body("Dersin Amacı")), ("Dersin içeriği", body("Ders Tanımı")),
                              ("Kaynaklar", body("Kaynak", "Ders Kitabı"))])


async def detail(http, url) -> dict | None:
    if not re.search(r"/program/\d+/ders/", url):
        return None
    return _parse_detail(await http.text(url), url)
