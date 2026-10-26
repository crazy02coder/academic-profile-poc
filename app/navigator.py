"""LLM yönlendirmeli site gezgini (REA + Gemini + Scrapling).

Kullanıcı yalnızca üniversitenin ana adresini verir. Site yapısı üniversiteden
üniversiteye değiştiği için sabit kurallar yerine bir ajan döngüsü kullanılır:

  GÖZLEM  — Scrapling sayfayı okur; içerik JS ile geliyorsa REA render eder.
  KARAR   — Gemini'ye sayfa özeti (başlık, numaralı linkler, arama kutusu var mı,
            izlenen yol) verilir; hangi linklerin açılacağına veya site
            aramasının kullanılacağına karar verir (yapılandırılmış JSON).
  EYLEM   — Scrapling seçilen linkleri paralel açar; arama seçildiyse REA kutuya
            adı yazıp gönderir, gizli arama isteğini tarif olarak öğrenir.
  HAFIZA  — Kadro listesi olan sayfalar alan adı başına saklanır; aynı sitede bir
            sonraki kişi için önce bu sayfalar taranır (LLM'e gerek kalmaz).
"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import urldefrag, urlparse

from . import rea, recipes
from .net import fetch_smart, fetch_static, parse
from .text import clean, fold, name_in_text

MAX_STEPS = 9
BEAM = 3
TITLE_HITS = re.compile(r"Prof\.|Doç\.|Dr\.\s*Öğr|Öğr\.\s*Gör|Arş\.\s*Gör|Öğretim Üyesi|Professor|Lecturer|"
                        r"Assoc\.|Assist\.|Research Assistant", re.I)
SEARCH_INPUTS = ('input[type="search"]', 'input[name="q"]', 'input[name="s"]', 'input[name*="search" i]',
                 'input[name*="ara" i]', 'input[placeholder*="Ara" i]', 'input[placeholder*="Search" i]')

PAGE_TYPES = ["person_profile", "staff_list", "search_results", "news_or_event", "faculty_or_department", "other"]
PERCEIVE_SCHEMA = {
    "type": "object",
    "properties": {
        "page_type": {"type": "string", "enum": PAGE_TYPES},
        "is_target_person_page": {"type": "boolean"},
        "title": {"type": "string"},
        "department": {"type": "string"},
        "interests": {"type": "array", "items": {"type": "string"}},
        "next_links": {"type": "array", "items": {"type": "integer"}},
        "use_search": {"type": "boolean"},
        "reason": {"type": "string"},
    },
    "required": ["page_type", "is_target_person_page", "next_links", "use_search", "reason"],
}
PAGE_TYPE_TR = {"person_profile": "kişi profili", "staff_list": "kadro listesi", "search_results": "arama sonucu",
                "news_or_event": "haber/etkinlik", "faculty_or_department": "fakülte/bölüm", "other": "diğer"}


def page_view(sel, max_chars: int = 3200) -> str:
    """Scrapling'in temiz Markdown çıktısı; yalnızca link listesinden oluşan menü satırları atılır."""
    try:
        md = sel.markdown(main_content_only=True)
    except Exception:  # noqa: BLE001
        md = clean(sel.get_all_text(separator=" "))
    keep = []
    for line in md.splitlines():
        t = line.strip()
        if not t:
            continue
        # "* [Menü](url)" veya "[![](img)](url)" gibi saf gezinme satırları
        if re.fullmatch(r"[*+\-]?\s*\[[^\]]{0,60}\]\([^)]*\)(\s*\|\s*\[[^\]]{0,60}\]\([^)]*\))*", t) or t.startswith("[!["):
            continue
        t = re.sub(r"\]\([^)]*\)", "]", t)  # link adreslerini kısalt (linkler ayrıca numaralı veriliyor)
        keep.append(t)
    text = "\n".join(keep)
    return text[:max_chars]


def _registrable(host: str) -> str:
    from .discover import registrable

    return registrable(host)


