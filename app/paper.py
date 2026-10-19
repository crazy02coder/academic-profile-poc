"""Yayın ayrıntısı: yayıncı sayfasını Scrapling ile getir, künyeyi çıkar, Qwen ile Türkçe özetle.

Kullanıcı yayına tıkladığında siteye yönlendirmek yerine:
  1. DOI/URL Scrapling ile açılır (Elsevier, IEEE, Springer gibi bot korumalı yayıncılarda
     statik erişim duvara takılırsa StealthyFetcher devreye girer).
  2. Akademik meta etiketleri (citation_*, dc.*, og:*, JSON-LD) okunur: başlık, yazarlar,
     dergi, tarih, özet, anahtar kelimeler, PDF bağlantısı.
  3. Özet bulunamazsa OpenAlex'ten gelen özet kullanılır.
  4. Qwen kısa bir Türkçe özet yazar (amaç, yöntem, bulgu); LLM yoksa ilk cümleler gösterilir.
"""
from __future__ import annotations

import json
import re
from typing import AsyncIterator

from .net import fetch_smart, wall_reason
from .text import clean


def _meta(sel, *names: str) -> list[str]:
    out = []
    for n in names:
        for attr in ("name", "property"):
            for v in sel.css(f'meta[{attr}="{n}"]::attr(content)').getall():
                v = clean(v)
                if v and v not in out:
                    out.append(v)
    return out


def _jsonld(sel) -> dict:
    for raw in sel.css('script[type="application/ld+json"]::text').getall():
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        items = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
        for it in items:
            if isinstance(it, dict) and (it.get("abstract") or it.get("description")) and it.get("@type") in (
                    "ScholarlyArticle", "Article", "CreativeWork", "Chapter", "Book", "Report", None):
                return it
    return {}


def _unwrap(target: str) -> str:
    """Sarmalayıcı yönlendirme adreslerinin içindeki asıl hedef (?Redirect=, ?url=, ?returnUrl= …)."""
    from urllib.parse import unquote

    for _ in range(2):
        m = re.search(r"[?&](?:redirect|redirecturl|url|target|returnurl|dest|destination)=(https?(?:%3A|:)[^&]+)", target, re.I)
        if not m:
            break
        target = unquote(m.group(1))
    return target


def _unwrap(target: str) -> str:
    """Sarmalayıcı yönlendirme adreslerinin içindeki asıl hedef (?Redirect=, ?url=, ?returnUrl= …)."""
    from urllib.parse import unquote

    for _ in range(2):
        m = re.search(r"[?&](?:redirect|redirecturl|url|target|returnurl|dest|destination)=(https?(?:%3A|:)[^&]+)", target, re.I)
        if not m:
            break
        target = unquote(m.group(1))
    return target


def soft_redirect(sel, url: str) -> str | None:
    """Ara yönlendirme sayfaları (meta refresh, gizli redirectURL alanı, JS location) için hedef adres."""
    from urllib.parse import unquote, urljoin

    target = None
    for refresh in sel.css("meta[http-equiv]"):
        if (refresh.attrib.get("http-equiv") or "").lower() == "refresh":
            content = refresh.attrib.get("content") or ""
            if "url=" in content.lower():
                target = urljoin(url, re.split(r"(?i)url=", content, 1)[1].strip(" '\""))
                break
    if target is None:
        hidden = sel.css('input[name="redirectURL"]::attr(value)').get() or sel.css('input[id="redirectURL"]::attr(value)').get()
        if hidden:
            target = urljoin(url, unquote(hidden))
    if target is None:
        html = sel.html_content if hasattr(sel, "html_content") else ""
        m = re.search(r"(?:window\.)?location(?:\.href)?\s*=\s*['\"]([^'\"]+)['\"]", html)
        if m and len(sel.get_all_text()) < 2000:
            target = urljoin(url, m.group(1))
    return _unwrap(target.replace("&amp;", "&")) if target else None


