"""Hazır veri seti (bahadir-yok dışa aktarımı): üniversite → fakülte → bölüm → dersler. Ağ isteği atmaz.

Veri: data/poc/student/<alan adı>.json ya da .json.gz (scripts/import_poc_dataset.py ile kopyalanır). Dosya ya da eşleşme
yoksa None döner; çağıran canlı taramaya geçer. Öğrenci görünümü bölümün dersleri veri setinde varsa onları anında
gösterir; yoksa veri setindeki bölüm sitesi ve ders bilgi paketi adresi canlı taramaya başlangıç olarak verilir.

Eşleştirme kurumun alan adıyla, sonra fakülte ve bölüm adıyla yapılır. Bölüm adı birebir tutmalıdır (yazım farkları ve
"Bölümü / Programı / Lisans" ekleri dışında): "Matematik" sorulunca "Matematik Öğretmenliği", "Türkçe Öğretmenliği"
sorulunca "İngilizce Öğretmenliği" dönmez. Programın dil ve öğretim türü ("(İngilizce)", "(%30 İngilizce)", "(İÖ)")
adın parçası sayılmaz ama ayrı tutulur: istenen varyant varsa o, yoksa işaretsiz olan seçilir.
"""
from __future__ import annotations

import functools
import gzip
import json
import re
import time
import unicodedata
from pathlib import Path

try:  # proje içinde
    from .config import ROOT
except ImportError:  # tek başına
    ROOT = Path(__file__).resolve().parent.parent

DATA = ROOT / "data" / "poc" / "student"
MIN_COURSES = 5  # bundan az ders satırı ders planı sayılmaz; canlı taramaya geçilir

_EN_TR = {
    "arts and sciences": "fen edebiyat", "business administration": "isletme", "international relations": "uluslararasi iliskiler",
    "political science and public administration": "siyaset bilimi kamu yonetimi", "molecular biology": "molekuler biyoloji",
    "computer": "bilgisayar", "engineering": "muhendislik", "mechanical": "makine", "electrical": "elektrik",
    "electronics": "elektronik", "industrial": "endustri", "civil": "insaat", "chemical": "kimya", "chemistry": "kimya",
    "physics": "fizik", "mathematics": "matematik", "statistics": "istatistik", "economics": "iktisat",
    "psychology": "psikoloji", "sociology": "sosyoloji", "history": "tarih", "philosophy": "felsefe",
    "architecture": "mimarlik", "education": "egitim", "law": "hukuk", "medicine": "tip", "nursing": "hemsirelik",
    "dentistry": "dis hekimligi", "pharmacy": "eczacilik", "genetics": "genetik", "biology": "biyoloji",
}
_EN_RX = re.compile(r"\b(?:" + "|".join(sorted(map(re.escape, _EN_TR), key=len, reverse=True)) + r")\b")
_DROP = re.compile(r"\b(?:fakultesi|fakulte|bolumu|bolum|anabilim dali|programi|program|lisans|pr|faculty|department|college"
                   r"|school|of|and|ve|the|kktc|burslu|ucretli|indirimli)\b")
_LANGUAGE = {"ingilizce": "en", "english": "en", "turkce": "tr", "turkish": "tr", "almanca": "de", "german": "de",
             "fransizca": "fr", "french": "fr", "arapca": "ar", "arabic": "ar", "rusca": "ru", "russian": "ru"}
_SINGLE = re.compile(r"tip|dis hekimligi|eczacilik|veteriner(?: hekimligi)?|hukuk")
# Bir sitenin bütün dersleri tek kutuda toplanmış: bölüm adı değildir, ada göre eşleşmez.
_BUCKET = re.compile(r"^ders sayfasi\b")


def fold(value: str) -> str:
    text = (value or "").replace("İ", "i").replace("I", "ı").lower()
    text = text.translate(str.maketrans("çğıöşüâîû", "cgiosuaiu"))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


