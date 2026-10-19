"""Qwen ile sayfa anlama: Scrapling sayfayı temiz Markdown'a çevirir, Qwen okuyup yapılandırılmış bilgi çıkarır.

Kurallar asıl yolu çizmez; yalnızca DOĞRULAMA (Qwen'in verdiği ad/birim sayfa metninde gerçekten geçiyor mu)
ve model yoksa YEDEK olarak kullanılır. Böylece "Ad | Dekan", "Dekan: Ad", tablo, kart gibi biçim farkları
için ayrı düzenli ifade yazmaya gerek kalmaz.

Çıktı:
  people — görevleriyle kişiler: ad, unvan, görev (Rektör, Dekan, Dekan Yardımcısı, Bölüm Başkanı…), birim
  units  — sayfada listelenen akademik birimler: ad, tür (fakülte/enstitü/yüksekokul/bölüm), link
"""
from __future__ import annotations

import hashlib
from urllib.parse import urlparse

from . import navigator
from .discover import _links, registrable
from .text import clean, fold

UNIT_KINDS = ["fakülte", "enstitü", "yüksekokul", "bölüm", "diğer"]
SCHEMA = {
    "type": "object",
    "properties": {
        "people": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "title": {"type": "string"},
            "role": {"type": "string"}, "unit": {"type": "string"}}, "required": ["name", "role"]}},
        "units": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "kind": {"type": "string", "enum": UNIT_KINDS},
            "link": {"type": "integer"}}, "required": ["name", "kind"]}},
    },
    "required": ["people", "units"],
}
_CACHE: dict[str, dict] = {}


def _links_for_prompt(sel, url: str, limit: int = 120) -> list[tuple[str, str]]:
    root = registrable(urlparse(url).hostname or "")
    out, seen = [], set()
    for u, t in _links(sel, url):
        t = clean(t)
        if not t or len(t) > 90 or registrable(urlparse(u).hostname or "") != root:
            continue
        key = fold(t)
        if key in seen:
            continue
        seen.add(key)
        out.append((u, t))
        if len(out) >= limit:
            break
    return out


ROLE_WORDS = {"rektor", "dekan", "mudur", "baskan", "baskani", "yardimcisi", "uyesi", "ogretim", "gorevlisi", "bolum"}


def _windows(text: str, word_rx, radius: int = 450, limit: int = 3500) -> str:
    """Yalnızca görev kelimesinin geçtiği bölgeler (modele bütün sayfayı okutmamak için)."""
    import re

    spans = []
    for m in re.finditer(word_rx, text):
        a, b = max(0, m.start() - radius), min(len(text), m.end() + radius)
        if spans and a <= spans[-1][1]:
            spans[-1] = (spans[-1][0], b)
        else:
            spans.append((a, b))
    return " … ".join(text[a:b] for a, b in spans)[:limit]


def _valid_name(name: str, page_f: str) -> bool:
    words = [w for w in name.split() if not w.endswith(".") and fold(w) not in ("prof", "dr", "doc")]
    if len(words) < 2 or any(fold(w) in ROLE_WORDS for w in words):
        return False  # "Rektör", "Müdür" gibi görev kelimeleri ad değildir
    return all(tok in page_f for tok in fold(" ".join(words)).split())


