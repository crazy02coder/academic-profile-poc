"""Hazır veri dosyalarını GitHub Pages'te yayımlanacak klasöre hazırlar (uygulama bunları app/remote_data.py ile okur).

    python scripts/publish_data.py <kaynak veri klasörü> <yayın klasörü>

Kaynak klasörde şunlar beklenir (eksik olan atlanır):
    poc/universities.json, poc/student/<alan adı>.json.gz   hazır ders veri seti (scripts/import_poc_dataset.py)
    arge_merkezleri.json                                     Ar-Ge ve tasarım merkezleri (scripts/import_arge.py)
    yok_university_logos.json                                YÖK'teki üniversite logoları
    journal_quartiles.sqlite                                 dergi çeyrekleri (scripts/import_sjr.py); sıkıştırılarak yayımlanır

Yayın klasörüne dosyalar aynı yollarla kopyalanır ve bir manifest.json yazılır: her dosyanın boyutu ve SHA-256 özeti.
Uygulama yalnız manifest'te özeti değişen dosyayı yeniden indirir. Yayın klasörü veri deposunun (akademik-iz-data)
köküdür; commit edilip gönderilince GitHub Pages yeni sürümü yayımlar.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

FILES = ("poc/universities.json", "arge_merkezleri.json", "yok_university_logos.json", "firm_logos/index.json")
PACKED = {"journal_quartiles.sqlite": "journal_quartiles.sqlite.gz"}  # kaynak → yayımlanan (sıkıştırılmış) ad


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main(source: Path, target: Path) -> int:
    target.mkdir(parents=True, exist_ok=True)
    published: list[str] = []
    for rel in FILES:
        if (source / rel).is_file():
            (target / rel).parent.mkdir(parents=True, exist_ok=True)
            # Satır sonları LF yazılır: Windows kopyasındaki CRLF yayımlanırsa özet, sunulan dosyayla tutmaz.
            (target / rel).write_bytes((source / rel).read_bytes().replace(b"\r\n", b"\n"))
            published.append(rel)
    # Firma logoları (scripts/build_firm_logos.py) ve ders veri seti olduğu gibi kopyalanır.
    images = [p for p in sorted((source / "firm_logos").glob("*")) if p.suffix in {".png", ".jpg", ".gif", ".webp", ".ico", ".svg"}]
    for path in images + sorted((source / "poc" / "student").glob("*.json.gz")):
        rel = path.relative_to(source).as_posix()
        (target / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target / rel)
        published.append(rel)
    for name, packed in PACKED.items():
        if (source / name).is_file():
            # mtime=0: aynı veri aynı dosyayı üretir (gereksiz depo değişikliği olmaz)
            with (source / name).open("rb") as raw, (target / packed).open("wb") as out, \
                    gzip.GzipFile(filename="", fileobj=out, mode="wb", compresslevel=9, mtime=0) as handle:
                shutil.copyfileobj(raw, handle, 1 << 20)
            published.append(packed)
    files = {rel: {"size": (target / rel).stat().st_size, "sha256": digest(target / rel)} for rel in published}
    manifest = {"name": "akademik-iz-data", "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "files": files}
    (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    (target / ".nojekyll").write_text("", encoding="utf-8")  # Pages dosyaları olduğu gibi sunsun (Jekyll işlemesin)
    # Ana adres boş kalmasın: veri dosyalarını listeleyen tanıtım sayfası (manifest.json'u okur).
    shutil.copyfile(Path(__file__).with_name("publish_index.html"), target / "index.html")
    # Git dosyalara dokunmasın (satır sonu dönüştürmesi yok): yayımlanan bayt, manifest'teki özetle aynı kalır.
    (target / ".gitattributes").write_text("* -text\n", encoding="utf-8")
    total = sum(f["size"] for f in files.values())
    # Çıktıda yalnız her konsol kodlamasında bulunan karakterler.
    print(f"{len(files)} dosya, {total / 1e6:.1f} MB -> {target}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2])))