def extract(sel, url: str) -> dict:
    ld = _jsonld(sel)
    abstract = (_meta(sel, "citation_abstract", "dc.description", "DC.Description", "dcterms.abstract")
                or [clean(ld.get("abstract") or "")])
    if not abstract or not abstract[0]:
        # Yayıncı sayfasındaki özet bölümü (yaygın kalıplar)
        for css in ("#abstract", ".abstract", "section.abstract", "div.abstract-text", "[class*=abstract]",
                    "#Abs1-content", ".c-article-section__content", "div.html-abstract"):
            els = sel.css(css)
            if els:
                text = clean(els[0].get_all_text(separator=" "))
                if len(text) > 120:
                    abstract = [re.sub(r"^(Abstract|Özet)\s*[:.]?\s*", "", text, flags=re.I)]
                    break
    if not abstract or not abstract[0]:
        abstract = _meta(sel, "og:description", "description", "twitter:description")
    return {
        "title": (_meta(sel, "citation_title", "dc.title", "og:title") or [clean(sel.css("title::text").get() or "")])[0],
        "authors": _meta(sel, "citation_author", "dc.creator")[:30],
        "journal": (_meta(sel, "citation_journal_title", "citation_conference_title", "citation_publisher",
                          "dc.publisher", "og:site_name") or [""])[0],
        "date": (_meta(sel, "citation_publication_date", "citation_date", "dc.date") or [""])[0],
        "keywords": [k for v in _meta(sel, "citation_keywords", "keywords") for k in re.split(r"[;,]", v) if clean(k)][:15],
        "pdf": (_meta(sel, "citation_pdf_url") or [""])[0],
        "abstract": (abstract[0] if abstract else "")[:4000],
        "final_url": url,
    }


# ------------------------------------------------------------------ dış özet kaynakları
async def _semantic_scholar(doi: str) -> dict:
    import httpx

    fields = "title,abstract,tldr,citationCount,influentialCitationCount,fieldsOfStudy,venue,year,openAccessPdf"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}", params={"fields": fields})
        if r.status_code != 200:
            return {}
        d = r.json()
    return {"abstract": clean(d.get("abstract") or ""), "tldr": clean((d.get("tldr") or {}).get("text") or ""),
            "citations": d.get("citationCount"), "influential": d.get("influentialCitationCount"),
            "fields": d.get("fieldsOfStudy") or [], "pdf": ((d.get("openAccessPdf") or {}).get("url") or "")}


async def _crossref_abstract(doi: str) -> str:
    import httpx

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"https://api.crossref.org/works/{doi}")
        if r.status_code != 200:
            return ""
        return clean(re.sub(r"<[^>]+>", " ", r.json().get("message", {}).get("abstract") or ""))


def _abstract_from_json(obj, depth: int = 0) -> str:
    """REA'nın yakaladığı JSON yanıtlarında 'abstract'/'description' anahtarlı en uzun metin."""
    best = ""
    if depth > 8:
        return best
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and re.search(r"abstract|description|summary", str(k), re.I) and len(v) > len(best):
                best = v
            else:
                cand = _abstract_from_json(v, depth + 1)
                if len(cand) > len(best):
                    best = cand
    elif isinstance(obj, list):
        for v in obj[:200]:
            cand = _abstract_from_json(v, depth + 1)
            if len(cand) > len(best):
                best = cand
    return clean(re.sub(r"<[^>]+>", " ", best))


# --------------------------------------------------------------------- yayıncı erişimi
def _apply_rewrites(url: str, store: dict) -> str:
    from urllib.parse import urlparse, urlunparse

    u = urlparse(url)
    for rule in store.get("rewrites", []):
        if u.path.startswith(rule["from"]):
            return urlunparse(u._replace(path=rule["to"] + u.path[len(rule["from"]):], query=""))
    return url


def _learn_rewrite(requested: str, final: str, store: dict, slow: bool, emit):
    """Yavaş/duvarlı erişim sonunda site bizi aynı kimlikli başka bir yola götürdüyse
    (örn. /article/pii/X → /article/abs/pii/X) bu dönüşüm yayıncı tarifine yazılır."""
    from urllib.parse import urlparse

    from . import recipes

    a, b = urlparse(requested), urlparse(final)
    if not slow or a.netloc != b.netloc or a.path == b.path:
        return
    last = a.path.rstrip("/").rsplit("/", 1)[-1]
    if not last or not b.path.rstrip("/").endswith(last):
        return
    src, dst = a.path[: -len(last)], b.path.rstrip("/")[: -len(last)]
    if src == dst or any(r["from"] == src for r in store.get("rewrites", [])):
        return
    store.setdefault("rewrites", []).append({"from": src, "to": dst, "learned_at": recipes._now()})
    emit({"stage": f"Öğrenildi: {a.netloc}{src}… → {dst}… (bu yayıncının sonraki makaleleri hızlı yoldan açılacak)."})



