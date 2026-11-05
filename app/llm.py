"""Yapay zekâ istemcisi (metin, JSON şeması, akış, embedding). Anahtar yoksa `available=False` → mock yollar.

Sağlayıcı ayarlardan gelir (ai_settings): Gemini, ChatGPT, Claude ya da OpenAI uyumlu kendi sunucusu.
Uygulamanın geri kalanı yalnızca bu sınıfı kullanır. Claude'un gömme modeli yoktur; sohbet o zaman kelime aramasıyla çalışır.

Ücretsiz katman dalgalıdır: kota (429), yoğunluk (503) ve geçici 403/404 yanıtları
olağan. Bu yüzden her çağrı bir model zinciri üzerinde kısa beklemelerle denenir;
kotası dolan model bir süre zincirde atlanır.

CAG için: Gemini aynı önekle başlayan istemlerde örtük önbellek kullanır; önek
(sistem talimatı + bilgi tabanı) her soruda bayt bayt aynı tutulur.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import AsyncIterator

import httpx

from . import ai_settings
from .config import GEMINI_EMBED_MODEL, GEMINI_FALLBACKS, LLM_MODE

API = "https://generativelanguage.googleapis.com/v1beta"
EMBED_DIM = 768
RETRY_STATUS = {403, 404, 429, 500, 503}
RETRY_OTHER = {408, 429, 500, 502, 503, 504, 529}
ANTHROPIC_VERSION = "2023-06-01"
OPENAI_EMBED_MODEL = "text-embedding-3-small"
MAX_OUTPUT = 8192
COOLDOWN_S = 60
_SLOTS = asyncio.Semaphore(4)  # ücretsiz katmanın dakika sınırını zorlamamak için


class LLMError(RuntimeError):
    pass


def _contents(messages: list[dict]) -> tuple[str, list[dict]]:
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    turns = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
             for m in messages if m["role"] != "system"]
    return system, turns


def _text(data: dict) -> str:
    parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))


def _loose_json(text: str) -> dict | None:
    """Model JSON'u kod bloğu ya da açıklamayla sarmış olabilir: ilk { ile son } arasını okur."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except ValueError:
        return None


async def list_models(provider: str, base_url: str, key: str, timeout: int = 8) -> list[str] | None:
    """Sağlayıcının model adları; uç nokta yoksa (bazı kendi sunucularda) None. Yetki/ağ hatasında istisna."""
    if provider == "gemini":
        url, params, headers = f"{API}/models", {"pageSize": 200}, {"x-goog-api-key": key}
    elif provider == "anthropic":
        url, params, headers = f"{base_url}/models", {"limit": 1000}, {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION}
    else:
        url, params, headers = f"{base_url}/models", {}, {"Authorization": f"Bearer {key}"} if key else {}
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url, params=params, headers=headers)
    if provider == "custom" and resp.status_code in (404, 405, 501):
        return None
    resp.raise_for_status()
    body = resp.json()
    if provider == "gemini":
        return sorted(m["name"].removeprefix("models/") for m in body.get("models", []))
    return sorted(m["id"] for m in body.get("data", []) if m.get("id"))


