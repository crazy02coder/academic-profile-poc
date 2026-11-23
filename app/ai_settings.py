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
            "model": saved.get("model") or base["model"], "fast_model": saved.get("fast_model") or base["fast_model"]}


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
         base_url: str = "") -> None:
    if provider not in PROVIDERS:
        raise ValueError("Bilinmeyen sağlayıcı.")
    data = _load()
    providers = data.setdefault("providers", {})
    entry = providers.setdefault(provider, {})
    entry.update(model=model.strip(), fast_model=fast_model.strip())
    entry.pop("embed_model", None)  # eski sürümün gömme modeli ayarı
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
    keys = search()
    return [p["key"] for p in (_load().get("providers") or {}).values() if p.get("key")] \
        + [keys[name] for name in ("serper_key", "google_cse_key", "epo_key", "epo_secret", "openalex_key") if keys[name]]


# ------------------------------------------------------------------ arama servisleri (Serper.dev, Google Custom Search)
# Ayarlar sayfasından girilen servis anahtarları → yedek ortam değişkeni (.env). EPO: patent servisi (Open Patent Services).
_SEARCH_ENV = {"serper_key": "SERPER_API_KEY", "google_cse_key": "GOOGLE_CSE_KEY", "google_cse_cx": "GOOGLE_CSE_CX",
               "epo_key": "EPO_KEY", "epo_secret": "EPO_SECRET", "openalex_key": "OPENALEX_API_KEY"}


def search() -> dict:
    """Arama servisi anahtarları: Ayarlar sayfasında kaydedilen değer; yoksa ortam değişkeni (.env)."""
    saved = _load().get("search")
    saved = saved if isinstance(saved, dict) else {}
    return {name: str(saved.get(name) or os.getenv(env, "") or "").strip() for name, env in _SEARCH_ENV.items()}


def search_public() -> dict:
    """Arayüze giden görünüm: anahtarların kendisi yok, yalnız kayıtlı olup olmadıkları. Arama motoru kimliği gizli değildir."""
    keys = search()
    return {"serper": bool(keys["serper_key"]), "google_cse": bool(keys["google_cse_key"]), "google_cse_cx": keys["google_cse_cx"],
            "epo": bool(keys["epo_key"] and keys["epo_secret"]), "openalex": bool(keys["openalex_key"])}


def save_search(serper_key: str = "", google_cse_key: str = "", google_cse_cx: str | None = None, clear: tuple = (),
                epo_key: str = "", epo_secret: str = "", openalex_key: str = "") -> None:
    """Boş bırakılan anahtar değişmez; silmek için adı clear içinde verilir. Kimlik (cx) verildiği gibi yazılır."""
    data = _load()
    entry = data.get("search") if isinstance(data.get("search"), dict) else {}
    for name in clear:
        if name in _SEARCH_ENV:
            entry.pop(name, None)
    if serper_key.strip():
        entry["serper_key"] = serper_key.strip()
    if epo_key.strip():
        entry["epo_key"] = epo_key.strip()
    if epo_secret.strip():
        entry["epo_secret"] = epo_secret.strip()
    if openalex_key.strip():
        entry["openalex_key"] = openalex_key.strip()
    if google_cse_key.strip():
        entry["google_cse_key"] = google_cse_key.strip()
    if google_cse_cx is not None:
        entry["google_cse_cx"] = google_cse_cx.strip()
    data["search"] = entry
    _write(data)


# ------------------------------------------------------------------ sesli asistan (Konu bul / Danışman bul)
_ASSISTANT_DEFAULT = {"name": "Ada", "voice": "Kore", "tone": "samimi", "address": "sen", "extra": "", "live_model": "",
                      "color": "mavi"}


def assistant() -> dict:
    """Asistanın adı, sesi (Gemini Live hazır sesi), konuşma tonu, hitabı ve ek talimatı."""
    saved = _load().get("assistant")
    saved = saved if isinstance(saved, dict) else {}
    return {k: (str(saved.get(k)).strip() if saved.get(k) not in (None, "") else v) for k, v in _ASSISTANT_DEFAULT.items()}


def save_assistant(values: dict) -> dict:
    data = _load()
    entry = assistant()
    for key in ("name", "voice", "tone", "address", "extra", "live_model", "color"):
        if key in values and values[key] is not None:
            entry[key] = str(values[key]).strip()[:600 if key == "extra" else 60]
    entry["name"] = entry["name"] or _ASSISTANT_DEFAULT["name"]
    data["assistant"] = entry
    _write(data)
    return entry


def apply_openalex_key() -> None:
    """Kayıtlı OpenAlex anahtarını bütün OpenAlex isteklerine uygular (config.OPENALEX_PARAMS yerinde güncellenir;
    modüller aynı sözlüğü kullandığı için yeniden başlatmak gerekmez)."""
    from . import config
    key = search()["openalex_key"]
    if key:
        config.OPENALEX_PARAMS["api_key"] = key
    else:
        config.OPENALEX_PARAMS.pop("api_key", None)
