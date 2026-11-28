"""Dil tespiti ve varlık çözümleme (tekilleştirme).

Klasik ER hattı: bloklama → çift puanlama → (belirsiz çiftlerde) LLM hakemliği → union-find.
  * Kesin eşleşme : aynı DOI veya aynı normalize başlık
  * Bulanık       : rapidfuzz token_set_ratio ≥ 92 ve yıl farkı ≤ 1
  * Çapraz dil    : TR/EN farklı dilde, yıl ±1, ortak yazar veya aynı dergi → Gemini'ye
                    "bu iki başlık aynı makalenin çevirisi mi?" sorulur; LLM yoksa
                    sınırlı TR→EN sözlükle terim örtüşmesi kullanılır.
"""
from __future__ import annotations

import asyncio

from rapidfuzz import fuzz

from .text import LANG_NAMES, _tr_lookup, content_tokens, detect_language, fold, name_score, title_key

SOURCE_PRIORITY = {"openalex": 0, "crossref": 1, "yok": 2, "trdizin": 3, "tez": 4, "openaire": 5, "orcid": 6,
                   "scholar": 7}

def _translate(tokens: list[str]) -> set[str]:
    """Köklenmiş tokenları ortak İngilizce uzaya taşır (TR kökü → EN terim)."""
    return {_tr_lookup(t) or t for t in tokens}


class _UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


def _coauthor_overlap(a: dict, b: dict, subject: str) -> int:
    na = {fold(x).split()[-1] for x in a["authors"] if x and name_score(subject, x) < 0.75 and fold(x)}
    nb = {fold(x).split()[-1] for x in b["authors"] if x and name_score(subject, x) < 0.75 and fold(x)}
    return len(na & nb)


# Kişiyi adıyla arayan kaynaklar: kayıtta ORCID yoksa eşleşme yalnız ada dayanır (adaş riski).
NAME_SEARCHED = {"openaire", "trdizin"}
# Kişinin kendisinin girdiği ya da ORCID kimliğiyle süzülen kaynaklar.
IDENTITY = {"yok", "orcid", "crossref", "wos"}


def drop_homonyms(papers: list[dict], subject: str) -> tuple[list[dict], list[dict]]:
    """Adaşların yayınlarını ayıklar: (kalanlar, çıkarılanlar).

    OpenAIRE ve TR Dizin kişiyi adıyla arar. Yaygın bir adda ("Murat Şimşek") başka alanlardaki adaşların makale ve
    tezleri de gelir. Yalnız bu kaynaklarda bulunan ve ORCID ile doğrulanmamış kayıt "ada dayalı"dır; kimliği belli
    kaynaklardan (YÖK, ORCID, OpenAlex, Crossref…) gelenler "kesin"dir. Ada dayalı bir kayıt, kesin kayıtlarla ortak
    yazar ya da aynı dergi/yayın yeri paylaşıyorsa desteklenmiş sayılır.

    Ada dayalı kayıtların yarısından azı destekleniyorsa ad yaygındır: desteklenmeyenler çıkarılır. Çoğu
    destekleniyorsa (nadir ad) hiçbirine dokunulmaz; kesin kayıt azsa (5'ten az) karar verilemez, yine dokunulmaz."""
    # Kişinin kendi beyanına dayanan kayıtlar (YÖK, ORCID, ORCID ile süzülen Crossref, WoS) varsa "kesin" yalnız onlardır:
    # OpenAlex ve Scholar da adaşları tek yazar profilinde birleştirebiliyor, o yüzden bu durumda onlar da sınanır.
    hard = [p for p in papers if set(p.get("sources") or []) & IDENTITY or p.get("orcid_match")]
    loose_sources = NAME_SEARCHED | ({"openalex", "scholar", "tez"} if len(hard) >= 5 else set())
    def named(p):
        return set(p.get("sources") or []) <= loose_sources and not p.get("orcid_match")
    sure = [p for p in papers if not named(p)]
    loose = [p for p in papers if named(p)]
    if len(sure) < 5 or len(loose) < 5:
        return papers, []
    def others(p):
        return {fold(x).split()[-1] for x in p.get("authors") or [] if x and fold(x) and name_score(subject, x) < 0.75}
    coauthors = set().union(*(others(p) for p in sure))
    venues = {fold(p.get("venue") or "") for p in sure} - {""}
    backed = [p for p in loose if others(p) & coauthors or fold(p.get("venue") or "") in venues]
    if len(backed) * 2 >= len(loose):
        return papers, []
    keep = {id(p) for p in backed}
    return [p for p in papers if not named(p) or id(p) in keep], [p for p in loose if id(p) not in keep]


