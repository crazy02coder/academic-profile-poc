"""Yerel Ollama istemcisi (Qwen2.5 + embedding). Erişilemezse `available=False` → mock yollar.

CAG için önemli: Ollama, aynı model yuvasında AYNI önekle başlayan istemlerde KV
önbelleğini yeniden kullanır. Bunun bozulmaması için tüm çağrılarda aynı `num_ctx`
kullanılır (num_ctx değişirse model yeniden yüklenir, önbellek düşer) ve model
`keep_alive` ile bellekte tutulur.
"""
from __future__ import annotations

import json
import os
import time
from typing import AsyncIterator

import httpx

from .config import LLM_MODE, OLLAMA_MODEL, OLLAMA_URL

PREFERRED = ("qwen2.5:7b", "qwen2.5:14b", "qwen2.5:3b", "qwen2.5")
EMBED_PREFERRED = ("bge-m3", "nomic-embed-text", "mxbai-embed-large", "all-minilm")
NUM_CTX = int(os.getenv("LLM_NUM_CTX", "12288"))  # paralel slot × bağlam belleği 18 GB Mac'e sığsın
KEEP_ALIVE = os.getenv("LLM_KEEP_ALIVE", "30m")


class LLM:
    def __init__(self):
        self.model: str = ""
        self.fast_model: str = ""  # soru yorumu, link seçimi gibi kısa işler için küçük model
        self.embed_model: str = ""
        self.available = False
        self.reason = ""

    async def probe(self) -> "LLM":
        if LLM_MODE == "mock":
            self.available, self.reason = False, "LLM_MODE=mock"
            return self
        try:
            async with httpx.AsyncClient(timeout=3) as client:
                tags = (await client.get(f"{OLLAMA_URL}/api/tags")).json().get("models", [])
        except Exception:  # noqa: BLE001
            self.available, self.reason = False, "Ollama erişilemedi"
            return self
        names = [m.get("name", "") for m in tags]
        embed_env = os.getenv("EMBED_MODEL", "")
        for pref in ((embed_env,) if embed_env else ()) + EMBED_PREFERRED:
            hit = next((n for n in names if n.startswith(pref)), "")
            if hit:
                self.embed_model = hit
                break
        chosen = ""
        if OLLAMA_MODEL:
            chosen = OLLAMA_MODEL if any(n == OLLAMA_MODEL or n.startswith(OLLAMA_MODEL) for n in names) else ""
        if not chosen:
            for pref in PREFERRED:
                chosen = next((n for n in names if n.startswith(pref)), "")
                if chosen:
                    break
        if not chosen:
            chosen = next((n for n in names if n.startswith("qwen")), "")
        if not chosen:
            self.available, self.reason = False, "Ollama'da Qwen modeli yok (ollama pull qwen2.5:7b)"
            return self
        self.model, self.available, self.reason = chosen, True, ""
        fast_env = os.getenv("OLLAMA_FAST_MODEL", "")
        self.fast_model = next((n for pref in ((fast_env,) if fast_env else ()) + ("qwen2.5:3b", "qwen2.5:1.5b")
                                for n in names if pref and n.startswith(pref)), chosen)
        return self

    def _options(self, temperature: float) -> dict:
        return {"temperature": temperature, "num_ctx": NUM_CTX}

    async def json(self, prompt: str, schema: dict | None = None, system: str = "", timeout: int = 120,
                   num_ctx: int | None = None, fast: bool = False) -> dict | None:  # noqa: ARG002 - num_ctx sabit
        if not self.available:
            return None
        body = {"model": self.fast_model if fast and self.fast_model else self.model, "prompt": prompt, "stream": False, "format": schema or "json",
                "options": self._options(0.1), "keep_alive": KEEP_ALIVE}
        if system:
            body["system"] = system
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(f"{OLLAMA_URL}/api/generate", json=body)
                resp.raise_for_status()
                return json.loads(resp.json().get("response", ""))
        except Exception:  # noqa: BLE001
            return None

    async def embed(self, texts: list[str], timeout: int = 120) -> list[list[float]] | None:
        if not self.embed_model or not texts:
            return None
        out: list[list[float]] = []
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                for i in range(0, len(texts), 32):
                    resp = await client.post(f"{OLLAMA_URL}/api/embed",
                                             json={"model": self.embed_model, "input": texts[i:i + 32],
                                                   "keep_alive": KEEP_ALIVE})
                    resp.raise_for_status()
                    out.extend(resp.json()["embeddings"])
        except Exception:  # noqa: BLE001
            return None
        return out

    async def stream_chat(self, messages: list[dict], stats: dict | None = None, timeout: int = 240) -> AsyncIterator[str]:
        """Akışlı sohbet. `stats` sözlüğüne ilk token süresi ve Ollama prompt istatistikleri yazılır."""
        body = {"model": self.model, "messages": messages, "stream": True, "options": self._options(0.2),
                "keep_alive": KEEP_ALIVE}
        started = time.time()
        received_text = False
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", f"{OLLAMA_URL}/api/chat", json=body) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    if chunk.get("error"):
                        raise RuntimeError(str(chunk["error"]))
                    piece = (chunk.get("message") or {}).get("content", "")
                    if piece:
                        received_text = True
                        if stats is not None and "ttft" not in stats:
                            stats["ttft"] = round(time.time() - started, 2)
                        yield piece
                    if chunk.get("done"):
                        if stats is not None:
                            stats["prompt_tokens"] = chunk.get("prompt_eval_count")
                            stats["prompt_eval_s"] = round((chunk.get("prompt_eval_duration") or 0) / 1e9, 2)
                            stats["output_tokens"] = chunk.get("eval_count")
                            stats["total_s"] = round(time.time() - started, 2)
                        break
        if not received_text:
            raise RuntimeError("Ollama boş cevap döndürdü")

    def label(self) -> str:
        if not self.available:
            return f"Mock LLM ({self.reason})"
        return f"Ollama · {self.model}" + (f" · emb {self.embed_model}" if self.embed_model else "")
