"""Marmara Üniversitesi — Eğitim-Öğretim Bilgi Sistemi MEOBS (meobs.marmara.edu.tr).

Yapı:
  /Program/programlar-hakkinda-bilgi/lisans-900002   → tüm lisans programları (fakülte h2 → program bağlantıları)
  /ProgramTanitim/<fakülte>/<program>-<a>-<b>-<c>    → program tanıtımı; içindeki betik güncel müfredatın kimliğini taşır
  /Mufredat/DersListesi?organizasyonId=…&programMufredatId=…  → müfredatın tamamı (dönem tabloları + seçmeli havuzları)
  /Ders/<ad>/<kod>-<dersId>-<müfredatId>             → dersin içerik sayfası (amaç, içerik, haftalar, çıktılar, değerlendirme)
Ders planı 2 istekte gelir (program sayfası + ders listesi); müfredatı yalnız alt dallarında olan bölümde dal başına 2.
"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import urljoin

from . import base

DOMAINS = ("marmara.edu.tr",)
ROOT = "https://meobs.marmara.edu.tr"
# 900002: MEOBS'ta "Lisans" düzeyinin kimliği (900001 ön lisans, 900003 yüksek lisans, 900004 doktora).
PROGRAMS = ROOT + "/Program/programlar-hakkinda-bilgi/lisans-900002"

# "Lisans( 4 yıllık, %30 İngilizce)" ya da "Ekoloji - Lisans( 4 yıllık, Türkçe)": bölüm başlığı altındaki varyant satırı.
_VARIANT = re.compile(r"^(?:(?P<track>.+?)\s+-\s+)?Lisans\(\s*(?P<years>\d+)\s*yıllık\s*,\s*(?P<lang>[^)]+?)\s*\)$")
# Program sayfasındaki betik: loadMufredatDersListesi("?organizasyonId=97&…&programMufredatId=4199&…")
_PLAN = re.compile(r"loadMufredatDersListesi\(\s*[\"'](\?[^\"']*programMufredatId=\d+[^\"']*)[\"']")
_OPTION = re.compile(r"<option[^>]*tip=[\"']Guncel[\"'][^>]*value=[\"'](\?[^\"']*programMufredatId=\d+[^\"']*)[\"']")


def _parse_programs(text: str) -> list[dict]:
    """Lisans listesi: h2 fakülte; altında ya doğrudan program bağlantısı ya da h4 bölüm adı + varyant bağlantıları.
    Adresin sonu <programId>-<birimId>-<üstBirimId>: alt dalda üstBirimId, ana programın birimId'sidir."""
    rows = []
    for link in base.parse(text).xpath('//ul[@id="panelbar"]//a[contains(@href, "/ProgramTanitim/")]'):
        label = base.txt(link)
        ids = re.search(r"-(\d+)-(\d+)-(\d+)$", link.get("href"))
        if not label or not ids or "Formasyon(" in label:  # Rektörlük altındaki pedagojik formasyon lisans programı değil
            continue
        faculty = base.txt((link.xpath("preceding::h2[contains(@class, 'UstBirimMenu')][1]") or [None])[0])
        # Varyant bağlantısı, bölüm başlığıyla (h4) aynı <li> içindedir.
        head = link.xpath("ancestor::li[h4[contains(@class, 'UstBirimMenu')]][1]/h4")
        match = _VARIANT.match(label)
        row = {"name": label, "faculty": faculty, "url": urljoin(ROOT, link.get("href")),
               "pid": int(ids[1]), "unit": int(ids[2]), "parent": int(ids[3]), "years": ""}
        if head and match:
            name, lang = base.txt(head[0]), match["lang"]
            if match["track"]:  # bölümün alt dalı (ör. İşletme - Pazarlama): ayrı müfredat
                name, row["track"] = f"{name} - {match['track']}", match["track"]
            if lang.lower() != "türkçe" and f"({lang.lower()})" not in name.lower():
                name += f" ({lang})"
            row.update(name=name, years=match["years"])
        rows.append(row)
    # Aynı fakültede aynı adla birden çok kayıt (eski/yeni program, 4 ve 5 yıllık): en yeni programId adı taşır.
    groups: dict[tuple, list[dict]] = {}
    for row in rows:
        groups.setdefault((row["faculty"], row["name"]), []).append(row)
    for same in groups.values():
        same.sort(key=lambda r: -r["pid"])
        for n, row in enumerate(same[1:], 2):
            other = row["years"] and row["years"] != same[0]["years"]
            row["name"] += f" ({row['years']} yıllık)" if other else " (eski program)" if n == 2 else f" (eski program {n - 1})"
    # Ana programın kendi müfredatı yoksa (İşletme) dersler alt dallarından okunur.
    for row in rows:
        if "track" not in row:
            tracks = [t["url"] for t in rows if "track" in t and t["pid"] == row["pid"] and t["parent"] == row["unit"]]
            if tracks:
                row["tracks"] = tracks
    return [{k: v for k, v in row.items() if k not in {"unit", "parent", "years"}} for row in rows]


