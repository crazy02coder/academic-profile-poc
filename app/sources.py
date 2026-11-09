"""Yayın kaynakları: OpenAlex → Crossref → ORCID → YÖK Akademik → Google Scholar.

Her kaynak aynı normalize kayıt şemasını üretir:
  {source, source_id, title, year, doi, venue, authors[], abstract, url, citations, type, labels[]}
"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import quote, urljoin, urlparse

import httpx

from . import rea, recipes
from .config import CONTACT_MAIL, OPENALEX_PARAMS, USER_AGENT
from .discover import Profile, registrable, tr_title
from .net import fetch_smart, parse, wall_reason
from .text import clean, doi_key, fold, name_score, title_key

OPENALEX = "https://api.openalex.org"
CROSSREF = "https://api.crossref.org"
ORCID_API = "https://pub.orcid.org/v3.0"
YOK = "https://akademik.yok.gov.tr/AkademikArama/"


def record(source: str, **kw) -> dict:
    base = {"source": source, "source_id": "", "title": "", "year": None, "doi": "", "venue": "", "authors": [],
            "abstract": "", "url": "", "citations": None, "type": "", "labels": []}
    base.update({k: v for k, v in kw.items() if v not in (None, "")})
    base["title"] = clean(base["title"])
    base["doi"] = doi_key(base["doi"])
    if base["doi"] and not base["url"]:
        base["url"] = f"https://doi.org/{base['doi']}"
    try:
        base["year"] = int(base["year"]) if base["year"] else None
    except (TypeError, ValueError):
        base["year"] = None
    base["date"] = pub_date(base.get("date"), base["year"])
    if base.get("abstract"):
        base["abstract_source"] = source
        base["abstract_url"] = base["url"]
    return base


def pub_date(value, year=None) -> str:
    """Yayın tarihini 'YYYY-MM-DD' ya da 'YYYY-MM' biçimine indirger; yalnız yıl varsa boş döner.

    Kaynağın verdiği tarihin yılı kaydın yılıyla uyuşmuyorsa (ör. çevrimiçi önce yayımlanma) tarih kullanılmaz.
    """
    if isinstance(value, (list, tuple)):
        parts = [int(x) for x in value if str(x).isdigit()]
    else:
        parts = [int(x) for x in re.findall(r"\d+", str(value or ""))[:3]]
    if len(parts) < 2 or not 1000 < parts[0] < 3000 or not 1 <= parts[1] <= 12 or (year and parts[0] != year):
        return ""
    if len(parts) > 2 and 1 <= parts[2] <= 31:
        return f"{parts[0]:04d}-{parts[1]:02d}-{parts[2]:02d}"
    return f"{parts[0]:04d}-{parts[1]:02d}"


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=25, follow_redirects=True,
                             headers={"User-Agent": USER_AGENT, "Accept": "application/json"})


# --------------------------------------------------------------------- OpenAlex
def _abstract(inv: dict | None) -> str:
    if not inv:
        return ""
    words = sorted((pos, w) for w, positions in inv.items() for pos in positions)
    return " ".join(w for _, w in words)


async def openalex_institution(client, profile: Profile) -> dict | None:
    """Kurumu OpenAlex'te bulur. Aynı alan adını paylaşan araştırma merkezleri/hastaneler yerine
    ana üniversite seçilir: tür 'education' ve eser sayısı en büyük olan."""
    name = profile.get("institution")
    domain = registrable(urlparse(profile.source_url or profile.listing_url).hostname or "")
    queries = [q for q in (name, re.sub(r"(?i)üniversitesi", "University", name or ""), domain.split(".")[0] if domain else "") if q]
    pool: dict[str, dict] = {}
    for q in dict.fromkeys(queries):
        r = await client.get(f"{OPENALEX}/institutions", params={"search": q, "per-page": 10, **OPENALEX_PARAMS})
        if r.status_code != 200:
            continue
        for inst in r.json().get("results", []):
            home = registrable(urlparse(inst.get("homepage_url") or "").hostname or "")
            names = fold(inst.get("display_name", "")) + " " + " ".join(fold(a) for a in inst.get("display_name_alternatives") or [])
            key_tokens = [t for t in fold(name or "").split() if t not in ("universitesi", "university", "teknik", "technical")]
            if (domain and home == domain) or (key_tokens and all(t in names for t in key_tokens)):
                pool[inst["id"]] = inst
    if not pool:
        return None
    return max(pool.values(), key=lambda i: (i.get("type") == "education",
                                            "univers" in fold(i.get("display_name", "")),
                                            i.get("works_count") or 0))


async def openalex_author(client, profile: Profile, log) -> dict | None:
    orcid = profile.links.get("orcid")
    if orcid:
        r = await client.get(f"{OPENALEX}/authors", params={"filter": f"orcid:{orcid}", **OPENALEX_PARAMS})
        res = r.json().get("results", []) if r.status_code == 200 else []
        if res:
            await log("publications", "running", f"OpenAlex: ORCID {orcid} ile yazar kesinleştirildi → {res[0]['id'].rsplit('/', 1)[-1]}.")
            return res[0]
    inst = await openalex_institution(client, profile)
    if inst:
        profile.set("institution", tr_title(inst["display_name"]) if inst["display_name"].isupper() else inst["display_name"],
                    "openalex", inst["id"])
    params = {"search": profile.name or profile.query_name, "per-page": 25, **OPENALEX_PARAMS}
    if inst:
        params["filter"] = f"affiliations.institution.id:{inst['id'].rsplit('/', 1)[-1]}"
    r = await client.get(f"{OPENALEX}/authors", params=params)
    results = r.json().get("results", []) if r.status_code == 200 else []
    scored = [(name_score(profile.query_name, a.get("display_name", "")), a.get("works_count", 0), a) for a in results]
    scored = [s for s in scored if s[0] >= 0.75]
    if not scored:
        # Filtresiz ara; kurumu yazarın bağlı olduğu kurumlar içinde doğrula (TR/EN ad farkına dayanıklı)
        params.pop("filter", None)
        r = await client.get(f"{OPENALEX}/authors", params=params)
        inst_tokens = [t for t in fold(profile.get("institution", "")).split()
                       if t not in ("universitesi", "university", "teknik", "technical")]
        for a in (r.json().get("results", []) if r.status_code == 200 else []):
            affs = " ".join(fold(i.get("display_name", "")) for i in (a.get("last_known_institutions") or []))
            affs += " " + " ".join(fold((x.get("institution") or {}).get("display_name", "")) for x in a.get("affiliations") or [])
            same_inst = (inst and inst["id"] in str(a.get("last_known_institutions")) + str(a.get("affiliations"))) or \
                (inst_tokens and all(t in affs for t in inst_tokens))
            sc = name_score(profile.query_name, a.get("display_name", ""))
            if sc >= 0.75 and same_inst:
                scored.append((sc, a.get("works_count", 0), a))
    if not scored:
        await log("publications", "running", "OpenAlex: ad + kurum ile güvenilir yazar eşleşmesi yok.")
        return None
    scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
    best = scored[0][2]
    note = f"kurum filtresi {inst['display_name']}" if inst else "kurum filtresi yok"
    await log("publications", "running", f"OpenAlex: ad + {note} ile yazar seçildi ({best['display_name']}, "
                                         f"{best.get('works_count', 0)} eser).")
    return best


OPENALEX_SELECT = ("id,doi,display_name,publication_year,publication_date,primary_location,authorships,abstract_inverted_index,"
                   "cited_by_count,language,type,topics")


def _openalex_record(w: dict, is_self) -> dict:
    """OpenAlex eserini ortak kayda çevirir; `is_self(authorship)` kişinin kendisini ortak kurum listesinden ayırır."""
    loc = w.get("primary_location") or {}
    return record(
        "openalex", source_id=w["id"], title=w.get("display_name"), year=w.get("publication_year"),
        date=w.get("publication_date"),
        doi=w.get("doi"), venue=((loc.get("source") or {}).get("display_name")), issn=(loc.get("source") or {}).get("issn"),
        authors=[n for a in w.get("authorships") or [] if (n := (a.get("author") or {}).get("display_name"))][:25],
        abstract=_abstract(w.get("abstract_inverted_index")), url=w.get("doi") or loc.get("landing_page_url") or w["id"],
        citations=w.get("cited_by_count"), type=w.get("type"),
        labels=[t["display_name"] for t in (w.get("topics") or [])[:3]],
        orgs=[{"name": i.get("display_name"), "type": i.get("type"), "country": i.get("country_code")}
              for a in w.get("authorships") or [] if not is_self(a)
              for i in a.get("institutions") or [] if i.get("type") == "company" and i.get("display_name")])


async def openalex_by_doi(records: list[dict], name: str, log) -> list[dict]:
    """Diğer kaynakların bulduğu DOI'leri OpenAlex'te doğrudan arar.

    Yazar kaydı bulunamayan ya da bölünmüş kişilerde atıf, özet ve tarih böylece kaybolmaz. Eser, yalnız yazarları
    arasında bu kişi varsa eklenir; başka kaynaktaki yanlış bir DOI kişiye yayın olarak yazılmasın.
    """
    have = {r["doi"] for r in records if r["source"] == "openalex" and r.get("doi")}
    # "|" filtre ayırıcısı, "," filtre sonu olduğu için bu karakterleri içeren DOI'ler sorgulanamaz
    dois = sorted({r["doi"] for r in records if r.get("doi") and r["doi"] not in have and not re.search(r"[|,]", r["doi"])})
    if not dois:
        return []
    is_self = lambda a: name_score(name, (a.get("author") or {}).get("display_name") or "") >= 0.75  # noqa: E731
    out, other, failed = [], 0, 0
    sem = asyncio.Semaphore(4)  # 50'lik gruplar aynı anda, en çok 4 istek

    async def batch_get(client, batch):
        async with sem:
            return batch, await client.get(f"{OPENALEX}/works", params={
                "filter": "doi:" + "|".join(batch), "per-page": 50, "select": OPENALEX_SELECT, **OPENALEX_PARAMS})

    async with _client() as client:
        replies = await asyncio.gather(*(batch_get(client, dois[i:i + 50]) for i in range(0, len(dois), 50)),
                                       return_exceptions=True)
        for reply in replies:
            if isinstance(reply, Exception):
                failed += 50
                continue
            batch, r = reply
            if r.status_code != 200:
                failed += len(batch)
                continue
            for w in r.json().get("results", []):
                if any(is_self(a) for a in w.get("authorships") or []):
                    out.append(_openalex_record(w, is_self))
                else:
                    other += 1
    msg = f"OpenAlex DOI ile tamamlama: {len(dois)} DOI arandı, {len(out)} eser eklendi"
    if other:
        msg += f", {other} eserin yazarlarında bu kişi görünmediği için eklenmedi"
    if failed:
        msg += f", {failed} DOI sorgulanamadı"
    await log("publications", "running", msg + ".")
    return out


async def openalex_works(profile: Profile, log) -> tuple[list[dict], dict | None]:
    async with _client() as client:
        author = await openalex_author(client, profile, log)
        if not author:
            return [], None
        aid = author["id"].rsplit("/", 1)[-1]
        if author.get("orcid"):
            oid = author["orcid"].rsplit("/", 1)[-1]
            profile.links.setdefault("orcid", oid)
            profile.observe("orcid", oid, "openalex", author["id"])
        for inst in author.get("last_known_institutions") or []:
            profile.observe("institution", inst.get("display_name"), "openalex", author["id"])
        out, page, more = [], 1, True
        # cursor= ile sayfalama anahtarsız 401 döner; page= anahtarsız çalışır.
        while more and len(out) < 400:
            r = await client.get(f"{OPENALEX}/works", params={
                "filter": f"author.id:{aid}", "per-page": 200, "page": page, "select": OPENALEX_SELECT,
                "sort": "publication_year:desc", **OPENALEX_PARAMS})
            if r.status_code != 200:
                break
            data = r.json()
            for w in data.get("results", []):
                out.append(_openalex_record(w, lambda a: ((a.get("author") or {}).get("id") or "").endswith(aid)))
            more = len(data.get("results") or []) == 200
            page += 1
        topics = author.get("topics") or author.get("x_concepts") or []
        meta = {"id": aid, "display_name": author.get("display_name"), "works_count": author.get("works_count"),
                "cited_by_count": author.get("cited_by_count"),
                "h_index": (author.get("summary_stats") or {}).get("h_index"),
                "topics": [t.get("display_name") for t in topics[:8]],
                "institutions": [i.get("display_name") for i in author.get("last_known_institutions") or []]}
        return out, meta


# --------------------------------------------------------------------- Crossref
async def crossref_works(profile: Profile, log) -> list[dict]:
    orcid = profile.links.get("orcid")
    inst = profile.get("institution", "")
    select = "DOI,title,author,published,issued,container-title,ISSN,abstract,URL,is-referenced-by-count,type"
    params = {"rows": 200, "select": select, "mailto": CONTACT_MAIL}
    if orcid:
        params["filter"] = f"orcid:{orcid}"
    elif inst:
        params.update({"query.author": profile.name or profile.query_name, "query.affiliation": inst, "rows": 80})
    else:
        return []
    async with _client() as client:
        r = await client.get(f"{CROSSREF}/works", params=params)
        r.raise_for_status()
        items = r.json().get("message", {}).get("items", [])
    out = []
    inst_tokens = [t for t in fold(inst).split() if len(t) > 3 and t not in ("universitesi", "university")]
    for it in items:
        authors = it.get("author") or []
        mine = None
        for a in authors:
            full = f"{a.get('given', '')} {a.get('family', '')}"
            if orcid and orcid in (a.get("ORCID") or ""):
                mine = a
                break
            if name_score(profile.query_name, full) >= 0.85:
                affs = fold(" ".join(x.get("name", "") for x in a.get("affiliation") or []))
                if orcid or (inst_tokens and all(t in affs for t in inst_tokens)):
                    mine = a
                    break
        if not mine:
            continue
        date = (it.get("published") or it.get("issued") or {}).get("date-parts", [[None]])[0]
        out.append(record(
            "crossref", source_id=it.get("DOI"), title=(it.get("title") or [""])[0], year=date[0] if date else None, date=date,
            doi=it.get("DOI"), venue=(it.get("container-title") or [""])[0], issn=it.get("ISSN"),
            authors=[clean(f"{a.get('given', '')} {a.get('family', '')}") for a in authors][:25],
            abstract=re.sub(r"<[^>]+>", " ", it.get("abstract") or ""), url=it.get("URL"),
            citations=it.get("is-referenced-by-count"), type=it.get("type")))
    mode = "ORCID filtresi" if orcid else "ad + kurum (aynı yazar nesnesinde)"
    await log("publications", "running", f"Crossref ({mode}): {len(out)} doğrulanmış kayıt.")
    return out


# ------------------------------------------------------------------------ ORCID
async def orcid_works(profile: Profile, log) -> list[dict]:
    orcid = profile.links.get("orcid")
    if not orcid:
        return []
    async with _client() as client:
        r = await client.get(f"{ORCID_API}/{orcid}/works")
        if r.status_code != 200:
            return []
        groups = r.json().get("group", [])
    out = []
    for g in groups:
        s = (g.get("work-summary") or [{}])[0]
        ids = (s.get("external-ids") or {}).get("external-id") or []
        doi = next((i.get("external-id-value") for i in ids if i.get("external-id-type") == "doi"), "")
        out.append(record(
            "orcid", source_id=str(s.get("put-code")), title=((s.get("title") or {}).get("title") or {}).get("value"),
            year=(((s.get("publication-date") or {}).get("year")) or {}).get("value"), doi=doi,
            date=[((s.get("publication-date") or {}).get(k) or {}).get("value") for k in ("year", "month", "day")],
            venue=(s.get("journal-title") or {}).get("value"), url=(s.get("url") or {}).get("value"),
            type=s.get("type")))
    await log("publications", "running", f"ORCID public API: {len(out)} eser.")
    return out


# ----------------------------------------------------------------------- Scholar
def _scholar_rows(sel) -> list[dict]:
    rows = []
    for tr in sel.css("tr.gsc_a_tr"):
        a = tr.css("a.gsc_a_at")
        if not a:
            continue
        grays = tr.css("div.gs_gray")
        authors = clean(grays[0].get_all_text()) if grays else ""
        venue = clean(grays[1].get_all_text()) if len(grays) > 1 else ""
        cites = clean(tr.css("a.gsc_a_ac::text").get() or "")
        year = clean(tr.css("span.gsc_a_h::text").get() or tr.css(".gsc_a_y span::text").get() or "")
        href = a[0].attrib.get("href", "")
        rows.append(record(
            "scholar", source_id=href, title=a[0].get_all_text(), year=year if year.isdigit() else None,
            venue=re.sub(r",?\s*\d{4}$", "", venue), authors=[clean(x) for x in authors.split(",") if clean(x)],
            url=urljoin("https://scholar.google.com", href) if href else "",
            citations=int(cites) if cites.isdigit() else None))
    return rows


async def scholar_works(profile: Profile, log) -> tuple[list[dict], dict | None]:
    link = profile.links.get("scholar", "")
    m = re.search(r"user=([\w-]{12})", link)
    if not m:
        # Profil linki yoksa: Scholar arama sayfasında 'User profiles for' kutusu (best-effort)
        q = f'author:"{profile.name or profile.query_name}" {profile.get("institution", "")}'.strip()
        try:
            page = await fetch_smart(f"https://scholar.google.com/scholar?hl=en&q={quote(q)}")
            if wall_reason(page.status, page.html):
                raise RuntimeError("wall")
            for a in page.selector.css('a[href*="citations?user="]'):
                if name_score(profile.query_name, a.get_all_text()) >= 0.75:
                    m = re.search(r"user=([\w-]{12})", a.attrib.get("href", ""))
                    break
        except Exception:  # noqa: BLE001
            m = None
        if not m:
            return await scholar_search_works(profile, log)
    uid = m.group(1)
    out: list[dict] = []
    meta = None
    for start in range(0, 400, 100):
        url = f"https://scholar.google.com/citations?user={uid}&hl=en&cstart={start}&pagesize=100&sortby=pubdate"
        try:
            page = await fetch_smart(url, log=lambda msg: log("publications", "running", f"Scholar: {msg}"))
        except Exception:  # noqa: BLE001
            break
        if wall_reason(page.status, page.html):
            await log("publications", "running", "Scholar bot korumasına takıldı; sessizce atlandı, OpenAlex kullanıldı.")
            break
        sel = page.selector
        if meta is None:
            stats = [clean(x) for x in sel.css("#gsc_rsb_st td.gsc_rsb_std::text").getall()]
            meta = {"id": uid, "name": clean(sel.css("#gsc_prf_in::text").get() or ""),
                    "affiliation": clean(sel.css(".gsc_prf_il::text").get() or ""),
                    "interests": [clean(a.get_all_text()) for a in sel.css("#gsc_prf_int a")],
                    "citations": int(stats[0]) if stats and stats[0].isdigit() else None,
                    "h_index": int(stats[2]) if len(stats) > 2 and stats[2].isdigit() else None,
                    "via": page.via}
            if meta["name"] and name_score(profile.query_name, meta["name"]) < 0.6:
                await log("publications", "warning", f"Scholar profil adı uyuşmuyor ({meta['name']}); atlandı.")
                return [], None
        rows = _scholar_rows(sel)
        out.extend(rows)
        if len(rows) < 100:
            break
    if meta:
        await log("publications", "running", f"Google Scholar [{meta['via']}]: {len(out)} yayın, "
                                             f"{meta.get('citations') or '?'} atıf, h-index {meta.get('h_index') or '?'}.")
    return out, meta


def _scholar_result_rows(sel, profile: Profile) -> list[dict]:
    """Scholar arama sonuç sayfası (gs_ri blokları). Yazar satırında kişinin soyadı ve
    ad baş harfi yoksa sonuç alınmaz (aynı soyadlı başka kişilerin yayınları karışmasın)."""
    tokens = fold(profile.query_name).split()
    surname, initial = (tokens[-1], tokens[0][:1]) if tokens else ("", "")
    out = []
    for ri in sel.css("div.gs_ri"):
        a = ri.css("h3.gs_rt a")
        title = clean((a[0] if a else ri.css("h3.gs_rt")[0] if ri.css("h3.gs_rt") else ri).get_all_text(separator=" "))
        title = re.sub(r"^\[(PDF|HTML|BOOK|B|CITATION|C)\]\s*", "", title)
        line = clean(ri.css("div.gs_a")[0].get_all_text(separator=" ")) if ri.css("div.gs_a") else ""
        authors_part = line.split(" - ")[0]
        folded = fold(authors_part)
        if not surname or surname not in folded.split() or not re.search(rf"\b{initial}", folded):
            continue
        year = re.search(r"\b(19|20)\d{2}\b", line)
        venue = line.split(" - ")[1] if " - " in line else ""
        cited = re.search(r"Cited by (\d+)", clean(ri.get_all_text(separator=" ")))
        out.append(record("scholar", source_id=(a[0].attrib.get("href", "") if a else title[:80]), title=title,
                          year=year.group(0) if year else None, venue=re.sub(r",?\s*(19|20)\d{2}.*$", "", venue),
                          authors=[clean(x) for x in authors_part.split(",") if clean(x)],
                          url=a[0].attrib.get("href", "") if a else "", citations=int(cited.group(1)) if cited else None))
    return out


async def scholar_search_works(profile: Profile, log, pages: int = 3) -> tuple[list[dict], dict | None]:
    """Profil yoksa: Scholar arama sonuçları Scrapling StealthyFetcher ile (best-effort)."""
    q = f'author:"{profile.query_name}"'
    out: list[dict] = []
    for start in range(0, pages * 10, 10):
        url = f"https://scholar.google.com/scholar?hl=en&as_sdt=0,5&q={quote(q)}&start={start}"
        try:
            page = await fetch_smart(url)
        except Exception:  # noqa: BLE001
            break
        if wall_reason(page.status, page.html) or "accounts.google.com" in page.url:
            await log("publications", "running", "Scholar bot korumasına takıldı; sessizce atlandı, OpenAlex kullanıldı.")
            break
        rows = _scholar_result_rows(page.selector, profile)
        out.extend(rows)
        if len(page.selector.css("div.gs_ri")) < 10:
            break
    if not out:
        await log("publications", "running", "Scholar profili yok ve arama sonucu eşleşmedi; OpenAlex kullanıldı.")
        return [], None
    meta = {"id": None, "mode": "search", "name": profile.query_name, "affiliation": "", "interests": [],
            "citations": sum(r["citations"] or 0 for r in out), "h_index": None, "via": "scrapling.stealthy"}
    await log("publications", "running", f"Google Scholar (profil yok → arama sonuçları, stealth): {len(out)} yayın, "
                                         f"bu sonuçlarda toplam {meta['citations']} atıf.")
    return out, meta


# -------------------------------------------------------------------------- YÖK
def _yok_parse_profile(sel) -> dict:
    row = sel.css("#authorlistTb tr")
    if not row:
        return {}
    td = row[0]
    title = clean(td.css("h6::text").get() or "")
    name = clean(td.css("h4::text").get() or "")
    full = clean(td.get_all_text(separator=" "))
    path_m = re.search(r"([A-ZÇĞİÖŞÜ0-9 .'’\-]+ÜNİVERSİTESİ[^@]*?)/\s*(?:[A-ZÇĞİÖŞÜa-zçğıöşü ]+Temel Alanı|$)", full)
    path = [p.strip() for p in (path_m.group(1) if path_m else "").split("/") if p.strip()]
    if path:  # bazı sonuç düzenlerinde kurumun önüne kimlik no, unvan ve ad yapışıyor → yalnızca kurum adı kalsın
        m = re.search(r"((?:[A-ZÇĞİÖŞÜ.'’\-]+\s+){0,4}(?:TEKNİK\s+)?ÜNİVERSİTESİ)$", path[0])
        head = path[0]
        for junk in [title, name] + list(YOK_TITLES):
            if junk:
                head = head.replace(junk, " ")
        head = re.sub(r"^\s*\d+\s*", "", re.sub(r"\s+", " ", head)).strip()
        path[0] = head or (m.group(1) if m else path[0])
    labels = [clean(x) for x in td.css("span.label::text").getall()]
    tail = full.split(labels[-1], 1)[-1] if labels else ""
    tail = re.split(r"\S+\[at\]\S+", tail)[0]
    keywords = [clean(k) for k in re.split(r"[,;]", tail) if 2 < len(clean(k)) < 60]
    orcid = re.search(r"ORCID:\s*(\d{4}-\d{4}-\d{4}-\d{3}[\dX])", sel.get_all_text(separator=" "))
    dept = next((p for p in path if re.search(r"BÖLÜMÜ|ANABİLİM|PROGRAM|PR\.", p)), path[-1] if path else "")
    return {"title_raw": title, "name": name, "path": path, "institution": path[0] if path else "",
            "department": dept, "field": labels[1] if len(labels) > 1 else (labels[0] if labels else ""),
            "keywords": keywords, "orcid": orcid.group(1) if orcid else ""}


YOK_TITLES = {"PROFESÖR": "Prof. Dr.", "DOÇENT": "Doç. Dr.", "DOKTOR ÖĞRETİM ÜYESİ": "Dr. Öğr. Üyesi",
              "ÖĞRETİM GÖREVLİSİ": "Öğr. Gör.", "ARAŞTIRMA GÖREVLİSİ": "Arş. Gör."}

# YÖK profil menüsündeki yayın dışı bölümler → sonuçtaki anahtar
YOK_SECTIONS = {"Projeler": "projects", "Dersler": "courses", "Yönetilen Tezler": "theses", "Ödüller": "awards",
                "Patentler": "patents", "Üyelikler": "memberships", "Sanatsal faaliyetler": "art",
                "İdari Görevler": "admin", "Üniversite Dışı Deneyim": "experience"}
_NODE_RE = re.compile(r"graph\.addNode\('([^']+)',\s*\{url\s*:\s*'([^']*)',\s*name:\s*'([^']*)'"
                      r"(?:,\s*unvan:\s*'([^']*)')?(?:,\s*universite:\s*'([^']*)')?")


def _text_of(node, css: str) -> str:
    found = node.css(css)
    return clean(" ".join(x.get_all_text(separator=" ") for x in found)) if found else ""


def _yok_timelines(sel) -> dict[str, list[dict]]:
    """`ul.timeline` listeleri (görev, öğrenim, idari görev): başlık → [dönem, rol, kurum, birim, not]."""
    out = {}
    for ul in sel.css("ul.timeline"):
        heading, period, items = "", "", []
        for li in ul.css("li"):
            if "time-label" in (li.attrib.get("class") or ""):
                text = clean(li.get_all_text(separator=" "))
                if re.search(r"\d{4}", text):
                    period = text
                elif text:
                    heading = text
                continue
            if not li.css(".timeline-item"):
                continue
            items.append({"period": period, "role": _text_of(li, ".timeline-footer"),
                          "place": tr_title(_text_of(li, ".timeline-item h4")),
                          "unit": tr_title(_text_of(li, ".timeline-body h5")),
                          "note": _text_of(li, ".timeline-body h6")})
        if items:
            out[heading or f"liste{len(out) + 1}"] = items
    return out


def _yok_section(sel) -> list[dict]:
    """Bölüm sayfaları üç düzenden birini kullanır: sekmeli tablo, zaman çizelgesi ya da liste satırı."""
    rows = []
    for panel in sel.css(".panel-group .panel"):
        group = _text_of(panel, ".panel-title")
        heads = [clean(th.get_all_text(separator=" ")) for th in panel.css("thead th")]
        for tr in panel.css("tbody tr"):
            cells = [clean(td.get_all_text(separator=" ")) for td in tr.css("td")]
            row = {"group": group, **dict(zip(heads, cells))}
            link = tr.css("a[href^='http']")
            if link:
                row["url"] = link[0].attrib.get("href", "")
            rows.append(row)
    if rows:
        return rows
    timelines = _yok_timelines(sel)
    if timelines:
        return [item for items in timelines.values() for item in items]
    # Proje (ve benzeri) sayfalarının güncel düzeni: .projectmain kartları
    for block in sel.css(".projectmain"):
        title = _text_of(block, ".baslika")
        if not title:
            continue
        labels = [clean(x.get_all_text(separator=" ")) for x in block.css(".projectType .label")]
        people, roles = [], []
        for a in block.css("a.popoverData"):
            people.append(tr_title(clean(a.get_all_text())))
            info = re.sub(r"<br\s*/?>", " · ", a.attrib.get("data-content") or "", flags=re.I)
            info = clean(re.sub(r"<[^>]+>", "", info)).strip(" ·")
            roles.append(re.sub(r"Üniversite:\s*(.+)$", lambda m: "Üniversite: " + tr_title(m.group(1)), info))
        type_text = _text_of(block, ".projectType")
        for label in labels:
            type_text = type_text.replace(label, "", 1)
        parent = block.parent
        topic = _text_of(parent, ".collapse p") if parent is not None else ""
        rows.append({"labels": [x for x in labels if x], "title": title,
                     "detail": " · ".join(x for x in [", ".join(people[:6]), roles[0] if roles else ""] if x),
                     "extra": " · ".join(x for x in [clean(type_text).strip(" ,"), f"Konu: {topic}" if topic else ""] if x)})
    if rows:
        return rows
    for r in sel.css(".listrow"):
        rows.append({"labels": [clean(x.get_all_text(separator=" ")) for x in r.css(".listRowType .label")],
                     "title": _text_of(r, ".listRowTitle"), "detail": _text_of(r, ".listRowAuthor"),
                     "extra": _text_of(r, ".listRowExtra, .listRowDescription")})
    return [r for r in rows if r["title"] or r["detail"]]


def _yok_collaborators(html: str, self_id: str) -> list[dict]:
    out = []
    for aid, photo, name, title, unit in _NODE_RE.findall(html):
        if aid == self_id:
            continue
        path = [p.strip() for p in unit.split("/") if p.strip()]
        out.append({"yok_id": aid, "name": tr_title(name), "title": YOK_TITLES.get(title, tr_title(title)),
                    "institution": tr_title(path[0]) if path else "", "unit": tr_title(" / ".join(path[1:3])),
                    "photo": photo if photo.startswith("data:image") else "",
                    "url": f"{YOK}AkademisyenGorevOgrenimBilgileri?islem=direct&authorId={aid}"})
    return out[:60]


def _yok_extra(bridge, page, link: str, emit, sections: set[str] | None = None) -> dict:
    """Profilin yayın dışı her şeyi: fotoğraf, e-posta, görev/öğrenim, bölümler ve birlikte çalıştığı kişiler."""
    photo = next((img.attrib.get("src", "") for img in page.css("img.img-circle")
                  if (img.attrib.get("src") or "").startswith("data:image")), "")
    mail = next((a.attrib.get("href", "")[7:] for a in page.css("#authorlistTb a[href^='mailto:']")), "")
    updated = re.search(r"Son güncelleme:\s*([\d.]+)", page.get_all_text(separator=" "))
    timelines = _yok_timelines(page)
    extra = {"photo": photo, "email": clean(mail), "updated": updated.group(1) if updated else "",
             "career": next((v for k, v in timelines.items() if "Görev" in k), []),
             "education": next((v for k, v in timelines.items() if "Öğrenim" in k), []),
             "sections": {}, "collaborators": []}
    self_id = (re.search(r"authorId=([A-Z0-9]+)", link) or [None, ""])[1]
    if sections is None or "industry" in sections:
        try:  # graf sayfası oturumdaki son profile göre oluşur
            graph = bridge.fetch(urljoin(YOK, "view/viewAuthorGraphs.jsp"), network_idle=False)
            extra["collaborators"] = _yok_collaborators(graph.html_content or "", self_id)
        except Exception as exc:  # noqa: BLE001
            extra.pop("collaborators", None)
            emit(f"YÖK birlikte çalıştığı kişiler okunamadı ({type(exc).__name__}).")
    else:
        extra.pop("collaborators", None)
    menu = {clean(a.get_all_text()): urljoin(YOK, a.attrib.get("href", "")) for a in page.css("a[href]")}
    for label, key in YOK_SECTIONS.items():
        group = "career" if key in {"admin", "experience"} else "projects" if key in {"projects", "awards", "memberships", "art"} else key
        if sections is not None and group not in sections:
            continue
        if label not in menu:
            continue
        try:
            section_page = bridge.fetch(menu[label], network_idle=False)
            rows = _yok_section(section_page)
        except Exception as exc:  # noqa: BLE001
            emit(f"YÖK {label} okunamadı ({type(exc).__name__}).")
            continue
        explicitly_empty = re.search(r"kayit (?:bulunamadi|bulunmamaktadir|yok)", fold(section_page.get_all_text()))
        if rows or sections is not None and explicitly_empty:
            extra["sections"][key] = rows
    counts = ", ".join(f"{label} {len(extra['sections'][key])}" for label, key in YOK_SECTIONS.items()
                       if key in extra["sections"])
    emit(f"YÖK profil ayrıntıları: görev {len(extra['career'])}, öğrenim {len(extra['education'])}, "
         f"birlikte çalıştığı {len(extra.get('collaborators', []))} kişi" + (f", {counts}" if counts else "") + ".")
    if sections is not None and "career" not in sections:
        extra.pop("career", None)
        extra.pop("education", None)
    return extra


def _yok_pubs(sel, kind: str, profile_url: str = "") -> list[dict]:
    out = []
    pane = sel.css("#all tbody.searchable > tr") or sel.css("tbody.searchable > tr")
    for tr in pane:
        a = tr.css(".baslika a")
        if not a:
            continue
        cell = clean(tr.get_all_text(separator=" "))
        venue = re.search(r"Yayın Yeri\s*:\s*(.*?)\s*,\s*(\d{4})", cell)
        year = re.search(r",\s*((?:19|20)\d{2})\b", cell)
        doi = tr.css('a[href*="doi.org"]::attr(href)').get() or ""
        out.append(record(
            "yok", source_id=a[0].attrib.get("href", ""), title=a[0].get_all_text(),
            year=year.group(1) if year else None, venue=venue.group(1) if venue else "",
            authors=[tr_title(clean(x.get_all_text())) for x in tr.css("a.popoverData")], doi=doi,
            url=doi or urljoin(YOK + "view/", a[0].attrib.get("href", "")), type=kind,
            labels=[clean(x) for x in tr.css("span.label::text").getall() if clean(x)],
            yok_context={"profile_url": profile_url, "kind": kind} if profile_url else {}))
    return out


def yok_detail_sync(paper: dict, profile_url: str, emit) -> dict:
    """Eski şifreli ayrıntı URL'si yerine profil → güncel liste → aynı oturumda AJAX."""
    from .rea import StealthBridge
    from urllib.parse import parse_qs

    context = paper.get("yok_context") or {}
    profile_url = context.get("profile_url") or profile_url
    target = urlparse(profile_url or "")
    out = {"final_url": profile_url, "source_label": "YÖK profiline git", "access_status": "unavailable"}
    if target.scheme != "https" or target.hostname != "akademik.yok.gov.tr" or \
            not target.path.endswith("/AkademisyenGorevOgrenimBilgileri") or not parse_qs(target.query).get("authorId"):
        out["access_note"] = "YÖK ayrıntısı için akademisyenin profil bağlantısı bulunamadı; eski ayrıntı bağlantısı yeniden kullanılmadı."
        emit(out["access_note"])
        return out

    expected = {title_key(paper["title"])} | {title_key(v["title"]) for v in paper.get("variants", [])}
    kind = context.get("kind") or paper.get("type") or "article"
    labels = {"article": "Makaleler", "proceedings": "Bildiriler", "book": "Kitaplar"}
    label = labels.get(kind, "Makaleler")
    with StealthBridge() as bridge:
        emit("YÖK: akademisyen profili açılıyor; yayın listesi ve ayrıntı aynı oturumda okunacak.")
        profile = bridge.fetch(profile_url, network_idle=False)
        listing_url = next((urljoin(YOK, a.attrib.get("href", "")) for a in profile.css("a")
                            if "AkademisyenYayinBilgileri" in a.attrib.get("href", "")
                            and clean(a.get_all_text()) == label), "")
        if not listing_url or urlparse(listing_url).hostname != target.hostname:
            out["access_note"] = "YÖK profilindeki yayın listesine ulaşılamadı; oturum veya erişim hatası olabilir."
            emit(out["access_note"])
            return out
        box = {}

        def read_detail(page):
            try:
                rows = _yok_pubs(parse(page.content(), page.url), kind, profile_url)
                matches = [r for r in rows if title_key(r["title"]) in expected
                           and (not paper.get("year") or not r.get("year") or paper["year"] == r["year"])]
                if len(matches) != 1:
                    box["error"] = "Yayın güncel YÖK listesinde tek bir kayıtla eşleştirilemedi."
                    return
                row = matches[0]
                detail_url = urljoin(YOK + "view/", row["source_id"])
                if urlparse(detail_url).hostname != target.hostname:
                    box["error"] = "YÖK ayrıntı bağlantısı beklenen alan adına ait değil."
                    return
                response = page.evaluate("""async (url) => {
                    const controller = new AbortController();
                    const deadline = setTimeout(() => controller.abort(), 30000);
                    try {
                        const response = await fetch(url, {
                            credentials: 'same-origin', cache: 'no-store', signal: controller.signal,
                            headers: {'X-Requested-With': 'XMLHttpRequest'}
                        });
                        return {status: response.status, html: await response.text(), url: response.url};
                    } finally { clearTimeout(deadline); }
                }""", detail_url)
                box.update(row=row, **response)
            except Exception as exc:  # Scrapling page_action hatalarını kendi içinde yakalar.
                box["error"] = f"YÖK ayrıntısı okunamadı ({type(exc).__name__})."

        bridge.fetch(listing_url, page_action=read_detail, network_idle=False)
        html = box.get("html", "")
        if box.get("error") or not html:
            out["access_note"] = box.get("error") or "YÖK ayrıntı isteği boş cevap döndürdü."
            emit(out["access_note"])
            return out
        sel = parse(html, box.get("url") or listing_url)
        text = clean(sel.get_all_text(separator=" "))
        failed = box.get("error") or (f"YÖK HTTP {box['status']} döndürdü." if box.get("status", 0) >= 400 else "")
        if not failed and any(marker in fold(text) for marker in ("istediginiz isleme cevap veremiyoruz",
                                                                  "istek oturum zaman", "session expired")):
            failed = "YÖK ayrıntı isteği oturum/zaman aşımı hatası döndürdü."
        if failed or not text:
            out["access_note"] = failed or "YÖK ayrıntı isteği boş cevap döndürdü."
            emit(out["access_note"])
            return out

        field_names = r"Ad[ıi]|Yazar(?:\(lar\))?|Kapsam|Hakem|[İI]ndeks\s+t[üu]r[üu]|T[üu]r|Yay[ıi]n\s+Yeri|Y[ıi]l|ISSN|ISBN|DOI|[ÖO]zet|Abstract"

        def field(label_pattern):
            match = re.search(rf"(?:^|\s)(?:{label_pattern})\s*:\s*(.*?)(?=\s+(?:{field_names})\s*:|"
                              rf"\s+(?:IEEE|ACM|APA|Chicago|MLA|BibTeX)\b|$)", text, re.I)
            return clean(match.group(1)) if match else ""

        title = field(r"Ad[ıi]")
        if title_key(title) not in expected:
            out["access_note"] = "YÖK yanıtında bu yayının başlığı doğrulanamadı; içerik künye veya özet olarak kullanılmadı."
            emit(out["access_note"])
            return out
        row = box["row"]
        out.update(title=title, authors=[clean(a.get_all_text()) for a in sel.css('a[href*="authorId="]')]
                   or row["authors"], journal=field(r"Yay[ıi]n\s+Yeri") or row["venue"],
                   date=field(r"Y[ıi]l") or str(row.get("year") or ""), abstract=field(r"[ÖO]zet|Abstract"),
                   via="scrapling.stealthy.yok-session", access_status="metadata_only")
        out["bibliography"] = {label: value for label, pattern in (
            ("Kapsam", r"Kapsam"), ("Hakem", r"Hakem"), ("İndeks türü", r"[İI]ndeks\s+t[üu]r[üu]"),
            ("Tür", r"T[üu]r"), ("ISSN", r"ISSN"), ("ISBN", r"ISBN")) if (value := field(pattern))}
        emit("YÖK yayın künyesi aynı oturumdaki güncel ayrıntı isteğinden alındı.")
    return out


