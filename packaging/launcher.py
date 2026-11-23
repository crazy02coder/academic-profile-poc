"""Akademik İz masaüstü başlatıcısı (Windows exe'nin giriş noktası; PyInstaller ile paketlenir).

Açılınca:
  1. Sunucuyu (FastAPI + uvicorn) arka planda, boş bir yerel portta başlatır.
  2. Logolu küçük bir kontrol penceresi gösterir: adres, durum, "Uygulamayı aç" ve "Kapat".
  3. Sunucu hazır olunca uygulamayı varsayılan tarayıcıda açar.
  4. Tarama için bilgisayarın Chrome'unu (yoksa Edge'ini) kullanır; ikisi de yoksa ilk açılışta Chromium indirir.
Pencere kapanınca sunucu da kapanır.

Uygulama başka bir süreç olarak kendini çağırdığında ("exe -m app.search_worker") yalnız o modül çalışır.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def _worker_mode() -> bool:
    """Uygulamanın alt süreçleri ("python -m app.search_worker" yerine "exe -m app.search_worker")."""
    if len(sys.argv) >= 3 and sys.argv[1] == "-m":
        import runpy
        if FROZEN:  # pencereli exe'de standart akışlar boştur; üst sürecin verdiği borular yeniden bağlanır
            try:
                sys.stdin = open(0, "r", encoding="utf-8", closefd=False)
                sys.stdout = open(1, "w", encoding="utf-8", closefd=False)
                sys.stderr = open(2, "w", encoding="utf-8", closefd=False)
            except OSError:
                pass
        module = sys.argv[2]
        sys.argv = [sys.argv[0], *sys.argv[3:]]
        runpy.run_module(module, run_name="__main__", alter_sys=True)
        return True
    return False


if _worker_mode():
    sys.exit(0)

os.chdir(BASE)
# PyInstaller'ın Playwright kancası tarayıcıları paketin içinde arar (PLAYWRIGHT_BROWSERS_PATH=0); paket Chromium
# taşımadığı için bilgisayarın ortak klasörü kullanılır. İlk açılıştaki indirme de buraya yapılır.
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "ms-playwright")
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))
LOGS = BASE / "data" / "job-log"
LOGS.mkdir(parents=True, exist_ok=True)
if FROZEN or sys.stdout is None:
    # Pencereli exe'nin konsolu yok: sunucu kayıtları dosyaya yazılır.
    _log = open(LOGS / "app.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = _log

import json  # noqa: E402
import socket  # noqa: E402
import subprocess  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import urllib.request  # noqa: E402
import webbrowser  # noqa: E402

TITLE = "Akademik İz"
DEFAULT_PORT = 8000


def _running_instance(port: int) -> bool:
    """Bu portta zaten çalışan bir Akademik İz var mı."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1.5) as response:
            return response.status == 200 and "llm_ready" in json.loads(response.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return False


def _free_port(start: int) -> int:
    for port in range(start, start + 30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return 0


def _browsers_missing() -> list[str]:
    """Tarama için gereken Chromium'lardan diskte olmayanlar (Playwright ve Patchright ayrı sürüm kullanır).
    Bilgisayarda Chrome varsa ikisi de onu kullanır (yalnız Edge varsa Playwright onu kullanır); indirme gerekmez."""
    from app.config import system_browser
    needed = [name for name, have in (("playwright", system_browser()), ("patchright", system_browser(chrome_only=True))) if not have]
    missing = []
    for name in needed:
        try:
            module = __import__(f"{name}._impl._driver", fromlist=["compute_driver_executable", "get_driver_env"])
            node, cli = module.compute_driver_executable()
            result = subprocess.run([node, cli, "install", "--dry-run", "chromium"], capture_output=True, text=True,
                                    env=module.get_driver_env(), timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            paths = [line.split(":", 1)[1].strip() for line in result.stdout.splitlines() if "Install location:" in line]
            if not paths or not all(Path(p).exists() for p in paths):
                missing.append(name)
        except Exception:  # noqa: BLE001 — denetlenemezse indirilmesi denenir
            missing.append(name)
    return missing


def _install_browsers(names: list[str], report) -> bool:
    ok = True
    for name in names:
        report(f"Tarama bileşenleri indiriliyor ({name}, bir kez)…")
        try:
            module = __import__(f"{name}._impl._driver", fromlist=["compute_driver_executable", "get_driver_env"])
            node, cli = module.compute_driver_executable()
            result = subprocess.run([node, cli, "install", "chromium"], capture_output=True, text=True,
                                    env=module.get_driver_env(), timeout=1800, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            print(f"[{name} install] {result.returncode}\n{result.stdout[-2000:]}\n{result.stderr[-2000:]}", flush=True)
            ok = ok and result.returncode == 0
        except Exception as exc:  # noqa: BLE001
            print(f"[{name} install] {type(exc).__name__}: {exc}", flush=True)
            ok = False
    return ok


class Server:
    def __init__(self, port: int):
        import uvicorn
        from app.main import app
        self.port = port
        self.url = f"http://127.0.0.1:{port}"
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="info", access_log=False))
        self.thread = threading.Thread(target=self.server.run, name="uvicorn", daemon=True)

    def start(self):
        self.thread.start()

    @property
    def ready(self) -> bool:
        return bool(self.server.started)

    def stop(self):
        self.server.should_exit = True


def main() -> None:
    if "--check" in sys.argv:  # paket denetimi: uygulama içe aktarılabiliyor mu
        from app.main import app
        from app.config import rea_command
        print(f"ok {len(app.routes)} utf8={sys.flags.utf8_mode} rea={bool(rea_command())}", flush=True)
        return
    if _running_instance(DEFAULT_PORT):
        webbrowser.open(f"http://127.0.0.1:{DEFAULT_PORT}/")
        return
    port = _free_port(DEFAULT_PORT)
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title(TITLE)
    root.resizable(False, False)
    icon = BASE / "packaging" / "akademik-iz.ico"
    if icon.exists():
        try:
            root.iconbitmap(default=str(icon))
        except tk.TclError:
            pass
    frame = ttk.Frame(root, padding=22)
    frame.grid()
    logo_file = BASE / "packaging" / "akademik-iz-128.png"
    if logo_file.exists():
        logo = tk.PhotoImage(file=str(logo_file))
        ttk.Label(frame, image=logo).grid(row=0, column=0, rowspan=3, padx=(0, 18))
        root._logo = logo  # çöp toplayıcı resmi silmesin
    ttk.Label(frame, text=TITLE, font=("Segoe UI", 18, "bold")).grid(row=0, column=1, sticky="w")
    ttk.Label(frame, text="Araştırma keşif platformu", foreground="#6b6b73").grid(row=1, column=1, sticky="w")
    status = tk.StringVar(value="Başlatılıyor…")
    ttk.Label(frame, textvariable=status, wraplength=320).grid(row=2, column=1, sticky="w", pady=(10, 0))
    buttons = ttk.Frame(frame)
    buttons.grid(row=3, column=0, columnspan=2, sticky="e", pady=(18, 0))
    open_btn = ttk.Button(buttons, text="Uygulamayı aç", state="disabled")
    open_btn.grid(row=0, column=0, padx=(0, 8))
    close_btn = ttk.Button(buttons, text="Kapat")
    close_btn.grid(row=0, column=1)

    def say(text: str):
        root.after(0, status.set, text)

    try:
        server = Server(port)
    except Exception as exc:  # noqa: BLE001
        print(f"[başlatma] {type(exc).__name__}: {exc}", flush=True)
        status.set(f"Uygulama başlatılamadı: {type(exc).__name__}. Ayrıntı: {LOGS / 'app.log'}")
        close_btn.configure(command=root.destroy)
        root.mainloop()
        return
    server.start()
    open_btn.configure(command=lambda: webbrowser.open(server.url + "/"))

    def shutdown():
        status.set("Kapatılıyor…")
        server.stop()
        root.after(400, root.destroy)

    close_btn.configure(command=shutdown)
    root.protocol("WM_DELETE_WINDOW", shutdown)
    state = {"opened": False, "browsers": "checking"}

    def browsers():
        missing = _browsers_missing()
        if missing:
            state["browsers"] = "installing"
            ok = _install_browsers(missing, say)
            state["browsers"] = "ready" if ok else "failed"
        else:
            state["browsers"] = "ready"
        refresh()

    def refresh():
        if not server.ready:
            return
        note = {"checking": "", "installing": " · tarama bileşenleri indiriliyor",
                "failed": " · tarama bileşenleri indirilemedi (internet bağlantısını kontrol edip yeniden açın)",
                "ready": ""}[state["browsers"]]
        say(f"Çalışıyor: {server.url}{note}")

    def wait_ready():
        if server.ready:
            open_btn.configure(state="normal")
            refresh()
            if not state["opened"]:
                state["opened"] = True
                webbrowser.open(server.url + "/")
            return
        if not server.thread.is_alive():
            status.set(f"Sunucu başlatılamadı. Ayrıntı: {LOGS / 'app.log'}")
            return
        root.after(250, wait_ready)

    threading.Thread(target=browsers, name="browsers", daemon=True).start()
    root.after(250, wait_ready)
    root.mainloop()
    server.stop()
    time.sleep(0.5)
    os._exit(0)


if __name__ == "__main__":
    main()
