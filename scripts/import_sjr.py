#!/usr/bin/env python3
"""SCImago (SJR) yıllık dergi listelerini sisteme aktarır.

Dosyaları tarayıcıdan indirip data/sjr/ klasörüne koyun: https://www.scimagojr.com/journalrank.php → "Download data"
Kullanım: python scripts/import_sjr.py [klasör]   (varsayılan: data/sjr)

Çıktı: data/journal_quartiles.sqlite. Değerler SJR'dir (Scopus tabanlı); WoS/JCR çeyreği değildir.
"""
from __future__ import annotations

import csv
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.quartiles import PATH, norm_issn, norm_title  # noqa: E402

REQUIRED = ("Sourceid", "Title", "Issn", "SJR Best Quartile", "Categories")


def main(folder: Path) -> int:
    files = sorted(folder.glob("*.csv"))
    if not files:
        print(f"{folder} içinde CSV yok.")
        return 1
    csv.field_size_limit(10_000_000)
    tmp = PATH.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.executescript("""CREATE TABLE rankings(jid INTEGER, year INTEGER, best TEXT, categories TEXT, title TEXT, PRIMARY KEY(jid, year));
                         CREATE TABLE issns(issn TEXT PRIMARY KEY, jid INTEGER);
                         CREATE TABLE titles(key TEXT PRIMARY KEY, jid INTEGER);""")
    issns: dict[str, set[int]] = {}
    titles: dict[str, set[int]] = {}
    for path in files:
        with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")
            fields = reader.fieldnames or []
            missing = [c for c in REQUIRED if c not in fields]
            year = next((m.group(1) for c in fields if (m := re.search(r"Total Docs\. \((\d{4})\)", c))), None)
            if missing or not year:
                print(f"{path.name}: beklenen sütunlar yok ({missing or 'yıl'}). Bulunan: {fields[:12]}")
                con.close()
                tmp.unlink(missing_ok=True)
                return 1
            total = rated = 0
            for row in reader:
                total += 1
                jid = int(row["Sourceid"])
                title = (row["Title"] or "").strip()
                for issn in re.split(r"[,\s]+", row["Issn"] or ""):
                    if norm_issn(issn):
                        issns.setdefault(norm_issn(issn), set()).add(jid)
                if norm_title(title):
                    titles.setdefault(norm_title(title), set()).add(jid)
                best = (row["SJR Best Quartile"] or "").strip().upper()
                if best in ("Q1", "Q2", "Q3", "Q4"):
                    rated += 1
                    con.execute("INSERT OR REPLACE INTO rankings VALUES(?,?,?,?,?)",
                                (jid, int(year), best, (row["Categories"] or "").strip(), title))
            print(f"{year}: {total} dergi, {rated} tanesinde çeyrek")
    # Birden çok dergiye işaret eden ISSN ya da ad güvenilmez: eşleştirmede kullanılmaz
    con.executemany("INSERT INTO issns VALUES(?,?)", [(k, next(iter(v))) for k, v in issns.items() if len(v) == 1])
    con.executemany("INSERT INTO titles VALUES(?,?)", [(k, next(iter(v))) for k, v in titles.items() if len(v) == 1])
    con.commit()
    con.close()
    tmp.replace(PATH)
    print(f"{len(files)} dosya aktarıldı. Belirsiz olduğu için atlanan: {sum(len(v) > 1 for v in issns.values())} ISSN, "
          f"{sum(len(v) > 1 for v in titles.values())} ad. → {PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "sjr"))
