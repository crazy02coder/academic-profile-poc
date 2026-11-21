"""Kampüs çevresi (OpenStreetMap): ana yerleşkenin yakınındaki toplu taşıma, yurt, kütüphane, yeme-içme ve sağlık
noktaları. Öğrenci bakışının "Kampüs ve ulaşım" başlığı kullanır.

Koordinat künyeden (Wikidata) gelir; yoksa Nominatim'de üniversite adıyla aranır. Çevredeki noktalar Overpass API ile
tek sorguda alınır. Üniversite başına bir kez çalışır, 90 gün saklanır. İki servis de açık veridir (ODbL); istekler
genel bir istemci adıyla gider.
"""
from __future__ import annotations

import json
import math
import re
import time

import httpx

from .config import ROOT
from .text import clean, fold

DIR = ROOT / "data" / "campus"
TTL = 90 * 24 * 3600
RADIUS = 1200  # metre
VERSION = 6  # kayıt biçimi (6: yerleşke merkezi yalnız adı birebir tutan harita kaydından)
_V5 = 5  # kayıt biçimi (… 4: merkez OpenStreetMap kaydından; 5: eczane, kafe, AVM ayrı gruplar, konumlu tam liste)
LINE_RADIUS = 700  # hatlar için: kampüse bu kadar yakından geçen güzergâhlar
MODES = {"subway": "Metro", "light_rail": "Hafif raylı", "tram": "Tramvay", "train": "Tren", "monorail": "Monoray", "funicular": "Füniküler",
         "ferry": "Vapur", "trolleybus": "Troleybüs", "bus": "Otobüs", "share_taxi": "Dolmuş / minibüs"}
UA = {"User-Agent": "academic-profile-poc/1.0 (campus surroundings; OpenStreetMap data)"}
# Sorgu sunucuları sık sık dolu oluyor: sırayla denenir, yanıt vermeyen kısa sürede geçilir.
OVERPASS_SERVERS = ("https://overpass.openstreetmap.fr/api/interpreter", "https://overpass-api.de/api/interpreter",
                    "https://overpass.private.coffee/api/interpreter", "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
                    "https://overpass.kumi.systems/api/interpreter")
# Sorgu sunucularının hepsi düşerse: adres arama servisi (Nominatim) ile grup başına bir arama (en çok 40 sonuç).
NOMINATIM_PHRASES = {"rail": ["railway station", "tram stop"], "ferry": ["ferry terminal"], "bus": ["bus stop"], "cafe": ["cafe"],
                     "food": ["restaurant"], "pharmacy": ["pharmacy"], "health": ["hospital"], "mall": ["mall", "supermarket"],
                     "dorm": ["dormitory"], "library": ["library"], "sport": ["sports centre"]}
NOMINATIM = "https://nominatim.openstreetmap.org/search"

# (anahtar, başlık, Overpass süzgeçleri)
GROUPS = [
    ("rail", "Metro, tren ve tramvay", ['node["railway"~"station|halt|tram_stop"]', 'node["station"="subway"]']),
    ("ferry", "Vapur ve iskele", ['node["amenity"="ferry_terminal"]']),
    ("bus", "Otobüs durakları", ['node["highway"="bus_stop"]']),
    ("cafe", "Kafeler", ['nwr["amenity"="cafe"]']),
    ("food", "Restoran ve yemek", ['nwr["amenity"~"restaurant|fast_food|food_court"]']),
    ("pharmacy", "Eczaneler", ['nwr["amenity"="pharmacy"]']),
    ("health", "Hastane ve klinik", ['nwr["amenity"~"hospital|clinic|doctors"]']),
    ("mall", "AVM ve market", ['nwr["shop"~"mall|department_store|supermarket"]']),
    ("dorm", "Yurtlar", ['nwr["building"="dormitory"]', 'nwr["amenity"="student_accommodation"]', 'nwr["tourism"="hostel"]']),
    ("library", "Kütüphaneler", ['nwr["amenity"="library"]']),
    ("sport", "Spor", ['nwr["leisure"~"sports_centre|fitness_centre|swimming_pool|stadium"]']),
]
# AVM'ler kampüsten biraz uzakta olabilir: bu grup daha geniş alanda aranır.
WIDE = {"mall": 3000}


