"""Seçilen profil bölümlerini ve yayın kaynaklarını kayıpsız yeniler."""
from __future__ import annotations

import asyncio
import copy
import re
import time
from collections import Counter

from . import industry, patents, publication_status, quartiles, trsources, wos, wos_enrichment
from .discover import Fact, Profile, locate
from .dedup import resolve
from .sources import crossref_works, openalex_by_doi, openalex_works, orcid_works, scholar_works, yok_works
from .text import doi_key, fold, title_key

SECTIONS = {"profile", "institution", "publications", "career", "courses", "theses", "projects", "industry", "patents"}
SOURCES = {"yok", "openalex", "crossref", "orcid", "scholar", "trdizin", "openaire", "tez", "wos"}
SOURCE_NAMES = {"yok": "YÖK", "openalex": "OpenAlex", "crossref": "Crossref", "orcid": "ORCID", "scholar": "Google Scholar",
                "trdizin": "TR Dizin", "openaire": "OpenAIRE", "tez": "Tez Merkezi", "wos": "Web of Science"}


def restore_profile(raw: dict) -> Profile:
    p = Profile(query_name=raw.get("query_name") or raw.get("name") or "", name=raw.get("name") or "")
    for key in ("title", "department", "institution", "interests", "bio", "field"):
        if raw.get(key):
            origin = (raw.get("provenance") or {}).get(key) or {}
            p.facts[key] = Fact(copy.deepcopy(raw[key]), origin.get("source", "saved"), origin.get("url", ""))
    p.links = copy.deepcopy(raw.get("links") or {})
    if raw.get("orcid"):
        p.links.setdefault("orcid", raw["orcid"])
    p.source_url, p.listing_url = raw.get("source_url", ""), raw.get("listing_url", "")
    p.found = bool(raw.get("found"))
    p.verification = copy.deepcopy(raw.get("verification") or {})
    p.yok = copy.deepcopy(raw.get("yok") or {})
    return p


def merge_publications(result: dict, incoming: list[dict]):
    """Eski P# kimlikleri, WoS kanıtı, seçilmeyen kaynaklar ve alınan tüm yayınlar korunur."""
    papers = result.setdefault("publications", [])
    max_id = max((int(p["id"][1:]) for p in papers if re.fullmatch(r"P\d+", p.get("id", ""))), default=0)
    for raw in incoming:
        record = copy.deepcopy(raw)
        current, ambiguous = wos_enrichment._match(papers, record, result.get("profile") or {})
        if current is None and not ambiguous:
            # Kaynağın aynı kaydı yazar listesi olmadan döndürmesi ikinci satır yaratmasın.
            matches = [p for p in papers if title_key(record.get("title", ""))
                       and title_key(p.get("title", "")) == title_key(record.get("title", ""))
                       and record.get("year") and p.get("year") == record.get("year")
                       and not (p.get("authors") and record.get("authors"))
                       and wos_enrichment._same_kind(p, record)
                       and set(p.get("sources") or []) & set(record.get("sources") or [])
                       and (p.get("venue") and fold(p["venue"]) == fold(record.get("venue") or "")
                            or p.get("source") == record.get("source") and record.get("source_id")
                            and p.get("source_id") == record["source_id"])
                       and not (doi_key(p.get("doi")) and doi_key(record.get("doi")) and doi_key(p["doi"]) != doi_key(record["doi"]))]
            if len(matches) == 1:
                current = matches[0]
        if ambiguous:
            continue
        if current is None:
            max_id += 1
            record.update(id=f"P{max_id}", runs_seen=1, is_new=True)
            current = record
            papers.append(current)
        else:
            for field in ("doi", "venue", "issn", "abstract", "year", "date", "url", "type", "authors", "yok_context", "orgs", "wos", "jcr"):
                if not current.get(field) and record.get(field):
                    current[field] = record[field]
                    if field == "abstract":
                        current["abstract_source"] = record.get("abstract_source") or record.get("source", "")
                        current["abstract_url"] = record.get("abstract_url") or record.get("url", "")
            current["sources"] = list(dict.fromkeys([*(current.get("sources") or []), *(record.get("sources") or [])]))
            for field in ("labels", "languages", "language_names"):
                current[field] = list(dict.fromkeys([*(current.get(field) or []), *(record.get(field) or [])]))
            variants = current.setdefault("variants", [])
            seen = {(v.get("title"), v.get("source")) for v in variants}
            variants.extend(v for v in record.get("variants") or [] if (v.get("title"), v.get("source")) not in seen)
        source = record.get("source")
        citations = dict(record.get("citations_by_source") or {})
        if source and len(record.get("sources") or [source]) == 1 and isinstance(record.get("citations"), int):
            citations[source] = record["citations"]
        if citations:
            current.setdefault("citations_by_source", {}).update(citations)
            # Diğer kaynakların önceki sayıları da korunur.
            current["citations"] = max(current.get("citations") or 0, *current["citations_by_source"].values())
        current["verified"] = len(current.get("sources") or []) > 1 or bool(current.get("verified"))
    papers.sort(key=lambda p: (-(p.get("year") or 0), p.get("title") or ""))
    counts = Counter(s for p in papers for s in set(p.get("sources") or []))
    result.update(unique_count=len(papers), by_source=dict(counts), raw_count=sum(counts.values()))
    result["languages"] = dict(Counter(l for p in papers for l in p.get("language_names") or []))
    result.setdefault("paper_verification", {}).update(verified=sum(bool(p.get("verified")) for p in papers),
        multi_source=sum(len(p.get("sources") or []) > 1 for p in papers), new=sum(bool(p.get("is_new")) for p in papers))
    result.setdefault("dedup", {}).update(raw=result["raw_count"], unique=len(papers))
    result["summary"] = f"{result['profile'].get('name', '')} için {len(papers)} benzersiz yayın derlendi."
    quartiles.annotate(papers)
    wos.annotate(papers)
    publication_status.annotate(papers)


