"""YÖK Akademik kurum dizini: üniversite → fakülte → akademisyen.

Kasım 2026'dan itibaren YÖK Akademik yeni bir uygulamadır; veriler herkese açık JSON API'den
(akademik.yok.gov.tr/api) gelir. Bir üniversitenin bütün aktif kadrosu birkaç büyük sayfayla çekilir,
fakülte/bölüm ayrımı yerelde yapılır (eski HTML dizininde onlarca sayfa ve dakikalar süren iş saniyeler sürer).
Kimlikler (birimId vb.) YÖK tarafından şifreli ve dönemsel olduğundan liste önbelleği kısa tutulur.
Kurum sitesi ayrıştırması (directory._people) fotoğraf/profil bağlantısı ve yedek için kullanılır.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from collections import Counter

import httpx

from .config import ROOT
from .discover import registrable, tr_title
from .sources import YOK_TITLES
from .text import clean, fold, name_score, name_tokens

BASE = "https://akademik.yok.gov.tr"
API = f"{BASE}/api"
DIR = ROOT / "data" / "yok"
TTL = 7 * 24 * 3600
LIST_TTL = 24 * 3600  # üniversite listesi: şifreli kimlikler dönemsel
PAGE = 500
MAX_PEOPLE = 12000
FREE_MAIL = {"gmail.com", "hotmail.com", "yahoo.com", "outlook.com", "yandex.com", "icloud.com", "live.com", "msn.com",
             "windowslive.com", "mynet.com", "hotmail.com.tr", "yahoo.com.tr"}
TITLE_RANK = {"Prof. Dr.": 0, "Doç. Dr.": 1, "Dr. Öğr. Üyesi": 2, "Öğr. Gör.": 3, "Arş. Gör.": 4}
# tr_title kısaltmaları bozmasın: "Ted Üniversitesi" değil "TED Üniversitesi"
ACRONYMS = ("TED", "TOBB", "MEF", "OSTİM", "KTO", "SANKO", "TOGÜ", "ODTÜ", "İSTE", "ERÜ")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
WIKI_UA = "AkademikIz/2.0 (https://github.com/akademik-iz; academic research PoC) httpx"
# Birim adlarında eşleştirmeyi bozan ekler: "Yazılım Mühendisliği Bölümü", "… Lisans", "… (İngilizce)"
UNIT_NOISE = {"bolumu", "bolum", "lisans", "programi", "program", "pr", "turkce", "ingilizce", "department", "of",
              "anabilim", "dali", "fakultesi", "faculty", "the"}
ACTIVE = {"aktifAkademisyen": "true", "aktifAkademisyen_matchMode": "equals"}
_GATE = asyncio.Semaphore(3)  # YÖK'ü yormamak için aynı anda en fazla üç istek


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", fold(text).replace("ı", "i")).strip()


def _unit_tokens(text: str) -> set[str]:
    return {t for t in _key(text).split() if t not in UNIT_NOISE and len(t) > 1}


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=45, follow_redirects=True, headers={
        "User-Agent": UA, "Accept-Language": "tr", "Accept": "application/json", "Referer": f"{BASE}/"})


def _cache(name: str):
    return DIR / f"{name}.json"


def _load(name: str, ttl: int = TTL):
    p = _cache(name)
    if p.exists():
        d = json.loads(p.read_text())
        if time.time() - d.get("ts", 0) < ttl:
            return d["data"]
    return None


def _save(name: str, data):
    DIR.mkdir(parents=True, exist_ok=True)
    _cache(name).write_text(json.dumps({"ts": time.time(), "data": data}, ensure_ascii=False))


def people_key(university_label: str, faculty_name: str) -> str:
    """Fakülte kadrosu önbellek anahtarı (yeni API kimlikleriyle; eski HTML önbelleğiyle karışmaz)."""
    want = _unit_tokens(faculty_name)
    return "people2-" + hashlib.sha1(f"{university_label}|{' '.join(sorted(want))}".encode()).hexdigest()[:12]


async def api(client, path: str, **params):
    """YÖK API çağrısı: `data` alanını döndürür. Zaman aşımında bir kez daha dener."""
    for attempt in range(2):
        try:
            async with _GATE:
                r = await client.get(API + path, params=params)
            break
        except httpx.TimeoutException:
            if attempt:
                raise
            await asyncio.sleep(1.5)
    r.raise_for_status()
    body = r.json()
    if not body.get("result", True):
        raise httpx.HTTPStatusError(body.get("errorMessage") or "YÖK API hatası", request=r.request, response=r)
    return body.get("data")


# ------------------------------------------------------------------ üniversite ve fakülteler
async def universities(client, refresh: bool = False) -> list[dict]:
    cached = None if refresh else _load("universities2", LIST_TTL)
    if cached:
        return cached
    d = await api(client, "/university/list", page=1, length=1000)
    out = [{"name": clean(u["birimAdi"]), "url": f"{BASE}/universities", "birim_id": u["birimId"],
            "name_en": u.get("birimAdiEn") or "", "city": u.get("ilAdi") or "", "type": u.get("tur") or "",
            "year": u.get("yil"), "rector": u.get("adSoyad") or "", "rector_guid": u.get("authorGuidId") or ""}
           for u in (d or {}).get("data", []) if u.get("birimAdi")]
    if out:
        _save("universities2", out)
    return out


def match_university(unis: list[dict], names: list[str]) -> dict | None:
    """Kurum adlarından (site adı, OpenAlex adı ve alternatifleri) YÖK üniversitesini seçer."""
    keys = {_key(n) for n in names if n}
    exact = next((u for u in unis if _key(u["name"]) in keys), None)
    if exact:
        return exact
    best, score = None, 0.0
    for u in unis:
        a = _unit_tokens(u["name"]) - {"universitesi", "university"}
        for n in names:
            b = _unit_tokens(n or "") - {"universitesi", "university"}
            j = len(a & b) / len(a | b) if a and b else 0
            if j > score:
                best, score = u, j
    return best if score >= 0.75 else None


def _person(row: dict) -> dict:
    guid = row.get("authorGuidId") or ""
    title_raw = clean(row.get("kadroUnvanAdi") or "")
    keywords = [clean(row.get(f"anahtarkelime{i}Ad") or "") for i in (1, 2, 3)]
    return {
        "name": tr_title(clean(row.get("personelAdiSoyadi") or "")),
        "title": YOK_TITLES.get(title_raw, tr_title(title_raw)), "university": clean(row.get("universiteAd") or ""),
        "faculty": clean(row.get("fakulteAd") or ""), "department": clean(row.get("bolumAd") or ""),
        "orcid": row.get("orcid") or "", "email": "", "url": f"{BASE}/academician-details?authorGuidId={guid}" if guid else "",
        "yok_id": guid, "photo": "", "source": "yok", "field": clean(row.get("bilimAlanAd") or ""),
        "area": clean(row.get("temelAlanAd") or ""), "keywords": [k for k in keywords if k],
        "scopus_id": row.get("scopusId") or "", "researcher_id": row.get("researcherId") or ""}


async def uni_people(client, uni: dict) -> list[dict]:
    """Üniversitenin bütün aktif akademisyenleri (7 gün önbellek); 500'lük sayfalarla."""
    key = "unistaff-" + uni_id(uni["name"])
    cached = _load(key)
    if cached is not None:
        return cached
    rows, page = [], 1
    while len(rows) < MAX_PEOPLE:
        d = await api(client, "/akademisyen/list", page=page, length=PAGE, birimId=uni["birim_id"], birimId_matchMode="equals", **ACTIVE)
        batch = (d or {}).get("data") or []
        rows += batch
        if not batch or page >= ((d or {}).get("totalPages") or 1):
            break
        page += 1
    uniq: dict[str, dict] = {}
    for r in rows:
        p = _person(r)
        uniq.setdefault(p["yok_id"] or p["name"], p)
    people = list(uniq.values())
    if people:
        _save(key, people)
    return people


