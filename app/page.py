"""Site ajanı: eklentinin gönderdiği (kullanıcının gerçek tarayıcısında render edilmiş) sayfa üzerinde
genel yetenekler. Herhangi bir sitede çalışır; akademisyen görülürse akademik profil önerilir.

  understand  — sayfa türü, sayfadaki kişiler, tekrar eden öğeler, önerilen linkler
  ask         — sayfa (ve istenirse sitenin diğer sayfaları) üzerinde CAG/RAG soru-cevap
  find        — site içinde bir şeyi bul: Scrapling Spider + Qwen yön seçimi; bulunca sekme oraya gider
  extract     — tekrar eden öğeleri (kart/satır) Scrapling find_similar ile tabloya çevir, sayfalamayı izle
  apis        — REA ile sitenin gizli isteklerini çöz; eklentinin HAR kaydından öğren (öğrenme modu)
"""
from __future__ import annotations

import asyncio
import json
import math
import re
import tempfile
from collections import Counter
from urllib.parse import urljoin, urlparse

from . import navigator, rea, recipes
from .discover import STAFF_WORDS, _institution, _links, _visible_text, registrable, tr_title
from .net import fetch_smart, fetch_static, parse
from .text import clean, content_tokens, detect_title, expand_bilingual, fold, stem_tr, strip_titles

# ------------------------------------------------------------------ kişi tespiti
NAME_RE = re.compile(r"^[A-ZÇĞİÖŞÜ][a-zçğıöşü'’\-]+(?:\s+[A-ZÇĞİÖŞÜ][A-Za-zÇĞİÖŞÜçğıöşü'’\-]+){1,3}$")
NOT_NAME = re.compile(r"bölüm|fakülte|üniversite|enstitü|başkan|koordinat|kurul|ofis|müdür|sekreter|dekan|rektör|"
                      r"department|faculty|university|office|program|kadro|staff|iletişim|contact|duyuru|haber|"
                      r"\bemail\b|e-posta|homepage|web|detay|bilgi|öğretim|üyeleri|üyesi|mühendisli|bilimleri|"
                      r"profil|more|details|phone|tel\b|cv\b|github|linkedin|scholar|orcid", re.I)


_TITLE_ALT = (r"Prof\.?\s*Dr\.?|Profes[öo]r|Do[çc]\.?\s*Dr\.?|Do[çc]ent|Dr\.?\s*[ÖO]ğr\.?\s*[ÜU]yesi|Doktor\s+[ÖO]ğretim\s+[ÜU]yesi|"
              r"[ÖO]ğr\.?\s*G[öo]r\.?(?:\s*Dr\.?)?|[ÖO]ğretim\s+G[öo]revlisi|Ar[şs]\.?\s*G[öo]r\.?(?:\s*Dr\.?)?|"
              r"Ara[şs]t[ıi]rma\s+G[öo]revlisi|Assoc\.?\s*Prof\.?(?:\s*Dr\.?)?|Assist\.?\s*Prof\.?(?:\s*Dr\.?)?|"
              r"Asst\.?\s*Prof\.?(?:\s*Dr\.?)?|Professor|Associate Professor|Assistant Professor|Lecturer|Prof\.?|Dr\.")
_NAME_PART = r"((?:[A-ZÇĞİÖŞÜ][\wÇĞİÖŞÜçğıöşü'’\-]*\.?[ \t]+){1,3}[A-ZÇĞİÖŞÜ][\wÇĞİÖŞÜçğıöşü'’\-]+)"
# "Prof. Dr. | Ad Soyad" (unvan önce)  ve  "Ad Soyad | Profesör" (ad önce); öğe sınırı '|' aşılamaz
TITLED = re.compile(rf"(?<![\w])({_TITLE_ALT})[ \t]*\|?[ \t]*{_NAME_PART}")
NAME_THEN_TITLE = re.compile(rf"(?:^|\|)[ \t]*{_NAME_PART}[ \t]*\|[ \t]*({_TITLE_ALT})(?:[ \t]*\||$)")


def _clean_name(raw: str) -> str:
    """Yakalanan dizinin sonundaki ad olmayan kelimeleri (E-mail, Office, Homepage…) atar."""
    words = []
    for w in raw.split():
        if NOT_NAME.search(w) or re.match(r"(?i)e-?mail|tel|phone|ofis|office|oda|room", w) or re.fullmatch(_TITLE_ALT, w):
            break
        words.append(w)
    return tr_title(" ".join(words)) if 2 <= len(words) <= 4 else ""