def drop_foreign_theses(papers: list[dict], education: list[dict] | None) -> tuple[list[dict], list[dict]]:
    """Tez Merkezi'nde yazar adıyla bulunan tezlerden adaşlara ait olanları ayıklar: (kalanlar, çıkarılanlar).

    Bir kişi en çok birkaç tez yazar; yaygın bir adda yazar araması onlarca adaşın tezini getirir. YÖK'teki öğrenim
    bilgisi varsa tez yalnız orada yazan tez adıyla ya da okunan üniversiteyle tutuyorsa kişinindir. Öğrenim bilgisi
    yoksa üçe kadar teze dokunulmaz; daha fazlası adaş karışımıdır, hangisinin kişiye ait olduğu bilinemediği için
    hiçbiri yayın sayılmaz (YÖK profili yenilenince öğrenim bilgisiyle yeniden eşleşir)."""
    def thesis_only(p):
        return set(p.get("sources") or []) == {"tez"}
    theses = [p for p in papers if thesis_only(p)]
    if not theses:
        return papers, []
    rows = [e for e in education or [] if isinstance(e, dict)]
    if rows:
        titles = {title_key(e.get("note") or "") for e in rows} - {""}
        places = {fold(e.get("place") or "") for e in rows} - {""}
        def mine(p):
            venue = fold(p.get("venue") or "")
            return title_key(p.get("title") or "") in titles or bool(venue) and any(venue in x or x in venue for x in places)
        gone = [p for p in theses if not mine(p)]
    else:
        gone = theses if len(theses) > 3 else []
    drop = {id(p) for p in gone}
    return [p for p in papers if id(p) not in drop], gone