async def faculty_staff(uni_names: list[str], faculty_name: str) -> dict | None:
    """Fakültenin YÖK kadrosu: {"university", "faculty", "people"} ya da None (YÖK'e ulaşılamadı / eşleşme yok)."""
    want = _unit_tokens(faculty_name)
    if not want:
        return None
    async with _client() as client:
        try:
            uni = match_university(await universities(client), uni_names)
            if not uni:
                return None
            pkey = people_key(uni["name"], faculty_name)
            people = _load(pkey)
            if people is None:
                everyone = await uni_people(client, uni)
                groups: dict[str, list] = {}
                for p in everyone:
                    groups.setdefault(p["faculty"], []).append(p)
                fac = max(groups, key=lambda f: _jaccard(want, _unit_tokens(f)), default=None)
                if not fac or _jaccard(want, _unit_tokens(fac)) < 0.6:
                    return None
                people = groups[fac]
                _save(pkey, people)
        except httpx.HTTPError:
            return None
    if not people:
        return None
    return {"university": uni["name"], "faculty": people[0]["faculty"], "people": people}


def pick_department(people: list[dict], dept_name: str, site_people: list[dict] | None = None) -> list[dict]:
    """Fakülte kadrosundan bölüm: önce bölüm adı (kurum yolundaki), tutmazsa site kadrosuyla en çok örtüşen bölüm."""
    groups: dict[str, list] = {}
    for p in people:
        groups.setdefault(p["department"], []).append(p)
    want = _unit_tokens(dept_name)
    if want:
        name, score = max(((d, _jaccard(want, _unit_tokens(d))) for d in groups), key=lambda x: x[1], default=("", 0))
        if score >= 0.6:
            return groups[name]
    if site_people:
        name, group = max(groups.items(), key=lambda kv: _overlap(kv[1], site_people), default=("", []))
        if _overlap(group, site_people) >= max(2, len(site_people) // 3):
            return group
    return []


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _overlap(yok_people: list[dict], site_people: list[dict]) -> int:
    site = {tuple(sorted(name_tokens(p["name"]))) for p in site_people}
    return sum(tuple(sorted(name_tokens(p["name"]))) in site for p in yok_people)


def merge_site(yok_people: list[dict], site_people: list[dict]) -> list[dict]:
    """YÖK kadrosu esas; fotoğraf ve kurum profil bağlantısı siteden eklenir. Sitede olup YÖK bölümünde olmayanlar
    (misafir, başka birimden görevli) site ayrıştırması güvenilirse (çoğu YÖK'te bulunuyorsa) eklenir."""
    site = {tuple(sorted(name_tokens(p["name"]))): p for p in site_people}
    out = []
    for p in yok_people:
        s = site.pop(tuple(sorted(name_tokens(p["name"]))), None)
        out.append(p | ({"photo": s.get("photo", ""), "site_url": s.get("url", "")} if s else {}))
    if site_people and len(site_people) - len(site) >= len(site_people) / 2:
        out += [p | {"source": "site"} for p in site.values()]
    return out


# ------------------------------------------------------------------ kurum sitesi bağlantısı olmadan gezinme
def uni_id(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _key(name)).strip("-")


def display_uni(name: str) -> str:
    text = tr_title(name)
    for short in ACRONYMS:
        text = re.sub(rf"(?<!\w){re.escape(tr_title(short))}(?!\w)", short, text)
    text = re.sub(r"-(\w)", lambda m: "-" + m.group(1).replace("i", "İ").replace("ı", "I").upper(), text)  # "Fen-Edebiyat"
    return re.sub(r"(?<=\s)(Ve|İle|Veya)(?=\s)", lambda m: {"Ve": "ve", "İle": "ile", "Veya": "veya"}[m.group(1)], text)


async def university_list() -> list[dict]:
    """YÖK'teki tüm üniversiteler: {"id", "name" (okunur), "raw", "url", "birim_id", il, tür, yıl, rektör}."""
    async with _client() as client:
        unis = await universities(client)
    return sorted(({**u, "id": uni_id(u["name"]), "name": display_uni(u["name"]), "raw": u["name"]} for u in unis),
                  key=lambda u: fold(u["name"]))


async def _university(uid: str) -> dict | None:
    return next((u for u in await university_list() if u["id"] == uid), None)


def site_domain(people: list[dict]) -> str:
    """Kurum alan adı: akademisyenlerin kurumsal e-postalarında en sık geçen alan adı."""
    counts = Counter(registrable(p["email"].split("@")[-1].lower()) for p in people if "@" in (p.get("email") or ""))
    for domain, _ in counts.most_common():
        if domain and domain not in FREE_MAIL and re.search(r"\.edu(\.[a-z]{2})?$|\.tr$", domain):
            return domain
    return ""


async def _wikidata_site(name: str) -> str:
    """Yeni YÖK API e-posta vermez; kurum sitesi Wikidata'daki resmî web sitesinden (P856) alınır."""
    async with httpx.AsyncClient(timeout=15, headers={"User-Agent": WIKI_UA}) as w:
        s = await w.get("https://www.wikidata.org/w/api.php", params={
            "action": "wbsearchentities", "search": display_uni(name), "language": "tr", "uselang": "tr", "type": "item",
            "limit": 5, "format": "json"})
        for hit in s.json().get("search", []):
            if _jaccard(_unit_tokens(hit.get("label", "")), _unit_tokens(name)) < 0.6:
                continue
            e = await w.get("https://www.wikidata.org/w/api.php", params={
                "action": "wbgetentities", "ids": hit["id"], "props": "claims", "format": "json"})
            claims = e.json().get("entities", {}).get(hit["id"], {}).get("claims", {}).get("P856") or []
            for c in claims:
                url = (c.get("mainsnak", {}).get("datavalue") or {}).get("value") or ""
                host = registrable(re.sub(r"^https?://", "", url).split("/")[0])
                if re.search(r"\.edu(\.[a-z]{2})?$|\.tr$", host):
                    return f"https://www.{host}"
    return ""


async def _home_of(client, uni: dict) -> str:
    """Kurum sitesi (site adresini kullanıcı girmez): önbellek, yoksa Wikidata."""
    key = f"home-{uni['id']}"
    cached = _load(key, 30 * 24 * 3600)
    if cached:
        return cached
    try:
        home = await _wikidata_site(uni.get("raw") or uni["name"])
    except (httpx.HTTPError, ValueError):
        return ""
    if home:
        _save(key, home)
    return home


async def university_detail(uid: str) -> dict | None:
    """Üniversite: {"id", "name", "raw", "home", "items": fakülteler}. Sonuç 7 gün saklanır."""
    uni = await _university(uid)
    if not uni:
        return None
    async with _client() as client:
        items = _load(f"fac2-{uid}")
        if items is None:
            units = await api(client, "/genel/birim-list", listVal=2, q=uni["birim_id"]) or []
            items = [clean(u["label"]) for u in units if u.get("label")]
            if items:
                _save(f"fac2-{uid}", items)
        home = await _home_of(client, uni)
    return {"id": uid, "name": uni["name"], "raw": uni["raw"], "home": home,
            "items": [{"name": display_uni(f), "raw": f} for f in items]}


def public_person(p: dict, university: str = "") -> dict:
    """Arayüze giden satır: kurum yolu okunur yazımla, sıralama için unvan sırası değil unvanın kendisi."""
    dept = re.sub(r"\s*B[ÖO]L[ÜU]M[ÜU]$", "", p.get("department") or "")
    return p | {"university": display_uni(p.get("university") or university), "faculty": display_uni(p.get("faculty") or ""),
                "department": display_uni(dept), "department_raw": p.get("department") or ""}


def by_rank(people: list[dict]) -> list[dict]:
    return sorted(people, key=lambda p: (TITLE_RANK.get(p.get("title"), 9), fold(p.get("name"))))


async def faculty_detail(uid: str, faculty_raw: str) -> dict | None:
    """Fakülte kadrosu ve kurum yolundan çıkan bölümler; (None: üniversite/fakülte yok ya da YÖK'e ulaşılamadı)."""
    uni = await _university(uid)
    if not uni:
        return None
    fac = await faculty_staff([uni["raw"]], faculty_raw)
    if not fac:
        return None
    people = by_rank([public_person(p, uni["raw"]) for p in fac["people"]])
    counts = Counter(p["department"] for p in people)
    deps = [{"name": name or "Bölümü belirtilmemiş", "key": name, "count": n} for name, n in sorted(counts.items(), key=lambda kv: (not kv[0], fold(kv[0])))]
    domain = registrable(re.sub(r"^https?://", "", _load(f"home-{uid}", 30 * 24 * 3600) or "").split("/")[0])
    return {"university": uni["name"], "faculty": display_uni(faculty_raw), "people": people, "departments": deps,
            "domain": domain or site_domain(fac["people"])}


def _upper_tr(text: str) -> str:
    return text.replace("i", "İ").replace("ı", "I").upper()


async def search_people(q: str, limit: int = 60) -> list[dict]:
    """YÖK'te ad araması (API, tarayıcısız). Aynı adlı kişiler seçim için listelenir."""
    query = clean(q)
    key = "search2-" + hashlib.sha1(fold(query).encode()).hexdigest()[:12]
    people = _load(key, 24 * 3600)
    if people is None:
        async with _client() as client:
            d = await api(client, "/akademisyen/list", page=1, length=max(limit, 60),
                          personelAdiSoyadi=_upper_tr(query), personelAdiSoyadi_matchMode="contains")
        people = [_person(r) for r in (d or {}).get("data") or []]
        _save(key, people)
    people = sorted(people, key=lambda p: (-name_score(query, p["name"]), TITLE_RANK.get(p.get("title"), 9), fold(p["name"])))
    return [public_person(p) for p in people[:limit]]


async def person_site(university_raw: str, email: str = "") -> str:
    """Seçilen akademisyenin kurum sitesi: kendi kurumsal e-postası, yoksa üniversitenin resmî sitesi."""
    domain = site_domain([{"email": email}])
    if domain:
        return f"https://www.{domain}"
    uni = await _university(uni_id(university_raw)) if university_raw else None
    if not uni:
        return ""
    async with _client() as client:
        return await _home_of(client, uni)


async def unit_summary(uid: str) -> dict | None:
    """Üniversite özeti: fakülte ve birim sayısı; bölüm sayısı önbellekteki kadrodan (YÖK'e ek istek yok)."""
    d = await university_detail(uid)
    uni = await _university(uid)
    if not d or not uni:
        return None
    faculties = [x for x in d["items"] if "FAKÜLTE" in x["raw"].upper()]
    everyone = _load("unistaff-" + uni_id(uni["raw"])) or []
    deps = {(p["faculty"], p["department"]) for p in everyone if p.get("department") and "FAKÜLTE" in p.get("faculty", "").upper()}
    scanned = len({p["faculty"] for p in everyone if "FAKÜLTE" in p.get("faculty", "").upper()})
    return {"id": uid, "name": d["name"], "home": d["home"], "faculties": len(faculties), "units": len(d["items"]),
            "departments": len(deps), "scanned": scanned}
