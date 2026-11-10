"""Konular sayfasının rafları ve uygulama içi PDF okuyucu.

- Türkiye gündemi: Türkiye adresli yayınlarda son 12 ayda en hızlı büyüyen OpenAlex konuları.
- Okuma köşesi: alana göre (tıp, mühendislik, yazılım…) Türkiye adresli, açık erişimli, çok atıf alan güncel yayınlar.
- PDF: yalnız herkese açık adresten okunur. Yayıncı erişimi kapatmışsa koruma aşılmaz; aynı DOI'nin OpenAlex'te
  kayıtlı yasal açık erişim kopyaları denenir.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import date, timedelta

import httpx

from .config import ROOT
from .org_assets import public_client, read_public
from .text import clean

OPENALEX = "https://api.openalex.org"
UA = "AkademikIz/2.0 (https://github.com/akademik-iz; academic research PoC) httpx"
CACHE = ROOT / "data" / "reading"
DAY = 24 * 3600
PDF_MAX = 30_000_000
TR = "institutions.country_code:TR"
# Okuma köşesi rafları: OpenAlex alan/domain kimlikleriyle
CATEGORIES = {
    "tip": ("Tıp ve Sağlık", "heart", "primary_topic.domain.id:4"),
    "muhendislik": ("Mühendislik", "settings", "primary_topic.field.id:22|25|21"),
    "kod": ("Yazılım ve Yapay Zekâ", "code", "primary_topic.field.id:17"),
    "temel": ("Temel Bilimler", "atom", "primary_topic.field.id:26|31|16"),
    "yasam": ("Yaşam ve Çevre", "leaf", "primary_topic.domain.id:1"),
    "sosyal": ("Sosyal Bilimler", "scale", "primary_topic.domain.id:2"),
    "sanayi": ("Sanayi ve Ar-Ge", "briefcase", "institutions.type:company"),
}
_LOCKS: dict[str, asyncio.Lock] = {}


def _load(name: str, ttl: int):
    try:
        d = json.loads((CACHE / f"{name}.json").read_text(encoding="utf-8"))
        return d["data"] if time.time() - d.get("ts", 0) < ttl else None
    except (OSError, ValueError, KeyError):
        return None


def _save(name: str, data):
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / f"{name}.json").write_text(json.dumps({"ts": time.time(), "data": data}, ensure_ascii=False), encoding="utf-8")


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=25, headers={"User-Agent": UA})


# ------------------------------------------------------------------ Türkiye gündemi
async def _turkish(rows: list[dict], llm) -> list[dict]:
    """Konu adlarını tek LLM çağrısıyla Türkçeye çevirir (`name_tr`); çevrilemezse İngilizce ad kalır."""
    todo = [r for r in rows if not r.get("name_tr")]
    if not todo or llm is None or not llm.available:
        return rows
    try:
        data = await llm.json(
            "Aşağıdaki akademik araştırma konusu adlarını kısa ve doğal Türkçe terimlere çevir. Yerleşik Türkçe "
            "karşılığı olmayan kısaltma ve özel adları (ör. COVID-19, MIMO) olduğu gibi bırak. Sırayı koru.\n"
            + "\n".join(f"{i + 1}. {r['name']}" for i, r in enumerate(todo)),
            {"type": "object", "properties": {"tr": {"type": "array", "items": {"type": "string"}}}, "required": ["tr"]},
            timeout=40, fast=True)
    except Exception:  # noqa: BLE001  çeviri yalnız görünüm; gündem yine gösterilir
        return rows
    names = (data or {}).get("tr") or []
    if len(names) == len(todo):
        for r, name in zip(todo, names):
            if clean(name):
                r["name_tr"] = clean(name)
    return rows


async def trending(limit: int = 14, llm=None) -> list[dict]:
    """Son 12 ayda Türkiye adresli yayınlarda en hızlı büyüyen konular (önceki 12 aya göre)."""
    cached = _load("trending", DAY)
    if cached is not None:
        if llm is not None and any(not r.get("name_tr") for r in cached):
            cached = await _turkish(cached, llm)
            if all(r.get("name_tr") for r in cached):
                _save("trending", cached)
        return cached
    async with _LOCKS.setdefault("trending", asyncio.Lock()):
        today = date.today()
        cur_from, prev_from = today - timedelta(days=365), today - timedelta(days=730)

        async def groups(start, end):
            r = await client.get(f"{OPENALEX}/works", params={
                "filter": f"{TR},from_publication_date:{start},to_publication_date:{end}", "group_by": "primary_topic.id", "per_page": 200})
            r.raise_for_status()
            return {g["key"]: (g["key_display_name"], g["count"]) for g in r.json().get("group_by", [])}
        async with _client() as client:
            cur, prev = await asyncio.gather(groups(cur_from, today), groups(prev_from, cur_from - timedelta(days=1)))
        rows = []
        for key, (name, n) in cur.items():
            if key not in prev:  # önceki dönemin ilk 200'ünde yoksa sayısı bilinmiyor: büyüme hesaplanmaz
                continue
            before = prev[key][1]
            if n >= 60:
                rows.append({"id": key.rsplit("/", 1)[-1], "name": name, "count": n, "prev": before,
                             "growth": round((n - before) / max(before, 1) * 100)})
        rows.sort(key=lambda r: -(r["count"] - r["prev"]) / (r["prev"] + 40))
        out = await _turkish(rows[:limit], llm)
        if out:
            _save("trending", out)
        return out


# ------------------------------------------------------------------ okuma köşesi
def _abstract(inverted: dict | None) -> str:
    """OpenAlex'in ters dizinli özetini düz metne çevirir."""
    if not inverted:
        return ""
    words = sorted((i, word) for word, places in inverted.items() for i in places)
    return clean(" ".join(word for _i, word in words))[:2500]