def find_people(sel) -> list[dict]:
    """Unvanla birlikte geçen kişi adları (kadro kartları).

    İki yol: (1) öğenin kendi metni ad ise ve yakınında unvan varsa, (2) sayfa metninde
    "unvan + Ad Soyad" kalıbı (unvan ile ad ayrı HTML öğelerinde olduğunda da yakalar)."""
    out: dict[str, dict] = {}
    try:
        piped = clean(sel.get_all_text(separator=" | ", ignore_tags=("script", "style", "noscript", "template")))
    except Exception:  # noqa: BLE001
        piped = ""
    for m in TITLED.finditer(piped):
        name = _clean_name(m.group(2))
        if name and NAME_RE.match(name) and not NOT_NAME.search(name):
            out.setdefault(fold(name), {"name": name, "title": detect_title(m.group(1)) or m.group(1).strip()})
    for m in NAME_THEN_TITLE.finditer(piped):
        name = _clean_name(m.group(1))
        if name and NAME_RE.match(name) and not NOT_NAME.search(name):
            out.setdefault(fold(name), {"name": name, "title": detect_title(m.group(2)) or m.group(2).strip()})
    for el in sel.css("h1, h2, h3, h4, h5, h6, strong, b, a, span, p, td, li, div, [class*=name]")[:5000]:
        own = clean(el.text or "")
        if not (4 <= len(own) <= 70) or re.search(r"\d|@", own):
            continue
        title = detect_title(own)
        name = tr_title(strip_titles(own))
        if not NAME_RE.match(name) or NOT_NAME.search(name):
            continue
        if not title:
            parent = el.parent
            ctx = clean(parent.get_all_text(separator=" "))[:220] if parent is not None else ""
            title = detect_title(ctx)
        if not title:
            continue
        out.setdefault(fold(name), {"name": name, "title": title})
    return list(out.values())[:300]


# ----------------------------------------------------------- tekrar eden öğeler
PRICE_RE = re.compile(r"(?:₺|TL|\$|€|£)\s?\d[\d.,]*|\d[\d.,]*\s?(?:₺|TL|USD|EUR)")


def repeating_items(sel, base: str, limit: int = 300) -> tuple[list[dict], str]:
    """Sayfadaki en belirgin tekrar eden öğe grubu (ürün kartları, kişi kartları, tablo satırları…)."""
    groups: dict[str, list] = {}
    for el in sel.css("li, tr, article, div[class], section[class]")[:6000]:
        cls = " ".join(sorted((el.attrib.get("class") or "").split())[:3])
        parent = el.parent
        sig = f"{parent.tag if parent is not None else ''}>{el.tag}.{cls}"
        groups.setdefault(sig, []).append(el)
    best_sig, best_score = "", 0.0
    for sig, els in groups.items():
        if len(els) < 4:
            continue
        lens = [len(clean(e.get_all_text(separator=" "))) for e in els[:60]]
        avg = sum(lens) / len(lens)
        if not 15 <= avg <= 800:
            continue
        score = len(els) * math.log(avg + 1)
        if score > best_score:
            best_sig, best_score = sig, score
    if not best_sig:
        return [], ""
    rows = []
    for el in groups[best_sig][:limit]:
        text = clean(el.get_all_text(separator=" | "))
        a = el.css("a[href]")
        img = el.css("img[src]")
        title_el = [t for t in el.css("h1, h2, h3, h4, h5, strong, b, a") if len(clean(t.get_all_text(separator=" "))) >= 3]
        price = PRICE_RE.search(text)
        rows.append({
            "başlık": clean(title_el[0].get_all_text(separator=" ")) if title_el else text[:80],
            "metin": text[:400],
            "link": urljoin(base, a[0].attrib.get("href", "")) if a else "",
            "görsel": urljoin(base, img[0].attrib.get("src", "")) if img else "",
            **({"fiyat": price.group(0)} if price else {}),
        })
    return rows, best_sig