async def read_page(sel, url: str, llm, mode: str = "people", role_rx: str = "", focus: str = "") -> dict:
    """Qwen sayfayı okur. mode='people': role_rx'e uyan görevli(ler); mode='units': listelenen akademik birimler.
    Modele yalnızca gereken kısım verilir (görev kelimesi çevresi / link adları), sonuçlar sayfa metninde doğrulanır."""
    import re

    text = clean(sel.get_all_text(separator=" | ", ignore_tags=("script", "style", "noscript", "template")))
    key = hashlib.sha1(f"{mode}|{role_rx}|{url}|{text[:20000]}".encode()).hexdigest()
    if key in _CACHE:
        return _CACHE[key]
    result = {"people": [], "units": [], "url": url, "by": "none"}
    if not llm.available:
        return result
    page_f = fold(text)
    if mode == "people":
        region = _windows(text, re.compile(role_rx, re.I)) if role_rx else text[:3500]
        if not region:
            _CACHE[key] = result
            return result
        schema = {"type": "object", "properties": {"people": SCHEMA["properties"]["people"]}, "required": ["people"]}
        data = await llm.json(
            "Aşağıdaki metin bir üniversite sayfasından alınmıştır (öğeler '|' ile ayrılmış). Metinde bir GÖREVLE "
            "birlikte geçen HER kişiyi listele: name = unvanıyla birlikte adı (yazdığı gibi), role = o kişinin görevi "
            "(Dekan, Dekan Yardımcısı, Bölüm Başkanı, Rektör, Müdür…). Görevi yazmayanları ekleme. Bir kişinin görevi "
            "adının hemen önünde veya hemen arkasında yazar; görevi başka kişiye karıştırma.\n\n"
            f"METİN:\n{region}", schema, timeout=60) or {}
        for p in data.get("people") or []:
            name, role = clean(p.get("name") or ""), clean(p.get("role") or "")
            if role and _valid_name(name, page_f):
                result["people"].append({"name": name, "title": clean(p.get("title") or ""), "role": role,
                                         "unit": clean(p.get("unit") or ""), "url": url})
    else:
        links = _links_for_prompt(sel, url, limit=150)
        listing = "\n".join(f"{i}. {t}" for i, (_, t) in enumerate(links))
        schema = {"type": "object", "properties": {"units": SCHEMA["properties"]["units"]}, "required": ["units"]}
        data = await llm.json(
            "Aşağıda bir üniversite sayfasındaki link adları numaralı olarak var. Bunlardan akademik birim olanları seç: "
            "fakülte, enstitü, yüksekokul (meslek yüksekokulu dahil), bölüm. Menü başlıklarını ('Fakülteler', "
            f"'Akademik', 'Bölümler') birim sayma. kind: birimin türü, link: numarası. {focus}\n\nLİNKLER:\n{listing}",
            schema, timeout=60) or {}
        for u in data.get("units") or []:
            name = clean(u.get("name") or "")
            idx = u.get("link", -1)
            link = links[idx][0] if isinstance(idx, int) and 0 <= idx < len(links) else ""
            if not link:
                link = next((lu for lu, lt in links if fold(lt) == fold(name)), "")
            if name and link and fold(name) in page_f:
                kind = u.get("kind") or "diğer"
                if re.search(r"(?i)y[uü]ksekokul|school", name):
                    kind = "yüksekokul"  # model türü karıştırırsa addan düzelt
                elif re.search(r"(?i)enstit|institute", name):
                    kind = "enstitü"
                elif re.search(r"(?i)fak[uü]lte|faculty", name):
                    kind = "fakülte"
                result["units"].append({"name": name, "kind": kind, "url": link})
    result["by"] = "qwen"
    _CACHE[key] = result
    return result


async def pick_links(sel, url: str, llm, goal: str, k: int = 2) -> list[tuple[str, str]]:
    """Qwen'e menü linkleri arasından hedefe götürecek olanları seçtirir (sabit kelime listesi yok)."""
    links = _links_for_prompt(sel, url, limit=150)
    if not links:
        return []
    listing = "\n".join(f"{i}. {t} — {urlparse(u).path[:60]}" for i, (u, t) in enumerate(links))
    data = await llm.json(
        f"Bir üniversite sitesindesin. Hedef: {goal}. Aşağıdaki linklerden hedefe en olası götürecek en fazla {k} "
        "tanesinin numarasını seç (menü başlıkları genelde: Akademik, Öğretim, Birimler, Fakülteler…). Hiçbiri "
        f"uygun değilse boş liste ver.\n\nLİNKLER:\n{listing}\n" + 'JSON: {"links": [numaralar]}',
        {"type": "object", "properties": {"links": {"type": "array", "items": {"type": "integer"}}}, "required": ["links"]},
        timeout=45, fast=True) or {}
    return [links[i] for i in data.get("links", []) if isinstance(i, int) and 0 <= i < len(links)][:k]


# ============================================================ soru yorumlama ve sayfa değerlendirme
INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "terms": {"type": "array", "items": {"type": "string"}},
        "page_types": {"type": "array", "items": {"type": "string"}},
        "answer_type": {"type": "string", "enum": ["kişi", "sayı", "tarih", "liste", "belge", "metin"]},
        "person": {"type": "string"},
        "unit": {"type": "string"},
    },
    "required": ["terms", "page_types", "answer_type"],
}


