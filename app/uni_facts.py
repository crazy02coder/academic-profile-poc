"""Üniversite künyesi: kimlik (Vikipedi/Wikidata), ölçek (YÖK Akademik, Vikipedi), araştırma (OpenAlex).

Her alan kaynağıyla döner; bulunamayan alan boş kalır, tahmin edilmez. Sonuç 14 gün saklanır.
İdari görevler (dekan, bölüm başkanı) YÖK Akademik profilindeki "İdari Görevler" sayfasından,
yalnız seçilen fakültenin önbellekteki kadrosu için ve kişi başı 30 gün önbellekle okunur.
"""
from __future__ import annotations

import asyncio
from collections import Counter
import hashlib
import html
import re
import time

import httpx
from scrapling import Selector

from . import yokdir
from .config import OPENALEX_PARAMS
from .text import clean, fold

TTL = 14 * 24 * 3600
ROLE_TTL = 30 * 24 * 3600
VERSION = 3
WIKI_UA = "AkademikIz/2.0 (https://github.com/akademik-iz; academic research PoC) httpx"
OPENALEX = "https://api.openalex.org"
TITLES = [("1", "Prof. Dr."), ("2", "Doç. Dr."), ("11", "Dr. Öğr. Üyesi"), ("4", "Öğr. Gör."), ("7", "Arş. Gör.")]
_LOCKS: dict[str, asyncio.Lock] = {}


# ------------------------------------------------------------------ Vikipedi bilgi kutusu
def _wikitext_value(raw: str) -> str:
    """Bilgi kutusu değerini düz metne çevirir: kaynaklar, şablonlar ve bağlantılar ayıklanır."""
    v = re.sub(r"<ref[^>]*/>", "", raw)
    v = re.sub(r"<ref[^>]*>.*?</ref>", "", v, flags=re.S)
    v = re.sub(r"<!--.*?-->", "", v, flags=re.S)
    v = re.sub(r"<br\s*/?>", ", ", v, flags=re.I)
    for _ in range(3):  # iç içe şablonlar: {{küçük|(2023-24)}} → (2023-24); diğerleri atılır
        v = re.sub(r"\{\{\s*(?:küçük|small|nowrap|lang\|[a-z]+)\s*\|([^{}]*)\}\}", r"\1", v, flags=re.I)
        v = re.sub(r"\{\{[^{}]*\}\}", "", v)
    v = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", v)
    v = re.sub(r"\[https?://\S+\s+([^\]]+)\]", r"\1", v)
    v = re.sub(r"<[^>]+>", "", v)
    v = html.unescape(v).replace("'''", "").replace("''", "")
    return clean(v.strip(" ,;"))


UNI_BOX = r"\{\{\s*(?:Üniversite bilgi kutusu|Bilgi kutusu üniversite|Infobox university)"


def _infobox(text: str, pattern: str = UNI_BOX) -> dict:
    m = re.search(pattern, text, re.I)
    if not m:
        return {}
    depth, i = 0, m.start()
    while i < len(text):  # şablonun kapanışını parantez derinliğiyle bul
        if text.startswith("{{", i):
            depth, i = depth + 1, i + 2
        elif text.startswith("}}", i):
            depth, i = depth - 1, i + 2
            if depth == 0:
                break
        else:
            i += 1
    body, fields, key = text[m.end():i - 2], {}, None
    for line in re.split(r"\n(?=\s*\|)", body):
        kv = re.match(r"\s*\|\s*([^=|]+?)\s*=(.*)", line, re.S)
        if kv:
            key = fold(kv.group(1)).replace("_", " ")
            fields[key] = _wikitext_value(kv.group(2))
    return {k: v for k, v in fields.items() if v}


def _pick(box: dict, *keys: str) -> str:
    return next((box[k] for k in keys if box.get(k)), "")


