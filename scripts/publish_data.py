"""Hazır veri dosyalarını GitHub Pages'te yayımlanacak klasöre hazırlar (uygulama bunları app/remote_data.py ile okur).

    python scripts/publish_data.py <kaynak veri klasörü> <yayın klasörü>
    python scripts/publish_data.py --search <uygulamanın data klasörü> <yayın klasörü>

İkinci biçim yalnız arama kaydını günceller: yayındaki diğer dosyalara ve dosya listesindeki (manifest.json)
kayıtlarına dokunmaz. Arama kaydını göndermek için bu kullanılır; ilk biçim, kaynak klasörde bulunmayan hazır veriyi
(ders veri seti gibi) dosya listesinden çıkarır.

Kaynak klasörde şunlar beklenir (eksik olan atlanır):
    poc/universities.json, poc/student/<alan adı>.json.gz   hazır ders veri seti (scripts/import_poc_dataset.py)
    arge_merkezleri.json                                     Ar-Ge ve tasarım merkezleri (scripts/import_arge.py)
    yok_university_logos.json                                YÖK'teki üniversite logoları
    journal_quartiles.sqlite                                 dergi çeyrekleri (scripts/import_sjr.py); sıkıştırılarak yayımlanır
    search-cache/site/<alan adı>.json, search-cache/web/<0-f>.json   arama sonuçları (uygulama yazar: app/search_store.py)

Arama sonuçları search/ altında yayımlanır; başka bilgisayarlar aynı sorguyu arama motoruna gitmeden buradan okur.
Yayın klasöründeki önceki arama kaydıyla birleştirilir (sorgu başına yeni olan kalır), 60 günden eski kayıt atılır,
başlık ve açıklamalardaki e-posta adresleri silinir.

Yayın klasörüne dosyalar aynı yollarla kopyalanır ve bir manifest.json yazılır: her dosyanın boyutu ve SHA-256 özeti.
Uygulama yalnız manifest'te özeti değişen dosyayı yeniden indirir. Yayın klasörü veri deposunun (akademik-iz-data)
köküdür; commit edilip gönderilince GitHub Pages yeni sürümü yayımlar.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
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


SEARCH_MAX_AGE = 60 * 24 * 3600  # app/search_store.py TTL ile aynı: daha eskisini uygulama zaten kullanmaz
_SEARCH_FILE = re.compile(r"(?:site/[a-z0-9.-]+|web/[0-9a-f])")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")


def _search_entries(raw, now: float) -> dict:
    """Bir arama dosyasının yayımlanabilir kayıtları: süresi dolmamış, satırı olan; metinlerde e-posta yok."""
    out = {}
    for query, entry in (raw.items() if isinstance(raw, dict) else ()):
        try:
            ts = int(float(entry.get("ts") or 0))
        except (AttributeError, TypeError, ValueError):
            continue
        rows = []
        for row in entry.get("rows") or []:
            url = str(row.get("url") or "") if isinstance(row, dict) else ""
            if not url.startswith(("http://", "https://")) or "@" in url:
                continue
            kept = {"url": url, "title": _EMAIL.sub("…", str(row.get("title") or ""))}
            if row.get("snippet"):
                kept["snippet"] = _EMAIL.sub("…", str(row["snippet"]))
            if row.get("engine"):
                kept["engine"] = str(row["engine"])
            rows.append(kept)
        if rows and 0 <= now - ts <= SEARCH_MAX_AGE:
            out[str(query)] = {"ts": ts, "provider": str(entry.get("provider") or ""), "rows": rows}
    return out


def publish_search(source: Path, target: Path) -> list[str]:
    """Arama kaydı: kaynak/search-cache/<dosya>.json → yayın/search/<dosya>.json.gz (önceki yayınla birleştirilerek)."""
    now = time.time()
    local = {path.relative_to(source / "search-cache").as_posix()[:-len(".json")]: path
             for path in sorted((source / "search-cache").glob("*/*.json"))}
    old = {path.relative_to(target / "search").as_posix()[:-len(".json.gz")]: path
           for path in sorted((target / "search").glob("*/*.json.gz"))}
    published, queries = [], 0
    for name in sorted(set(local) | set(old)):
        if not _SEARCH_FILE.fullmatch(name):
            continue
        merged: dict = {}
        for path, opener in ((old.get(name), gzip.open), (local.get(name), open)):
            if path is None:
                continue
            try:
                with opener(path, "rt", encoding="utf-8") as handle:
                    entries = _search_entries(json.load(handle), now)
            except (OSError, ValueError, EOFError):
                continue
            for query, entry in entries.items():
                if query not in merged or entry["ts"] >= merged[query]["ts"]:  # eşitlikte yerel kayıt (sonra okunur) kalır
                    merged[query] = entry
        out = target / "search" / (name + ".json.gz")
        if not merged:
            out.unlink(missing_ok=True)  # içinde geçerli kayıt kalmadı: yayından çıkar
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(merged, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        # mtime=0 ve sıralı anahtarlar: aynı kayıt aynı dosyayı üretir (özet değişmez, uygulama yeniden indirmez)
        with out.open("wb") as raw, gzip.GzipFile(filename="", fileobj=raw, mode="wb", compresslevel=9, mtime=0) as handle:
            handle.write(text.encode("utf-8"))
        published.append(f"search/{name}.json.gz")
        queries += len(merged)
    if published:
        print(f"arama kaydi: {queries} sorgu, {len(published)} dosya")
    return published


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
    published += publish_search(source, target)
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


def main_search(source: Path, target: Path) -> int:
    """Yalnız arama kaydı: search/ dosyaları yeniden yazılır, dosya listesinde yalnız onların kayıtları değişir."""
    listing = target / "manifest.json"
    try:
        manifest = json.loads(listing.read_text(encoding="utf-8"))
        files = dict(manifest["files"])
    except (OSError, ValueError, KeyError, TypeError):
        # Yanlış klasöre yazıp yalnız arama dosyaları içeren bir liste üretmemek için durulur.
        print(f"Yayin klasorunde gecerli bir manifest.json yok: {target}")
        return 2
    files = {rel: meta for rel, meta in files.items() if not rel.startswith("search/")}
    for rel in publish_search(source, target):
        files[rel] = {"size": (target / rel).stat().st_size, "sha256": digest(target / rel)}
    if files != manifest["files"]:  # değişiklik yoksa liste (ve tarihi) aynı kalır: gereksiz depo değişikliği olmaz
        manifest.update(generated_at=time.strftime("%Y-%m-%d %H:%M:%S"), files=files)
        listing.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    count = sum(1 for rel in files if rel.startswith("search/"))
    print(f"arama dosyasi: {count}, listede toplam {len(files)} dosya -> {target}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--search":
        sys.exit(main_search(Path(sys.argv[2]), Path(sys.argv[3])))
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2])))