def yok_sync(name: str, institution: str, link: str, emit, sections: set[str] | None = None, publications: bool = True) -> dict:
    """Scrapling stealth tarayıcı + REA CDP köprüsü ile YÖK Akademik.

    `emit(msg)` iş parçacığından güvenli log fonksiyonudur.
    """
    from .rea import StealthBridge

    result: dict = {"profile": {}, "records": [], "rea": None}
    with StealthBridge() as bridge:
        if not link:
            store = recipes.load("yok.gov.tr")
            recipe = store["replay"].get("yok_search")
            home = bridge.fetch(YOK)
            emit(f"YÖK ana sayfası Scrapling stealth ile açıldı (HTTP {home.status}); düz istemciler 418 alıyor.")
            dom = None
            if recipe:
                box: dict = {}

                def action(page):
                    box.update(recipes.replay_in_browser(page, recipe, name))
                    return page

                try:
                    bridge.fetch(YOK, page_action=action)
                except Exception as exc:  # noqa: BLE001
                    box["error"] = type(exc).__name__
                if box.get("status") == 200 and "Akademisyenler" in box.get("text", ""):
                    dom = parse(box["text"], box["url"])
                    recipe["hits"] = recipe.get("hits", 0) + 1
                    recipes.event(store, "replay_ok", f"POST {recipe['url']}", elapsed=box.get("elapsed"))
                    emit(f"REA tarifi (öğrenildi {recipe['learned_at']}) stealth bağlamında tekrar oynatıldı: "
                         f"{recipe['method']} {recipe['url']} → {box.get('elapsed')} sn; REA gözlemine gerek kalmadı.")
                    result["rea"] = {"method": recipe["method"], "url": recipe["url"], "body": "(tarif)",
                                     "replayed": True, "elapsed": box.get("elapsed")}
                else:
                    recipe["failures"] = recipe.get("failures", 0) + 1
                    recipes.event(store, "replay_failed", f"{recipe['url']}: {box.get('status') or box.get('error')}")
                    emit("DEĞİŞİKLİK: YÖK arama tarifi artık çalışmıyor → REA formu yeniden gözlemleyecek.")
            if dom is None and rea.available():
                cap = bridge.observe(YOK, [
                    {"step_id": "fill", "action": "fill", "locator": {"kind": "css", "selector": "#aramaTerim"},
                     "value": {"source": "literal", "value": name}, "timeout_ms": 8000},
                    {"step_id": "submit", "action": "press", "locator": {"kind": "css", "selector": "#aramaTerim"},
                     "key": "Enter", "timeout_ms": 8000},
                    {"step_id": "settle", "action": "wait_for_timeout", "duration_ms": 3000},
                ])
                hidden = next((t for t in cap.documents if t.method == "POST"), None)
                if hidden:
                    emit(f"REA arama formunun gizli isteğini çözdü: POST {hidden.url} "
                         f"(gövde alanları: {', '.join(k.split('=')[0] for k in (hidden.request_body or '').split('&')[:4])}…)")
                    result["rea"] = {"method": "POST", "url": hidden.url, "body": (hidden.request_body or "")[:300],
                                     "evidence_id": cap.evidence_id, "requests": len(cap.transactions)}
                learned = recipes.learn_replay(cap, name, "yok_search")
                if learned:
                    store["replay"]["yok_search"] = learned
                    recipes.event(store, "relearned" if recipe else "learned", f"POST {learned['url']}",
                                  evidence_id=cap.evidence_id)
                    emit("Tarif kaydedildi: sonraki aramalarda bu istek REA'sız, doğrudan tekrar oynatılacak.")
                dom = parse(cap.dom, cap.final_url or YOK) if cap.dom else None
            recipes.save(store)
            if dom is None:
                emit("REA yok veya gözlem başarısız; YÖK araması atlandı.")
                return result
            list_link = next((urljoin(YOK, a.attrib.get("href", "")) for a in dom.css("a")
                              if "Akademisyenler" in a.get_all_text()), None)
            if not list_link:
                emit("YÖK: akademisyen sonucu yok.")
                return result
            listing = bridge.fetch(list_link)
            best, best_score = None, 0.0
            inst_f = fold(institution)
            def row_name(tr):  # isim <h4> içinde doğrudan ya da bir <a> içinde olabilir
                h = tr.css("h4")
                return clean(h[0].get_all_text(separator=" ")) if h else ""

            for tr in listing.css("tr"):
                text = clean(tr.get_all_text(separator=" "))
                h4 = row_name(tr)
                score = name_score(name, h4 or text)
                if score < 0.75:
                    continue
                if inst_f and inst_f.split()[0] in fold(text):
                    score += 1
                href = next((a.attrib.get("href") for a in tr.css("a") if re.search(r"authorId|AkademisyenGorevOgrenim",
                                                                                   a.attrib.get("href") or "")), None)
                if href and score > best_score:
                    best, best_score = urljoin(YOK, href), score
            n = len([1 for tr in listing.css("tr") if name_score(name, row_name(tr)) >= 0.75])
            if not best or (institution and best_score < 1):
                emit(f"YÖK: {n} aynı adlı akademisyen var, kurumla eşleşen yok; atlandı.")
                return result
            emit(f"YÖK: {n} aynı adlı akademisyen arasından kurumla eşleşen seçildi.")
            link = best
        page = bridge.fetch(link)
        prof = _yok_parse_profile(page)
        if not prof:
            emit("YÖK profil sayfası ayrıştırılamadı.")
            return result
        result["profile"] = prof
        result["profile_url"] = link
        emit(f"YÖK profili: {prof.get('title_raw')} · {' / '.join(prof.get('path', [])[:3])}"
             + (f" · ORCID {prof['orcid']}" if prof.get("orcid") else ""))
        result["extra"] = _yok_extra(bridge, page, link, emit, sections)
        pub_links = [(clean(a.get_all_text()), urljoin(YOK, a.attrib.get("href", ""))) for a in page.css("a")
                     if "AkademisyenYayinBilgileri" in (a.attrib.get("href") or "")]
        for label, url in pub_links:
            if not publications:
                break
            if label not in ("Makaleler", "Bildiriler", "Kitaplar"):
                continue
            pubs = _yok_pubs(bridge.fetch(url), {"Makaleler": "article", "Bildiriler": "proceedings",
                                                 "Kitaplar": "book"}[label], link)
            emit(f"YÖK {label}: {len(pubs)} kayıt.")
            result["records"].extend(pubs)
    return result


