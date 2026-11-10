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


# -------------------------------------------------------------------------- YÖK (yeni herkese açık API)
YOK_TITLES = {"PROFESÖR": "Prof. Dr.", "DOÇENT": "Doç. Dr.", "DOKTOR ÖĞRETİM ÜYESİ": "Dr. Öğr. Üyesi",
              "ÖĞRETİM GÖREVLİSİ": "Öğr. Gör.", "ARAŞTIRMA GÖREVLİSİ": "Arş. Gör."}
YOK_PROFILE = "https://akademik.yok.gov.tr/academician-details?authorGuidId="
# Eski (AkademikArama ?authorId=) ve yeni (?authorGuidId=) bağlantılarda aynı 16 haneli kimlik kullanılır
YOK_ID_RE = re.compile(r"author(?:Guid)?Id=([0-9A-Fa-f]{16})")
YOK_PUB_TYPES = {"MAKALE": "article", "BİLDİRİ": "proceedings", "KİTAP": "book"}


def yok_guid(link: str) -> str:
    m = YOK_ID_RE.search(link or "")
    return m.group(1).upper() if m else ""


_TOKEN = re.compile(r"^[A-Za-z0-9_-]{18,}$")  # API'nin şifreli kimlikleri (gösterilmez)


def _ok(value) -> bool:
    text = clean(str(value or ""))
    return bool(text) and text not in ("0", "None") and not (_TOKEN.match(text) and not text.isdigit())


def _cap(text) -> str:
    """Tamamı büyük ya da küçük harfli adları düzeltir; karışık yazılmış ("Prof. Dr.", "IEEE Xplore") olduğu gibi kalır."""
    from .yokdir import _upper_tr
    text = clean(str(text or ""))
    return tr_title(_upper_tr(text)) if text and (text.isupper() or text.islower()) else text


def _tl(period_from, period_to, role="", place="", unit="", note="") -> dict:
    start, end = clean(str(period_from or "")), clean(str(period_to or ""))
    period = f"{start} - {end}" if start and end and start != end else start or end
    return {"period": period, "role": _cap(role), "place": _cap(place), "unit": _cap(unit), "note": clean(note or "")}


def _join(*parts) -> str:
    return " · ".join(clean(str(p)) for p in parts if _ok(p))


def _labels(*parts) -> list[str]:
    return [clean(str(p)) for p in parts if _ok(p)]


def _team(team) -> str:
    if not isinstance(team, list):
        return clean(str(team or ""))
    people = [_cap(" ".join(x for x in (m.get("yazarad"), m.get("yazarsoyad")) if x))
              + (f" ({m['projedekiGoreviAd']})" if m.get("projedekiGoreviAd") else "") for m in team if isinstance(m, dict)]
    lead = [x for x in people if "Yürütücü" in x]
    return ", ".join((lead + [x for x in people if x not in lead])[:6]) + (f" +{len(people) - 6}" if len(people) > 6 else "")


def _units(*parts) -> str:
    return " / ".join(clean(p).strip("/ ") for p in parts if p and clean(p).strip("/ "))


def _generic_row(r: dict) -> dict:
    """Alanları önceden bilinmeyen bölümler (ders, üyelik, sanatsal faaliyet): ad içeren ilk alan başlık olur."""
    vals = {k: v for k, v in r.items() if isinstance(v, (str, int)) and v not in ("", None) and not re.search(r"Id$|Guid|En$", k)}
    title_key = next((k for k in vals if re.search(r"(?i)(adi|ad|baslik|konu)$", k) and isinstance(vals[k], str)
                      and len(vals[k]) > 3 and k != "personelAdiSoyadi"), None)
    title = vals.pop(title_key, "") if title_key else ""
    vals.pop("personelAdiSoyadi", None)
    return {"labels": [], "title": clean(str(title)), "detail": _join(*list(vals.values())[:4]), "extra": ""}


