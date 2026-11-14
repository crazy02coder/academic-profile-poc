"""Üniversitenin fakülte ve bölümleri Türkçe Vikipedi'den: YÖK'e ulaşılamadığında ve kurum sitesi listeyi vermediğinde
(engelli site, JS ile çizilen menü, menüde eksik birim) yedek kaynak. Siteye ya da YÖK'e istek atmaz; 1 yıl saklanır."""
from __future__ import annotations

import json
import re
import time

import httpx

from .config import ROOT, USER_AGENT
from .text import clean, fold

DIR = ROOT / "data" / "wiki"
TTL = 365 * 24 * 3600
API = "https://tr.wikipedia.org/w/api.php"
UNIT_RX = re.compile(r"(?:Fakültesi|Yüksekokulu|Meslek Yüksekokulu|Enstitüsü|Konservatuvarı|Konservatuarı)\b")
DEPT_RX = re.compile(r"\bB[öo]l[üu]m[üu]\b")
NOISE_RX = re.compile(r"kaynak|dış bağlantı|ayrıca bakınız|notlar|rektör|kategori|dosya:|resim:|file:", re.I)


def _plain(text: str) -> str:
    text = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", text)   # [[a|b]] → b
    text = re.sub(r"\{\{[^}]*\}\}|<ref[^>]*/>|<ref.*?</ref>|<[^>]+>", " ", text)
    text = re.sub(r"'{2,}|\[https?://\S+\s*([^\]]*)\]", r"\1", text)
    return clean(text.strip(" *#:;=|-–"))


def parse(wikitext: str) -> dict[str, list[str]]:
    """{fakülte adı: [bölüm adları]}: madde işaretli listeler ve başlıklar. Fakülte satırının altındaki daha
    derin maddeler (ya da "… Bölümü" satırları) bölüm sayılır."""
    units: dict[str, list[str]] = {}
    current, depth = "", 0
    for raw in wikitext.splitlines():
        line = raw.strip()
        if not line or NOISE_RX.search(line[:40]):
            continue
        bullets = len(line) - len(line.lstrip("*#"))
        heading = re.fullmatch(r"(=+)\s*(.*?)\s*=+", line)
        text = _plain(heading.group(2) if heading else line)
        if not text or len(text) > 90:
            continue
        if UNIT_RX.search(text) and not DEPT_RX.search(text):
            current, depth = text, (bullets or 0)
            units.setdefault(current, [])
        elif current and bullets and (bullets > depth or DEPT_RX.search(text)):
            name = clean(re.sub(r"\s*B[öo]l[üu]m[üu]$", "", text))
            if name and name not in units[current] and not UNIT_RX.search(name):
                units[current].append(name)
        elif heading:
            current = ""
    return units


async def units(university: str) -> dict[str, list[str]]:
    """Vikipedi maddesindeki birimler; madde yoksa ya da ulaşılamazsa {}."""
    key = re.sub(r"[^a-z0-9]+", "-", fold(university)).strip("-")
    path = DIR / f"{key}.json"
    try:
        saved = json.loads(path.read_text())
        if time.time() - saved["ts"] < TTL:
            return saved["data"]
    except (OSError, ValueError, KeyError):
        pass
    try:
        async with httpx.AsyncClient(timeout=12, headers={"User-Agent": USER_AGENT}) as client:
            r = await client.get(API, params={"action": "parse", "page": university, "prop": "wikitext",
                                              "format": "json", "redirects": 1})
            text = ((r.json().get("parse") or {}).get("wikitext") or {}).get("*", "")
            if not text:  # tam ad tutmazsa arama
                s = await client.get(API, params={"action": "opensearch", "search": university, "limit": 1, "format": "json"})
                title = (s.json()[1] or [""])[0]
                if title:
                    r = await client.get(API, params={"action": "parse", "page": title, "prop": "wikitext",
                                                      "format": "json", "redirects": 1})
                    text = ((r.json().get("parse") or {}).get("wikitext") or {}).get("*", "")
    except (httpx.HTTPError, ValueError):
        return {}
    data = parse(text) if text else {}
    try:
        DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"ts": time.time(), "data": data}, ensure_ascii=False))
    except OSError:
        pass
    return data