def _count(value: str) -> dict | None:
    """'10.660 (2023-24)' → {"value": 10660, "year": "2023-24"}."""
    m = re.search(r"(\d{1,3}(?:[.,]\d{3})+|\d+)", value or "")
    if not m:
        return None
    n = int(re.sub(r"[.,]", "", m.group(1)))
    if n < 10:
        return None
    year = re.search(r"\((?:[^()]*?)(\d{4}(?:\s*[-–/]\s*\d{2,4})?)\)", value)
    return {"value": n, "year": year.group(1).replace(" ", "") if year else ""}


async def _wikipedia(client, title: str) -> tuple[dict, str, str]:
    """(bilgi kutusu, sayfa başlığı, wikidata QID)."""
    params = {"action": "query", "prop": "revisions|pageprops", "rvprop": "content", "rvslots": "main",
              "format": "json", "redirects": 1, "titles": title}
    r = await client.get("https://tr.wikipedia.org/w/api.php", params=params)
    page = next(iter(r.json().get("query", {}).get("pages", {}).values()), {})
    if "missing" in page or not page.get("revisions"):
        s = await client.get("https://tr.wikipedia.org/w/api.php", params={
            "action": "query", "list": "search", "srsearch": f'"{title}"', "srlimit": 1, "format": "json"})
        hits = s.json().get("query", {}).get("search", [])
        if not hits or fold(title.split()[0]) not in fold(hits[0]["title"]):
            return {}, "", ""
        r = await client.get("https://tr.wikipedia.org/w/api.php", params={**params, "titles": hits[0]["title"]})
        page = next(iter(r.json().get("query", {}).get("pages", {}).values()), {})
    text = (page.get("revisions") or [{}])[0].get("slots", {}).get("main", {}).get("*", "")
    return _infobox(text), page.get("title", ""), page.get("pageprops", {}).get("wikibase_item", "")


def _claims(entity: dict, prop: str) -> list[dict]:
    return [c for c in entity.get("claims", {}).get(prop, []) if c.get("mainsnak", {}).get("datavalue")]


async def _wikidata(client, qid: str) -> dict:
    if not qid:
        return {}
    r = await client.get("https://www.wikidata.org/w/api.php", params={
        "action": "wbgetentities", "ids": qid, "props": "claims", "format": "json"})
    e = r.json().get("entities", {}).get(qid, {})
    out = {}
    if c := _claims(e, "P571"):
        out["founded"] = c[0]["mainsnak"]["datavalue"]["value"]["time"][1:5]
    types = {c["mainsnak"]["datavalue"]["value"]["id"] for c in _claims(e, "P31")}
    if types & {"Q902104", "Q23002054"}:
        out["type"] = "Vakıf üniversitesi"
    elif types & {"Q875538", "Q62078547"}:
        out["type"] = "Devlet üniversitesi"
    if c := _claims(e, "P6782"):
        out["ror"] = c[0]["mainsnak"]["datavalue"]["value"]
    if c := _claims(e, "P625"):
        v = c[0]["mainsnak"]["datavalue"]["value"]
        out["coords"] = [round(v["latitude"], 6), round(v["longitude"], 6)]
    if c := _claims(e, "P856"):
        out["website"] = c[0]["mainsnak"]["datavalue"]["value"]
    students = []
    for c in _claims(e, "P2196"):
        when = (c.get("qualifiers", {}).get("P585") or [{}])[0].get("datavalue", {}).get("value", {}).get("time", "")
        students.append((when, int(float(c["mainsnak"]["datavalue"]["value"]["amount"]))))
    if students:
        when, n = max(students)
        out["students"] = {"value": n, "year": when[1:5]}
    # Rektör: bitiş tarihi (P582) olmayan en güncel kayıt
    heads = [c for c in _claims(e, "P1037") if not c.get("qualifiers", {}).get("P582")]
    labels = {c["mainsnak"]["datavalue"]["value"]["id"] for c in heads[:1]}
    labels |= {c["mainsnak"]["datavalue"]["value"]["id"] for c in _claims(e, "P131")[:1]}
    if labels:
        lr = await client.get("https://www.wikidata.org/w/api.php", params={
            "action": "wbgetentities", "ids": "|".join(labels), "props": "labels", "languages": "tr|en", "format": "json"})
        names = {k: (v.get("labels", {}).get("tr") or v.get("labels", {}).get("en") or {}).get("value", "")
                 for k, v in lr.json().get("entities", {}).items()}
        if heads:
            out["rector"] = names.get(heads[0]["mainsnak"]["datavalue"]["value"]["id"], "")
        if c := _claims(e, "P131"):
            out["city"] = names.get(c[0]["mainsnak"]["datavalue"]["value"]["id"], "")
    return {k: v for k, v in out.items() if v}


