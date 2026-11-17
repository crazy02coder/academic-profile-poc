"""YÖK Atlas (tercih kılavuzu): üniversitenin programları için taban puan, başarı sırası, kontenjan, yerleşen,
puan türü, öğretim dili ve burs. Aday bakışı bunu kullanır.

Atlas'ın kendi arayüzünün kullandığı iki açık uç: üniversite listesi (ad → kimlik) ve arama (üniversite kimliğiyle
süzülür). Üniversite başına tek istek; sonuçlar 30 gün saklanır. yok.gov.tr hız sınırından geçer.
"""
from __future__ import annotations

import json
import re
import time

import httpx

from .config import ROOT, USER_AGENT
from .text import clean, fold
from .yok_rate import HOOKS

API = "https://yokatlas.yok.gov.tr/api"
DIR = ROOT / "data" / "atlas"
TTL = 30 * 24 * 3600
VERSION = 2  # program kaydının biçimi: değişince kayıtlı üniversiteler bir kez yeniden alınır
EMPTY_FILTERS = {"puanTuru": None, "universiteId": [], "birimGrupId": [], "ilKodu": [], "birimTuruId": None,
                 "universiteTuru": None, "bursOraniId": None, "ogrenimTuruId": None, "kilavuzKodu": None,
                 "minBasariSirasi": None, "maxBasariSirasi": None}


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=25, event_hooks=HOOKS, headers={
        "User-Agent": USER_AGENT, "Accept": "application/json", "Accept-Language": "tr", "Referer": "https://yokatlas.yok.gov.tr/"})


def _load(name: str, ttl: float = TTL, stale: bool = False):
    try:
        saved = json.loads((DIR / f"{name}.json").read_text(encoding="utf-8"))
        if stale or time.time() - saved["ts"] < ttl:
            return saved["data"]
    except (OSError, ValueError, KeyError):
        pass
    return None


