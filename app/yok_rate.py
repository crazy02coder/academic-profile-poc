"""yok.gov.tr (akademik, tez, açık bilim…) için tek, süreçler arası hız sınırlayıcı.

İki istek arası en az RATE_GAP saniye, 60 saniyede en fazla RATE_PER_MIN istek. Zaman damgaları
data/yok/_rate.json'da, dosya kilidiyle (fcntl) paylaşılır; aynı makinedeki tüm uvicorn/betik süreçleri
aynı bütçeyi kullanır. httpx istemcilerine `event_hooks=HOOKS` ile bağlanır: yönlendirmeler dahil
yok.gov.tr'ye giden her istek sayılır, başka alan adları etkilenmez.
"""
from __future__ import annotations

import asyncio
import fcntl
import json
import time

from .config import ROOT

DIR = ROOT / "data" / "yok"
RATE_GAP = 2.0
RATE_PER_MIN = 20
_RATE_FILE = DIR / "_rate.json"
_LOCK_FILE = DIR / "_rate.lock"


def is_yok(host: str | None) -> bool:
    host = (host or "").lower().rstrip(".")
    return host == "yok.gov.tr" or host.endswith(".yok.gov.tr")


def _reserve() -> float:
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
            if stamps:
                wait = max(wait, stamps[-1] + RATE_GAP - now)
            if len(stamps) >= RATE_PER_MIN:
                wait = max(wait, stamps[-RATE_PER_MIN] + 60 - now)
            if wait > 0:
                return wait
            stamps.append(now)
            tmp = _RATE_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps(stamps[-RATE_PER_MIN * 2:]))
            tmp.replace(_RATE_FILE)
            return 0.0
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


async def throttle() -> None:
    while (wait := await asyncio.to_thread(_reserve)) > 0:
        await asyncio.sleep(min(wait, 5) + 0.05)


def throttle_sync() -> None:
    """Tarayıcı (REA/StealthBridge) gibi httpx dışı, eşzamanlı yollar için."""
    while (wait := _reserve()) > 0:
        time.sleep(min(wait, 5) + 0.05)


async def _hook(request) -> None:
    if is_yok(request.url.host):
        await throttle()


HOOKS = {"request": [_hook]}