# -------------------------------------------------------------------- anlama
def understand(url: str, html: str) -> dict:
    sel = parse(html, url)
    text = _visible_text(sel)
    people = find_people(sel)
    items, sig = repeating_items(sel, url, limit=50)
    title = clean(sel.css("title::text").get() or "")
    if len(people) >= 3:
        kind = "staff_list"
    elif len(people) in (1, 2) and len(text) < 8000:
        kind = "person_profile"
    elif len(items) >= 6:
        kind = "listing"
    else:
        kind = "page"
    suggestions = []
    root = registrable(urlparse(url).hostname or "")
    if kind not in ("staff_list", "person_profile"):
        seen = set()
        for link, label in _links(sel, url):
            if registrable(urlparse(link).hostname or "") != root or not label or link in seen:
                continue
            blob = fold(f"{link} {label}")
            if STAFF_WORDS.search(blob) or re.search(r"fakulte|faculty|bolum|department|people|kadro", blob):
                seen.add(link)
                suggestions.append({"url": link, "text": label[:60]})
            if len(suggestions) >= 6:
                break
    return {"url": url, "title": title, "institution": _institution(sel), "page_type": kind,
            "people": people, "items": len(items), "item_preview": [r["başlık"] for r in items[:5]],
            "suggestions": suggestions, "chars": len(text), "pagination": len(navigator.pagination_links(sel, url))}


# ------------------------------------------------------------ soru-cevap (CAG/RAG)
SITE_KB: dict[str, dict] = {}  # url → {"chunks": [...], "pages": [...]}


def chunk_page(sel, url: str, size: int = 900, seen: set | None = None) -> list[dict]:
    """Sayfayı Markdown parçalarına böler. Her parçaya sayfa başlığı eklenir; `seen` ile sayfalar arasında
    tekrar eden parçalar (menü, altbilgi, duyuru bandı) atılır."""
    title = clean(sel.css("title::text").get() or "") or urlparse(url).path
    md = navigator.page_view(sel, max_chars=60000)
    parts, buf = [], ""
    for line in md.splitlines():
        if line.startswith("#") and len(buf) > 200:
            parts.append(buf)
            buf = ""
        buf += line + "\n"
        if len(buf) > size:
            parts.append(buf)
            buf = ""
    if buf.strip():
        parts.append(buf)
    out = []
    for p in parts:
        key = fold(p)[:300]
        if not p.strip() or len(key) < 20 or (seen is not None and key in seen):
            continue
        if seen is not None:
            seen.add(key)
        out.append({"id": f"S{len(out) + 1}", "url": url, "page": title[:80], "text": p.strip()})
    return out


async def add_site_pages(key: str, url: str, sel, log, max_pages: int = 12):
    """Sitenin aynı bölümündeki önemli sayfaları da bilgi tabanına ekler (Scrapling, paralel)."""
    root = registrable(urlparse(url).hostname or "")
    links = [u for u, t in _links(sel, url) if registrable(urlparse(u).hostname or "") == root and t][:max_pages]
    await log(f"Sitenin {len(links)} sayfası daha Scrapling ile okunuyor…")
    pages = await asyncio.gather(*(fetch_static(u, timeout=12) for u in links), return_exceptions=True)
    kb = SITE_KB[key]
    n = len(kb["chunks"])
    for p in pages:
        if isinstance(p, Exception) or p.status >= 400:
            continue
        for c in chunk_page(p.selector, p.url, seen=kb["seen"]):
            n += 1
            c["id"] = f"S{n}"
            kb["chunks"].append(c)
        kb["people"].extend(find_people(p.selector))
        kb["pages"].append(p.url)


def _bm25(question: str, chunks: list[dict], k: int = 6) -> list[dict]:
    docs = [content_tokens(c["text"]) for c in chunks]
    q = [stem_tr(t) for t in expand_bilingual(content_tokens(question))]
    df = Counter(t for d in docs for t in set(d))
    avg = sum(len(d) for d in docs) / max(1, len(docs))
    scored = []
    for c, d in zip(chunks, docs):
        tf = Counter(d)
        s = sum(math.log(1 + (len(docs) - df[t] + 0.5) / (df[t] + 0.5)) * tf[t] * 2.2 /
                (tf[t] + 1.2 * (0.25 + 0.75 * len(d) / max(avg, 1))) for t in q if t in tf)
        scored.append((s, c))
    return [c for s, c in sorted(scored, key=lambda x: -x[0])[:k] if s > 0] or chunks[:k]