async def _publisher(url: str, emit) -> dict:
    """Scrapling merdiveni (hafızadaki seviyeden başlar) + gerekirse Scrapling-stealth/REA köprüsü."""
    import asyncio
    from urllib.parse import urlparse

    from . import rea, recipes
    from .discover import registrable
    from .net import fetch_stealth, parse

    out: dict = {}

    async def note(msg):
        emit({"stage": msg})

    page = await fetch_smart(url, log=note, allow_cloudflare=True)
    for _ in range(2):  # yayıncı ara sayfaları (ör. linkinghub → sciencedirect)
        nxt = soft_redirect(page.selector, page.url)
        if not nxt or nxt.rstrip("/") == page.url.rstrip("/"):
            break
        emit({"stage": f"Ara yönlendirme sayfası → {nxt[:90]}"})
        host = registrable(urlparse(nxt).hostname or "")
        store = recipes.load(host)
        rewritten = _apply_rewrites(nxt, store)
        if rewritten != nxt:
            emit({"stage": f"Öğrenilmiş yol dönüşümü uygulandı → {rewritten[:90]} (yavaş Cloudflare yolu atlanıyor)."})
            nxt = rewritten
        started = asyncio.get_running_loop().time()
        page = await fetch_smart(nxt, log=note, allow_cloudflare=True)
        slow = asyncio.get_running_loop().time() - started > 20
        _learn_rewrite(nxt, page.url, store, slow, emit)
    host = registrable(urlparse(page.url).hostname or "")
    store = recipes.load(host)
    wall = wall_reason(page.status, page.html)
    if wall:
        emit({"stage": f"Yayıncı sayfası tüm Scrapling seviyelerinden sonra da kapalı ({wall})."})
        return out
    store["access"] = {"tier": page.via, "at": recipes._now()}
    out.update(extract(page.selector, page.url))
    out["via"] = page.via
    emit({"stage": f"Sayfa alındı [{page.via}] → {page.url[:90]}"})

    if len(out.get("abstract") or "") < 200 and rea.available():
        emit({"stage": "Özet ilk HTML'de yok → Scrapling stealth sayfayı açıyor, REA aynı oturuma CDP ile bağlanıp "
                       "render sonrası DOM'u ve JSON isteklerini kaydediyor…"})
        loop = asyncio.get_running_loop()

        def bridge_job():
            from .rea import StealthBridge

            with StealthBridge() as b:
                b.fetch(page.url)
                return b.observe(page.url, [
                    {"step_id": "settle", "action": "wait_for_timeout", "duration_ms": 4000},
                    {"step_id": "scroll", "action": "press", "locator": {"kind": "css", "selector": "body"},
                     "key": "End", "timeout_ms": 3000},
                    {"step_id": "lazy", "action": "wait_for_timeout", "duration_ms": 2000}])

        try:
            cap = await asyncio.wait_for(loop.run_in_executor(None, bridge_job), timeout=90)
        except Exception as exc:  # noqa: BLE001
            cap = None
            emit({"stage": f"REA köprüsü tamamlanamadı ({type(exc).__name__})."})
        if cap is not None and cap.ok:
            internal = sorted({urlparse(t.url).path.rsplit("/", 1)[0] for t in cap.json_endpoints
                               if registrable(urlparse(t.url).hostname or "") == host})[:6]
            emit({"stage": f"REA Evidence {cap.evidence_id[:14]}…: {len(cap.transactions)} istek, "
                           f"{len(cap.json_endpoints)} JSON yanıtı" + (f"; iç API'ler: {', '.join(internal)}" if internal else "")})
            dom_abs = extract(parse(cap.dom, page.url), page.url).get("abstract", "") if cap.dom else ""
            xhr_abs, xhr_src = "", ""
            for tx in cap.json_endpoints:
                cand = _abstract_from_json(tx.json())
                if len(cand) > len(xhr_abs):
                    xhr_abs, xhr_src = cand, tx.url
            if len(xhr_abs) > max(200, len(dom_abs)):
                out["abstract"], out["rea"] = xhr_abs, True
                store["abstract_source"] = {"kind": "xhr", "url_pattern": re.sub(r"[A-Z0-9]{10,}", "{id}", xhr_src), "at": recipes._now()}
                emit({"stage": f"REA özeti gizli JSON isteğinde buldu → {xhr_src[:90]} (tarif kaydedildi)."})
            elif len(dom_abs) > 200:
                out["abstract"], out["rea"] = dom_abs, True
                store["abstract_source"] = {"kind": "rendered-dom", "at": recipes._now()}
                emit({"stage": "REA: özet JavaScript render sonrası DOM'da bulundu (tarif kaydedildi)."})
            else:
                emit({"stage": "REA: render sonrası DOM'da ve JSON isteklerinde de özet yok → yayıncı bu makale için özet sunmuyor."})
        elif cap is not None:
            emit({"stage": f"REA gözlemi başarısız: {cap.error[:100]}"})
    recipes.save(store)
    return out


