"""Doğrulama: kaynaklar arası uzlaşı + ardışık çalıştırmalar arası tutarlılık.

Bir bilgi (unvan, bölüm, kurum, ORCID, ilgi alanı, yayın) ne kadar çok BAĞIMSIZ
kaynaktan ve ne kadar çok ARDIŞIK çalıştırmada aynı gelirse güveni o kadar artar.

  güven = Σ(kaynak ağırlığı, bu çalıştırmada aynı değeri veren bağımsız kaynaklar)
        + 0.35 × (bu değerin görüldüğü önceki çalıştırma sayısı, en fazla 3)
  normalize: [0, 1]

Durumlar:
  doğrulandı   — ≥2 bağımsız kaynak VEYA ≥2 çalıştırmada aynı
  tek kaynak   — yalnızca bir kaynak, ilk kez görülüyor
  çelişki      — ikinci en güçlü değer, birincinin ≥%60'ı kadar destek alıyor
  değişti      — önceki çalıştırmalardaki değer bu çalıştırmada farklı (örn. unvan yükseltmesi)
"""
from __future__ import annotations

import json
import re
import time
from collections import defaultdict

from rapidfuzz import fuzz

from .config import ROOT
from .text import detect_title, doi_key, fold, title_key

FACTS_DIR = ROOT / "data" / "facts"
WEIGHTS = {"yok": 1.0, "university": 0.9, "rea-json": 0.9, "orcid": 0.85, "openalex": 0.75, "scholar": 0.6,
           "crossref": 0.6, "llm": 0.4}
FIELDS = ("title", "department", "institution", "orcid")


def _norm(field: str, value) -> str:
    v = str(value)
    if field == "title":
        return fold(detect_title(v) or v)
    v = fold(v)
    for en, tr in (("technical", "teknik"), ("technology", "teknoloji"), ("engineering", "muhendisligi"),
                   ("computer", "bilgisayar"), ("artificial intelligence", "yapay zeka")):
        v = v.replace(en, tr)
    for junk in ("universitesi", "university", "bolumu", "department of", "programi", "turkce", "ingilizce", " of "):
        v = v.replace(junk, " ")
    v = re.sub(r"\b(pr|dr|dali|anabilim)\b", " ", v)
    return " ".join(v.split())


def _same(field: str, a: str, b: str) -> bool:
    if a == b:
        return True
    if field in ("department", "institution", "interest"):
        return fuzz.token_set_ratio(a, b) >= 88
    return False


def _cluster(field: str, obs: list[dict]) -> list[dict]:
    groups: list[dict] = []
    for o in obs:
        key = _norm(field, o["value"])
        if not key:
            continue
        g = next((g for g in groups if _same(field, g["key"], key)), None)
        if g is None:
            g = {"key": key, "value": o["value"], "sources": {}, "urls": []}
            groups.append(g)
        g["sources"][o["source"]] = max(g["sources"].get(o["source"], 0), WEIGHTS.get(o["source"], 0.5))
        if o.get("url"):
            g["urls"].append(o["url"])
        # en yetkili kaynağın yazımını göster
        if WEIGHTS.get(o["source"], 0) >= max(g["sources"].values()):
            g["value"] = o["value"]
    return groups


def _history_path(key: str):
    return FACTS_DIR / f"{key}.json"


def load_history(key: str) -> dict:
    p = _history_path(key)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except ValueError:
            pass
    return {"key": key, "runs": []}


def _past_support(history: dict, field: str, key: str) -> int:
    n = 0
    for run in history["runs"][-3:]:
        vals = run.get("fields", {}).get(field, [])
        if any(_same(field, key, v) for v in vals):
            n += 1
    return n


def _status(groups, best, past, field, history) -> str:
    indep = len(best["sources"])
    if len(groups) > 1:
        second = groups[1]
        if second["score"] >= 0.6 * best["score"] and len(second["sources"]) >= 1 and second["score"] > 0.5:
            return "çelişki"
    prev_vals = [v for run in history["runs"][-1:] for v in run.get("fields", {}).get(field, [])]
    if prev_vals and not any(_same(field, best["key"], v) for v in prev_vals):
        return "değişti"
    if indep >= 2 or past >= 1:
        return "doğrulandı"
    return "tek kaynak"


