"""Ders bilgi paketi yapısı bilinen üniversiteler: ders planı keşif yapılmadan, bilinen adreslerden doğrudan okunur.

Her üniversite bu klasörde bir modüldür ve üç işlev sunar (hepsi `base.Http` ile istek atar):

    DOMAINS = ("metu.edu.tr",)                      # kurumun alan adları (ilki ana alan adı)
    async def programs(http) -> list[dict]          # lisans programları: {"name", "faculty", "url", "aliases"?, …}
    async def courses(http, program) -> list[dict]  # programın dersleri: base.course(...) kayıtları
    async def detail(http, url) -> dict | None      # (isteğe bağlı) tek dersin içeriği: base.detail(...)

Sıra (student_view.get): hazır veri seti → bu modül → genel keşif. Program listesi 30 gün, ders içerikleri 30 gün
diskte tutulur; ders planı geldikten sonra derslerin içerikleri arka planda önceden indirilir (tıklayınca anında açılır).
"""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import importlib
import json
import logging
import time
from urllib.parse import urlsplit

import httpx

from ..discover import registrable
from . import base

log = logging.getLogger(__name__)

# alan adı → modül adı
MODULES = {
    "bogazici.edu.tr": "boun", "boun.edu.tr": "boun",
    "ege.edu.tr": "ege",
    "deu.edu.tr": "deu",
    "baskent.edu.tr": "baskent",
    "marmara.edu.tr": "marmara",
    "ktu.edu.tr": "ktu",
    "etu.edu.tr": "tobb",
    "sabanciuniv.edu": "sabanci",
    "gtu.edu.tr": "gtu",
    "metu.edu.tr": "odtu",
    "itu.edu.tr": "itu",
    "gsu.edu.tr": "gsu",
    "tedu.edu.tr": "tedu",
    "ku.edu.tr": "koc",
    "fbu.edu.tr": "fbu", "fenerbahce.edu.tr": "fbu",
    "ostimteknik.edu.tr": "ostim",
    "bilkent.edu.tr": "bilkent",
    "hacettepe.edu.tr": "hacettepe",
    "ankara.edu.tr": "ankara",
    "ankarabilim.edu.tr": "ankarabilim",
}
PROGRAM_TTL = 30 * 24 * 3600
DETAIL_TTL = 30 * 24 * 3600
_LOADED: dict[str, object] = {}
_LOCKS: dict[str, asyncio.Lock] = {}
_WARMING: dict[str, asyncio.Task] = {}


def _domain(home_or_url: str) -> str:
    return registrable(urlsplit(home_or_url if "://" in home_or_url else "https://" + home_or_url).hostname or "")


def module(home_or_url: str):
    """Kurumun modülü; yoksa ya da yüklenemiyorsa None."""
    name = MODULES.get(_domain(home_or_url))
    if not name:
        return None
    if name not in _LOADED:
        try:
            _LOADED[name] = importlib.import_module(f"{__name__}.{name}")
        except Exception as exc:  # noqa: BLE001 — eksik ya da bozuk modül genel keşfi engellemez
            log.warning("ders bilgi paketi modülü yüklenemedi: %s (%s)", name, exc)
            _LOADED[name] = None
    return _LOADED[name]


def has(home_or_url: str) -> bool:
    return module(home_or_url) is not None


@contextlib.asynccontextmanager
async def _open(mod, fresh: bool = False):
    from ..org_assets import public_client
    client = public_client(timeout=httpx.Timeout(20, connect=8), headers=base.HEADERS,
                           limits=httpx.Limits(max_connections=12, max_keepalive_connections=8))
    http = base.Http(client, mod.DOMAINS, limit=getattr(mod, "PARALLEL", 6), fresh=fresh)
    try:
        yield http
    finally:
        await http.client.aclose()


def _read(path, ttl: float):
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        return saved["data"] if time.time() - saved.get("ts", 0) < ttl else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _write(path, data) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"ts": time.time(), "data": data}, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


async def _programs(mod, http, force: bool = False) -> list[dict]:
    name = mod.__name__.rsplit(".", 1)[-1]
    path = base.CACHE / f"{name}-programs.json"
    async with _LOCKS.setdefault(name, asyncio.Lock()):  # aynı anda açılan bölümler listeyi bir kez indirir
        rows = None if force else _read(path, PROGRAM_TTL)
        if not rows:
            rows = [row for row in await mod.programs(http) if isinstance(row, dict) and row.get("name")]
            if rows:
                _write(path, rows)
    return rows or []