async def detail(paper: dict, llm, cache: dict) -> AsyncIterator[dict]:
    import asyncio

    key = paper["id"]
    if key in cache:
        yield {"stage": "Önbellekten getirildi."}
        yield {"meta": cache[key]["meta"]}
        yield {"delta": cache[key]["summary"]}
        return
    url = paper.get("url") or (f"https://doi.org/{paper['doi']}" if paper.get("doi") else "")
    doi = paper.get("doi") or ""
    meta = {"title": paper["title"], "authors": paper.get("authors", []), "journal": paper.get("venue", ""),
            "date": str(paper.get("year") or ""), "keywords": [], "pdf": "", "abstract": paper.get("abstract", ""),
            "final_url": url, "via": "", "source_note": "özet OpenAlex'ten" if paper.get("abstract") else "",
            "tldr": "", "fields": [], "s2_citations": None}

    queue: asyncio.Queue = asyncio.Queue()
    emit = queue.put_nowait
    results: dict = {}

    async def run(name, coro):
        try:
            results[name] = await coro
        except Exception as exc:  # noqa: BLE001
            results[name] = None
            emit({"stage": f"{name}: erişilemedi ({type(exc).__name__})"})

    tasks = []
    if url and not url.startswith("https://openalex.org"):
        emit({"stage": f"Scrapling ile yayıncı sayfası getiriliyor: {url}"})
        tasks.append(asyncio.create_task(run("Yayıncı", _publisher(url, emit))))
    if doi:
        emit({"stage": "Paralel: Semantic Scholar (özet + TL;DR + atıf) ve Crossref sorgulanıyor."})
        tasks.append(asyncio.create_task(run("Semantic Scholar", _semantic_scholar(doi))))
        tasks.append(asyncio.create_task(run("Crossref", _crossref_abstract(doi))))
    pending = set(tasks)
    while pending:
        getter = asyncio.create_task(queue.get())
        done, _ = await asyncio.wait(pending | {getter}, return_when=asyncio.FIRST_COMPLETED)
        if getter in done:
            yield getter.result()
        else:
            getter.cancel()
        pending -= done
    while not queue.empty():
        yield queue.get_nowait()

    pub = results.get("Yayıncı") or {}
    s2 = results.get("Semantic Scholar") or {}
    cr = results.get("Crossref") or ""
    for k in ("title", "journal", "date", "pdf", "final_url", "via"):
        if pub.get(k):
            meta[k] = pub[k]
    if pub.get("authors"):
        meta["authors"] = pub["authors"]
    if pub.get("keywords"):
        meta["keywords"] = pub["keywords"]
    candidates = [(pub.get("abstract") or "", "özet yayıncı sayfasından (Scrapling" + (" + REA)" if pub.get("rea") else ")")),
                  (s2.get("abstract") or "", "özet Semantic Scholar'dan"), (cr, "özet Crossref'ten"),
                  (meta["abstract"] or "", meta["source_note"] or "özet OpenAlex'ten")]
    best = max(candidates, key=lambda c: len(c[0]))
    meta["abstract"], meta["source_note"] = (best if best[0] else ("", "özet hiçbir kaynakta yok"))
    meta["tldr"] = s2.get("tldr", "")
    meta["fields"] = s2.get("fields", [])
    meta["s2_citations"] = s2.get("citations")
    if not meta["pdf"] and s2.get("pdf"):
        meta["pdf"] = s2["pdf"]
    yield {"meta": meta}

    summary = ""
    basis = meta["abstract"] or meta["tldr"]
    if llm.available:
        yield {"stage": f"{llm.model} Türkçe özet yazıyor…"}
        messages = [
            {"role": "system", "content": "Akademik bir yayını Türkçe özetleyen asistansın. Yalnızca verilen bilgilere "
                                          "dayan; uydurma. Özet varsa üç kısa madde yaz: **Amaç**, **Yöntem**, "
                                          "**Bulgu/Katkı**. Özet yoksa başlık ve künyeden çalışmanın konusunu tek "
                                          "paragrafta anlat ve özetin bulunamadığını belirt."},
            {"role": "user", "content": f"BAŞLIK: {meta['title']}\nDERGİ: {meta['journal']} ({meta['date']})\n"
                                        f"ANAHTAR KELİMELER: {', '.join(meta['keywords'] or meta['fields'])}\n"
                                        f"TL;DR: {meta['tldr'] or '-'}\nÖZET: {basis[:3500] or '(yok)'}"},
        ]
        try:
            async for piece in llm.stream_chat(messages):
                summary += piece
                yield {"delta": piece}
        except Exception:  # noqa: BLE001
            summary = ""
    if not summary:
        sentences = re.split(r"(?<=[.!?])\s+", basis or "")
        summary = " ".join(sentences[:3]) if sentences and sentences[0] else "Özet bulunamadı; yalnızca künye bilgisi var."
        yield {"delta": summary}
    cache[key] = {"meta": meta, "summary": summary}
