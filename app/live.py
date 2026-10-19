"""Canlı site asistanı: her soru siteyi O AN araştırarak cevaplanır (önceden taranmış veri tabanı yok).

Zincir (her basamak sonuç vermezse bir sonrakine geçilir):
  1. Açık sayfa      — cevap ekrandaki sayfadaysa hemen.
  2. Sitenin araması — HTML form ise Scrapling doğrudan kullanır; JS araması ise REA bir kez öğrenir,
                       sonra tarif Scrapling ile tarayıcısız tekrar oynatılır. WordPress ise ?s= denenir.
  3. Site haritası   — robots.txt / sitemap.xml'deki tüm adresler; soruyla eşleşen adresler okunur.
  4. Canlı tarama    — kişi sorusunda Qwen ajanı + Scrapling Spider yarışı; diğerlerinde Qwen yönlendirmeli tarama.
  5. Okuma + cevap   — bulunan sayfalar o an okunur, Qwen kaynak linkiyle cevaplar; yoksa "bulamadım" der.

Saklanan tek şey hızlandırma amaçlı yol bilgisidir (REA'nın öğrendiği arama isteği, site haritası adresleri).
"""
from __future__ import annotations

import asyncio
import json
import math
import re
import time
from collections import Counter
from urllib.parse import urlencode, urljoin, urlparse

from . import navigator, recipes
from .config import ROOT
from .discover import _links, registrable
from .net import fetch_smart, fetch_static, parse
from .page import SYSTEM_SITE, _question_name, chunk_page, find_generic, find_people, looks_like_person, PERSON_Q
from .text import clean, content_tokens, expand_bilingual, fold, name_in_text, stem_tr

SITEMAP_DIR = ROOT / "data" / "sitemaps"
QUESTION_WORDS = set("kim kimdir nedir ne neler nerede nereden ne zaman zaman hangi hangisi nasıl kaç var mı mi mu mü "
                     "varmı varmi midir mıdır bu şu o bir için ile ve veya da de ki acaba peki lütfen bana söyle "
                     "who what where when which how is are the a an of".split())
SEARCH_INPUT_NAMES = ("q", "s", "search", "query", "keyword", "keywords", "k", "ara", "aranan", "arama", "term", "text",
                      "searchword", "search_query", "kelime")


# --------------------------------------------------------------------------- yardımcılar
PERSON_CUE = re.compile(r"(?i)\b(adında|adinda|adlı|adli|isimli|akademisyen|hoca|öğretim üyesi|ogretim uyesi|personel)\b")


def _single_name_ok(name: str, question: str) -> bool:
    """Tek kelimelik ad/soyad ('Gülsüm adında biri') ancak soruda kişi ipucu varsa kişi araması sayılır."""
    return len(name.split()) == 1 and len(name) >= 3 and bool(PERSON_CUE.search(question)) and not re.search(r"\d", name)


def person_in(question: str) -> str:
    """Sorudaki kişi adı — yalnızca Büyük Harfle yazılmışsa ya da 'adlı/isimli' ile belirtilmişse."""
    if not PERSON_Q.search(question) and not PERSON_CUE.search(question):
        return ""
    name = _question_name(question)
    if not name:
        single = re.search(r"\b([A-ZÇĞİÖŞÜ][a-zçğıöşü]{2,})\s+(?:adında|adinda|adlı|adli|isimli)", question)
        return single.group(1) if single else ""
    if not looks_like_person(name):
        return ""
    capitalized = all(w[:1].isupper() for w in name.split())
    marked = re.search(r"(?i)\b(adl[ıi]|isimli)\b", question)
    return name if capitalized or marked else ""


def search_terms(question: str) -> str:
    """Sitenin aramasına gönderilecek ifade: kişi adı varsa o, yoksa soru kelimeleri ayıklanmış çekirdek."""
    name = person_in(question)
    if name:
        return name
    words = [w for w in re.findall(r"[\wçğıöşüÇĞİÖŞÜ\-]+", question) if w.lower() not in QUESTION_WORDS and len(w) > 1]
    return " ".join(words[:5])


def _relevant(chunk_text: str, q_tokens: list[str], person: str) -> bool:
    if person:
        return name_in_text(person, chunk_text)
    body = fold(chunk_text)
    hits = sum(1 for t in q_tokens if t in body)
    return hits >= max(1, math.ceil(len(q_tokens) * 0.5))


def _rank(question: str, chunks: list[dict], k: int = 8) -> list[tuple[float, dict]]:
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
    return sorted(scored, key=lambda x: -x[0])[:k]


async def _read(urls: list[str], seen_urls: set, limit: int = 8) -> list[dict]:
    """Sayfaları Scrapling ile paralel okur (duvar varsa stealth), parçalara böler."""
    todo = [u for u in dict.fromkeys(urls) if u.split("#")[0] not in seen_urls][:limit]
    for u in todo:
        seen_urls.add(u.split("#")[0])
    pages = await asyncio.gather(*(fetch_smart(u) for u in todo), return_exceptions=True)
    chunks, seen = [], set()
    for p in pages:
        if isinstance(p, Exception) or p.status >= 400:
            continue
        chunks.extend(chunk_page(p.selector, p.url, seen=seen))
    return chunks


