"""bahadir-yok dışa aktarımını (data/export/poc) projeye alır: öğrenci görünümü dersleri oradan anında gösterir.

    python scripts/import_poc_dataset.py /yol/bahadir-yok/data/export/poc

student/<alan adı>.json dosyaları sıkıştırılarak data/poc/student/<alan adı>.json.gz olarak yazılır (yaklaşık 170 MB →
27 MB); universities.json özet listesi data/poc/ altına kopyalanır. Dosyaları app/poc_dataset.py okur. Yeni bir dışa
aktarım geldiğinde aynı komut yeniden çalıştırılır; eski dosyaların üzerine yazılır.
"""
from __future__ import annotations

import gzip
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "data" / "poc"


def main(source: Path) -> int:
    students = source / "student"
    if not students.is_dir():
        print(f"student/ klasörü bulunamadı: {students}")
        return 1
    (TARGET / "student").mkdir(parents=True, exist_ok=True)
    count = courses = raw = packed = 0
    for path in sorted(students.glob("*.json")):
        blob = path.read_bytes()
        try:
            data = json.loads(blob.decode("utf-8"))
        except ValueError:
            print(f"atlandı (okunamadı): {path.name}")
            continue
        if not isinstance(data, dict) or not isinstance(data.get("faculties"), list):
            print(f"atlandı (beklenen biçimde değil): {path.name}")
            continue
        out = TARGET / "student" / f"{path.stem}.json.gz"
        tmp = out.with_suffix(".tmp")
        # mtime=0: aynı veri aynı dosyayı üretir (gereksiz depo değişikliği olmaz)
        with tmp.open("wb") as target, gzip.GzipFile(filename="", fileobj=target, mode="wb", compresslevel=9, mtime=0) as handle:
            handle.write(blob)
        tmp.replace(out)
        count += 1
        raw += len(blob)
        packed += out.stat().st_size
        courses += sum(len(d.get("courses") or []) for f in data["faculties"] for d in f.get("departments") or [])
    if (source / "universities.json").exists():
        shutil.copyfile(source / "universities.json", TARGET / "universities.json")
    # Çıktıda yalnız her konsol kodlamasında bulunan karakterler (Windows konsolu "→" yazamıyor).
    print(f"{count} universite, {courses} ders: {raw / 1e6:.0f} MB -> {packed / 1e6:.0f} MB, hedef: {TARGET}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1])))