def _plan_url(text: str) -> str:
    """Program sayfasından güncel müfredatın ders listesi adresi; yoksa ''. Tek müfredat betikte, birden çok müfredat
    #mufredatCombo seçeneklerinde durur (ilk "Guncel" seçenek sayfada varsayılan yüklenen)."""
    match = _PLAN.search(text) or _OPTION.search(text)
    return ROOT + "/Mufredat/DersListesi" + match[1].replace("&amp;", "&") if match else ""


def _parse_plan(text: str, url: str) -> list[dict]:
    """Ders listesi: h5 "3. Dönem" + tablo. "Seçmeli" h3'ünden sonraki tablolar havuzdur ("7. Dönem > T-E1 Teknik
    Seçimlik - I"); "Müfredattan Kaldırılmış Dersler" bölümü atlanır. Dönem tablosundaki bağlantısız seçmeli satırları
    (kod: T-E1, bağlantı: #T-E1) o dönemde alınacak seçmeli yuvasıdır ve dönemde bırakılır."""
    out, seen = [], set()
    section = ""
    for node in base.parse(text).xpath("//h3 | //h5[following-sibling::table]"):
        title = base.txt(node)
        if node.tag == "h3":
            section = "removed" if "Kaldırılmış" in title else "elective" if title.startswith("Seçmeli") else ""
            continue
        if section == "removed":
            continue
        table = node.xpath("following-sibling::table[1]")[0]
        heads = [base.txt(th) for th in table.xpath(".//thead//th")]
        col = {name: heads.index(name) for name in ("Ders Kodu", "Ders Adı", "Ders Türü", "T", "U", "Kredi", "AKTS") if name in heads}
        if "Ders Kodu" not in col or "Ders Adı" not in col:
            continue
        pool = title.split(">", 1)[1].strip() if section == "elective" and ">" in title else ""
        when = base.period(elective=True) if section == "elective" else base.period(title)
        for row in table.xpath(".//tbody/tr"):
            cells = row.xpath("./td")
            if len(cells) < len(heads) - 1:  # "Toplam" satırı
                continue

            def get(name):
                return base.txt(cells[col[name]]) if name in col else ""

            code, name = get("Ders Kodu"), get("Ders Adı")
            href = (cells[col["Ders Kodu"]].xpath(".//a/@href") or [""])[0]
            link = urljoin(ROOT, href) if href.startswith("/Ders/") else ""
            if not code or not name or (code, when) in seen:
                continue
            seen.add((code, when))
            kind = " · ".join(x for x in (get("Ders Türü"), pool) if x)
            hours = f"{get('T')}+{get('U')}" if get("T") else ""
            credit = base._num(get("Kredi"))
            out.append(base.course(code, name, when, ects=get("AKTS"), credit=f"{credit} ({hours})" if credit and hours else credit,
                                   kind=kind, url=link, source=url))
    return out


