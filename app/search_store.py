"""Arama sonuçlarının kalıcı ve ortak kaydı.

Web araması (app/websearch.py) sonuç verdiğinde sorgu ve satırlar diske yazılır: data/search-cache/. Aynı sorgu
sonraki sefer — uygulama kapatılıp açılsa da — arama motoruna gitmez; tarayıcı açılmaz, arama kredisi harcanmaz.

Aynı kayıt scripts/publish_data.py ile veri deposunda (akademik-iz-data, GitHub Pages) yayımlanır: search/ altında.
Başka bilgisayarlar sorguyu önce oradan okur. Yayımlanan dosya yalnız özeti değiştiğinde yeniden indirilir
(app/remote_data.py); yani kayıt değişmediyse ağa yalnız küçük dosya listesi için çıkılır.

Sıra: yerel kayıt → yayımlanan kayıt → canlı arama.

Dosyalar: bir kurumun sitesindeki aramalar ("site:ankara.edu.tr …") alan adına göre tek dosyada toplanır
(site/ankara.edu.tr.json); site kısıtı olmayan aramalar on altı dosyaya dağılır (web/0 … web/f). Böylece bir
üniversite açıldığında yalnız o üniversitenin küçük dosyası iner.

Kullanıcı "Yenile" dediğinde (FRESH) yalnız son 24 saatin kaydı kullanılır: yayın o arada güncellendiyse sonuç oradan
gelir, güncellenmediyse arama yeniden yapılır ve kayıt tazelenir.
"""
from __future__ import annotations

import asyncio
import contextvars
import gzip
import hashlib
import json
import re
import threading
import time

from .config import ROOT

DIR = ROOT / "data" / "search-cache"
PUBLISHED = "search/"        # veri deposundaki klasör
TTL = 60 * 24 * 3600         # kayıt bu süre boyunca canlı aramanın yerine geçer
FRESH_TTL = 24 * 3600        # "Yenile" isteğinde yalnız bu kadar yeni kayıt kullanılır
MAX_ROWS = 30                # sorgu başına saklanan satır
MAX_ENTRIES = 600            # dosya başına sorgu (dolunca en eskiler atılır)
SHARED_WAIT = 3.0            # yayımlanan dosya bu sürede gelmezse canlı aramaya geçilir (indirme arkada sürer)
# İsteğin "yenile" isteği olduğunu taşır (app/main.py ara katmanı ayarlar); isteğin başlattığı arka plan işlerine de geçer.
FRESH: contextvars.ContextVar[bool] = contextvars.ContextVar("search_fresh", default=False)

_LOCK = threading.Lock()
_LOCAL: dict[str, tuple[float, dict]] = {}    # dosya adı → (diskteki değişme zamanı, kayıtlar)
_SHARED: dict[str, tuple[tuple, dict]] = {}   # dosya adı → (indirilen dosyanın kimliği, kayıtlar)
_LISTED = {"at": 0.0}
_SKIP = {"until": 0.0}                         # yayın az önce yanıt vermedi: bu ana kadar ortak kayda bakılmaz


def key(query: str) -> str:
    return " ".join(str(query).split())


def shard(query: str) -> str:
    """Sorgunun yazıldığı dosya: site aramaları alan adına göre, diğerleri sorgu özetinin ilk hanesine göre."""
    q = key(query).lower()
    site = re.match(r"site:([a-z0-9.-]{3,80})(?:\s|$)", q)
    name = site[1].strip(".-") if site and ".." not in site[1] else ""
    return "site/" + name if name else "web/" + hashlib.sha1(q.encode("utf-8")).hexdigest()[0]


def _read_local(name: str) -> dict:
    path = DIR / (name + ".json")
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}
    hit = _LOCAL.get(name)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data = data if isinstance(data, dict) else {}
    _LOCAL[name] = (mtime, data)
    return data


def _read_shared(name: str, fresh: bool) -> dict:
    """Yayımlanan dosya. Ağ isteği yapabilir (dosya listesi, değişen dosya): iş parçacığından çağrılır."""
    from . import remote_data
    if not remote_data.ENABLED:
        return {}
    rel = f"{PUBLISHED}{name}.json.gz"
    if fresh and time.time() - _LISTED["at"] > 300:
        # "Yenile": yayın değişti mi diye dosya listesi yeniden okunur (beş dakikada en çok bir kez).
        _LISTED["at"] = time.time()
        remote_data.manifest(force=True)
    if rel not in remote_data.manifest() and not (remote_data.CACHE / rel).is_file():
        return {}
    path = remote_data.path(rel)
    if not path:
        return {}
    try:
        stat = path.stat()
        stamp = (stat.st_mtime, stat.st_size)
    except OSError:
        return {}
    hit = _SHARED.get(name)
    if hit and hit[0] == stamp:
        return hit[1]
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError, EOFError):
        data = {}
    data = data if isinstance(data, dict) else {}
    _SHARED[name] = (stamp, data)
    return data