def _distance(a: tuple[float, float], b: tuple[float, float]) -> int:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return round(6371000 * 2 * math.asin(math.sqrt(h)))


async def _center(uid: str) -> tuple[float, float, str] | None:
    """(enlem, boylam, kaynak). Önce OpenStreetMap'te üniversitenin kendi kaydı (amenity=university/college/school ya
    da üniversite binası; adı tutmalı) — yerleşkenin gerçek yeri budur. Yoksa künyedeki Wikidata koordinatı (bazı
    kurumlarda yanlış ya da eski yeri gösterir), o da yoksa ad aramasının ilk sonucu."""
    from . import uni_facts, yokdir
    uni = await yokdir._university(uid)
    rows = []
    if uni:
        try:
            async with httpx.AsyncClient(timeout=20, headers=UA) as client:
                r = await client.get(NOMINATIM, params={"q": uni["name"], "format": "jsonv2", "limit": 8, "countrycodes": "tr"})
            rows = r.json() if r.status_code == 200 else []
        except (httpx.HTTPError, ValueError):
            rows = []
    # Ad birebir tutmalı: "Ankara Üniversitesi" aranırken "Ankara Yıldırım Beyazıt Üniversitesi" kabul edilmez. Yalnız
    # yerleşke belirten ekler ("… Merkez Kampüsü", "… Rektörlüğü") yok sayılır.
    extra = {"universitesi", "university", "kampusu", "kampus", "yerleskesi", "yerleske", "merkez", "ana", "rektorlugu", "rektorluk", "campus"}

    def tokens(text: str) -> set[str]:
        return {w for w in re.split(r"[^a-z0-9]+", fold(text)) if len(w) > 1} - extra
    words = tokens((uni or {}).get("name") or "")

    def campus(row: dict) -> bool:
        kind = (row.get("category"), row.get("type"))
        named = bool(words) and tokens(row.get("name") or "") == words
        return named and (kind[0] == "amenity" and kind[1] in {"university", "college", "school"} or kind == ("building", "university")
                          or kind == ("office", "educational_institution"))
    hit = next((row for row in rows if isinstance(row, dict) and campus(row)), None)
    if hit:
        return float(hit["lat"]), float(hit["lon"]), "OpenStreetMap"
    try:
        facts = await uni_facts.facts(uid)
    except Exception:  # noqa: BLE001 — künye yardımcıdır
        facts = None
    coords = ((facts or {}).get("identity") or {}).get("coords")
    if isinstance(coords, list) and len(coords) == 2:
        return float(coords[0]), float(coords[1]), "Wikidata"
    if rows and isinstance(rows[0], dict):
        return float(rows[0]["lat"]), float(rows[0]["lon"]), "OpenStreetMap"
    return None


