"""Çalışma zamanı ayarları ve araç keşfi (REA, Chromium, Ollama)."""
from __future__ import annotations

import glob
import os
import platform
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT / "runs"
CACHE_DIR = ROOT / ".cache"

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "")  # boşsa otomatik seçilir
LLM_MODE = os.getenv("LLM_MODE", "auto")  # auto | mock

USER_AGENT = "AkademikIz/2.0 (academic research PoC; mailto:akademik-iz@example.org)"
CONTACT_MAIL = os.getenv("OPENALEX_MAILTO", "akademik-iz@example.org")

# Crawler sınırları: kibar ve sınırlı.
CRAWL_MAX_PAGES = int(os.getenv("CRAWL_MAX_PAGES", "90"))
CRAWL_CONCURRENCY = int(os.getenv("CRAWL_CONCURRENCY", "8"))
CRAWL_MAX_DEPTH = int(os.getenv("CRAWL_MAX_DEPTH", "3"))


def rea_command() -> list[str] | None:
    """REA CLI: önce REA_BIN, sonra proje içi node_modules, sonra PATH."""
    explicit = os.getenv("REA_BIN")
    if explicit and Path(explicit).exists():
        return [explicit]
    local = ROOT / "node_modules" / ".bin" / "rea"
    if local.exists():
        return [str(local)]
    found = shutil.which("rea")
    return [found] if found else None


def chromium_executable() -> str | None:
    """REA'nın 'launch' modu için Playwright'ın indirdiği Chromium'u bulur."""
    explicit = os.getenv("REA_CHROME")
    if explicit and Path(explicit).exists():
        return explicit
    base = os.getenv("PLAYWRIGHT_BROWSERS_PATH") or (
        str(Path.home() / "Library/Caches/ms-playwright")
        if platform.system() == "Darwin"
        else str(Path.home() / ".cache/ms-playwright")
    )
    patterns = [
        "chromium-*/chrome-mac*/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
        "chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium",
        "chromium-*/chrome-linux*/chrome",
        "chromium-*/chrome-win*/chrome.exe",
    ]
    hits: list[str] = []
    for pattern in patterns:
        hits.extend(glob.glob(os.path.join(base, pattern)))
    if hits:
        return sorted(hits)[-1]
    for name in ("chromium", "chromium-browser", "google-chrome"):
        found = shutil.which(name)
        if found:
            return found
    return None