async def resolve(records: list[dict], subject: str, llm=None, log=None) -> tuple[list[dict], dict]:
    recs = [r for r in records if r.get("title") and len(r["title"]) > 5]
    for r in recs:
        r["lang"], r["lang_conf"] = detect_language(r["title"], r.get("abstract", ""))
    n = len(recs)
    uf = _UF(n)
    stats = {"doi": 0, "exact": 0, "fuzzy": 0, "cross_lang": 0, "llm_checked": 0}

    by_doi, by_title = {}, {}
    for i, r in enumerate(recs):
        if r["doi"]:
            if r["doi"] in by_doi:
                uf.union(i, by_doi[r["doi"]])
                stats["doi"] += 1
            by_doi.setdefault(r["doi"], i)
        k = title_key(r["title"])
        if k in by_title:
            if uf.find(i) != uf.find(by_title[k]):
                stats["exact"] += 1
            uf.union(i, by_title[k])
        by_title.setdefault(k, i)

    # Bloklama: yıl kovası (±1). Bilinmeyen yıl her bloğa aday.
    pending_llm = []
    for i in range(n):
        for j in range(i + 1, n):
            if uf.find(i) == uf.find(j):
                continue
            a, b = recs[i], recs[j]
            if a["doi"] and b["doi"] and a["doi"] != b["doi"]:
                continue  # farklı DOI asla birleşmez
            if a["year"] and b["year"] and abs(a["year"] - b["year"]) > 1:
                continue
            if fuzz.token_set_ratio(title_key(a["title"]), title_key(b["title"])) >= 92 and \
                    abs(len(a["title"]) - len(b["title"])) < 0.4 * max(len(a["title"]), len(b["title"])):
                uf.union(i, j)
                stats["fuzzy"] += 1
                continue
            if {a["lang"], b["lang"]} == {"tr", "en"} and a["year"] and a["year"] == b["year"]:
                shared = _coauthor_overlap(a, b, subject)
                same_venue = a["venue"] and fold(a["venue"]) == fold(b["venue"])
                if shared or same_venue:
                    ta, tb = _translate(content_tokens(a["title"])), _translate(content_tokens(b["title"]))
                    jacc = len(ta & tb) / max(1, len(ta | tb))
                    pending_llm.append((i, j, jacc))

    if pending_llm:
        pending_llm = pending_llm[:25]

        async def judge(i, j):
            if llm is None or not llm.available:
                return None
            data = await llm.json(
                "İki yayın başlığı veriliyor. Biri diğerinin farklı dildeki (TR/EN) karşılığı mı, yani AYNI çalışma mı?\n"
                f"A ({recs[i]['year']}, {recs[i]['venue']}): {recs[i]['title']}\n"
                f"B ({recs[j]['year']}, {recs[j]['venue']}): {recs[j]['title']}\n"
                'JSON: {"same": true/false, "reason": "kısa"}',
                {"type": "object", "properties": {"same": {"type": "boolean"}, "reason": {"type": "string"}},
                 "required": ["same"]}, timeout=40, fast=True)
            return bool(data and data.get("same"))

        # Çiftler birbirinden bağımsız: sırayla değil aynı anda sorulur (LLM eşzamanlılığı llm.py'de sınırlı).
        verdicts = await asyncio.gather(*(judge(i, j) for i, j, _ in pending_llm), return_exceptions=True)
        for (i, j, jacc), verdict in zip(pending_llm, verdicts):
            if isinstance(verdict, bool):
                stats["llm_checked"] += 1
            else:
                verdict = jacc >= 0.5
            if verdict:
                uf.union(i, j)
                stats["cross_lang"] += 1

    clusters: dict[int, list[dict]] = {}
    for i, r in enumerate(recs):
        clusters.setdefault(uf.find(i), []).append(r)

    papers = []
    for members in clusters.values():
        members.sort(key=lambda r: (SOURCE_PRIORITY.get(r["source"], 9), -len(r.get("abstract") or "")))
        best = dict(members[0])
        if best.get("abstract"):
            best.setdefault("abstract_source", best.get("source", ""))
            best.setdefault("abstract_url", best.get("url", ""))
        for m in members[1:]:
            for key in ("doi", "venue", "issn", "abstract", "year", "url"):
                if not best.get(key) and m.get(key):
                    best[key] = m[key]
                    if key == "abstract":
                        best["abstract_source"] = m.get("abstract_source") or m.get("source", "")
                        best["abstract_url"] = m.get("abstract_url") or m.get("url", "")
            if len(m.get("authors") or []) > len(best.get("authors") or []):
                best["authors"] = m["authors"]
        # En ayrıntılı tarih (gün > ay); yılı birleşik kaydın yılıyla uyuşmalı
        dates = [m["date"] for m in members if m.get("date") and (not best.get("year") or m["date"][:4] == str(best["year"]))]
        best["date"] = max(dates, key=len) if dates else ""
        cites = [m["citations"] for m in members if isinstance(m.get("citations"), int)]
        best["citations"] = max(cites) if cites else None
        best["sources"] = sorted({m["source"] for m in members}, key=lambda s: SOURCE_PRIORITY.get(s, 9))
        yok_context = next((m["yok_context"] for m in members if m.get("yok_context")), None)
        if yok_context:
            best["yok_context"] = yok_context
        variants, seen = [], set()
        for m in members:
            k = title_key(m["title"])
            if k not in seen:
                seen.add(k)
                variants.append({"title": m["title"], "lang": m["lang"], "source": m["source"]})
        best["variants"] = variants
        best["languages"] = sorted({v["lang"] for v in variants})
        best["language_names"] = [LANG_NAMES.get(x, x) for x in best["languages"]]
        best["labels"] = sorted({lab for m in members for lab in (m.get("labels") or [])})[:6]
        sdgs = {g["name"]: g for m in members for g in (m.get("sdgs") or []) if isinstance(g, dict) and g.get("name")}
        if sdgs:
            best["sdgs"] = list(sdgs.values())
        orgs = {(o.get("name"), o.get("type")): o for m in members for o in (m.get("orgs") or [])}
        if orgs:
            best["orgs"] = list(orgs.values())
        if any(m.get("orcid_match") for m in members):
            best["orcid_match"] = True
        papers.append(best)

    papers, dropped = drop_homonyms(papers, subject)
    stats["homonym_dropped"] = len(dropped)
    if dropped and log:
        await log("dedup", "running", f"Adaş ayıklama: yalnız ada göre eşleşen ve kişinin diğer yayınlarıyla ortak yazarı ya da "
                                      f"dergisi olmayan {len(dropped)} kayıt çıkarıldı (ör. {dropped[0]['title'][:70]}).")

    papers.sort(key=lambda p: (-(p["year"] or 0), p["title"]))
    for idx, p in enumerate(papers, 1):
        p["id"] = f"P{idx}"
    stats.update({"raw": len(records), "unique": len(papers)})
    return papers, stats