def verify_profile(profile, key: str, orcid_sources: list[str]) -> tuple[dict, dict]:
    """Profil alanlarını doğrular; seçilen değerleri profile yazar. (verification, history) döndürür."""
    history = load_history(key)
    obs_by_field = defaultdict(list)
    for o in profile.observations:
        if o["field"] == "interests":
            for item in o["value"] if isinstance(o["value"], list) else [o["value"]]:
                obs_by_field["interest"].append({**o, "value": item})
        else:
            obs_by_field[o["field"]].append(o)
    for src in orcid_sources:
        if profile.links.get("orcid"):
            obs_by_field["orcid"].append({"field": "orcid", "value": profile.links["orcid"], "source": src})

    out: dict = {}
    for field in (*FIELDS, "interest"):
        groups = _cluster(field, obs_by_field.get(field, []))
        if not groups:
            continue
        for g in groups:
            past = _past_support(history, field, g["key"])
            g["past"] = past
            g["score"] = sum(g["sources"].values()) + 0.35 * min(past, 3)
        groups.sort(key=lambda g: -g["score"])
        if field == "interest":
            items = []
            for g in groups[:15]:
                conf = min(1.0, g["score"] / 2.0)
                items.append({"value": g["value"], "confidence": round(conf, 2),
                              "sources": sorted(g["sources"]), "runs_seen": g["past"] + 1})
            # Birden çok kaynakta/çalıştırmada teyit edilenler önce
            items.sort(key=lambda x: (-len(x["sources"]), -x["runs_seen"], -x["confidence"]))
            out["interests"] = items
            profile.set("interests", [x["value"] for x in items[:10]], "consensus", override=True)
            continue
        best = groups[0]
        total = sum(g["score"] for g in groups)
        conf = min(1.0, best["score"] / 2.0) * (best["score"] / total if total else 0)
        status = _status(groups, best, best["past"], field, history)
        out[field] = {"value": best["value"], "confidence": round(conf, 2), "status": status,
                      "sources": sorted(best["sources"]), "runs_seen": best["past"] + 1,
                      "alternatives": [{"value": g["value"], "sources": sorted(g["sources"])} for g in groups[1:3]]}
        if field == "orcid":
            profile.links["orcid"] = best["value"]
        else:
            prev = profile.facts.get(field)
            profile.set(field, best["value"], prev.source if prev else best_source(best), override=True)
    profile.verification = out
    return out, history


def best_source(group: dict) -> str:
    return max(group["sources"], key=lambda s: group["sources"][s])


def _paper_key(p: dict) -> str:
    return p.get("doi") or title_key(p["title"])[:120]


def verify_papers(papers: list[dict], history: dict) -> dict:
    """Yayın bazında: çok kaynaklı teyit + önceki çalıştırmalarda görülme."""
    prev_runs = [set(r.get("papers", [])) for r in history["runs"][-3:]]
    last = prev_runs[-1] if prev_runs else set()
    current = set()
    for p in papers:
        keys = {_paper_key(p)} | {title_key(v["title"])[:120] for v in p.get("variants", [])}
        if p.get("doi"):
            keys.add(doi_key(p["doi"]))
        current.add(_paper_key(p))
        seen = sum(1 for r in prev_runs if keys & r)
        p["runs_seen"] = seen + 1
        p["verified"] = len(p.get("sources", [])) >= 2 or seen >= 1
        p["is_new"] = bool(prev_runs) and not (keys & last)
    removed = len(last - current) if last else 0
    return {"previous_runs": len(history["runs"]), "new": sum(p["is_new"] for p in papers), "removed": removed,
            "multi_source": sum(len(p.get("sources", [])) >= 2 for p in papers),
            "verified": sum(p["verified"] for p in papers)}


def save_run(key: str, history: dict, verification: dict, papers: list[dict]):
    FACTS_DIR.mkdir(parents=True, exist_ok=True)
    fields = {f: [_norm(f, v["value"])] for f, v in verification.items() if f in FIELDS}
    fields["interest"] = [_norm("interest", x["value"]) for x in verification.get("interests", [])]
    history["runs"].append({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "fields": fields,
                            "papers": sorted(_paper_key(p) for p in papers)})
    history["runs"] = history["runs"][-10:]
    _history_path(key).write_text(json.dumps(history, ensure_ascii=False, indent=1))
