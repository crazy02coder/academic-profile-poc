"""Firma logolarını toplar ve hazır veriye (data/firm_logos/) yazar; sonra scripts/publish_data.py ile yayımlanır.

    SERPER_API_KEY=... python scripts/build_firm_logos.py [en çok firma sayısı]

Firmalar sayfasında gösterilen firmalar sırasıyla (firms.firm_list) işlenir. Her firma için uygulamanın kendi logo
toplayıcısı (org_assets._collect) çalışır: kayıtlı web sitesi → OpenAlex → Wikidata → web araması (Serper anahtarı
varsa önce o) ile firmanın resmî sitesi bulunur, sitenin adı firma adıyla doğrulanır ve sitedeki logo alınır.
Bulunanlar data/firm_logos/<firma kimliği>.<uzantı> ve data/firm_logos/index.json olarak yazılır. Daha önce toplanmış
firma yeniden aranmaz (--yeniden ile aranır).
"""
from __future__ import annotations

import asyncio
import base64
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import firms, org_assets  # noqa: E402

OUT = ROOT / "data" / "firm_logos"
EXT = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp", "image/x-icon": "ico",
       "image/svg+xml": "svg"}


async def main(limit: int, again: bool) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    index_path = OUT / "index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8")).get("logos") or {}
    except (OSError, ValueError):
        index = {}
    listing = firms.firm_list("")
    if not listing.get("available"):
        print("Ar-Ge merkezi listesi yok; once uzak veri indirilebilmeli.")
        return 1
    ids = [item["id"] for item in listing["items"]][:limit]
    todo = [fid for fid in ids if again or fid not in index]
    print(f"{len(ids)} firma, {len(todo)} tanesi aranacak", flush=True)
    done = found = 0
    tmp = Path(tempfile.mkdtemp(prefix="firm-logos-"))

    async def one(fid: str) -> None:
        nonlocal done, found
        try:
            result = await org_assets._collect("firms", fid, tmp / f"{fid}.json")
        except Exception as exc:  # noqa: BLE001
            result = {"reason": type(exc).__name__}
        done += 1
        if result.get("data") and result.get("type") in EXT:
            name = f"{fid}.{EXT[result['type']]}"
            (OUT / name).write_bytes(base64.b64decode(result["data"]))
            index[fid] = {"file": name, "type": result["type"], "home": result.get("home") or "", "source": result.get("source") or ""}
            found += 1
        if done % 10 == 0 or done == len(todo):
            print(f"{done}/{len(todo)} · bulunan {found}", flush=True)
            index_path.write_text(json.dumps({"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "logos": index},
                                             ensure_ascii=False, indent=1), encoding="utf-8")

    # org_assets._collect kendi içinde en çok üç firmayı aynı anda işler.
    await asyncio.gather(*(one(fid) for fid in todo))
    index_path.write_text(json.dumps({"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "logos": index},
                                     ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"bitti: {found} yeni logo, toplam {len(index)}", flush=True)
    return 0


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    sys.exit(asyncio.run(main(int(args[0]) if args else 300, "--yeniden" in sys.argv)))
