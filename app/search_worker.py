"""Süre aşımında sonlandırılabilen DDGS işçisi; yalnızca JSON stdin/stdout."""
from __future__ import annotations

import json
import sys


def main():
    from ddgs import DDGS
    from ddgs.exceptions import DDGSException

    request = json.load(sys.stdin)
    backend = request.get("backend") or "auto"
    # Kurulu DDGS bazı motorları kapatabiliyor. Bilinmeyen isimde sessizce
    # tüm motorlara dönmek bu işçinin tek-motor süre bütçesini bozardı.
    if backend != "auto":
        from ddgs.engines import ENGINES

        if backend not in ENGINES.get("text", {}):
            json.dump([], sys.stdout)
            return
    try:
        results = DDGS(timeout=4).text(
            request["query"], max_results=10, region="tr-tr",
            backend=backend)
    except DDGSException as exc:
        if str(exc) != "No results found.":
            raise
        results = []
    json.dump([{"url": r.get("href", ""), "title": r.get("title", ""),
                "snippet": r.get("body", ""), "engine": f"ddgs:{backend}"} for r in results],
              sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
