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


async def collect(old: dict, sections: set[str], sources: set[str], llm, log) -> dict:
    result = copy.deepcopy(old)
    p = restore_profile(old["profile"])
    warnings, records, source_meta = [], [], {}

    async def warn(message):
        warnings.append(message)
        await log("publications", "warning", message)

    # Kurum sayfası ayrı bir seçimdir; diğer bölümlerde site keşfi yapılmaz.
    if "institution" in sections:
        url = p.source_url or (old.get("input") or {}).get("url") or p.listing_url
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
            await warn("Bu profilde kurum sayfası bağlantısı bulunmuyor.")

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
