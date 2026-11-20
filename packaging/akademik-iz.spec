# PyInstaller paket tanımı: Akademik İz masaüstü uygulaması (klasör biçiminde; kurulum dosyası bunu paketler).
#
#     .venv\Scripts\python -m PyInstaller packaging\akademik-iz.spec --noconfirm --distpath dist --workpath build
#
# Çıktı: dist\AkademikIz\AkademikIz.exe ve yanındaki _internal klasörü. Hazır veri pakete girmez (GitHub Pages'ten
# indirilir); tarama için gereken Chromium da pakete girmez, ilk açılışta indirilir (bkz. packaging/launcher.py).
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).parent

datas = [(str(ROOT / "static"), "static"),
         # Uygulama paketinin .py olmayan dosyaları (puan ölçütleri, WoS kayıt eşlemesi).
         (str(ROOT / "app" / "criteria"), "app/criteria"),
         (str(ROOT / "app" / "wos_records.json"), "app"),
         # REA (Node betikleri); Node'u Playwright'ın sürücüsünden gelir (bkz. app/config.py rea_command).
         (str(ROOT / "node_modules"), "node_modules"),
         (str(ROOT / "packaging" / "akademik-iz.ico"), "packaging"),
         (str(ROOT / "packaging" / "akademik-iz-128.png"), "packaging")]
binaries = []
hiddenimports = collect_submodules("app") + collect_submodules("uvicorn")

# Veri dosyaları, sürücüler ya da dinamik içe aktarmalar taşıyan paketler bütünüyle alınır.
for package in ("scrapling", "curl_cffi", "playwright", "patchright", "langdetect", "browserforge",
                "apify_fingerprint_datapoints", "ddgs", "primp", "certifi", "tld", "rapidfuzz", "websockets", "pypdf"):
    try:
        d, b, h = collect_all(package)
    except Exception:  # paket kurulu değilse atlanır
        continue
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "IPython", "matplotlib", "notebook"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    # Python UTF-8 kipi: veri dosyaları UTF-8; Windows'un yerel kod sayfasıyla (cp1254) açılmasın.
    [("X utf8=1", None, "OPTION")],
    exclude_binaries=True,
    name="AkademikIz",
    icon=str(ROOT / "packaging" / "akademik-iz.ico"),
    console=False,
    upx=False,
    version=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="AkademikIz", upx=False)