_NOT_PORTRAIT = re.compile(r"logo|icon|ikon|banner|slider|sprite|favicon|bayrak|flag|footer|header|social|whatsapp|"
                           r"facebook|twitter|instagram|linkedin|youtube|qr|placeholder|default|loading|\.svg(?:\?|$)", re.I)
_PORTRAIT_HINT = re.compile(r"personel|akademik|academic|staff|profil|profile|foto|photo|portre|avatar|uploads?|kadro|team|people", re.I)


# Kişinin profil sayfası olamayacak adresler: tarihli yazılar ve haber/duyuru/etkinlik sayfaları. Kadro listesinde ad
# bazen kişiyle ilgili bir habere bağlanır ("… yüksek lisansını tamamladı"); o sayfa özgeçmiş ya da portre kaynağı değildir.
_NOT_PROFILE = re.compile(r"/(?:19|20)\d{2}/\d{1,2}(?:/|$)|/(?:haber|haberler|duyuru|duyurular|news|announcements?|etkinlik|"
                          r"etkinlikler|events?|blog|basin|press)(?:/|-|$)", re.I)


def _homepage(url: str) -> bool:
    """Adres bir sitenin yalnız ana sayfası mı ("https://www.kurum.edu.tr", ".../", ".../tr", ".../en/index.html")."""
    from urllib.parse import urlsplit
    if not url or not url.startswith(("https://", "http://")):
        return False
    parts = urlsplit(url)
    path = parts.path.strip("/").lower()
    return not parts.query and bool(re.fullmatch(r"(?:(?:tr|en)/?)?(?:(?:index|default|anasayfa|home)(?:\.\w{2,5})?)?", path))


def _profile_like(url: str) -> bool:
    return bool(url) and not _NOT_PROFILE.search(url)


