"""Canlı test kurumu: Hogwarts Üniversitesi · tek fakülte · tek bölüm · tek akademisyen (Bahadır Arslan).

Jüri gösterimi için statik olarak uygulamayla gelir (app/demo/):
  * hogwarts_yok.json     — akademik-iz-poc-test'in YÖK benzeri yanıtlarının anlık kopyası. Hogwarts'a ait YÖK
                            istekleri (yokdir.api) ağa çıkmadan buradan yanıtlanır; üniversite YÖK listesinde görünür.
  * hogwarts_profile.json — Bahadır Arslan'ın hazır profili ("İncelenen profiller"de Hogwarts altında; kadrodaki
                            adına tıklayınca açılır).
Yeniden üretmek: python scripts/build_hogwarts_demo.py  (test projesinin veri.py'sinden)

Yayın takibi ve veri tarifi denetimi canlı test API'sini (test_source) kullanır; bu modül yalnız dizin ve profil içindir.
"""
from __future__ import annotations

import json
from functools import lru_cache

from .config import ROOT

DIR = ROOT / "app" / "demo"
GUID = "0B4AD1A25A1A0001"
UNI_RAW = "HOGWARTS ÜNİVERSİTESİ"
UNI_ID = "hogwarts-universitesi"
BIRIM, FAKULTE_ID, BOLUM_ID = "hogwarts-uni", "hogwarts-fak", "hogwarts-bol"
IDS = {BIRIM, FAKULTE_ID, BOLUM_ID, GUID}
CHAT_ID = "ba4ad1a25a1a"   # history: 12 haneli onaltılık kimlik
JOB_ID = "ba4ad1a25a1b"


@lru_cache(maxsize=1)
def _yok() -> dict:
    try:
        return json.loads((DIR / "hogwarts_yok.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


@lru_cache(maxsize=1)
def _profile() -> dict:
    try:
        return json.loads((DIR / "hogwarts_profile.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def available() -> bool:
    return bool(_yok())


# ------------------------------------------------------------------ YÖK dizini
def university_row() -> dict | None:
    """yokdir.universities() biçiminde üniversite kaydı."""
    u = _yok().get("university")
    if not u:
        return None
    return {"name": UNI_RAW, "url": "https://akademik.yok.gov.tr/universities", "birim_id": BIRIM,
            "name_en": u.get("birimAdiEn") or "", "city": u.get("ilAdi") or "", "type": u.get("tur") or "",
            "year": u.get("yil"), "rector": "", "rector_guid": ""}


def handles(path: str, params: dict) -> bool:
    """Bu YÖK isteği Hogwarts'a mı ait (kimliklerden biri parametrede ya da yolda)."""
    if not available():
        return False
    if GUID in path:
        return True
    return any(str(v) in IDS or str(v).startswith("hogwarts-") for v in params.values())


def yok_api(path: str, params: dict):
    """YÖK API'sinin `data` alanı (yokdir.api ile aynı dönüş)."""
    data = _yok()
    if path == "/genel/birim-list":
        return data.get("faculties") if str(params.get("listVal")) == "2" else data.get("departments") if str(params.get("listVal")) == "3" else []
    if path == "/akademisyen/list":
        return {"data": [data["list_row"]], "recordsTotal": 1, "recordsFiltered": 1, "totalPages": 1} if data.get("list_row") else {"data": []}
    if path == "/proje/detay":
        return data.get(f"/proje/detay?projeId={params.get('projeId')}") or {}
    if path == "/yayin/list" and params.get("yayinAnaTurId"):
        return data.get(f"/yayin/list?yayinAnaTurId={params['yayinAnaTurId']}") or {"data": []}
    if path.startswith("/akademisyen/birlikte/calisanlar/") or path.startswith("/tez/yurt/ici/yonetilen/"):
        return data.get(path.split(GUID)[0].rstrip("/") + "/{guid}") or []
    return data.get(path, {"data": []})


def home() -> str:
    return _yok().get("home") or ""


# ------------------------------------------------------------------ hazır profil (history)
def chat() -> dict | None:
    r = _profile()
    if not r:
        return None
    p = r["profile"]
    return {"id": CHAT_ID, "job_id": JOB_ID, "name": p.get("name"), "title": p.get("title"), "institution": p.get("institution"),
            "papers": r.get("unique_count", 0), "created": r.get("created", "2026-11-22 12:00:00"),
            "updated": r.get("created", "2026-11-22 12:00:00"), "messages": [], "demo": True}


def result(job_id: str) -> dict | None:
    return dict(_profile()) if job_id == JOB_ID and _profile() else None


def attach(people: list[dict]) -> list[dict]:
    """Kadro listesinde Bahadır Arslan'a hazır profilin bağlantısı (tıklayınca yeni tarama yerine profil açılır)."""
    if _profile():
        for p in people:
            if (p.get("yok_id") or "").upper() == GUID:
                p["chat_id"] = CHAT_ID
    return people