NOISE_PAGE = re.compile(r"search results|arama sonuç|sonuçları|haber|news|duyuru|announcement|etkinlik|event|"
                        r"seminer|seminar|tez sunumu|dissertation|thesis defen|konferans|blog", re.I)


def is_person_hit(sel, text: str, name: str, url: str) -> bool:
    """Ad geçiyor diye her sayfa kişinin sayfası değildir (arama sonucu, haber, tez duyurusu…).
    Kabul: kadro listesi VEYA ad bir başlık/isim öğesinde geçiyor ve sayfa haber/arama değil."""
    title = clean(sel.css("title::text").get() or "")
    heads = " ".join(clean(h.get_all_text(separator=" ")) for h in sel.css("h1, h2")[:4])
    if re.search(r"[?&](s|q|search|ara|query|keyword)=", url) or NOISE_PAGE.search(f"{title} {heads}"):
        return False
    if is_staff_page(text):
        return True
    for h in sel.css("h1, h2, h3, h4, h5, strong, b, .name, [class*=name], [class*=title]")[:300]:
        t = clean(h.get_all_text(separator=" "))
        if len(t) < 120 and name_in_text(name, t):
            return True
    return name_in_text(name, title)


def is_staff_page(text: str) -> bool:
    """Birden çok akademik unvan geçen sayfa = kadro listesi."""
    return len(TITLE_HITS.findall(text)) >= 4


def _candidate_links(sel, base: str, root: str, seen: set[str]) -> list[tuple[str, str]]:
    from .discover import BAD_WORDS, SKIP_EXT, _links

    out, keys = [], set()
    for url, text in _links(sel, base):
        host = urlparse(url).hostname or ""
        key = urldefrag(url)[0].rstrip("/")
        if _registrable(host) != root or key in seen or key in keys or SKIP_EXT.search(url):
            continue
        if BAD_WORDS.search(fold(url + " " + text)):
            continue
        keys.add(key)
        out.append((url, text or urlparse(url).path))
    return out[:70]


PAGE_PARAM = re.compile(r"[?&](pn|page|p|sayfa|pg|start|offset|paged|currentpage)=(\d+)", re.I)
PAGE_PATH = re.compile(r"/(page|sayfa)/(\d+)/?$", re.I)


def pagination_links(sel, url: str) -> list[str]:
    """Aynı listenin diğer sayfaları: ?pn=2, ?page=3, /page/4, rel=next, numaralı sayfa linkleri.

    Yalnızca AYNI yol üzerinde, sadece sayfa parametresi farklı olan linkler alınır;
    böylece başka listelere sapılmaz. Görünen en büyük sayfa numarasına kadar eksikler doldurulur.
    """
    from urllib.parse import parse_qsl, urlencode, urljoin, urlunparse

    base = urlparse(url)
    found: dict[int, str] = {}
    param_name = None
    for a in sel.css("a[href]"):
        href = urljoin(url, a.attrib.get("href", "").strip())
        u = urlparse(href)
        if u.netloc != base.netloc:
            continue
        m = PAGE_PARAM.search("?" + u.query) if u.query else None
        if m and u.path.rstrip("/") == base.path.rstrip("/"):
            param_name = m.group(1)
            found[int(m.group(2))] = urldefrag(href)[0]
            continue
        m = PAGE_PATH.search(u.path)
        if m and u.path[: m.start()].rstrip("/") == re.sub(PAGE_PATH, "", base.path).rstrip("/"):
            found[int(m.group(2))] = urldefrag(href)[0]
    for a in sel.css('a[rel="next"], link[rel="next"]'):
        href = urljoin(url, a.attrib.get("href", ""))
        if urlparse(href).netloc == base.netloc:
            found.setdefault(10_000 + len(found), urldefrag(href)[0])
    numbered = [n for n in found if n < 10_000]
    if param_name and numbered and max(numbered) <= 60:  # görünmeyen ara sayfaları doldur (1 … 5 … 9)
        q = [(k, v) for k, v in parse_qsl(base.query) if k.lower() != param_name.lower()]
        for n in range(1, max(numbered) + 1):
            if n not in found:
                found[n] = urlunparse(base._replace(query=urlencode(q + [(param_name, n)])))
    own = urldefrag(url)[0].rstrip("/")
    return [u for _, u in sorted(found.items()) if u.rstrip("/") != own][:60]


