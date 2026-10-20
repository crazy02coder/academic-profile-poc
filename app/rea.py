"""REA (morluto/rea) entegrasyonu.

İki kullanım biçimi:
  * recon()        — REA kendi Chromium'unu başlatır (capture-browser-scenario,
                     mode=launch); sayfanın render edilmiş DOM'unu ve TÜM ağ
                     trafiğini (XHR/fetch gövdeleri dahil) Evidence olarak döndürür.
                     Böylece içeriğin sunucu HTML'inden mi yoksa gizli bir JSON
                     API'sinden mi geldiği anlaşılır.
  * StealthBridge  — Scrapling StealthySession (Patchright) bot duvarını geçer ve
                     CDP portunu açar; REA aynı tarayıcıya 'connect' moduyla
                     bağlanıp etkileşimli senaryoyu (form doldur, gönder) çalıştırır
                     ve formun arkasındaki gizli isteği (yöntem, URL, gövde) çözer.
                     Sonraki sayfalar yine Scrapling ile, aynı oturumla çekilir.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import socket
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .config import chromium_executable, rea_command

NOISE_HOSTS = ("google-analytics", "googletagmanager", "doubleclick", "facebook", "hotjar", "clarity.ms",
               "yandex", "gstatic", "fonts.googleapis", "cloudflareinsights", "tiktok", "linkedin",
               "analytics.google", "www.google.com", "adservice", "googlesyndication", "youtube")


@dataclass
class Transaction:
    id: str
    method: str
    url: str
    resource_type: str
    status: int | None = None
    failure: str | None = None
    request_body: str | None = None
    response_body: bytes | None = None
    media_type: str = ""

    @property
    def is_noise(self) -> bool:
        host = urlparse(self.url).hostname or ""
        return any(n in host for n in NOISE_HOSTS)

    def json(self):
        if self.response_body is None:
            return None
        try:
            return json.loads(self.response_body.decode("utf-8", "replace"))
        except ValueError:
            return None


@dataclass
class Capture:
    ok: bool
    dom: str = ""
    final_url: str = ""
    duration_ms: int = 0
    transactions: list[Transaction] = field(default_factory=list)
    error: str = ""
    evidence_id: str = ""

    @property
    def documents(self) -> list[Transaction]:
        return [t for t in self.transactions if t.resource_type == "document" and not t.is_noise]

    @property
    def api_calls(self) -> list[Transaction]:
        return [t for t in self.transactions if t.resource_type in ("xhr", "fetch") and not t.is_noise]

    @property
    def json_endpoints(self) -> list[Transaction]:
        return [t for t in self.api_calls if t.json() is not None]

    def summary(self) -> dict:
        return {
            "evidence_id": self.evidence_id,
            "duration_ms": self.duration_ms,
            "requests": len(self.transactions),
            "documents": [{"method": t.method, "url": t.url, "status": t.status,
                           "body": (t.request_body or "")[:300]} for t in self.documents][:12],
            "api_calls": [{"method": t.method, "url": t.url, "status": t.status,
                           "json": t.json() is not None} for t in self.api_calls][:25],
            "third_party": len([t for t in self.transactions if t.is_noise]),
        }


def available() -> bool:
    return rea_command() is not None


def _parse(raw: str) -> Capture:
    try:
        doc = json.loads(raw)
    except ValueError:
        return Capture(ok=False, error="REA çıktısı JSON değil")
    result = doc.get("normalized_result")
    nested_error = result if isinstance(result, dict) and (result.get("error") or result.get("code")) else None
    error_doc = nested_error or (doc.get("error") if isinstance(doc.get("error"), dict) else doc)
    ok = isinstance(result, dict) and nested_error is None
    if not ok:
        partial = (error_doc.get("details") or {}).get("partial_observation") or {}
        result = partial.get("capture") or partial.get("normalized_result") or (partial if "steps" in partial else {})
    detail = error_doc.get("details") or {}
    diagnostic = {k: error_doc[k] for k in ("code", "category") if error_doc.get(k)}
    diagnostic.update({k: detail[k] for k in ("provider_id", "operation", "reason", "execution_failure", "diagnostics")
                       if detail.get(k) is not None})
    message = error_doc.get("message") or error_doc.get("error") or "REA hatası"
    error = str(message)
    if diagnostic:
        error = json.dumps(diagnostic, ensure_ascii=False)[:600] + " · " + error
    cap = Capture(ok=ok, evidence_id=doc.get("evidence_id", ""), duration_ms=result.get("duration_ms", 0),
                  error="" if ok else error)
    tx: dict[str, Transaction] = {}
    for ev in (result.get("events") or {}).get("items", []):
        tid = ev.get("transaction_id")
        if not tid:
            continue
        kind = ev.get("kind")
        if kind == "request":
            tx[tid] = Transaction(id=tid, method=ev.get("method", "GET"), url=(ev.get("url") or {}).get("url", ""),
                                  resource_type=ev.get("resource_type", ""))
        elif kind == "response" and tid in tx:
            tx[tid].status = ev.get("status")
        elif kind == "request-failed" and tid in tx:
            tx[tid].failure = ev.get("failure")
        elif kind == "network-content" and tid in tx:
            body = ev.get("body") or {}
            if body.get("state") != "captured":
                continue
            data = base64.b64decode(body.get("content", "")) if body.get("encoding") == "base64" else \
                str(body.get("content", "")).encode()
            if ev.get("phase") == "request":
                tx[tid].request_body = data.decode("utf-8", "replace")
            else:
                tx[tid].response_body = data
                tx[tid].media_type = body.get("media_type") or ""
    cap.transactions = list(tx.values())
    steps = result.get("steps") or []
    for step in reversed(steps):
        dom = (step.get("artifacts") or {}).get("dom") or {}
        if dom.get("state") == "captured":
            cap.dom = (dom.get("value") or {}).get("text", "")
            break
    for step in reversed(steps):
        after = step.get("after_url") or {}
        if after.get("url"):
            cap.final_url = after["url"]
            break
    return cap


def run_scenario_sync(scenario: dict, timeout: int = 90) -> Capture:
    cmd = rea_command()
    if not cmd:
        return Capture(ok=False, error="REA CLI bulunamadı")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(scenario, fh)
        path = fh.name
    try:
        started = time.time()
        proc = subprocess.run([*cmd, "capture-browser-scenario", path, "--format", "json"],
                              capture_output=True, text=True, timeout=timeout,
                              env={**os.environ, "NO_COLOR": "1"})
        cap = _parse(proc.stdout)
        if not cap.duration_ms:
            cap.duration_ms = int((time.time() - started) * 1000)
        if not cap.ok and not cap.error:
            cap.error = (proc.stderr or "")[:300]
        return cap
    except subprocess.TimeoutExpired:
        return Capture(ok=False, error=f"REA {timeout}s içinde tamamlanmadı")
    finally:
        os.unlink(path)


def _capture_block(response_body: bool = True) -> dict:
    return {"at_end": ["dom", "url"], "events": ["network"],
            "network": {"request_body": True, "response_body": response_body, "header_values": False}}


async def capture_connected(endpoint: str, target_id: str, url: str, timeout: int = 6,
                            wait_ms: int = 700) -> Capture:
    """Playwright sekmesinde verilen adrese git, DOM/ağ gözlemi yap.

    İptal ve zaman aşımı CLI sürecini de sonlandırır. Tarayıcı çağırana aittir.
    Arama motorunun geçici isteklerinden tekrar oynatılabilir API varsayılmaz.
    """
    cmd = rea_command()
    if not cmd:
        return Capture(ok=False, error="REA CLI bulunamadı")
    scenario = {
        "browser": {"mode": "connect", "cdp_endpoint": endpoint, "target_id": target_id},
        "start_url": {"url": url, "query": []},
        "environment": {"locale": "tr-TR", "timezone": "Europe/Istanbul", "service_workers": "allow"},
        "actions": [{"step_id": "dynamic-results", "action": "wait_for_timeout", "duration_ms": wait_ms}],
        "capture": {"at_end": ["dom", "url"], "events": ["network"],
                    "network": {"request_body": False, "response_body": False, "header_values": False}},
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(scenario, fh)
        path = fh.name
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, "capture-browser-scenario", path, "--format", "json",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "NO_COLOR": "1"})
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)
        cap = _parse(stdout.decode("utf-8", "replace"))
        if proc.returncode and cap.ok:
            cap.ok = False
            cap.error = f"REA CLI çıkış kodu {proc.returncode}"
        if not stdout.strip() and stderr.strip():
            cap.error = f"REA JSON döndürmedi; CLI çıkış kodu {proc.returncode}."
        return cap
    except TimeoutError:
        return Capture(ok=False, error=f"REA {timeout}s süre sınırı")
    finally:
        if proc is not None and proc.returncode is None:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            await proc.communicate()
        os.unlink(path)


async def recon(url: str, settle_ms: int = 3500) -> Capture:
    """REA launch modu: render + ağ haritası çıkarımı."""
    exe = chromium_executable()
    if not exe:
        return Capture(ok=False, error="REA için Chromium bulunamadı (playwright install chromium)")
    scenario = {
        "browser": {"mode": "launch", "executable_path": exe, "headless": True},
        "start_url": {"url": url, "query": []},
        "environment": {"locale": "tr-TR", "timezone": "Europe/Istanbul", "service_workers": "allow"},
        "actions": [
            {"step_id": "settle", "action": "wait_for_timeout", "duration_ms": settle_ms},
            {"step_id": "scroll", "action": "press", "locator": {"kind": "css", "selector": "body"},
             "key": "End", "timeout_ms": 3000},
            {"step_id": "lazy", "action": "wait_for_timeout", "duration_ms": 1200},
        ],
        "capture": _capture_block(),
    }
    cap = await asyncio.to_thread(run_scenario_sync, scenario)
    if not cap.ok and "environment" in cap.error.lower():
        scenario.pop("environment")
        cap = await asyncio.to_thread(run_scenario_sync, scenario)
    return cap


async def click_capture(url: str, selector: str, settle_ms: int = 2000) -> Capture:
    """REA: sayfayı açar, verilen öğeye tıklar ve tıklamanın tetiklediği istekleri yakalar."""
    exe = chromium_executable()
    if not exe:
        return Capture(ok=False, error="REA için Chromium bulunamadı")
    scenario = {
        "browser": {"mode": "launch", "executable_path": exe, "headless": True},
        "start_url": {"url": url, "query": []},
        "environment": {"service_workers": "allow"},
        "actions": [
            {"step_id": "settle", "action": "wait_for_timeout", "duration_ms": settle_ms},
            {"step_id": "click", "action": "click", "locator": {"kind": "css", "selector": selector}, "timeout_ms": 8000},
            {"step_id": "after", "action": "wait_for_timeout", "duration_ms": 2500},
        ],
        "capture": _capture_block(),
    }
    return await asyncio.to_thread(run_scenario_sync, scenario)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class StealthBridge:
    """Scrapling StealthySession + REA (CDP connect) — aynı tarayıcı, aynı oturum.

    Senkron sınıftır; bir iş parçacığı içinde (asyncio.to_thread) kullanılır.
    """

    def __init__(self, log=None):
        self.port = _free_port()
        self.endpoint = f"http://127.0.0.1:{self.port}"
        self.log = log or (lambda msg: None)
        self.session = None

    def __enter__(self):
        from scrapling.fetchers import StealthySession

        self.session = StealthySession(headless=True, network_idle=True, timeout=45000, block_webrtc=True,
                                       extra_flags=[f"--remote-debugging-port={self.port}",
                                                    "--remote-debugging-address=127.0.0.1"])
        self.session.__enter__()
        return self

    def __exit__(self, *exc):
        if self.session:
            self.session.__exit__(*exc)

    def fetch(self, url: str, **kwargs):
        return self.session.fetch(url, **kwargs)

    def _target_for(self, origin: str) -> str | None:
        cmd = rea_command()
        if not cmd:
            return None
        proc = subprocess.run([*cmd, "list-browser-targets", self.endpoint, "--format", "json"],
                              capture_output=True, text=True, timeout=40)
        try:
            targets = json.loads(proc.stdout)["normalized_result"]["targets"]
        except (ValueError, KeyError, TypeError):
            return None
        for t in targets:
            if t.get("origin") == origin:
                return t["target_id"]
        return targets[0]["target_id"] if targets else None

    def observe(self, start_url: str, actions: list[dict]) -> Capture:
        """Stealth tarayıcıda açık sekmeye REA ile bağlanıp senaryoyu gözlemler."""
        parsed = urlparse(start_url)
        target = self._target_for(f"{parsed.scheme}://{parsed.netloc}")
        if not target:
            return Capture(ok=False, error="REA hedef sekmeyi bulamadı")
        scenario = {
            "browser": {"mode": "connect", "cdp_endpoint": self.endpoint, "target_id": target},
            "start_url": {"url": start_url, "query": []},
            # Service worker engeli bazı sitelerde (ör. ScienceDirect) bağlı oturumda senaryoyu düşürüyor
            "environment": {"service_workers": "allow"},
            "actions": actions,
            "capture": _capture_block(),
        }
        return run_scenario_sync(scenario)
