"""YÖK İstatistik (istatistik.yok.gov.tr): üniversite bazında öğrenci sayıları — önlisans, lisans, yüksek lisans,
doktora; erkek / kadın / toplam.

Site, tarayıcıdaki her tıklamayı sunucuya küçük bir istekle ileten bir uygulamadır (ZK). Burada aynı istekler sırayla
gönderilir: rapor penceresi açılır, en güncel öğretim yılı seçilir, "Raporu Getir" denir ve tablo sayfa sayfa okunur.
Oturum açma, doğrulama ya da engel aşma yoktur; rapor herkese açıktır.

Tablo bütün üniversiteleri içerir: bir kez okunur (yaklaşık 55 küçük istek, aralıklı) ve 180 gün saklanır; sonraki
bütün üniversiteler kayıttan gelir. Okuma yalnız kullanıcı dişli menüsünden yenileme istediğinde başlar.
"""
from __future__ import annotations

import asyncio
import json
import re
import time

import httpx

from .config import ROOT
from .text import clean, fold

BASE = "https://istatistik.yok.gov.tr"
DIR = ROOT / "data" / "extra"
TTL = 180 * 24 * 3600
GAP = 1.0  # istekler arası bekleme (sn)
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}
LEVELS = ("associate", "undergrad", "graduate", "doctoral", "total")
_LOCK = asyncio.Lock()


def _text(value: str) -> str:
    return value.encode("latin-1", "backslashreplace").decode("unicode_escape") if "\\" in value else value


def _rows(payload: str) -> list[list[str]]:
    """ZK yanıtındaki liste satırları: her satır hücre etiketlerinin listesi."""
    out = []
    for block in re.split(r"\['zul\.sel\.Listitem',", payload)[1:]:
        cells = [_text(x) for x in re.findall(r"\['zul\.sel\.Listcell','[^']+',\{[^}]*?label:'((?:[^'\\]|\\.)*)'", block)]
        if cells:
            out.append(cells)
    return out


def _path():
    return DIR / "ogrenci-sayilari.json"


def _load(stale: bool = False) -> dict | None:
    try:
        saved = json.loads(_path().read_text(encoding="utf-8"))
        if stale or time.time() - saved.get("ts", 0) < TTL:
            return saved
    except (OSError, ValueError):
        pass
    return None


def _name_key(name: str) -> str:
    return " ".join(fold(re.sub(r"\([^)]*\)", " ", clean(name))).split())


async def sample() -> dict:
    """Veri tarifi denetimi için: raporun yalnız ilk sayfası (yaklaşık 6 küçük istek). {"year", "row": ilk satırın hücreleri}."""
    year, rows = await _read(first_page_only=True)
    if not rows:
        raise ValueError("YÖK İstatistik tablosu boş geldi")
    return {"year": year, "row": rows[0], "rows": len(rows)}


async def _collect() -> dict:
    """Raporun tamamı: {"year", "universities": {ad anahtarı: {"name", "type", "city", düzeyler…}}}."""
    year_text, rows = await _read()
    year = (None, year_text)
    return _aggregate(year, rows)


