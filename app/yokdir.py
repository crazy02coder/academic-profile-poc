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
from .yok_rate import URGENT, HOOKS as RATE_HOOKS, RATE_GAP, RATE_PER_MIN, throttle, throttle_sync  # noqa: F401  tüm yok.gov.tr istekleri

BASE = "https://akademik.yok.gov.tr"
API = f"{BASE}/api"
DIR = ROOT / "data" / "yok"
TTL = 7 * 24 * 3600
LIST_TTL = 24 * 3600  # üniversite listesi: şifreli kimlikler dönemsel
PAGE = 100            # sayfa başına kişi (eskiden 500: kısa sürede çok büyük yanıt → IP engeli)
MAX_PEOPLE = 12000
STAFF_TTL = 182 * 24 * 3600  # akademisyenler 6 ay saklanır (yenile ile erken tazelenir)
EMPTY_TTL = 3600  # boş dönen bölüm kadrosu bu kadar sonra yeniden sorulur
FILTER_RETRY = 3 * 3600  # "süzgeç çalışmıyor" işareti bu kadar sonra yeniden denenir
UNIT_TTL = 365 * 24 * 3600  # fakülte ve bölüm listeleri 1 yıl saklanır (yenile ile erken tazelenir)
STAFF_PAGE_GAP = 3.0  # aynı listenin sayfaları arasında bekleme (ortak hız sınırına ek)
_BULK = asyncio.Lock()  # aynı anda tek kadro çekimi
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


