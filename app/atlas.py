"""Sitenin anlam haritası (atlas): tüm linkleri tek tek gezmek yerine sitenin İSKELETİNİ anlamak.

Kurulum (site başına bir kez, data/atlas/<alan adı>.json):
  * Kaynaklar  — ana sayfa + menü linkleri (Scrapling), sitemap.xml adresleri, REA'nın gözlediği site içi API'ler.
  * Anlam      — her link bir kategoriye atanır (ders programı, kadro, bölüm, takvim, duyuru, başvuru, iletişim…).
                 Türkçe/İngilizce kurallar çoğu linki anında etiketler; soru yorumu ve seçim Qwen'dedir.
  * Derinleşme — "X bölümünün ders programı" gibi sorularda bölümün sitesi açılır, menüsü haritaya eklenir
                 (üniversitelerde bu bilgiler çoğunlukla bölüm alt sitelerindedir).

Soru gelince: soru kategorisi + varsa bölüm belirlenir → harita içinden adaylar seçilir → Qwen en uygun
adresleri seçer → belge (PDF/Excel) ise link verilir, sayfa ise Scrapling okur ve Qwen kaynakla cevaplar.
"""
from __future__ import annotations

import json
import re
import time
from urllib.parse import urlparse

from . import rea
from .config import ROOT
from .discover import _links, registrable
from .net import fetch_smart, parse
from .text import clean, content_tokens, fold, stem_tr

ATLAS_DIR = ROOT / "data" / "atlas"
FILE_EXT = re.compile(r"\.(pdf|xlsx?|docx?|pptx?|ods|odt)(\?|$)", re.I)

# Sıra önemli: özel kategoriler genel olanlardan önce
CATEGORIES = [
    ("ders_programi", "Ders programı / müfredat / ders içerikleri",
     r"ders ?program|haftalik program|course schedule|timetable|weekly schedule|mufredat|curriculum|ders icerik|"
     r"izlence|syllabus|ders plan|ders listesi|course list|courses|dersler|ders bilgi|bologna|akts|ects"),
    ("takvim", "Akademik takvim / sınav takvimi", r"takvim|calendar|sinav|exam|final|vize|butunleme"),
    ("kadro", "Akademik kadro / personel", r"kadro|staff|faculty member|ogretim (?:uye|eleman)|people|personel|akademisyen"),
    ("basvuru", "Başvuru / kayıt / burs / ücret", r"basvuru|kayit|admission|burs|scholarship|ucret|fee|aday|kontenjan|tercih|apply"),
    ("duyuru", "Duyuru / haber / etkinlik", r"duyuru|haber|news|etkinlik|event|announcement|blog"),
    ("iletisim", "İletişim / ulaşım", r"iletisim|contact|ulasim|adres|harita|map|bize ulas"),
    ("yonetim", "Yönetim / organizasyon", r"rektor|dekan|yonetim|senato|kurul|baskan|mutevelli|organizasyon|management|board"),
    ("ogrenci", "Öğrenci işleri / yönetmelik / formlar",
     r"ogrenci isleri|yonetmelik|yonerge|mevzuat|form|dilekce|obs|registrar|regulation|staj|internship|mezuniyet"),
    ("bolum", "Bölüm / program / fakülte",
     r"bolum|department|muhendislig|program|fakulte|faculty|enstitu|institute|yuksekokul|school|lisans|graduate|undergraduate"),
    ("arastirma", "Araştırma / proje / yayın / laboratuvar", r"arastirma|research|proje|project|yayin|publication|laboratuvar|\blab|merkez|center"),
    ("yasam", "Kütüphane / kampüs yaşamı", r"kutuphane|library|yurt|yemek|spor|kulup|topluluk|saglik|kafeterya|kampus|campus"),
]
CAT_RE = [(k, d, re.compile(rx)) for k, d, rx in CATEGORIES]
CAT_NAMES = {k: d for k, d, _ in CATEGORIES} | {"api": "Site içi API (REA)", "diger": "Diğer"}
CAT_WORDS = set("ders programi program haftalik mufredat takvim akademik kadro bolum fakulte iletisim duyuru basvuru "
                "burs ucret yonetmelik form staj sinav nedir nerede var hangi kim ne zaman nasil icin bilgi sayfa "
                "listesi icerik izlence".split())


def categorize(text: str, url: str) -> str:
    blob = fold(f"{text} {urlparse(url).path.replace('-', ' ').replace('_', ' ').replace('/', ' ')} {urlparse(url).hostname or ''}")
    for key, _, rx in CAT_RE:
        if rx.search(blob):
            return key
    return "diger"


def question_category(question: str) -> str:
    q = fold(question)
    for key, _, rx in CAT_RE:
        if key != "bolum" and rx.search(q):
            return key
    return "bolum" if CAT_RE[[k for k, _, _ in CATEGORIES].index("bolum")][2].search(q) else ""


def _entries_from(sel, base: str, root: str, source: str) -> list[dict]:
    out = []
    for u, t in _links(sel, base):
        host = urlparse(u).hostname or ""
        if registrable(host) != root or not (t or FILE_EXT.search(u)):
            continue
        out.append({"u": u.split("#")[0], "t": clean(t)[:90], "cat": categorize(t, u), "host": host, "src": source})
    return out