class LLM:
    def __init__(self):
        cfg = ai_settings.resolved()
        self.provider: str = cfg["provider"]
        self.provider_label: str = cfg["label"]
        self.key: str = cfg["key"]
        self.base_url: str = cfg["base_url"]
        self.model: str = cfg["model"]
        self.fast_model: str = cfg["fast_model"]  # link seçimi gibi kısa işler
        self.embed_model: str = ""
        self._embed_setting: str = cfg["embed_model"]
        self.available = False
        self.reason = ""
        self._cooldown: dict[str, float] = {}
        self._no_thinking_cfg: set[str] = set()  # thinkingLevel desteklemeyen modeller

    async def probe(self) -> "LLM":
        if LLM_MODE == "mock":
            self.available, self.reason = False, "LLM_MODE=mock"
            return self
        if self.provider == "custom" and not self.base_url:
            self.available, self.reason = False, "kendi sunucunuzun adresi girilmedi"
            return self
        if self.provider != "custom" and not self.key:
            self.available, self.reason = False, f"{self.provider_label} anahtarı tanımlı değil"
            return self
        try:
            names = await list_models(self.provider, self.base_url, self.key)
        except Exception as exc:  # noqa: BLE001
            self.available, self.reason = False, f"{self.provider_label} erişilemedi ({type(exc).__name__})"
            return self
        if not self.model and self.provider == "custom" and names:
            self.model = names[0]
        if not self.model:
            self.available, self.reason = False, f"{self.provider_label} için model seçilmedi"
            return self
        if names is not None and self.model not in names:
            self.available, self.reason = False, f"{self.model} bu anahtarla kullanılamıyor"
            return self
        if not self.fast_model or (names is not None and self.fast_model not in names):
            self.fast_model = self.model
        wanted = self._embed_setting or {"gemini": GEMINI_EMBED_MODEL, "openai": OPENAI_EMBED_MODEL}.get(self.provider, "")
        self.embed_model = wanted if wanted and self.provider != "anthropic" and (names is None or wanted in names) else ""
        self.available, self.reason = True, ""
        return self

    def _headers(self) -> dict:
        if self.provider == "gemini":
            return {"x-goog-api-key": self.key}
        if self.provider == "anthropic":
            return {"x-api-key": self.key, "anthropic-version": ANTHROPIC_VERSION}
        return {"Authorization": f"Bearer {self.key}"} if self.key else {}

    def _chain(self, first: str) -> list[str]:
        now = time.monotonic()
        chain = list(dict.fromkeys([first, *(GEMINI_FALLBACKS if self.provider == "gemini" else [self.fast_model])]))
        return [m for m in chain if self._cooldown.get(m, 0) <= now] or chain[:1]

    def _config(self, model: str, temperature: float, extra: dict | None = None) -> dict:
        cfg = {"temperature": temperature, **(extra or {})}
        if model not in self._no_thinking_cfg:
            cfg["thinkingConfig"] = {"thinkingLevel": "minimal"}  # kısa çıkarım işlerinde düşünme gecikmesi gereksiz
        return cfg

    def _failed(self, model: str, status: int, body: str) -> bool:
        """Hatayı kaydeder; aynı model düşünme ayarı olmadan yeniden denenecekse True."""
        if status == 429:
            self._cooldown[model] = time.monotonic() + COOLDOWN_S
        if status == 400 and "thinking" in body.lower() and model not in self._no_thinking_cfg:
            self._no_thinking_cfg.add(model)
            return True
        return False

    async def _generate(self, first: str, body_for, timeout: int) -> dict:
        """Zincirdeki modelleri sırayla dener (iki tur); başarılı yanıtın gövdesini döndürür."""
        last = ""
        async with _SLOTS, httpx.AsyncClient(timeout=timeout) as client:
            for round_ in range(2):
                if round_:
                    await asyncio.sleep(1.5)
                for model in self._chain(first):
                    for _ in range(2):
                        resp = await client.post(f"{API}/models/{model}:generateContent",
                                                 headers=self._headers(), json=body_for(model))
                        if resp.status_code == 200:
                            return resp.json()
                        if not self._failed(model, resp.status_code, resp.text):
                            break
                    last = f"{model}: HTTP {resp.status_code}"
                    if resp.status_code not in RETRY_STATUS:
                        raise LLMError(last)
        raise LLMError(last or "Gemini yanıt vermedi")

    async def json(self, prompt: str, schema: dict | None = None, system: str = "", timeout: int = 120,
                   fast: bool = False, **_) -> dict | None:
        if not self.available:
            return None
        if self.provider != "gemini":
            first = self.fast_model if fast else self.model
            try:
                if self.provider == "anthropic":
                    return await self._json_anthropic(first, prompt, schema, system, timeout)
                return await self._json_openai(first, prompt, schema, system, timeout)
            except Exception:  # noqa: BLE001
                return None
        extra = {"responseMimeType": "application/json"}
        if schema:
            extra["responseJsonSchema"] = schema

        def body(model: str) -> dict:
            out = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                   "generationConfig": self._config(model, 0.1, extra)}
            if system:
                out["systemInstruction"] = {"parts": [{"text": system}]}
            return out

        try:
            return json.loads(_text(await self._generate(self.fast_model if fast else self.model, body, timeout)))
        except Exception:  # noqa: BLE001
            return None

    async def _post(self, first: str, path: str, body_for, timeout: int) -> dict:
        """Gemini dışı sağlayıcılar: zincirdeki modelleri iki tur dener."""
        last = ""
        async with _SLOTS, httpx.AsyncClient(timeout=timeout) as client:
            for round_ in range(2):
                if round_:
                    await asyncio.sleep(1.5)
                for model in self._chain(first):
                    resp = await client.post(f"{self.base_url}{path}", headers=self._headers(), json=body_for(model))
                    if resp.status_code == 200:
                        return resp.json()
                    last = f"{model}: HTTP {resp.status_code}"
                    if resp.status_code == 429:
                        self._cooldown[model] = time.monotonic() + COOLDOWN_S
                    if resp.status_code not in RETRY_OTHER:
                        raise LLMError(last)
        raise LLMError(last or f"{self.provider_label} yanıt vermedi")

    async def _json_anthropic(self, first: str, prompt: str, schema: dict | None, system: str, timeout: int) -> dict | None:
        """Şema zorunlu araç çağrısıyla uygulanır: Claude yanıtı şemaya uygun araç girdisi olarak verir."""
        use_tool = bool(schema) and schema.get("type") == "object"
        text = prompt if use_tool else f"{prompt}\n\nYalnızca JSON döndür."

        def body(model: str) -> dict:
            out = {"model": model, "max_tokens": MAX_OUTPUT, "messages": [{"role": "user", "content": text}]}
            if system:
                out["system"] = system
            if use_tool:
                out["tools"] = [{"name": "sonuc", "description": "Sonucu yapılandırılmış olarak kaydet.", "input_schema": schema}]
                out["tool_choice"] = {"type": "tool", "name": "sonuc"}
            return out

        blocks = (await self._post(first, "/messages", body, timeout)).get("content") or []
        for block in blocks:
            if block.get("type") == "tool_use":
                return block.get("input")
        return _loose_json("".join(b.get("text", "") for b in blocks))

    async def _json_openai(self, first: str, prompt: str, schema: dict | None, system: str, timeout: int) -> dict | None:
        """Şema destekleyen sunucuda json_schema; desteklemeyen kendi sunucuda düz istem ve metinden JSON okuma."""
        def build(fmt: dict | None, text: str):
            def body(model: str) -> dict:
                messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": text}]
                out = {"model": model, "messages": messages}
                if self.provider == "custom":
                    out["temperature"] = 0.1  # OpenAI'ın yeni modelleri bu alanı kabul etmeyebilir
                if fmt:
                    out["response_format"] = fmt
                return out
            return body

        fmt = {"type": "json_schema", "json_schema": {"name": "sonuc", "schema": schema}} if schema else {"type": "json_object"}
        plain = f"{prompt}\n\nYalnızca JSON döndür, açıklama yazma." + (f"\nŞema: {json.dumps(schema, ensure_ascii=False)}" if schema else "")
        try:
            data = await self._post(first, "/chat/completions", build(fmt, plain), timeout)
        except LLMError as exc:
            if self.provider != "custom" or not any(code in str(exc) for code in ("HTTP 400", "HTTP 422", "HTTP 501")):
                raise
            data = await self._post(first, "/chat/completions", build(None, plain), timeout)
        return _loose_json(((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "")

    async def embed(self, texts: list[str], timeout: int = 120,
                    task: str = "RETRIEVAL_DOCUMENT") -> list[list[float]] | None:
        if not self.embed_model or not texts:
            return None
        out: list[list[float]] = []
        if self.provider != "gemini":
            try:
                async with _SLOTS, httpx.AsyncClient(timeout=timeout) as client:
                    for i in range(0, len(texts), 100):
                        body = {"model": self.embed_model, "input": texts[i:i + 100]}
                        if self.provider == "openai":
                            body["dimensions"] = EMBED_DIM
                        resp = await client.post(f"{self.base_url}/embeddings", headers=self._headers(), json=body)
                        resp.raise_for_status()
                        out.extend(e["embedding"] for e in sorted(resp.json()["data"], key=lambda e: e["index"]))
            except Exception:  # noqa: BLE001
                return None
            return out
        try:
            async with _SLOTS, httpx.AsyncClient(timeout=timeout) as client:
                for i in range(0, len(texts), 100):
                    reqs = [{"model": f"models/{self.embed_model}", "content": {"parts": [{"text": t}]},
                             "taskType": task, "outputDimensionality": EMBED_DIM} for t in texts[i:i + 100]]
                    resp = await client.post(f"{API}/models/{self.embed_model}:batchEmbedContents",
                                             headers=self._headers(), json={"requests": reqs})
                    resp.raise_for_status()
                    out.extend(e["values"] for e in resp.json()["embeddings"])
        except Exception:  # noqa: BLE001
            return None
        return out

    async def stream_chat(self, messages: list[dict], stats: dict | None = None,
                          timeout: int = 240) -> AsyncIterator[str]:
        """Akışlı sohbet. `stats` sözlüğüne ilk token süresi ve token sayıları yazılır."""
        if self.provider != "gemini":
            async for piece in self._stream_other(messages, stats, timeout):
                yield piece
            return
        system, turns = _contents(messages)
        started = time.time()
        last = ""
        queue = self._chain(self.model)
        async with httpx.AsyncClient(timeout=timeout) as client:
            while queue:
                model = queue.pop(0)
                body = {"contents": turns, "generationConfig": self._config(model, 0.2)}
                if system:
                    body["systemInstruction"] = {"parts": [{"text": system}]}
                received_text = False
                usage: dict = {}
                async with client.stream("POST", f"{API}/models/{model}:streamGenerateContent",
                                         params={"alt": "sse"}, headers=self._headers(), json=body) as resp:
                    if resp.status_code != 200:
                        text = (await resp.aread()).decode("utf-8", "replace")
                        last = f"{model}: HTTP {resp.status_code}"
                        if self._failed(model, resp.status_code, text):
                            queue.insert(0, model)
                        elif resp.status_code not in RETRY_STATUS:
                            break
                        continue
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        chunk = json.loads(line[5:])
                        usage = chunk.get("usageMetadata") or usage
                        piece = _text(chunk)
                        if piece:
                            received_text = True
                            if stats is not None and "ttft" not in stats:
                                stats["ttft"] = round(time.time() - started, 2)
                            yield piece
                if not received_text:
                    last = f"{model}: boş cevap"
                    continue
                if stats is not None:
                    stats["model"] = model
                    stats["prompt_tokens"] = usage.get("promptTokenCount")
                    stats["cached_tokens"] = usage.get("cachedContentTokenCount", 0)
                    stats["output_tokens"] = usage.get("candidatesTokenCount")
                    stats["total_s"] = round(time.time() - started, 2)
                return
        raise LLMError(last or "Gemini boş cevap döndürdü")

    async def _stream_other(self, messages: list[dict], stats: dict | None, timeout: int) -> AsyncIterator[str]:
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        turns = [{"role": m["role"], "content": m["content"]} for m in messages if m["role"] != "system"]
        claude = self.provider == "anthropic"
        started, last = time.time(), ""
        async with httpx.AsyncClient(timeout=timeout) as client:
            for model in self._chain(self.model):
                body: dict = {"model": model, "stream": True}
                if claude:
                    # Bilgi tabanı öneki her soruda aynı: Claude önbelleği yeniden kullanır
                    body |= {"max_tokens": MAX_OUTPUT, "messages": turns}
                    if system:
                        body["system"] = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
                else:
                    body["messages"] = ([{"role": "system", "content": system}] if system else []) + turns
                    if self.provider == "openai":
                        body["stream_options"] = {"include_usage": True}
                    else:
                        body["temperature"] = 0.2
                path = "/messages" if claude else "/chat/completions"
                got_text = False
                usage: dict = {}
                async with client.stream("POST", f"{self.base_url}{path}", headers=self._headers(), json=body) as resp:
                    if resp.status_code != 200:
                        await resp.aread()
                        last = f"{model}: HTTP {resp.status_code}"
                        if resp.status_code == 429:
                            self._cooldown[model] = time.monotonic() + COOLDOWN_S
                        if resp.status_code in RETRY_OTHER:
                            continue
                        break
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:") or line[5:].strip() == "[DONE]":
                            continue
                        chunk = json.loads(line[5:])
                        if claude:
                            usage |= (chunk.get("message") or {}).get("usage") or {}
                            usage |= chunk.get("usage") or {}
                            piece = (chunk.get("delta") or {}).get("text") or "" if chunk.get("type") == "content_block_delta" else ""
                        else:
                            usage = chunk.get("usage") or usage
                            piece = ((chunk.get("choices") or [{}])[0].get("delta") or {}).get("content") or ""
                        if piece:
                            got_text = True
                            if stats is not None and "ttft" not in stats:
                                stats["ttft"] = round(time.time() - started, 2)
                            yield piece
                if not got_text:
                    last = f"{model}: boş cevap"
                    continue
                if stats is not None:
                    cached = usage.get("cache_read_input_tokens", 0) if claude else (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
                    stats |= {"model": model, "cached_tokens": cached, "total_s": round(time.time() - started, 2),
                              "prompt_tokens": usage.get("input_tokens" if claude else "prompt_tokens"),
                              "output_tokens": usage.get("output_tokens" if claude else "completion_tokens")}
                return
        raise LLMError(last or f"{self.provider_label} boş cevap döndürdü")

    def label(self) -> str:
        if not self.available:
            return f"Yapay zekâ kapalı ({self.reason})"
        return f"{self.provider_label} · {self.model}" + (f" · emb {self.embed_model}" if self.embed_model else "")
