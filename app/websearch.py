"""DDGS → isteğe bağlı Brave API → Google (Playwright/Scrapling/REA) → Brave.

Arama özetleri kanıt değildir; yalnızca kurumun kaynak sayfaları döndürülür.
Motorların süre sınırı, önbelleği ve hata bekleme süresi birbirinden bağımsızdır.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import sys
import time
from urllib.parse import quote, unquote, urldefrag, urlparse

import httpx

from .config import ROOT
from .discover import registrable
from .text import content_tokens

_CACHE: dict[tuple[str, str], tuple[float, list[dict]]] = {}
_STATE: dict = {"loop": None, "providers": {}, "queries": {}}
CACHE_TTL = 3600
EMPTY_TTL = 30
MIN_GAP = 0.5
# Motor başına iki istek arası en az süre ve aynı anda en çok istek. Brave arama sayfası hızlı ardışık istekte IP'yi
# kısıtlıyor (6 sn arayla 2. istek 429; 10 sn arayla 3 istek geçti, 2026-11-15): istekler sıraya girer, 10 sn arayla.
GAPS = {"brave_page": 10.0}
SLOTS = {"brave_page": 1}
PROVIDER_TIMEOUTS = {"serper": 6, "google_cse": 6, "ddgs": 7, "brave_api": 5, "google": 14, "brave_page": 7}


def rank_results(rows: list[dict], query: str) -> list[dict]:
    """Aramayı değiştirmez; dönen başlık/açıklamaları soruyla örtüşmesine göre sıralar."""
    terms = set(content_tokens(query))
    docs = []
    for row in rows:
        title = set(content_tokens(row.get("title", "")))
        snippet = set(content_tokens(row.get("snippet", "")))
        path = set(content_tokens(unquote(urlparse(row["url"]).path).replace("/", " ").replace("-", " ")))
        docs.append((title, snippet, path))
    frequency = {t: sum(t in (a | b | c) for a, b, c in docs) for t in terms}
    scored = []
    for index, (row, (title, snippet, path)) in enumerate(zip(rows, docs)):
        score = sum(math.log(1 + (len(rows) + 1) / (frequency[t] + 1)) *
                    (3 * (t in title) + 2 * (t in snippet) + (t in path)) for t in terms)
        if not urlparse(row["url"]).path.strip("/"):
            score -= 1  # eşit ilgi durumunda konu sayfası ana sayfanın önüne geçer
        if row.get("engine") == "google_overview":
            score += 4
        scored.append((-score, index, row))
    return [row for _, _, row in sorted(scored, key=lambda item: (item[0], item[1]))]


_SENT: dict[str, list[float]] = {}  # motor başına gerçekten gönderilen isteklerin zamanları (sunucu açıkken)


def _usage(provider: str, outcome: str, query: str, limited: bool = False) -> None:
    """Gönderilen her arama isteği data/job-log/search.log'a bir satır: motorun istek sınırını (kaç istekte 429
    verdiği) sonradan ölçmek için. Satırda son 1/10/60 dakikada ve oturumda o motora giden istek sayısı yazar."""
    now = time.time()
    sent = _SENT.setdefault(provider, [])
    sent.append(now)
    window = {m: sum(1 for t in sent if now - t <= m * 60) for m in (1, 10, 60)}
    try:
        folder = ROOT / "data" / "job-log"
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / "search.log").open("a", encoding="utf-8") as out:
            out.write("\t".join([time.strftime("%d.%m %H:%M:%S"), provider, ("SINIR " if limited else "") + outcome,
                                  f"1dk={window[1]} 10dk={window[10]} 60dk={window[60]} oturum={len(sent)}",
                                  " ".join(query.split())[:90]]) + "\n")
    except OSError:
        pass


def _state(provider: str) -> dict:
    loop = asyncio.get_running_loop()
    if _STATE["loop"] is not loop:
        _STATE.update(loop=loop, providers={}, queries={})
    return _STATE["providers"].setdefault(
        provider, {"blocked_until": 0.0, "last": 0.0, "gate": asyncio.Lock(), "slots": asyncio.Semaphore(SLOTS.get(provider, 2))})


def _site_rows(rows: list[dict], root: str) -> list[dict]:
    """Sonuç sayısı değil, hedef siteye ait geçerli bağlantılar başarı sayılır."""
    seen, out = set(), []
    for row in rows:
        try:
            url = urldefrag(row.get("url") or row.get("href") or "")[0]
            parsed = urlparse(url)
        except (ValueError, TypeError):
            continue
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme not in ("http", "https") or parsed.username or parsed.password:
            continue
        if not (host == root or host.endswith("." + root)) or url in seen:
            continue
        seen.add(url)
        out.append({**row, "url": url})
    return out


async def _ddgs_worker(query: str, backend: str) -> list[dict]:
    # Ayrı süreç sayesinde süre aşımı/iptal gerçek isteği de sonlandırır;
    # asyncio.to_thread arka planda çalışmaya devam ederdi.
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "app.search_worker",
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        cwd=str(ROOT))
    try:
        stdout, _ = await proc.communicate(json.dumps({"query": query, "backend": backend}).encode())
        if proc.returncode:
            raise RuntimeError("DDGS sorgusu tamamlanamadı")
        return json.loads(stdout)
    finally:
        if proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.communicate()


async def _ddgs(query: str) -> list[dict]:
    """DDGS'nin toplu 'auto' bekleyişi yerine iki motor yarışır; ilk site sonucu kazanır."""
    configured = os.getenv("DDGS_BACKEND", "").strip()
    backends = list(dict.fromkeys(x.strip() for x in
                                 (configured or "brave,duckduckgo,google").split(",") if x.strip()))[:3]
    root = query.split()[0].removeprefix("site:")
    pending = set()
    tasks = set()
    failures = 0
    try:
        for backend in backends[:2]:
            task = asyncio.create_task(_ddgs_worker(query, backend))
            pending.add(task)
            tasks.add(task)
        remaining = iter(backends[2:])
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                try:
                    rows = _site_rows(task.result(), root)
                except Exception:
                    failures += 1
                    rows = []
                if rows:
                    return rows
                backend = next(remaining, None)
                if backend:
                    task = asyncio.create_task(_ddgs_worker(query, backend))
                    pending.add(task)
                    tasks.add(task)
        if failures == len(backends):
            raise RuntimeError("DDGS motorları yanıt vermedi")
        return []
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def _brave_api(query: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=4) as client:
        response = await client.get(
            "https://api.search.brave.com/res/v1/web/search", params={"q": query, "count": 10},
            headers={"X-Subscription-Token": os.environ["BRAVE_API_KEY"], "Accept": "application/json"})
        response.raise_for_status()
        return [{"url": x.get("url", ""), "title": x.get("title", "")}
                for x in response.json().get("web", {}).get("results", [])]