async def _page_info(url: str, name: str) -> dict:
    """Kişinin kurum sayfasından: portre ("photo"), araştırma alanları ("interests"), ofis ("office") ve özgeçmiş
    metni ("bio"). E-posta ve telefon alınmaz.

    Portre: alt/başlık metninde ya da dosya adında kişinin adı geçen görsel; yoksa yolu personel/profil/foto… içeren
    ilk görsel; o da yoksa sayfanın paylaşım görseli. Dosya adı URL kodlamalı ve harfleri ayrık yazılmış olabilir
    ("Serpil%20O%CC%88zer.jpg"): karşılaştırmadan önce çözülür ve birleştirilir. Logo, ikon, bayrak ve afişler elenir."""
    import unicodedata
    from urllib.parse import unquote, urljoin
    from scrapling import Selector
    from .net import fetch_smart
    from .text import clean, name_tokens
    out = {"photo": "", "interests": [], "office": "", "bio": ""}
    try:
        page = await asyncio.wait_for(fetch_smart(url, allow_stealth=False), 20)
    except Exception:  # noqa: BLE001
        return out
    if page.status >= 400 or not page.html:
        return out
    sel = Selector(page.html)
    base = page.url or url
    tokens = [t for t in name_tokens(name) if len(t) > 2]

    def about(text: str) -> bool:
        key = fold(unicodedata.normalize("NFC", unquote(text or "")))
        return bool(tokens) and all(t in key for t in tokens[-2:])  # ad ve soyad birlikte geçmeli
    main = sel.css("main, #wrap, article, #content, .content")
    scope = main[0] if main else sel
    named, hinted = "", ""
    for img in scope.css("img"):
        src = img.attrib.get("data-src") or img.attrib.get("data-lazy-src") or img.attrib.get("src") or ""
        if not src or src.startswith("data:") or _NOT_PORTRAIT.search(unquote(src)):
            continue
        full = urljoin(base, src)
        if about(f"{img.attrib.get('alt', '')} {img.attrib.get('title', '')}") or about(src):
            named = full
            break
        if not hinted and _PORTRAIT_HINT.search(src):
            hinted = full
    # Yalnız kişinin adını taşıyan görsel kabul edilir. Yolundan tahmin edilen görsel ve sayfanın paylaşım görseli
    # çoğu sitede bölüm logosu ya da ilgisiz bir afiş çıkardığı için kullanılmaz.
    out["photo"] = named
    # Metin: ana içerik; etiketli alanlar (araştırma alanları, ofis) ve kalan özgeçmiş paragrafı.
    text = clean(scope.get_all_text(separator=" ", ignore_tags=("script", "style", "nav", "header", "footer")))
    label = r"(?:E-?\s?posta|E-?mail|Tel(?:efon)?|Telefon|Phone|Ofis|Office|Oda|Araştırma Alanları|Research (?:Areas|Interests)|İlgi Alanları)"
    found = re.search(r"(?:Araştırma Alanları|İlgi Alanları|Research (?:Areas|Interests))\s*:?\s*(.{3,400}?)(?=\s" + label + r"\s*:|$)", text, re.I)
    if found:
        out["interests"] = [clean(x) for x in re.split(r"[,;•·|]", found[1]) if 2 < len(clean(x)) < 80][:12]
    office = re.search(r"(?:Ofis|Office|Oda)\s*:\s*(.{3,90}?)(?=\s(?:19|20)\d{2}\s|\s" + label + r"\s*:|$)", text, re.I)
    if office:
        out["office"] = clean(office[1])[:90]
    # Özgeçmiş: etiketli satırlar ve ad çıkarıldıktan sonra kalan en uzun cümle bloğu.
    rest = re.sub(label + r"\s*:\s*.{0,160}?(?=\s" + label + r"\s*:|\s(?:19|20)\d{2}\s|$)", " ", text, flags=re.I)
    start = re.search(r"\b(?:19|20)\d{2}\s+yılında\b|\b(?:received|graduated|born|completed)\b|\b(?:lisans|doktora|mezun)\b", rest, re.I)
    bio = clean(rest[start.start():] if start else "")
    if len(bio) >= 80:
        out["bio"] = bio[:1800]
    return out


