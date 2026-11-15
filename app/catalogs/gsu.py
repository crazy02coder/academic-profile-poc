"""Galatasaray Üniversitesi — AKTS Bilgilendirme Sistemi (ects.gsu.edu.tr).

Yapı: /tr ana sayfası tüm programları öğretim düzeyine ve fakülteye göre listeler (tek istek);
/tr/program/programmedetails/<id> programın sekiz yarıyıllık ders planını ve "Ortak Bölüm Dersleri" seçmeli
havuzunu tek sayfada verir; /tr/program/coursedetails/<ders id> tek dersin içeriğidir.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from . import base

DOMAINS = ("gsu.edu.tr",)
ROOT = "https://ects.gsu.edu.tr"
HOME = ROOT + "/tr"

# Program adının sonundaki tür eki: "Bilgisayar Mühendisliği Lisans Programı", "… Bölümü".
_SUFFIX = re.compile(r"\s+(Lisans\s+Programı|Programı|Bölümü)\s*$", re.I)


async def programs(http) -> list[dict]:
    return _parse_programs(await http.text(HOME))


def _parse_programs(text: str) -> list[dict]:
    """Ana sayfadaki "Lisans" sekmesi: div.gsu-level[data-level=lisans] > div.gsu-group (fakülte) > a.gsu-prog."""
    tree = base.parse(text)
    rows = []
    for group in tree.xpath('//div[contains(@class,"gsu-level")][@data-level="lisans"]//div[contains(@class,"gsu-group")][@data-name]'):
        faculty = base.txt(group.get("data-name"))
        found = []
        for link in group.xpath('.//a[contains(@class,"gsu-prog")][@href]'):
            match = re.search(r"/program/index/(\d+)", link.get("href"))
            if not match:
                continue
            name = _SUFFIX.sub("", base.txt(link))
            found.append({"name": name, "faculty": faculty, "id": match[1],
                          "url": f"{ROOT}/tr/program/programmedetails/{match[1]}"})
        if len(found) == 1:
            # Tek programlı fakülte (Hukuk, İletişim): bölüm adı fakülte adıyla da aranabilir.
            short = re.sub(r"\s+Fakültesi$", "", faculty)
            found[0]["aliases"] = [n for n in (short, faculty) if n and n != found[0]["name"]]
        rows.extend(found)
    return rows


async def courses(http, program) -> list[dict]:
    url = program["url"]
    return _parse_plan(await http.text(url), url)


def _parse_plan(text: str, url: str) -> list[dict]:
    """Her table.gsu-plan bir yarıyıldır; başlığı <caption>'dadır ("3. Yarıyıl" ya da "Ortak Bölüm Dersleri").
    Sütunlar başlıktan okunur: yarıyıl tablolarında "Ön Koşul" sütunu var, ortak dersler tablosunda yok."""
    tree = base.parse(text)
    out, seen = [], set()
    for table in tree.xpath('//table[contains(@class,"gsu-plan")]'):
        caption = base.txt((table.xpath("./caption/text()") or [""])[0])
        match = re.match(r"(\d+)\.\s*Yarıyıl", caption)
        period = base.period(match[1]) if match else base.period(elective=True)
        heads = [base.txt(th) for th in table.xpath("./thead/tr/th")]
        col = {name: i for i, name in enumerate(heads)}
        for tr in table.xpath("./tbody/tr[not(contains(@class,'aciklama'))]"):
            cells = tr.xpath("./td")
            if len(cells) < len(heads) or "Ders Kodu" not in col:
                continue
            get = lambda name: base.txt(cells[col[name]]) if name in col else ""  # noqa: E731
            code, name = get("Ders Kodu"), get("Dersin Adı")
            href = (cells[col["Ders Kodu"]].xpath(".//a/@href") or [""])[0]
            # Ortak derslerin bağlantısı "?from=<program>" taşır; içerik aynı olduğundan atılır.
            link = urljoin(url, href.split("?")[0]) if href else ""
            if not code or not name or (code, period) in seen:
                continue
            seen.add((code, period))
            hours = "+".join(get(k) or "0" for k in ("Teori", "Uygulama", "Lab"))
            out.append(base.course(code, name, period, ects=get("AKTS"), credit=hours, kind=get("Türü"),
                                   url=link, source=url))
    return out


async def detail(http, url) -> dict | None:
    return _parse_detail(await http.text(url), url)


def _rows(table) -> list[list[str]]:
    return [[base.txt(td) for td in tr.xpath("./td")] for tr in table.xpath("./tbody/tr[not(contains(@class,'toplam'))]")]


def _parse_detail(text: str, url: str) -> dict | None:
    tree = base.parse(text)
    title = base.txt((tree.xpath('//h1[contains(@class,"gsu-h1")]') or [None])[0])
    if not title:
        return None
    info = [(base.txt(dt), base.txt(dd)) for dt, dd in
            zip(tree.xpath('//dl[contains(@class,"gsu-meta")]//dt'), tree.xpath('//dl[contains(@class,"gsu-meta")]//dd'))]
    info = [(a, b) for a, b in info if b not in {"", "-"}]
    # Başlığın altındaki satır: "Zorunlu · Fransızca" (tür ve öğretim dili).
    head = [base.txt(s).lstrip("· ") for s in tree.xpath('//div[contains(@class,"gsu-head-alt")]/span[not(contains(@class,"gsu-badge"))]')]
    for label, value in zip(("Türü", "Dil"), head):
        info.append((label, value))
    teachers = [base.txt(s) for s in tree.xpath('//div[contains(@class,"gsu-side-box-b")]//strong')]
    if teachers:
        info.append(("Dersi veren", ", ".join(teachers)))

    # İçerik bölümü: h2#amac / h3 başlıkları ve hemen ardından gelen <p>.
    parts, outcomes = [], []
    for head_node in tree.xpath('//div[contains(@class,"gsu-prose")]/*[self::h2 or self::h3]'):
        heading = base.txt(head_node)
        nxt = head_node.getnext()
        if nxt is None or nxt.tag != "p":
            continue
        body = base.lines(nxt)
        if not body:
            continue
        if "Öğrenme Çıktıları" in heading:
            outcomes = [row for row in body.split("\n") if row]
        else:
            parts.append((heading, body))

    weeks, marks, workload = [], [], {}
    for table in tree.xpath('//div[contains(@class,"gsu-prose")]//table[contains(@class,"gsu-table")]'):
        caption = base.txt((table.xpath("./caption") or [None])[0])
        heads = [base.txt(th) for th in table.xpath("./thead/tr/th")]
        if caption == "Teori Konu Başlıkları" or (caption.endswith("Konu Başlıkları") and not weeks):
            weeks = [(row[0], row[1]) for row in _rows(table) if len(row) >= 2 and row[1]]
        elif caption == "Yarıyıl İçi Çalışmaları":
            # Yarıyıl içi etkinliklerin dökümü; oranlar yarıyıl içi payın içindedir, ayrı gösterilir.
            used = [f"{row[0]}: {row[1]} adet, %{row[2]}" for row in _rows(table) if len(row) >= 3 and base.number(row[2])]
            if used:
                parts.append(("Yarıyıl içi çalışmaları", "\n".join(used)))
        elif caption == "Başarı Notuna Etki Oranları":
            marks = [(row[0], row[2], row[1]) for row in _rows(table) if len(row) >= 3]
        elif "Toplam İş Yükü" in heads:
            total = table.xpath("./tbody/tr[contains(@class,'toplam')]")
            for tr in total:
                label, value = base.txt(tr.xpath("./td")[0]), base.txt(tr.xpath("./td")[-1])
                if label == "Toplam İş Yükü":
                    workload["hours"] = value
                elif label == "Dersin AKTS Kredisi":
                    workload["ects"] = value
    return base.detail(url, title, info=info, parts=parts, weeks=weeks, outcomes=outcomes, assessment=marks, workload=workload)