def _save(name: str, data) -> None:
    try:
        DIR.mkdir(parents=True, exist_ok=True)
        (DIR / f"{name}.json").write_text(json.dumps({"ts": time.time(), "data": data}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _name_key(name: str) -> str:
    """"MARMARA ÜNİVERSİTESİ (İSTANBUL)" → "marmara universitesi"."""
    return " ".join(fold(re.sub(r"\([^)]*\)", " ", clean(name))).replace("t.c.", " ").split())


async def _universities(client) -> dict[str, int]:
    """{ad anahtarı: Atlas üniversite kimliği}; 30 gün saklanır."""
    cached = _load("universities")
    if cached is not None:
        return cached
    rows = (await client.get(f"{API}/tercih-kilavuz/universiteler")).json()
    data = {_name_key(r["universiteAdi"]): r["universiteId"] for r in rows if r.get("universiteAdi") and r.get("universiteId")}
    if data:
        _save("universities", data)
    return data


def _num(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number == int(number) else round(number, 3)


def _program(row: dict, year: int, announced: bool) -> dict:
    """Atlas satırından aday için kısa kayıt. Yıl etiketleri Atlas arayüzüyle aynı kurulur: sonuçlar açıklandıysa
    eksiz alanlar kılavuz yılına, 1/2/3 ekli alanlar önceki yıllara aittir; açıklanmadıysa bir yıl geriden başlar."""
    years = []
    if announced and row.get("minPuan") is not None:
        years.append({"year": year, "score": _num(row.get("minPuan")), "rank": _num(row.get("basariSirasi")),
                      "quota": _num(row.get("kontenjan")), "placed": _num(row.get("gkY"))})
    for k in (1, 2, 3):
        score, rank = _num(row.get(f"minPuan{k}")), _num(row.get(f"basariSirasi{k}"))
        if score is None and rank is None:
            continue
        years.append({"year": year - k - (0 if announced else 1), "score": score, "rank": rank,
                      "quota": _num(row.get(f"gk{k}")), "placed": None})
    return {
        "code": row.get("kilavuzKodu"), "faculty": clean(row.get("fymkAdi") or ""), "name": clean(row.get("birimAdi") or ""),
        "group": clean(row.get("birimGrupAdi") or ""), "level": "Ön lisans" if fold(row.get("birimTuruAdi") or "").replace(" ", "").startswith("on") else "Lisans",
        "score_type": clean(row.get("puanTuru") or ""), "language": clean(row.get("ogrenimDiliAdi") or ""),
        "study": clean(row.get("ogrenimTuruAdi") or ""), "duration": row.get("ogrenimSuresi"),
        "scholarship": clean(row.get("bursOraniAdi") or "") or "Ücretsiz", "quota": _num(row.get("kontenjan")),
        "accreditation": clean(row.get("akreditasyon") or ""), "district": clean(row.get("ilceAdi") or ""), "years": years,
        # Atlas'ın program ayrıntısındaki diğer alanlar (aynı satırda gelir, ek istek yok)
        "city": clean(row.get("ilAdi") or ""), "uni_type": clean(row.get("universiteTuru") or ""), "fee": _num(row.get("ucret")),
        "uni_accreditation": clean(row.get("uniAkreditasyon") or ""), "tyc": clean(str(row.get("tyc") or "")),
        "applied": clean(str(row.get("uygulamaliEgitimModeli") or "")), "hierarchy": str(row.get("birimHiyerarsi") or ""),
        "staff": {k: n for k, f in (("prof", "prof"), ("doc", "doc"), ("dou", "dou"), ("ogr_gor", "ogrGor"), ("ar_gor", "arGor"))
                  if (n := _num(row.get(f))) is not None},
        "quotas": [{"name": name, "quota": q, "placed": _num(row.get(placed))} for name, quota, placed in (
            ("Genel", "kontenjan", "gkY"), ("Okul birincisi", "kontenjanObs", "obkY"), ("Şehit / gazi yakını", "kontenjanSgy", "sgyY"),
            ("34 yaş üstü kadın", "kontenjanY34", "y34"), ("Depremzede", "kontenjanDep", "dprmY")) if (q := _num(row.get(quota)))],
        "conditions": [{"code": str(code), "text": clean(str(text))[:1500]} for item in row.get("kosulList") or [] if isinstance(item, dict)
                       for code, text in item.items()][:30],
    }


async def programs(university: str, refresh: bool = False) -> dict | None:
    """Üniversitenin Atlas'taki programları. None: üniversite Atlas'ta bulunamadı ya da Atlas'a ulaşılamadı
    (eski kayıt varsa o döner)."""
    key = re.sub(r"[^a-z0-9]+", "-", _name_key(university)).strip("-")
    if not key:
        return None
    cached = None if refresh else _load(f"programs-{key}")
    if cached is not None and cached.get("v") == VERSION:
        return cached
    try:
        async with _client() as client:
            unis = await _universities(client)
            uid = unis.get(_name_key(university))
            if not uid:
                return None
            announced = str((await client.get(f"{API}/parameters/sonuc-aciklandi")).text).strip() == "1"
            body = {"filters": {**EMPTY_FILTERS, "universiteId": [uid]}, "page": 0, "size": 600, "sortBy": "basariSirasi", "direction": "ASC"}
            found = (await client.post(f"{API}/tercih-kilavuz/search", json=body)).json()
    except (httpx.HTTPError, ValueError, KeyError):
        return _load(f"programs-{key}", stale=True)
    year = int(found.get("yil") or time.localtime().tm_year)
    rows = [_program(r, year, announced) for r in found.get("content") or [] if r.get("birimAdi")]
    data = {"v": VERSION, "university": university, "year": year, "announced": announced, "programs": rows,
            "source": "https://yokatlas.yok.gov.tr/", "checked_at": time.time()}
    if rows:
        _save(f"programs-{key}", data)
    return data


NET_FIELDS = (("tytTrkNet", "TYT Türkçe"), ("tytSosNet", "TYT Sosyal"), ("tytMatNet", "TYT Matematik"), ("tytFenNet", "TYT Fen"),
              ("aytMatNet", "AYT Matematik"), ("aytFizNet", "AYT Fizik"), ("aytKimNet", "AYT Kimya"), ("aytBioNet", "AYT Biyoloji"),
              ("aytTdeNet", "AYT Edebiyat"), ("aytTrh1Net", "AYT Tarih-1"), ("aytCog1Net", "AYT Coğrafya-1"), ("aytTrh2Net", "AYT Tarih-2"),
              ("aytCog2Net", "AYT Coğrafya-2"), ("aytFelNet", "AYT Felsefe grubu"), ("aytDinNet", "AYT Din kültürü"), ("ydtYdilNet", "YDT Yabancı dil"))


async def nets(code: str) -> dict | None:
    """Programa son yerleşen adayın netleri, yıllara göre (Atlas "Yerleşen Son Kişinin Netleri"). Program başına tek
    istek, yalnız program tıklanınca; 30 gün saklanır."""
    if not re.fullmatch(r"\d{6,12}", str(code)):
        return None
    cached = _load(f"nets-{code}")
    if cached is not None:
        return cached
    try:
        async with _client() as client:
            found = (await client.post(f"{API}/netler/search", json={"filters": {"kilavuzKodu": int(code)}, "page": 0, "size": 10})).json()
    except (httpx.HTTPError, ValueError):
        return _load(f"nets-{code}", stale=True)
    years = []
    for row in found.get("content") or []:
        tests = [{"name": label, "net": n} for field, label in NET_FIELDS if (n := _num(row.get(field))) is not None]
        years.append({"year": row.get("yil"), "score_type": clean(row.get("puanTuru") or ""), "score": _num(row.get("tabanPuan")),
                      "obp": _num(row.get("obp")), "tests": tests})
    data = {"code": str(code), "years": sorted(years, key=lambda y: -(y["year"] or 0))}
    _save(f"nets-{code}", data)
    return data