# ------------------------------------------------------------------ YÖK Akademik kadro sayıları
async def _yok_staff_titles(uni: dict) -> dict:
    """Unvan dağılımı, yalnız kullanıcı "Yenile"ye basınca: bir liste sayfasından unvan kimlikleri öğrenilir, sonra
    unvan başına tek küçük sayım isteği atılır (en çok 7 istek; yok.gov.tr hız sınırından geçer). Üniversite sayfası
    açılırken ÇALIŞMAZ — eskiden açılışta unvan başına istek IP engeline yol açmıştı."""
    order = {label: i for i, (_, label) in enumerate(TITLES)}
    scope = {"birimId": uni["birim_id"], "birimId_matchMode": "equals", **yokdir.ACTIVE}
    async with yokdir._client() as client:
        first = await yokdir.api(client, "/akademisyen/list", page=1, length=400, **scope) or {}
        grand = first.get("totalElements")
        if grand is None:
            raise ValueError("YÖK arama sonucu okunamadı")
        ids: dict[str, str] = {}
        area_ids: dict[str, str] = {}
        seen_areas: Counter = Counter()
        for row in first.get("data") or []:
            raw, tid = clean(row.get("kadroUnvanAdi") or ""), row.get("kadroUnvanId")
            if raw and tid and raw not in ids:
                ids[raw] = tid
            area, aid = clean(row.get("temelAlanAd") or ""), row.get("temelAlanId")
            if area and aid:
                area_ids.setdefault(area, aid)
                seen_areas[area] += 1
        rows = []
        for raw, tid in list(ids.items())[:6]:
            d = await yokdir.api(client, "/akademisyen/list", page=1, length=1, kadroUnvanId=tid, kadroUnvanId_matchMode="equals", **scope) or {}
            n = d.get("totalElements")
            # Süzgeç yok sayılırsa toplam döner: o satır kullanılmaz.
            if isinstance(n, int) and 0 < n < grand:
                rows.append({"title": yokdir.YOK_TITLES.get(raw, yokdir.tr_title(raw)), "count": n})
        # Temel alanlara göre dağılım: ilk sayfada görülen alanlar (en sık 12) için alan başına tek sayım isteği.
        areas = []
        for area, _ in seen_areas.most_common(12):
            d = await yokdir.api(client, "/akademisyen/list", page=1, length=1, temelAlanId=area_ids[area], temelAlanId_matchMode="equals", **scope) or {}
            n = d.get("totalElements")
            if isinstance(n, int) and 0 < n < grand:
                areas.append({"name": re.sub(r"\s*Temel Alanı$", "", area), "count": n})
    rest = grand - sum(r["count"] for r in rows)
    if rows and rest > 0:
        rows.append({"title": "Diğer", "count": rest})
    return {"total": grand, "titles": sorted(rows, key=lambda r: order.get(r["title"], 9)),
            "areas": sorted(areas, key=lambda r: -r["count"])}


