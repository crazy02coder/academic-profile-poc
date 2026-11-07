"""Yapay zekâ sağlayıcı ayarları: Gemini, ChatGPT, Claude ya da OpenAI uyumlu kendi sunucusu.

Ayarlar proje kökünde, yalnızca sahibinin okuyabildiği `.ai-settings.json` dosyasında durur (git'e girmez).
Anahtar ve adres yalnızca Ayarlar sayfasından girilir (.env okunmaz); anahtar arayüze hiçbir zaman geri gönderilmez.
"""
from __future__ import annotations

import json
import os
from urllib.parse import urlparse

from .config import GEMINI_FAST_MODEL, GEMINI_MODEL, ROOT

PATH = ROOT / ".ai-settings.json"
PROVIDERS = {
    "gemini": {"label": "Gemini", "base_url": "https://generativelanguage.googleapis.com/v1beta",
               "model": GEMINI_MODEL, "fast_model": GEMINI_FAST_MODEL},
    "openai": {"label": "ChatGPT", "base_url": "https://api.openai.com/v1",
               "model": "", "fast_model": ""},
    "anthropic": {"label": "Claude", "base_url": "https://api.anthropic.com/v1",
                  "model": "claude-sonnet-5-5", "fast_model": "claude-haiku-5-5"},
    "custom": {"label": "Kendi sunucum", "base_url": "", "model": "", "fast_model": ""},
}


def _load() -> dict:
    try:
        data = json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(data: dict) -> None:
    """Geçici dosya 0600 açılır: anahtar hiçbir an başkalarına okunur olmaz."""
    tmp = PATH.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    tmp.replace(PATH)


def clean_url(url: str) -> str:
    """Sunucu adresi: http(s) olmalı; sondaki / ve /chat/completions atılır. Geçersizse ValueError."""
    url = (url or "").strip().rstrip("/").removesuffix("/chat/completions")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Sunucu adresi http:// ya da https:// ile başlamalı.")
    return url


def resolved(provider: str | None = None) -> dict:
    """Çağrı için tam ayar: sağlayıcı, anahtar, adres ve modeller."""
    data = _load()
    provider = provider or data.get("provider") or "gemini"
    if provider not in PROVIDERS:
        provider = "gemini"
    base, saved = PROVIDERS[provider], (data.get("providers") or {}).get(provider) or {}
    return {"provider": provider, "label": base["label"],
            "key": saved.get("key") or "",
            "base_url": saved.get("base_url") or base["base_url"],
            "model": saved.get("model") or base["model"], "fast_model": saved.get("fast_model") or base["fast_model"],
            "embed_model": saved.get("embed_model") or ""}


def public() -> dict:
    """Arayüze giden görünüm; anahtarın kendisi yok, yalnızca kayıtlı olup olmadığı var."""
    out = {}
    for name in PROVIDERS:
        r = resolved(name)
        r["has_key"] = bool(r.pop("key"))
        out[name] = r
    return {"provider": resolved()["provider"], "providers": out}


def key_for_test(provider: str, key: str, base_url: str) -> str:
    """Model listesi için anahtar. Kayıtlı anahtar, kaydedildiği adresten başka bir adrese gönderilmez."""
    if key:
        return key
    r = resolved(provider)
    return r["key"] if base_url == r["base_url"] else ""


def save(provider: str, key: str = "", clear_key: bool = False, model: str = "", fast_model: str = "",
         embed_model: str = "", base_url: str = "") -> None:
    if provider not in PROVIDERS:
        raise ValueError("Bilinmeyen sağlayıcı.")
    data = _load()
    providers = data.setdefault("providers", {})
    entry = providers.setdefault(provider, {})
    entry.update(model=model.strip(), fast_model=fast_model.strip(), embed_model=embed_model.strip())
    default = PROVIDERS[provider]["base_url"]
    url = clean_url(base_url) if base_url.strip() or not default else default
    if url != (entry.get("base_url") or default):
        entry.pop("key", None)  # eski anahtar yeni adrese gitmesin
    entry["base_url"] = url
    if clear_key:
        entry.pop("key", None)
    if key.strip():
        entry["key"] = key.strip()
    data["provider"] = provider
    _write(data)


def secrets() -> list[str]:
    return [p["key"] for p in (_load().get("providers") or {}).values() if p.get("key")]
