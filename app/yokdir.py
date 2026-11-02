"""YÖK Akademik kurum dizini: üniversite → fakülte → akademisyen.

Her satırda unvan, ad, birim yolu ("ÜNİVERSİTE/FAKÜLTE/BÖLÜM/PROGRAM"), ORCID, e-posta ve YÖK kimliği bulunur.
Yapı Türkiye'deki tüm üniversitelerde aynıdır; kurum sitelerinin birbirinden farklı kadro sayfası düzenlerine
bağımlı değildir. Kurum sitesi ayrıştırması (directory._people) fotoğraf/profil bağlantısı ve YÖK'e
ulaşılamadığında yedek için kullanılır.

Liste sayfaları (universityListview.jsp, AkademisyenArama?birim=…) herkese açıktır; istekler sıralı ve
önbelleklidir (data/yok/, 7 gün).
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import time
from collections import Counter
from urllib.parse import urljoin

import httpx

from . import recipes
from .config import ROOT
from .discover import registrable, tr_title
from .sources import YOK_TITLES
from .text import clean, fold, name_score, name_tokens

BASE = "https://akademik.yok.gov.tr"
UNIVERSITIES = f"{BASE}/AkademikArama/view/universityListview.jsp"
DIR = ROOT / "data" / "yok"
TTL = 7 * 24 * 3600
MAX_PAGES = 120  # sayfa başına 20 kişi
SEARCH_URL = f"{BASE}/AkademikArama/AkademisyenArama"
# Ad araması formu; REA'nın öğrendiği tarif (data/recipes/yok.gov.tr.json) varsa o kullanılır
SEARCH_FORM = [["aramaTerim", "{name}"], ["islem", "1"], ["yazarCheckbox", "on"]]
FREE_MAIL = {"gmail.com", "hotmail.com", "yahoo.com", "outlook.com", "yandex.com", "icloud.com", "live.com", "msn.com",
             "windowslive.com", "mynet.com", "hotmail.com.tr", "yahoo.com.tr"}
TITLE_RANK = {"Prof. Dr.": 0, "Doç. Dr.": 1, "Dr. Öğr. Üyesi": 2, "Öğr. Gör.": 3, "Arş. Gör.": 4}
# tr_title kısaltmaları bozmasın: "Ted Üniversitesi" değil "TED Üniversitesi"
ACRONYMS = ("TED", "TOBB", "MEF", "OSTİM", "KTO", "SANKO", "TOGÜ", "ODTÜ", "İSTE", "ERÜ")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
# Birim adlarında eşleştirmeyi bozan ekler: "Yazılım Mühendisliği Bölümü", "… Lisans", "… (İngilizce)"
UNIT_NOISE = {"bolumu", "bolum", "lisans", "programi", "program", "pr", "turkce", "ingilizce", "department", "of",
              "anabilim", "dali", "fakultesi", "faculty", "the"}


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", " ", fold(text).replace("ı", "i")).strip()


def _unit_tokens(text: str) -> set[str]:
    return {t for t in _key(text).split() if t not in UNIT_NOISE and len(t) > 1}


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=30, follow_redirects=True, headers={"User-Agent": UA, "Accept-Language": "tr"})


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


# ------------------------------------------------------------------ üniversite ve fakülteler
async def universities(client) -> list[dict]:
    cached = _load("universities", 30 * 24 * 3600)
    if cached:
        return cached
    r = await client.get(UNIVERSITIES)
    r.raise_for_status()
    out = [{"name": clean(html.unescape(n)), "url": BASE + html.unescape(h)}
           for h, n in re.findall(r'<a href="(/AkademikArama/AkademisyenArama\?islem=[^"]+)">([^<]+)</a>', r.text)]
    if out:
        _save("universities", out)
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


def _units(page: str) -> list[dict]:
    return [{"name": clean(html.unescape(n)), "url": BASE + html.unescape(h)}
            for h, n in re.findall(r'<a href="(/AkademikArama/AkademisyenArama\?birim=[^"]+)"[^>]*><span>([^<]+)', page)]


def _rows(page: str) -> list[dict]:
    out = []
    for row in re.findall(r'<tr id="authorInfo_\d+">(.*?)</tr>', page, re.S):
        name = re.search(r"<h4><a href=\"([^\"]+)\">([^<]+)</a></h4>", row)
        if not name:
            continue
        h6 = [clean(html.unescape(x)) for x in re.findall(r"<h6>([^<]*)</h6>", row)]
        path = [clean(x) for x in (h6[1] if len(h6) > 1 else "").split("/") if clean(x)]
        orcid = re.search(r"ORCID:(\d{4}-\d{4}-\d{4}-\d{3}[\dX])", row)
        mail = re.search(r'href="mailto:([^"]+)"', row)
        yok_id = re.search(r"authorId=([0-9A-F]+)", name.group(1))
        out.append({
            "name": tr_title(clean(html.unescape(name.group(2)))),
            "title": YOK_TITLES.get(h6[0], tr_title(h6[0])) if h6 else "", "university": path[0] if path else "",
            "faculty": path[1] if len(path) > 1 else "", "department": path[2] if len(path) > 2 else "",
            "orcid": orcid.group(1) if orcid else "", "email": clean(mail.group(1)) if mail else "",
            "url": BASE + html.unescape(name.group(1)), "yok_id": yok_id.group(1) if yok_id else "",
            "photo": "", "source": "yok"})
    return out


async def _listing(client, url: str, max_pages: int = MAX_PAGES) -> list[dict]:
    """Bir birimin tüm akademisyenleri. Sayfalama bağlantıları oturuma bağlı ve her açılışta farklı kodlu olduğu
    için sayfa numarasına göre sıralı gezilir (URL'ye göre gezmek her birimde MAX_PAGES isteğe gider)."""
    rows, done, pending = [], {1}, {}
    while url and len(done) <= max_pages:
        r = await client.get(url)
        if r.status_code != 200:
            break
        rows += _rows(r.text)
        pager = re.search(r'class="pagination">(.*?)</ul>', r.text, re.S)
        for h, n in re.findall(r'<a href="([^"]+)">(\d+)</a>', pager.group(1) if pager else ""):
            if int(n) not in done:
                pending[int(n)] = BASE + html.unescape(h)
        if not pending:
            break
        page = min(pending)
        url = pending[page]
        pending.clear()
        done.add(page)
    uniq = {}
    for p in rows:
        uniq.setdefault(p["yok_id"] or p["name"], p)
    return list(uniq.values())


async def faculty_staff(uni_names: list[str], faculty_name: str) -> dict | None:
    """Fakültenin YÖK kadrosu: {"university", "faculty", "people"} ya da None (YÖK'e ulaşılamadı / eşleşme yok).

    Fakülte adı kurum yolundaki adla eşleşmezse None döner (tüm üniversiteyi taramak yerine site ayrıştırmasına
    düşülür).
    """
    want = _unit_tokens(faculty_name)
    if not want:
        return None
    async with _client() as client:
        try:
            uni = match_university(await universities(client), uni_names)
            if not uni:
                return None
            pkey = "people-" + hashlib.sha1(f"{uni['name']}|{' '.join(sorted(want))}".encode()).hexdigest()[:12]
            people = _load(pkey)
            if people is None:
                # birim bağlantıları oturuma bağlı olabilir: her seferinde üniversite sayfasından alınır
                r = await client.get(uni["url"])
                r.raise_for_status()
                facs = _units(r.text)
                fac = max(facs, key=lambda f: _jaccard(want, _unit_tokens(f["name"])), default=None)
                if not fac or _jaccard(want, _unit_tokens(fac["name"])) < 0.6:
                    return None
                people = await _listing(client, fac["url"])
                if people:
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
    """YÖK'teki tüm üniversiteler: {"id", "name" (okunur), "raw", "url"}."""
    async with _client() as client:
        unis = await universities(client)
    return sorted(({"id": uni_id(u["name"]), "name": display_uni(u["name"]), "raw": u["name"], "url": u["url"]} for u in unis),
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


async def _home_of(client, uni: dict) -> str:
    """Üniversite sayfasındaki ilk akademisyenlerin e-postalarından kurum sitesi (site adresini kullanıcı girmez)."""
    key = f"home-{uni['id']}"
    cached = _load(key, 30 * 24 * 3600)
    if cached is not None:
        return cached
    r = await client.get(uni["url"])
    r.raise_for_status()
    domain = site_domain(_rows(r.text))
    home = f"https://www.{domain}" if domain else ""
    _save(key, home)
    return home


async def university_detail(uid: str) -> dict | None:
    """Üniversite: {"id", "name", "raw", "home", "items": fakülteler}. Sonuç 7 gün saklanır."""
    uni = await _university(uid)
    if not uni:
        return None
    async with _client() as client:
        items = _load(f"fac-{uid}")
        if items is None:
            r = await client.get(uni["url"])
            r.raise_for_status()
            items = [f["name"] for f in _units(r.text)]
            if items:
                _save(f"fac-{uid}", items)
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
    return {"university": uni["name"], "faculty": display_uni(faculty_raw), "people": people, "departments": deps,
            "domain": site_domain(fac["people"])}


async def search_people(q: str, limit: int = 60) -> list[dict]:
    """YÖK'te ad araması: tarayıcısız, REA'nın öğrendiği form isteğiyle. Aynı adlı kişiler seçim için listelenir."""
    query = clean(q)
    key = "search-" + hashlib.sha1(fold(query).encode()).hexdigest()[:12]
    people = _load(key, 24 * 3600)
    if people is None:
        store = recipes.load("yok.gov.tr")
        recipe = store["replay"].get("yok_search") or {}
        form = {k: str(v).replace("{name}", query) for k, v in (recipe.get("form") or SEARCH_FORM)}
        async with _client() as client:
            await client.get(UNIVERSITIES)  # oturum çerezi
            r = await client.post(recipe.get("url") or SEARCH_URL, data=form)
            r.raise_for_status()
            link = re.search(r'<a[^>]*href="([^"]+)"[^>]*>(?:(?!</a>).){0,200}Akademisyenler', r.text, re.S)
            people = await _listing(client, urljoin(str(r.url), html.unescape(link.group(1))), max_pages=3) if link else []
        if recipe:
            recipe["hits"] = recipe.get("hits", 0) + 1
            recipes.save(store)
        _save(key, people)
    people = sorted(people, key=lambda p: (-name_score(query, p["name"]), TITLE_RANK.get(p.get("title"), 9), fold(p["name"])))
    return [public_person(p) for p in people[:limit]]


async def person_site(university_raw: str, email: str = "") -> str:
    """Seçilen akademisyenin kurum sitesi: kendi kurumsal e-postası, yoksa üniversitenin diğer e-postaları."""
    domain = site_domain([{"email": email}])
    if domain:
        return f"https://www.{domain}"
    uni = await _university(uni_id(university_raw)) if university_raw else None
    if not uni:
        return ""
    try:
        async with _client() as client:
            return await _home_of(client, uni)
    except httpx.HTTPError:
        return ""