def _client(timeout: float = 45) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, follow_redirects=True, event_hooks=RATE_HOOKS, headers={
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


def _stale(name: str):
    """Süresi dolmuş olsa da önbellekteki kayıt (YÖK'e ulaşılamadığında sayfa boş kalmasın); yoksa None."""
    try:
        return _load(name, 10 ** 10)
    except (OSError, ValueError, KeyError):
        return None


def _save(name: str, data):
    DIR.mkdir(parents=True, exist_ok=True)
    _cache(name).write_text(json.dumps({"ts": time.time(), "data": data}, ensure_ascii=False))


def people_key(university_label: str, faculty_name: str) -> str:
    """Fakülte kadrosu önbellek anahtarı (yeni API kimlikleriyle; eski HTML önbelleğiyle karışmaz)."""
    want = _unit_tokens(faculty_name)
    return "people2-" + hashlib.sha1(f"{university_label}|{' '.join(sorted(want))}".encode()).hexdigest()[:12]


COOLDOWN = 20 * 60  # YÖK yanıt vermez / reddederse bu süre boyunca hiç istek atılmaz
_PAUSE_FILE = DIR / "_pause.json"


def paused_until() -> float:
    try:
        return float(json.loads(_PAUSE_FILE.read_text())["until"])
    except (OSError, ValueError, KeyError, TypeError):
        return 0.0


def paused() -> bool:
    return time.time() < paused_until()


def _trip(reason: str) -> None:
    try:
        DIR.mkdir(parents=True, exist_ok=True)
        _PAUSE_FILE.write_text(json.dumps({"until": time.time() + COOLDOWN, "reason": reason}))
    except OSError:
        pass


async def api(client, path: str, **params):
    """YÖK API çağrısı: `data` alanını döndürür. Zaman aşımı/engelde sigorta atar; tekrar denemez."""
    if paused():
        raise httpx.ConnectError("YÖK Akademik şu an yanıt vermiyor; bir süre sonra yeniden denenecek.")
    try:
        if URGENT.get():  # kullanıcının beklediği küçük istek: arka plan taramalarının eşzamanlılık sırasını beklemez
            r = await client.get(API + path, params=params)
        else:
            async with _GATE:
                r = await client.get(API + path, params=params)
    except (httpx.TimeoutException, httpx.ConnectError) as exc:
        _trip(type(exc).__name__)
        raise
    if r.status_code in (403, 429) or r.status_code >= 500:
        _trip(f"HTTP {r.status_code}")
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
    try:
        d = await api(client, "/university/list", page=1, length=1000)
    except httpx.HTTPError:
        stale = _load("universities2", 10 ** 10)  # YÖK yanıt vermezse eski liste: sayfa takılmasın
        if stale:
            return stale
        raise
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


def place(row: dict) -> tuple[str, str]:
    """(fakülte, bölüm). YÖK eskiden bunları fakulteAd / bolumAd alanlarında veriyordu; Kasım 2026'dan beri liste
    satırlarında yalnız kadroYeri var: "ÜNİVERSİTE/FAKÜLTE/BÖLÜM/ANABİLİM DALI/". Eski alanlar varsa onlar kullanılır."""
    faculty, department = clean(row.get("fakulteAd") or ""), clean(row.get("bolumAd") or "")
    if faculty and department:
        return faculty, department
    # Ayarlar → Veri tarifleri'nde öğrenilmiş eşleme varsa (yanıt biçimi yine değiştiyse) o kullanılır.
    from . import contracts
    faculty = faculty or contracts.mapped("yok.staff", "faculty", row)
    department = department or contracts.mapped("yok.staff", "department", row)
    if faculty and department:
        return faculty, department
    parts = [clean(x) for x in str(row.get("kadroYeri") or "").split("/") if clean(x)]
    # İlk parça üniversitedir; rektörlüğe bağlı birimlerde fakülte parçası olmayabilir.
    if parts and "ÜNİVERSİTE" in parts[0].upper().replace("I", "İ") or parts and fold(parts[0]) == fold(row.get("universiteAd") or ""):
        parts = parts[1:]
    return faculty or (parts[0] if parts else ""), department or (parts[1] if len(parts) > 1 else "")


def _person(row: dict) -> dict:
    guid = row.get("authorGuidId") or ""
    title_raw = clean(row.get("kadroUnvanAdi") or "")
    keywords = [clean(row.get(f"anahtarkelime{i}Ad") or "") for i in (1, 2, 3)]
    return {
        "name": tr_title(clean(row.get("personelAdiSoyadi") or "")),
        "title": YOK_TITLES.get(title_raw, tr_title(title_raw)), "university": clean(row.get("universiteAd") or ""),
        "faculty": place(row)[0], "department": place(row)[1],
        "orcid": row.get("orcid") or "", "email": "", "url": f"{BASE}/academician-details?authorGuidId={guid}" if guid else "",
        "yok_id": guid, "photo": "", "source": "yok", "field": clean(row.get("bilimAlanAd") or ""),
        "area": clean(row.get("temelAlanAd") or ""), "keywords": [k for k in keywords if k],
        "scopus_id": row.get("scopusId") or "", "researcher_id": row.get("researcherId") or ""}


def _unique(rows: list[dict]) -> list[dict]:
    uniq: dict[str, dict] = {}
    for r in rows:
        p = _person(r)
        uniq.setdefault(p["yok_id"] or p["name"], p)
    return list(uniq.values())


async def _pages(client, **filters) -> list[dict]:
    """Listeyi küçük sayfalarla, sayfalar arası bekleyerek okur; ilk hatada durur (sigorta api() içinde)."""
    rows, page = [], 1
    while len(rows) < MAX_PEOPLE:
        if page > 1:
            await asyncio.sleep(STAFF_PAGE_GAP)
        d = await api(client, "/akademisyen/list", page=page, length=PAGE, **filters, **ACTIVE)
        batch = (d or {}).get("data") or []
        rows += batch
        if not batch or page >= ((d or {}).get("totalPages") or 1):
            break
        page += 1
    return rows


async def _faculty_id(client, uni: dict, faculty_name: str) -> str:
    """Fakültenin YÖK birim kimliği (süzme ekranındaki fakülte listesi: birim-list listVal=2). 1 yıl saklanır."""
    uid = uni_id(uni["name"])
    units = _load(f"units3-{uid}", UNIT_TTL)
    if units is None:
        rows = await api(client, "/genel/birim-list", listVal=2, q=uni["birim_id"]) or []
        units = {clean(u["label"]): u.get("value") for u in rows if u.get("label") and u.get("value")}
        if units:
            _save(f"units3-{uid}", units)
    want = _key(faculty_name)
    return next((v for label, v in (units or {}).items() if _key(label) == want), "") or ""


async def faculty_rows(client, uni: dict, faculty_name: str) -> list[dict] | None:
    """Yalnız bu fakültenin kadrosu (fakulteAd süzgeci): fakülte başına çoğunlukla 1 istek. Süzgecin gerçekten
    çalıştığı ilk yanıtta denetlenir (gelen herkes bu fakülteden mi); çalışmıyorsa bir daha denenmez → None."""
    # "Süzgeç çalışmıyor" kararı kısa süre geçerli: engel sırasındaki tek hata aylarca kalıcı karara dönüşmesin.
    if _load("_faculty_filter", FILTER_RETRY) is False:
        return None
    want = _unit_tokens(faculty_name)
    fid = await _faculty_id(client, uni, faculty_name)
    if not fid:
        return None
    scope = {"birimId": uni["birim_id"], "birimId_matchMode": "equals", "facultyId": fid, "facultyId_matchMode": "equals"}
    async with _BULK:
        first = await api(client, "/akademisyen/list", page=1, length=PAGE, **scope, **ACTIVE)
        batch = (first or {}).get("data") or []
        faculties = {place(r)[0] for r in batch} - {""}
        if batch and any(_jaccard(want, _unit_tokens(f)) < 0.6 for f in faculties):
            _save("_faculty_filter", False)  # süzgeç yok sayılıyor: tüm üniversite geliyor
            return None
        if not batch:
            return []
        _save("_faculty_filter", True)
        rows, pages = list(batch), (first or {}).get("totalPages") or 1
        for page in range(2, min(pages, MAX_PEOPLE // PAGE) + 1):
            await asyncio.sleep(STAFF_PAGE_GAP)
            d = await api(client, "/akademisyen/list", page=page, length=PAGE, **scope, **ACTIVE)
            more = (d or {}).get("data") or []
            if not more:
                break
            rows += more
    return _unique(rows)


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
            people = _load(pkey, STAFF_TTL)
            if people and not any(p.get("faculty") or p.get("department") for p in people):
                people = None  # YÖK alan adlarını değiştirdiği dönemde bölümsüz kaydedilmiş kadro: yeniden alınır
            if people is None:
                stale = False
                try:
                    # Önce yalnız bu fakülte (küçük istek); süzgeç çalışmıyorsa ya da boşsa üniversite listesi.
                    own = await faculty_rows(client, uni, faculty_name)
                    if own:
                        _save(pkey, own)
                        return {"university": uni["name"], "faculty": own[0]["faculty"], "people": own}
                    if own == [] and _load("_faculty_filter", STAFF_TTL) is True:
                        return None  # süzgeç çalışıyor ama bu adla kimse yok: tüm üniversiteyi çekmeye değmez
                    # Tüm üniversitenin kadrosu artık çekilmez (IP engelinin kaynağı): yalnız eski kayıt varsa
                    # ondan ayıklanır; yoksa None → çağıran kurum sitesindeki kadroya düşer.
                    everyone = _stale("unistaff-" + uni_id(uni["name"]))
                    if everyone is None:
                        return None
                except httpx.HTTPError:
                    # YÖK yanıt vermiyor: eski kayıt varsa onu göster (yeni istek atılmaz).
                    people = _stale(pkey)
                    if people is None:
                        everyone = _stale("unistaff-" + uni_id(uni["name"]))
                        if everyone is None:
                            raise
                        stale = True
                if people is not None:
                    return {"university": uni["name"], "faculty": people[0]["faculty"], "people": people, "stale": True} if people else None
                groups: dict[str, list] = {}
                for p in everyone:
                    groups.setdefault(p["faculty"], []).append(p)
                fac = max(groups, key=lambda f: _jaccard(want, _unit_tokens(f)), default=None)
                if not fac or _jaccard(want, _unit_tokens(fac)) < 0.6:
                    # YÖK'e ulaşıldı ama bu birime (ör. uygulama ve araştırma merkezi) kayıtlı kimse yok: hata değil.
                    return {"university": uni["name"], "faculty": faculty_name, "people": [], "empty": True}
                people = groups[fac]
                if not stale:  # eski kayıttan türetilen liste taze gibi saklanmaz
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
    error = ""
    token = URGENT.set(True)  # sayfa açılışı: kadro sayıları gibi arka plan isteklerinin önüne geçer
    try:
        return await _university_detail(uid, uni)
    finally:
        URGENT.reset(token)


async def _university_detail(uid: str, uni: dict) -> dict:
    error = ""
    async with _client(12) as client:
        items = _load(f"fac2-{uid}", UNIT_TTL)
        if items is None:
            try:
                units = await api(client, "/genel/birim-list", listVal=2, q=uni["birim_id"]) or []
                items = [clean(u["label"]) for u in units if u.get("label")]
                if items:
                    _save(f"fac2-{uid}", items)
            except httpx.HTTPError:
                # YÖK'e ulaşılamıyor: sayfa yine açılır (öğrenci bakışı kurum sitesinden okur); fakülteler eski kayıttan.
                items = _stale(f"fac2-{uid}") or []
                error = ("YÖK Akademik'e şu an ulaşılamıyor; fakülteler son kayıttan gösteriliyor." if items else
                         "YÖK Akademik'e şu an ulaşılamıyor; fakülte listesi alınamadı. Öğrenci bakışındaki genel başlıklar çalışır.")
        home = await _home_of(client, uni) or _stale(f"home-{uid}") or ""
    return {"id": uid, "name": uni["name"], "raw": uni["raw"], "home": home, "yok_error": error,
            "items": [{"name": display_uni(f), "raw": f} for f in items]}


async def _faculty_units(uid: str, faculty_raw: str, refresh: bool = False, urgent: bool = True) -> dict[str, str] | None:
    """Fakültenin bölümleri {okunur ad: YÖK birim kimliği}; kadro çekmeden en çok iki küçük istek. Kimlikler
    1 yıl saklanır; kimlik eskirse department_staff tazeler. None: fakülte bulunamadı ya da YÖK'e ulaşılamadı."""
    key = "deps4-" + hashlib.sha1(f"{uid}|{_key(faculty_raw)}".encode()).hexdigest()[:14]
    cached = None if refresh else _load(key, UNIT_TTL)
    if cached is not None:
        return cached
    uni = await _university(uid)
    if not uni:
        return None
    token = URGENT.set(urgent)  # tıklanan fakülte arka plan isteklerinin önüne geçer; iş bitince eski haline döner
    try:
        async with _client(12) as client:
            units = None if refresh else _load(f"units3-{uid}", UNIT_TTL)
            if units is None:
                rows = await api(client, "/genel/birim-list", listVal=2, q=uni["birim_id"]) or []
                units = {clean(u["label"]): u.get("value") for u in rows if u.get("label") and u.get("value")}
                if units:
                    _save(f"units3-{uid}", units)
            want = _key(faculty_raw)
            fid = next((v for label, v in units.items() if _key(label) == want), None)
            if not fid:
                return None
            rows = await api(client, "/genel/birim-list", listVal=3, q=fid) or []
    except (httpx.HTTPError, ValueError):
        return _stale(key)
    finally:
        URGENT.reset(token)
    out, links = {}, {}
    for u in rows:
        if u.get("label"):
            name = display_uni(re.sub(r"\s*B[ÖO]L[ÜU]M[ÜU]$", "", clean(u["label"]), flags=re.I))
            out.setdefault(name, u.get("value") or "")
            # YÖK satırında bölümün sitesi varsa (alan adı değişebilir: http ile başlayan ilk alan) saklanır.
            link = next((v for v in u.values() if isinstance(v, str) and re.match(r"https?://", v)), "")
            if link:
                links[name] = link
    if out:
        _save(key, out)
        if links:
            _save(key + "-links", links)
    return out or None


def cached_departments(uid: str, faculty_raw: str, uni: dict | None = None) -> list[str] | None:
    """YÖK'e ulaşılamazken: daha önce kaydedilmiş kadrodan (fakülte ya da üniversite listesi, süresi geçmiş olsa da)
    bu fakültenin bölüm adları. Ağa çıkmaz."""
    key = "deps4-" + hashlib.sha1(f"{uid}|{_key(faculty_raw)}".encode()).hexdigest()[:14]
    old = _stale(key)
    if old:
        return sorted(old, key=fold)
    people = None
    if uni:
        people = _stale(people_key(uni["name"], faculty_raw))
    if not people:
        want = _unit_tokens(faculty_raw)
        everyone = _stale("unistaff-" + uid) or []
        people = [p for p in everyone if _jaccard(want, _unit_tokens(p.get("faculty") or "")) >= 0.6]
    names = {display_uni(re.sub(r"\s*B[ÖO]L[ÜU]M[ÜU]$", "", p.get("department") or "")) for p in people or []} - {""}
    return sorted(names, key=fold) or None


def department_links(uid: str, faculty_raw: str) -> dict[str, str]:
    """YÖK birim listesinde gelen bölüm siteleri (varsa); ağa çıkmaz."""
    key = "deps4-" + hashlib.sha1(f"{uid}|{_key(faculty_raw)}".encode()).hexdigest()[:14]
    return _load(key + "-links", UNIT_TTL) or {}


async def faculty_departments(uid: str, faculty_raw: str, refresh: bool = False, urgent: bool = True) -> list[str] | None:
    """Fakültenin bölüm adları (kadro çekilmez)."""
    units = await _faculty_units(uid, faculty_raw, refresh, urgent)
    return sorted(units, key=fold) if units else None


async def department_staff(uid: str, faculty_raw: str, department: str, urgent: bool = True,
                           refresh: bool = False, _retry: bool = True) -> list[dict] | None:
    """Yalnız bu bölümün aktif kadrosu: bölümün YÖK birim kimliğiyle süzülmüş liste (çoğunlukla tek istek),
    30 gün saklanır. Süzgecin gerçekten bölümle sınırladığı ilk yanıtta denetlenir; sınırlamıyorsa bir daha
    denenmez ve None döner (çağıran fakülte kadrosuna düşer). None: YÖK'e ulaşılamadı / bölüm yok."""
    key = "depstaff-" + hashlib.sha1(f"{uid}|{_key(faculty_raw)}|{_key(department)}".encode()).hexdigest()[:14]
    cached = None if refresh else _load(key, STAFF_TTL)
    if cached:
        return cached
    if cached == [] and _load(key, EMPTY_TTL) is not None:
        return cached  # boş yanıt kısa süre saklanır: YÖK geçici olarak boş döndüyse aylarca "kadro yok" kalmaz
    if _load("_department_filter", FILTER_RETRY) is False:
        return None
    units = await _faculty_units(uid, faculty_raw, refresh=refresh and _retry) or {}
    want = _unit_tokens(department)
    name = max(units, key=lambda n: _jaccard(want, _unit_tokens(n)), default=None)
    if not name or not units.get(name) or _jaccard(want, _unit_tokens(name)) < 0.6:
        return None
    uni = await _university(uid)
    fid = next((v for label, v in (_load(f"units3-{uid}", UNIT_TTL) or {}).items() if _key(label) == _key(faculty_raw)), "")
    if not uni or not fid:
        return None
    # YÖK'ün kendi süzme ekranındaki parametreler: üniversite (birimId) + fakülte (facultyId) + bölüm (departmentId).
    scope = {"birimId": uni["birim_id"], "birimId_matchMode": "equals", "facultyId": fid, "facultyId_matchMode": "equals",
             "departmentId": units[name], "departmentId_matchMode": "equals"}
    token = URGENT.set(urgent)
    rows, page = [], 1
    try:
        async with _client(15) as client:
            while True:
                d = await api(client, "/akademisyen/list", page=page, length=PAGE, **scope, **ACTIVE)
                batch = (d or {}).get("data") or []
                if page == 1 and batch:
                    deps = {place(r)[1] for r in batch} - {""}
                    if any(_jaccard(want, _unit_tokens(x)) < 0.6 for x in deps):
                        _save("_department_filter", False)  # süzgeç yok sayılıyor: başka bölümler de geliyor
                        return None
                    _save("_department_filter", True)
                rows += batch
                if not batch or page >= ((d or {}).get("totalPages") or 1) or len(rows) >= MAX_PEOPLE:
                    break
                page += 1
                await asyncio.sleep(STAFF_PAGE_GAP)
    except httpx.HTTPStatusError as exc:
        if page == 1 and exc.response is not None and 400 <= exc.response.status_code < 500 and exc.response.status_code != 429:
            _save("_department_filter", False)  # YÖK bu süzgeci kabul etmiyor: her tıklamada yeniden denenmez
        return _stale(key)
    except (httpx.HTTPError, ValueError):
        return _stale(key)
    finally:
        URGENT.reset(token)
    if not rows and _retry:
        # Saklı birim kimliği eskimiş olabilir: kimlikleri bir kez tazeleyip yeniden dene.
        return await department_staff(uid, faculty_raw, department, urgent, refresh=True, _retry=False)
    people = _unique(rows)
    _save(key, people)
    return people


async def academic_stats(guid: str, refresh: bool = False) -> dict | None:
    """Akademisyenin YÖK Akademik'teki hazır istatistikleri: Web of Science yıllık yayın/atıf, yayın türü ve kapsam
    dağılımı, toplam sayılar. Üç küçük istek; 30 gün saklanır. None: YÖK'e ulaşılamadı."""
    if not re.fullmatch(r"[0-9A-F]{16}", guid or ""):
        return None
    key = f"stats2-{guid}"
    cached = None if refresh else _load(key, 30 * 24 * 3600)
    if cached is not None:
        return cached
    token = URGENT.set(True)
    try:
        async with _client(15) as client:
            yearly = await api(client, "/analiz/wos-yillik-istatistik", authorGuidId=guid) or []
            kinds = await api(client, "/analiz/yayin-tur-kapsam-dagilimi", authorGuidId=guid) or []
            totals = await api(client, "/analiz/total-count-by-academician", authorGuidId=guid) or []
            # Profil sayfasındaki "Metrikler" (WoS / Scopus yayın, atıf, h-indeks), alan bilgisi ve BM Sürdürülebilir
            # Kalkınma Amaçları: kayıtlı profil eski olsa da buradan gelir.
            try:
                detail = await api(client, "/akademisyen/detay", authorGuidId=guid) or {}
                goals = await api(client, "/surdurulebilirlik/list", authorGuidId=guid) or []
            except (httpx.HTTPError, ValueError):
                detail, goals = {}, []
    except (httpx.HTTPError, ValueError):
        return _stale(key)
    finally:
        URGENT.reset(token)
    out = {
        "wos_yearly": [{"year": r.get("yil"), "pubs": r.get("yayinSayisi") or 0, "cites": r.get("atifSayisi") or 0}
                       for r in yearly if isinstance(r, dict) and r.get("yil")],
        "types": [{"name": clean(r.get("turAdi") or ""), "national": r.get("ulusalSayi") or 0, "international": r.get("uluslararasiSayi") or 0}
                  for r in kinds if isinstance(r, dict) and r.get("turAdi")],
        "totals": {r.get("label"): r.get("count") or 0 for r in totals if isinstance(r, dict) and r.get("label")},
        "metrics": {
            "wos": {"pubs": _int(detail.get("wpublication")), "cites": _int(detail.get("watif")), "h": _int(detail.get("whindex")),
                    "date": detail.get("wosResearcherDate") or ""},
            "scopus": {"pubs": _int(detail.get("scPublication")), "cites": _int(detail.get("scAtif")), "h": _int(detail.get("scHindex")),
                       "date": detail.get("scopusMetricDate") or ""},
        },
        "ids": {"scopus": detail.get("scopusId") or "", "researcher": detail.get("researcherId") or "", "orcid": detail.get("orcid") or "",
                "scholar": detail.get("gscholar") or ""},
        "area": clean(detail.get("temelAlanAd") or ""), "field": clean(detail.get("bilimAlanAd") or ""),
        "keywords": [clean(detail[k]) for k in ("anahtarkelime1Ad", "anahtarkelime2Ad", "anahtarkelime3Ad") if detail.get(k)],
        "sdgs": [{"id": r.get("sdgId"), "name": clean(r.get("sdgAdTr") or r.get("sdgAdEn") or "")} for r in goals
                 if isinstance(r, dict) and r.get("sdgId")] if isinstance(goals, list) else [],
    }
    _save(key, out)
    return out


def _int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


async def record_detail(guid: str, kind: str, title: str) -> dict | None:
    """Profildeki bir projenin ya da patentin YÖK'teki ayrıntısı (proje: konu ve tam ekip; patent: sınıf ve buluş
    özeti). Kayıt kimliği listeden başlıkla bulunur (liste kişi başına bir kez alınır, 30 gün saklanır), ayrıntı
    kayıt başına bir istek; yalnız kullanıcı kayda tıklayınca çalışır."""
    if not re.fullmatch(r"[0-9A-F]{16}", guid or "") or kind not in {"project", "patent"} or not title:
        return None
    path, id_key, title_key = ("/proje", "projeId", "projeAdi") if kind == "project" else ("/patent", "patentId", "patentBaslik")
    token = URGENT.set(True)
    try:
        async with _client(15) as client:
            rows = _load(f"{kind}list-{guid}", 30 * 24 * 3600)
            if rows is None:
                found = await api(client, f"{path}/list", authorGuidId=guid, page=1, length=1000)
                rows = (found.get("data") if isinstance(found, dict) else found) or []
                _save(f"{kind}list-{guid}", rows)
            want = fold(title)
            row = next((r for r in rows if isinstance(r, dict) and fold(r.get(title_key) or "") == want), None)
            if not row:
                return None
            rid = row.get(id_key)
            detail = _load(f"{kind}-{rid}", 30 * 24 * 3600)
            if detail is None:
                detail = await api(client, f"{path}/detay", **{id_key: rid}) or {}
                _save(f"{kind}-{rid}", detail)
    except (httpx.HTTPError, ValueError):
        return None
    finally:
        URGENT.reset(token)
    merged = {**row, **(detail if isinstance(detail, dict) else {})}
    if kind == "project":
        team = [{"name": tr_title(" ".join(x for x in (m.get("yazarad"), m.get("yazarsoyad")) if x)), "role": clean(m.get("projedekiGoreviAd") or ""),
                 "unit": tr_title(m.get("birimAdi") or "")} for m in merged.get("projeEkip") or [] if isinstance(m, dict)]
        budget = clean(str(merged.get("butcesi") or ""))
        return {"kind": kind, "title": clean(merged.get("projeAdi") or ""), "type": clean(merged.get("projeTuruAd") or ""),
                "status": clean(merged.get("projeDurumuAd") or ""), "start": merged.get("baslangicTarihi") or "",
                "end": merged.get("bitisTarihi") or merged.get("bitisyil") or "", "budget": "" if budget in ("", "0") else budget,
                "team": team, "subject": clean(merged.get("projeKonusu") or "")}
    split = lambda text: [clean(x) for x in str(text or "").split(",") if clean(x)]  # noqa: E731
    return {"kind": kind, "title": clean(merged.get("patentBaslik") or ""), "number": clean(merged.get("patentNo") or ""),
            "year": clean(str(merged.get("patentTarih") or "")), "type": clean(merged.get("patentDosyaTipi") or ""),
            "category": clean(merged.get("kategoriAd") or ""), "classes": clean(merged.get("patentSinif") or ""),
            "applicants": split(merged.get("patentBasvuruSahip")), "inventors": split(merged.get("patentBulusSahip")),
            "abstract": clean(merged.get("bulusOzet") or "")}


def public_person(p: dict, university: str = "") -> dict:
    """Arayüze giden satır: kurum yolu okunur yazımla, sıralama için unvan sırası değil unvanın kendisi."""
    dept = re.sub(r"\s*B[ÖO]L[ÜU]M[ÜU]$", "", p.get("department") or "")
    return p | {"university": display_uni(p.get("university") or university), "faculty": display_uni(p.get("faculty") or ""),
                "department": display_uni(dept), "department_raw": p.get("department") or ""}


def by_rank(people: list[dict]) -> list[dict]:
    return sorted(people, key=lambda p: (TITLE_RANK.get(p.get("title"), 9), fold(p.get("name"))))


async def _staff_by_departments(uid: str, faculty_raw: str) -> list[dict]:
    """Fakülte kadrosu bölüm bölüm (bölüm birim kimliğiyle küçük istekler; hız sınırına uyar, saklanır). Fakülte
    süzgeci çalışmadığında tüm üniversiteyi çekmek yerine kullanılır."""
    names = await faculty_departments(uid, faculty_raw) or []
    people: list[dict] = []
    empty_run = 0
    for name in names[:60]:
        rows = await department_staff(uid, faculty_raw, name, _retry=False)
        if rows is None and _load("_department_filter", FILTER_RETRY) is False:
            break  # bölüm süzgeci de çalışmıyor: kalan bölümler için istek atılmaz
        empty_run = 0 if rows else empty_run + 1
        if empty_run >= 3 and not people:
            break  # YÖK art arda boş dönüyor (geçici kısıt olabilir): kalan bölümler için istek atılmaz
        people += rows or []
    seen: dict[str, dict] = {}
    for person in people:  # bölüm kadroları zaten kişi biçiminde; iki bölümde görünen kişi bir kez
        seen.setdefault(person.get("yok_id") or person.get("name"), person)
    return list(seen.values())


async def faculty_detail(uid: str, faculty_raw: str, by_departments: bool = True) -> dict | None:
    """Fakülte kadrosu ve kurum yolundan çıkan bölümler; (None: üniversite/fakülte yok ya da YÖK'e ulaşılamadı).
    Fakülte kadrosu tek istekle alınamazsa bölüm bölüm toplanır (by_departments)."""
    uni = await _university(uid)
    if not uni:
        return None
    try:
        fac = await faculty_staff([uni["raw"]], faculty_raw)
    except httpx.HTTPError:
        fac = None
    if (not fac or not fac.get("people")) and by_departments:
        rows = await _staff_by_departments(uid, faculty_raw)
        if rows:
            fac = {"university": uni["name"], "faculty": rows[0].get("faculty") or faculty_raw, "people": rows}
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


async def search_people(q: str, limit: int = 60, timeout: float = 45) -> list[dict]:
    """YÖK'te ad araması (API, tarayıcısız). Aynı adlı kişiler seçim için listelenir."""
    query = clean(q)
    key = "search2-" + hashlib.sha1(fold(query).encode()).hexdigest()[:12]
    people = _load(key, 24 * 3600)
    if people is None:
        async with _client(timeout) as client:
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