def _work(w: dict) -> dict:
    oa = w.get("best_oa_location") or {}
    src = ((w.get("primary_location") or {}).get("source") or {})
    return {"id": (w.get("id") or "").rsplit("/", 1)[-1], "title": clean(w.get("title") or ""), "year": w.get("publication_year"),
            "doi": (w.get("doi") or "").replace("https://doi.org/", ""), "venue": src.get("display_name") or "",
            "authors": [clean((a.get("author") or {}).get("display_name") or "") for a in (w.get("authorships") or [])[:4]],
            "institutions": sorted({clean(i.get("display_name") or "") for a in (w.get("authorships") or [])
                                    for i in a.get("institutions") or [] if i.get("country_code") == "TR"})[:3],
            "pdf": oa.get("pdf_url") or "", "url": oa.get("landing_page_url") or w.get("doi") or "",
            "citations": w.get("cited_by_count") or 0, "topic": ((w.get("primary_topic") or {}).get("display_name") or ""),
            "abstract": _abstract(w.get("abstract_inverted_index"))}


async def shelf(cat: str) -> dict | None:
    """Bir alanın okuma rafı: son iki yılda Türkiye adresli, açık erişimli, en çok atıf alan yayınlar."""
    if cat not in CATEGORIES:
        return None
    label, icon, filt = CATEGORIES[cat]
    cached = _load(f"shelf2-{cat}", DAY)
    if cached is not None:
        return cached
    since = date.today() - timedelta(days=730)
    async with _client() as client:
        r = await client.get(f"{OPENALEX}/works", params={
            "filter": f"{TR},is_oa:true,{filt},from_publication_date:{since},type:article", "sort": "cited_by_count:desc",
            "per_page": 24, "select": "id,doi,title,publication_year,authorships,primary_location,best_oa_location,cited_by_count,primary_topic,abstract_inverted_index"})
        r.raise_for_status()
    items = [x for x in (_work(w) for w in r.json().get("results", [])) if x["title"]]
    out = {"id": cat, "label": label, "icon": icon, "items": items}
    if items:
        _save(f"shelf2-{cat}", out)
    return out


async def topic_works(topic_id: str = "", q: str = "", en: str = "") -> dict:
    """Bir konunun rafı. Gündem konusu OpenAlex kimliğiyle (son 12 ay, Türkiye adresli); kullanıcının aradığı
    konu metinle aranır (önce Türkiye adresli, azsa bütün dünyadan). En çok atıf alanlar önde."""
    topic_id = topic_id.strip().rsplit("/", 1)[-1]
    if topic_id and not (topic_id[:1] in "Tt" and topic_id[1:].isdigit()):
        topic_id = ""
    text = clean(en or q)[:160]
    if not topic_id and len(text) < 3:
        return {"items": [], "scope": ""}
    key = "topic2-" + hashlib.sha1(f"{topic_id}|{fold_key(text)}".encode()).hexdigest()[:16]
    cached = _load(key, DAY)
    if cached is not None:
        return cached
    select = "id,doi,title,publication_year,authorships,primary_location,best_oa_location,cited_by_count,primary_topic,abstract_inverted_index"
    async with _client() as client:
        async def get(filt: str, search: str = ""):
            params = {"filter": filt, "sort": "cited_by_count:desc", "per_page": 20, "select": select}
            if search:
                params["search"] = search
            r = await client.get(f"{OPENALEX}/works", params=params)
            r.raise_for_status()
            return [x for x in (_work(w) for w in r.json().get("results", [])) if x["title"]]
        if topic_id:
            since = date.today() - timedelta(days=365)
            items, scope = await get(f"{TR},primary_topic.id:{topic_id},from_publication_date:{since}"), "tr-year"
        else:
            since = date.today() - timedelta(days=5 * 365)
            items, scope = await get(f"{TR},from_publication_date:{since}", text), "tr"
            if len(items) < 6:
                items, scope = await get(f"from_publication_date:{since}", text), "world"
    out = {"items": items, "scope": scope}
    if items:
        _save(key, out)
    return out