async def lookup(home: str, faculty: str, department: str, refresh: bool = False) -> dict | None:
    """Bölümün ders planı: {"group": ders grubu, "program": program kaydı, "requests": istek sayısı} ya da None
    (modül yok, program listede bulunamadı ya da ders planı okunamadı — çağıran genel keşfe geçer)."""
    mod = module(home)
    if mod is None or not department:
        return None
    async with _open(mod, fresh=refresh) as http:
        rows = await _programs(mod, http)
        found = base.candidates(rows, faculty, department)
        if not found and (refresh or http.requests == 0):
            # Liste önbellekten geldi ve bölüm içinde yok: yeni açılmış program olabilir, liste bir kez yenilenir.
            rows = await _programs(mod, http, force=True)
            found = base.candidates(rows, faculty, department)
        program, items = None, []
        # Tek aday kesin eşleşmedir. Aynı adlı program birden çok fakültedeyse (kurum fakülteyi bölmüş ya da taşımış)
        # adaylar olasılık sırasıyla denenir; ders planı olan ilk aday alınır (eski kayıtların planı çoğu kez boştur).
        for program in found[:3]:
            items = [item for item in await mod.courses(http, program) if isinstance(item, dict) and item.get("title")]
            if len(items) >= base.MIN_COURSES:
                break
        requests = http.requests
    if program is None or len(items) < base.MIN_COURSES:
        return None
    items = _yearly(items)
    links = [{"title": "Ders bilgi paketi", "url": program["url"]}] if program.get("url") else []
    group = {"title": "Dersler ve içerikleri", "format": "course_catalog", "source": "catalog", "links": links, "items": items}
    return {"group": group, "program": program, "requests": requests}


def _yearly(items: list[dict]) -> list[dict]:
    """Yıllık okutulan programlar (Hukuk, Tıp): site yılları 1, 3, 5… numaralı dönem olarak verir. Dönemli derslerin
    hepsi tek numaralıysa ve en az üç ayrı yıl varsa etiketler "1. sınıf dersleri", "2. sınıf dersleri"… yapılır."""
    import re
    numbers = {int(m[1]) for item in items if (m := re.fullmatch(r"(\d+)\. dönem", item.get("period") or ""))}
    if len(numbers) < 3 or any(n % 2 == 0 for n in numbers):
        return items
    return [{**item, "period": f"{(int(m[1]) + 1) // 2}. sınıf dersleri"}
            if (m := re.fullmatch(r"(\d+)\. dönem", item.get("period") or "")) else item for item in items]


def _detail_path(url: str):
    return base.CACHE / "details" / f"{hashlib.sha256(url.encode()).hexdigest()[:32]}.json"


async def course_detail(home: str, url: str, http=None) -> dict | None:
    """Tek dersin içeriği (arayüzün ders kartı biçimi); modül bu adresi tanımıyorsa ya da içerik yoksa None."""
    mod = module(home)
    if mod is None or not hasattr(mod, "detail") or _domain(url) not in mod.DOMAINS:
        return None
    path = _detail_path(url)
    saved = _read(path, DETAIL_TTL)
    if saved:
        return saved
    if http is not None:
        data = await mod.detail(http, url)
    else:
        async with _open(mod) as own:
            data = await mod.detail(own, url)
    if data:
        _write(path, data)
    return data


def warm(home: str, items: list[dict]) -> None:
    """Ders planındaki derslerin içeriklerini arka planda önceden indirir (aynı anda en çok üç istek). Kullanıcı bir
    dersi açtığında içerik diskten gelir. Aynı kurum için tek ön yükleme çalışır; yenisi sıraya eklenmez."""
    mod = module(home)
    if mod is None or not hasattr(mod, "detail"):
        return
    name = mod.__name__
    if (task := _WARMING.get(name)) is not None and not task.done():
        return
    urls = list(dict.fromkeys(item.get("detail_url") for item in items if item.get("detail_url")))
    urls = [url for url in urls if _read(_detail_path(url), DETAIL_TTL) is None][:400]
    if not urls:
        return

    async def run():
        gate = asyncio.Semaphore(getattr(mod, "WARM_PARALLEL", 3))
        async with _open(mod) as http:
            async def one(url):
                async with gate:
                    try:
                        await course_detail(home, url, http)
                    except Exception:  # noqa: BLE001 — tek dersin hatası ön yüklemeyi durdurmaz
                        pass
            await asyncio.gather(*(one(url) for url in urls))

    _WARMING[name] = asyncio.create_task(run())
