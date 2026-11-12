"""Danışman bulucu: konuya göre son yıllarda yayın yapan, tez yönetmiş ve aktif Türkiye'deki akademisyenler.

Sıralama OpenAlex yayınlarından; unvan ve yönetilen tez sayısı ilk adaylar için YÖK Akademik'in açık API'sinden (önbellekli).
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import math
import time
from datetime import date
import httpx
from .config import ROOT, OPENALEX_PARAMS
from .library_common import atomic_json, clean_title
from .text import fold
from . import reading, yokdir, history

CACHE = ROOT / "data/cache/advisors"
YEARS = 5
ADVISOR_TITLES = ("prof", "doç", "dr. öğr", "doktor öğretim")


def _cached(key: str, ttl: float):
    try:
        value = json.loads((CACHE / f"{key}.json").read_text())
        return value["v"] if time.time() - value["at"] < ttl else None
    except (OSError, ValueError, KeyError):
        return None


def _store(key: str, value):
    atomic_json(CACHE / f"{key}.json", {"at": time.time(), "v": value})


def _tokens(name: str) -> set[str]:
    return {{"technical": "teknik", "technology": "teknoloji"}.get(t, t) for t in fold(name).split() if t not in ("universitesi", "university", "of", "the", "ve")}


async def _institution(client, uni: dict) -> dict | None:
    key = "inst-" + hashlib.sha1(uni["id"].encode()).hexdigest()[:12]
    hit = _cached(key, 90 * 86400)
    if hit is not None:
        return hit or None
    want, best = _tokens(uni["name"]), None
    for q in dict.fromkeys(x for x in (uni.get("name_en"), uni["name"]) if x):
        r = await client.get(reading.OPENALEX + "/institutions", params=OPENALEX_PARAMS | {"search": q, "filter": "country_code:TR", "per_page": 10})
        if r.status_code != 200:
            continue
        for inst in r.json().get("results", []):
            names = [inst.get("display_name", ""), *(inst.get("display_name_alternatives") or [])]
            en = _tokens(uni.get("name_en") or "")
            if any(_tokens(n) == want or (en and _tokens(n) == en) for n in names):
                if not best or (inst.get("works_count") or 0) > (best.get("works_count") or 0):
                    best = inst
        if best:
            break
    value = {"id": best["id"].rsplit("/", 1)[-1], "name": best["display_name"]} if best else {}
    _store(key, value)
    return value or None


async def _works(client, query: str, inst_id: str) -> list[dict]:
    since = f"{date.today().year - YEARS}-01-01"
    flt = f"{reading.TR},from_publication_date:{since}" + (f",authorships.institutions.id:{inst_id}" if inst_id else "")
    r = await client.get(reading.OPENALEX + "/works", params=OPENALEX_PARAMS | {
        "search": query, "filter": flt, "per_page": 200, "select": "id,title,publication_year,cited_by_count,doi,authorships,primary_topic"})
    r.raise_for_status()
    return r.json().get("results", [])


async def _yok(name: str, institution: str) -> dict:
    """Unvan, birim ve yönetilen tez sayısı (kişi başına en fazla iki hafif API çağrısı, 30 gün önbellek)."""
    key = "yok-" + hashlib.sha1(f"{fold(name)}|{fold(institution)}".encode()).hexdigest()[:16]
    hit = _cached(key, 30 * 86400)
    if hit is not None:
        return hit
    out: dict = {}
    try:
        people = await yokdir.search_people(name, 20)
        want = _tokens(institution)
        same = [p for p in people if fold(p["name"]) == fold(name)]
        match = next((p for p in same if not want or want <= _tokens(p.get("university", "")) or _tokens(p.get("university", "")) <= want), None)
        if not match and len(same) == 1:  # kurum adı İngilizce geldiyse: aynı adlı tek kişi
            match = same[0]
        if match:
            out = {k: match.get(k) or "" for k in ("title", "university", "faculty", "department", "yok_id", "url", "field")}
            out["keywords"] = match.get("keywords") or []
            if match.get("yok_id"):
                async with yokdir._client() as client:
                    rows = await yokdir.api(client, f"/tez/yurt/ici/yonetilen/{match['yok_id']}") or []
                done = [r for r in rows if "devam" not in fold(r.get("durumAdi") or "")]
                out["theses"] = len(done)
                out["theses_phd"] = sum(1 for r in done if "doktora" in fold(r.get("tezTurAd") or ""))
                out["theses_recent"] = sum(1 for r in done if str(r.get("yil") or "0")[:4].isdigit() and int(str(r.get("yil"))[:4]) >= date.today().year - YEARS)
                out["thesis_titles"] = [clean_title(r.get("tezAdi") or "") for r in sorted(done, key=lambda r: str(r.get("yil") or ""), reverse=True)[:3]]
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        return {}
    _store(key, out)
    return out


async def find(q: str, uni_id: str = "", mode: str = "tez", english: str = "") -> dict:
    q = " ".join(q.split())[:400]
    uni = None
    if uni_id:
        uni = next((u for u in await yokdir.university_list() if u["id"] == uni_id), None)
    key = "find-" + hashlib.sha1(f"{fold(q)}|{uni_id}|{mode}".encode()).hexdigest()[:16]
    hit = _cached(key, 6 * 3600)
    if hit is not None:
        return hit
    async with reading._client() as client:
        inst = await _institution(client, uni) if uni else None
        if uni and not inst:
            return {"items": [], "query": q, "english": english, "university": uni["name"], "message": "Bu üniversite OpenAlex'te eşleştirilemedi; filtresiz dene."}
        results = await asyncio.gather(*(_works(client, text, inst["id"] if inst else "") for text in dict.fromkeys(x for x in (english, q) if x)), return_exceptions=True)
    works, seen = [], set()
    for rows in results:
        if isinstance(rows, Exception):
            continue
        for w in rows:
            if w["id"] not in seen:
                seen.add(w["id"]); works.append(w)
    if not works and all(isinstance(r, Exception) for r in results):
        raise httpx.HTTPError("OpenAlex")
    now, people = date.today().year, {}
    for rank, w in enumerate(works):
        year = w.get("publication_year") or 0
        for a in w.get("authorships") or []:
            insts = [i for i in a.get("institutions") or [] if i.get("country_code") == "TR" and (not inst or i.get("id", "").endswith(inst["id"]))]
            author = a.get("author") or {}
            if not insts or not author.get("id"):
                continue
            p = people.setdefault(author["id"], {"id": author["id"].rsplit("/", 1)[-1], "name": author.get("display_name") or "", "orcid": (author.get("orcid") or "").rsplit("/", 1)[-1],
                                                "institutions": {}, "works": [], "score": 0.0, "citations": 0, "last": 0, "topics": {}})
            p["institutions"][insts[0].get("display_name", "")] = max(p["institutions"].get(insts[0].get("display_name", ""), 0), year)
            p["works"].append({"title": clean_title(w.get("title") or ""), "year": year, "citations": w.get("cited_by_count") or 0, "doi": (w.get("doi") or "").replace("https://doi.org/", "")})
            # yakın tarih, konuya yakınlık (arama sırası) ve atıf birlikte
            p["score"] += (1.0 + .25 * max(0, year - (now - YEARS))) * (1.2 if rank < 40 else 1.0) + .15 * math.log1p(w.get("cited_by_count") or 0)
            p["citations"] += w.get("cited_by_count") or 0; p["last"] = max(p["last"], year)
            topic = (w.get("primary_topic") or {}).get("display_name")
            if topic: p["topics"][topic] = p["topics"].get(topic, 0) + 1
    ranked = sorted(people.values(), key=lambda p: -p["score"])[:40]
    chats = {(fold(c.get("name") or "")): c for c in history.list_all()}
    top = ranked[:12]
    enriched = await asyncio.gather(*(_yok(p["name"], max(p["institutions"], key=p["institutions"].get)) for p in top), return_exceptions=True)
    items = []
    for i, p in enumerate(ranked):
        institution = max(p["institutions"], key=p["institutions"].get)
        yok = enriched[i] if i < len(top) and isinstance(enriched[i], dict) else {}
        chat = chats.get(fold(p["name"]))
        title = yok.get("title") or (chat or {}).get("title") or ""
        active = p["last"] >= now - 2
        score = p["score"] * (1.15 if active else .7) + min(6, (yok.get("theses_recent") or 0) * .8) + (1.5 if yok.get("theses") else 0)
        eligible = any(t in title.lower() for t in ADVISOR_TITLES) if title else None
        if mode == "2209" and eligible is False:
            continue
        works_ = sorted(p["works"], key=lambda w: (-w["year"], -w["citations"]))
        items.append({"openalex": p["id"], "name": yok and p["name"] or p["name"], "orcid": p["orcid"], "institution": yok.get("university") or institution,
                      "title": title, "faculty": yok.get("faculty", ""), "department": yok.get("department", ""), "field": yok.get("field", ""),
                      "keywords": yok.get("keywords", []), "yok_url": yok.get("url", ""), "chat_id": (chat or {}).get("id", ""), "job_id": (chat or {}).get("job_id", ""),
                      "works": len(p["works"]), "citations": p["citations"], "last_year": p["last"], "active": active,
                      "theses": yok.get("theses"), "theses_phd": yok.get("theses_phd"), "theses_recent": yok.get("theses_recent"), "thesis_titles": yok.get("thesis_titles", []),
                      "topics": [t for t, _ in sorted(p["topics"].items(), key=lambda kv: -kv[1])[:3]], "samples": works_[:3],
                      "eligible": eligible, "score": round(score, 2)})
    items.sort(key=lambda x: -x["score"])
    best = items[0]["score"] if items else 1
    for x in items:
        x["match"] = max(5, round(100 * x["score"] / best))
    out = {"items": items[:30], "query": q, "english": english, "university": uni["name"] if uni else "", "mode": mode, "works": len(works), "years": YEARS, "message": ""}
    if items:
        _store(key, out)
    return out