def _parse_detail(text: str, url: str) -> dict | None:
    """Ders sayfası: üstte özet tablosu, "Dersin İçeriği" altında FieldsetBaslik + <p> çiftleri, sonra öğrenme
    çıktıları (ul.numberList), haftalık içerik tablosu, #degerlendirme ve #isYuku tabloları."""
    tree = base.parse(text)
    summary = tree.xpath('//article[@id="bbicerik"]/table[1]')
    heads = [base.txt(td) for td in summary[0].xpath("./tr[1]/td|./tbody/tr[1]/td")] if summary else []
    values = [base.txt(td) for td in summary[0].xpath("./tr[2]/td|./tbody/tr[2]/td")] if summary else []
    top = dict(zip(heads, values))
    info = [(key, top.get(key, "")) for key in ("Ders Türü", "Dönem", "AKTS", "Teorik", "Uygulama", "Müfredat Adı")]
    parts = []
    for head in tree.xpath('//div[contains(@class, "FieldsetBaslik")]'):
        label = base.txt(head)
        body = head.xpath("following-sibling::*[1][self::p]")
        value = base.lines(body[0]) or base.txt(body[0]) if body else ""
        if not value or value in {"-", "Yok"}:
            continue
        if label in {"Dersin Sunulduğu Dil", "Öğrenim Türü", "Staj Durumu"}:
            info.append((label, value))
        else:
            parts.append((label, value))
    outcomes = [base.txt(li) for li in tree.xpath('//ul[contains(@class, "numberList")]/li')]
    weeks = []
    for table in tree.xpath('//table[contains(@class, "fullTable")][.//th[1][normalize-space()="Hafta"]]'):
        for row in table.xpath(".//tr[td]"):
            cells = [base.txt(td) for td in row.xpath("./td")]
            topic = " / ".join(dict.fromkeys(c for c in cells[1:] if c))  # Teorik / Uygulama / Laboratuvar sütunları
            if cells and topic:
                weeks.append((cells[0], topic))
    # Değerlendirme: ilk başlık satırından sonraki satırlar yıl içi / yıl sonu ağırlığıdır; sonraki başlıklar alt dökümdür.
    assessment = []
    for row in tree.xpath('//div[@id="degerlendirme"]//table//tr')[1:]:
        if row.xpath("./th"):
            break
        cells = [base.txt(td) for td in row.xpath("./td")]
        if len(cells) >= 2:
            assessment.append((cells[0], cells[1]))
    hours = sum(base.number(base.txt(row.xpath("./td[last()]")[0])) or 0 for row in tree.xpath('//div[@id="isYuku"]//table//tr[td]'))
    workload = {"hours": base._num(hours), "ects": base._num(top.get("AKTS"))} if hours else None
    title = " ".join(x for x in (top.get("Ders Kodu", ""), top.get("Ders Adı", "")) if x)
    return base.detail(url, title, info=info, parts=parts, weeks=weeks, outcomes=outcomes, assessment=assessment, workload=workload)


async def programs(http) -> list[dict]:
    """Tüm lisans programları (fakülte ve yüksekokullar); tek istek."""
    return _parse_programs(await http.text(PROGRAMS))


async def _plan(http, page: str) -> list[dict]:
    plan = _plan_url(await http.text(page))
    return _parse_plan(await http.text(plan), plan) if plan else []


async def courses(http, program) -> list[dict]:
    """Program sayfasından güncel müfredat kimliği, ardından ders listesi (toplam 2 istek). Programın kendi müfredatı
    yoksa alt dallarının müfredatları paralel okunup birleştirilir (ortak dersler bir kez)."""
    items = await _plan(http, program["url"])
    if items or not program.get("tracks"):
        return items
    out, seen = [], set()
    for rows in await asyncio.gather(*(_plan(http, url) for url in program["tracks"]), return_exceptions=True):
        for item in rows if isinstance(rows, list) else []:
            if (item["code"], item["period"]) not in seen:
                seen.add((item["code"], item["period"]))
                out.append(item)
    order = {base.period(n): n for n in range(1, 15)}
    out.sort(key=lambda item: order.get(item["period"], 99))  # dallar birleşince dönem sırası korunur
    return out


async def detail(http, url) -> dict | None:
    return _parse_detail(await http.text(url), url)
