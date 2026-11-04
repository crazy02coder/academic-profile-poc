"""Dergi çeyreği (Q1-Q4): içe aktarılmış yıllık listelerden yayınlara eklenir.

Değer derginin o yılki durumudur ve kaynağıyla taşınır ("SJR" ile WoS/JCR aynı değildir). Yayın kendi yılının listesiyle
eşleşir; yılın listesi henüz yayımlanmadıysa en son liste kullanılır ve etikette o yıl yazar. Dergi önce ISSN, yoksa adının
birebir eşleşmesiyle bulunur; yanlış çeyrek göstermemek için benzer ad eşleştirmesi yapılmaz. Liste yoksa hiçbir şey eklenmez.
"""
from __future__ import annotations

import re
import sqlite3

from .config import ROOT
from .text import fold

PATH = ROOT / "data" / "journal_quartiles.sqlite"
SOURCE = "SJR"


def norm_issn(value) -> str:
    s = re.sub(r"[^0-9Xx]", "", str(value or "")).upper()
    return s if len(s) == 8 else ""


def norm_title(value) -> str:
    return fold(str(value or "").replace("&", " and "))


def parse_categories(text: str) -> list[dict]:
    """"Signal Processing (Q2); Applied Mathematics (Q1)" → alan ve çeyrek listesi."""
    return [{"name": m.group(1).strip(), "q": m.group(2)} for m in re.finditer(r"([^;]+?)\s*\((Q[1-4])\)", text or "")]


def annotate(papers: list[dict]) -> list[dict]:
    if not PATH.exists():
        return papers
    con = sqlite3.connect(f"file:{PATH}?mode=ro", uri=True)
    try:
        latest = con.execute("SELECT MAX(year) FROM rankings").fetchone()[0]
        for p in papers:
            p.pop("quartile", None)
            year = p.get("year")
            if not year or not latest:
                continue
            jid = None
            for issn in map(norm_issn, p.get("issn") or []):
                row = con.execute("SELECT jid FROM issns WHERE issn=?", (issn,)).fetchone()
                if row:
                    jid = row[0]
                    break
            if jid is None and p.get("venue"):
                row = con.execute("SELECT jid FROM titles WHERE key=?", (norm_title(p["venue"]),)).fetchone()
                jid = row[0] if row else None
            if jid is None:
                continue
            used = min(int(year), latest)
            row = con.execute("SELECT best, categories, title FROM rankings WHERE jid=? AND year=?", (jid, used)).fetchone()
            if row:
                p["quartile"] = {"q": row[0], "source": SOURCE, "year": used, "journal": row[2],
                                 "categories": parse_categories(row[1])}
    finally:
        con.close()
    return papers