async def _yok_staff(uni: dict) -> dict:
    """Üniversitenin aktif akademisyen sayısı ve unvan dağılımı (YÖK API; unvan başına tek küçük istek)."""
    order = {label: i for i, (_, label) in enumerate(TITLES)}
    people = yokdir._stale("unistaff-" + yokdir.uni_id(uni["name"]))
    if people:  # eski toplu kayıt varsa sayılar ondan (ağsız)
        counts = Counter(p.get("title") or "" for p in people)
        rows = [{"title": t, "count": n} for t, n in counts.items() if t]
        return {"total": len(people), "titles": sorted(rows, key=lambda r: order.get(r["title"], 9))}
    # Yalnız toplam: tek küçük istek (eskiden unvan başına bir istek, üniversite açılışında ~12 istek → IP engeli).
    async with yokdir._client() as client:
        d = await yokdir.api(client, "/akademisyen/list", page=1, length=1, birimId=uni["birim_id"],
                             birimId_matchMode="equals", **yokdir.ACTIVE)
    grand = (d or {}).get("totalElements")
    if grand is None:
        raise ValueError("YÖK arama sonucu okunamadı")
    return {"total": grand, "titles": []}


_STAFF_TASKS: dict[str, asyncio.Task] = {}


async def staff_counts(uid: str, titles: bool = False) -> dict | None:
    """Kadro sayıları (30 gün önbellek); aynı üniversite için tek tarama çalışır. titles=True (kullanıcı "Yenile"ye
    bastı): unvan dağılımı kayıtta yoksa YÖK'ten sayılır."""
    cached = yokdir._load(f"staff-{uid}", ROLE_TTL)
    if cached and ((cached.get("titles") and "areas" in cached) or not titles):
        return cached
    if titles:
        uni = await yokdir._university(uid)
        if not uni:
            return None
        async with _LOCKS.setdefault(f"staff-{uid}", asyncio.Lock()):
            again = yokdir._load(f"staff-{uid}", ROLE_TTL)
            if again and again.get("titles") and "areas" in again:
                return again
            data = await _yok_staff_titles(uni)
            yokdir._save(f"staff-{uid}", data)
            return data
    task = _STAFF_TASKS.get(uid)
    if task is None:
        async def run():
            uni = await yokdir._university(uid)
            if not uni:
                return None
            data = await _yok_staff(uni)
            yokdir._save(f"staff-{uid}", data)
            return data
        task = _STAFF_TASKS[uid] = asyncio.create_task(run())
        task.add_done_callback(lambda t: _STAFF_TASKS.pop(uid, None) if _STAFF_TASKS.get(uid) is t else None)
    return await asyncio.shield(task)


# ------------------------------------------------------------------ OpenAlex kurum verisi
async def _openalex(client, ror: str, name: str) -> dict:
    inst = None
    if ror:
        r = await client.get(f"{OPENALEX}/institutions/ror:{ror.rsplit('/', 1)[-1]}", params=OPENALEX_PARAMS)
        inst = r.json() if r.status_code == 200 else None
    if not inst:
        r = await client.get(f"{OPENALEX}/institutions", params={**OPENALEX_PARAMS, "search": name,
                                                                 "filter": "country_code:TR", "per_page": 1})
        inst = (r.json().get("results") or [None])[0] if r.status_code == 200 else None
    if not inst:
        return {}
    iid = inst["id"].rsplit("/", 1)[-1]
    years = sorted(inst.get("counts_by_year") or [], key=lambda x: x["year"])[-10:]
    out = {"id": iid, "name": inst.get("display_name", ""), "ror": inst.get("ror", ""),
           "works": inst.get("works_count"), "citations": inst.get("cited_by_count"),
           "h_index": (inst.get("summary_stats") or {}).get("h_index"),
           "i10_index": (inst.get("summary_stats") or {}).get("i10_index"),
           "trend": [{"year": y["year"], "works": y["works_count"]} for y in years],
           "topics": [t["display_name"] for t in (inst.get("topics") or [])[:3]], "partners": []}
    try:
        r = await client.get(f"{OPENALEX}/works", params={**OPENALEX_PARAMS, "group_by": "authorships.institutions.lineage",
                                                          "filter": f"authorships.institutions.lineage:{iid}"})
        out["partners"] = [{"name": g["key_display_name"], "count": g["count"]}
                           for g in r.json().get("group_by", []) if not g["key"].endswith(iid)][:5]
    except (httpx.HTTPError, ValueError):
        pass
    return out


