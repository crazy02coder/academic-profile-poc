"""Ders bilgi paketi yapısı bilinen üniversitelerin modülleri için ortak altyapı (bkz. catalogs/__init__.py).

Bir modül sitenin adreslerini ve tablo düzenini doğrudan bilir; arama motoru, tahmin ya da model çağrısı kullanmaz.
Buradaki yardımcılar: istek katmanı (Http), ders kaydı ve ders içeriği biçimleri, bölüm adı eşleme.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from urllib.parse import urlsplit

import httpx
from lxml import html as html_tree

from ..config import ROOT, USER_AGENT
from ..discover import registrable
from ..text import clean, fold

CACHE = ROOT / "data" / "student-view" / "catalog"
PAGE_TTL = 24 * 3600
MIN_COURSES = 5
HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.6"}
_RETRY = {429, 500, 502, 503, 504}


class Http:
    """Bir üniversitenin sitelerine istek: yalnız modülün alan adları, aynı anda en çok `limit` istek, geçici hatada iki
    yeniden deneme, kodlama tespiti ve disk önbelleği (aynı sayfa 24 saat içinde yeniden indirilmez). fresh=True
    ("Yeniden tara") önbelleği okumaz ama yazar."""

    def __init__(self, client: httpx.AsyncClient, domains, limit: int = 6, fresh: bool = False):
        self.client, self.domains, self.fresh = client, set(domains), fresh
        self.gate = asyncio.Semaphore(limit)
        self.requests = 0

    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        return parts.scheme in {"http", "https"} and registrable(parts.hostname or "") in self.domains

    async def raw(self, url: str, *, data=None, json_body=None, headers: dict | None = None, ttl: float = PAGE_TTL,
                  limit: int = 6_000_000) -> bytes:
        """Yanıt gövdesi. data/json_body verilirse POST; headers yalnız bu isteğe eklenir."""
        if not self.allowed(url):
            raise ValueError(f"Kurum alan adı dışında adres: {url}")
        key = hashlib.sha256(json.dumps([url, data, json_body], sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()[:32]
        path = CACHE / "pages" / f"{key}.bin"
        if ttl and not self.fresh:
            try:
                if time.time() - path.stat().st_mtime < ttl:
                    return path.read_bytes()
            except OSError:
                pass
        async with self.gate:
            body = await self._send(url, data, json_body, headers, limit)
        if ttl and body:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".tmp")
                tmp.write_bytes(body)
                tmp.replace(path)
            except OSError:
                pass
        return body

    async def _send(self, url, data, json_body, headers, limit) -> bytes:
        from ..org_assets import public_client, read_public
        plain = data is None and json_body is None and not headers
        for attempt in range(3):
            self.requests += 1
            try:
                if plain:
                    # Yönlendirmeleri tek tek izler, yanıt boyutunu sınırlar ve eksik TLS zincirini onarır.
                    body, _, final = await read_public(self.client, url, limit)
                    if not self.allowed(final):
                        raise ValueError(f"Kurum alan adı dışına yönlenen adres: {url}")
                    return body
                method = "GET" if data is None and json_body is None else "POST"
                response = await self.client.request(method, url, data=data, json=json_body, headers=headers, follow_redirects=True)
                if not self.allowed(str(response.url)):
                    raise ValueError(f"Kurum alan adı dışına yönlenen adres: {url}")
                response.raise_for_status()
                if len(response.content) > limit:
                    raise ValueError("Yanıt çok büyük")
                return response.content
            except httpx.ConnectError as exc:
                if "certificate_verify_failed" in str(exc).lower() and not plain and attempt == 0:
                    # Eksik ara sertifika: zincir onarılır, onarılmış paketi kullanan yeni istemciyle sürdürülür.
                    from ..net import repaired_bundle
                    try:
                        await asyncio.to_thread(repaired_bundle, url)
                    except Exception:
                        raise exc
                    old = self.client
                    self.client = public_client(timeout=old.timeout, headers=dict(old.headers), cookies=old.cookies)
                    await old.aclose()
                    continue
                if attempt == 2:
                    raise
            except httpx.HTTPStatusError as exc:
                if attempt == 2 or exc.response.status_code not in _RETRY:
                    raise
            except httpx.TransportError:
                if attempt == 2:
                    raise
            await asyncio.sleep(0.6 * (attempt + 1))
        raise ValueError("İstek tamamlanamadı")

    async def text(self, url: str, *, encoding: str = "", **kwargs) -> str:
        return decode(await self.raw(url, **kwargs), encoding)

    async def tree(self, url: str, **kwargs):
        """lxml ağacı; boş ya da HTML olmayan yanıtta boş bir <html> düğümü."""
        text = await self.text(url, **kwargs)
        return parse(text)

    async def json(self, url: str, **kwargs):
        return json.loads(await self.text(url, **kwargs))


def decode(body: bytes, encoding: str = "") -> str:
    if encoding:
        return body.decode(encoding, errors="replace")
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        declared = re.search(rb"charset=[\"']?([a-zA-Z0-9_-]+)", body[:4000])
        try:
            return body.decode(declared[1].decode("ascii") if declared else "windows-1254", errors="replace")
        except LookupError:
            return body.decode("windows-1254", errors="replace")


def parse(text: str):
    try:
        return html_tree.fromstring(text) if text and text.strip() else html_tree.fromstring("<html></html>")
    except Exception:  # noqa: BLE001 — bozuk belge boş sayfa sayılır
        return html_tree.fromstring("<html></html>")


def txt(node) -> str:
    """Düğümün (ya da metnin) temiz, tek satırlık metni; None → ''."""
    if node is None:
        return ""
    if isinstance(node, str):
        return clean(node)
    return clean(" ".join(node.itertext()))


def lines(node) -> str:
    """Düğümün metni, satır sonları korunarak (<br>, <p>, <li> yeni satır başlatır)."""
    if node is None:
        return ""
    out = []
    for piece in node.xpath(".//text()|.//br|.//p|.//li|.//tr|.//div"):
        out.append("\n" if not isinstance(piece, str) else str(piece))
    rows = [clean(row) for row in "".join(out).split("\n")]
    return "\n".join(row for row in rows if row)


def number(value) -> float | None:
    """'7,5' → 7.5; '6 AKTS' → 6.0; sayı yoksa None."""
    match = re.search(r"\d+(?:[.,]\d+)?", str(value if value is not None else ""))
    return float(match[0].replace(",", ".")) if match else None


def _num(value) -> str:
    n = number(value)
    return "" if n is None else str(int(n)) if n == int(n) else str(n)


def period(semester=None, *, year=None, term=None, elective: bool = False) -> str:
    """Dönem etiketi: period(3) → '3. dönem'; period(year=2, term=1) → '3. dönem'; elective → 'Seçmeli dersler'."""
    if elective:
        return "Seçmeli dersler"
    n = number(semester)
    if n is None and year is not None and term is not None:
        y, t = number(year), number(term)
        n = (y - 1) * 2 + t if y and t else None
    return f"{int(n)}. dönem" if n and 1 <= n <= 14 else ""


def course(code: str, name: str, period: str = "", *, ects=None, credit=None, kind: str = "", url: str = "",
           source: str = "", **content) -> dict:
    """Ders kaydı (öğrenci görünümünün "course_catalog" satırı).

    url: dersin içerik sayfası — arayüz ders açılınca içeriği bu adresten ister (modülün detail() işlevi okur).
    source: yalnız "Kaynağı aç" bağlantısı (içerik sayfası yoksa ders planının adresi).
    content: içerik ders planıyla birlikte geldiyse doğrudan kayda yazılır: objective, content, outcomes (metin).
             Bu durumda url boş bırakılır; arayüz içeriği kayıttan gösterir.
    """
    code, name = clean(code), clean(name)
    bits = [f"Kredi: {clean(str(credit))}" if credit not in (None, "") else "", f"AKTS: {_num(ects)}" if _num(ects) else "",
            f"Tür: {clean(kind)}" if kind else ""]
    item = {"title": clean(f"{code} {name}")[:200], "code": code, "name": name, "detail": " · ".join(b for b in bits if b),
            "period": period or "", "quote": clean(f"{code} {name} {' '.join(b for b in bits if b)}")[:500],
            "source_url": source or url, "detail_url": url, "type": "courses"}
    if number(ects) is not None:
        item["ects"] = number(ects)
    item.update({key: value for key, value in content.items() if value})
    return item


def detail(url: str, title: str = "", *, info=(), parts=(), weeks=(), outcomes=(), assessment=(), workload: dict | None = None) -> dict | None:
    """Ders içeriği (arayüzün ders kartı biçimi). İçerik yoksa None.

    info: [(etiket, değer)] — dil, tür, ön koşul, öğretim elemanı…
    parts: [(başlık, metin)] — "Dersin amacı", "Dersin içeriği", "Kaynaklar"…
    weeks: [(hafta, konu)] ya da [(hafta, konu, hazırlık)]
    outcomes: [metin]; assessment: [(ad, yüzde)] ya da [(ad, yüzde, sayı)]; workload: {"hours": "150", "ects": "5"}
    """
    info = [{"label": clean(a)[:60], "value": clean(b)[:200]} for a, b in info if clean(a) and clean(b)][:10]
    parts = [{"heading": clean(a)[:150], "text": str(b).strip()[:12000]} for a, b in parts if clean(a) and b and str(b).strip()][:30]
    rows = []
    for row in weeks:
        week, topic, prep = (list(row) + ["", ""])[:3]
        if clean(topic):
            rows.append({"week": clean(str(week))[:12], "topic": clean(topic)[:400], "prep": clean(prep)[:200]})
    outs = [clean(x)[:300] for x in outcomes if clean(x)][:15]
    marks = []
    for row in assessment:
        name, percent, count = (list(row) + [""])[:3]
        pct = number(percent)
        if clean(name) and pct and 0 < pct <= 100:
            marks.append({"name": clean(name)[:80], "count": clean(str(count)), "percent": int(pct) if pct == int(pct) else pct})
    syllabus = {"info": info, "weeks": rows, "assessment": marks, "workload": workload or {}, "outcomes": outs} \
        if rows or marks or outs else {}
    if not syllabus and info:
        parts = [{"heading": x["label"], "text": x["value"]} for x in info] + parts
    if not syllabus and not parts:
        return None
    return {"url": url, "title": clean(title)[:160], "description": "", "paragraphs": [], "sections": [], "items": 0,
            "course_content": parts, "syllabus": syllabus}


_FILLER = {"ve", "bilimleri", "bilimi", "bilim", "teknolojileri", "teknolojisi", "and", "of", "the", "sciences", "science"}


def _names(program: dict) -> list[str]:
    return [n for n in [program.get("name"), *(program.get("aliases") or [])] if isinstance(n, str) and n.strip()]


def pick(programs: list[dict], faculty: str, department: str) -> dict | None:
    """Program listesinden bölümü seçer. Ad anahtarı veri setiyle aynı kuraldadır (poc_dataset.unit_key: İngilizce
    program adları Türkçe karşılığına çevrilir, "(İngilizce)" gibi ekler varyanttır). Aynı ad birden çok fakültedeyse
    seçilen fakültedeki; birden çok varyant varsa istenen, istenmediyse işaretsiz olan seçilir. Emin olunamazsa None."""
    from ..poc_dataset import unit_key
    key, variant = unit_key(department)
    if not key:
        return None
    words = set(key.split())
    rows = [(program, *unit_key(name)) for program in programs for name in _names(program)]
    same = [row for row in rows if row[1] == key]
    if not same:
        # Yalnız dolgu kelimesi farkı ("Moleküler Biyoloji ve Genetik" ~ "Moleküler Biyoloji Genetik Bilimi").
        same = [row for row in rows if row[1] and (set(row[1].split()) ^ words) <= _FILLER and (set(row[1].split()) & words) - _FILLER]
    if not same:
        # Tek programlı fakülte (Tıp, Hukuk, Diş Hekimliği): YÖK bölümü fakültenin adıyla verir, site programı başka
        # adla yazar ("Tıp Doktorluğu", "Diş Programı (İngilizce)"). Fakültesinin adı bölümle aynı olan programlar,
        # hepsi aynı programın dil varyantlarıysa (tek ad) seçilir.
        inside = [(program, *unit_key(program.get("name") or "")) for program in programs
                  if unit_key(program.get("faculty") or "")[0] == key]
        if len({row[1] for row in inside}) == 1:
            same = inside
    if not same:
        return None
    fac = unit_key(faculty)[0] if faculty else ""
    inside = [row for row in same if fac and unit_key(row[0].get("faculty") or "")[0] == fac]
    same = inside or same
    if variant:
        marked = {row[2] for row in same}
        same = [row for row in same if row[2] == variant] or (same if marked == {""} else [])
    else:
        same = [row for row in same if not row[2]] or [row for row in same if row[2] in {"tr", "+io", "tr+io"}] or same
    found = list({id(row[0]): row[0] for row in same}.values())
    if len(found) > 1 and not inside:
        homes = {fold(p.get("faculty") or "") for p in found}
        if len(homes) > 1:
            return None  # aynı adlı program iki fakültede; hangisi olduğu bilinmiyor
    return found[0] if found else None