@functools.lru_cache(maxsize=20000)
def unit_key(value: str) -> tuple[str, str]:
    """(ad anahtarı, varyant). 'Bilgisayar Mühendisliği (%30 İngilizce)' → ('bilgisayar muhendislik', 'en30');
    'İngilizce Öğretmenliği' → ('ingilizce ogretmenligi', ''): dil kelimesi yalnız adın SONUNDAYSA varyanttır."""
    words = fold(value).split()
    variant = ""
    while words:
        last = words[-1]
        if last in _LANGUAGE and len(words) > 1:
            words.pop()
            percent = words.pop() if words and words[-1].isdigit() else ""
            variant = _LANGUAGE[last] + (percent if percent and percent != "100" else "") + variant
        elif len(words) > 2 and words[-2:] in (["ikinci", "ogretim"], ["uzaktan", "ogretim"], ["normal", "ogretim"],
                                               ["orgun", "ogretim"], ["i", "o"]):
            kind = words[-2]
            del words[-2:]
            variant += {"ikinci": "+io", "i": "+io", "uzaktan": "+uzaktan"}.get(kind, "")
        elif len(words) > 1 and last in {"io", "burslu", "ucretli", "indirimli"} or last.isdigit() and len(words) > 1:
            words.pop()
            variant += "+io" if last == "io" else ""
        else:
            break
    text = _EN_RX.sub(lambda m: _EN_TR[m.group(0)], " ".join(words))
    text = re.sub(r"\bmuhendisligi\b", "muhendislik", re.sub(r"\bmakina\b", "makine", text))
    return " ".join(_DROP.sub(" ", text).split()), variant


def domain_of(url_or_domain: str) -> str:
    host = re.sub(r"^https?://", "", (url_or_domain or "").strip().lower()).split("/")[0].split(":")[0]
    parts = host.split(".")
    return ".".join(parts[-3:]) if host.endswith(".edu.tr") and len(parts) >= 3 else host.removeprefix("www.")


def available() -> bool:
    """Veri seti kurulu mu (klasör var mı); yoksa hiçbir arama yapılmaz."""
    return DATA.is_dir()


def university(domain: str) -> dict | None:
    """Üniversitenin kaydı (alan adı ya da ana sayfa adresiyle); son açılan sekiz üniversite bellekte tutulur."""
    return _university(domain_of(domain))


