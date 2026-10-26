"""Gemini API istemcisi (metin, JSON şeması, akış, embedding). Anahtar yoksa `available=False` → mock yollar.

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

from .config import GEMINI_API_KEY, GEMINI_EMBED_MODEL, GEMINI_FALLBACKS, GEMINI_FAST_MODEL, GEMINI_MODEL, LLM_MODE

API = "https://generativelanguage.googleapis.com/v1beta"
EMBED_DIM = 768
RETRY_STATUS = {403, 404, 429, 500, 503}
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


class LLM:
    def __init__(self):
        self.model: str = GEMINI_MODEL
        self.fast_model: str = GEMINI_FAST_MODEL  # link seçimi gibi kısa işler
        self.embed_model: str = ""
        self.available = False
        self.reason = ""
        self._cooldown: dict[str, float] = {}
        self._no_thinking_cfg: set[str] = set()  # thinkingLevel desteklemeyen modeller

    async def probe(self) -> "LLM":
        if LLM_MODE == "mock":
            self.available, self.reason = False, "LLM_MODE=mock"
            return self
        if not GEMINI_API_KEY:
            self.available, self.reason = False, "GEMINI_API_KEY tanımlı değil (.env)"
            return self
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                resp = await client.get(f"{API}/models", params={"pageSize": 200}, headers=self._headers())
            resp.raise_for_status()
            names = {m["name"].removeprefix("models/") for m in resp.json().get("models", [])}
        except Exception as exc:  # noqa: BLE001
            self.available, self.reason = False, f"Gemini erişilemedi ({type(exc).__name__})"
            return self
        if self.model not in names:
            self.available, self.reason = False, f"{self.model} bu anahtarla kullanılamıyor"
            return self
        if self.fast_model not in names:
            self.fast_model = self.model
        self.embed_model = GEMINI_EMBED_MODEL if GEMINI_EMBED_MODEL in names else ""
        self.available, self.reason = True, ""
        return self

    def _headers(self) -> dict:
        return {"x-goog-api-key": GEMINI_API_KEY}

    def _chain(self, first: str) -> list[str]:
        now = time.monotonic()
        chain = list(dict.fromkeys([first, *GEMINI_FALLBACKS]))
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

    async def embed(self, texts: list[str], timeout: int = 120,
                    task: str = "RETRIEVAL_DOCUMENT") -> list[list[float]] | None:
        if not self.embed_model or not texts:
            return None
        out: list[list[float]] = []
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

    def label(self) -> str:
        if not self.available:
            return f"Mock LLM ({self.reason})"
        return f"Gemini · {self.model}" + (f" · emb {self.embed_model}" if self.embed_model else "")