def _firms(openalex_name: str) -> list[dict]:
    """Ortak yayın taramasında bu kurumdan akademisyen çıkan firmalar (yerel firma önbelleği)."""
    if not openalex_name:
        return []
    from . import firms
    out = []
    for fid, g in firms._groups().items():
        d = firms._cached(fid)
        rows = (d or {}).get("rows") or []
        people = {r.get("name") for r in rows if fold(r.get("institution") or "") == fold(openalex_name)}
        if people:
            out.append({"id": fid, "name": g["name"], "people": len(people)})
    return sorted(out, key=lambda x: -x["people"])[:8]


# ------------------------------------------------------------------ künye
async def facts(uid: str, refresh: bool = False) -> dict | None:
    key = f"facts-{uid}"
    cached = None if refresh else yokdir._load(key, TTL)
    if cached and cached.get("v") == VERSION:
        cached["firms"] = _firms((cached.get("research") or {}).get("name", ""))
        return _with_staff(cached)
    lock = _LOCKS.setdefault(uid, asyncio.Lock())
    async with lock:
        cached = None if refresh else yokdir._load(key, TTL)
        if cached and cached.get("v") == VERSION:
            return _with_staff(cached)
        uni = await yokdir._university(uid)
        if not uni:
            return None
        out = {"v": VERSION, "id": uid, "name": uni["name"], "identity": {}, "scale": {}, "research": {},
               "sources": {}, "errors": []}
        async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers={"User-Agent": WIKI_UA}) as client:
            box, wiki_title, qid = {}, "", ""
            try:
                box, wiki_title, qid = await _wikipedia(client, uni["name"])
            except (httpx.HTTPError, ValueError) as exc:
                out["errors"].append(f"Vikipedi: {type(exc).__name__}")
            wd = {}
            try:
                wd = await _wikidata(client, qid)
            except (httpx.HTTPError, ValueError, KeyError) as exc:
                out["errors"].append(f"Wikidata: {type(exc).__name__}")
            year = re.search(r"\b(1[89]\d{2}|20\d{2})\b", _pick(box, "kurulus"))
            kind = _pick(box, "tur", "turu")
            ident = {
                "founded": year.group(1) if year else wd.get("founded", ""),
                "type": ("Vakıf üniversitesi" if "vakif" in fold(kind) else "Devlet üniversitesi" if "devlet" in fold(kind)
                         else wd.get("type", "")),
                "rector": re.sub(r"^(Prof\.?\s*Dr\.?\s*)", "Prof. Dr. ", _pick(box, "rektor")) or wd.get("rector", ""),
                "city": _pick(box, "sehir") or wd.get("city", ""),
                "address": _pick(box, "adres"),
                "campus": _pick(box, "kampus", "yerleske"),
                "motto": _pick(box, "slogan").strip('"“”'),
                "language": _pick(box, "egitim dili", "dil"),
                "affiliation": _pick(box, "baglilik"),
                "website": wd.get("website") or uni.get("home", ""),
                "wikipedia": f"https://tr.wikipedia.org/wiki/{wiki_title.replace(' ', '_')}" if wiki_title else "",
                "coords": wd.get("coords"),
            }
            out["identity"] = {k: v for k, v in ident.items() if v}
            students = _count(_pick(box, "kayitli", "ogrenciler", "ogrenci", "ogrenci sayisi")) or wd.get("students")
            out["scale"] = {k: v for k, v in {
                "students": students,
                "associate": _count(_pick(box, "onlisans", "on lisans")),
                "undergrad": _count(_pick(box, "lisans")),
                "graduate": _count(_pick(box, "lisans ustu", "lisansustu", "yuksek lisans")),
                "doctoral": _count(_pick(box, "doktora")),
                "graduates": _count(_pick(box, "mezun", "mezunlar")),
                "staff": _count(_pick(box, "akademik personel", "fakulte uyeleri", "personel")),
            }.items() if v}
            out["sources"]["identity"] = "Vikipedi · Wikidata" if box and wd else "Vikipedi" if box else "Wikidata" if wd else ""
            async def research():
                try:
                    async with httpx.AsyncClient(timeout=25) as oa:
                        out["research"] = await _openalex(oa, wd.get("ror", ""), uni["name"])
                    out["sources"]["research"] = "OpenAlex" if out["research"] else ""
                except (httpx.HTTPError, ValueError) as exc:
                    out["errors"].append(f"OpenAlex: {type(exc).__name__}")

            async def units():
                try:
                    out["units"] = await yokdir.unit_summary(uid)
                except httpx.HTTPError:
                    out["units"] = None
                if out["units"] is not None and not out["units"].get("departments"):
                    # Kadro henüz taranmadı: bölüm (lisans programı) sayısı YÖK Atlas'tan, olmazsa hazır veri setinden.
                    n, source = await _department_count(uni)
                    if n:
                        out["units"].update(departments=n, scanned=out["units"].get("faculties") or 1, departments_source=source)
            await asyncio.gather(research(), units())
        out["checked_at"] = time.time()
        if not out["errors"]:
            yokdir._save(key, out)
    out["firms"] = _firms(out["research"].get("name", ""))
    return _with_staff(out)