def _keys() -> dict:
    from . import ai_settings
    return ai_settings.search()


async def search_check() -> dict:
    """Ayarlar sayfasındaki "Dene" düğmesi: kayıtlı her arama servisine tek bir sorgu atar, sonucu kısa metinle döndürür."""
    keys, out = _keys(), {}
    for name, ready, call in (("serper", keys["serper_key"], _serper),
                              ("google_cse", keys["google_cse_key"] and keys["google_cse_cx"], _google_cse)):
        if not ready:
            out[name] = "Anahtar yok" if name == "serper" or not keys["google_cse_key"] else "Arama motoru kimliği (cx) yok"
            continue
        try:
            rows = await asyncio.wait_for(call("site:metu.edu.tr ders programı"), 8)
            out[name] = f"Çalışıyor · {len(rows)} sonuç"
            _STATE["providers"].pop(name, None)  # önceki hata beklemesi kalkar
        except Exception as exc:  # noqa: BLE001
            out[name] = f"Hata: {type(exc).__name__} {str(exc)[:80]}"
    return out


async def _serper(query: str) -> list[dict]:
    """Serper.dev (Google sonuçları, JSON). Anahtar Ayarlar sayfasından (ai_settings.search); hata iletisine yazılmaz."""
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.post("https://google.serper.dev/search", json={"q": query, "num": 10, "gl": "tr", "hl": "tr"},
                                     headers={"X-API-KEY": _keys()["serper_key"], "Content-Type": "application/json"})
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code}")  # 429: istek sınırı; 400/403: kredi bitti ya da anahtar geçersiz
    return [{"url": x.get("link", ""), "title": x.get("title", ""), "snippet": x.get("snippet", "")}
            for x in response.json().get("organic", []) if isinstance(x, dict)]