async def around(uid: str, refresh: bool = False) -> dict | None:
    """Ana yerleşkenin çevresi: gruplar (sayı + en yakın adlı noktalar) ve harita için merkez."""
    path = DIR / f"{uid}.json"
    if not refresh:
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            if time.time() - saved.get("ts", 0) < TTL and saved.get("v") == VERSION:
                return saved["data"]
        except (OSError, ValueError, KeyError):
            pass
    center = await _center(uid)
    if not center:
        return None
    lat, lon, source = center
    parts = "".join(f"{flt}(around:{WIDE.get(key, RADIUS)},{lat},{lon});" for key, _, filters in GROUPS for flt in filters)
    query = f"[out:json][timeout:25];({parts});out center tags 1200;"
    elements = None
    async with httpx.AsyncClient(timeout=httpx.Timeout(8, connect=4), headers=UA) as client:
        for server in OVERPASS_SERVERS:
            try:
                r = await client.post(server, data={"data": query})
                if r.status_code == 200:
                    elements = r.json().get("elements") or []
                    break
            except (httpx.HTTPError, ValueError):
                continue
    exact = elements is not None
    if elements is None:
        elements = await _nominatim_points(lat, lon)
    lines = await _lines(lat, lon) if exact else None
    lines_ok = lines is not None
    lines = lines or []

    def kind(tags: dict) -> str:
        if tags.get("_group"):
            return tags["_group"]
        amenity, shop = tags.get("amenity"), tags.get("shop")
        if amenity == "ferry_terminal":
            return "ferry"
        if tags.get("highway") == "bus_stop":
            return "bus"
        if tags.get("railway") in {"station", "halt", "tram_stop"} or tags.get("station") == "subway":
            return "rail"
        if tags.get("building") == "dormitory" or amenity == "student_accommodation" or tags.get("tourism") == "hostel":
            return "dorm"
        if amenity == "library":
            return "library"
        if amenity == "cafe":
            return "cafe"
        if amenity in {"restaurant", "fast_food", "food_court"}:
            return "food"
        if amenity == "pharmacy":
            return "pharmacy"
        if amenity in {"hospital", "clinic", "doctors"}:
            return "health"
        if shop in {"mall", "department_store", "supermarket"}:
            return "mall"
        if tags.get("leisure"):
            return "sport"
        return ""

    found: dict[str, list[dict]] = {key: [] for key, _, _ in GROUPS}
    for el in elements:
        tags = el.get("tags") or {}
        key = kind(tags)
        point = (el.get("lat"), el.get("lon")) if el.get("lat") is not None else ((el.get("center") or {}).get("lat"), (el.get("center") or {}).get("lon"))
        if not key or point[0] is None:
            continue
        found[key].append({"name": clean(tags.get("name:tr") or tags.get("name") or ""), "lat": point[0], "lon": point[1],
                           "distance": _distance((lat, lon), point),
                           "note": clean({"mall": "AVM", "department_store": "Mağaza", "supermarket": "Market"}.get(tags.get("shop") or "", "")
                                         or tags.get("cuisine") or tags.get("network") or tags.get("operator") or "")[:60],
                           "hours": clean(tags.get("opening_hours") or "")[:80]})
    groups = []
    for key, label, _ in GROUPS:
        rows = sorted(found[key], key=lambda x: x["distance"])
        named, seen = [], set()
        for row in rows:
            if row["name"] and row["name"] not in seen:
                seen.add(row["name"])
                named.append(row)
        if rows:
            groups.append({"key": key, "label": label, "count": len(rows), "nearest": rows[0]["distance"], "items": named[:40]})
    data = {"v": VERSION, "center": {"lat": lat, "lon": lon, "source": source}, "radius": RADIUS, "groups": groups, "capped": not exact, "lines": lines,
            # Yol tarifi: kullanıcının konumundan kampüse toplu taşıma güzergâhı (harita uygulamasında açılır)
            "directions": f"https://www.google.com/maps/dir/?api=1&destination={lat},{lon}&travelmode=transit",
            "map": f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=16/{lat}/{lon}"}
    if not groups or not lines_ok:
        data["v"] = 0  # eksik veri: gösterilir ama kayda yazılmaz, sonraki açılışta yeniden denenir
        return data
    try:
        DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"ts": time.time(), "v": VERSION, "data": data}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return data


async def _lines(lat: float, lon: float) -> list[dict] | None:
    """Kampüsün yakınından geçen toplu taşıma hatları (OpenStreetMap güzergâh kayıtları): tür, hat numarası, ad ve
    nereden nereye gittiği. Gidiş-dönüş aynı hat tek satırdır. Sorgu sunucusu yanıt vermezse boş liste."""
    kinds = "|".join(MODES)
    query = f'[out:json][timeout:20];relation["type"="route"]["route"~"^({kinds})$"](around:{LINE_RADIUS},{lat},{lon});out tags 300;'
    elements = await _overpass(query, 12)
    if elements is None:
        return None  # sorgu sunucusu yanıt vermedi: "hat yok" diye kaydedilmez
    found: dict[tuple, dict] = {}
    for el in elements:
        tags = el.get("tags") or {}
        mode = tags.get("route") or ""
        ref = clean(tags.get("ref") or "")
        name = clean(tags.get("name:tr") or tags.get("name") or "")
        start, end = clean(tags.get("from") or ""), clean(tags.get("to") or "")
        if mode not in MODES or not (ref or name):
            continue
        key = (mode, ref or name)
        row = found.setdefault(key, {"mode": mode, "label": MODES[mode], "ref": ref, "name": name, "ends": [], "ids": [],
                                      "network": clean(tags.get("network") or tags.get("operator") or "")[:60]})
        if el.get("id") and len(row["ids"]) < 2:
            row["ids"].append(el["id"])  # gidiş ve dönüş güzergâhı
        for stop in (start, end):
            if stop and stop not in row["ends"]:
                row["ends"].append(stop)
    order = list(MODES)

    def ref_key(row):
        digits = "".join(ch for ch in row["ref"] if ch.isdigit())
        return (order.index(row["mode"]), int(digits) if digits else 10**6, row["ref"] or row["name"])
    return [{**row, "ends": row["ends"][:2]} for row in sorted(found.values(), key=ref_key)][:80]