# ------------------------------------------------------------------- 2) sitenin araması
def _form_search_url(sel, base: str, query: str) -> str | None:
    """HTML arama formu (GET) varsa doğrudan sonuç adresi."""
    for form in sel.css("form"):
        method = (form.attrib.get("method") or "get").lower()
        inputs = form.css("input")
        field = None
        for inp in inputs:
            name = (inp.attrib.get("name") or "").strip()
            typ = (inp.attrib.get("type") or "text").lower()
            if typ in ("search", "text") and name and (name.lower() in SEARCH_INPUT_NAMES or "search" in name.lower()
                                                      or "ara" in name.lower() or typ == "search"):
                field = name
                break
        if not field or method != "get":
            continue
        params = {field: query}
        for inp in inputs:
            if (inp.attrib.get("type") or "").lower() == "hidden" and inp.attrib.get("name"):
                params[inp.attrib["name"]] = inp.attrib.get("value", "")
        action = urljoin(base, form.attrib.get("action") or base)
        return action + ("&" if "?" in action else "?") + urlencode(params)
    return None


async def site_search(url: str, sel, html: str, query: str, store: dict, log) -> tuple[list[str], str]:
    """Sitenin kendi araması → sonuç linkleri. (linkler, kullanılan yol)"""
    root = registrable(urlparse(url).hostname or "")
    tokens = [t for t in fold(query).split() if len(t) > 2]

    def result_links(rsel, rurl):
        out = []
        for u, t in _links(rsel, rurl):
            if registrable(urlparse(u).hostname or "") != root or re.search(r"[?&](s|q|search|query)=", u):
                continue
            blob = fold(f"{t} {u}")
            if tokens and sum(1 for tok in tokens if tok in blob) >= max(1, math.ceil(len(tokens) * 0.5)):
                out.append(u)
        return list(dict.fromkeys(out))[:10]

    # a) Daha önce REA'nın öğrendiği arama tarifi
    recipe = store["replay"].get("site_search")
    if recipe:
        try:
            resp = await recipes.replay_static(recipe, query)
            links = result_links(resp, str(resp.url))
            if links:
                return links, f"sitenin araması (REA tarifi, tarayıcısız: {recipe['method']} {urlparse(recipe['url']).path})"
        except Exception:  # noqa: BLE001
            pass
    # b) HTML arama formu
    form_url = _form_search_url(sel, url, query)
    # c) WordPress varsayılan araması
    if not form_url and ("wp-content" in html or 'content="WordPress' in html):
        form_url = urljoin(url, "/?" + urlencode({"s": query}))
    if form_url:
        try:
            page = await fetch_smart(form_url)
            links = result_links(page.selector, page.url)
            if links:
                return links, "sitenin araması (HTML formu, Scrapling)"
        except Exception:  # noqa: BLE001
            pass
    # d) JS ile çalışan arama kutusu → REA öğrenir (daha önce çözülemediyse bir gün tekrar denenmez)
    css = navigator._search_selector(sel)
    failed_at = store.get("search_failed_at", 0)
    if css and time.time() - failed_at > 86400:
        await log("Sitenin araması JavaScript ile çalışıyor → REA arama kutusunu kullanıp isteği öğreniyor…")
        cap = await navigator._rea_search(url, css, query, store, log)
        if cap and cap.dom:
            links = result_links(parse(cap.dom, cap.final_url or url), cap.final_url or url)
            if links:
                return links, "sitenin araması (REA ile öğrenildi)"
        store["search_failed_at"] = time.time()
    return [], ""


# ---------------------------------------------------------------------- 3) site haritası
async def sitemap_urls(url: str, log) -> list[str]:
    root = registrable(urlparse(url).hostname or "")
    SITEMAP_DIR.mkdir(parents=True, exist_ok=True)
    cache = SITEMAP_DIR / f"{root}.json"
    if cache.exists():
        data = json.loads(cache.read_text())
        if time.time() - data.get("at", 0) < 7 * 86400:
            return data["urls"]
    base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    queue, seen, urls = [], set(), []
    try:
        robots = await fetch_static(base + "/robots.txt", timeout=10)
        queue += re.findall(r"(?im)^sitemap:\s*(\S+)", robots.html or "")
    except Exception:  # noqa: BLE001
        pass
    queue += [base + p for p in ("/sitemap.xml", "/sitemap_index.xml", "/wp-sitemap.xml")]
    while queue and len(seen) < 25 and len(urls) < 30000:
        sm = queue.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        try:
            page = await fetch_static(sm, timeout=15)
        except Exception:  # noqa: BLE001
            continue
        body = page.html or ""
        if page.status >= 400 or "<loc>" not in body:
            continue
        locs = [clean(x) for x in re.findall(r"<loc>\s*(.*?)\s*</loc>", body, re.S)]
        if "<sitemapindex" in body:
            queue += locs
        else:
            urls += locs
    urls = list(dict.fromkeys(u for u in urls if registrable(urlparse(u).hostname or "") == root))
    cache.write_text(json.dumps({"at": time.time(), "urls": urls}))
    if urls:
        await log(f"Site haritası: {len(urls)} adres bulundu (robots.txt / sitemap.xml).")
    return urls