async def _google_cse(query: str) -> list[dict]:
    """Google Custom Search JSON API: API anahtarı ve arama motoru kimliği (cx) Ayarlar sayfasından; ikisi de yoksa bu
    sağlayıcı kullanılmaz. Anahtar sorgu parametresinde gittiği için hata iletisine adres yazılmaz."""
    async with httpx.AsyncClient(timeout=5) as client:
        response = await client.get("https://www.googleapis.com/customsearch/v1", params={
            "key": _keys()["google_cse_key"], "cx": _keys()["google_cse_cx"], "q": query, "num": 10})
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code}")  # 429: günlük kota doldu
    return [{"url": x.get("link", ""), "title": x.get("title", ""), "snippet": x.get("snippet", "")}
            for x in response.json().get("items", []) if isinstance(x, dict)]


async def _brave_page(query: str) -> list[dict]:
    from .net import _stealth_session

    session = await _stealth_session()
    response = await session.fetch(f"https://search.brave.com/search?q={quote(query)}&source=web",
                                   network_idle=False, wait=600, timeout=6000)
    if response.status >= 400:
        headers = {str(k).lower(): v for k, v in (getattr(response, "headers", None) or {}).items()}
        wait = headers.get("retry-after") or headers.get("x-ratelimit-reset") or ""
        raise RuntimeError(f"HTTP {response.status}" + (f" (bekle: {wait})" if wait else ""))
    return [{"url": a.attrib.get("href", ""), "title": a.get_all_text(strip=True)[:160]}
            for a in response.css("a[href^='http']")]


async def _google(query: str, log=None) -> list[dict]:
    from .google_search import search

    result = await search(query, log)
    # Arama özeti yerine kaynak sayfaları döndürülür.
    return result["results"]


