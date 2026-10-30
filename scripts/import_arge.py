"""Sanayi ve Teknoloji Bakanlığı Ar-Ge / Tasarım Merkezi listelerini data/arge_merkezleri.json'a çevirir.

Excel dosyaları bakanlık sitesinde CAPTCHA arkasında olduğu için elle indirilir:
  https://www.sanayi.gov.tr/assets/doc/Ar-Gemerkezleri.xlsx
  https://www.sanayi.gov.tr/assets/doc/Tasarimmerkeziistatistik.xlsx

Kullanım (openpyxl gerekir: pip install openpyxl):
  python scripts/import_arge.py Ar-Gemerkezleri.xlsx Tasarimmerkeziistatistik.xlsx
Dosya adında "tasarim" geçen liste Tasarım Merkezi, diğerleri Ar-Ge Merkezi sayılır.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import openpyxl

OUT = Path(__file__).resolve().parent.parent / "data" / "arge_merkezleri.json"


def read(path: str) -> list[dict]:
    kind = "Tasarım Merkezi" if "tasarim" in Path(path).name.lower() else "Ar-Ge Merkezi"
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True).worksheets[0]
    rows = ws.iter_rows(values_only=True)
    header = [str(h or "").strip().upper() for h in next(rows)]
    col = {key: next(i for i, h in enumerate(header) if key in h) for key in ("AD", "İL", "SEKTÖR", "TARİH")}
    out = []
    for r in rows:
        name = str(r[col["AD"]] or "").replace("​", "").strip()
        if not name:
            continue
        since = r[col["TARİH"]]
        out.append({"name": " ".join(name.split()), "city": str(r[col["İL"]] or "").strip(),
                    "sector": str(r[col["SEKTÖR"]] or "").strip(), "kind": kind,
                    "since": since.date().isoformat() if isinstance(since, dt.datetime) else str(since or "")})
    return out


def main(paths: list[str]):
    centers = [c for p in paths for c in read(p)]
    OUT.write_text(json.dumps({"source": "Sanayi ve Teknoloji Bakanlığı (agtm.sanayi.gov.tr)",
                               "imported": dt.date.today().isoformat(), "centers": centers},
                              ensure_ascii=False, indent=1))
    kinds = {k: sum(c["kind"] == k for c in centers) for k in {c["kind"] for c in centers}}
    print(f"{OUT}: {len(centers)} merkez {kinds}")


if __name__ == "__main__":
    main(sys.argv[1:])