async def scan_pagination(sel, url: str, name: str, log, seen: set[str] | None = None):
    """Sayfalı kadro listesinin tüm sayfalarını Scrapling ile paralel tarar."""
    from .discover import _visible_text

    pages = [u for u in pagination_links(sel, url) if not seen or u.rstrip("/") not in seen]
    if not pages:
        return None, []
    await log("crawl", "running", f"Sayfalama algılandı: {url} → {len(pages)} sayfa daha, Scrapling ile paralel taranıyor.")
    sem = asyncio.Semaphore(8)

    async def one(u):
        async with sem:
            try:
                p = await fetch_static(u, timeout=15)
                return p, _visible_text(p.selector)
            except Exception:  # noqa: BLE001
                return None

    results = await asyncio.gather(*(one(u) for u in pages))
    if seen is not None:
        seen.update(u.rstrip("/") for u in pages)
    for res in results:
        if res and name_in_text(name, res[1]):
            p, t = res
            await log("crawl", "done", f"Kişi sayfalı listenin içinde bulundu: {p.url}")
            return (p.selector, p.url, p.html, t), pages
    return None, pages


def _search_selector(sel) -> str | None:
    for css in SEARCH_INPUTS:
        try:
            if sel.css(css):
                return css
        except Exception:  # noqa: BLE001
            continue
    return None


async def perceive(llm, name: str, sel, url: str, links: list[tuple[str, str]], has_search: bool,
                   trail: list[str], tried_search: bool) -> dict | None:
    """Gemini sayfayı OKUR: türünü belirler, hedef kişinin sayfası mı karar verir, bilgileri çıkarır ve yön seçer."""
    title = clean(sel.css("title::text").get() or "")
    listing = "\n".join(f"{i}. {t[:70]} — {urlparse(u).netloc}{urlparse(u).path[:70]}" for i, (u, t) in enumerate(links))
    prompt = (
        f"GÖREV: Bir üniversite sitesinde '{name}' adlı akademisyenin KENDİ profil sayfasını veya içinde yer aldığı "
        "akademik kadro listesini bulmak.\n"
        f"SAYFA: {title} ({url})\nİZLENEN YOL: {' → '.join(trail[-5:]) or '(başlangıç)'}\n"
        f"SİTE ARAMA KUTUSU: {'VAR' if has_search and not tried_search else 'YOK/denendi'}\n\n"
        f"SAYFA İÇERİĞİ (Markdown):\n{page_view(sel)}\n\nLİNKLER:\n{listing}\n\n"
        "YAP:\n"
        f"1) page_type: {', '.join(PAGE_TYPES)}.\n"
        f"2) is_target_person_page: sayfa '{name}' kişisinin profili mi, ya da onu bir kişi kartı olarak içeren "
        "kadro listesi mi? Adın yalnızca haberde, arama sonucunda, tez danışmanı olarak geçmesi HAYIR demektir.\n"
        "3) Hedefse: title (akademik unvan), department (bölüm), interests (araştırma alanları) — SADECE sayfada "
        "yazanlar, yoksa boş bırak.\n"
        "4) Hedef değilse next_links: kişiye en hızlı götürecek en fazla 3 link numarası. Tipik yol: Fakülteler → "
        "Fakülte → Bölüm → Akademik Kadro/Öğretim Üyeleri/People/Faculty; arama sonucundaysan kişinin profil "
        "sayfasına götüren sonucu seç.\n"
        "5) use_search: yalnızca arama kutusu VAR ve hiçbir link kadro/fakülte/bölüm/people sayfasına benzemiyorsa true.\n"
        "6) reason: tek cümle Türkçe gerekçe."
    )
    data = await llm.json(prompt, PERCEIVE_SCHEMA, timeout=90)
    if not data or data.get("page_type") not in PAGE_TYPES:
        return None
    data["next_links"] = [i for i in data.get("next_links", []) if isinstance(i, int) and 0 <= i < len(links)][:BEAM]
    # Doğrulama: LLM'in söyledikleri sayfa metninde gerçekten var mı?
    text = clean(sel.get_all_text(separator=" "))
    if data.get("is_target_person_page") and not name_in_text(name, text):
        data["is_target_person_page"] = False
        data["reason"] = "Gemini hedef dedi ama ad sayfada yok → reddedildi. " + data.get("reason", "")
    page_f = fold(text)
    for key in ("title", "department"):
        v = clean(data.get(key) or "")
        data[key] = v if v and fold(v) in page_f else ""
    data["interests"] = [clean(x) for x in data.get("interests") or [] if clean(x) and fold(x) in page_f][:10]
    return data