async def _nominatim_points(lat: float, lon: float) -> list[dict]:
    """Yedek yol: Nominatim'de kampüs çevresindeki kutuda grup başına arama. Servisin kuralı gereği saniyede en çok
    bir istek gider. Sonuçlar Overpass öğeleriyle aynı biçime çevrilir (grup "_group" etiketinde)."""
    import asyncio
    dlat = RADIUS / 111320
    dlon = RADIUS / (111320 * max(0.2, math.cos(math.radians(lat))))
    box = f"{lon - dlon},{lat + dlat},{lon + dlon},{lat - dlat}"
    out, seen = [], set()
    async with httpx.AsyncClient(timeout=15, headers=UA) as client:
        for group, phrases in NOMINATIM_PHRASES.items():
            for phrase in phrases:
                try:
                    r = await client.get(NOMINATIM, params={"q": phrase, "viewbox": box, "bounded": 1, "format": "jsonv2", "limit": 40})
                    rows = r.json() if r.status_code == 200 else []
                except (httpx.HTTPError, ValueError):
                    rows = []
                for row in rows if isinstance(rows, list) else []:
                    key = (row.get("osm_type"), row.get("osm_id"))
                    if key in seen:
                        continue
                    seen.add(key)
                    try:
                        out.append({"lat": float(row["lat"]), "lon": float(row["lon"]), "tags": {"_group": group, "name": row.get("name") or ""}})
                    except (KeyError, TypeError, ValueError):
                        continue
                await asyncio.sleep(1.05)
    return out


async def _overpass(query: str, timeout: float = 14) -> list[dict] | None:
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=4), headers=UA) as client:
        for server in OVERPASS_SERVERS[:4]:
            try:
                r = await client.post(server, data={"data": query})
                if r.status_code == 200:
                    return r.json().get("elements") or []
            except (httpx.HTTPError, ValueError):
                continue
    return None


async def line_detail(relation_id: int) -> dict | None:
    """Bir toplu taşıma hattının ayrıntısı: sıralı duraklar, işletmeci, sefer aralığı ve çalışma saatleri (kayıtta
    varsa). Hat tıklanınca istenir; 30 gün saklanır."""
    path = DIR / f"line-{int(relation_id)}.json"
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - saved.get("ts", 0) < 30 * 24 * 3600:
            return saved["data"]
    except (OSError, ValueError, KeyError):
        pass
    elements = await _overpass(f"[out:json][timeout:20];relation({int(relation_id)});out body;node(r);out tags;")
    if not elements:
        return None
    relation = next((e for e in elements if e.get("type") == "relation"), None)
    if not relation:
        return None
    nodes = {e["id"]: e.get("tags") or {} for e in elements if e.get("type") == "node"}
    stops, seen = [], set()
    for member in relation.get("members") or []:
        if member.get("type") != "node":
            continue
        tags = nodes.get(member["ref"]) or {}
        # Durak: rolü stop/platform olan ya da (rol yazılmamışsa) durak/peron etiketi taşıyan üye.
        marked = str(member.get("role") or "").startswith(("stop", "platform")) or tags.get("highway") == "bus_stop" \
            or tags.get("public_transport") in {"stop_position", "platform", "station"} or tags.get("railway") in {"station", "stop", "halt", "tram_stop"}
        if not marked:
            continue
        name = clean((nodes.get(member["ref"]) or {}).get("name:tr") or (nodes.get(member["ref"]) or {}).get("name") or "")
        if name and name not in seen:
            seen.add(name)
            stops.append(name)
    tags = relation.get("tags") or {}
    data = {"id": int(relation_id), "ref": clean(tags.get("ref") or ""), "name": clean(tags.get("name:tr") or tags.get("name") or ""),
            "mode": tags.get("route") or "", "from": clean(tags.get("from") or ""), "to": clean(tags.get("to") or ""),
            "operator": clean(tags.get("operator") or ""), "network": clean(tags.get("network") or ""),
            "interval": clean(tags.get("interval") or ""), "hours": clean(tags.get("opening_hours") or ""),
            "duration": clean(tags.get("duration") or ""), "fee": clean(tags.get("charge") or tags.get("fee") or ""),
            "stops": stops, "url": f"https://www.openstreetmap.org/relation/{int(relation_id)}"}
    try:
        DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"ts": time.time(), "data": data}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return data


