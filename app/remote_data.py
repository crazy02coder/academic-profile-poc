"""Uzak hazır veri: GitHub Pages'te statik JSON servisi olarak yayımlanan dosyalar (veri deposu: akademik-iz-data).

Uygulama hazır veri dosyalarını (ders veri seti, Ar-Ge merkezleri, üniversite logoları, dergi çeyrekleri) diskte taşımaz;
ilk gerektiğinde HTTPS ile indirir ve data/remote/ altında saklar. Yayın kökündeki manifest.json her dosyanın SHA-256
özetini verir: dosya yalnız özeti değiştiğinde yeniden indirilir, indirilen dosya özetle doğrulanır.

İnternet yoksa ya da yayın erişilemezse daha önce indirilmiş kopya kullanılır; o da yoksa (geliştirme ortamı) data/
altındaki yerel dosya. Yayın adresi AKADEMIK_IZ_DATA_URL ortam değişkeniyle değiştirilebilir; "off" yazılırsa uzak veri
hiç kullanılmaz.

Arayüz istekleri beklemesin diye sunucu açılırken prefetch() küçük dosyaları ve dergi çeyreklerini arka planda indirir;
üniversite dosyaları (her biri ~100 KB) ilk açıldıklarında tek tek iner.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import shutil
import threading
import time
from pathlib import Path

import certifi
import httpx

from .config import ROOT

BASE = os.getenv("AKADEMIK_IZ_DATA_URL", "https://crazy02coder.github.io/akademik-iz-data/").rstrip("/") + "/"
ENABLED = BASE.lower() not in {"off/", "0/", "false/"}
CACHE = ROOT / "data" / "remote"
LOCAL = ROOT / "data"  # yayın öncesi yerel kopyalar (geliştirme ortamı)
MANIFEST_TTL = 6 * 3600
# Sıkıştırılmış yayımlanan dosya → diskte açılmış hali (SQLite doğrudan dosyadan okunur).
PACKED = {"journal_quartiles.sqlite": "journal_quartiles.sqlite.gz"}
log = logging.getLogger(__name__)
_LOCK = threading.Lock()
_FILE_LOCKS: dict[str, threading.Lock] = {}
_STATE: dict = {"manifest": None, "at": 0.0, "failed_at": 0.0}


def _client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(60, connect=10), follow_redirects=True, verify=certifi.where(),
                        headers={"User-Agent": "AkademikIz/2.0 (data client)"})


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def manifest() -> dict:
    """{yol: {"size", "sha256"}}; uzak yayın yoksa son indirilen manifest, o da yoksa boş."""
    if not ENABLED:
        return {}
    with _LOCK:
        now = time.time()
        if _STATE["manifest"] is not None and now - _STATE["at"] < MANIFEST_TTL:
            return _STATE["manifest"]
        saved = CACHE / "manifest.json"
        if _STATE["manifest"] is None:
            try:
                _STATE["manifest"] = json.loads(saved.read_text(encoding="utf-8")).get("files") or {}
                _STATE["at"] = saved.stat().st_mtime
                if now - _STATE["at"] < MANIFEST_TTL:
                    return _STATE["manifest"]
            except (OSError, ValueError, AttributeError):
                _STATE["manifest"] = None
        if now - _STATE["failed_at"] < 120:  # yayın az önce erişilemedi: her istekte yeniden beklenmez
            return _STATE["manifest"] or {}
        try:
            with _client() as client:
                response = client.get(BASE + "manifest.json")
                response.raise_for_status()
                data = response.json()
            files = data.get("files") if isinstance(data, dict) else None
            if not isinstance(files, dict):
                raise ValueError("manifest biçimi beklenmedik")
            CACHE.mkdir(parents=True, exist_ok=True)
            tmp = saved.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            tmp.replace(saved)
            _STATE.update(manifest=files, at=now)
        except (httpx.HTTPError, ValueError, OSError) as exc:
            log.warning("Uzak veri listesi alınamadı (%s); indirilmiş kopyalar kullanılacak.", type(exc).__name__)
            _STATE["failed_at"] = now
        return _STATE["manifest"] or {}


def has(rel: str) -> bool:
    """Dosya yayında ya da diskte var mı (indirmeden)."""
    rel = PACKED.get(rel, rel)
    return rel in manifest() or (CACHE / rel).is_file() or (LOCAL / _unpacked(rel)).is_file()


def listed(prefix: str) -> list[str]:
    """Yayında (ya da indirilmiş kopyalar arasında) prefix ile başlayan dosyalar."""
    names = {rel for rel in manifest() if rel.startswith(prefix)}
    names |= {p.relative_to(CACHE).as_posix() for p in (CACHE / prefix).parent.glob("*") if p.is_file()} if (CACHE / prefix).parent.is_dir() else set()
    names |= {p.relative_to(LOCAL).as_posix() for p in (LOCAL / prefix).parent.glob("*") if p.is_file()} if (LOCAL / prefix).parent.is_dir() else set()
    return sorted(n for n in names if n.startswith(prefix))


def _unpacked(rel: str) -> str:
    return next((name for name, packed in PACKED.items() if packed == rel), rel)


def path(rel: str) -> Path | None:
    """Dosyanın diskteki yolu: gerekirse indirir (ve sıkıştırılmış yayımlananı açar). Bulunamazsa None.

    Ağ isteği yapabilir; olay döngüsünden değil iş parçacığından çağrılmalıdır (asyncio.to_thread)."""
    published = PACKED.get(rel, rel)
    target = CACHE / rel  # açılmış hali (sıkıştırılmamış dosyalarda yayımlananla aynı)
    entry = manifest().get(published)
    with _LOCK:
        lock = _FILE_LOCKS.setdefault(rel, threading.Lock())
    with lock:
        stamp = target.with_name(target.name + ".sha256")
        if entry:
            try:
                if target.is_file() and stamp.read_text(encoding="ascii").strip() == entry["sha256"]:
                    return target
            except OSError:
                pass
            try:
                return _download(published, rel, entry, target, stamp)
            except (httpx.HTTPError, ValueError, OSError) as exc:
                log.warning("Uzak veri indirilemedi: %s (%s)", published, type(exc).__name__)
        if target.is_file():
            return target  # eski ama elde olan kopya
        local = LOCAL / rel
        return local if local.is_file() else None


def ready(rel: str) -> Path | None:
    """Ağ beklemeden: dosya diskte hazırsa yolu; değilse None döner ve indirmeyi arka planda başlatır
    (olay döngüsünden çağrılan, veri gelene kadar onsuz çalışabilen yerler için: dergi çeyrekleri)."""
    target = CACHE / rel
    if target.is_file():
        return target
    if ENABLED:
        threading.Thread(target=path, args=(rel,), name="remote-data-fetch", daemon=True).start()
    local = LOCAL / rel
    return local if local.is_file() else None


def _download(published: str, rel: str, entry: dict, target: Path, stamp: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    part = CACHE / (published + ".part")
    part.parent.mkdir(parents=True, exist_ok=True)
    with _client() as client, client.stream("GET", BASE + published) as response:
        response.raise_for_status()
        with part.open("wb") as out:
            for chunk in response.iter_bytes(1 << 16):
                out.write(chunk)
    if _sha256(part) != entry["sha256"]:
        part.unlink(missing_ok=True)
        raise ValueError("özet tutmuyor")
    if published != rel:  # sıkıştırılmış yayımlanan: açılıp yazılır
        tmp = target.with_name(target.name + ".tmp")
        with gzip.open(part, "rb") as src, tmp.open("wb") as dst:
            shutil.copyfileobj(src, dst, 1 << 20)
        part.unlink(missing_ok=True)
        tmp.replace(target)
    else:
        part.replace(target)
    stamp.write_text(entry["sha256"], encoding="ascii")
    return target


def prefetch() -> None:
    """Sunucu açılırken arka planda: liste, küçük dosyalar ve dergi çeyrekleri (arayüz istekleri beklemesin)."""
    def run():
        for rel in ("arge_merkezleri.json", "yok_university_logos.json", "poc/universities.json", "journal_quartiles.sqlite"):
            try:
                path(rel)
            except Exception:  # noqa: BLE001 — ön yükleme yardımcıdır
                pass
    if ENABLED:
        threading.Thread(target=run, name="remote-data-prefetch", daemon=True).start()