async def _rea_search(url: str, selector: str, name: str, store: dict, log):
    """REA: site arama kutusuna adı yazar, gönderir; gizli arama isteğini tarif olarak öğrenir."""
    from .config import chromium_executable

    exe = chromium_executable()
    if not exe or not rea.available():
        return None
    scenario = {
        "browser": {"mode": "launch", "executable_path": exe, "headless": True},
        "start_url": {"url": url, "query": []},
        "actions": [
            {"step_id": "settle", "action": "wait_for_timeout", "duration_ms": 1500},
            {"step_id": "fill", "action": "fill", "locator": {"kind": "css", "selector": selector},
             "value": {"source": "literal", "value": name}, "timeout_ms": 6000},
            {"step_id": "submit", "action": "press", "locator": {"kind": "css", "selector": selector},
             "key": "Enter", "timeout_ms": 6000},
            {"step_id": "results", "action": "wait_for_timeout", "duration_ms": 3000},
        ],
        "capture": {"at_end": ["dom", "url"], "events": ["network"],
                    "network": {"request_body": True, "response_body": True, "header_values": False}},
    }
    cap = await asyncio.to_thread(rea.run_scenario_sync, scenario)
    if not cap.ok:
        await log("crawl", "warning", f"REA site araması başarısız: {cap.error[:120]}")
        return None
    learned = recipes.learn_replay(cap, name, "site_search")
    if learned:
        store["replay"]["site_search"] = learned
        recipes.event(store, "learned", f"site araması {learned['method']} {learned['url']}", evidence_id=cap.evidence_id)
        await log("crawl", "running", f"REA site aramasının isteğini çözdü: {learned['method']} {learned['url']} → tarif kaydedildi.")
    return cap


async def scan_known_staff_pages(store: dict, name: str, log):
    """Hafızadaki kadro sayfalarını Scrapling ile paralel tarar (LLM/REA gerektirmez)."""
    pages = list(dict.fromkeys(store.get("staff_pages", [])))[:60]
    if not pages:
        return None
    await log("crawl", "running", f"Hafıza: bu sitede daha önce öğrenilmiş {len(pages)} kadro sayfası Scrapling ile paralel taranıyor…")
    sem = asyncio.Semaphore(10)

    async def one(u):
        async with sem:
            try:
                p = await fetch_static(u, timeout=15)
                from .discover import _visible_text

                t = _visible_text(p.selector)
                return (p.selector, p.url, p.html, t) if name_in_text(name, t) else None
            except Exception:  # noqa: BLE001
                return None

    for res in await asyncio.gather(*(one(u) for u in pages)):
        if res:
            await log("crawl", "done", f"Kişi hafızadaki kadro sayfasında bulundu: {res[1]} (ajan çalıştırılmadı).")
            return res
    return None


