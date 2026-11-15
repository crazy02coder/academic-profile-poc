"""İstanbul Teknik Üniversitesi — ÖBS herkese açık sayfalar (obs.itu.edu.tr/public).

Yapı:
  DersPlan                                              akademik birim listesi (select#akademikBirimId)
  POST DersPlan/GetAkademikProgramByBirimIdAndPlanTipi  birimId + planTipiKodu → JSON [{programKodu, programAdi}]
  DersPlan/DersPlanlariList?FakulteId=&PlanTipiKodu=&programKodu=   programın yıllara göre planları (DersPlanDetay/<id>)
  DersPlan/DersPlanDetay/<id>                           plan: yarıyıl tabloları; seçmeli yuvaları "Dersler" bağlantısı
  DersPlan/_DersGrupSearch?grupId=&dersTipiId=          seçmeli yuvasının ders havuzu
  DersKatalog/DersKatalogBilgiBransDersKodu?bransKodu=&dersNo=   ders katalog formu (tanım, amaç, çıktı, haftalık plan)
  DersBilgi/DersBilgiSearch?bransKodu=&dersNo=          kısa ders bilgisi (katalog formu yoksa yedek)
"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

from ..text import fold
from . import base

DOMAINS = ("itu.edu.tr",)
PARALLEL = 6
BASE = "https://obs.itu.edu.tr/public/"
# Plan tipi kodları (select#planTipiId): lisans ve uluslararası ortak lisans programları (UOLP).
PLAN_TYPES = ("lisans", "uolp")
_CODE = re.compile(r"^([A-ZÇĞİÖŞÜ]{2,4})\s*(\d{3,4})(E?)([A-Z]*)$")


def _parse_units(text: str) -> list[tuple[str, str]]:
    """Lisans programı olabilecek birimler: (birim kimliği, ad). Enstitüler ve meslek yüksekokulu alınmaz."""
    units = []
    for option in base.parse(text).xpath('//select[@id="akademikBirimId"]/option[@value!=""]'):
        name = base.txt(option).replace(" - ", "-")
        if "enstitu" in fold(name) or "meslek yuksekokulu" in fold(name):
            continue
        units.append((option.get("value"), name))
    return units


def _plan_list_url(unit: str, plan_type: str, code: str) -> str:
    return f"{BASE}DersPlan/DersPlanlariList?" + urlencode({"FakulteId": unit, "PlanTipiKodu": plan_type, "programKodu": code})


def _parse_programs(rows: list, unit: str, faculty: str, plan_type: str) -> list[dict]:
    """JSON program listesi → program kayıtları. Sitedeki ad "… Mühendisliği (İngilizce) Lisans" biçimindedir."""
    out = []
    for row in rows or []:
        code, name = str(row.get("programKodu") or ""), base.txt(row.get("programAdi") or "")
        name = re.sub(r"\s+Lisans$", "", name)
        if code and name:
            out.append({"name": name, "faculty": faculty, "url": _plan_list_url(unit, plan_type, code), "aliases": [],
                        "code": code, "unit": unit, "plan_type": plan_type})
    return out


def _mark_variants(rows: list[dict]) -> list[dict]:
    """İTÜ'de aynı programın "(İngilizce)" (%100) eşi varsa işaretsiz olan %30 İngilizce programdır: adı
    "… (%30 İngilizce)" yapılır, işaretsiz ad takma ad olarak kalır (veri setinde bölüm işaretsiz geçer)."""
    names = {(row["faculty"], row["name"]) for row in rows}
    for row in rows:
        if "(" not in row["name"] and (row["faculty"], f'{row["name"]} (İngilizce)') in names:
            row["aliases"] = [row["name"]]
            row["name"] = f'{row["name"]} (%30 İngilizce)'
    return rows


def _latest_plan(text: str, url: str) -> str:
    """Plan listesinden en güncel planın adresi: "… Dönemi Sonrası" olan, yoksa en ileri yılı anan, yoksa son satır."""
    best = None
    for index, row in enumerate(base.parse(text).xpath('//tr[.//a[contains(@href, "DersPlanDetay/")]]')):
        title = base.txt(row)
        years = [int(year) for year in re.findall(r"\b(?:19|20)\d\d\b", title)]
        key = ("sonras" in fold(title), max(years, default=0), index)
        if best is None or key > best[0]:
            best = (key, urljoin(url, row.xpath('.//a[contains(@href, "DersPlanDetay/")]/@href')[0]))
    return best[1] if best else ""


def _catalog_url(code: str, href: str = "") -> str:
    """Dersin katalog formu adresi. Plandaki bağlantı (DersBilgi?bransKodu=BLG&dersNo=101) varsa ondan, yoksa koddan:
    "BLG 448E" → BLG/448, "FIZ 101EL" → FIZ/101L (rakamdan hemen sonraki E "İngilizce verilen şube" ekidir)."""
    query = parse_qs(urlsplit(href).query) if href else {}
    branch, number = (query.get("bransKodu") or [""])[0], (query.get("dersNo") or [""])[0]
    if not (branch and number):
        match = _CODE.match(code.strip())
        if not match:
            return ""
        branch, number = match[1], match[2] + match[4]
    return f"{BASE}DersKatalog/DersKatalogBilgiBransDersKodu?" + urlencode({"bransKodu": branch, "dersNo": number})


def _parse_plan(text: str, url: str) -> tuple[list[dict], list[dict]]:
    """Plan sayfası → (zorunlu ders kayıtları, seçmeli yuvaları [{"name", "url", "type"}])."""
    tree = base.parse(text)
    items, groups, label = [], [], ""
    for node in tree.iter("h2", "tr"):
        if node.tag == "h2":
            match = re.match(r"\s*(\d+)\.\s*(?:Yar|Sem)", base.txt(node))  # "3. Yarıyıl" / "3. Semester"
            label = base.period(match[1]) if match else label
            continue
        cells = node.xpath("./td")
        if len(cells) < 6:
            continue
        href = (cells[0].xpath(".//a/@href") or [""])[0]
        name = base.txt(cells[1])
        if "_DersGrupSearch" in href:
            kind = (parse_qs(urlsplit(href).query).get("dersTipiId") or [""])[0]
            groups.append({"name": name, "url": urljoin(url, href), "type": kind})
            continue
        code = base.txt(cells[0])
        if not code:
            continue
        kind = {"Z": "Zorunlu", "S": "Seçmeli"}.get(base.txt(cells[3]), "")
        items.append(base.course(code, name, label, ects=base.txt(cells[5]), credit=base.txt(cells[4]), kind=kind,
                                 url=_catalog_url(code, href), source=url))
    return items, groups


def _parse_group(text: str, url: str, name: str = "") -> list[dict]:
    """Seçmeli havuzu: ilk hücrede "KOD <br> Ad", ardından dil, kredi, AKTS."""
    family = re.search(r"\(([A-ZİÜ]{2,4})\)\s*$", name)  # "(TM)", "(MT)", "(ITB)": ders türü kısaltması
    kind = f"Seçmeli ({family[1]})" if family else f"Seçmeli · {name}" if name else "Seçmeli"
    items = []
    for row in base.parse(text).xpath("//table//tr[td]"):
        cells = row.xpath("./td")
        head = base.lines(cells[0]).split("\n") if cells else []
        if len(cells) < 4 or len(head) < 2:
            continue
        items.append(base.course(head[0], " ".join(head[1:]), base.period(elective=True), ects=base.txt(cells[3]),
                                 credit=base.txt(cells[2]), kind=kind, url=_catalog_url(head[0]), source=url))
    return items


def _parse_detail(text: str, url: str) -> dict | None:
    """Ders katalog formu. Her alan iki satırdır (üstte Türkçe, altta İngilizce); Türkçesi boşsa İngilizcesi alınır."""
    tree = base.parse(text)
    title = language = unit = ""
    code_row: list[str] = []
    fields: dict[str, list] = {}  # etiket anahtarı → [Türkçe hücre, İngilizce hücre]
    weeks = {"tr": [], "en": []}
    mode, pending = "", ""
    for row in tree.xpath("//table//tr[not(.//table)]"):
        heads, cells = row.xpath("./th"), row.xpath("./td")
        first = base.txt(heads[0]) if heads else ""
        if heads and not cells:
            mode = {"ders plani": "tr", "course plan": "en"}.get(fold(first), mode)
            pending = ""
            continue
        if heads and first.isdigit():  # haftalık plan satırı: hafta | konu | ilgili çıktılar
            if mode:
                weeks[mode].append((first, base.txt(cells[0])))
            continue
        if heads:
            pending = fold(first)
            fields[pending] = [cells[0]]
            continue
        texts = [base.txt(cell) for cell in cells]
        if pending and len(cells) == 1 and len(fields[pending]) == 1 and not texts[0].startswith("Sınıf önşartı"):
            fields[pending].append(cells[0])  # alanın İngilizce satırı
            continue
        for value in texts:
            if value.startswith("Dersin Adı"):
                title = value.split(":", 1)[-1].strip()
            elif value.startswith("Dersin Dili"):
                language = value.split(":", 1)[-1].strip()
            elif value.startswith("Bölüm / Program"):
                unit = re.split(r"\s*Department / Program", value.split(":", 1)[-1])[0].strip()
        if len(texts) == 6 and re.match(r"[A-ZÇĞİÖŞÜ]{2,4}\s?\d{3}", texts[0]):
            code_row = texts

    def field(*keys: str):
        """Etiketi verilen anahtarlardan birini içeren alanın dolu olan ilk hücresi (önce Türkçe)."""
        for key in keys:
            for label, nodes in fields.items():
                if key in label:
                    for node in nodes:
                        if base.txt(node):
                            return node
        return None

    def text_of(*keys: str) -> str:
        return base.lines(field(*keys))

    if not title and not fields:
        return None
    outcomes_node = field("ciktilari", "learning outcomes")
    outcomes = [base.txt(li) for li in outcomes_node.xpath(".//li")] if outcomes_node is not None else []
    if not outcomes and outcomes_node is not None:
        outcomes = base.lines(outcomes_node).split("\n")
    prerequisite = re.sub(r"^Ders önşartı \(Course prerequisite\)\s*", "", base.txt(field("onsart")))
    info = []
    if code_row:
        info = [("Kod", code_row[0]), ("Kredi", code_row[1]), ("AKTS", code_row[2]),
                ("Ders / Uygulama / Lab. (saat/hafta)", " / ".join(code_row[3:6]))]
    info += [("Öğretim dili", language), ("Bölüm / Program", unit), ("Ön koşul", prerequisite)]
    parts = [("Dersin tanımı", text_of("dersin tanimi", "course description")),
             ("Dersin amacı", text_of("dersin amaci", "course objectives")),
             ("Ders kitabı", text_of("ders kitabi", "textbook")),
             ("Diğer kaynaklar", text_of("diger kaynaklar", "other references")),
             ("Ödevler ve projeler", text_of("odevler")),
             ("Laboratuvar uygulamaları", text_of("laboratuar uygulamalari")),
             ("Bilgisayar kullanımı", text_of("bilgisayar kullanimi")),
             ("Diğer uygulamalar", text_of("diger uygulamalar"))]
    code = (code_row[0].split("-")[0].strip() + " ") if code_row else ""
    return base.detail(url, f"{code}{title}", info=info, parts=parts, weeks=weeks["tr"] or weeks["en"], outcomes=outcomes)


def _parse_brief(text: str, url: str) -> dict | None:
    """DersBilgiSearch parçası (katalog formu olmayan ders): ad, kredi, ön koşul ve ders tanımı."""
    rows = [[base.txt(cell) for cell in row.xpath("./td|./th")] for row in base.parse(text).xpath("//tr[not(.//table)]")]
    title, info, parts = "", [], []
    for index, cells in enumerate(rows):
        following = rows[index + 1] if index + 1 < len(rows) else []
        if cells[:2] == ["Ders Kodu", "Ders Adı"] and len(following) >= 3:
            title = f"{following[0]} {following[1]}"
            info.append(("Öğretim dili", following[2]))
        elif cells[:2] == ["Kredi", "AKTS"] and len(following) >= 2:
            info += [("Kredi", following[0]), ("AKTS", following[1])]
        elif cells and cells[0] == "Ders Önşartları" and len(cells) > 1:
            info.append(("Ön koşul", cells[1]))
        elif cells == ["Ders Tanımı"] and following:
            parts.append(("Dersin tanımı", following[0]))
    return base.detail(url, title, info=info, parts=parts)


async def programs(http) -> list[dict]:
    """Birim listesi (1 istek) + her birim için lisans ve UOLP program listesi (birim başına 2 küçük JSON isteği)."""
    units = _parse_units(await http.text(f"{BASE}DersPlan"))
    endpoint = f"{BASE}DersPlan/GetAkademikProgramByBirimIdAndPlanTipi"

    async def one(unit: str, faculty: str, plan_type: str) -> list[dict]:
        try:
            rows = await http.json(endpoint, data={"birimId": unit, "planTipiKodu": plan_type})
        except Exception:  # noqa: BLE001 — tek birimin hatası listeyi düşürmez
            return []
        return _parse_programs(rows if isinstance(rows, list) else [], unit, faculty, plan_type)

    found = await asyncio.gather(*(one(unit, faculty, plan_type) for plan_type in PLAN_TYPES for unit, faculty in units))
    return _mark_variants([row for rows in found for row in rows])


async def courses(http, program) -> list[dict]:
    """Plan listesi → en güncel plan → seçmeli havuzları (2 istek + farklı her seçmeli türü için 1 paralel istek).
    Aynı planda aynı dersTipiId'li yuvalar (ör. her yarıyılın ITB seçmelisi) aynı havuzu gösterir; biri okunur."""
    list_url = program.get("url") or _plan_list_url(program["unit"], program.get("plan_type") or "lisans", program["code"])
    plan_url = _latest_plan(await http.text(list_url), list_url)
    if not plan_url:
        return []
    items, groups = _parse_plan(await http.text(plan_url), plan_url)
    pools: dict[str, dict] = {}
    for group in groups:
        pools.setdefault(group["type"] or group["url"], group)  # her türün ilk yuvası
    pools = list(pools.values())
    pages = await asyncio.gather(*(http.text(group["url"]) for group in pools), return_exceptions=True)
    seen = {item["code"] for item in items}
    for group, page in zip(pools, pages):
        if not isinstance(page, str):
            continue
        for item in _parse_group(page, group["url"], group["name"]):
            if item["code"] not in seen:
                seen.add(item["code"])
                items.append(item)
    return items


async def detail(http, url) -> dict | None:
    """Katalog formu (1 istek); form boşsa aynı dersin kısa bilgisi (1 istek daha)."""
    found = _parse_detail(await http.text(url), url) if "DersKatalog" in url else None
    if found:
        return found
    query = urlsplit(url).query
    if "bransKodu" not in query:
        return None
    brief_url = f"{BASE}DersBilgi/DersBilgiSearch?{query}"
    return _parse_brief(await http.text(brief_url), url)