def match_sitemap(urls: list[str], query: str, person: str, k: int = 8) -> list[str]:
    tokens = [stem_tr(t) for t in content_tokens(person or query) if len(t) > 2]
    if not tokens:
        return []
    scored = []
    for u in urls:
        path = fold(urlparse(u).path.replace("-", " ").replace("_", " ").replace("/", " "))
        hits = sum(1 for t in tokens if t[:5] in path)
        if hits:
            scored.append((hits, -len(path), u))
    need = len(tokens) if person else max(1, math.ceil(len(tokens) * 0.5))
    return [u for h, _, u in sorted(scored, reverse=True) if h >= need][:k]


# ------------------------------------------------------------------------------ ana akış
NEGATIVE = re.compile(r"(?i)taranan sayfalarda yok|bulunamad|yer alm[ıi]yor|bilgi (?:verilmemi|yok)|belirtilmemi|bahsedilmemi")


async def _draft(llm, question: str, chunks: list[dict], history: list[dict]) -> str:
    for i, c in enumerate(chunks, 1):
        c["id"] = f"S{i}"
    context = "\n\n".join(f"[{c['id']}] ({c['page']} — {c['url']})\n{c['text']}" for c in chunks)
    if not llm.available:
        return "\n".join(f"- [{c['id']}] {c['text'][:240]}" for c in chunks[:3])
    messages = [{"role": "system", "content": SYSTEM_SITE + "\n\nSAYFA İÇERİĞİ:\n" + context[:30000]}]
    for h in history[-4:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": str(h["content"])[:1200]})
    messages.append({"role": "user", "content": question})
    out = ""
    async for piece in llm.stream_chat(messages):
        out += piece
    return out.strip()


async def _read_pages(urls: list[str], seen_urls: set, limit: int = 3) -> list[dict]:
    """Sayfaları Scrapling ile paralel okur; her sayfa Qwen'e verilecek temiz metne (Markdown) çevrilir."""
    from .discover import _visible_text

    todo = [u for u in dict.fromkeys(urls) if u.split("#")[0] not in seen_urls][:limit]
    seen_urls.update(u.split("#")[0] for u in todo)
    fetched = await asyncio.gather(*(fetch_smart(u) for u in todo), return_exceptions=True)
    out = []
    for p in fetched:
        if isinstance(p, Exception) or p.status >= 400:
            continue
        md = navigator.page_view(p.selector, max_chars=40000)
        text = md if len(md) > 400 else _visible_text(p.selector)[:40000]
        out.append({"url": p.url, "title": clean(p.selector.css("title::text").get() or "")[:90] or p.url, "text": text})
    return out


def _page_from_html(html: str, url: str) -> dict:
    from .discover import _visible_text

    sel = parse(html, url)
    md = navigator.page_view(sel, max_chars=40000)
    return {"url": url, "title": clean(sel.css("title::text").get() or "")[:90] or url,
            "text": md if len(md) > 400 else _visible_text(sel)[:40000]}


async def answer_single(url: str, html: str, question: str, history: list[dict], llm, log):
    """Tek soru: Qwen soruyu yorumlar → aşamalar sayfa getirir → Qwen her aşamada sayfaları okuyup cevabın
    nerede olduğuna karar verir (alıntı sayfada doğrulanır). Model yoksa kelime eşleştirmeli yedek."""
    from . import atlas as atlas_mod
    from . import understand

    root = registrable(urlparse(url).hostname or "")
    store = recipes.load(root)
    sel = parse(html, url)
    seen_urls: set = {url.split("#")[0]}

    # 1) Qwen soruyu yorumlar (TR+EN eş anlamlılar, sayfa türü) — AYNI ANDA açık sayfa okunup değerlendirilir
    page0 = _page_from_html(html, url)
    interp_task = asyncio.create_task(understand.interpret(question, llm, {k: v for k, v in atlas_mod.CAT_NAMES.items() if k != "api"}))
    open_task = asyncio.create_task(understand.judge(question, [page0], llm)) if llm.available else None
    intent = await interp_task
    if intent:
        await log("Soru yorumu: aranacak ifadeler " + ", ".join(intent["terms"][:6])
                  + (f" · sayfa türü {', '.join(atlas_mod.CAT_NAMES[p].split(' /')[0] for p in intent['page_types'])}"
                     if intent["page_types"] else ""))
        person = intent["person"] if intent["person"] and (looks_like_person(intent["person"]) or _single_name_ok(intent["person"], question)) \
            else person_in(question)
        terms = intent["terms"]
    else:
        person = person_in(question)
        terms = [search_terms(question)] if search_terms(question) else []
    query = person or (terms[0] if terms else "")
    if open_task is not None:
        verdict = await open_task
        if not verdict and len(page0["text"]) > 12000 and terms:  # uzun sayfada terimlerin geçtiği yerlerle bir kez daha
            verdict = await understand.judge(question, [page0], llm, terms=terms + ([person] if person else []))
        if verdict:
            yield {"meta": {"mode": "live", "path": ["açık sayfa"], "found": True,
                            "sources": [{"id": "S1", "url": page0["url"], "page": page0["title"]}]}}
            if person:
                yield {"person": person}
            yield {"delta": f"{verdict['answer']} [S1]\n\n> “{verdict['quote']}”"}
            return
        await log("Açık sayfada cevap yok → anlam haritası, sitenin araması ve site haritası paralel deneniyor…")

    async def stage_page():
        return [_page_from_html(html, url)], "açık sayfa"

    atlas_hit: dict = {}

    async def stage_atlas():
        if person:
            return [], ""
        at = await atlas_mod.build(url, html, log)
        chosen, label = await atlas_mod.route(at, question, llm, log, intent=intent)
        if not chosen:
            await log("Anlam haritasında uygun bölüm yok.")
            return [], ""
        files = [e for e in chosen if atlas_mod.FILE_EXT.search(e["u"])]
        pages = [e["u"] for e in chosen if not atlas_mod.FILE_EXT.search(e["u"])]
        atlas_hit.update({"files": files, "pages": [e for e in chosen if e["u"] in pages]})
        await log(f"{label}: " + ", ".join((e["t"] or e["u"])[:40] for e in chosen))
        return (await _read_pages(pages, seen_urls) if pages else []), label

    async def stage_search():
        for term in (terms[:2] if not person else [person]):
            await log(f"Sitenin aramasında aranıyor: “{term}”…")
            links, how = await site_search(url, sel, html, term, store, log)
            if links:
                await log(f"{how}: {len(links)} sonuç → okunuyor…")
                return await _read_pages(links, seen_urls), how
        await log("Sitenin araması yok ya da sonuç vermedi.")
        return [], ""

    async def stage_sitemap():
        urls = await sitemap_urls(url, log)
        cand = []
        for term in (terms[:4] if not person else [person]):
            cand += match_sitemap(urls, term, person, k=4)
        cand = list(dict.fromkeys(cand))[:6]
        if not cand:
            await log("Site haritasında eşleşen adres yok." if urls else "Site haritası yok.")
            return [], ""
        await log(f"Site haritasında {len(cand)} ilgili adres → okunuyor…")
        return await _read_pages(cand, seen_urls, limit=4), "site haritası (sitemap.xml)"

    async def stage_crawl():
        if person:
            from .page import find_person

            await log("Kişi araması: REA siteyi çözümlüyor, Scrapling Spider ve Qwen ajanı yarışıyor…")
            hit = await find_person(url, html, person, llm, log)
            if not hit:
                return [], ""
            pages = [u for u in (hit.get("profile_url"), hit["url"]) if u]
            label = {"agent": "canlı tarama (Qwen ajanı)", "spider": "canlı tarama (Scrapling Spider)",
                     "memory": "kadro hafızası (daha önce öğrenilmiş sayfa, Scrapling)",
                     "page": "başlangıç sayfası / sayfalama (Scrapling)"}.get(hit.get("winner"), "canlı tarama")
            return await _read_pages(pages, seen_urls, limit=2), label
        await log("Canlı tarama: Qwen yönlendirmesiyle site geziliyor…")
        hit = await find_generic(url, html, " ".join(terms[:2]) or question, llm, log)
        if not hit:
            return [], ""
        return await _read_pages([hit["url"]], seen_urls, limit=1), "canlı tarama (Qwen + Scrapling)"

    tried, best_page = [], []

    async def finish(verdict: dict, how: str):
        page = verdict["page"]
        recipes.save(store)
        out = [{"meta": {"mode": "live", "path": [how], "found": True,
                         "sources": [{"id": "S1", "url": page["url"], "page": page["title"]}]}}]
        if person:
            out.append({"person": person})
        out.append({"delta": f"{verdict['answer']} [S1]\n\n> “{verdict['quote']}”"})
        return out

    if not query:
        stages = []
    elif llm.available:
        stages = [stage_atlas, stage_search, stage_sitemap]
    else:
        stages = [stage_atlas, stage_search, stage_sitemap, stage_crawl]

    if llm.available and stages:
        # Aşamalar AYNI ANDA çalışır; biten aşamanın sayfaları hemen Qwen'e okutulur; ilk geçerli cevap kazanır.
        running: dict = {asyncio.create_task(asyncio.wait_for(st(), timeout=75)): ("stage", st) for st in stages}
        result_events = None
        try:
            while running and result_events is None:
                done, _ = await asyncio.wait(running.keys(), return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    kind, ref = running.pop(task)
                    try:
                        res = task.result()
                    except Exception:  # noqa: BLE001 - süre aşımı / hata: o aşama sonuçsuz
                        continue
                    if kind == "stage":
                        pages, how = res
                        if ref is stage_atlas and atlas_hit.get("files") and not pages:
                            files = atlas_hit["files"]  # hedef bir belge (PDF/Excel): doğrudan ver
                            recipes.save(store)
                            result_events = [
                                {"meta": {"mode": "live", "path": [how], "found": True,
                                          "sources": [{"id": f"D{i + 1}", "url": e["u"], "page": e["t"] or "belge"} for i, e in enumerate(files)]}},
                                {"delta": "İstediğin belge" + ("ler" if len(files) > 1 else "") + ":\n" +
                                          "\n".join(f"- **{e['t'] or urlparse(e['u']).path.rsplit('/', 1)[-1]}** "
                                                    f"({urlparse(e['u']).path.rsplit('.', 1)[-1].upper()}) [D{i + 1}]" for i, e in enumerate(files))}]
                            break
                        if pages:
                            tried.append(how)
                            if ref is stage_atlas and atlas_hit.get("pages"):
                                best_page.append({"u": pages[0]["url"], "t": pages[0]["title"]})
                            await log(f"{how}: Qwen {len(pages)} sayfayı okuyup karar veriyor…")
                            jt = asyncio.create_task(understand.judge(question, pages, llm, terms=(terms + ([person] if person else []))))
                            running[jt] = ("judge", how)
                    else:
                        if res:
                            result_events = await finish(res, ref)
                            break
                        await log(f"{ref}: okunan sayfalarda cevap yok.")
        finally:
            for t in running:
                t.cancel()
        if result_events:
            for ev in result_events:
                yield ev
            return
        # Hiçbiri bulamadı → son çare canlı tarama
        try:
            pages, how = await asyncio.wait_for(stage_crawl(), timeout=150)
        except Exception:  # noqa: BLE001
            pages, how = [], ""
        if pages:
            tried.append(how)
            verdict = await understand.judge(question, pages, llm, terms=(terms + ([person] if person else [])))
            if verdict:
                for ev in await finish(verdict, how):
                    yield ev
                return
    else:
        # Model yoksa: sıralı, kelime eşleştirmeli yedek
        for stage in stages:
            try:
                pages, how = await asyncio.wait_for(stage(), timeout=150 if stage is stage_crawl else 75)
            except Exception:  # noqa: BLE001
                continue
            if not pages:
                continue
            tried.append(how)
            q_tokens = [t for t in content_tokens(person or query) if len(t) > 2]
            chunks = []
            for pg in pages:
                chunks += [{"id": "", "url": pg["url"], "page": pg["title"], "text": pg["text"][i:i + 900]}
                           for i in range(0, len(pg["text"]), 900)]
            hits = [c for _, c in _rank(question, chunks) if _relevant(c["text"], q_tokens, person)][:3]
            if hits:
                draft = await _draft(llm, question, hits, history)
                yield {"meta": {"mode": "live", "path": [how], "found": True,
                                "sources": [{"id": c["id"], "url": c["url"], "page": c["page"]} for c in hits]}}
                yield {"delta": draft}
                return

    recipes.save(store)
    srcs = [{"id": "S1", "url": best_page[0]["u"], "page": best_page[0]["t"] or "sayfa"}] if best_page else []
    yield {"meta": {"mode": "live", "path": tried, "sources": srcs, "found": False}}
    what = f"**{person}**" if person else "Bu bilgi"
    yield {"delta": f"{what} sitede bulunamadı ({', '.join(tried) or 'açık sayfa'} denendi)."
                    + (f" En ilgili sayfa: **{best_page[0]['t']}** [S1]." if best_page else "")}


# ===================================================== birleşik sorular (ayrıştır → her parçayı cevapla)
UNIT_PATTERNS = {
    "fakülte": r"fak[uü]ltes[iı]$|^faculty of|faculty$",
    "enstitü": r"enstit[uü]s[uü]$|institute",
    "yüksekokul": r"y[uü]ksekokulu$|meslek y[uü]ksekokulu|school of|vocational school",
    "bölüm": r"b[oö]l[uü]m[uü]$|department of|m[uü]hendisli[gğ]i$",
}
ROLE_PATTERNS = {
    "dekan": (r"\bdekan(?!\s*yard)|\bdean\b(?!.*assoc)", r"dekan|y[oö]netim|dean|administration|yönetim kurulu"),
    "müdür": (r"\bm[uü]d[uü]r(?!\s*yard)|\bdirector\b", r"m[uü]d[uü]r|y[oö]netim|director|administration"),
    "bölüm başkanı": (r"b[oö]l[uü]m ba[sş]kan(?!\s*yard)|\bhead of department|\bchair\b", r"ba[sş]kan|y[oö]netim|head|chair"),
}
DECOMPOSE_SCHEMA = {"type": "object", "properties": {"parts": {"type": "array", "items": {"type": "object", "properties": {
    "question": {"type": "string"}, "kind": {"type": "string", "enum": ["single", "count", "list_each"]},
    "unit": {"type": "string"}, "role": {"type": "string"}}, "required": ["question", "kind"]}}}, "required": ["parts"]}


def _unit_key(text: str) -> str:
    f = fold(text)
    for key in UNIT_PATTERNS:
        if fold(key)[:5] in f:
            return key
    return ""


def _role_key(text: str) -> str:
    f = fold(text)
    for key in ROLE_PATTERNS:
        if fold(key).split()[0][:5] in f:
            return key
    return ""


async def decompose(question: str, llm) -> list[dict]:
    """Mesajı alt sorulara ayırır: single (tek bilgi), count (kaç X), list_each (her X için Y)."""
    parts = []
    if llm.available:
        data = await llm.json(
            "Kullanıcının mesajını bağımsız alt sorulara ayır. Her parça için kind: 'single' (tek bir bilgi, örn. "
            "'rektör kim'), 'count' (bir birimin sayısı, örn. 'kaç fakülte var' → unit='fakülte'), 'list_each' "
            "(her birim için bir görevli, örn. 'fakültelerin dekanları' → unit='fakülte', role='dekan'). "
            "Birimler: fakülte, enstitü, yüksekokul, bölüm. Görevler: dekan, müdür, bölüm başkanı.\n"
            f"MESAJ: {question}", DECOMPOSE_SCHEMA, timeout=45, fast=True)
        parts = [p for p in (data or {}).get("parts", []) if clean(p.get("question"))]
    if not parts:  # LLM yoksa: basit bölme
        for piece in re.split(r"\?|;|\baynı zamanda\b|\bayrıca\b|(?<=\bvar)\s+(?=\S)|(?<=\bvarmı)\s+(?=\S)|"
                              r"(?<=\bvar mı)\s+(?=\S)", question):
            if len(clean(piece)) > 4:
                parts.append({"question": clean(piece), "kind": "single"})
    for p in parts:  # kural ile düzelt/tamamla
        q = fold(p["question"])
        p["unit"] = _unit_key(p.get("unit") or p["question"])
        p["role"] = _role_key(p.get("role") or p["question"])
        if p["unit"] and re.search(r"\bkac\b|sayisi|how many", q):
            p["kind"] = "count"
        elif p["unit"] and p["role"]:
            p["kind"] = "list_each"
        elif p.get("kind") in ("count", "list_each") and not p["unit"]:
            p["kind"] = "single"
    return parts[:5] or [{"question": question, "kind": "single", "unit": "", "role": ""}]


async def enumerate_units(url: str, html: str, unit: str, log, llm=None) -> list[dict]:
    """Kurumun birimleri (fakülteler vb.): Qwen 'Fakülteler/Akademik Birimler' sayfasını ve ana sayfayı okuyup
    birimleri çıkarır (sayfa metninde doğrulanır). Model yoksa ya da sonuç çıkmazsa kural tabanlı yedek."""
    from . import atlas as atlas_mod
    from . import understand

    at = await atlas_mod.build(url, html, log)
    rx = re.compile(UNIT_PATTERNS[unit], re.I)

    def by_rules(entries):
        out = {}
        for e in entries:
            name = clean(e["t"] or "")
            if 6 <= len(name) <= 80 and len(name.split()) >= 2 and rx.search(name) and not atlas_mod.FILE_EXT.search(e["u"]) \
                    and not atlas_mod.NEWS_RE.search(fold(e["u"])) and not re.search(r"(?i)sayfas|ler$|lar$", name):
                out.setdefault(fold(name), {"name": name, "url": e["u"], "src": e.get("src", "")})
        return list(out.values())

    menu = [e for e in at["entries"] if e.get("src", "").startswith(atlas_mod.MENU_SOURCES)]
    if llm is not None and llm.available:
        # Qwen yönlendirmeli iniş: sayfayı oku → birim yoksa "hangi link birim listesine götürür?" → in (≤3 seviye)
        home = f"{urlparse(url).scheme}://{urlparse(url).netloc}/"
        frontier = list(dict.fromkeys([e["u"] for e in menu if atlas_mod.DIRECTORY_RE.search(fold(e["t"] or ""))][:2] + [home]))
        seen: set[str] = set()
        units: dict[str, dict] = {}
        for depth in range(3):
            next_pages: list[str] = []
            pages = [u for u in frontier if u not in seen][:3]
            seen.update(pages)
            fetched = await asyncio.gather(*(fetch_smart(u) for u in pages), return_exceptions=True)
            for page in fetched:
                if isinstance(page, Exception) or page.status >= 400:
                    continue
                view = await understand.read_page(page.selector, page.url, llm, mode="units")
                for u in view["units"]:
                    if fold(u["kind"])[:5] == fold(unit)[:5]:
                        units.setdefault(fold(u["name"]), {"name": u["name"], "url": u["url"], "src": "qwen"})
                if len(units) >= 3:
                    continue
                pick = await understand.pick_links(page.selector, page.url, llm,
                                                   f"Üniversitenin tüm {unit} listesinin (ör. 'X {unit.capitalize()}si' "
                                                   "bağlantılarının) bulunduğu sayfa")
                if pick:
                    await log(f"Qwen: {unit} listesi için '{pick[0][1]}' bölümüne iniliyor…")
                next_pages += [u for u, _ in pick]
            if len(units) >= 3 or not next_pages:
                break
            frontier = next_pages
        if units:
            return list(units.values())[:40]
        await log("Qwen birim listesi çıkaramadı → kural tabanlı yedek.")
    units = by_rules(menu)
    if len(units) < 2:
        for d in [e for e in at["entries"] if atlas_mod.DIRECTORY_RE.search(fold(e["t"] or ""))][:2]:
            units = by_rules(await atlas_mod.expand_hub(at, d["u"], log, kind="dizin")) or units
            if len(units) >= 2:
                break
    return units[:30]


def _role_name_in(text: str, role_rx) -> tuple[str, str] | None:
    """'Ad | Dekan', 'Dekan | Ad' ve 'Dekan: Ad' biçimlerinde görevlinin adı (yardımcıları hariç)."""
    from .page import TITLED, _clean_name

    segs = [x.strip() for x in text.split("|") if x.strip()]
    for i, seg in enumerate(segs):
        if not role_rx.search(seg) or re.search(r"(?i)yard[ıi]mc|assistant|associate|vice", seg) or len(seg) > 80:
            continue
        for j in (i, i - 1, i + 1, i - 2, i + 2):  # önce aynı öğe ("Dekan: Prof. Dr. X"), sonra komşular
            if 0 <= j < len(segs):
                cand = segs[j] if j != i - 2 else f"{segs[j]} {segs[j + 1]}"
                m = TITLED.search(cand)
                if m and _clean_name(m.group(2)):
                    return f"{clean(m.group(1))} {_clean_name(m.group(2))}", segs[j]
    return None


async def find_role(unit: dict, role: str, at: dict, llm, log) -> dict:
    """Bir birimin (fakülte…) sitesinde görevlinin (dekan…) adını bulur.

    Birimin kendi adres yolu altındaki yönetim ve kadro sayfaları paralel okunur; ad sayfadaki
    'Ad | Dekan' komşuluğundan çıkarılır. Kural sonuç vermezse birim başına bir kez Qwen'e sorulur
    ve verdiği ad sayfa metninde doğrulanır."""
    from . import atlas as atlas_mod

    role_rx, page_rx = (re.compile(x, re.I) for x in ROLE_PATTERNS[role])
    entries = await atlas_mod.expand_hub(at, unit["url"], log)
    base = urlparse(unit["url"])
    prefix = base.path.rstrip("/")

    def inside(u: str) -> bool:  # birimin kendi alt sitesi / adres yolu
        pu = urlparse(u)
        return pu.netloc == base.netloc and (not prefix or pu.path.startswith(prefix)) or \
            (pu.netloc != base.netloc and pu.netloc.endswith(at["root"]) and prefix in ("", "/"))

    ranked = []
    for e in entries:
        if atlas_mod.FILE_EXT.search(e["u"]) or not inside(e["u"]):
            continue
        blob = fold(f"{e['t']} {e['u']}")
        if page_rx.search(blob):
            ranked.append((0, e["u"]))
        elif e["cat"] == "kadro" or re.search(r"kadro|staff|people|personel", blob):
            ranked.append((1, e["u"]))
    pages = [u for _, u in sorted(ranked)] + [unit["url"]]  # yönetim/kadro sayfaları önce
    pages = list(dict.fromkeys(pages))[:4]
    results = await asyncio.gather(*(fetch_smart(u) for u in pages), return_exceptions=True)
    fetched = [(u, p) for u, p in zip(pages, results) if not isinstance(p, Exception) and p.status < 400]
    # 1) Qwen sayfayı okur: görevleriyle kişiler (biçimden bağımsız)
    if llm.available:
        from . import understand

        for u, page in fetched:
            text = clean(page.selector.get_all_text(separator=" ", ignore_tags=("script", "style", "noscript")))
            if not role_rx.search(text):
                continue  # görev kelimesi hiç geçmeyen sayfayı modele okutma
            view = await understand.read_page(page.selector, page.url, llm, mode="people",
                                              role_rx=ROLE_PATTERNS[role][0], focus=f"{unit['name']} — {role}")
            for person in view["people"]:
                r = person["role"]
                if role_rx.search(r) and not re.search(r"(?i)yard[ıi]mc|assistant|associate|vice", r):
                    name = f"{person['title']} {person['name']}".strip() if person["title"] and person["title"] not in person["name"] else person["name"]
                    return {"unit": unit["name"], "role": role, "name": name, "url": page.url, "by": "qwen"}
    # 2) Yedek: kural ('Ad | Dekan' komşuluğu)
    for u, page in fetched:
        text = clean(page.selector.get_all_text(separator=" | ", ignore_tags=("script", "style", "noscript")))
        hit = _role_name_in(text, role_rx)
        if hit:
            return {"unit": unit["name"], "role": role, "name": hit[0], "url": page.url, "by": "kural"}
    return {"unit": unit["name"], "role": role, "name": "", "url": unit["url"]}


_ANSWER_CACHE: dict[tuple[str, str], tuple[float, list]] = {}
ANSWER_TTL = 600  # sn


async def answer(url: str, html: str, question: str, history: list[dict], llm, log):
    """Önbellek sarmalayıcı: aynı sitede aynı soru 10 dk içinde tekrar sorulursa cevap anında döner."""
    key = (registrable(urlparse(url).hostname or ""), " ".join(fold(question).split()))
    hit = _ANSWER_CACHE.get(key)
    if hit and time.time() - hit[0] < ANSWER_TTL:
        await log("Bu soru az önce cevaplanmıştı → önbellekten.")
        for ev in hit[1]:
            yield ev
        return
    events = []
    async for ev in _answer(url, html, question, history, llm, log):
        events.append(ev)
        yield ev
    if any(e.get("meta", {}).get("found") for e in events):
        _ANSWER_CACHE[key] = (time.time(), events)


async def _answer(url: str, html: str, question: str, history: list[dict], llm, log):
    """Birleşik mesajları alt sorulara ayırır; her parçayı uygun yöntemle cevaplar ve tek cevapta birleştirir."""
    from . import atlas as atlas_mod

    parts = await decompose(question, llm)
    if len(parts) == 1 and parts[0]["kind"] == "single":
        async for ev in answer_single(url, html, question, history, llm, log):
            yield ev
        return
    await log("Mesaj " + str(len(parts)) + " alt soruya ayrıldı: " + " · ".join(p["question"][:40] for p in parts))
    sections, sources, paths = [], [], []

    def cite(u: str, page: str) -> str:
        for s_ in sources:
            if s_["url"] == u:
                return s_["id"]
        sid = f"S{len(sources) + 1}"
        sources.append({"id": sid, "url": u, "page": page[:80]})
        return sid

    for i, p in enumerate(parts, 1):
        head = f"**{i}) {p['question'].rstrip('?')}?**"
        if p["kind"] in ("count", "list_each"):
            await log(f"[{i}] {p['unit'].capitalize()} listesi anlam haritasından çıkarılıyor…")
            units = await enumerate_units(url, html, p["unit"], log, llm)
            paths.append(f"anlam haritası → {p['unit']} listesi")
            if not units:
                sections.append(f"{head}\n{p['unit'].capitalize()} listesi sitede bulunamadı.")
                continue
            if p["kind"] == "count":
                lines = ", ".join(f"{u['name']} [{cite(u['url'], u['name'])}]" for u in units)
                sections.append(f"{head}\nSitede **{len(units)} {p['unit']}** görünüyor: {lines}")
                continue
            at = await atlas_mod.build(url, html, log)
            await log(f"[{i}] {len(units)} {p['unit']} sitesinde {p['role']} aranıyor (Scrapling, paralel)…")
            sem = asyncio.Semaphore(6)

            async def one(u):
                async with sem:
                    return await find_role(u, p["role"], at, llm, log)

            found = await asyncio.gather(*(one(u) for u in units[:12]))
            lines = []
            for n, r in enumerate(found, 1):
                if r["name"]:
                    lines.append(f"{n}. {r['unit']} — {p['role'].capitalize()}: **{r['name']}** [{cite(r['url'], r['unit'])}]")
                else:
                    lines.append(f"{n}. {r['unit']} — {p['role']} adı sitede bulunamadı [{cite(r['url'], r['unit'])}]")
            sections.append(head + "\n" + "\n".join(lines))
            continue
        # tek bilgi: mevcut zincir
        text, meta = "", {}
        async for ev in answer_single(url, html, p["question"], history, llm, log):
            if "meta" in ev:
                meta = ev["meta"]
            text += ev.get("delta", "")
        mapping = {s_["id"]: cite(s_["url"], s_["page"]) for s_ in meta.get("sources", [])}
        text = re.sub(r"\[([SD]\d+)\]", lambda m: f"[{mapping.get(m.group(1), m.group(1))}]", text)
        paths += meta.get("path", [])
        sections.append(f"{head}\n{text.strip()}")
    yield {"meta": {"mode": "live", "path": list(dict.fromkeys(paths)), "found": True, "sources": sources}}
    yield {"delta": "\n\n".join(sections)}


async def locate_target(url: str, html: str, query: str, llm, log) -> dict | None:
    """'Bul: X' — soru-cevap ile AYNI zincir (Qwen yorumu → açık sayfa → anlam haritası → arama → harita →
    canlı tarama; Qwen sayfayı okuyup karar verir). Bulunan sayfa ve kısa cevap döner; panel oraya götürür."""
    question = query if re.search(r"\?|\b(kim|nerede|nedir|hangi)\b", query, re.I) else f"{query} kim / nerede?"
    meta, text, person = {}, "", ""
    async for ev in answer_single(url, html, question, [], llm, log):
        if "meta" in ev:
            meta = ev["meta"]
        if "person" in ev:
            person = ev["person"]
        text += ev.get("delta", "")
    if not meta.get("found") or not meta.get("sources"):
        return None
    src = meta["sources"][0]
    return {"url": src["url"], "title": src["page"], "answer": re.sub(r"\s*\[[SD]\d+\]", "", text).strip(),
            "person": person, "path": meta.get("path", []), "here": src["url"].split("#")[0] == url.split("#")[0]}