def _path(root: str):
    ATLAS_DIR.mkdir(parents=True, exist_ok=True)
    return ATLAS_DIR / f"{root}.json"


def load(root: str) -> dict | None:
    p = _path(root)
    if p.exists():
        data = json.loads(p.read_text())
        ttl = 3600 if data.get("incomplete") else 7 * 86400  # ana sayfa okunamadıysa 1 saat sonra yeniden kur
        if time.time() - data.get("at", 0) < ttl:
            return data
    return None


def save(atlas: dict):
    seen, uniq = set(), []
    for e in atlas["entries"]:
        if e["u"] not in seen:
            seen.add(e["u"])
            uniq.append(e)
    atlas["entries"] = uniq[:6000]
    _path(atlas["root"]).write_text(json.dumps(atlas, ensure_ascii=False))


async def build(url: str, html: str, log) -> dict:
    """Haritayı kurar ya da hafızadan döndürür."""
    from .live import sitemap_urls

    root = registrable(urlparse(url).hostname or "")
    atlas = load(root)
    if atlas:
        return atlas
    await log("Sitenin anlam haritası çıkarılıyor (menüler, site haritası, REA ile arka plan istekleri)…")
    entries = _entries_from(parse(html, url), url, root, "açık sayfa")
    home = f"{urlparse(url).scheme}://www.{root}/" if not urlparse(url).hostname.startswith("www.") else \
        f"{urlparse(url).scheme}://{urlparse(url).hostname}/"
    home_ok = False
    for _ in range(2):  # geçici hatalara karşı bir kez daha dene
        try:
            hp = await fetch_smart(home)
            if hp.status < 400:
                entries += _entries_from(hp.selector, hp.url, root, "ana sayfa menüsü")
                home_ok = True
                break
        except Exception:  # noqa: BLE001
            continue
    for u in (await sitemap_urls(url, log))[:5000]:
        slug = urlparse(u).path.rstrip("/").rsplit("/", 1)[-1].replace("-", " ").replace("_", " ")
        entries.append({"u": u, "t": slug[:90], "cat": categorize(slug, u), "host": urlparse(u).hostname or "", "src": "sitemap.xml"})
    apis: list[dict] = []  # REA gözlemi burada çıkarıldı: harita kurulumuna katkısı yoktu, ~10 sn sürüyordu
    atlas = {"root": root, "at": time.time(), "entries": entries + apis, "hubs": {}, "incomplete": not home_ok}
    save(atlas)
    counts = summary(atlas)
    await log("Anlam haritası hazır: " + ", ".join(f"{CAT_NAMES[k].split(' /')[0]} {n}" for k, n in counts[:6]))
    return atlas


def summary(atlas: dict) -> list[tuple[str, int]]:
    c: dict[str, int] = {}
    for e in atlas["entries"]:
        c[e["cat"]] = c.get(e["cat"], 0) + 1
    return sorted(c.items(), key=lambda kv: -kv[1])


Q_WORDS = set("kim kimdir nedir ne neler nerede nereden zaman hangi hangisi nasil kac var mi mu midir bu su bir icin "
              "ile ve veya da de ki acaba peki lutfen basliyor baslar bitiyor biter ogrenebilir bulabilir goster "
              "where what when which how is are the kac tane adi adlari isim isimleri sirasiyla ayni zamanda kurum "
              "kurumun kurumda universite universitenin universitede okul okulun sayisi liste listesi tum butun her "
              "hepsi olan nelerdir".split())
NEWS_RE = re.compile(r"news|haber|duyuru|announce|blog|etkinlik|event|/\d{4}/\d{1,2}/|documents/news|basin")
MENU_SOURCES = ("açık sayfa", "ana sayfa menüsü", "bölüm sitesi", "dizin")
DIRECTORY_RE = re.compile(r"fakulteler|bolumler|akademik birim|departments|faculties|academic units|akademik programlar|"
                          r"programs|lisans programlari|schools")


def _topic_tokens(question: str) -> list[str]:
    """Kategori ve soru kelimeleri dışındaki konu/bölüm terimleri (örn. 'bilgisayar', 'yazılım')."""
    out = []
    for t in content_tokens(question, stem=False):
        if t in Q_WORDS or t in CAT_WORDS or len(t) <= 2:
            continue
        st = stem_tr(t)
        if st not in CAT_WORDS and st not in Q_WORDS:
            out.append(st)
    return out


def _topic_hits(e: dict, topic: list[str]) -> int:
    blob = fold(f"{e['t']} {e['u']}")
    return sum(1 for t in topic if t[:5] in blob)


def _score(e: dict, cat: str, topic: list[str]) -> float:
    url_f = fold(e["u"])
    s = 3.0 if cat and e["cat"] == cat else 0.0
    hits = _topic_hits(e, topic)
    s += 1.5 * hits
    if e.get("src", "").startswith(MENU_SOURCES):
        s += 1.5  # menüde yer alan link, site haritasındaki sıradan adresten daha anlamlı
    if NEWS_RE.search(url_f) and cat != "duyuru":
        s -= 2.5
    if FILE_EXT.search(e["u"]):
        s += 0.5 if (hits or not topic) else -2.0
    if not re.search(r"[a-zA-ZçğıöşüÇĞİÖŞÜ]{3}", e["t"] or ""):
        s -= 1.0  # "55", "352" gibi anlamsız link adları
    return s