PERSON_Q = re.compile(r"(?:adl[ıi]|isimli|var\s*m[ıi]|çalış[ıi]yor\s*mu|kimdir|\bkim\b|hoca(?:s[ıi])?\s+m[ıi])", re.I)
Q_STOP = set("bu şu o bir biri kişi kimse adlı isimli kurumda okulda üniversitede sitede burada orada rektör rektörü "
             "değil degil zaten acaba peki hoca hocası prof dr doç öğretim üyesi var varmı varsa mı mi kim kimdir "
             "ve ile de da ki".split())


def _question_name(question: str) -> str:
    """Sorudaki kişi adı: önce Büyük Harfle yazılmış 2–4 kelime, yoksa işaretten önceki son 2–3 anlamlı kelime."""
    caps = re.findall(r"[A-ZÇĞİÖŞÜ][a-zçğıöşü]+(?:\s+[A-ZÇĞİÖŞÜ][a-zçğıöşü]+){1,3}", question)
    caps = [c for c in caps if not all(w.lower() in Q_STOP for w in c.split())]
    if caps:
        return max(caps, key=len)
    m = PERSON_Q.search(question)
    if not m:
        return ""
    words = [w for w in re.findall(r"[\wçğıöşüÇĞİÖŞÜ]+", question[: m.start()]) if w.lower() not in Q_STOP]
    return " ".join(words[-3:]) if len(words) >= 2 else ""


def _person_lookup(question: str, kb: dict) -> dict | None:
    """'X var mı / X kim' sorularında önce sitenin kişi listesine ve metnine deterministik olarak bakılır."""
    from .text import name_in_text, name_score

    if not PERSON_Q.search(question):
        return None
    cand = _question_name(question)
    if len(cand.split()) < 2:
        return None
    for p in kb["people"]:
        if name_score(cand, p["name"]) >= 0.8:
            return {"name": p["name"], "title": p["title"], "found": True, "where": "kişi listesi"}
    for c in kb["chunks"]:
        if name_in_text(cand, c["text"]):
            return {"name": cand, "title": "", "found": True, "where": c["page"], "chunk": c}
    return {"name": cand, "found": False}


SYSTEM_SITE = (
    "Sen bir web sitesi asistanısın. Kurallar:\n"
    "1) YALNIZCA aşağıdaki SAYFA İÇERİĞİ'ne dayan. Kendi bilgini kullanma.\n"
    "2) Cevap içerikte varsa doğrudan ver ve dayandığın parçayı cümle sonunda [S#] ile göster. Kaynaksız iddia yazma.\n"
    "3) İçerikte yoksa YALNIZCA şu tek cümleyi yaz: 'Bu bilgi taranan sayfalarda yok.'\n"
    "4) Özür dileme, 'siteyi ziyaret edin' gibi kalıp cümleler kurma, kendinle çelişme.\n"
    "5) Kısa, düzgün Türkçe yaz.")