async def _read(first_page_only: bool = False) -> tuple[str, list[list[str]]]:
    """Siteyi açıp raporu okur: (öğretim yılı, satırlar)."""
    async with httpx.AsyncClient(timeout=60, headers=UA, follow_redirects=True) as client:
        home = (await client.get(BASE + "/")).text
        desktop = re.search(r"dt:'([^']+)'", home)
        items = [(uuid, _text(label)) for uuid, label in re.findall(r"\['zul\.menu\.Menuitem','([^']+)',\{[^}]*label:'([^']*)'", home)]
        target = next((uuid for uuid, label in items if "niversite Baz" in label and "renci Say" in label), None)
        if not desktop or not target:
            raise ValueError("YÖK İstatistik menüsü okunamadı")
        serial = 0

        async def send(uuid: str, command: str = "onClick", data: dict | None = None) -> str:
            nonlocal serial
            serial += 1
            await asyncio.sleep(GAP)
            r = await client.post(BASE + "/zkau", headers={"ZK-SID": str(serial)}, data={
                "dtid": desktop[1], "cmd_0": command, "uuid_0": uuid,
                "data_0": json.dumps(data if data is not None else {"pageX": 300, "pageY": 120, "which": 1, "x": 20, "y": 10})})
            r.raise_for_status()
            return r.text

        def button(name: str, source: str) -> str:
            found = re.search(r"\['zul\.wgt\.Button','([^']+)',\{id:'" + name + "'", source)
            if not found:
                raise ValueError(f"YÖK İstatistik düğmesi bulunamadı: {name}")
            return found[1]

        window = await send(target)
        popup = await send(button("btnYilSeciniz", window))
        listbox = re.search(r"\['zul\.sel\.Listbox','([^']+)',\{id:'lbYillar'", popup)
        first = re.search(r"\['zul\.sel\.Listitem','([^']+)',\{_loaded:true,_index:0\}", popup)
        year = re.search(r"_index:0\},\{\},\[\s*\['zul\.sel\.Listcell','[^']+',\{label:'([^']+)'", popup)
        if not listbox or not first:
            raise ValueError("YÖK İstatistik yıl listesi okunamadı")
        await send(listbox[1], "onSelect", {"items": [first[1]], "reference": first[1], "clearFirst": False, "selectAll": False})
        await send(button("btnSecVeAktar", popup))
        report = await send(button("btnRaporuGetir", window))
        paging = re.search(r"\['zul\.mesh\.Paging','([^']+)',\{[^}]*pageCount:(\d+)", report)
        rows = _rows(report)
        if paging and not first_page_only:
            for page in range(1, min(int(paging[2]), 80)):
                rows += _rows(await send(paging[1], "onPaging", {"": page}))
    return (year[1] if year else ""), rows


def _aggregate(year, rows: list[list[str]]) -> dict:
    universities: dict[str, dict] = {}
    for cells in rows:
        if len(cells) < 19:
            continue
        key = _name_key(cells[0])
        nums = []
        for value in cells[4:19]:
            try:
                nums.append(int(float(value.replace(".", "").replace(",", ".") or 0)))
            except ValueError:
                nums.append(0)
        entry = universities.setdefault(key, {"name": clean(cells[0]), "type": clean(cells[1]), "city": clean(cells[2]),
                                              **{level: {"male": 0, "female": 0, "total": 0} for level in LEVELS}, "modes": {}})
        if fold(cells[3]) == "toplam":
            continue  # tablo her üniversite için ayrıca bir "TOPLAM" satırı verir: toplanırsa sayılar iki katına çıkar
        for i, level in enumerate(LEVELS):
            male, female, total = nums[i * 3:i * 3 + 3]
            entry[level]["male"] += male
            entry[level]["female"] += female
            entry[level]["total"] += total
        entry["modes"][clean(cells[3])] = entry["modes"].get(clean(cells[3]), 0) + nums[14]  # öğrenim türüne göre toplam
    if len(universities) < 50:
        raise ValueError("YÖK İstatistik tablosu eksik okundu")
    return {"ts": time.time(), "year": year[1] if year else "", "universities": universities}


def cached(name: str) -> dict | None:
    """Kayıtlı tablodan üniversitenin satırı (ağ isteği yok; kayıt eskiyse de kullanılır)."""
    saved = _load(stale=True)
    if not saved:
        return None
    key = _name_key(name)
    row = saved["universities"].get(key) or next((v for k, v in saved["universities"].items() if k.startswith(key) or key.startswith(k)), None)
    return {**row, "year": saved.get("year", ""), "source": "YÖK İstatistik"} if row else None


async def students(name: str, fetch: bool = False) -> dict | None:
    """Üniversitenin öğrenci dağılımı. fetch=False: yalnız kayıttan (ağ isteği yok). fetch=True: kayıt yoksa ya da
    eskiyse tablo bir kez okunur (kullanıcı yenileme istedi)."""
    saved = _load()
    if saved is None and fetch:
        async with _LOCK:
            saved = _load()
            if saved is None:
                try:
                    saved = await _collect()
                    DIR.mkdir(parents=True, exist_ok=True)
                    _path().write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
                except (httpx.HTTPError, ValueError, StopIteration):
                    saved = _load(stale=True)
    if saved is None:
        saved = _load(stale=True)
    if not saved:
        return None
    key = _name_key(name)
    row = saved["universities"].get(key) or next((v for k, v in saved["universities"].items() if k.startswith(key) or key.startswith(k)), None)
    if not row:
        return None
    return {**row, "year": saved.get("year", ""), "source": "YÖK İstatistik"}
