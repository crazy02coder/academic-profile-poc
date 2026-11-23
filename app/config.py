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


def curl_path(path) -> str:
    """libcurl (Scrapling'in kullandığı curl_cffi) Windows'ta ASCII dışı harf içeren dosya yolunu açamaz
    ("C:/Users/Bahadır/…" → curl 77: sertifika dosyası okunamadı). Böyle bir yol için aynı dosyanın kısa (8.3) adı,
    o da yoksa ASCII bir klasördeki kopyası döndürülür; diğer sistemlerde yol aynen kalır."""
    path = str(path)
    if os.name != "nt" or path.isascii():
        return path
    try:
        import ctypes
        buffer = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.kernel32.GetShortPathNameW(path, buffer, 1024) and buffer.value.isascii():
            return buffer.value
    except Exception:  # noqa: BLE001
        pass
    try:  # diskte kısa adlar kapalı: dosya ASCII bir klasöre kopyalanır
        import shutil
        folder = Path(os.environ.get("PROGRAMDATA") or "C:/ProgramData") / "akademik-iz"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / Path(path).name
        if not target.exists() or target.stat().st_mtime < Path(path).stat().st_mtime:
            shutil.copyfile(path, target)
        return str(target) if str(target).isascii() else path
    except OSError:
        return path


if os.name == "nt":
    # Scrapling'in varsayılan kök sertifika dosyası sanal ortamın içindedir; yol ASCII değilse curl onu açamaz.
    try:
        import certifi
        if not certifi.where().isascii():
            os.environ.setdefault("CURL_CA_BUNDLE", curl_path(certifi.where()))
    except Exception:  # noqa: BLE001
        pass

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
GEMINI_FAST_MODEL = os.getenv("GEMINI_FAST_MODEL", "gemini-3.5-flash-lite")
# Kota/yoğunluk hatasında sırayla denenecek modeller
GEMINI_FALLBACKS = [m.strip() for m in os.getenv(
    "GEMINI_FALLBACKS", "gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-2.5-flash").split(",") if m.strip()]
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
    script = ROOT / "node_modules" / "rea-agents" / "scripts" / "rea.mjs"
    if os.name == "nt" and script.exists():
        # Windows: .bin/rea bir kabuk betiğidir, doğrudan çalıştırılamaz; betik Node ile çağrılır. Node kurulu değilse
        # (masaüstü paketi) Playwright'ın kendi Node'u kullanılır.
        node = shutil.which("node")
        if not node:
            try:
                from playwright._impl._driver import compute_driver_executable
                node = compute_driver_executable()[0]
            except Exception:  # noqa: BLE001
                node = None
        if node and Path(node).exists():
            return [node, str(script)]
    local = ROOT / "node_modules" / ".bin" / "rea"
    if local.exists() and os.name != "nt":
        return [str(local)]
    found = shutil.which("rea")
    return [found] if found else None


def hidden_process() -> dict:
    """Alt süreç bayrakları: Windows'ta (özellikle pencereli exe'de) her Node/araç çağrısı için cmd penceresi açılmaz."""
    if os.name == "nt":
        import subprocess
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {}


def system_browser(chrome_only: bool = False) -> str | None:
    """Bilgisayarda kurulu Chrome (yoksa Edge). Varsa tarama bunu kullanır; ayrıca Chromium indirilmez."""
    if platform.system() == "Windows":
        roots = [os.environ.get(k) for k in ("LOCALAPPDATA", "PROGRAMFILES", "PROGRAMFILES(X86)", "ProgramW6432")]
        names = [("Google", "Chrome", "Application", "chrome.exe")]
        if not chrome_only:
            names.append(("Microsoft", "Edge", "Application", "msedge.exe"))
        for parts in names:
            for root in roots:
                if root and Path(root, *parts).exists():
                    return str(Path(root, *parts))
        return None
    if platform.system() == "Darwin":
        apps = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
        if not chrome_only:
            apps.append("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge")
        return next((a for a in apps if Path(a).exists()), None)
    for name in ("google-chrome", "google-chrome-stable") + (() if chrome_only else ("microsoft-edge",)):
        found = shutil.which(name)
        if found:
            return found
    return None


def stealth_browser() -> dict:
    """Scrapling gizli oturumları için: kurulu Chrome varsa o kullanılır (Patchright'ın Chromium'u indirilmez)."""
    return {"real_chrome": True} if system_browser(chrome_only=True) else {}


def chromium_executable() -> str | None:
    """REA'nın 'launch' modu ve Playwright için tarayıcı: önce bilgisayarın Chrome/Edge'i, yoksa Playwright'ın
    indirdiği Chromium."""
    explicit = os.getenv("REA_CHROME")
    if explicit and Path(explicit).exists():
        return explicit
    system = system_browser()
    if system:
        return system
    base = os.getenv("PLAYWRIGHT_BROWSERS_PATH") or (
        str(Path.home() / "Library/Caches/ms-playwright")
        if platform.system() == "Darwin"
        else str(Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "ms-playwright")
        if platform.system() == "Windows"
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