async def _department_count(uni: dict) -> tuple[int, str]:
    """Lisans programı sayısı: dil/öğretim türü varyantları ("(İngilizce)", "(İÖ)") tek program sayılır."""
    from . import atlas, poc_dataset
    try:
        data = await atlas.programs(uni["name"])
    except Exception:  # noqa: BLE001 — Atlas yardımcıdır
        data = None
    names = {re.sub(r"\s*\(.*?\)", "", fold(p["name"])).strip() for p in (data or {}).get("programs") or [] if p.get("level") == "Lisans"}
    if names:
        return len(names), "YÖK Atlas"
    try:
        found = poc_dataset.university(uni.get("home") or "")
    except Exception:  # noqa: BLE001
        found = None
    if found:
        n = len({poc_dataset.unit_key(d.get("name") or "")[0] for f in found.get("faculties") or [] for d in f.get("departments") or [] if d.get("name")})
        if n:
            return n, "hazır veri seti"
    return 0, ""


def _with_staff(out: dict) -> dict:
    # Öğrenci sayıları: YÖK İstatistik kaydı varsa (ağsız) künyedeki Vikipedi sayılarının yerine geçer — günceldir ve
    # düzeylere göre kırılım içerir.
    try:
        from . import yok_istatistik
        row = yok_istatistik.cached(out.get("name") or "")
        if row and row["total"]["total"]:
            scale = dict(out.get("scale") or {})
            year = row.get("year", "")
            scale["students"] = {"value": row["total"]["total"], "year": year}
            for key in ("associate", "undergrad", "graduate", "doctoral"):
                if row[key]["total"]:
                    scale[key] = {"value": row[key]["total"], "year": year}
                else:
                    scale.pop(key, None)
            out = {**out, "scale": scale, "sources": {**(out.get("sources") or {}), "students": "YÖK İstatistik"}}
    except Exception:  # noqa: BLE001 — kayıt yardımcıdır
        pass
    staff = yokdir._load(f"staff-{out['id']}", ROLE_TTL)
    out["academics"] = staff
    if staff:
        out["sources"]["academics"] = "YÖK Akademik"
    elif out["id"] not in _STAFF_TASKS:
        task = asyncio.ensure_future(staff_counts(out["id"]))
        task.add_done_callback(lambda t: t.exception())  # hata önyüzde ayrı istekle görünür
    return out


# ------------------------------------------------------------------ idari görevler (dekan / bölüm başkanı)
ROLE_RE = re.compile(r"dekan|bolum baskan|rektor|mudur|anabilim dali baskan|enstitu", re.I)


def _roles_cached(person: dict) -> bool:
    return yokdir._load(f"role2-{person['yok_id']}", ROLE_TTL) is not None


