"""Veri tarifleri: tarayıcısız, doğrudan API ile okunan kaynakların (YÖK Akademik…) yanıt biçimi denetimi.

REA tarifleri (recipes.py) sayfa iskeletini ve istek adreslerini izler. Buradaki kaynaklarda ise adres ve istek aynı
kalır, yanıtın İÇİNDEKİ alan adları değişebilir (Kasım 2026: YÖK kadro listesinden fakulteAd / bolumAd kalktı, bilgi
kadroYeri alanına taşındı). O durumda istek "başarılı" döner ama ayrıştırılan veri boş kalır.

Her tarif için:
  * kontrol — kaynaktan tek örnek kayıt alınır, bizim ayrıştırıcımızdan geçirilir; beklenen çıktılardan boş kalan var
    mı ve ham alan adları son bilinen biçime göre değişmiş mi bakılır.
  * güncelle — boş kalan çıktılar için yeni eşleme öğrenilir (model örnek kayda bakıp hangi alandan, gerekirse hangi
    ayırıcı ve sırayla okunacağını önerir; öneri örnek üzerinde doğrulanmadan kaydedilmez) ve yeni alan listesi
    "bilinen biçim" olarak saklanır. Ayrıştırıcılar kayıtlı eşlemeyi `mapped()` ile kullanır.

Kontrol ve güncelleme yalnız kullanıcı Ayarlar'dan istediğinde çalışır (tarif başına 1-2 küçük istek).
"""
from __future__ import annotations

import json
import time

from .config import ROOT
from .text import clean, fold

DIR = ROOT / "data" / "contracts"
SAMPLE_UNI = "ostim-teknik-universitesi"  # örnek kayıt için küçük bir üniversite

# kimlik → başlık, kaynak ve ayrıştırıcının doldurması beklenen çıktılar
CONTRACTS = {
    "yok.staff": {"label": "YÖK Akademik · kadro listesi", "source": "akademik.yok.gov.tr /akademisyen/list", "learnable": True,
                  "outputs": {"name": "Ad soyad", "title": "Unvan", "faculty": "Fakülte", "department": "Bölüm", "yok_id": "Kimlik"}},
    "atlas.programs": {"label": "YÖK Atlas · program listesi", "source": "yokatlas.yok.gov.tr /tercih-kilavuz/search",
                       "outputs": {"name": "Program", "faculty": "Fakülte", "score_type": "Puan türü", "language": "Öğretim dili",
                                   "score": "Taban puan", "rank": "Başarı sırası", "quota": "Kontenjan"},
                       # Yeni açılan ya da henüz yerleştirme yapılmamış programda puan ve sıra boş olabilir.
                       "optional": ["score", "rank"]},
    "yok.istatistik": {"label": "YÖK İstatistik · öğrenci sayıları", "source": "istatistik.yok.gov.tr (Öğrenci Sayıları Raporu)",
                       "outputs": {"name": "Üniversite", "type": "Üniversite türü", "city": "İl", "mode": "Öğrenim türü",
                                   "year": "Öğretim yılı", "total": "Genel toplam"}},
}
_CACHE: dict[str, tuple[float, dict]] = {}


def _path(cid: str):
    return DIR / f"{cid}.json"


def load(cid: str) -> dict:
    """Tarifin kaydı: {"fields": bilinen alan adları, "map": {çıktı: kural}, "status", "checked_at", …}."""
    path = _path(cid)
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return {"fields": [], "map": {}}
    hit = _CACHE.get(cid)
    if hit and hit[0] == stamp:
        return hit[1]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data = {"fields": [], "map": {}, **(data if isinstance(data, dict) else {})}
    _CACHE[cid] = (stamp, data)
    return data


def _save(cid: str, data: dict) -> None:
    try:
        DIR.mkdir(parents=True, exist_ok=True)
        _path(cid).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass
    _CACHE.pop(cid, None)


def _apply(rule: dict, row: dict) -> str:
    value = row.get(rule.get("field") or "")
    if value in (None, ""):
        return ""
    text = str(value)
    if rule.get("split"):
        parts = [clean(x) for x in text.split(rule["split"]) if clean(x)]
        index = rule.get("index") if isinstance(rule.get("index"), int) else 0
        return parts[index] if -len(parts) <= index < len(parts) else ""
    return clean(text)


def mapped(cid: str, output: str, row: dict) -> str:
    """Öğrenilmiş eşlemeyle çıktının değeri (eşleme yoksa ya da alan boşsa "")."""
    rule = (load(cid).get("map") or {}).get(output)
    return _apply(rule, row) if isinstance(rule, dict) else ""