async def ask(url: str, html: str, question: str, history: list[dict], llm, deep: bool, log):
    """Sayfa/site soru-cevap. Bilgi tabanı küçükse CAG (tamamı, önbellekli önek), büyükse RAG."""
    key = url.split("#")[0]
    sel = parse(html, url)
    if key not in SITE_KB:
        seen: set = set()
        SITE_KB[key] = {"chunks": chunk_page(sel, url, seen=seen), "pages": [url], "seen": seen,
                        "people": find_people(sel)}
    kb = SITE_KB[key]
    if deep and len(kb["pages"]) == 1:
        await add_site_pages(key, url, sel, log)
    chunks = kb["chunks"]

    # Kişi soruları: önce deterministik arama (LLM tahmini yok)
    who = _person_lookup(question, kb)
    if who:
        yield {"meta": {"mode": "lookup", "chunks": len(chunks), "pages": len(kb["pages"]), "detail": " · kişi araması",
                        "sources": [{"id": who["chunk"]["id"], "url": who["chunk"]["url"], "page": who["chunk"]["page"]}]
                        if who.get("chunk") else []}}
        if who["found"]:
            extra = f" ({who['title']})" if who.get("title") else ""
            yield {"delta": f"Evet, **{who['name']}**{extra} bu sitede geçiyor — {who['where']}."
                            + (f" [{who['chunk']['id']}]" if who.get("chunk") else "")}
            yield {"person": who["name"]}
            if who.get("chunk") and llm.available:
                yield {"delta": "\n\n"}
                messages = [{"role": "system", "content": SYSTEM_SITE + "\n\nSAYFA İÇERİĞİ:\n"
                             + f"[{who['chunk']['id']}] ({who['chunk']['page']})\n{who['chunk']['text']}"},
                            {"role": "user", "content": f"{who['name']} bu içerikte hangi görev/unvanla geçiyor? Tek cümle."}]
                async for piece in llm.stream_chat(messages):
                    yield {"delta": piece}
        else:
            yield {"delta": f"**{who['name']}** bu sayfada ve bağlantılı {len(kb['pages']) - 1} sayfada yok — "
                            "site genelinde arıyorum…"}
            yield {"suggest_find": who["name"]}
        return

    full = "\n\n".join(f"[{c['id']}] ({c['page']})\n{c['text']}" for c in chunks)
    if len(full) // 3 <= 9000:
        mode, used = "cag", chunks
    else:
        mode, used = "rag", _bm25(question, chunks, k=8)
    context = "\n\n".join(f"[{c['id']}] ({c['page']})\n{c['text']}" for c in used)
    yield {"meta": {"mode": mode, "chunks": len(chunks), "pages": len(kb["pages"]),
                    "detail": f" · getirilen: {', '.join(c['id'] for c in used)}" if mode == "rag" else "",
                    "sources": [{"id": c["id"], "url": c["url"], "page": c["page"]} for c in used]}}
    if not llm.available:
        yield {"delta": "Yerel model kapalı; en ilgili bölümler:\n" + "\n".join(f"- [{c['id']}] {c['text'][:240]}" for c in used[:3])}
        return
    messages = [{"role": "system", "content": SYSTEM_SITE + "\n\nSAYFA İÇERİĞİ:\n" + context[:40000]}]
    for h in history[-6:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": str(h["content"])[:1500]})
    messages.append({"role": "user", "content": question})
    async for piece in llm.stream_chat(messages):
        yield {"delta": piece}


# ---------------------------------------------------------------------- bulma
GENERIC_Q = re.compile(r"(?i)\b(sayfa|iletişim|kadro|akademik|bölüm|fakülte|duyuru|haber|takvim|ders|program|ürün|"
                       r"fiyat|hakkında|staff|faculty|department|contact|about|news|page)\b")


def looks_like_person(query: str) -> bool:
    words = query.split()
    return 2 <= len(words) <= 4 and not GENERIC_Q.search(query) and not re.search(r"\d", query)


async def find_person(url: str, html: str, name: str, llm, log) -> dict | None:
    """Kişi arama — hiç görülmemiş sitede de çalışır: REA siteyi keşfeder (yeni/değişmişse), sayfalama ve
    hafızadaki kadro sayfaları taranır, sonra Scrapling Spider (≈90 sayfa) ile Qwen ajanı yarışır."""
    from .discover import locate

    async def plog(step, status, msg):
        await log(msg if len(msg) < 140 else msg[:140] + "…")

    profile, report = await locate(url, name, plog, llm, html)
    if not profile.found:
        return None
    where = profile.listing_url or profile.source_url
    return {"url": where, "profile_url": profile.source_url if profile.source_url != where else "",
            "title": f"{profile.get('title', '')} {profile.name}".strip(), "person": profile.name,
            "pages": (report.get("crawl") or {}).get("pages", 0), "winner": _how_found(report)}


def _how_found(report: dict) -> str:
    """Kişinin gerçekte hangi yolla bulunduğu (etiketler uydurulmaz)."""
    kinds = {e.get("kind") for e in (report.get("recipe") or {}).get("events", [])}
    if report.get("race_winner"):
        return report["race_winner"]
    if "memory" in kinds:
        return "memory"
    if (report.get("crawl") or {}).get("found_at"):
        return "spider"
    return "page"


async def find(url: str, html: str, query: str, llm, log) -> dict | None:
    if looks_like_person(query):
        await log(f"'{query}' bir kişi adı gibi görünüyor → site genelinde kişi araması (REA + Scrapling Spider + Qwen ajanı).")
        return await find_person(url, html, query, llm, log)
    return await find_generic(url, html, query, llm, log)


async def find_generic(url: str, html: str, query: str, llm, log) -> dict | None:
    """Site içinde arama: Scrapling ile linkler puanlanıp paralel taranır; Qwen her turda en umut
    verici linkleri seçer. Hedef: sorgu terimleri sayfanın başlık/başlıklarında ve metninde geçer."""
    root = registrable(urlparse(url).hostname or "")
    q_tokens = [t for t in content_tokens(query) if len(t) > 2]
    if not q_tokens:
        return None

    def score_link(u, t):
        blob = fold(f"{u} {t}")
        return sum(2 if tok in fold(t) else 1 for tok in q_tokens if tok in blob)

    def is_target(sel, text, page_url):
        # Menülerde her kelime geçebilir; hedef sayfada terimlerin çoğu başlıkta/adres yolunda olmalı.
        heads = fold(" ".join(clean(h.get_all_text(separator=" ")) for h in sel.css("title, h1, h2, h3")[:8]))
        where = heads + " " + fold(urlparse(page_url).path)
        body = fold(text)
        strong = sum(1 for t in q_tokens if t in where)
        return all(t in body for t in q_tokens) and strong >= max(1, math.ceil(len(q_tokens) * 0.6))

    sel = parse(html, url)
    seen = {url.rstrip("/")}
    frontier = [(url, sel)]
    pages = 0
    for step in range(4):
        candidates = []
        for page_url, s in frontier:
            for u, t in _links(s, page_url):
                if registrable(urlparse(u).hostname or "") == root and u.rstrip("/") not in seen:
                    candidates.append((score_link(u, t), u, t))
        candidates.sort(key=lambda x: -x[0])
        picked = [c for c in candidates if c[0] > 0][:8]
        if llm.available and len(candidates) > 8:
            listing = "\n".join(f"{i}. {t[:60]} — {urlparse(u).path[:60]}" for i, (_, u, t) in enumerate(candidates[:60]))
            data = await llm.json(f"Kullanıcı bu sitede şunu arıyor: '{query}'. Aşağıdaki linklerden hedefe en hızlı "
                                  f"götürecek en fazla 4 tanesinin numarasını seç.\n{listing}\nJSON: {{\"links\": [..]}}",
                                  {"type": "object", "properties": {"links": {"type": "array", "items": {"type": "integer"}}},
                                   "required": ["links"]}, timeout=45)
            for i in (data or {}).get("links", [])[:4]:
                if isinstance(i, int) and 0 <= i < min(60, len(candidates)) and candidates[i] not in picked:
                    picked.insert(0, candidates[i])
        if not picked:
            break
        await log(f"Tur {step + 1}: {len(picked)} sayfa Scrapling ile açılıyor…")
        results = await asyncio.gather(*(fetch_smart(u) for _, u, _ in picked[:10]), return_exceptions=True)
        frontier = []
        for (_, u, _), res in zip(picked[:10], results):
            seen.add(u.rstrip("/"))
            if isinstance(res, Exception) or res.status >= 400:
                continue
            pages += 1
            text = _visible_text(res.selector)
            if is_target(res.selector, text, res.url):
                return {"url": res.url, "title": clean(res.selector.css("title::text").get() or ""), "pages": pages}
            frontier.append((res.url, res.selector))
    return None


# ------------------------------------------------------------------- veri çıkarma
async def extract(url: str, html: str, log, max_pages: int = 5) -> dict:
    sel = parse(html, url)
    rows, sig = repeating_items(sel, url)
    pages = [url]
    for purl in navigator.pagination_links(sel, url)[: max_pages - 1]:
        try:
            p = await fetch_smart(purl)
        except Exception:  # noqa: BLE001
            continue
        more, _ = repeating_items(p.selector, p.url)
        rows.extend(more)
        pages.append(p.url)
        await log(f"Sayfalama: {len(pages)}. sayfa okundu ({len(rows)} satır).")
    seen, unique = set(), []
    for r in rows:
        k = (r["başlık"], r["link"])
        if k not in seen:
            seen.add(k)
            unique.append(r)
    return {"rows": unique, "pattern": sig, "pages": pages}


# -------------------------------------------------------------- gizli API'ler (REA)
def _capture_from_rea_har(path: str) -> rea.Capture:
    """REA'nın HAR çözümlemesini (inspect-web-network-capture) Capture nesnesine çevirir."""
    import subprocess

    cmd = rea.rea_command()
    proc = subprocess.run([*cmd, "inspect-web-network-capture", path, "har", "--format", "json"],
                          capture_output=True, text=True, timeout=120)
    doc = json.loads(proc.stdout or "{}")
    cap = rea.Capture(ok=bool(doc.get("normalized_result")), evidence_id=doc.get("evidence_id", ""))
    for rec in ((doc.get("normalized_result") or {}).get("records") or []):
        r = rec.get("reported") or {}
        req, resp = r.get("request") or {}, r.get("response") or {}
        tx = rea.Transaction(id=str(rec.get("ordinal")), method=req.get("method", "GET"), url=req.get("url", ""),
                             resource_type=r.get("_resourceType", "xhr"), status=resp.get("status"),
                             request_body=(req.get("postData") or {}).get("text"),
                             response_body=((resp.get("content") or {}).get("text") or "").encode(),
                             media_type=(resp.get("content") or {}).get("mimeType", ""))
        cap.transactions.append(tx)
    return cap


def summarize_capture(cap: rea.Capture, host_root: str) -> list[dict]:
    out = []
    for t in cap.transactions:
        if t.is_noise or t.resource_type not in ("xhr", "fetch", "document"):
            continue
        u = urlparse(t.url)
        data = t.json()
        shape = ""
        if isinstance(data, dict):
            shape = "{" + ", ".join(list(data.keys())[:8]) + "}"
        elif isinstance(data, list):
            shape = f"[{len(data)} kayıt]"
        out.append({"method": t.method, "url": t.url, "path": u.path, "status": t.status,
                    "same_site": registrable(u.hostname or "") == host_root, "json": data is not None, "shape": shape,
                    "body": (t.request_body or "")[:200]})
    out.sort(key=lambda x: (not x["same_site"], not x["json"]))
    return out[:40]


async def apis_live(url: str, log) -> dict:
    """REA siteyi gerçek tarayıcıda açar, tüm istekleri kaydeder ve çözer."""
    await log("REA sayfayı gerçek tarayıcıda açıp tüm ağ trafiğini kaydediyor…")
    cap = await rea.recon(url)
    root = registrable(urlparse(url).hostname or "")
    if not cap.ok:
        return {"ok": False, "error": cap.error[:200]}
    return {"ok": True, "evidence_id": cap.evidence_id, "requests": len(cap.transactions),
            "calls": summarize_capture(cap, root)}


async def learn_from_har(url: str, har: dict, name: str, attrs: dict, log) -> dict:
    """Eklentinin gerçek tarayıcıdan kaydettiği HAR → REA → tarif."""
    with tempfile.NamedTemporaryFile("w", suffix=".har", delete=False) as fh:
        json.dump(har, fh)
        path = fh.name
    await log(f"REA, gerçek tarayıcından gelen {len(har.get('log', {}).get('entries', []))} isteği çözümlüyor…")
    cap = await asyncio.to_thread(_capture_from_rea_har, path)
    root = registrable(urlparse(url).hostname or "")
    store = recipes.load(root)
    learned = []
    if name:
        r = recipes.learn_replay(cap, name, "person_lookup")
        if r:
            store["replay"]["person_lookup"] = r
            learned.append(r)
    if attrs:
        r, _ = recipes.learn_detail(cap, attrs)
        if r:
            store["replay"]["profile_detail"] = r
            learned.append(r)
    apis = summarize_capture(cap, root)
    store.setdefault("observed_apis", [])
    known = {a["path"] for a in store["observed_apis"]}
    for a in apis:
        if a["same_site"] and a["json"] and a["path"] not in known:
            store["observed_apis"].append({"method": a["method"], "path": a["path"], "shape": a["shape"],
                                           "at": recipes._now()})
    recipes.event(store, "learned_from_browser", f"{len(cap.transactions)} istek, {len(learned)} tarif",
                  evidence_id=cap.evidence_id)
    recipes.save(store)
    return {"ok": cap.ok, "evidence_id": cap.evidence_id, "requests": len(cap.transactions), "calls": apis,
            "learned": [{"purpose": r["purpose"], "method": r["method"], "url": r["url"]} for r in learned]}
