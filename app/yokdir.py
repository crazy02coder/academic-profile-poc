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

import httpx

from .config import ROOT
from .discover import tr_title
from .sources import YOK_TITLES
from .text import clean, fold, name_tokens

BASE = "https://akademik.yok.gov.tr"
UNIVERSITIES = f"{BASE}/AkademikArama/view/universityListview.jsp"
DIR = ROOT / "data" / "yok"
TTL = 7 * 24 * 3600
MAX_PAGES = 60  # sayfa başına 20 kişi
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
            "name": tr_title(clean(html.unescape(name.group(2)))), "title": YOK_TITLES.get(h6[0] if h6 else "", ""),
            "faculty": path[1] if len(path) > 1 else "", "department": path[2] if len(path) > 2 else "",
            "orcid": orcid.group(1) if orcid else "", "email": clean(mail.group(1)) if mail else "",
            "url": BASE + html.unescape(name.group(1)), "yok_id": yok_id.group(1) if yok_id else "",
            "photo": "", "source": "yok"})
    return out


async def _listing(client, url: str) -> list[dict]:
    """Bir birimin tüm akademisyenleri; sayfalama bağlantıları oturuma bağlı olduğu için sıralı gezilir."""
    rows, seen_pages, queue = [], set(), [url]
    while queue and len(seen_pages) < MAX_PAGES:
        u = queue.pop(0)
        if u in seen_pages:
            continue
        seen_pages.add(u)
        r = await client.get(u)
        if r.status_code != 200:
            break
        rows += _rows(r.text)
        pager = re.search(r'class="pagination">(.*?)</ul>', r.text, re.S)
        for h, n in re.findall(r'<a href="([^"]+)">(\d+)</a>', pager.group(1) if pager else ""):
            nxt = BASE + html.unescape(h)
            if nxt not in seen_pages and nxt not in queue:
                queue.append(nxt)
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