# ------------------------------------------------------------------ örnek kayıt ve ayrıştırma
async def _sample(cid: str) -> dict:
    if cid == "yok.istatistik":
        from . import yok_istatistik
        got = await yok_istatistik.sample()
        return {"year": got["year"], **{f"sutun{i + 1}": cell for i, cell in enumerate(got["row"])}}
    from . import yokdir
    uni = await yokdir._university(SAMPLE_UNI)
    if not uni:
        raise ValueError("örnek üniversite bulunamadı")
    if cid == "atlas.programs":
        from . import atlas
        async with atlas._client() as client:
            unis = await atlas._universities(client)
            uid = unis.get(atlas._name_key(uni["name"]))
            if not uid:
                raise ValueError("örnek üniversite Atlas'ta bulunamadı")
            body = {"filters": {**atlas.EMPTY_FILTERS, "universiteId": [uid]}, "page": 0, "size": 1, "sortBy": "basariSirasi", "direction": "ASC"}
            found = (await client.post(f"{atlas.API}/tercih-kilavuz/search", json=body)).json()
        rows = found.get("content") or []
        if not rows:
            raise ValueError("örnek program gelmedi")
        return {**rows[0], "_yil": found.get("yil")}
    async with yokdir._client(15) as client:
        found = await yokdir.api(client, "/akademisyen/list", page=1, length=1, birimId=uni["birim_id"],
                                 birimId_matchMode="equals", **yokdir.ACTIVE) or {}
    rows = found.get("data") or []
    if not rows:
        raise ValueError("örnek kayıt gelmedi")
    return rows[0]


def _parse(cid: str, row: dict) -> dict:
    if cid == "yok.staff":
        from .yokdir import _person
        return _person(row)
    if cid == "atlas.programs":
        from . import atlas
        program = atlas._program(row, int(row.get("_yil") or time.localtime().tm_year), True)
        latest = (program.get("years") or [{}])[0]
        return {**program, "score": latest.get("score"), "rank": latest.get("rank"), "quota": program.get("quota") or latest.get("quota")}
    # yok.istatistik: satır hücreleri sırayla (ad, tür, il, öğrenim türü, 15 sayı)
    cells = [row.get(f"sutun{i}") or "" for i in range(1, 20)]
    numeric = all(str(c).replace(".", "").replace(",", "").isdigit() for c in cells[4:19])
    return {"name": cells[0], "type": cells[1], "city": cells[2], "mode": cells[3], "year": row.get("year") or "",
            "total": cells[18] if numeric else ""}


def _fields(row: dict) -> list[str]:
    return sorted(k for k, v in row.items() if v not in (None, "", [], {}))


def summary() -> list[dict]:
    out = []
    for cid, spec in CONTRACTS.items():
        saved = load(cid)
        out.append({"id": cid, "label": spec["label"], "source": spec["source"], "status": saved.get("status") or "unknown",
                    "checked_at": saved.get("checked_at") or 0, "empty": saved.get("empty") or [], "removed": saved.get("removed") or [],
                    "added": saved.get("added") or [], "map": saved.get("map") or {}, "learned_at": saved.get("learned_at") or 0,
                    "learnable": bool(spec.get("learnable")), "similarity": saved.get("similarity"),
                    "outputs": spec["outputs"]})
    return out


async def check(cid: str) -> dict:
    """Örnek kayıt alınır ve denetlenir. status: ok | changed (alanlar değişti ama çıktılar dolu) | broken (boş çıktı var)."""
    spec = CONTRACTS[cid]
    saved = dict(load(cid))
    try:
        row = await _sample(cid)
    except Exception as exc:  # noqa: BLE001 — kaynağa ulaşılamadı: önceki durum korunur
        return {**{k: saved.get(k) for k in ("status", "empty", "removed", "added")}, "id": cid, "label": spec["label"],
                "error": f"Kaynağa ulaşılamadı ({type(exc).__name__})", "checked_at": saved.get("checked_at") or 0}
    parsed = _parse(cid, row)
    optional = set(spec.get("optional") or [])
    empty = [key for key in spec["outputs"] if not parsed.get(key) and key not in optional]
    blank = [key for key in optional if not parsed.get(key)]
    fields, known = _fields(row), saved.get("fields") or []
    # İsteğe bağlı alanların ham adları (bu örnekte boş oldukları için listede yoktur) "kalkan alan" sayılmasın.
    known = [f for f in known if f in fields or f in row or not blank]
    removed = [f for f in known if f not in fields] if known else []
    added = [f for f in fields if f not in known] if known else []
    status = "broken" if empty else "changed" if (removed or added) else "ok"
    union = set(known) | set(fields)
    similarity = round(len(set(known) & set(fields)) / len(union), 3) if known and union else 1.0
    saved.update(status=status, empty=empty, removed=removed, added=added, checked_at=time.time(), similarity=similarity)
    if not known and not empty:
        saved["fields"] = fields  # ilk kontrol: çalışan biçim "bilinen biçim" olarak kaydedilir
    _save(cid, saved)
    return {"id": cid, "label": spec["label"], "status": status, "empty": empty, "removed": removed, "added": added,
            "blank": blank, "checked_at": saved["checked_at"], "similarity": similarity, "fields": len(fields), "outputs": spec["outputs"], "learnable": bool(spec.get("learnable")),
            "parsed": {key: (parsed.get(key) if isinstance(parsed.get(key), str) else str(parsed.get(key) or ""))[:80] for key in spec["outputs"]}}