async def scene(uid: str) -> dict | None:
    """3B kampüs görünümü için çevredeki binalar (taban çokgeni + yükseklik) ve yollar, merkeze göre metre cinsinden.
    Yükseklik: "height" etiketi, yoksa kat sayısı × 3,2 m, o da yoksa 9 m. Üniversite başına bir kez, 90 gün saklanır."""
    path = DIR / f"{uid}.3d.json"
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - saved.get("ts", 0) < TTL and saved.get("v") == VERSION:
            return saved["data"]
    except (OSError, ValueError, KeyError):
        pass
    center = await _center(uid)
    if not center:
        return None
    lat, lon, _ = center
    radius = 520
    elements = await _overpass(
        f'[out:json][timeout:25];(way["building"](around:{radius},{lat},{lon});way["highway"](around:{radius},{lat},{lon});'
        f'way["leisure"~"park|pitch|garden"](around:{radius},{lat},{lon});way["natural"="water"](around:{radius},{lat},{lon}););out geom tags 2500;', 22)
    if elements is None:
        return None
    kx = 111320 * math.cos(math.radians(lat))

    def local(geometry) -> list[list[float]]:
        return [[round((g["lon"] - lon) * kx, 1), round((g["lat"] - lat) * 111320, 1)] for g in geometry or [] if "lat" in g]

    def height(tags: dict) -> float:
        for key, scale in (("height", 1.0), ("building:levels", 3.2)):
            try:
                value = float(str(tags.get(key) or "").replace(",", ".").split()[0]) * scale
                if 2 <= value <= 400:
                    return round(value, 1)
            except (ValueError, IndexError):
                continue
        return 9.0
    buildings, roads, greens, water = [], [], [], []
    for el in elements:
        tags, pts = el.get("tags") or {}, local(el.get("geometry"))
        if len(pts) < 2:
            continue
        if tags.get("building") and len(pts) >= 4:
            kind = tags.get("building") or ""
            buildings.append({"p": pts, "h": height(tags), "n": clean(tags.get("name:tr") or tags.get("name") or "")[:80],
                              "u": kind in {"university", "college", "dormitory", "school"} or tags.get("amenity") in {"university", "library", "college"}})
        elif tags.get("highway"):
            major = tags["highway"] in {"motorway", "trunk", "primary", "secondary", "tertiary"}
            foot = tags["highway"] in {"footway", "path", "pedestrian", "steps", "cycleway"}
            roads.append({"p": pts, "w": 9 if major else 2.2 if foot else 5.5, "f": foot})
        elif tags.get("natural") == "water" and len(pts) >= 4:
            water.append(pts)
        elif tags.get("leisure") and len(pts) >= 4:
            greens.append(pts)
    data = {"center": {"lat": lat, "lon": lon}, "radius": radius, "buildings": buildings[:1800], "roads": roads[:1500],
            "greens": greens[:200], "water": water[:60]}
    if buildings:
        try:
            DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"ts": time.time(), "v": VERSION, "data": data}, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return data