async def expand_hub(atlas: dict, hub_url: str, log, kind: str = "bölüm sitesi") -> list[dict]:
    """Bölüm/fakülte alt sitesinin menüsünü haritaya ekler (bir kez, sonra hafızadan)."""
    if hub_url in atlas["hubs"]:
        return atlas["hubs"][hub_url]
    try:
        page = await fetch_smart(hub_url)
    except Exception:  # noqa: BLE001
        return []
    entries = _entries_from(page.selector, page.url, atlas["root"], f"{kind}: {urlparse(page.url).hostname}")
    atlas["hubs"][hub_url] = entries
    atlas["entries"] += entries
    save(atlas)
    await log(f"{kind.capitalize()} haritaya eklendi: {page.url[:70]} ({len(entries)} link).")
    return entries


async def route(atlas: dict, question: str, llm, log, intent: dict | None = None) -> tuple[list[dict], str]:
    """Soru → haritadaki en uygun adresler. (adaylar, açıklama)
    intent (Qwen'in soru yorumu) varsa kategori ve konu kelimeleri ondan alınır; yoksa kurallarla tahmin edilir."""
    if intent:
        cat = next((p for p in intent.get("page_types", []) if p in CAT_NAMES), "")
        unit_topic = [stem_tr(t) for t in content_tokens(intent.get("unit") or "", stem=False) if len(t) > 2]
        term_topic = [stem_tr(t) for term in intent.get("terms", []) for t in content_tokens(term, stem=False) if len(t) > 2]
        topic = unit_topic or list(dict.fromkeys(term_topic))[:8]
    else:
        cat = question_category(question)
        topic = _topic_tokens(question)
    pool = atlas["entries"]
    # Bölüm belirtilmiş ama soru bölümün kendisi değilse → önce bölüm sitesine in
    if topic and cat and cat != "bolum" and (not intent or intent.get("unit")):
        def hubs_in(entries):
            hs = [e for e in entries if not FILE_EXT.search(e["u"]) and not NEWS_RE.search(fold(e["u"]))
                  and _topic_hits(e, topic) >= len(topic) and re.search(r"[a-zA-ZçğıöşüÇĞİÖŞÜ]{3}", e["t"] or "")]
            return sorted(hs, key=lambda e: (-(e["cat"] == "bolum"), -e.get("src", "").startswith(MENU_SOURCES), len(e["u"])))

        hubs = hubs_in(pool)
        if not hubs:
            # Bölüm adı menüde yok → "Fakülteler / Bölümler / Akademik Birimler" dizinine in
            dirs = [e for e in pool if e.get("src", "").startswith(MENU_SOURCES) and DIRECTORY_RE.search(fold(e["t"] or ""))][:2]
            for d in dirs:
                await log(f"Bölüm menüde yok → dizin sayfası açılıyor: {d['t']}")
                hubs = hubs_in(await expand_hub(atlas, d["u"], log, kind="dizin"))
                if hubs:
                    break
        for h in hubs[:2]:
            await log(f"Soru bir bölüme ait → bölüm sitesine iniliyor: {h['t'] or h['u']}")
            sub = await expand_hub(atlas, h["u"], log)
            inside = [e for e in sub if e["cat"] == cat]
            if inside:
                pool = inside + [h]
                topic = []  # artık bölümün içindeyiz; konu kelimesi aramaya gerek yok
                break
    ranked = sorted(pool, key=lambda e: -_score(e, cat, topic))
    cands = [e for e in ranked[:40] if _score(e, cat, topic) > 0]
    if not cands:
        return [], ""
    chosen = cands[:3]
    if llm.available and len(cands) > 3:
        listing = "\n".join(f"{i}. [{CAT_NAMES.get(e['cat'], e['cat'])}] {e['t'] or '-'} — {e['u'][:110]}" for i, e in enumerate(cands[:30]))
        data = await llm.json(
            f"Kullanıcının sorusu: '{question}'.\nAşağıda bir üniversite sitesinin anlam haritasından aday adresler var. "
            "Soruyu en doğrudan cevaplayacak en fazla 3 adresin numarasını seç (sayfa veya belge).\n"
            f"{listing}\nJSON: {{\"picks\": [numaralar], \"reason\": \"kısa\"}}",
            {"type": "object", "properties": {"picks": {"type": "array", "items": {"type": "integer"}},
                                              "reason": {"type": "string"}}, "required": ["picks"]}, timeout=45, fast=True)
        picks = [cands[i] for i in (data or {}).get("picks", []) if isinstance(i, int) and 0 <= i < min(30, len(cands))]
        if picks:
            chosen = picks[:3]
    label = f"anlam haritası → {CAT_NAMES.get(cat, 'genel')}" + (f" ({', '.join(topic[:3])})" if topic else "")
    return chosen, label