def fold_key(text: str) -> str:
    return " ".join(text.lower().split())


def categories() -> list[dict]:
    return [{"id": k, "label": v[0], "icon": v[1]} for k, v in CATEGORIES.items()]


# ------------------------------------------------------------------ PDF
async def _oa_copies(client, doi: str) -> list[str]:
    if not doi:
        return []
    r = await client.get(f"{OPENALEX}/works/doi:{doi}", params={"select": "best_oa_location,locations"})
    if r.status_code != 200:
        return []
    w = r.json()
    urls = [(w.get("best_oa_location") or {}).get("pdf_url")] + [loc.get("pdf_url") for loc in w.get("locations") or []]
    return [u for u in dict.fromkeys(urls) if u]


async def pdf(url: str, doi: str = "") -> tuple[bytes, str]:
    """PDF baytları ve okunduğu adres. Önce verilen adres, açılmazsa aynı DOI'nin açık erişim kopyaları."""
    doi = doi.replace("https://doi.org/", "").strip()
    key = hashlib.sha256(f"{url}|{doi}".encode()).hexdigest()[:24]
    path = CACHE / "pdf" / f"{key}.pdf"
    if path.exists() and time.time() - path.stat().st_mtime < 7 * DAY:
        return path.read_bytes(), url
    tried = []
    async with public_client(timeout=25, headers={"User-Agent": UA, "Accept": "application/pdf,*/*;q=0.5"}) as client:
        candidates = [url] if url else []
        for attempt in range(2):
            for target in candidates:
                if target in tried:
                    continue
                tried.append(target)
                try:
                    raw, _mime, final = await read_public(client, target, PDF_MAX)
                except (httpx.HTTPError, ValueError, OSError):
                    continue
                if raw[:5] == b"%PDF-":
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(raw)
                    return raw, final
            if attempt == 0:
                async with _client() as oa:
                    try:
                        candidates = await _oa_copies(oa, doi)
                    except httpx.HTTPError:
                        candidates = []
    raise ValueError("Bu yayının PDF'i yayıncı tarafından kapalı ya da açık erişim kopyası bulunamadı.")


# ------------------------------------------------------------------ makale yazarları ve kurumları
async def authorships(doi: str) -> list[dict]:
    """DOI'den yazarlar ve kurumları (OpenAlex). Türk üniversiteleri YÖK listesindeki kimlikle eşlenir
    (arayüzde üniversite sayfasına bağlanır); eşleşmeyen kurum yalnız adıyla gösterilir."""
    from . import yokdir
    doi = doi.replace("https://doi.org/", "").strip()
    if not doi:
        return []
    cached = _load("auth-" + hashlib.sha1(doi.encode()).hexdigest()[:16], 7 * DAY)
    if cached is not None:
        return cached
    async with _client() as client:
        r = await client.get(f"{OPENALEX}/works/doi:{doi}", params={"select": "authorships"})
    if r.status_code != 200:
        return []
    unis = await yokdir.university_list()
    by_key = {}
    for u in unis:
        for label in (u.get("raw"), u.get("name_en")):
            if label:
                by_key[yokdir._key(label)] = u["id"]
    out = []
    for a in r.json().get("authorships") or []:
        insts = []
        for i in a.get("institutions") or []:
            name = clean(i.get("display_name") or "")
            uid = by_key.get(yokdir._key(name)) if i.get("country_code") == "TR" else None
            if not uid and i.get("country_code") == "TR":
                hit = yokdir.match_university([{"name": u.get("name_en") or "", "id": u["id"]} for u in unis if u.get("name_en")], [name])
                uid = hit["id"] if hit else None
            insts.append({"name": name, "country": i.get("country_code") or "", "uni_id": uid or ""})
        author = a.get("author") or {}
        out.append({"name": clean(author.get("display_name") or ""), "orcid": (author.get("orcid") or "").rsplit("/", 1)[-1], "institutions": insts})
    out = [x for x in out if x["name"]][:40]
    _save("auth-" + hashlib.sha1(doi.encode()).hexdigest()[:16], out)
    return out


async def abstract_of(doi: str) -> str:
    """Makalenin özeti (OpenAlex); kütüphanede kitabın arka kapağı ve okuma sayfası için."""
    doi = doi.replace("https://doi.org/", "").strip()
    if not doi:
        return ""
    key = "abs-" + hashlib.sha1(doi.encode()).hexdigest()[:16]
    cached = _load(key, 30 * DAY)
    if cached is not None:
        return cached
    async with _client() as client:
        r = await client.get(f"{OPENALEX}/works/doi:{doi}", params={"select": "abstract_inverted_index"})
    text = _abstract(r.json().get("abstract_inverted_index")) if r.status_code == 200 else ""
    _save(key, text)
    return text