async def yok_works(profile: Profile, log, *, sections: set[str] | None = None, publications: bool = True) -> tuple[list[dict], dict | None]:
    loop = asyncio.get_running_loop()

    def emit(msg: str):
        asyncio.run_coroutine_threadsafe(log("yok", "running", msg), loop)

    res = await asyncio.to_thread(yok_sync, profile.name or profile.query_name, profile.get("institution", ""),
                                  profile.links.get("yok", ""), emit, sections, publications)
    prof = res.get("profile") or {}
    if prof:
        if res.get("profile_url"):
            profile.links["yok"] = res["profile_url"]
        src = profile.links.get("yok") or YOK
        profile.set("title", YOK_TITLES.get(prof.get("title_raw", ""), tr_title(prof.get("title_raw", ""))), "yok", src,
                    override=True)
        if prof.get("institution"):
            profile.set("institution", tr_title(prof["institution"]), "yok", src, override=True)
        if prof.get("department"):
            profile.set("department", tr_title(re.sub(r"\s*PR\.$", " Programı", prof["department"])), "yok", src,
                        override=True)
        if prof.get("field"):
            profile.set("field", prof["field"], "yok", src, override=sections is not None and "profile" in sections)
        if prof.get("keywords"):
            profile.set("interests", prof["keywords"], "yok", src, override=sections is not None and "profile" in sections)
        if prof.get("orcid"):
            profile.links.setdefault("orcid", prof["orcid"])
            profile.observe("orcid", prof["orcid"], "yok", src)
        profile.yok = res.get("extra") or {}
        profile.found = True
    return res.get("records", []), res.get("rea")
