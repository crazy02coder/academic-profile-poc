"""Çalışma zamanı ayarları ve araç keşfi (REA, Chromium, Gemini)."""
from __future__ import annotations

import glob
import os
import platform
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT / "runs"
CACHE_DIR = ROOT / ".cache"


def _load_env(path: Path) -> None:
    """Proje kökündeki .env (KEY=değer satırları); ortamda zaten tanımlı olanlar ezilmez."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and key and not key.startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_env(ROOT / ".env")

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
GEMINI_FAST_MODEL = os.getenv("GEMINI_FAST_MODEL", "gemini-3.5-flash-lite")
# Kota/yoğunluk hatasında sırayla denenecek modeller
GEMINI_FALLBACKS = [m.strip() for m in os.getenv(
    "GEMINI_FALLBACKS", "gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-2.5-flash").split(",") if m.strip()]
GEMINI_EMBED_MODEL = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001")
LLM_MODE = os.getenv("LLM_MODE", "auto")  # auto | mock

USER_AGENT = "AkademikIz/2.0 (academic research PoC; mailto:akademik-iz@example.org)"
CONTACT_MAIL = os.getenv("OPENALEX_MAILTO", "akademik-iz@example.org")
# OpenAlex ücretsiz anahtarı (.env: OPENALEX_API_KEY=…). Anahtarsız istekler IP başına günlük ortak bütçeyi
# (~1000 istek) paylaşır; anahtarla kişisel bütçe kullanılır. Yalnızca OpenAlex isteklerine eklenir.
OPENALEX_API_KEY = os.getenv("OPENALEX_API_KEY", "")
OPENALEX_PARAMS = {"mailto": CONTACT_MAIL} | ({"api_key": OPENALEX_API_KEY} if OPENALEX_API_KEY else {})
# EPO Open Patent Services (patentler): ücretsiz kayıt, developers.epo.org → My Apps → Consumer Key/Secret
EPO_KEY = os.getenv("EPO_KEY", "")
EPO_SECRET = os.getenv("EPO_SECRET", "")


def redact(text: str) -> str:
    """Kullanıcıya gösterilen hata metinlerinden (istek URL'leri) anahtarları siler."""
    from . import ai_settings  # döngüsel içe aktarmayı önler: ai_settings bu modülü kullanır
    for secret in (OPENALEX_API_KEY, EPO_KEY, EPO_SECRET, *ai_settings.secrets()):
        if secret:
            text = text.replace(secret, "***")
    return text

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