async def _site_card(p: Profile) -> dict | None:
    """Kişinin, bölümünün (yoksa fakültesinin) kurum sayfasındaki kadro kartı: {"url", "photo", "title", "unit_url",
    "faculty", "department"}. Fakülte ve bölüm YÖK kadro yolundan alınır. Kayıtlı yolda fakülte yoksa (kayıt YÖK'ün
    Kasım 2026'daki yanıt değişikliğinden önce ya da bölümsüz açılmış) YÖK'te ad aramasıyla bir kez bulunur."""
    from . import directory, main, yokdir
    from .text import name_tokens
    path = [x for x in (p.yok or {}).get("path") or [] if x]
    institution = p.get("institution", "") or (path[0] if path else "")
    faculty = path[1] if len(path) > 1 else ""
    department = path[2] if len(path) > 2 else p.get("department", "")
    if fold(department) == fold(institution):
        department = ""  # bölüm alanına kurum adı yazılmış eski kayıt
    if institution and not faculty and p.name:
        want_name = tuple(sorted(name_tokens(p.name)))
        try:
            rows = await asyncio.wait_for(yokdir.search_people(p.name, limit=20), 25)
        except Exception:  # noqa: BLE001 — YÖK yanıt vermezse kadro listesi araması yapılamaz
            rows = []
        same = [r for r in rows if tuple(sorted(name_tokens(r.get("name") or ""))) == want_name
                and yokdir.uni_id(r.get("university") or "") == yokdir.uni_id(institution) and r.get("faculty")]
        if same:
            faculty = same[0]["faculty"]
            department = department or same[0].get("department") or ""
    if not institution or not faculty:
        return None
    uid = yokdir.uni_id(institution)
    try:
        deps = await main.university_site_departments(uid, faculty)
    except Exception:  # noqa: BLE001 — fakülte sitede bulunamadı
        return None
    dep = max(deps.get("departments") or [], key=lambda x: main._unit_score(department, x["name"]), default=None) if department else None
    urls = []
    if dep and dep.get("url") and main._unit_score(department, dep["name"]) >= 0.6:
        urls.append(dep["url"])
    if deps.get("faculty_url"):
        urls.append(deps["faculty_url"])
    want = tuple(sorted(name_tokens(p.name)))
    for unit_url in dict.fromkeys(urls):
        try:
            people = await asyncio.wait_for(directory.site_people(unit_url), 40)
        except Exception:  # noqa: BLE001
            continue
        for row in people:
            if want and tuple(sorted(name_tokens(row.get("name") or ""))) == want:
                page_url = row.get("url") or ""
                if not _profile_like(page_url):
                    page_url = ""  # kart bir habere bağlanıyor: profil sayfası sayılmaz
                info = await _page_info(page_url, p.name) if page_url else {}
                return {"url": page_url, "photo": row.get("photo") or info.get("photo") or "", "title": row.get("title") or "",
                        "unit_url": unit_url, "faculty": faculty, "department": department,
                        "interests": info.get("interests") or [], "office": info.get("office") or "", "bio": info.get("bio") or ""}
    return None