async def navigate(start_url: str, start_sel, start_html: str, name: str, llm, store: dict, log, report: dict):
    """LLM yönlendirmeli arama. Bulursa (sel, url, html, text) döndürür."""
    from .discover import _visible_text

    root = _registrable(urlparse(start_url).hostname or "")
    seen = {urldefrag(start_url)[0].rstrip("/")}
    staff = set(store.get("staff_pages", []))
    frontier = [(start_url, start_sel, start_html, ["başlangıç"])]
    steps, fetched, tried_search = 0, 1, False
    report["agent"] = {"steps": []}
    await log("crawl", "running", f"Ajan başlıyor: Scrapling sayfayı getirip Markdown'a çeviriyor, Gemini okuyup algılıyor "
                                  f"ve yön seçiyor, REA gerekirse etkileşime giriyor (en fazla {MAX_STEPS} algı).")
    while frontier and steps < MAX_STEPS:
        url, sel, html, trail = frontier.pop(0)
        text = _visible_text(sel)
        links = _candidate_links(sel, url, root, seen)
        search_css = _search_selector(sel)
        view = await perceive(llm, name, sel, url, links, bool(search_css), trail, tried_search)
        steps += 1
        if view is None:
            await log("crawl", "warning", "Gemini sayfayı algılayamadı (geçersiz çıktı); bu dal atlandı.")
            continue
        chosen = [links[i] for i in view["next_links"]]
        report["agent"]["steps"].append({"at": url, "page_type": view["page_type"], "target": view["is_target_person_page"],
                                         "action": "search" if view["use_search"] else "open",
                                         "reason": view.get("reason", ""), "chosen": [u for u, _ in chosen]})
        await log("crawl", "running", f"Gemini algısı #{steps}: [{PAGE_TYPE_TR[view['page_type']]}] "
                                      f"{'HEDEF ✓' if view['is_target_person_page'] else 'hedef değil'} — "
                                      f"{view.get('reason', '')[:110]}")
        if view["page_type"] == "staff_list" and not view["is_target_person_page"]:
            staff.add(urldefrag(url)[0])
            hit, pages = await scan_pagination(sel, url, name, log, seen)  # sayfalı kadro listesi
            staff.update(pages)
            if hit:
                staff.add(urldefrag(hit[1])[0])
                store["staff_pages"] = sorted(staff)
                report["agent"]["found_at"] = hit[1]
                return hit
        if view["is_target_person_page"]:
            if view["page_type"] == "staff_list":
                staff.add(urldefrag(url)[0])
            store["staff_pages"] = sorted(staff)
            report["agent"]["found_at"] = url
            report["agent"]["person"] = {k: view.get(k) for k in ("title", "department", "interests")}
            await log("crawl", "done", f"Ajan kişiyi buldu: {url} ({steps} algı, {fetched} sayfa).")
            return sel, url, html, text
        if view["use_search"] and search_css and not tried_search:
            tried_search = True
            cap = await _rea_search(url, search_css, name, store, log)
            if cap and cap.dom:
                rsel = parse(cap.dom, cap.final_url or url)
                frontier.insert(0, (cap.final_url or url, rsel, cap.dom, trail + ["site araması"]))
            continue
        if not chosen:
            continue
        await log("crawl", "running", "Scrapling açıyor: " + " · ".join(t[:35] for _, t in chosen))
        results = await asyncio.gather(*(fetch_smart(u) for u, _ in chosen), return_exceptions=True)
        new = []
        for (u, t), res in zip(chosen, results):
            seen.add(urldefrag(u)[0].rstrip("/"))
            if isinstance(res, Exception) or res.status >= 400:
                continue
            fetched += 1
            new.append((res.url, res.selector, res.html, trail + [t[:30]]))
        # Adı içeren sayfalar önce algılansın; yoksa Gemini'nin sırası korunur (derinlik önce)
        new.sort(key=lambda x: not name_in_text(name, _visible_text(x[1])))
        frontier = new + frontier
    store["staff_pages"] = sorted(staff)
    await log("crawl", "warning", f"LLM ajanı {steps} algıda kişiyi bulamadı.")
    return None