async def _person_roles(client, person: dict, university: str) -> list[dict]:
    """YÖK idari görevleri (API). Bitiş tarihi olmayan görev sürüyor sayılır; yalnız bu üniversitedeki görevler."""
    yok_id = person["yok_id"]
    key = f"role2-{yok_id}"
    cached = yokdir._load(key, ROLE_TTL)
    if cached is not None:
        return cached
    d = await yokdir.api(client, "/deneyim/idari/gorev", authorGuidId=yok_id, page=1, length=50)
    uni, roles = fold(university), []
    for x in (d or {}).get("data") or []:
        place = clean(x.get("unvBirimAdi") or x.get("yerAdi") or x.get("yurticiBirimAdi") or "")
        if x.get("bitisTarihi") or (place and fold(place) != uni):
            continue
        year = re.search(r"(19|20)\d{2}", str(x.get("baslangicTarihi") or x.get("tarih") or ""))
        unit = clean(" ".join(v for v in (x.get("fakulteBilgisi"), x.get("bolumBilgisi")) if v))
        role = clean(x.get("gorevAdi") or "")
        if role and year:
            roles.append({"role": role, "unit": unit, "since": year.group(0)})
    yokdir._save(key, roles)
    return roles


async def faculty_roles(uid: str, faculty_raw: str, fetch: bool = False) -> dict | None:
    """Fakültenin önbellekteki kadrosu için süren idari görevler. Varsayılan yalnız kayıtlı görevler (YÖK'e istek
    atılmaz); fetch=True kullanıcı açıkça isteyince en çok 20 kişi, tek tek ve sırayla sorulur."""
    uni = await yokdir._university(uid)
    if not uni:
        return None
    people = yokdir._load(yokdir.people_key(uni["raw"], faculty_raw))
    if not people:
        return {"roles": {}, "dean": None, "heads": {}, "checked": 0, "cached": False}
    rank = {"Prof. Dr.": 0, "Doç. Dr.": 1, "Dr. Öğr. Üyesi": 2}
    pool = sorted((p for p in people if p.get("yok_id") and p.get("url") and p.get("title") in rank),
                  key=lambda p: rank[p["title"]])[:20 if fetch else 80]
    roles: dict[str, list[dict]] = {}
    queue = list(pool)

    async def worker():
        async with yokdir._client() as client:
            while queue:
                p = queue.pop(0)
                if not fetch and not _roles_cached(p):
                    continue
                try:
                    found = await _person_roles(client, p, uni["raw"])
                except (httpx.HTTPError, ValueError):
                    continue
                found = [x for x in found if ROLE_RE.search(fold(x["role"]))]
                if found:
                    roles[p["yok_id"]] = found
    await asyncio.gather(*(worker() for _ in range(1 if fetch else 4)))
    by_id = {p["yok_id"]: p for p in pool}
    dean, heads = None, {}
    fac_key = fold(faculty_raw)
    for yid, items in roles.items():
        p = by_id[yid]
        for x in items:
            role, unit = fold(x["role"]), fold(x["unit"])
            if role.startswith("dekan") and "yardimci" not in role and fac_key in unit:
                if not dean or x["since"] > dean["since"]:  # YÖK eski görevi kapatmamış olabilir: en yenisi
                    dean = {"yok_id": yid, "name": p["name"], "title": p["title"], "since": x["since"]}
            elif "bolum baskan" in role and "yardimci" not in role:
                dep = re.sub(r"\s*B[ÖO]L[ÜU]M[ÜU]$", "", p.get("department") or "")
                if not dep or fold(dep) not in unit:
                    continue
                name = yokdir.display_uni(dep)
                if name not in heads or x["since"] > heads[name]["since"]:
                    heads[name] = {"yok_id": yid, "name": p["name"], "title": p["title"], "since": x["since"]}
    return {"roles": roles, "dean": dean, "heads": heads, "checked": len(pool), "cached": True}