async def collect(old: dict, sections: set[str], sources: set[str], llm, log) -> dict:
    result = copy.deepcopy(old)
    p = restore_profile(old["profile"])
    warnings, records, source_meta = [], [], {}
    site_card = None

    async def warn(message):
        warnings.append(message)
        await log("publications", "warning", message)

    # Kurum sayfası ayrı bir seçimdir; diğer bölümlerde site keşfi yapılmaz.
    if "institution" in sections:
        url = p.source_url or (old.get("input") or {}).get("url") or p.listing_url
        if _homepage(url):
            # Kayıtlı adres yalnız üniversitenin ana sayfası (profil adla + kurum sitesiyle açılmış, kişinin sayfası hiç
            # bulunmamış): ana sayfadan baştan site taraması yerine kişi, bölümünün kadro listesinde aranır (aşağıda).
            url = ""
        if url and url.startswith(("https://", "http://")) and "akademik.yok.gov.tr" not in url:
            try:
                fresh, report = await asyncio.wait_for(locate(url, p.name, log, llm), 90)
                if fresh.found:
                    for key, fact in fresh.facts.items():
                        if fact.value:
                            p.facts[key] = fact
                    p.links.update(fresh.links)
                    p.source_url, p.listing_url = fresh.source_url or p.source_url, fresh.listing_url or p.listing_url
                    p.found = True
                    p.observations.extend(fresh.observations)
                    result.setdefault("recon", {})["institution_refresh"] = report
                else:
                    await warn("Kurum sayfasında kişi doğrulanamadı; kayıtlı bilgiler korundu.")
            except Exception as exc:
                await warn(f"Kurum sayfası yenilenemedi ({type(exc).__name__}); kayıtlı bilgiler korundu.")
        else:
            # Kayıtlı kurum sayfası yok (isimle / YÖK'ten açılmış profil): kişi, bölümünün sayfasındaki kadro
            # kartlarından ad eşleşmesiyle bulunur; fotoğrafı ve profil sayfası oradan alınır.
            await log("institution", "running", "Kişi, bölümünün kurum sayfasındaki kadro listesinde aranıyor…")
            try:
                site_card = await asyncio.wait_for(_site_card(p), 75)
            except Exception as exc:  # noqa: BLE001
                site_card = None
                await warn(f"Kurum sayfası okunamadı ({type(exc).__name__}).")
            if site_card:
                # Sayfadaki özgeçmiş, profilde özgeçmiş yoksa oraya da yazılır (YÖK alanlarının üzerine yazılmaz).
                if site_card.get("bio") and "bio" not in p.facts:
                    p.set("bio", site_card["bio"], "institution", site_card.get("url") or "")
                if site_card.get("url"):
                    p.source_url = site_card["url"]
                    p.links["institution"] = site_card["url"]
                    try:
                        fresh, report = await asyncio.wait_for(locate(site_card["url"], p.name, log, llm), 75)
                        if fresh.found:
                            for key, fact in fresh.facts.items():
                                if fact.value and key not in p.facts:
                                    p.facts[key] = fact  # YÖK'ten gelen alanların üzerine yazılmaz; eksikler tamamlanır
                            p.observations.extend(fresh.observations)
                            result.setdefault("recon", {})["institution_refresh"] = report
                    except Exception:  # noqa: BLE001 — kart bilgisi yine kaydedilir
                        pass
                await log("institution", "done", "Kurum sayfasında bulundu" + (" · fotoğraf alındı" if site_card.get("photo") else ""))
            else:
                await warn("Kişi, bölümünün kurum sayfasındaki kadro listesinde bulunamadı.")

    if "institution" in sections and p.source_url and not _profile_like(p.source_url):
        # Önceki yenilemede profil sayfası diye bir haber yazısı kaydedilmiş: adres, o sayfadan alınan fotoğraf ve
        # özgeçmiş geri alınır.
        wrong = (old.get("profile") or {}).get("site") or {}
        if wrong.get("bio") and p.get("bio", "") == wrong["bio"]:
            p.facts.pop("bio", None)
        clear_photo = wrong.get("photo") or ""
        p.source_url = ""
        p.links.pop("institution", None)
        site_card = {**{k: v for k, v in (site_card or {}).items() if k in ("title", "unit_url", "faculty", "department")},
                     "url": "", "photo": "", "bio": "", "interests": [], "office": "", "_clear_photo": clear_photo}
    if "institution" in sections and p.source_url and "akademik.yok.gov.tr" not in p.source_url:
        # Sayfa adresi biliniyor (bu yenilemede bulundu ya da önceden kayıtlı): fotoğraf, araştırma alanları, ofis ve
        # özgeçmiş sayfanın kendisinden okunur; önceki kurum sayfası kaydının üzerine eksikler tamamlanır.
        try:
            info = await asyncio.wait_for(_page_info(p.source_url, p.name), 30)
        except Exception:  # noqa: BLE001
            info = {}
        base = {**((old.get("profile") or {}).get("site") or {}), **(site_card or {})}
        base["url"] = base.get("url") or p.source_url
        for key, value in info.items():
            if value:
                base[key] = value  # sayfanın kendisi en güncel kaynaktır: eski (yanlış seçilmiş) fotoğrafın üzerine yazar
        site_card = base
        if site_card.get("bio") and not p.get("bio", ""):
            p.set("bio", site_card["bio"], "institution", site_card["url"], override=True)

    yok_sections = sections - {"institution", "publications"}
    needs_yok = bool(yok_sections) and bool(yok_sections - {"patents"}) or ("publications" in sections and "yok" in sources)
    if "patents" in sections and p.links.get("yok"):
        needs_yok = True
    if needs_yok:
        before_ref = p.yok
        before = copy.deepcopy(before_ref)
        try:
            await log("yok", "running", "YÖK'te seçilen bilgiler yenileniyor…")
            yok_records, _ = await asyncio.wait_for(yok_works(p, log, sections=yok_sections,
                publications="publications" in sections and "yok" in sources), 150)
            fresh = p.yok
            merged = copy.deepcopy(before)
            if fresh is not before_ref:
                for key in ("photo", "email", "updated") if "profile" in sections else ():
                    if fresh.get(key):
                        merged[key] = fresh[key]
                if "career" in sections:
                    for key in ("career", "education"):
                        if key in fresh:
                            merged[key] = fresh[key]
                if "industry" in sections and "collaborators" in fresh:
                    merged["collaborators"] = fresh["collaborators"]
                merged.setdefault("sections", {}).update(fresh.get("sections") or {})
                # Ekstra bilgi: temel alan, bilim alanı, anahtar kelimeler ve dizin kimlikleri her YÖK yanıtında gelir.
                for key in ("area", "field", "keywords", "scopus_id", "researcher_id"):
                    if fresh.get(key):
                        merged[key] = fresh[key]
            else:
                await warn("YÖK profil yanıtı alınamadı; kayıtlı bilgiler korundu.")
            p.yok = merged
            records.extend(yok_records)
        except Exception as exc:
            p.yok = before
            await warn(f"YÖK yenilenemedi ({type(exc).__name__}); kayıtlı bilgiler korundu.")

    jobs = {}
    selected = sources if "publications" in sections else set()
    providers = {"openalex": openalex_works, "crossref": crossref_works, "orcid": orcid_works,
                 "scholar": scholar_works, "trdizin": trsources.trdizin_works,
                 "openaire": trsources.openaire_works, "tez": trsources.tez_works}
    extra = ({"tez"} if "theses" in sections else set()) | ({"trdizin"} if "projects" in sections else set())
    # TR kaynakları setdefault kullanır; yalnız yeni veri dönerse eskisini değiştir.
    old_tez, old_projects = p.yok.pop("tez_merkezi", None), p.yok.pop("tr_projects", None)
    for source in sorted(selected | extra):
        if source in providers:
            jobs[source] = asyncio.wait_for(providers[source](p, log), 180)
    if jobs:
        await log("publications", "running", "Seçilen kaynaklar: " + ", ".join(SOURCE_NAMES[s] for s in jobs))
        values = await asyncio.gather(*jobs.values(), return_exceptions=True)
        for source, value in zip(jobs, values):
            if isinstance(value, BaseException):
                await warn(f"{SOURCE_NAMES[source]} yenilenemedi ({type(value).__name__}); kayıtlı yayınlar korundu.")
                continue
            rows, meta = value if isinstance(value, tuple) else (value, None)
            if source in selected:
                records.extend(rows)
            if meta:
                source_meta[source] = meta
    if "theses" not in sections or "tez_merkezi" not in p.yok:
        if old_tez is not None:
            p.yok["tez_merkezi"] = old_tez
        else:
            p.yok.pop("tez_merkezi", None)
    if "projects" not in sections or "tr_projects" not in p.yok:
        if old_projects is not None:
            p.yok["tr_projects"] = old_projects
        else:
            p.yok.pop("tr_projects", None)
    if "openalex" in selected and records:
        try:
            records.extend(await asyncio.wait_for(openalex_by_doi(records, p.name, log), 60))
        except Exception as exc:
            await warn(f"OpenAlex DOI tamamlama yapılamadı ({type(exc).__name__}).")

    fresh = p.to_dict()
    if {"profile", "institution"} & sections:
        result["profile"] = {**old["profile"], **fresh}
        if site_card:
            # Kurum sayfası bilgisi: profil sayfası, karttaki unvan ve fotoğraf. Fotoğraf adres olarak saklanır;
            # YÖK fotoğrafı yoksa /api/jobs/{id}/photo bunu sunar.
            stale_photo = site_card.pop("_clear_photo", "")
            result["profile"]["site"] = {**site_card, "checked_at": time.time()}
            if stale_photo and result["profile"].get("photo") == stale_photo:
                result["profile"]["photo"] = None  # haber sayfasından alınmış logo/afiş: profil fotoğrafı olmaktan çıkar
            if not site_card.get("bio") and result["profile"].get("bio") and not fresh.get("bio"):
                result["profile"]["bio"] = ""
            if site_card.get("photo") and not str(result["profile"].get("photo") or "").startswith("data:"):
                result["profile"]["photo"] = site_card["photo"]
        # Eski doğrulama etiketini değişen bir alana taşımayız.
        verification = result["profile"].setdefault("verification", {})
        for field in ("title", "department", "institution", "interests"):
            if fresh.get(field) != old["profile"].get(field):
                verification.pop(field, None)
    else:
        result["profile"]["yok"] = p.yok
        # Kaynağın doğruladığı kimlik diğer yayın kaynaklarına aktarılır, kullanıcı alanları aynı kalır.
        if not result["profile"].get("orcid") and fresh.get("orcid"):
            result["profile"]["orcid"] = fresh["orcid"]
            result["profile"].setdefault("links", {})["orcid"] = fresh["orcid"]
    if "publications" in sections and records:
        await log("dedup", "running", "Yeni kayıtlar mevcut yayınlarla birleştiriliyor…")
        incoming, _ = await resolve(records, p.name, llm, log)
        for paper in incoming:
            titles = {title_key(v.get("title", "")) for v in paper.get("variants") or []}
            paper["citations_by_source"] = {record["source"]: record["citations"] for record in records
                if isinstance(record.get("citations"), int) and (
                    doi_key(paper.get("doi")) and doi_key(paper.get("doi")) == doi_key(record.get("doi")) or
                    title_key(record.get("title", "")) in titles and record.get("year") == paper.get("year"))}
        merge_publications(result, incoming)
        result["analysis"] = {"mode": "pending", "summary": "", "areas": [], "methods": [], "timeline": []}
    result.setdefault("recon", {}).setdefault("sources_meta", {}).update(source_meta)
    if "industry" in sections:
        result["industry"] = industry.collaborations(result.get("publications") or [], result["profile"])
        result["industry_v"] = industry.VERSION
    if "patents" in sections:
        if patents.enabled():
            try:
                places = [p.get("institution")] + [c.get("place") for c in p.yok.get("career") or []]
                result["patents"] = await asyncio.wait_for(patents.person_patents(p.name, places), 180)
                result["patents_v"] = patents.VERSION
            except Exception as exc:
                await warn(f"Patentler yenilenemedi ({type(exc).__name__}); kayıtlı bilgiler korundu.")
        else:
            await warn("EPO bağlantısı tanımlı değil; YÖK patent bilgileri kullanıldı.")
    result["refresh_preferences"] = {"sections": sorted(sections), "sources": sorted(sources)}
    result["refresh_report"] = {"at": time.time(), "sections": sorted(sections), "sources": sorted(selected), "warnings": warnings}
    return result