def _rows(entry, fresh: bool) -> list[dict]:
    """Kaydın kullanılabilir satırları; süresi dolmuşsa ya da biçimi bozuksa boş."""
    if not isinstance(entry, dict) or not isinstance(entry.get("rows"), list):
        return []
    try:
        age = time.time() - float(entry.get("ts") or 0)
    except (TypeError, ValueError):
        return []
    if age > (FRESH_TTL if fresh else TTL) or age < -86400:  # ileri tarihli kayıt: saati bozuk bir bilgisayardan
        return []
    return [r for r in entry["rows"] if isinstance(r, dict) and str(r.get("url") or "").startswith(("http://", "https://"))]


async def get(query: str) -> tuple[list[dict], str] | None:
    """Sorgunun kayıtlı sonuçları: (satırlar, "yerel" ya da "ortak"). Kayıt yoksa ya da eskiyse None."""
    k, name, fresh = key(query), shard(query), FRESH.get()
    local = _read_local(name).get(k)
    local_rows = _rows(local, fresh)
    if local_rows and not fresh:
        return local_rows, "yerel"
    shared = None
    if time.monotonic() >= _SKIP["until"]:
        try:
            shared = (await asyncio.wait_for(asyncio.to_thread(_read_shared, name, fresh), SHARED_WAIT)).get(k)
        except asyncio.TimeoutError:
            # Yayın yanıt vermiyor: sonraki aramalar iki dakika boyunca beklemeden canlıya gider (her arama ayrı ayrı
            # beklemesin, bekleyen iş parçacıkları birikmesin). Süren indirme arkada tamamlanırsa sonra kullanılır.
            _SKIP["until"] = time.monotonic() + 120
        except Exception:  # noqa: BLE001 — ortak kayıt yardımcıdır: okunamazsa canlı arama yapılır
            shared = None
    shared_rows = _rows(shared, fresh)
    if local_rows and shared_rows:  # ikisi de geçerli: yeni olan
        return (shared_rows, "ortak") if float(shared.get("ts") or 0) > float(local.get("ts") or 0) else (local_rows, "yerel")
    if shared_rows:
        return shared_rows, "ortak"
    return (local_rows, "yerel") if local_rows else None


def put(query: str, provider: str, rows: list[dict]) -> None:
    """Canlı aramanın sonucu yerel kayda yazılır. Boş sonuç yazılmaz (arama sonraki sefer yeniden denenir)."""
    kept = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        url = str(r.get("url") or r.get("href") or "")
        if not url.startswith(("http://", "https://")):
            continue
        row = {"url": url[:600], "title": str(r.get("title") or "")[:200]}
        if r.get("snippet"):
            row["snippet"] = str(r["snippet"])[:400]
        if r.get("engine"):
            row["engine"] = str(r["engine"])[:40]
        kept.append(row)
        if len(kept) >= MAX_ROWS:
            break
    if not kept:
        return
    k, name = key(query), shard(query)
    with _LOCK:
        data = dict(_read_local(name))
        data[k] = {"ts": int(time.time()), "provider": provider, "rows": kept}
        if len(data) > MAX_ENTRIES:
            for old in sorted(data, key=lambda q: float((data[q] or {}).get("ts") or 0))[:len(data) - MAX_ENTRIES]:
                data.pop(old, None)
        path = DIR / (name + ".json")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            tmp.replace(path)
            _LOCAL[name] = (path.stat().st_mtime, data)
        except OSError:
            pass  # kayıt yardımcıdır: yazılamazsa arama sonucu yine kullanılır


def summary() -> dict:
    """Yerel kayıttaki sorgu ve dosya sayısı (tanı için)."""
    files = [p for p in DIR.glob("*/*.json")] if DIR.is_dir() else []
    queries = 0
    for path in files:
        try:
            queries += len(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
    return {"files": len(files), "queries": queries}