async def interpret(question: str, llm, categories: dict[str, str]) -> dict | None:
    """Qwen soruyu yorumlar: TR+EN eş anlamlı arama ifadeleri, aranacak sayfa türleri, beklenen cevap türü."""
    if not llm.available:
        return None
    cats = "\n".join(f"- {k}: {v}" for k, v in categories.items())
    data = await llm.json(
        "Bir üniversite web sitesinde kullanıcının sorusunu cevaplamak için arama planı çıkar.\n"
        "terms: sitede aranacak 3-8 KISA ifade; Türkçe ve İngilizce eş anlamlıları dahil (örn. rektör → rektör, "
        "rektörlük, rector, president, yönetim). Soru kalıplarını (kim, nedir, kaç) yazma.\n"
        f"page_types: cevabın büyük olasılıkla bulunduğu sayfa türleri, şu anahtarlardan (en olasıdan başla):\n{cats}\n"
        "answer_type: beklenen cevap türü. person: soru adı verilmiş bir kişiyle ilgiliyse adı (yalnızca ad ya da "
        "soyad verilmişse onu yaz, örn. 'Gülsüm adında biri var mı' → person='Gülsüm'), değilse boş. "
        "unit: soru belirli bir fakülte/bölümle sınırlıysa adı, değilse boş.\n"
        f"SORU: {question}", INTENT_SCHEMA, timeout=40)  # zincirin yönünü belirlediği için büyük model
    if not data or not data.get("terms"):
        return None
    junk = {"adinda", "adli", "isimli", "adin", "akademisyen", "akademisyenler", "var", "varmi", "biri", "kisi",
            "hoca", "hocasi", "ogretim uyesi", "personel"}
    data["terms"] = [clean(t) for t in data["terms"] if clean(t) and fold(t) not in junk][:8]
    data["page_types"] = [p for p in data.get("page_types") or [] if p in categories][:3]
    data["person"] = clean(data.get("person") or "")
    data["unit"] = clean(data.get("unit") or "")
    return data


JUDGE_SCHEMA = {
    "type": "object",
    "properties": {"page": {"type": "integer"}, "answer": {"type": "string"}, "quote": {"type": "string"}},
    "required": ["page", "answer", "quote"],
}


def _norm(s: str) -> str:
    import re

    return re.sub(r"\s+", " ", fold(s)).strip()


def _excerpt(text: str, terms: list[str], budget: int) -> str:
    """Sayfa bütçeye sığmıyorsa: kısa başlangıç + arama ifadelerinin geçtiği bölgeler (cevap kesilmesin)."""
    import re

    if len(text) <= budget:
        return text
    head = text[: budget // 4]
    spans = []
    for term in terms:
        for w in [x for x in term.split() if len(x) > 3][:3] or [term]:
            for m in re.finditer(re.escape(w[:6]), text, re.I):
                spans.append((max(0, m.start() - 500), min(len(text), m.end() + 500)))
    spans.sort()
    merged = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    body, left = [], budget - len(head)
    for a, b in merged:
        if a < len(head):
            a = len(head)
        if a >= b:
            continue
        piece = text[a:b]
        if len(piece) > left:
            piece = piece[:left]
        body.append(piece)
        left -= len(piece)
        if left <= 0:
            break
    return head + (" … " + " … ".join(body) if body else text[len(head): budget])


async def judge(question: str, pages: list[dict], llm, terms: list[str] | None = None) -> dict | None:
    """Qwen sayfaları (kelime filtresi olmadan) okur ve cevabın hangisinde olduğuna karar verir.
    Kabul koşulu: verdiği alıntı ilgili sayfanın metninde birebir geçmeli (uydurma engeli)."""
    if not pages or not llm.available:
        return None
    budget = max(3500, 12000 // len(pages))
    block = "\n\n".join(f"=== SAYFA {i} — {p['title']} ({p['url']})\n{_excerpt(p['text'], terms or [], budget)}"
                          for i, p in enumerate(pages, 1))
    data = await llm.json(
        "Aşağıdaki web sayfalarını oku ve soruyu cevapla. Kurallar:\n"
        "- Cevap hangi sayfada AÇIKÇA yazıyorsa page = o sayfanın numarası (1'den başlar); hiçbirinde yoksa page = 0.\n"
        "- answer: kısa, düzgün Türkçe cevap (sayfa İngilizce olsa da). Tahmin etme.\n"
        "- quote: cevabın dayandığı ifadeyi sayfadan HARFİ HARFİNE kopyala (en fazla 25 kelime).\n"
        f"SORU: {question}\n\n{block}", JUDGE_SCHEMA, timeout=90)
    if not data:
        return None
    quote, answer = clean(data.get("quote") or ""), clean(data.get("answer") or "")
    q_n = _norm(quote)
    if not q_n or not answer or data.get("page") in (0, -1):
        return None

    def contains(pg):  # alıntı birebir ya da (model birkaç kelimeyi kırptıysa) uzun bir parçası sayfada geçmeli
        page_n = _norm(pg["text"])
        return q_n in page_n or (len(q_n) > 30 and (q_n[:40] in page_n or q_n[-40:] in page_n))

    # Sayfa numarası yerine alıntının geçtiği sayfa esas alınır (model numarayı karıştırsa da doğru sayfa bulunur)
    stated = data.get("page")
    order = ([stated - 1] if isinstance(stated, int) and 1 <= stated <= len(pages) else []) + list(range(len(pages)))
    i = next((k for k in order if contains(pages[k])), None)
    if i is None:
        return None
    return {"page": pages[i], "answer": answer, "quote": quote}
