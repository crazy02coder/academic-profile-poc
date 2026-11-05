"""Firma → akademisyen (ters yön): resmi Ar-Ge / Tasarım Merkezi listesindeki bir firmayla çalışan akademisyenler.

Üç kanıt kaynağı birleştirilir:
  * OpenAlex  — firmada çalışan biriyle ortak yayını olan Türk üniversitesi yazarları (kurum türü "education")
  * TR Dizin  — yazar adresinde firma geçen yayınlardaki üniversiteli ortak yazarlar
  * Profiller — bu uygulamada profili çıkarılmış akademisyenlerin sanayi iş birlikleri (YÖK deneyim, proje…)
Sonuçlar data/firms/<firma>.json'da 7 gün saklanır; OpenAlex kotası dolduğunda eksik sonuç saklanmaz.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from collections import Counter

import httpx

from . import history as history_store
from . import industry, patents, trsources
from .config import OPENALEX_PARAMS, ROOT, USER_AGENT
from .text import clean, fold, name_tokens, word_match

FIRMS_DIR = ROOT / "data" / "firms"
TTL = 7 * 24 * 3600
CACHE_V = 2  # önbellek biçimi: değişince eski firma sonuçları yeniden toplanır
OPENALEX = "https://api.openalex.org"
UNIVERSITY = re.compile(r"[üu]niversit|university", re.I)


def _fid(key: tuple) -> str:
    return "-".join(key)


def _groups() -> dict[str, dict]:
    groups, _ = industry._index()
    return {_fid(k): g for k, g in groups.items()}


def _public(fid: str, g: dict) -> dict:
    return {"id": fid, "name": g["name"], "centers": g["centers"], "cities": sorted(g["cities"]),
            "sectors": sorted(g["sectors"]), "kinds": sorted(g["kinds"]), "areas": _areas().get(fid, {})}


# ------------------------------------------------------------------ çalışma alanları (scripts/build_firm_areas.py üretir)
AREAS_PATH = ROOT / "data" / "firm_areas.json"
_areas_cache: tuple[float, dict] = (0, {})


def _areas() -> dict:
    global _areas_cache
    try:
        mtime = AREAS_PATH.stat().st_mtime
    except OSError:
        return {}
    if _areas_cache[0] != mtime:
        _areas_cache = (mtime, json.loads(AREAS_PATH.read_text()).get("firms", {}))
    return _areas_cache[1]


# ------------------------------------------------------------------ uygulamadaki profiller
_LOCAL: dict[str, tuple[float, list]] = {}


def _profile_links() -> dict[str, list[dict]]:
    """Firma adı → profili çıkarılmış ve o firmayla iş birliği bulunan akademisyenler."""
    out: dict[str, list[dict]] = {}
    for chat in history_store.list_all():
        jid = chat.get("job_id") or ""
        try:
            path = history_store.RUNS_DIR / f"{history_store._safe(jid)}.json"
        except ValueError:
            continue
        if not path.exists():
            continue
        mtime = path.stat().st_mtime
        cached = _LOCAL.get(jid)
        if not cached or cached[0] != mtime:
            try:
                r = json.loads(path.read_text())
            except ValueError:
                continue
            ind = r.get("industry")
            if ind is None or r.get("industry_v") != industry.VERSION:
                ind = industry.collaborations(r.get("publications") or [], r.get("profile") or {})
            cached = _LOCAL[jid] = (mtime, [e for e in ind if e.get("official")])
        for e in cached[1]:
            out.setdefault(e["name"], []).append({
                "name": chat.get("name"), "title": chat.get("title"), "institution": chat.get("institution"),
                "chat_id": chat.get("id"), "evidence": [{"type": v["type"], "text": v["text"]} for v in e["evidence"]]})
    return out


def firm_list(q: str = "", sector: str = "", city: str = "", area: str = "") -> dict:
    info = industry.centers_info()
    if not info.get("available"):
        return {"available": False, "items": [], "sectors": [], "cities": []}
    groups = _groups()
    links = _profile_links()
    areas = _areas()
    area_counts = Counter(x["name"] for fid in groups for x in areas.get(fid, {}).get("tags", []))
    items = []
    for fid, g in groups.items():
        if q and not word_match(q, g["name"], *g["centers"]):
            continue
        if sector and sector not in g["sectors"]:
            continue
        if city and city not in g["cities"]:
            continue
        if area and not any(x["name"] == area for x in areas.get(fid, {}).get("tags", [])):
            continue
        cached = _cached(fid)
        items.append(_public(fid, g) | {"profiles": len(links.get(g["name"], [])),
                                        "academics": cached.get("academic_count") if cached else None})
    items.sort(key=lambda x: (-x["profiles"], -(x["academics"] or 0), -len(x["centers"]), fold(x["name"])))
    return {"available": True, "info": info, "total": len(groups), "count": len(items), "items": items[:300],
            "sectors": sorted({s for g in groups.values() for s in g["sectors"] if s}),
            "cities": sorted({c for g in groups.values() for c in g["cities"] if c}),
            "areas": [{"name": k, "count": n} for k, n in sorted(area_counts.items(), key=lambda x: (-x[1], x[0]))]}


# ------------------------------------------------------------------ dış kaynaklar
def _names(g: dict) -> list[str]:
    """Firmanın aranacak adları: listedeki marka adı + kısaltma/yabancı adları (industry.ALIASES)."""
    return [g["name"]] + [alias for alias, target in industry.ALIASES.items() if industry.match(target) is g]


QUOTA = "OpenAlex günlük kotası doldu (gece 03:00'te yenilenir)"


async def _openalex(client, g: dict) -> tuple[list[dict], str]:
    """(akademisyen-yayın satırları, hata).

    İki yol birleştirilir: firmanın OpenAlex kurum kaydı (varsa) ve yayınlardaki ham yazar adresleri
    ("R&D Dept, Aydin Yazilim ve Elektronik San. A.S., Ankara"). Birçok firmanın kurum kaydı yoktur.
    """
    r = await client.get(f"{OPENALEX}/institutions", params={
        "search": g["name"], "filter": "country_code:TR", "per-page": 25, **OPENALEX_PARAMS,
        "select": "id,display_name,type,works_count"})
    if r.status_code == 429:
        return [], QUOTA
    if r.status_code != 200:
        return [], f"OpenAlex {r.status_code}"
    ids = {i["id"].rsplit("/", 1)[-1] for i in r.json().get("results") or []
           if industry.match(i.get("display_name") or "") is g}
    filters = ([f"institutions.id:{'|'.join(ids)}"] if ids else []) + \
        [f'raw_affiliation_strings.search:"{n}"' for n in _names(g)]

    at_firm = _at_firm(g, ids)
    works: dict[str, dict] = {}
    for f in filters:
        for page in (1, 2):
            r = await client.get(f"{OPENALEX}/works", params={
                "filter": f"{f},institutions.type:education", "per-page": 200, "page": page,
                "sort": "publication_year:desc", **OPENALEX_PARAMS,
                "select": "id,doi,display_name,publication_year,authorships,cited_by_count"})
            if r.status_code == 429:
                return _openalex_rows(works.values(), at_firm), QUOTA
            batch = (r.json().get("results") or []) if r.status_code == 200 else []
            works.update((w["id"], w) for w in batch)
            if len(batch) < 200:
                break
    return _openalex_rows(works.values(), at_firm), ""


TURKEY = re.compile(r"t[uü]rk[iı]ye|turkey|\bTR\b", re.I)
NOT_FIRM_ADDRESS = re.compile(r"[üu]niversit|university|college|hospital|hastane|fak[üu]lte|faculty|school of|klinik|clinic", re.I)
# Marka ardından gelebilen kurumsal kelimeler ("Aselsan Research Center", "Arçelik Ar-Ge")
UNIT_WORDS = {"research", "center", "centre", "merkezi", "arge", "ar", "rd", "dept", "department", "division", "group",
              "grubu", "technologies", "technology", "teknoloji", "teknolojileri", "company", "co", "turkey", "turkiye"}


def firm_address(address: str, g: dict, in_turkey: bool = False) -> bool:
    """Ham yazar adresi bu firmayı mı gösteriyor? Tek kelimelik marka şehir ya da soyadı olabilir ("Agra, India"; "Doğu Anadolu").

    Adres Türkiye'de olmalı (metinde yazmıyorsa in_turkey: OpenAlex yazarı yalnızca Türkiye'ye bağlamış), üniversite/hastane
    adresi olmamalı; marka ya şirket ekiyle ya listedeki devam kelimesiyle ya da kurumsal bir kelimeyle birlikte veya adres
    parçasında tek başına yazılmalı.
    """
    if not address or not (in_turkey or TURKEY.search(address)) or NOT_FIRM_ADDRESS.search(address):
        return False
    for part in address.split(","):
        if industry.match(part) is not g:
            continue
        folded = " ".join(industry._words(part))
        if any(alias in folded and industry.match(target) is g for alias, target in industry.ALIASES.items()):
            return True  # "Ford Otosan" → Ford Otomotiv
        words = industry._words(re.sub(r"\([^)]*\)", " ", part))
        key = list(g["key"])
        i = next((n for n in range(len(words)) if words[n:n + len(key)] == key), None)
        if i is None:
            return True  # kısaltma/yabancı ad eşleşmesi (industry.ALIASES)
        after = [w for w in words[i + len(key):] if w not in industry.LEGAL]
        suffixed = i + len(key) < len(words) and words[i + len(key)] in industry.FIRM_SUFFIX
        if suffixed or not after or after[0] in g["nexts"] or after[0] in UNIT_WORDS:
            return True
    return False


def _at_firm(g: dict, ids: set[str]):
    """Yazar bu firmada mı: firmanın kurum kaydı ya da firma_address kuralını geçen ham adres."""
    def check(a) -> bool:
        if any(i.get("id", "").rsplit("/", 1)[-1] in ids for i in a.get("institutions") or []):
            return True
        in_turkey = (a.get("countries") or []) == ["TR"]
        return any(firm_address(s, g, in_turkey) for s in a.get("raw_affiliation_strings") or [])
    return check


async def openalex_areas(client, g: dict) -> dict | None:
    """Firmanın yayınlarından çalışma alanları; yazarlardan biri firmada değilse yayın sayılmaz. Kota/ağ hatasında None."""
    r = await client.get(f"{OPENALEX}/institutions", params={
        "search": g["name"], "filter": "country_code:TR", "per-page": 25, **OPENALEX_PARAMS, "select": "id,display_name"})
    if r.status_code != 200:
        return None
    ids = {i["id"].rsplit("/", 1)[-1] for i in r.json().get("results") or [] if industry.match(i.get("display_name") or "") is g}
    filters = ([f"institutions.id:{'|'.join(ids)}"] if ids else []) + \
        [f'raw_affiliation_strings.search:"{n}"' for n in _names(g)]
    at_firm = _at_firm(g, ids)
    works: dict[str, dict] = {}
    for f in filters:
        r = await client.get(f"{OPENALEX}/works", params={
            "filter": f, "per-page": 200, "sort": "publication_year:desc", "select": "id,authorships,primary_topic", **OPENALEX_PARAMS})
        if r.status_code != 200:
            return None
        works.update((w["id"], w) for w in r.json().get("results") or [] if any(at_firm(a) for a in w.get("authorships") or []))
    subfields, topics = Counter(), Counter()
    for w in works.values():
        t = w.get("primary_topic") or {}
        if t.get("display_name"):
            topics[t["display_name"]] += 1
        if (t.get("subfield") or {}).get("display_name"):
            subfields[t["subfield"]["display_name"]] += 1
    return {"papers": len(works), "tags": [{"name": k, "count": n} for k, n in subfields.most_common(6)],
            "topics": [{"name": k, "count": n} for k, n in topics.most_common(8)]}


def _openalex_rows(works, at_firm) -> list[dict]:
    rows = []
    for w in works:
        firm_people, academics = [], []
        for a in w.get("authorships") or []:
            name = clean((a.get("author") or {}).get("display_name") or "")
            if not name:
                continue
            if at_firm(a):
                firm_people.append(name)
                continue
            uni = next((i for i in a.get("institutions") or [] if i.get("type") == "education" and i.get("country_code") == "TR"), None)
            if uni:
                academics.append((name, (a.get("author") or {}).get("id", ""), clean(uni.get("display_name") or "")))
        if not firm_people:
            continue  # ham adres araması firmayı başka bağlamda (ör. teşekkür) bulmuş olabilir
        paper = {"title": clean(w.get("display_name") or ""), "year": w.get("publication_year"),
                 "url": w.get("doi") or w["id"], "source": "OpenAlex", "firm_people": firm_people[:6],
                 "citations": w.get("cited_by_count")}
        rows += [{"name": n, "openalex": aid, "institution": inst, "paper": paper} for n, aid, inst in academics]
    return rows


async def _trdizin(client, g: dict) -> tuple[list[dict], str]:
    rows = []
    try:
        hits = [h for name in _names(g) for page in (1, 2) for h in await trsources.trdizin_search(client, name, 100, page)]
    except httpx.HTTPError as exc:
        return [], f"TR Dizin: {type(exc).__name__}"

    def texts(a):
        return ((a.get("institution") or {}).get("rootTitle") or []) + (a.get("institutionName") or [])

    def at_firm(a):
        return any(industry.match(part) is g for t in texts(a) for part in re.split(r"[,;/]", t or ""))

    for s in hits:
        if s.get("docType") == "PROJECT":
            continue  # TÜBİTAK projeleri _ardeb'de (ekip + özetteki firma)
        authors = s.get("authors") or []
        firm_people = [clean(a.get("name") or "") for a in authors if at_firm(a)]
        if not firm_people:
            continue
        abstracts = s.get("abstracts") or []
        title = next((x.get("title") for x in abstracts if x.get("title")), "")
        paper = {"title": clean(title), "year": s.get("publicationYear"), "url": f"{trsources.TRDIZIN_PAGE}{s.get('id')}",
                 "source": "TR Dizin", "firm_people": firm_people[:6], "citations": s.get("orderCitationCount")}
        for a in authors:
            # Adres metninin üniversite geçen parçası ("Bilgi Teknolojileri Grubu, Wageningen University, …")
            uni = next((part for t in texts(a) for part in (t or "").split(",") if UNIVERSITY.search(part)), "")
            if uni and not at_firm(a) and a.get("name"):
                rows.append({"name": clean(a["name"]), "institution": clean(uni), "paper": paper})
    return rows, ""


async def _ardeb(client, g: dict) -> tuple[list[dict], list[dict], str]:
    """TÜBİTAK (ARDEB) projeleri: özetinde firma iş birliği ifadesiyle geçen projeler ve proje ekibi.

    Dönüş: (akademisyen satırları, projeler, hata).
    """
    hits: dict = {}
    try:
        for name in _names(g):
            for page in (1, 2, 3):
                batch = await trsources.trdizin_search(client, name, 100, page, doc_type="PROJECT")
                hits.update((h.get("id"), h) for h in batch)
                if len(batch) < 100:
                    break
    except httpx.HTTPError as exc:
        return [], [], f"TÜBİTAK ARDEB: {type(exc).__name__}"
    rows, projects = [], []
    for s in hits.values():
        abstracts = s.get("abstracts") or []
        text = " ".join(f"{x.get('title') or ''}. {x.get('abstract') or ''}" for x in abstracts)
        quote = next((sent for found, sent in industry.mentions(text) if found is g), "")
        if not quote:
            continue
        team = [{"name": clean(a.get("name") or ""), "role": trsources.PROJECT_ROLES[a.get("duty")]}
                for a in sorted(s.get("authors") or [], key=lambda a: a.get("order") or 0)
                if a.get("duty") in trsources.PROJECT_ROLES and a.get("name")]
        title = clean(next((x.get("title") for x in abstracts if x.get("title")), ""))
        project = {"title": title, "year": s.get("publicationYear"), "url": f"{trsources.TRDIZIN_PAGE}{s.get('id')}",
                   "group": s.get("projectGroup") or "", "number": s.get("projectnumber") or "", "quote": quote, "team": team}
        projects.append(project)
        for m in team:
            paper = {"title": title, "year": project["year"], "url": project["url"], "source": "TÜBİTAK ARDEB",
                     "firm_people": [], "role": m["role"], "quote": quote}
            rows.append({"name": m["name"], "institution": "", "paper": paper})
    projects.sort(key=lambda x: -(x["year"] or 0))
    return rows, projects, ""


async def _teydeb(g: dict) -> tuple[list[dict], str]:
    """Firmanın TÜBİTAK TEYDEB tamamlanmış projeleri (PRODİS); kuruluş adı resmi listedeki firmayla eşleşmeli."""
    try:
        rows = await trsources.teydeb_projects(g["name"])
    except httpx.HTTPError as exc:
        return [], f"TÜBİTAK TEYDEB: {type(exc).__name__}"
    rows = [r for r in rows if industry.match(r.get("firm") or "") is g]
    return sorted(rows, key=lambda r: -(r["year"] or 0)), ""


def _merge(rows: list[dict], local: list[dict]) -> list[dict]:
    people: dict[tuple, dict] = {}
    for row in rows:
        key = tuple(sorted(name_tokens(row["name"])))
        if not key:
            continue
        p = people.setdefault(key, {"name": row["name"], "institution": "", "papers": [], "sources": set(),
                                    "evidence": [], "chat_id": "", "title": "", "openalex": ""})
        p["institution"] = p["institution"] or row.get("institution", "")
        p["openalex"] = p["openalex"] or row.get("openalex", "")
        p["sources"].add(row["paper"]["source"])
        if not any(fold(x["title"]) == fold(row["paper"]["title"]) for x in p["papers"]):
            p["papers"].append(row["paper"])
    for row in local:
        key = tuple(sorted(name_tokens(row["name"] or "")))
        p = people.setdefault(key, {"name": row["name"], "institution": row.get("institution") or "", "papers": [],
                                    "sources": set(), "evidence": [], "chat_id": "", "title": "", "openalex": ""})
        p.update(chat_id=row["chat_id"], title=row.get("title") or "", evidence=row["evidence"])
        p["institution"] = row.get("institution") or p["institution"]
        p["sources"].add("Profil")
    out = []
    for p in people.values():
        p["papers"].sort(key=lambda x: -(x["year"] or 0))
        out.append(p | {"sources": sorted(p["sources"])})
    return sorted(out, key=lambda p: (not p["chat_id"], -len(p["papers"]), fold(p["name"])))


# ------------------------------------------------------------------ önbellek ve giriş noktası
def _path(fid: str, kind: str = ""):
    return FIRMS_DIR / f"{re.sub(r'[^a-z0-9-]', '', fid)}{'.' + kind if kind else ''}.json"


def _cached(fid: str, kind: str = "") -> dict | None:
    p = _path(fid, kind)
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text())
    except ValueError:
        return None
    return d if d.get("v") == CACHE_V and time.time() - d.get("ts", 0) < TTL else None


async def firm_detail(fid: str, refresh: bool = False) -> dict | None:
    g = _groups().get(fid)
    if not g:
        return None
    local = _profile_links().get(g["name"], [])
    cached = None if refresh else _cached(fid)
    if cached:
        rows, errors, ts = cached["rows"], cached["errors"], cached["ts"]
        ardeb = cached["ardeb"]
    else:
        async with httpx.AsyncClient(timeout=30, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}) as client:
            results = await asyncio.gather(_openalex(client, g), _trdizin(client, g), _ardeb(client, g),
                                           return_exceptions=True)
        rows, errors, ardeb = [], [], []
        for label, res in zip(("OpenAlex", "TR Dizin", "TÜBİTAK ARDEB"), results):
            if isinstance(res, Exception):
                errors.append(f"{label}: {type(res).__name__}")
                continue
            rows += res[0]
            if label == "TÜBİTAK ARDEB":
                ardeb = res[1]
            if res[-1]:
                errors.append(res[-1])
        ts = time.time()
        # Kota/ağ hatasıyla eksik kalan sonuç saklanmaz: bir sonraki açılışta yeniden denenir.
        if not errors:
            FIRMS_DIR.mkdir(parents=True, exist_ok=True)
            count = len({tuple(sorted(name_tokens(r["name"]))) for r in rows})
            _path(fid).write_text(json.dumps({"v": CACHE_V, "ts": ts, "rows": rows, "errors": errors, "ardeb": ardeb,
                                              "academic_count": count}, ensure_ascii=False))
    academics = _merge(rows, local)
    by_source: dict[str, int] = {}
    for p in academics:
        for s in p["sources"]:
            by_source[s] = by_source.get(s, 0) + 1
    return {"firm": _public(fid, g), "academics": academics, "by_source": by_source, "errors": errors,
            "papers": len({fold(r["paper"]["title"]) for r in rows}), "ardeb": ardeb,
            "updated": time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))}


async def firm_teydeb(fid: str, refresh: bool = False) -> dict | None:
    """Firmanın TEYDEB projeleri ayrı yüklenir: PRODİS sayfa başına ~15 sn sürüyor, firma sayfasını bekletmesin."""
    g = _groups().get(fid)
    if not g:
        return None
    cached = None if refresh else _cached(fid, "teydeb")
    if cached:
        return {"projects": cached["projects"], "error": ""}
    projects, error = await _teydeb(g)
    if not error:
        FIRMS_DIR.mkdir(parents=True, exist_ok=True)
        _path(fid, "teydeb").write_text(json.dumps({"v": CACHE_V, "ts": time.time(), "projects": projects}, ensure_ascii=False))
    return {"projects": projects, "error": error}


async def firm_patents(fid: str, refresh: bool = False) -> dict | None:
    """Firmanın patentleri (EPO); buluş sahipleri arasında firma sayfasındaki akademisyenler işaretlenir."""
    g = _groups().get(fid)
    if not g:
        return None
    if not patents.enabled():
        return {"enabled": False, "items": [], "total": 0, "error": ""}
    cached = None if refresh else _cached(fid, "patents")
    if cached and cached.get("pv") == patents.VERSION:
        return {"enabled": True, "items": cached["items"], "total": cached["total"], "error": ""}
    detail = _cached(fid) or {}
    academics = sorted({r["name"] for r in detail.get("rows", [])} | {p["name"] for p in _profile_links().get(g["name"], [])})
    try:
        d = await patents.firm_patents(_names(g), academics)
    except patents.PatentError as exc:
        return {"enabled": True, "items": [], "total": 0, "error": str(exc)}
    except httpx.HTTPError as exc:
        return {"enabled": True, "items": [], "total": 0, "error": f"EPO'ya ulaşılamadı ({type(exc).__name__})"}
    FIRMS_DIR.mkdir(parents=True, exist_ok=True)
    _path(fid, "patents").write_text(json.dumps({"v": CACHE_V, "pv": patents.VERSION, "ts": time.time(), **d}, ensure_ascii=False))
    return {"enabled": True, **d, "error": ""}


# ------------------------------------------------------------------ TÜBİTAK proje araması (Firmalar → TÜBİTAK)
def _firm_ref(g: dict | None) -> dict | None:
    return {"id": _fid(g["key"]), "name": g["name"]} if g else None


async def tubitak_ardeb(q: str) -> dict:
    """Konu/anahtar kelimeyle ARDEB projeleri: ekip (akademisyenler) ve özette iş birliğiyle geçen resmi Ar-Ge firmaları."""
    async with trsources._client() as client:
        hits = await trsources.trdizin_search(client, q, 60, doc_type="PROJECT")
    out = []
    for s in hits:
        abstracts = s.get("abstracts") or []
        text = " ".join(f"{x.get('title') or ''}. {x.get('abstract') or ''}" for x in abstracts)
        out.append({
            "title": clean(next((x.get("title") for x in abstracts if x.get("title")), "")),
            "year": s.get("publicationYear"), "group": s.get("projectGroup") or "", "number": s.get("projectnumber") or "",
            "url": f"{trsources.TRDIZIN_PAGE}{s.get('id')}",
            "team": [{"name": clean(a.get("name") or ""), "role": trsources.PROJECT_ROLES[a.get("duty")]}
                     for a in sorted(s.get("authors") or [], key=lambda a: a.get("order") or 0)
                     if a.get("duty") in trsources.PROJECT_ROLES and a.get("name")],
            "firms": [_firm_ref(g) | {"quote": sent} for g, sent in industry.mentions(text)]})
    out.sort(key=lambda x: (not x["firms"], -(x["year"] or 0)))
    return {"projects": out}


async def tubitak_teydeb(q: str) -> dict:
    """Konu/anahtar kelimeyle TEYDEB (sanayi) projeleri; yürüten kuruluş resmi listede ise firma sayfasına bağlanır."""
    try:
        by_kw, by_title = await asyncio.gather(trsources.teydeb_projects(pages=2, anahtarKelimeler=q),
                                               trsources.teydeb_projects(pages=2, projeAdi=q))
    except httpx.HTTPError as exc:
        return {"projects": [], "error": f"TÜBİTAK TEYDEB: {type(exc).__name__}"}
    seen, out = set(), []
    for r in by_kw + by_title:
        key = (r.get("title"), r.get("firm"))
        if key in seen:
            continue
        seen.add(key)
        out.append(r | {"official": _firm_ref(industry.match(r.get("firm") or ""))})
    return {"projects": sorted(out, key=lambda r: -(r["year"] or 0)), "error": ""}