def _yok_profile_of(d: dict) -> dict:
    path = [p for p in (d.get("universiteAd"), d.get("fakulteAd"), d.get("bolumAd")) if p]
    return {"title_raw": clean(d.get("kadroUnvanAdi") or ""), "name": clean(d.get("personelAdiSoyadi") or ""),
            "path": path, "institution": path[0] if path else "", "department": d.get("bolumAd") or (path[-1] if path else ""),
            "field": clean(d.get("bilimAlanAd") or ""), "area": clean(d.get("temelAlanAd") or ""),
            "keywords": [clean(d[k]) for k in ("anahtarkelime1Ad", "anahtarkelime2Ad", "anahtarkelime3Ad") if d.get(k)],
            "orcid": d.get("orcid") or "", "researcher_id": d.get("researcherId") or "", "scopus_id": d.get("scopusId") or ""}


async def _yok_rows(client, path: str, **params) -> list[dict]:
    from . import yokdir
    d = await yokdir.api(client, path, **params)
    if isinstance(d, dict):
        return d.get("data") or []
    return d or []


async def _yok_find(client, name: str, institution: str, emit) -> str:
    """Bağlantı yoksa ad araması: aynı adlı kişiler arasından kurumla eşleşen seçilir."""
    from . import yokdir
    rows = await _yok_rows(client, "/akademisyen/list", page=1, length=60, personelAdiSoyadi=yokdir._upper_tr(clean(name)),
                           personelAdiSoyadi_matchMode="contains")
    inst_f = fold(institution)
    scored = []
    for r in rows:
        score = name_score(name, clean(r.get("personelAdiSoyadi") or ""))
        if score < 0.75:
            continue
        if inst_f and inst_f.split()[0] in fold(r.get("universiteAd") or ""):
            score += 1
        scored.append((score, r.get("authorGuidId") or ""))
    scored.sort(reverse=True)
    if not scored or (institution and scored[0][0] < 1):
        emit(f"YÖK: {len(scored)} aynı adlı akademisyen var, kurumla eşleşen yok; atlandı.")
        return ""
    emit(f"YÖK: {len(scored)} aynı adlı akademisyen arasından kurumla eşleşen seçildi.")
    return scored[0][1]


async def _yok_publications(client, guid: str, profile_url: str, emit) -> list[dict]:
    types = await _yok_rows(client, "/yayin/ana/tur/list")
    wanted = [(t["value"], YOK_PUB_TYPES[t["label"]], t["label"]) for t in types if t.get("label") in YOK_PUB_TYPES]
    lists = await asyncio.gather(*[_yok_rows(client, "/yayin/list", authorGuidId=guid, yayinAnaTurId=v, page=1, length=1000)
                                   for v, _k, _l in wanted], return_exceptions=True)
    out = []
    for (_v, kind, label), rows in zip(wanted, lists):
        if isinstance(rows, BaseException):
            emit(f"YÖK {_cap(label)} okunamadı ({type(rows).__name__}).")
            continue
        for r in rows:
            doi = doi_key(r.get("doi") or "")
            pages = "-".join(x for x in (r.get("ilkSayfa"), r.get("sonSayfa")) if x)
            out.append(record(
                "yok", source_id=str(r.get("yayinId") or ""), title=r.get("yayinAdi") or "", year=r.get("yil"),
                venue=clean(r.get("yayinYeri") or ""), doi=doi, issn=r.get("issn") or "", isbn=r.get("isbn") or "",
                authors=[_cap(a) for a in (r.get("yazarAdi") or "").split(",") if clean(a)],
                url=f"https://doi.org/{doi}" if doi else profile_url, type=kind,
                volume=r.get("cilt") or "", issue=r.get("sayi") or "", pages=pages,
                labels=[x for x in [clean(r.get("yayinTuruAdi") or ""), "Uluslararası" if str(r.get("kapsam")) == "1" else ""] if x]))
        emit(f"YÖK {_cap(label)}: {sum(1 for x in out if x['type'] == kind)} kayıt.")
    return out