_MAP_SCHEMA = {"type": "object", "properties": {"rules": {"type": "array", "items": {"type": "object", "properties": {
    "output": {"type": "string"}, "field": {"type": "string"}, "split": {"type": "string"}, "index": {"type": "integer"}},
    "required": ["output", "field"]}}}, "required": ["rules"]}
_MAP_SYSTEM = """Bir API yanıtındaki kayıttan belirli çıktıları okuyacak kuralları belirliyorsun. Sana örnek kayıt (JSON) ve
doldurulması gereken çıktıların adları ile anlamları verilir. Her çıktı için: değerin bulunduğu alanın adı ("field"); değer
birleşik bir metnin parçasıysa ayırıcı karakter ("split", ör. "/") ve parçanın sırası ("index", 0'dan başlar). Değer alanın
tamamıysa split ve index verme. Yalnız örnek kayıtta gerçekten bulunan alan adlarını kullan; emin olmadığın çıktıyı yazma."""


async def relearn(cid: str, llm) -> dict:
    """Boş kalan çıktılar için eşlemeyi öğrenir ve yeni alan listesini bilinen biçim olarak kaydeder."""
    spec = CONTRACTS[cid]
    row = await _sample(cid)
    saved = dict(load(cid))
    rules = dict(saved.get("map") or {})
    optional = set(spec.get("optional") or [])
    before = _parse(cid, row)
    empty = [key for key in spec["outputs"] if not before.get(key) and key not in optional]
    taken = {fold(str(v)) for v in before.values() if isinstance(v, str) and v}  # başka çıktıların zaten taşıdığı değerler
    learned, failed = [], []
    if empty:
        answer = None
        if llm and getattr(llm, "available", False):
            prompt = json.dumps({"kayit": {k: (v if not isinstance(v, (list, dict)) else "…") for k, v in row.items() if v not in (None, "")},
                                 "ciktilar": {key: spec["outputs"][key] for key in empty}}, ensure_ascii=False)
            try:
                answer = await llm.json(prompt, _MAP_SCHEMA, system=_MAP_SYSTEM, timeout=30, fast=True)
            except Exception:  # noqa: BLE001
                answer = None
        for rule in (answer or {}).get("rules") or [] if isinstance(answer, dict) else []:
            key = rule.get("output") if isinstance(rule, dict) else None
            if key not in empty or rule.get("field") not in row:
                continue
            candidate = {"field": rule["field"], **({"split": rule["split"], "index": rule.get("index", 0)} if rule.get("split") else {})}
            value = _apply(candidate, row)
            # Öneri örnek kayıtta değer vermeli ve bu değer başka bir çıktının değeri olmamalı (ör. "bilim alanı" için
            # unvan alanını önermek): öyleyse kabul edilmez.
            if value and fold(value) not in taken:
                rules[key] = candidate
                learned.append(key)
                taken.add(fold(value))
    saved["map"] = rules
    _save(cid, saved)  # ayrıştırıcı yeni eşlemeyi görsün
    parsed = _parse(cid, row)
    failed = [key for key in spec["outputs"] if not parsed.get(key) and key not in optional]
    saved.update(fields=_fields(row), status="broken" if failed else "ok", empty=failed, removed=[], added=[],
                 checked_at=time.time(), learned_at=time.time())
    _save(cid, saved)
    return {"id": cid, "label": spec["label"], "status": saved["status"], "empty": failed, "learned": learned, "map": rules,
            "outputs": spec["outputs"], "checked_at": saved["checked_at"],
            "parsed": {key: (parsed.get(key) if isinstance(parsed.get(key), str) else str(parsed.get(key) or ""))[:80] for key in spec["outputs"]}}
