"""Sabancı Üniversitesi — SUIS diploma programı gereksinimleri (suis.sabanciuniv.edu/prod).

Yapı (hepsi düz GET; P_LANG=TR Türkçe, EN İngilizce ad verir):
  SU_DEGREE.p_list_degree?P_LEVEL=UG                         → lisans diploma programları (P_PROGRAM kodu: BSCS, BAECON…)
  SU_DEGREE.p_select_term?P_PROGRAM=…                        → giriş dönemi seçimi; seçili gelen dönem günceldir (202601)
  SU_DEGREE.p_degree_detail?P_PROGRAM=…&P_TERM=…             → mezuniyet koşulları: kategori başlıkları altında üniversite
                                                               dersleri ve zorunlu dersler; seçmeli havuzları ayrı bağlantı
  SU_DEGREE.p_list_courses?P_AREA=…                          → bir seçmeli havuzunun dersleri (çekirdek / alan seçmeli)
  sabanci_www.p_get_courses?subj_code=…&crse_numb=…&lang=tur → dersin tanımı, ön/yan koşul, AKTS, açıldığı dönemler
Sabancı'da dönemlik sabit ders planı yoktur (program sonradan seçilir, dersler kategoriye göre tamamlanır): zorunlu ve
üniversite dersleri dönemsiz, havuz dersleri "Seçmeli dersler" olarak verilir; kategori ders türüne yazılır.
"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import urljoin

from . import base

DOMAINS = ("sabanciuniv.edu",)
ROOT = "https://suis.sabanciuniv.edu/prod/"
PARALLEL = 4
# Diploma programı → fakülte (program kodunda fakülte bilgisi yok; BS… programları MDBF'dedir).
_FENS, _FASS, _SOM = "Mühendislik ve Doğa Bilimleri Fakültesi", "Sanat ve Sosyal Bilimler Fakültesi", "Yönetim Bilimleri Fakültesi"
_FACULTY = {"BAECON": _FASS, "BAPSIR": _FASS, "BAPSY": _FASS, "BAVACD": _FASS, "BAMAN": _SOM}
_OLD_NAME = re.compile(r"\s*\((?:Önceki(?: İsim)?|Previous Name|Pre\. Name)\s*:\s*([^)]*)\)?")


def _names(raw: str) -> list[str]:
    """'Endüstri Mühendisliği (Önceki İsim: Üretim Sistemleri Mühendisliği)' → [güncel ad, önceki ad]."""
    text = base.txt(raw)
    old = _OLD_NAME.search(text)
    return [name for name in [_OLD_NAME.sub("", text).strip(), old[1].strip() if old else ""] if name]


def _parse_list(text: str) -> dict[str, list[str]]:
    """Program listesi: {P_PROGRAM kodu: [ad, önceki ad]}."""
    out = {}
    for link in base.parse(text).xpath("//a[contains(@href,'P_PROGRAM=')]"):
        code = re.search(r"P_PROGRAM=(\w+)", link.get("href"))
        if code and _names(base.txt(link)):
            out[code[1]] = _names(base.txt(link))
    return out


def _parse_term(text: str) -> str:
    """Giriş dönemi listesinde seçili gelen dönem kodu (yıl + 01 güz / 02 bahar / 03 yaz)."""
    chosen = base.parse(text).xpath("//select[@name='P_TERM']/option[@selected]/@value")
    return chosen[0].strip() if chosen else ""


def _parse_programs(turkish: str, english: str, term: str) -> list[dict]:
    names = _parse_list(english)
    out = []
    for code, (name, *old) in _parse_list(turkish).items():
        aliases = [alias for alias in [*old, *names.get(code, [])] if alias != name]
        out.append({"name": name, "faculty": _FACULTY.get(code, _FENS), "aliases": aliases, "code": code, "term": term,
                    "url": _plan_url(code, term)})
    return out


def _plan_url(code: str, term: str) -> str:
    return f"{ROOT}SU_DEGREE.p_degree_detail?P_PROGRAM={code}&P_LANG=TR&P_LEVEL=UG&P_TERM={term}&P_SUBMIT=Select"


def _rows(tree, url: str, kind: str, period: str) -> list[dict]:
    """Ders tablosu satırları: [işaret | kod | ad | AKTS | SU kredisi | fakülte]; kod ve ad ders sayfasına bağlıdır."""
    out = []
    for row in tree.xpath(".//tr[td//a[contains(@href,'p_get_courses')]]") if tree.tag != "tr" else [tree]:
        cells = [base.txt(cell) for cell in row.xpath("./td")]
        if len(cells) < 5:
            continue
        href = row.xpath(".//a[contains(@href,'p_get_courses')]/@href")[0]
        out.append(base.course(cells[1], cells[2], period, ects=cells[3], credit=cells[4], kind=kind, url=urljoin(url, href), source=url))
    return out


def _parse_plan(text: str, url: str) -> tuple[list[dict], list[tuple[str, str]]]:
    """(sayfadaki dersler, [(kategori, havuz adresi)]). Kategori başlığı: <a name="BSCS_REQ"></a><b>Zorunlu Dersler</b>."""
    items, pools, category = [], [], ""
    for node in base.parse(text).iter("p", "tr", "a"):
        if node.tag == "p" and node.xpath("./a[@name]") and node.xpath("./b"):
            category = base.txt(node.xpath("string(./b)"))
        elif node.tag == "tr" and node.xpath("./td//a[contains(@href,'p_get_courses')]") and not node.xpath(".//tr"):
            elective = "seçmeli" in category.lower()
            kind = re.sub(r"\s+dersler(i)?$", "", category, flags=re.I) if category else ""
            items += _rows(node, url, kind, base.period(elective=True) if elective else "")
        elif node.tag == "a" and "p_list_courses" in (node.get("href") or ""):
            # Serbest seçmeli ve fakülte dersleri havuzları programa özgü değildir (bütün üniversitenin dersleri); alınmaz.
            if "seçmeli" in category.lower() and "serbest" not in category.lower():
                pools.append((re.sub(r"\s+dersler(i)?$", "", category, flags=re.I), urljoin(url, node.get("href"))))
    return items, pools


def _parse_pool(text: str, url: str, kind: str) -> list[dict]:
    return _rows(base.parse(text), url, kind, base.period(elective=True))


def _parse_detail(text: str, url: str) -> dict | None:
    tree = base.parse(text)
    head = [base.txt(cell) for cell in tree.xpath("(//table)[1]/tr[1]/th")]
    if not head or not head[0]:
        return None
    described = tree.xpath("(//table)[1]/tr[2]/td[@colspan]")
    labelled = {}
    rows = tree.xpath("(//table)[1]/tr[td/b]")
    for row in rows:
        label = base.txt(row.xpath("string(./td/b)")).rstrip(": ")
        value = base.txt(row.xpath("string(./td)"))[len(base.txt(row.xpath("string(./td/b)"))):].strip()
        if not value and "Genel" in label and row.getnext() is not None:
            value = base.txt(row.getnext())  # genel koşullar bir alt satırda yazılır
        labelled[label] = value
    terms = [base.txt(cell) for cell in tree.xpath("(//table)[1]//table//tr[position()>1]/td[1]")][:3]
    info = [("SU kredisi", head[1] if len(head) > 1 else ""), ("AKTS", labelled.get("ECTS Kredi", "")),
            ("Ön koşul", labelled.get("Onkosul", "")), ("Yan koşul", labelled.get("Yankosul", "")),
            ("Son açıldığı dönemler", ", ".join(terms))]
    parts = [("Dersin içeriği", base.txt(described[0]) if described else ""), ("Genel koşullar", labelled.get("Genel Kosullar", ""))]
    return base.detail(url, head[0], info=info, parts=parts)


async def _term(http) -> str:
    return _parse_term(await http.text(f"{ROOT}SU_DEGREE.p_select_term?P_PROGRAM=BSCS&P_LANG=TR&P_LEVEL=UG"))


async def programs(http) -> list[dict]:
    turkish, english, term = await asyncio.gather(
        http.text(f"{ROOT}SU_DEGREE.p_list_degree?P_LEVEL=UG&P_LANG=TR"),
        http.text(f"{ROOT}SU_DEGREE.p_list_degree?P_LEVEL=UG&P_LANG=EN"), _term(http))
    return _parse_programs(turkish, english, term)


async def courses(http, program) -> list[dict]:
    """Mezuniyet koşulları sayfası (1 istek) + çekirdek ve alan seçmeli havuzları (paralel, 1-2 istek)."""
    url = _plan_url(program["code"], program.get("term") or await _term(http))
    items, pools = _parse_plan(await http.text(url), url)
    if not items and (term := await _term(http)) and term != program.get("term"):
        # Program listesi kaydedildikten sonra yeni akademik yıla geçilmiş: güncel dönemle yeniden denenir.
        url = _plan_url(program["code"], term)
        items, pools = _parse_plan(await http.text(url), url)
    pages = await asyncio.gather(*(http.text(pool) for _, pool in pools), return_exceptions=True)
    for (kind, pool), page in zip(pools, pages):
        if not isinstance(page, BaseException):
            items += _parse_pool(page, pool, kind)
    seen, out = set(), []
    for item in items:  # aynı ders birden çok kategoride olabilir; ilk (zorunlu) kayıt kalır
        if item["code"] not in seen:
            seen.add(item["code"])
            out.append(item)
    return out


async def detail(http, url) -> dict | None:
    return _parse_detail(await http.text(url), url)