async def _provider(provider: str, query: str, log=None) -> list[dict]:
    state = _state(provider)
    key = (provider, query)
    # Aynı anda gelen aynı sorgu tek istek yapar; farklı sorgular iki slotta çalışır.
    locks = _STATE["queries"]
    lock, users = locks.setdefault(key, [asyncio.Lock(), 0])
    locks[key][1] = users + 1
    try:
        async with lock:
            hit = _CACHE.get(key)
            if hit and time.monotonic() - hit[0] < (CACHE_TTL if hit[1] else EMPTY_TTL):
                return hit[1]
            if time.monotonic() < state["blocked_until"]:
                return []
            try:
                async with state["slots"]:
                    # Sıra beklemesi motorun süre sınırına sayılmaz; süre sınırı yalnız isteğin kendisine uygulanır.
                    async with state["gate"]:
                        wait = GAPS.get(provider, MIN_GAP) - (time.monotonic() - state["last"])
                        if wait > 0:
                            await asyncio.sleep(wait)
                        if time.monotonic() < state["blocked_until"]:
                            return []  # beklerken başka bir istek 429 aldı: motor dinleniyor
                        state["last"] = time.monotonic()
                    started = time.monotonic()
                    async with asyncio.timeout(PROVIDER_TIMEOUTS[provider]):
                        if provider == "google":
                            rows = await _google(query, log)
                        else:
                            rows = await {"serper": _serper, "google_cse": _google_cse, "ddgs": _ddgs, "brave_api": _brave_api,
                                          "brave_page": _brave_page}[provider](query)
            except Exception as exc:  # bir motor diğer motorları devre dışı bırakmaz
                # Google bot kontrolü saatlerce sürer; her aramada yeniden denemek ~5 sn kaybettirir. İstek sınırı (429)
                # IP başınadır ve dakikalarca sürer: motor 30 dk dinlendirilir (sınırı uzatmamak için).
                limited = any(code in str(exc) for code in ("HTTP 429", "HTTP 402", "HTTP 403"))  # istek sınırı ya da biten kota
                state["blocked_until"] = time.monotonic() + (3600 if type(exc).__name__ == "GoogleBlocked"
                                                             else 1800 if limited else 60)
                _usage(provider, f"HATA {type(exc).__name__}: {str(exc)[:80]}", query, limited)
                if log:
                    await log(f"Arama · {provider}: {type(exc).__name__}: {str(exc)[:160]}; diğer yöntemlere geçiliyor.")
                return []
            _usage(provider, f"{len(rows)} sonuç", query)
            if len(_CACHE) >= 512:
                _CACHE.pop(next(iter(_CACHE)))
            _CACHE[key] = (time.monotonic(), rows)
            if log:
                await log(f"Arama · {provider}: {len(rows)} sonuç, {time.monotonic() - started:.1f} sn.")
            return rows
    finally:
        locks[key][1] -= 1
        if not locks[key][1]:
            locks.pop(key)


def provider_order() -> tuple[str, ...]:
    # Anahtarlı arama servisleri (tarayıcı gerektirmez, engellenmez) önce; anahtar yoksa listeye girmezler.
    keys = _keys()
    providers = (("serper",) if keys["serper_key"] else ()) \
        + (("google_cse",) if keys["google_cse_key"] and keys["google_cse_cx"] else ())
    providers += ("ddgs",) + (("brave_api",) if os.getenv("BRAVE_API_KEY") else ())
    if os.getenv("GOOGLE_SEARCH_ENABLED", "1").lower() not in ("0", "false", "off"):
        providers += ("google",)
    return providers + ("brave_page",)


async def site_results(domain_url: str, query: str, log=None, k: int = 6,
                       *, providers: tuple[str, ...] | None = None) -> list[dict]:
    """Başlık/açıklama/kaynak bağlantısını birlikte korur; site: kapsamı değişmez."""
    root = registrable(urlparse(domain_url).hostname or "")
    if not root or not query.strip() or k <= 0:
        return []
    q = f"site:{root} {' '.join(query.split())}"
    providers = provider_order() if providers is None else providers
    for provider in providers:
        rows = _site_rows(await _provider(provider, q, log), root)
        if rows:
            return rank_results(rows, query)[:k]
    return []


async def site_results_race(domain_url: str, query: str, log=None, k: int = 6) -> list[dict]:
    """site_results gibi, ama motorlar sırayla değil aynı anda sorulur; hedef siteden sonuç veren ilk motor kullanılır.
    Diğerleri iptal edilmez (yarıda kesilen tarayıcı oturumu bırakmamak için); sonuçları önbelleğe yazılır."""
    root = registrable(urlparse(domain_url).hostname or "")
    if not root or not query.strip() or k <= 0:
        return []
    q = f"site:{root} {' '.join(query.split())}"
    tasks = [asyncio.create_task(_provider(provider, q, log)) for provider in provider_order()]
    for done in asyncio.as_completed(tasks):
        try:
            rows = _site_rows(await done, root)
        except Exception:
            continue
        if rows:
            return rank_results(rows, query)[:k]
    return []


async def site_search(domain_url: str, query: str, log=None, k: int = 6,
                      *, providers: tuple[str, ...] | None = None) -> list[str]:
    return [r["url"] for r in await site_results(domain_url, query, log, k, providers=providers)]
