"""Ankara Üniversitesi — Bologna Bilgi Sistemi (bologna.ankara.edu.tr; Angular arayüzünün çağırdığı açık JSON API).

Eski bbs.ankara.edu.tr kapalıdır (404). Hepsi JSON gövdeli POST, oturum gerekmez; yanıt {"data": …, "success": true}:
  /api/AkademikProgram/getPublicList      {}                        bütün programlar (düzey, birim, öğretim türü ile)
  /api/PublicMufredatDers/getByProgram    {"Id", "Yil", "YilNo"}    programın güncel müfredatı: yarıyıl, zorunlu/seçmeli,
                                                                    seçmeli grubu, kredi, AKTS; "id" dersin bilgi kaydıdır
  /api/DersBilgi/getPublicById            {"Id"}                    dersin içeriği; liste alanları JSON metni olarak gelir
Arayüz adresleri: /program/<program id>/dersler ve /ders/<ders id> (detail() ders adresinden kimliği alır).

Ders planı tek istekte gelir; ders içeriği tembel okunur.
"""
from __future__ import annotations

import json
import re

from . import base

DOMAINS = ("ankara.edu.tr",)
SITE = "https://bologna.ankara.edu.tr"
API = SITE + "/api"
# Üniversite geneli seçmeli havuzu ("Üniversite Alan Dışı Genel Seçmeli Ders Grubu", ~360 ders) her programın 3. ve
# 4. yarıyılına eklenir; bölümün planı değildir. Bu büyüklükteki gruplar ders planına alınmaz.
POOL_LIMIT = 150
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
# Program olmayan birimler: ortak seçmeli ders havuzu ve yabancı dil dersleri birimi.
_NOT_UNIT = re.compile(r"alan dışı seçmeli|yabancı diller", re.I)
_ENGLISH = re.compile(r" \((?:%\d+ )?İngilizce\)")
_TERM_TYPE = {"Ara Sınav": "Yarıyıl içi", "Yıl Sonu": "Yıl sonu"}  # değerlendirme dökümünün iki bölümü


def _name(raw: str) -> str:
    """Sistemin otomatik büyük/küçük harf düzeltmesinin bozduklarını onarır: 'Yapay Zeka Ve Veri Mühendisliği' →
    '… ve …'; '(ingilizce)' → '(İngilizce)'; '(oyunculuk)' → '(Oyunculuk)'."""
    name = re.sub(r"\s+(Ve|İle)\s+", lambda m: f" {m[1].replace('İ', 'i').lower()} ", base.txt(raw))
    return re.sub(r"\(([a-zçğıöşü])", lambda m: "(" + {"i": "İ", "ı": "I"}.get(m[1], m[1].upper()), name)


def _parse_programs(text: str) -> list[dict]:
    """Yalnız düzeyi 'Lisans' olan kayıtlar. Öğretim türü 'Normal Öğretim' değilse adın sonuna eklenir."""
    out = []
    for row in json.loads(text).get("data") or []:
        faculty = base.txt(row.get("akademikBirimAdi") or "")
        if row.get("dersDuzeyAdi") != "Lisans" or not row.get("id") or _NOT_UNIT.search(faculty):
            continue
        name = _name(row.get("programAdi") or "")
        if not name:
            continue
        mode = base.txt(row.get("ogretimTurAd") or "")
        if mode and mode != "Normal Öğretim" and base.fold(mode) not in base.fold(name):
            name = f"{name} ({mode})"
        english = base.txt(row.get("programAdiEng") or "")
        variant = _ENGLISH.search(name)
        if english and variant and not re.search(r"english|ingilizce", english, re.I):
            # İngilizce adda dil varyantı her zaman yazılmıyor ("PUBLIC FINANCE" hem Maliye hem Maliye (%30 İngilizce)):
            # varyantsız takma ad Türkçe programla karışmasın diye varyant eklenir.
            english += variant[0]
        out.append({"name": name, "faculty": faculty, "url": f"{SITE}/program/{row['id']}/dersler", "id": row["id"],
                    "aliases": [english] if english else []})
    return out


async def programs(http) -> list[dict]:
    return _parse_programs(await http.text(f"{API}/AkademikProgram/getPublicList", json_body={}))


