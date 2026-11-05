#!/usr/bin/env python3
"""Ar-Ge / Tasarım Merkezi firmalarının çalışma alanlarını OpenAlex yayınlarından çıkarır.

Kullanım: python scripts/build_firm_areas.py [--limit 30] [--names "Aselsan,Arçelik"]
Çıktı: data/firm_areas.json. Yarıda kalırsa kaldığı yerden devam eder; kota dolunca durur, sonra yeniden çalıştırılır.
Etiketler firmanın yayınlarının konularıdır: yayını olmayan firmada etiket çıkmaz, bu "çalışma alanı yok" demek değildir.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import firms  # noqa: E402
from app.config import USER_AGENT  # noqa: E402
from app.text import fold  # noqa: E402

PAUSE = 0.25  # saniye: OpenAlex'i yormamak için firmalar arası bekleme


def save(done: dict):
    tmp = firms.AREAS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps({"source": "OpenAlex", "updated": time.strftime("%Y-%m-%d"), "firms": done}, ensure_ascii=False))
    tmp.replace(firms.AREAS_PATH)


async def main(limit: int | None, names: list[str]) -> int:
    done = json.loads(firms.AREAS_PATH.read_text()).get("firms", {}) if firms.AREAS_PATH.exists() else {}
    groups = firms._groups()
    todo = [(fid, g) for fid, g in groups.items() if fid not in done]
    if names:
        wanted = [fold(n) for n in names]
        todo = [(fid, g) for fid, g in groups.items() if any(n in fold(g["name"]) for n in wanted)]
    todo = todo[:limit] if limit else todo
    print(f"{len(groups)} firma, {len(done)} tamam, {len(todo)} taranacak", flush=True)
    async with httpx.AsyncClient(timeout=40, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}) as client:
        for i, (fid, g) in enumerate(todo, 1):
            try:
                res = await firms.openalex_areas(client, g)
            except httpx.HTTPError as exc:
                print(f"{g['name']}: {type(exc).__name__}", flush=True)
                res = None
            if res is None:
                save(done)
                print(f"{i}. firmada OpenAlex yanıt vermedi (kota ya da ağ). Sonra yeniden çalıştırın; kaldığı yerden devam eder.", flush=True)
                return 1
            done[fid] = res
            if names or res["tags"]:
                print(g["name"], res["papers"], [t["name"] for t in res["tags"][:4]], flush=True)
            if i % 25 == 0:
                save(done)
            await asyncio.sleep(PAUSE)
    save(done)
    print(f"Bitti: {len(done)} firma, {sum(bool(x['tags']) for x in done.values())} tanesinde etiket.", flush=True)
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--names", default="")
    a = ap.parse_args()
    raise SystemExit(asyncio.run(main(a.limit, [n for n in a.names.split(",") if n.strip()])))