@functools.lru_cache(maxsize=8)
def _university(name: str) -> dict | None:
    if not re.fullmatch(r"[a-z0-9.-]{3,80}", name) or ".." in name:
        return None
    for path, opener in ((DATA / f"{name}.json.gz", gzip.open), (DATA / f"{name}.json", open)):
        try:
            with opener(path, "rt", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            continue
        return data if isinstance(data, dict) and isinstance(data.get("faculties"), list) else None
    return None


def _faculty(uni: dict, faculty: str) -> dict | None:
    key = unit_key(faculty)[0] if faculty else ""
    return next((f for f in uni["faculties"] if not f.get("unassigned") and unit_key(f.get("name") or "")[0] == key), None) if key else None


def _pick(rows: list[tuple[dict, dict]], variant: str) -> tuple[dict, dict] | None:
    """Aynı ada sahip adaylar arasından: istenen varyant; istenmediyse işaretsiz, o da yoksa Türkçe olan. Dersi olan önce.
    İstenen varyant yoksa ve adayların hiçbiri varyant taşımıyorsa işaretsiz aday kabul edilir (YÖK "… (İngilizce)" der,
    İngilizce eğitim veren kurumun sitesi programı işaretsiz yazar)."""
    if variant:
        marked = {unit_key(row[1]["name"])[1] for row in rows}
        rows = [row for row in rows if unit_key(row[1]["name"])[1] == variant] or (rows if marked == {""} else [])
    else:
        plain = [row for row in rows if not unit_key(row[1]["name"])[1]]
        turkish = [row for row in rows if unit_key(row[1]["name"])[1] in {"tr", "+io", "tr+io"}]
        rows = plain or turkish or (rows if len(rows) == 1 else [])
    return max(rows, key=lambda row: len(row[1].get("courses") or []), default=None)


def department(domain: str, faculty: str, name: str) -> tuple[dict, dict] | None:
    """(fakülte kaydı, bölüm kaydı) ya da None. Önce seçilen fakültenin içinde, yoksa üniversitenin tamamında — ama
    yalnız ad tek bir fakültede geçiyorsa (aynı adlı bölüm iki fakültede varsa hangisi olduğu bilinemez)."""
    uni = university(domain)
    if not uni:
        return None
    key, variant = unit_key(name)
    fac = _faculty(uni, faculty)
    if not key:
        return None
    rows = [(f, d) for f in uni["faculties"] for d in f.get("departments") or []
            if isinstance(d, dict) and d.get("name") and not _BUCKET.match(fold(d["name"]))]
    if fac:
        inside = [row for row in rows if row[0] is fac and unit_key(row[1]["name"])[0] == key]
        if found := _pick(inside, variant):
            return found
        # Tek programlı fakülte (Tıp, Hukuk…): veri setinde bölüm, programın kendisi ya da en çok dersi olan birimdir.
        fac_key = unit_key(fac["name"])[0]
        if _SINGLE.fullmatch(fac_key) and key == fac_key:
            best = max((row for row in rows if row[0] is fac), key=lambda row: len(row[1].get("courses") or []), default=None)
            if best and len(best[1].get("courses") or []) >= MIN_COURSES:
                return best
    everywhere = [row for row in rows if unit_key(row[1]["name"])[0] == key]
    homes = {id(row[0]) for row in everywhere if not row[0].get("unassigned")}
    if len(homes) > 1:
        return None
    return _pick(everywhere, variant)


def _faculty_site(uni: dict, fac: dict | None) -> str:
    """Fakültenin sitesi: kayıtta varsa o; yoksa fakültedeki bölüm adreslerinin ortak kökü (aynı alt alan adı
    fakulte.kurum.edu.tr ya da aynı ilk yol parçası kurum.edu.tr/fakulte/…). Kurumun ana sitesinin kökü sayılmaz."""
    from urllib.parse import urlsplit
    if not fac:
        return ""
    if isinstance(fac.get("url"), str) and fac["url"].startswith("http") and not re.search(r"\.(?:gif|png|jpe?g|svg|webp|css|js|pdf)(?:\?|$)", fac["url"], re.I):
        return fac["url"]
    urls = [d["url"] for d in fac.get("departments") or [] if isinstance(d, dict) and isinstance(d.get("url"), str) and d["url"].startswith("http")]
    if len(urls) < 2:
        return ""
    parts = [urlsplit(u) for u in urls]
    hosts = {p.hostname or "" for p in parts}
    if len(hosts) != 1:
        return ""
    host = hosts.pop()
    main = {urlsplit(uni.get("home") or "").hostname or "", "www." + (uni.get("domain") or "")}
    scheme = parts[0].scheme
    if host not in main and host != (uni.get("domain") or ""):
        return f"{scheme}://{host}/"
    heads = {(p.path.strip("/").split("/") or [""])[0] for p in parts}
    if len(heads) == 1 and (head := heads.pop()):
        return f"{scheme}://{host}/{head}/"
    return ""


def _stamp(uni: dict) -> float:
    try:
        return time.mktime(time.strptime(str(uni.get("generated_at") or ""), "%Y-%m-%d %H:%M:%S"))
    except (ValueError, OverflowError):
        return 0.0


def lookup(home: str, faculty: str, name: str) -> dict | None:
    """Öğrenci görünümü için tek arama: {"group": ders grubu | None, "unit": birim bilgisi, "generated": veri tarihi}.
    group, student_view "courses" grubu biçimindedir (format="course_catalog"); bölümün dersi yoksa None."""
    uni = university(home)
    if not uni:
        return None
    fac = _faculty(uni, faculty)
    found = department(home, faculty, name)
    site = _faculty_site(uni, fac)
    if not found:
        unit = {"dean": fac.get("dean"), "faculty": fac.get("name")} if fac and fac.get("dean") else {}
        return {"group": None, "generated": _stamp(uni), "unit": {**unit, "faculty_url": site} if site else (unit or None)}
    owner, dept = found
    owner = owner if not owner.get("unassigned") else (fac or owner)
    source = dept.get("bologna_url") or dept.get("url") or uni.get("home") or ""
    courses = [c for c in dept.get("courses") or [] if isinstance(c, dict) and c.get("title")]
    group = None
    if len(courses) >= MIN_COURSES:
        links = [{"title": "Bologna / ders bilgi paketi", "url": dept["bologna_url"]}] if dept.get("bologna_url") else []
        group = {"title": "Dersler ve içerikleri", "format": "course_catalog", "source": "dataset", "links": links,
                 "items": [{**c, "source_url": c.get("source_url") or source, "type": "courses"} for c in courses]}
    unit = {"faculty": None if owner.get("unassigned") else owner.get("name"), "dean": None if owner.get("unassigned") else owner.get("dean"),
            "department": dept.get("name"), "head": dept.get("head"), "careers": dept.get("careers"),
            "url": dept.get("url") or "", "bologna_url": dept.get("bologna_url") or "",
            "faculty_url": _faculty_site(uni, owner if not owner.get("unassigned") else fac)}
    return {"group": group, "unit": unit, "generated": _stamp(uni)}