def _parse_plan(text: str, url: str) -> list[dict]:
    """Müfredat satırları. dersTipi 1 zorunlu, 2 seçmeli; yıllık okutulan derslerde (Hukuk) yariyilNo boştur.
    Bilgi kaydı olmayan derste "id" boş gelir: içerik adresi verilmez."""
    rows = json.loads(text).get("data") or []
    size = {}
    for row in rows:
        if row.get("secmeliGrupKodu"):
            size.setdefault(row["secmeliGrupKodu"], set()).add(row.get("dersKodu"))
    items, seen = [], set()
    for row in rows:
        group = row.get("secmeliGrupKodu")
        if group and len(size[group]) > POOL_LIMIT:
            continue
        code, name = base.txt(row.get("dersKodu") or ""), _name(row.get("dersAdi") or "")
        period = base.period(row.get("yariyilNo"))
        if not code or not name or (code, period) in seen:
            continue
        seen.add((code, period))
        elective = row.get("dersTipi") == 2
        label = base.txt(row.get("secmeliGrupAdi") or "")
        kind = (f"Seçmeli · {label}" if label else "Seçmeli") if elective else "Zorunlu"
        items.append(base.course(code, name, period, ects=row.get("akts"), credit=base._num(row.get("kredi")), kind=kind,
                                 url=f"{SITE}/ders/{row['id']}" if row.get("id") else "", source=url))
    return items


async def courses(http, program) -> list[dict]:
    body = {"Id": program["id"], "Yil": None, "YilNo": None}  # yıl verilmezse güncel müfredat döner
    return _parse_plan(await http.text(f"{API}/PublicMufredatDers/getByProgram", json_body=body), program["url"])


def _list(value) -> list[dict]:
    """Liste alanları ("kazanimlar", "haftalikAkis"…) JSON metni olarak gelir; boş ya da bozuksa []."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _parse_detail(text: str, url: str) -> dict | None:
    row = json.loads(text).get("data")
    if not isinstance(row, dict):
        return None
    hours = "+".join(base._num(row.get(key)) or "0" for key in ("teorik", "uygulama", "laboratuvar"))
    info = [("Dil", row.get("egitimDiliAdi") or ""), ("Tür", row.get("dersTipiAdi") or ""),
            ("Öğretim şekli", row.get("egitimYontemiAdi") or ""), ("T+U+L", hours), ("Kredi", base._num(row.get("kredi"))),
            ("AKTS", base._num(row.get("akts"))), ("Süre", row.get("sureAdi") or ""),
            ("Öğretim elemanı", row.get("gorevliUserAdi") or ""), ("Akademik yıl", row.get("akademikYilAdi") or "")]
    sources = "\n".join(base.txt(x.get("adi") or "") for x in _list(row.get("kaynakcalar")) if x.get("adi"))
    parts = [("Dersin amacı", row.get("amac") or ""), ("Dersin içeriği", row.get("icerik") or ""), ("Kaynaklar", sources)]
    weeks = [(x.get("hafta"), x.get("konu") or "") for x in _list(row.get("haftalikAkis"))]
    outcomes = [x.get("kazanimAdi") or "" for x in sorted(_list(row.get("kazanimlar")), key=lambda x: x.get("siraNo") or 0)]
    # Değerlendirme iki ayrı %100'lük dökümdür (sinavTuru "Ara Sınav": yarıyıl içi, "Yıl Sonu"); hangisi olduğu ada eklenir.
    assessment = [(" · ".join(x for x in (_TERM_TYPE.get(row_.get("sinavTuru"), row_.get("sinavTuru") or ""), row_.get("adi") or "") if x),
                   row_.get("oran")) for row_ in _list(row.get("degerlendirmeYontemleri"))]
    total = sum(base.number(x.get("toplam")) or 0 for x in _list(row.get("isYukleri")))
    workload = {"hours": base._num(total), "ects": base._num(row.get("akts"))} if total else None
    return base.detail(url, f"{row.get('dersKodu') or ''} {_name(row.get('dersAdi') or '')}", info=info, parts=parts, weeks=weeks,
                       outcomes=outcomes, assessment=assessment, workload=workload)


async def detail(http, url) -> dict | None:
    ident = _UUID.search(url.rsplit("/", 1)[-1])
    if not ident:
        return None
    return _parse_detail(await http.text(f"{API}/DersBilgi/getPublicById", json_body={"Id": ident[0]}), url)
