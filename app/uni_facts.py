"""Üniversite künyesi: kimlik (Vikipedi/Wikidata), ölçek (YÖK Akademik, Vikipedi), araştırma (OpenAlex).

Her alan kaynağıyla döner; bulunamayan alan boş kalır, tahmin edilmez. Sonuç 14 gün saklanır.
İdari görevler (dekan, bölüm başkanı) YÖK Akademik profilindeki "İdari Görevler" sayfasından,
yalnız seçilen fakültenin önbellekteki kadrosu için ve kişi başı 30 gün önbellekle okunur.
"""
from __future__ import annotations

import asyncio
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


def _infobox(text: str) -> dict:
    m = re.search(r"\{\{\s*(?:Üniversite bilgi kutusu|Bilgi kutusu üniversite|Infobox university)", text, re.I)
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
async def _yok_staff(uni: dict) -> dict:
    """Üniversitenin YÖK Akademik araması: toplam ve unvan başına kişi sayısı.

    YÖK büyük üniversitelerde her sayfayı yavaş döndürür; unvan filtresi oturuma bağlı olduğundan
    üç ayrı oturum paralel çalışır (her biri: üniversite sayfası → kendi unvan filtreleri).
    """
    def total(page: str) -> int | None:
        m = re.search(r"Arama sonucu:\s*([\d.]+)\s*sonuç", page)
        return int(m.group(1).replace(".", "")) if m else None

    def action(page: str) -> str:
        m = re.search(r'id="filterForm"[^>]*action="([^"]+)"', page)
        return html.unescape(m.group(1)) if m else ""

    counts: dict[int, int] = {}
    grand: list[int] = []

    async def session(indexes: list[int]):
        async with yokdir._client() as client:
            client.timeout = httpx.Timeout(60)
            r = await client.get(uni["url"])
            r.raise_for_status()
            if (n := total(r.text)) is not None:
                grand.append(n)
            act = action(r.text)
            for i in indexes:
                if not act:
                    return
                r = await client.post(yokdir.BASE + act, data={f"sec{i}": TITLES[i][0], "unvanSay": str(len(TITLES)), "kaydet": ""})
                if (n := total(r.text)) is not None:
                    counts[i] = n
                act = action(r.text)

    await asyncio.gather(session([0, 1]), session([2, 3]), session([4]))
    if not grand:
        raise ValueError("YÖK arama sonucu okunamadı")
    return {"total": grand[0], "titles": [{"title": TITLES[i][1], "count": counts[i]} for i in sorted(counts)]}


_STAFF_TASKS: dict[str, asyncio.Task] = {}


async def staff_counts(uid: str) -> dict | None:
    """Kadro sayıları (30 gün önbellek); aynı üniversite için tek tarama çalışır."""
    cached = yokdir._load(f"staff-{uid}", ROLE_TTL)
    if cached:
        return cached
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
            await asyncio.gather(research(), units())
        out["checked_at"] = time.time()
        if not out["errors"]:
            yokdir._save(key, out)
    out["firms"] = _firms(out["research"].get("name", ""))
    return _with_staff(out)


def _with_staff(out: dict) -> dict:
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


async def _person_roles(client, person: dict, university: str) -> list[dict]:
    """YÖK "İdari Görevler" sayfası oturumdaki son açılan profile göre çalışır: önce profil, sonra görevler."""
    yok_id = person["yok_id"]
    key = f"role-{yok_id}"
    cached = yokdir._load(key, ROLE_TTL)
    if cached is not None:
        return cached
    (await client.get(person["url"])).raise_for_status()
    r = await client.get(f"{yokdir.BASE}/AkademikArama/AkademisyenIdariGorevBilgileri", params={"authorId": yok_id})
    r.raise_for_status()
    sel, uni = Selector(r.text), fold(university)
    roles, period = [], ""
    for li in sel.css("ul.timeline li"):
        cls = li.attrib.get("class") or ""
        if "time-label" in cls:
            period = clean(li.get_all_text(separator=" "))
            continue
        if not li.css(".timeline-item"):
            continue
        role = clean(" ".join(x.get_all_text(separator=" ") for x in li.css(".timeline-footer")))
        place = clean(" ".join(x.get_all_text(separator=" ") for x in li.css(".timeline-item h4")))
        unit = clean(" ".join(x.get_all_text(separator=" ") for x in li.css(".timeline-body h5")))
        # Bitiş yılı yazılmayan görev sürüyor sayılır ("2022" sürüyor, "2015-2018" bitti)
        if re.fullmatch(r"\d{4}", period) and role and fold(place) == uni:
            roles.append({"role": role, "unit": unit, "since": period})
    yokdir._save(key, roles)
    return roles


async def faculty_roles(uid: str, faculty_raw: str) -> dict | None:
    """Fakültenin önbellekteki kadrosu için süren idari görevler. Kadro önbellekte yoksa YÖK taranmaz."""
    uni = await yokdir._university(uid)
    if not uni:
        return None
    want = yokdir._unit_tokens(faculty_raw)
    people = None
    for label in (uni["raw"], uni["name"]):
        people = yokdir._load("people-" + hashlib.sha1(f"{label}|{' '.join(sorted(want))}".encode()).hexdigest()[:12])
        if people:
            break
    if not people:
        return {"roles": {}, "dean": None, "heads": {}, "checked": 0, "cached": False}
    rank = {"Prof. Dr.": 0, "Doç. Dr.": 1, "Dr. Öğr. Üyesi": 2}
    pool = sorted((p for p in people if p.get("yok_id") and p.get("url") and p.get("title") in rank),
                  key=lambda p: rank[p["title"]])[:80]
    roles: dict[str, list[dict]] = {}
    queue = list(pool)

    async def worker():  # her işçinin kendi YÖK oturumu: profil → görev sırası karışmaz
        async with yokdir._client() as client:
            while queue:
                p = queue.pop(0)
                try:
                    found = await _person_roles(client, p, uni["raw"])
                except (httpx.HTTPError, ValueError):
                    continue
                found = [x for x in found if ROLE_RE.search(fold(x["role"]))]
                if found:
                    roles[p["yok_id"]] = found
    await asyncio.gather(*(worker() for _ in range(4)))
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
