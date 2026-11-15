"""Ege Üniversitesi — Eğitim Bilgi Paketi (ebp.ege.edu.tr; sunucuda üretilen HTML, UTF-8).

  /DereceProgramlari/GetJson/1?lang=tr-TR  lisans program ağacı (jstree JSON): fakülte > bölüm > (program) > lisans
  /DereceProgramlari/Detay/1/…             program sayfası: her müfredat div#accordion-mufredat içinde tek tablo;
                                           gruplar <thead><th colspan> ("1. Dönem", "TEG - TECHNICAL ELECTIVE") ile ayrılır
  /DereceProgramlari/Ders/1/…              ders sayfası: başlıklar <h3 class="sidebar-title">, haftalık plan tablo

Ders planı tek istekte gelir (program sayfası); ders içeriği dersin kendi sayfasından tembel okunur.
"""
from __future__ import annotations

import json
import re
from urllib.parse import urljoin

from . import base

DOMAINS = ("ege.edu.tr",)
BASE = "https://ebp.ege.edu.tr"
TREE = f"{BASE}/DereceProgramlari/GetJson/1?lang=tr-TR"
_SEMESTER = re.compile(r"^(\d{1,2})\s*\.\s*(?:Dönem|Yarıyıl)", re.I)
_SECONDARY = re.compile(r"yan\s*dal|çift\s*ana\s*dal|çap\b", re.I)  # yan dal / çift anadal müfredatları ana plan değildir


def _walk(nodes, path):
    for node in nodes or []:
        current = path + [base.txt(str(node.get("text") or ""))]
        if node.get("children"):
            yield from _walk(node["children"], current)
        else:
            href = (node.get("a_attr") or {}).get("href") or ""
            if href and href != "#":
                yield current, href


def _parse_programs(text: str) -> list[dict]:
    rows = []
    for path, href in _walk(json.loads(text), []):
        faculty = path[0] if path else ""
        if len(path) >= 3:
            # fakülte > bölüm > "Lisans (İngilizce)" yaprağı: program adı bölümün adıdır, yaprak yalnız varyantı verir.
            name, leaf = path[-2], path[-1]
            variant = re.search(r"\(([^)]+)\)", leaf)
            name = f"{name} ({variant[1]})" if variant else name
        else:
            name = path[-1] if path else ""
        if name:
            rows.append({"name": name, "faculty": faculty, "url": urljoin(BASE, href)})
    return rows


async def programs(http) -> list[dict]:
    return _parse_programs(await http.text(TREE, headers={"X-Requested-With": "XMLHttpRequest"}))


def _parse_plan(text: str, url: str) -> list[dict]:
    tree = base.parse(text)
    items = []
    for table in tree.xpath("//table[.//a[contains(@href, '/DereceProgramlari/Ders/')]][not(ancestor::table)]"):
        heading = table.xpath("ancestor::*[@id='accordion-mufredat'][1]//*[self::h3 or self::h4][1]")
        if heading and _SECONDARY.search(base.txt(heading[0])):
            continue
        group = ""
        for node in table.xpath(".//thead|.//tr[not(ancestor::thead)]"):
            if node.tag == "thead":
                title = node.xpath(".//th[@colspan]")
                if title:
                    group = base.txt(title[0])
                continue
            cells = node.xpath("./td")
            if len(cells) < 8:
                continue
            link = cells[0].xpath(".//a[contains(@href, '/DereceProgramlari/Ders/')]")
            if not link:
                continue  # "Toplam" satırı ya da seçmeli grup yer tutucusu
            match = _SEMESTER.match(group)
            items.append(base.course(base.txt(link[0]), base.txt(cells[2]),
                                     base.period(match[1]) if match else base.period(elective=True),
                                     ects=base.txt(cells[7]), kind="" if match else group,
                                     url=urljoin(BASE, link[0].get("href").strip()), source=url))
    unique = {}
    for item in items:
        unique.setdefault((item["code"], item["period"]), item)
    return list(unique.values())


async def courses(http, program) -> list[dict]:
    return _parse_plan(await http.text(program["url"]), program["url"])


def _sections(tree) -> dict:
    """{başlık: [başlıktan sonraki, bir sonraki başlığa kadar olan düğümler]}"""
    out = {}
    for heading in tree.xpath("//h3[contains(concat(' ', normalize-space(@class), ' '), ' sidebar-title ')]"):
        title = base.txt(heading)
        parent = heading.getparent()
        start = parent if parent is not None and "content-box" in (parent.get("class") or "") else heading
        nodes = []
        for sibling in start.itersiblings():
            if not isinstance(sibling.tag, str):
                continue
            if sibling.xpath("self::h3[contains(@class, 'sidebar-title')]|.//h3[contains(@class, 'sidebar-title')]"):
                break
            nodes.append(sibling)
        if title:
            out.setdefault(title, nodes)
    return out


def _parse_detail(text: str, url: str) -> dict | None:
    tree = base.parse(text)
    sections = _sections(tree)

    def body(*names):
        for title, nodes in sections.items():
            if any(title.startswith(name) for name in names):
                return "\n".join(x for x in (base.lines(n) for n in nodes if n.tag not in {"hr", "table"}) if x)
        return ""

    weeks = []
    for title, nodes in sections.items():
        if not title.startswith("Haftalık"):
            continue
        for node in nodes:
            for row in node.xpath("self::table//tr|.//table//tr"):
                cells = row.xpath("./td")
                week = base.number(base.txt(cells[0])) if len(cells) >= 2 else None
                if week is None:
                    continue
                topic = base.txt(cells[1]) or (base.txt(cells[2]) if len(cells) > 2 else "")
                weeks.append((str(int(week)), topic))
        break
    header = {}
    for table in tree.xpath("//table[.//thead//th]"):
        labels = [base.txt(th) for th in table.xpath(".//thead//th")]
        if "Dersin Kodu" in labels and "AKTS" in labels:
            row = table.xpath(".//tbody/tr") or table.xpath(".//tr[td]")
            if row:
                header = dict(zip(labels, [base.txt(td) for td in row[0].xpath("./td")]))
            break
    outcomes = [line for line in body("Dersin Öğrenme Çıktıları", "Öğrenme Çıktıları").split("\n") if len(line) > 8]
    info = [(label, header.get(label, "")) for label in ("Dersin Türü", "Dersin Dili", "Yıl", "Yarıyıl") if header.get(label)]
    title = f"{header.get('Dersin Kodu', '')} {header.get('Dersin Adı', '')}".strip()
    return base.detail(url, title, info=info, weeks=weeks, outcomes=outcomes,
                       parts=[("Dersin amacı", body("Dersin Amacı")), ("Dersin içeriği", body("Dersin İçeriği")),
                              ("Ön koşullar", body("Ön Koşul")), ("Kaynaklar", body("Ders Kitabı", "Önerilen", "Kaynak"))])


async def detail(http, url) -> dict | None:
    if "/DereceProgramlari/Ders/" not in url:
        return None
    return _parse_detail(await http.text(url), url)
