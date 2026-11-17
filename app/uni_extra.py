"""Üniversite için ek açık kaynaklar.

Erasmus: Avrupa Yükseköğretim Kurumları kaydı (HEI API, European University Foundation; açık JSON). Kurumun Erasmus
kodu, Erasmus Yükseköğretim Beyannamesi (ECHE) sahipliği ve geçerlilik tarihleri, PIC numarası. Türkiye listesi tek
istekle alınır ve 30 gün saklanır; üniversite alan adıyla, olmazsa İngilizce adıyla eşleştirilir.
"""
from __future__ import annotations

import json
import re
import time
from urllib.parse import urlsplit

import httpx

from .config import ROOT
from .discover import registrable
from .text import clean, fold

DIR = ROOT / "data" / "extra"
TTL = 30 * 24 * 3600
HEI = "https://hei.api.uni-foundation.eu/api/public/v1/country/TR/hei"
UA = {"User-Agent": "academic-profile-poc/1.0", "Accept": "application/json"}


async def _hei_list() -> list[dict]:
    path = DIR / "hei-tr.json"
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - saved.get("ts", 0) < TTL:
            return saved["rows"]
    except (OSError, ValueError, KeyError):
        saved = None
    try:
        async with httpx.AsyncClient(timeout=30, headers=UA) as client:
            r = await client.get(HEI)
        data = r.json().get("data") if r.status_code == 200 else None
    except (httpx.HTTPError, ValueError):
        data = None
    if not isinstance(data, list):
        return (saved or {}).get("rows") or []
    rows = []
    for item in data:
        a = item.get("attributes") or {}
        ids = {x.get("type"): x.get("value") for x in a.get("other_id") or [] if isinstance(x, dict)}
        rows.append({"id": clean(str(a.get("hei_id") or item.get("id") or "")).lower(), "label": clean(a.get("label") or ""),
                     "city": clean(a.get("city") or ""), "eche": bool(a.get("eche_holder")), "start": a.get("eche_start_date") or "",
                     "end": a.get("eche_end_date") or "", "erasmus": ids.get("erasmus") or "", "charter": ids.get("erasmus-charter") or "",
                     "pic": ids.get("pic") or ""})
    try:
        DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"ts": time.time(), "rows": rows}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return rows


def _words(name: str) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9]+", fold(name)) if len(w) > 2 and w not in {"university", "universitesi", "the", "and"}}


async def erasmus(uid: str) -> dict | None:
    """Üniversitenin Erasmus kaydı: {"code", "eche", "start", "end", "pic", "label"} ya da None."""
    from . import org_assets, yokdir
    rows = await _hei_list()
    if not rows:
        return None
    uni = await yokdir._university(uid) or {}
    home = await org_assets.university_home(uid) or ""
    domain = registrable(urlsplit(home).hostname or "")
    hit = next((r for r in rows if domain and (r["id"] == domain or r["id"].endswith("." + domain))), None)
    if not hit:
        # Kurum alan adını değiştirmiş olabilir (boun.edu.tr → bogazici.edu.tr): İngilizce adın kelimeleri tutmalı.
        want = _words(uni.get("name_en") or "")
        hit = next((r for r in rows if want and want == _words(r["label"])), None) \
            or next((r for r in rows if want and len(want) >= 2 and want <= _words(r["label"])), None)
    if not hit:
        return None
    return {"code": hit["erasmus"], "eche": hit["eche"], "start": hit["start"], "end": hit["end"], "pic": hit["pic"],
            "charter": hit["charter"], "label": hit["label"], "source": "Avrupa Yükseköğretim Kurumları kaydı (HEI API)"}
