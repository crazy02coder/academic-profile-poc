"""yok.gov.tr (akademik, tez, açık bilim…) için tek, süreçler arası hız sınırlayıcı.

İki istek arası en az ve 60 saniyede en fazla istek sayısı Ayarlar'daki YÖK hızı kademesinden (1-5) gelir. Zaman damgaları
data/yok/_rate.json'da, dosya kilidiyle (fcntl) paylaşılır; aynı makinedeki tüm uvicorn/betik süreçleri
aynı bütçeyi kullanır. httpx istemcilerine `event_hooks=HOOKS` ile bağlanır: yönlendirmeler dahil
yok.gov.tr'ye giden her istek sayılır, başka alan adları etkilenmez.
"""
from __future__ import annotations

import asyncio
import contextvars
import fcntl
import json
import time

from .config import ROOT

DIR = ROOT / "data" / "yok"
# Hız kademesi (Ayarlar → YÖK hızı, 1-5): (iki istek arası saniye, dakikada en fazla istek).
# 2 varsayılan ve güvenli; 4-5 hızlıdır ama IP engeli riski artar. Profil gibi acil istekler bir üst kademeden çalışır.
LEVELS = {1: (3.0, 12), 2: (2.0, 20), 3: (1.5, 30), 4: (1.0, 40), 5: (0.6, 60)}
DEFAULT_LEVEL = 2
SETTINGS = ROOT / ".app-settings.json"
RATE_GAP, RATE_PER_MIN = LEVELS[DEFAULT_LEVEL]
_level_cache = {"mtime": None, "level": DEFAULT_LEVEL}
_RATE_FILE = DIR / "_rate.json"
_LOCK_FILE = DIR / "_rate.lock"
# Kullanıcının beklediği küçük istekler (ör. bölüm listesi) arka plan taramalarının arkasında kalmasın:
# acil istek varken diğerleri sırasını ona bırakır; dakikalık bütçenin son URGENT_ROOM'u yalnız acil isteklere açık.
URGENT = contextvars.ContextVar("yok_urgent", default=False)
URGENT_ROOM = 4
_urgent_waiting = 0


def level() -> int:
    """Kayıtlı kademe; dosya değişmedikçe yeniden okunmaz."""
    try:
        mtime = SETTINGS.stat().st_mtime
    except OSError:
        return DEFAULT_LEVEL
    if mtime != _level_cache["mtime"]:
        try:
            value = int(json.loads(SETTINGS.read_text(encoding="utf-8")).get("yok_speed", DEFAULT_LEVEL))
        except (OSError, ValueError, TypeError, AttributeError):
            value = DEFAULT_LEVEL
        _level_cache.update(mtime=mtime, level=value if value in LEVELS else DEFAULT_LEVEL)
    return _level_cache["level"]


def set_level(value: int) -> int:
    if value not in LEVELS:
        raise ValueError("YÖK hızı 1 ile 5 arasında olmalı.")
    try:
        data = json.loads(SETTINGS.read_text(encoding="utf-8"))
        data = data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        data = {}
    data["yok_speed"] = value
    tmp = SETTINGS.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(SETTINGS)
    return value


def limits(urgent: bool = False) -> tuple[float, int]:
    """(aralık, dakikalık sınır). Acil istekler bir üst kademe; arka plan acile URGENT_ROOM kadar yer bırakır."""
    base = level()
    if urgent:
        return LEVELS[min(base + 1, 5)]
    gap, per_min = LEVELS[base]
    return gap, max(per_min - URGENT_ROOM, 4)


def is_yok(host: str | None) -> bool:
    host = (host or "").lower().rstrip(".")
    return host == "yok.gov.tr" or host.endswith(".yok.gov.tr")


def _reserve(urgent: bool = False) -> float:
    """Yer varsa şimdiye bir istek yazar ve 0 döndürür; yoksa beklenmesi gereken saniyeyi döndürür."""
    DIR.mkdir(parents=True, exist_ok=True)
    with open(_LOCK_FILE, "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            try:
                stamps = [float(t) for t in json.loads(_RATE_FILE.read_text())]
            except (OSError, ValueError, TypeError):
                stamps = []
            now = time.time()
            stamps = sorted(t for t in stamps if now - 60 < t <= now + 1)
            wait = 0.0
            gap, limit = limits(urgent)
            if stamps:
                wait = max(wait, stamps[-1] + gap - now)
            if len(stamps) >= limit:
                wait = max(wait, stamps[-limit] + 60 - now)
            if wait > 0:
                return wait
            stamps.append(now)
            tmp = _RATE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(stamps[-120:]))
            tmp.replace(_RATE_FILE)
            return 0.0
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


async def throttle() -> None:
    global _urgent_waiting
    if URGENT.get():
        _urgent_waiting += 1
        try:
            while (wait := await asyncio.to_thread(_reserve, True)) > 0:
                await asyncio.sleep(min(wait, 1) + 0.02)
        finally:
            _urgent_waiting -= 1
        return
    while True:
        while _urgent_waiting:
            await asyncio.sleep(0.25)
        wait = await asyncio.to_thread(_reserve)
        if wait <= 0:
            return
        await asyncio.sleep(min(wait, 5) + 0.05)


def throttle_sync() -> None:
    """Tarayıcı (REA/StealthBridge) gibi httpx dışı, eşzamanlı yollar için. asyncio.to_thread bağlamı taşıdığından
    profil işi gibi öncelikli işlerin istekleri burada da öncelikli sayılır."""
    urgent = URGENT.get()
    while (wait := _reserve(urgent)) > 0:
        time.sleep(min(wait, 1 if urgent else 5) + 0.05)


async def _hook(request) -> None:
    if is_yok(request.url.host):
        await throttle()


HOOKS = {"request": [_hook]}