async def yok_profile_api(name: str, institution: str, link: str, emit, sections: set[str] | None = None,
                          publications: bool = True) -> dict:
    """YÖK Akademik'in herkese açık JSON API'si: kimlik, görev/öğrenim, bölümler, birlikte çalışılanlar ve yayınlar.

    Tarayıcı ve REA gerekmez; istekler yokdir.api üzerinden en fazla üç eşzamanlı çağrıyla sınırlanır.
    """
    from . import yokdir

    result: dict = {"profile": {}, "records": [], "rea": None}
    want = lambda group: sections is None or group in sections  # noqa: E731
    async with yokdir._client() as client:
        guid = yok_guid(link) or await _yok_find(client, name, institution, emit)
        if not guid:
            return result
        url = YOK_PROFILE + guid
        detail = await yokdir.api(client, "/akademisyen/detay", authorGuidId=guid)
        if not detail:
            emit("YÖK profili bulunamadı (kimlik artık geçerli değil).")
            return result
        prof = _yok_profile_of(detail)
        result.update(profile=prof, profile_url=url)
        emit(f"YÖK profili (API): {prof['title_raw']} · {' / '.join(prof['path'][:3])}"
             + (f" · ORCID {prof['orcid']}" if prof["orcid"] else ""))
        page = {"authorGuidId": guid, "page": 1, "length": 1000}
        jobs = {}
        if want("career"):
            jobs |= {"career": ("/deneyim/akademik/gorev", page), "education": ("/akademisyen/ogrenim/bilgiler", page),
                     "admin": ("/deneyim/idari/gorev", page), "experience": ("/deneyim/universite/disi", page)}
        if want("projects"):
            jobs |= {"projects": ("/proje/list", page), "awards": ("/odul/list", page),
                     "memberships": ("/uyelik/list", page), "art": ("/sanatsal/faaliyet/list", page)}
        if want("courses"):
            jobs["courses"] = ("/ders/list", page)
        if want("theses"):
            jobs["theses"] = (f"/tez/yurt/ici/yonetilen/{guid}", {})
        if want("patents"):
            jobs["patents"] = ("/patent/list", page)
        if want("industry"):
            jobs["collaborators"] = (f"/akademisyen/birlikte/calisanlar/{guid}", {})
        tasks = [_yok_rows(client, path, **params) for path, params in jobs.values()]
        if publications:
            tasks.append(_yok_publications(client, guid, url, emit))
        got = await asyncio.gather(*tasks, return_exceptions=True)
        data = {}
        for key, rows in zip(jobs, got):
            if isinstance(rows, BaseException):
                emit(f"YÖK {key} okunamadı ({type(rows).__name__}).")
            else:
                data[key] = rows
        if publications:
            pubs = got[-1]
            result["records"] = [] if isinstance(pubs, BaseException) else pubs

    sec = {}
    if "admin" in data:
        sec["admin"] = [_tl(r.get("baslangicTarihi"), r.get("bitisTarihi"), r.get("gorevAdi"), r.get("yerAdi") or r.get("unvBirimAdi"),
                            _units(r.get("fakulteBilgisi"), r.get("bolumBilgisi"))) for r in data["admin"]]
    if "experience" in data:
        sec["experience"] = [_tl(r.get("baslangicTarihi"), r.get("bitisTarihi"), r.get("gorevAdi"), r.get("kurulusAdi") or r.get("kurumAdi"),
                                 r.get("isyeriTuruAdi"), r.get("isTanimi")) for r in data["experience"]]
    if "projects" in data:
        sec["projects"] = [{"labels": _labels(r.get("projeTuruAd"), r.get("projeDurumuAd")), "title": clean(r.get("projeAdi") or ""),
                            "detail": _join(f"{r.get('butcesi')} {r.get('paraBirimi')}" if str(r.get("butcesi") or "0") != "0" else "",
                                            _team(r.get("projeEkip"))),
                            "extra": _join(r.get("baslangicTarihi"), r.get("bitisTarihi") or r.get("bitisyil"))} for r in data["projects"]]
    if "awards" in data:
        sec["awards"] = [{"labels": _labels(r.get("turAdi"), r.get("isyeriTuruAdi")), "title": clean(r.get("odulAdi") or ""),
                          "detail": clean(r.get("kurulusAdi") or ""), "extra": _join(r.get("odulTarih"), tr_title(r.get("ulkeAd") or ""))}
                         for r in data["awards"]]
    if "theses" in data:
        sec["theses"] = [{"labels": _labels(r.get("tezTurAd"), r.get("durumAdi")), "title": clean(r.get("tezAdi") or ""),
                          "detail": _cap(r.get("hazAdSoyad") or f"{r.get('hazAd') or ''} {r.get('hazSoyad') or ''}"),
                          "extra": _join(tr_title(r.get("universiteAd") or ""), r.get("yil"))} for r in data["theses"]]
    if "patents" in data:
        sec["patents"] = [{"labels": _labels(r.get("kategoriAd"), r.get("basvuruTuru"), r.get("patentDosyaTipi")),
                           "title": clean(r.get("patentBaslik") or ""), "detail": _join(r.get("patentBulusSahip"), r.get("patentBasvuruSahip")),
                           "extra": _join(r.get("patentNo"), r.get("patentTarih"))} for r in data["patents"]]
    for key in ("courses", "memberships", "art"):
        if key in data:
            sec[key] = [x for x in (_generic_row(r) for r in data[key]) if x["title"] or x["detail"]]
    extra = {"photo": detail.get("authorImage") if str(detail.get("authorImage") or "").startswith("data:image") else "",
             "email": "", "updated": "", "sections": sec}
    if "career" in data:
        extra["career"] = [_tl(r.get("baslangicTarihi"), r.get("bitisTarihi"), YOK_TITLES.get(r.get("kadroUnvanAdi") or "", r.get("kadroUnvanAdi")),
                               r.get("unvBirimAdi"), _units(r.get("fakultebilgisi"), r.get("bolumbilgisi")), r.get("akademikDurumAdi"))
                           for r in data["career"]]
    if "education" in data:
        extra["education"] = [_tl(r.get("baslangicTarihi"), r.get("bitisTarihi"), r.get("programAdi"),
                                  r.get("unvBirimAdi") or r.get("digerUniversite") or r.get("yerAd"),
                                  _units(r.get("fakulteBilgisi"), r.get("bolumBilgisi")), r.get("tezAdi")) for r in data["education"]]
    if "collaborators" in data:
        extra["collaborators"] = [{"yok_id": c.get("authorGuidId") or "", "name": _cap(c.get("personelAdiSoyadi")),
                                   "title": YOK_TITLES.get(c.get("kadroUnvanAdi") or "", tr_title(c.get("kadroUnvanAdi") or "")),
                                   "institution": tr_title(c.get("universiteAd") or ""), "unit": tr_title(_units(c.get("fakulteAd"), c.get("bolumAd"))),
                                   "photo": c.get("authorImage") if str(c.get("authorImage") or "").startswith("data:image") else "",
                                   "url": YOK_PROFILE + (c.get("authorGuidId") or "")} for c in data["collaborators"]][:60]
    counts = ", ".join(f"{k} {len(v)}" for k, v in sec.items())
    emit(f"YÖK profil ayrıntıları: görev {len(extra.get('career', []))}, öğrenim {len(extra.get('education', []))}, "
         f"birlikte çalıştığı {len(extra.get('collaborators', []))} kişi" + (f", {counts}" if counts else "") + ".")
    result["extra"] = extra
    return result


# Eski AkademikArama kayıtları (yok_context taşıyanlar) için künye okuyucu
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


async def yok_works(profile: Profile, log, *, sections: set[str] | None = None, publications: bool = True) -> tuple[list[dict], dict | None]:
    pending: list = []

    def emit(msg: str):
        pending.append(asyncio.ensure_future(log("yok", "running", msg)))

    try:
        res = await yok_profile_api(profile.name or profile.query_name, profile.get("institution", ""),
                                    profile.links.get("yok", ""), emit, sections, publications)
    except httpx.HTTPError as exc:
        emit(f"YÖK'e ulaşılamadı ({type(exc).__name__}).")
        res = {}
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)
    prof = res.get("profile") or {}
    if prof:
        if res.get("profile_url"):
            profile.links["yok"] = res["profile_url"]
        src = profile.links.get("yok") or YOK_PROFILE
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
