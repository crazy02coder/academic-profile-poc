"""Kurum dizini: üniversite → fakülteler → bölümler → akademisyenler → yayınlar.

Kaynak üniversitenin kendi sitesidir (Scrapling). Bağlantı seçimini önce Gemini yapar
(menüdeki "Fakülte Haberleri" gibi gürültüyü ayıklar); model yoksa kurallar devrededir.
Her seçim sayfadaki gerçek bağlantılarla doğrulanır, uydurma adres kabul edilmez.
Birim yayınları hızlı liste olarak OpenAlex'ten tek seferde alınır; kişi başına tam
YÖK listesi, akademisyenin profili açıldığında gelir.

Sonuçlar alan adı başına önbelleklenir (data/directory/<alan-adı>.json, 7 gün).
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from urllib.parse import urldefrag, urljoin, urlparse

import httpx

from .config import OPENALEX_PARAMS, ROOT, USER_AGENT
from .discover import registrable, tr_title
from .net import fetch_smart, parse
from .text import clean, detect_title, fold, name_in_text, name_score, strip_titles

DIR = ROOT / "data" / "directory"
TTL = 7 * 24 * 3600
OPENALEX = "https://api.openalex.org"

FACULTY_RX = re.compile(r"fak[üu]lte|faculty|y[üu]ksekokul|meslek y[üu]ksekokulu|enstit[üu]|school of|college of|"
                        r"konservatuva?r|conservatory|graduate school", re.I)
DEPT_RX = re.compile(r"b[öo]l[üu]m|department|m[üu]hendisli[ğg]i|anabilim|program[ıi]?\b|dept\b|"
                     r"[öo][ğg]retmenli[ğg]i|bilimleri\b|engineering", re.I)
ROLE_RX = re.compile(r"\s(dekan|rekt[öo]r|m[üu]d[üu]r|b[öo]l[üu]m ba[şs]kan|ba[şs]kan|koordinat[öo]r|"
                     r"sekreter|head\b|dean\b|chair\b|director\b|vice\b)", re.I)
HUB_RX = re.compile(r"fak[üu]lteler|akademik birim|birimler|akademik$|academic units|faculties|schools|"
                    r"b[öo]l[üu]mler|departments|programlar", re.I)
STAFF_RX = re.compile(r"akademik kadro|akademik personel|[öo][ğg]retim (?:[üu]yeleri|elemanlar[ıi]|kadrosu)|"
                      r"kadro|academic staff|faculty members|our people|people|personel", re.I)
NOISE_RX = re.compile(r"haber|duyuru|etkinlik|news|event|announce|y[öo]netmelik|y[öo]nerge|form|ihale|takvim|"
                      r"mezun|alumni|kurul|toplant|tan[ıi]t[ıi]m|video|galeri|gallery|ileti[şs]im|contact|"
                      r"\.pdf$|\.docx?$|\.xlsx?$", re.I)


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _store_path(domain: str):
    return DIR / f"{re.sub(r'[^a-z0-9.-]', '_', domain)}.json"


def load(domain: str) -> dict:
    p = _store_path(domain)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except ValueError:
            pass
    return {"domain": domain, "name": "", "home": "", "faculties": None, "units": {}}


def save(store: dict):
    DIR.mkdir(parents=True, exist_ok=True)
    _store_path(store["domain"]).write_text(json.dumps(store, ensure_ascii=False, indent=1))


def all_stores() -> list[dict]:
    if not DIR.exists():
        return []
    out = []
    for p in sorted(DIR.glob("*.json")):
        try:
            s = json.loads(p.read_text())
        except ValueError:
            continue
        facs = (s.get("faculties") or {}).get("items") or []
        units = s.get("units") or {}
        out.append({"domain": s["domain"], "name": s.get("name") or s["domain"], "home": s.get("home", ""),
                    "faculties": len(facs), "departments": sum(len((u.get("departments") or {}).get("items") or [])
                                                               for u in units.values()),
                    "people": sum(len((u.get("staff") or {}).get("items") or []) for u in units.values()),
                    "updated": (s.get("faculties") or {}).get("at", "")})
    return out


def _fresh(entry: dict | None) -> bool:
    return bool(entry) and time.time() - entry.get("ts", 0) < TTL


def _entry(items: list, **extra) -> dict:
    # Boş sonuç önbellekte tutulmaz (ts=0): site geçici hata verdiyse ya da kural değiştiyse bir sonraki tık yeniden dener.
    return {"items": items, "at": _now(), "ts": time.time() if items else 0, **extra}


# ------------------------------------------------------------------ sayfa ve bağlantılar
async def _page(url: str):
    page = await fetch_smart(url)
    if page.status >= 400 or not page.html:
        raise RuntimeError(f"{url} açılamadı (HTTP {page.status})")
    return parse(page.html, page.url or url), page.url or url


def _anchors(sel, base: str) -> list[dict]:
    root = registrable(urlparse(base).hostname or "")
    seen, out = set(), []
    for a in sel.css("a[href]"):
        href = (a.attrib.get("href") or "").strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        url = urldefrag(urljoin(base, href))[0].rstrip("/")
        host = urlparse(url).hostname or ""
        text = clean(a.get_all_text(separator=" ")) or clean(a.attrib.get("title", ""))
        if not url.startswith("http") or registrable(host) != root or not (3 <= len(text) <= 90):
            continue
        key = (fold(text), url)
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": text, "url": url})
    return out


def _site_name(sel) -> str:
    title = clean((sel.css("title::text").get() or ""))
    # "OSTİM Teknik Üniversitesi: İş Tecrübeli Yeni Mezunlar" gibi slogan ekleri ayrılır
    parts = [p.strip() for p in re.split(r"\s*[|–—»:]\s+|\s-\s", title) if p.strip()]
    uni = next((p for p in parts if re.search(r"[üu]niversite|university", p, re.I)), "")
    return uni or (parts[-1] if parts else "")


def _rule_pick(anchors: list[dict], rx: re.Pattern, limit: int = 60) -> list[dict]:
    out, seen = [], set()
    for a in anchors:
        if rx.search(a["name"]) and not NOISE_RX.search(a["name"]) and not NOISE_RX.search(a["url"]) \
                and not HUB_RX.fullmatch(a["name"].strip()):
            key = fold(a["name"])
            if key not in seen:
                seen.add(key)
                out.append(a)
    return out[:limit]


async def _llm_pick(anchors: list[dict], kind: str, context: str, llm) -> list[dict] | None:
    """Gemini numaralı bağlantı listesinden birimleri seçer; yalnız listedeki numaralar kabul edilir."""
    if llm is None or not llm.available or not anchors:
        return None
    shown = anchors[:280]
    what = {"faculty": "fakülteleri, yüksekokulları, meslek yüksekokullarını ve enstitüleri",
            "department": "bu fakültenin akademik bölümlerini / anabilim dallarını / programlarını"}[kind]
    lines = "\n".join(f"{i}. {a['name']} → {urlparse(a['url']).path or '/'}" for i, a in enumerate(shown))
    data = await llm.json(
        f"{context} sayfasındaki bağlantılar aşağıda. Bunlardan yalnızca {what} seç. Haber, duyuru, yönetim, "
        f"iletişim, belge, öğrenci işleri, kulüp ve genel menü bağlantılarını alma. Aynı birim birden çok kez "
        f"geçiyorsa birim ana sayfasına gideni seç. Birim adını düzgün Türkçe yaz.\n\n{lines}",
        {"type": "object", "properties": {"items": {"type": "array", "items": {
            "type": "object", "properties": {"i": {"type": "integer"}, "name": {"type": "string"}},
            "required": ["i", "name"]}}}, "required": ["items"]}, timeout=60, fast=True)
    if not data or not isinstance(data.get("items"), list):
        return None
    out, seen = [], set()
    for it in data["items"]:
        i = it.get("i")
        if isinstance(i, int) and 0 <= i < len(shown) and shown[i]["url"] not in seen:
            seen.add(shown[i]["url"])
            out.append({"name": clean(it.get("name")) or shown[i]["name"], "url": shown[i]["url"]})
    return out


async def _hub_anchors(anchors: list[dict], rx: re.Pattern, limit: int = 2) -> list[dict]:
    """'Fakülteler', 'Akademik Birimler' gibi ara sayfaları da açıp bağlantılarını ekler."""
    hubs = [a for a in anchors if HUB_RX.search(a["name"]) and not NOISE_RX.search(a["name"])][:limit]
    extra = []
    for res in await asyncio.gather(*(_page(h["url"]) for h in hubs), return_exceptions=True):
        if not isinstance(res, Exception):
            extra.extend(_anchors(*res))
    return extra


# ---------------------------------------------------------------------- dizin katmanları
async def faculties(url: str, llm=None, refresh: bool = False) -> dict:
    host = urlparse(url).hostname or ""
    domain = registrable(host)
    store = load(domain)
    if not refresh and _fresh(store.get("faculties")):
        return {"domain": domain, "name": store["name"], "home": store["home"], **store["faculties"]}
    home = f"{urlparse(url).scheme or 'https'}://{host}"
    pages = await asyncio.gather(_page(url), *(() if url.rstrip("/") == home else (_page(home),)),
                                 return_exceptions=True)
    anchors, name = [], ""
    for res in pages:
        if isinstance(res, Exception):
            continue
        sel, base = res
        name = name or _site_name(sel)
        anchors.extend(_anchors(sel, base))
    if not anchors:
        raise RuntimeError("Üniversite sitesi açılamadı.")
    if len(_rule_pick(anchors, FACULTY_RX)) < 4:
        anchors.extend(await _hub_anchors(anchors, FACULTY_RX))
    items = await _llm_pick(anchors, "faculty", name or domain, llm)
    method = "gemini"
    if not items:
        items, method = _rule_pick(anchors, FACULTY_RX), "kural"
    store.update(name=name or store.get("name") or domain, home=home, faculties=_entry(items, method=method))
    save(store)
    return {"domain": domain, "name": store["name"], "home": home, **store["faculties"]}


async def departments(unit_url: str, llm=None, refresh: bool = False) -> dict:
    domain = registrable(urlparse(unit_url).hostname or "")
    store = load(domain)
    unit = store["units"].setdefault(unit_url, {})
    if not refresh and _fresh(unit.get("departments")):
        return unit["departments"]
    sel, base = await _page(unit_url)
    anchors = _anchors(sel, base)
    if len(_rule_pick(anchors, DEPT_RX)) < 3:
        anchors.extend(await _hub_anchors(anchors, DEPT_RX))
    # Bölüm bağlantıları fakültenin altında olmalı; site geneli menüyü dışarıda bırak
    fac_host, fac_path = urlparse(base).hostname, urlparse(base).path.rstrip("/")
    if fac_path:  # site.edu.tr/muhendislik-fakultesi/... → yolun altındakiler
        local = [a for a in anchors if urlparse(a["url"]).path.startswith(fac_path + "/")]
    else:  # muhendislik.site.edu.tr → aynı alt alan adı
        local = [a for a in anchors if urlparse(a["url"]).hostname == fac_host]
    # Bölümler ayrı alt alan adlarında olabilir (mf.site → mfcs.site, aerospace.site): yerel bağlantılarda
    # bölüme benzeyen yoksa fakülte sayfasındaki tüm bağlantılar aday olur.
    pool = local if len(_rule_pick(local, DEPT_RX)) >= 2 else anchors
    items = await _llm_pick(pool, "department", _site_name(sel) or unit_url, llm)
    method = "gemini"
    if not items:
        items, method = _rule_pick(pool, DEPT_RX), "kural"
    unit["departments"] = _entry(items, method=method)
    save(store)
    return unit["departments"]


def _container(node, max_up: int = 4):
    """Kişi kartını bulmak için yukarı çık: e-posta ya da fotoğraf içeren en yakın küçük kap."""
    cur = node
    for _ in range(max_up):
        parent = cur.parent
        if parent is None or len(clean(parent.get_all_text(separator=" "))) > 400:
            break
        cur = parent
        if cur.css("a[href^='mailto:']") or cur.css("img"):
            break
    return cur


def _people(sel, base: str) -> list[dict]:
    """Unvanla başlayan kısa metinlerden kişi listesi (ad, unvan, e-posta, fotoğraf, profil bağlantısı)."""
    out, seen = [], set()
    for el in sel.css("h2, h3, h4, h5, h6, a, strong, b, span, p, li, td, div"):
        text = clean(el.get_all_text(separator=" "))
        if not (6 <= len(text) <= 90):
            continue
        title = detect_title(text)
        if not title:
            continue
        name = strip_titles(text)
        name = re.split(r"\s[|,(–-]\s?|\s{2,}|@", name)[0].strip()
        role = ROLE_RX.search(name)
        if role:  # "Serdar Müldür Dekan" → "Serdar Müldür"; görev ayrı tutulur
            name = name[:role.start()].strip()
        words = name.split()
        if not (2 <= len(words) <= 5) or not all(w[:1].isupper() for w in words) or detect_title(name):
            continue
        key = fold(name)
        if key in seen:
            continue
        box = _container(el)
        mail = next((a.attrib.get("href", "")[7:].split("?")[0] for a in box.css("a[href^='mailto:']")), "")
        img = next((urljoin(base, i.attrib.get("src") or i.attrib.get("data-src") or "") for i in box.css("img")
                    if (i.attrib.get("src") or i.attrib.get("data-src"))), "")
        link = next((urljoin(base, a.attrib.get("href", "")) for a in box.css("a[href]")
                     if not (a.attrib.get("href") or "").startswith(("mailto:", "tel:", "#", "javascript:"))), "")
        # Aynı profil bağlantısı + birinin devamı olan ad ("Ahmet Özdi" / "Ahmet Özdi L") aynı kişidir
        if link and any(o["url"] == link and (key.startswith(fold(o["name"])) or fold(o["name"]).startswith(key)) for o in out):
            continue
        seen.add(key)
        out.append({"name": tr_title(name), "title": title, "email": clean(mail), "photo": img, "url": link})
    return out


async def _llm_people(sel, llm) -> list[dict]:
    if llm is None or not llm.available:
        return []
    text = clean(sel.get_all_text(separator=" "))[:12000]
    data = await llm.json(
        "Aşağıdaki akademik kadro sayfası metninden öğretim elemanlarını çıkar. Yalnızca metinde geçen kişileri "
        f"yaz, uydurma.\n\n{text}",
        {"type": "object", "properties": {"people": {"type": "array", "items": {
            "type": "object", "properties": {"name": {"type": "string"}, "title": {"type": "string"}},
            "required": ["name"]}}}, "required": ["people"]}, timeout=60)
    people = []
    for p in (data or {}).get("people") or []:
        name = strip_titles(clean(p.get("name")))
        if name and name_in_text(name, text):
            people.append({"name": tr_title(name), "title": detect_title(p.get("title") or "") or clean(p.get("title")),
                           "email": "", "photo": "", "url": ""})
    return people


async def staff(unit_url: str, llm=None, refresh: bool = False) -> dict:
    domain = registrable(urlparse(unit_url).hostname or "")
    store = load(domain)
    unit = store["units"].setdefault(unit_url, {})
    if not refresh and _fresh(unit.get("staff")):
        return unit["staff"]
    sel, base = await _page(unit_url)
    candidates = [(sel, base)]
    links = [a for a in _anchors(sel, base) if STAFF_RX.search(a["name"]) and not NOISE_RX.search(a["name"])]
    # Birimin altındaki kadro sayfaları öne alınır
    path = urlparse(base).path.rstrip("/")
    links.sort(key=lambda a: (not urlparse(a["url"]).path.startswith(path or "/"),
                              not re.search(r"akademik|academic|[öo][ğg]retim", a["name"], re.I)))
    for res in await asyncio.gather(*(_page(a["url"]) for a in links[:3]), return_exceptions=True):
        if not isinstance(res, Exception):
            candidates.append(res)
    best, best_url = [], base
    for s, u in candidates:
        found = _people(s, u)
        if len(found) > len(best):
            best, best_url = found, u
    method = "kural"
    if len(best) < 2:
        for s, u in candidates[1:] + candidates[:1]:
            found = await _llm_people(s, llm)
            if len(found) > len(best):
                best, best_url, method = found, u, "gemini"
    unit["staff"] = _entry(best, page=best_url, method=method)
    save(store)
    return unit["staff"]


# ------------------------------------------------------------------- birim yayınları
async def _institution(client, domain: str, name: str) -> dict | None:
    pool = {}
    short = re.split(r"\s*[|–—»:]\s+|\s-\s", name or "")[0].strip()  # eski kayıtlarda slogan ekli site adı
    for q in dict.fromkeys(x for x in (short, name, domain.split(".")[0]) if x):
        r = await client.get(f"{OPENALEX}/institutions", params={"search": q, "per-page": 10, **OPENALEX_PARAMS})
        for inst in (r.json().get("results", []) if r.status_code == 200 else []):
            home = registrable(urlparse(inst.get("homepage_url") or "").hostname or "")
            if home == domain:
                pool[inst["id"]] = inst
    if not pool:
        return None
    return max(pool.values(), key=lambda i: (i.get("type") == "education", i.get("works_count") or 0))


async def unit_papers(people: list[dict], domain: str, institution: str = "", per_author: int = 60) -> dict:
    """Birimdeki akademisyenlerin OpenAlex yayınları (hızlı liste). Kişi eşleşmesi ad + kurum ile yapılır."""
    sem = asyncio.Semaphore(6)
    async with httpx.AsyncClient(timeout=30, headers={"User-Agent": USER_AGENT}) as client:
        inst = await _institution(client, domain, institution)
        inst_id = inst["id"].rsplit("/", 1)[-1] if inst else ""

        loose: set[str] = set()

        async def search(name, flt=""):
            params = {"search": name, "per-page": 10, **OPENALEX_PARAMS} | ({"filter": flt} if flt else {})
            async with sem:
                r = await client.get(f"{OPENALEX}/authors", params=params)
            results = r.json().get("results", []) if r.status_code == 200 else []
            return sorted(((name_score(name, a.get("display_name", "")), a.get("works_count", 0), a) for a in results),
                          key=lambda s: (s[0], s[1]), reverse=True)

        async def author(person):
            scored = await search(person["name"], f"affiliations.institution.id:{inst_id}" if inst_id else "")
            if scored and scored[0][0] >= 0.75:
                return scored[0][2]
            if not inst_id:
                return None
            # Kurumda hiç yayını yoksa (önceki kurumlarında yayın yapmış): OpenAlex'te o adla tek yazar varsa kabul,
            # ama "yalnızca adla" işaretlenir. Aynı adlı birden çok yazar varsa (yaygın ad) eşleştirilmez.
            scored = [x for x in await search(person["name"]) if x[0] >= 0.9]
            if len(scored) == 1:
                loose.add(person["name"])
                return scored[0][2]
            return None

        authors = await asyncio.gather(*(author(p) for p in people), return_exceptions=True)
        matched = {}
        for person, a in zip(people, authors):
            if isinstance(a, dict):
                matched[a["id"].rsplit("/", 1)[-1]] = person
        papers: dict[str, dict] = {}
        ids = list(matched)
        select = "id,doi,display_name,publication_year,primary_location,authorships,cited_by_count,type,language"

        async def works(chunk):
            # Bir sayfa en fazla 200 kayıt; sonraki sayfalar page= ile alınır (cursor= anahtarsız 401 döner).
            rows = []
            for page in range(1, 6):
                async with sem:
                    r = await client.get(f"{OPENALEX}/works", params={
                        "filter": f"author.id:{'|'.join(chunk)}", "per-page": 200, "page": page,
                        "sort": "publication_year:desc", "select": select, **OPENALEX_PARAMS})
                batch = (r.json().get("results") or []) if r.status_code == 200 else []
                rows.extend(batch)
                if len(batch) < 200:
                    break
            return rows

        chunks = [ids[i:i + 20] for i in range(0, len(ids), 20)]
        for rows in await asyncio.gather(*(works(c) for c in chunks), return_exceptions=True):
            if isinstance(rows, Exception):
                continue
            for w in rows:
                # OpenAlex bazı yazarlarda kimliği/adı boş (null) döndürür
                aids = [((a.get("author") or {}).get("id") or "").rsplit("/", 1)[-1] for a in w.get("authorships") or []]
                mine = [matched[aid]["name"] for aid in aids if aid in matched]
                if not mine:
                    continue
                key = w["id"]
                loc = w.get("primary_location") or {}
                p = papers.setdefault(key, {
                    "key": key, "title": clean(w.get("display_name")), "year": w.get("publication_year"),
                    "doi": (w.get("doi") or "").replace("https://doi.org/", ""),
                    "venue": clean((loc.get("source") or {}).get("display_name") or ""),
                    "url": w.get("doi") or loc.get("landing_page_url") or w["id"], "type": w.get("type") or "",
                    "citations": w.get("cited_by_count"), "language": w.get("language") or "",
                    "authors": [n for a in w.get("authorships") or [] if (n := (a.get("author") or {}).get("display_name"))][:20],
                    "unit_authors": [], "source": "openalex"})
                p["unit_authors"] = sorted(set(p["unit_authors"]) | set(mine))
    found = {p["name"] for p in matched.values()}
    return {"papers": sorted((p for p in papers.values() if p["title"]),
                             key=lambda p: (-(p["year"] or 0), p["title"])),
            "matched": len(found), "missing": [p["name"] for p in people if p["name"] not in found],
            "loose": sorted(loose & found),
            "institution": inst.get("display_name") if inst else ""}


async def faculty_people(unit_url: str, llm=None, limit: int = 30) -> list[dict]:
    """Fakülte yayınları için: bölümlerin kadrolarını toplar (önbellekli, sınırlı eşzamanlılık)."""
    deps = (await departments(unit_url, llm))["items"][:limit]
    sem = asyncio.Semaphore(3)

    async def one(d):
        async with sem:
            return d, await staff(d["url"], llm)

    people, seen = [], set()
    for res in await asyncio.gather(*(one(d) for d in deps), return_exceptions=True):
        if isinstance(res, Exception):
            continue
        dept, st = res
        for p in st["items"]:
            if fold(p["name"]) not in seen:
                seen.add(fold(p["name"]))
                people.append({**p, "department": dept["name"]})
    if not people:  # bazı fakülteler tüm kadroyu tek sayfada verir
        people = (await staff(unit_url, llm))["items"]
    return people
