"""Üniversite sitesinden akademisyeni bulma ve profil çıkarma.

Akış:
  1. Başlangıç sayfası iki kanaldan paralel okunur:
       - Scrapling (statik, gerekirse stealth)
       - REA recon (render edilmiş DOM + ağ haritası + JSON gövdeleri)
  2. İçeriğin nereden geldiği raporlanır (sunucu HTML / JS render / gizli JSON API).
  3. Kişi sayfada yoksa: aynı kurum alan adında, puanlanmış linklerle sınırlı
     BFS (odaklı crawler). Sayfalar Scrapling AsyncFetcher ile eşzamanlı çekilir.
  4. Kişi kartı ve profil sayfası bulunur; alanlar köken bilgisiyle çıkarılır.
"""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from urllib.parse import urldefrag, urljoin, urlparse

from . import navigator, rea, recipes
from .config import CRAWL_CONCURRENCY, CRAWL_MAX_DEPTH, CRAWL_MAX_PAGES
from .net import Page, fetch_smart, fetch_static, parse, wall_reason
from .text import clean, detect_title, fold, lower_tr, name_in_text, name_tokens, strip_titles

STAFF_WORDS = re.compile(r"kadro|staff|akademik|academic|personel|people|faculty|ogretim|uyeler|team|kisiler|"
                         r"members|directory|ogretim-elemanlari|akademisyen", re.I)
DEPT_WORDS = re.compile(r"bolum|department|muhendisli|fakulte|faculty|program|enstitu|institute|school|"
                        r"yuksekokul|college|anabilim", re.I)
BAD_WORDS = re.compile(r"haber|news|duyuru|announcement|etkinlik|event|blog|login|giris|shop|cart|basvuru|"
                       r"ihale|galeri|gallery|video|takvim|calendar|menu|yemek|kariyer|mezun|alumni|"
                       r"cookie|kvkk|privacy|sitemap|social|wp-json|feed|kayit|rehber|ogrenci-isleri|aday|burs|"
                       r"ucret|yurt|kampus|iletisim|contact", re.I)
SKIP_EXT = re.compile(r"\.(pdf|jpe?g|png|gif|svg|webp|docx?|xlsx?|pptx?|zip|rar|mp4|mp3|ics)(\?|$)", re.I)

INTEREST_LABEL = re.compile(
    r"(?:(araştırma alanları|araştırma ilgi alanları|ilgi alanları|çalışma alanları|uzmanlık alanları|"
    r"research interests?|research areas?|areas of (?:interest|expertise))\s*[:：|]?"
    r"|(interests|expertise)\s*[:：])", re.I)
STOP_LABEL = re.compile(
    r"\b(e-?posta|e-?mail|tel(?:efon)?|phone|ofis|office|oda|room|adres|address|faks|fax|dahili|"
    r"eğitim|education|özgeçmiş|cv|yayınlar|publications|dersler|courses|web)\b\s*[:：]?", re.I)

ORCID_RE = re.compile(r"\b(\d{4}-\d{4}-\d{4}-\d{3}[\dX])\b")
SCHOLAR_RE = re.compile(r"scholar\.google\.[a-z.]+/citations\?[^\"'\s<>]*user=([\w-]{12})")
YOK_RE = re.compile(r"(https?://akademik\.yok\.gov\.tr/AkademikArama/[^\"'\s<>]*authorId=([0-9A-F]{16})[^\"'\s<>]*)")


def registrable(host: str) -> str:
    labels = (host or "").lower().split(".")
    if len(labels) >= 3 and labels[-2] in {"edu", "ac", "com", "org", "gov", "net", "gen", "bel", "k12"} \
            and len(labels[-1]) == 2:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


@dataclass
class Fact:
    value: object
    source: str  # "university", "rea-json", "yok", "scholar", "openalex", "llm", ...
    url: str = ""


@dataclass
class Profile:
    query_name: str
    name: str = ""
    facts: dict[str, Fact] = field(default_factory=dict)
    links: dict[str, str] = field(default_factory=dict)
    source_url: str = ""
    listing_url: str = ""
    found: bool = False
    page_text: str = ""
    card_text: str = ""
    observations: list[dict] = field(default_factory=list)  # doğrulama için her gözlem
    verification: dict = field(default_factory=dict)

    def observe(self, key: str, value, source: str, url: str = ""):
        """Kaynaktan gelen bilgiyi seçmeden kayda geçirir (konsensüs için)."""
        if value in (None, "", [], {}):
            return
        self.observations.append({"field": key, "value": value, "source": source, "url": url})

    def set(self, key: str, value, source: str, url: str = "", override: bool = False):
        if value in (None, "", [], {}):
            return
        if key in ("title", "department", "institution", "interests", "field"):
            self.observe(key, value, source, url)
        if override or key not in self.facts:
            self.facts[key] = Fact(value, source, url)

    def get(self, key: str, default=None):
        fact = self.facts.get(key)
        return fact.value if fact else default

    def to_dict(self) -> dict:
        return {
            "name": self.name or strip_titles(self.query_name),
            "query_name": self.query_name,
            "title": self.get("title", ""),
            "department": self.get("department", ""),
            "institution": self.get("institution", ""),
            "interests": self.get("interests", []),
            "bio": self.get("bio", ""),
            "orcid": self.links.get("orcid", ""),
            "links": self.links,
            "source_url": self.source_url,
            "listing_url": self.listing_url,
            "found": self.found,
            "provenance": {k: {"source": f.source, "url": f.url} for k, f in self.facts.items()},
            "verification": self.verification,
        }


# ------------------------------------------------------------------ yardımcılar
def _person_container(sel, name: str):
    """Kişinin adını içeren en küçük anlamlı içerik kabı (profil sayfalarında menü gürültüsünü atar)."""
    ignore = ("script", "style", "noscript", "template", "svg")
    best, best_len = None, 10**9
    for css in ("main", "article", "#content", ".content", "#main", "[class*=profile]", "[class*=detail]",
                "[class*=person]", "[class*=personel]", "[class*=member]", "section"):
        try:
            els = sel.css(css)
        except Exception:  # noqa: BLE001
            continue
        for el in els[:6]:
            text = clean(el.get_all_text(separator=" | ", ignore_tags=ignore))
            if 150 <= len(text) < best_len and name_in_text(name, text):
                best, best_len = el, len(text)
    return best


def _visible_text(sel) -> str:
    """Sayfanın asıl içeriği. <main>/<article> gibi kaplar ancak gövdenin anlamlı bir
    kısmını kapsıyorsa tercih edilir (bazı sitelerde <main> yalnızca arama penceresidir)."""
    ignore = ("script", "style", "noscript", "template", "svg")
    try:
        body = clean(sel.get_all_text(separator=" ", ignore_tags=ignore))
    except Exception:  # noqa: BLE001
        return ""
    best = body
    for css in ("main", "article", "#content", ".content", "#main", ".main-content"):
        for el in sel.css(css)[:3]:
            text = clean(el.get_all_text(separator=" ", ignore_tags=ignore))
            if len(text) >= 0.3 * len(body) and len(text) < len(best):
                best = text
    return best


def _links(sel, base: str) -> list[tuple[str, str]]:
    out = []
    for a in sel.css("a[href]"):
        href = (a.attrib.get("href") or "").strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        url = urldefrag(urljoin(base, href))[0]
        if url.startswith("http"):
            out.append((url, clean(a.get_all_text(separator=" "))[:160]))
    return out


def _external_ids(html: str, profile: Profile, url: str):
    m = SCHOLAR_RE.search(html)
    if m and "scholar" not in profile.links:
        profile.links["scholar"] = f"https://scholar.google.com/citations?user={m.group(1)}"
    m = YOK_RE.search(html)
    if m and "yok" not in profile.links:
        profile.links["yok"] = m.group(1).replace("&amp;", "&")
    m = re.search(r"orcid\.org/(\d{4}-\d{4}-\d{4}-\d{3}[\dX])", html)
    if m and "orcid" not in profile.links:
        profile.links["orcid"] = m.group(1)
    for key, rx in (("researchgate", r"https?://(?:www\.)?researchgate\.net/profile/[^\"'\s<>]+"),
                    ("avesis", r"https?://avesis\.[a-z.]+/[^\"'\s<>]+"),
                    ("scopus", r"https?://www\.scopus\.com/authid/detail\.uri\?authorId=\d+"),
                    ("wos", r"https?://www\.webofscience\.com/wos/author/record/[^\"'\s<>]+")):
        m = re.search(rx, html)
        if m and key not in profile.links:
            profile.links[key] = m.group(0).replace("&amp;", "&")


JUNK_INTEREST = {"welcome", "home", "ana sayfa", "anasayfa", "hos geldiniz", "hosgeldiniz", "menu", "contact",
                 "iletisim", "publications", "yayinlar", "teaching", "dersler", "news", "haberler", "cv", "ozgecmis",
                 "students", "ogrenciler", "projects", "projeler", "links", "baglantilar", "more", "devami"}
SENTENCE_INTEREST = re.compile(
    r"(?:ilgi|çalışma|araştırma|uzmanlık)\s+alanlar[ıi](?:n[ıi])?\s+(?:arasında\s+)?(.{5,300}?)"
    r"(?:['’]?(?:d[ıiuü]r|t[ıiuü]r)|\s+(?:yer\s+almaktadır|bulunmaktadır|oluşturmaktadır))?\s*\.", re.I)
SENTENCE_INTEREST_EN = re.compile(r"(?:research\s+)?interests?\s+(?:include|are|lie in|focus on)\s+(.{5,300}?)\.", re.I)


def _interests(text: str) -> list[str]:
    m = INTEREST_LABEL.search(text)
    if m:
        tail = text[m.end(): m.end() + 400]
        stop = STOP_LABEL.search(tail)
        chunk = tail[: stop.start()] if stop else tail
    else:
        # Türkçe biyografilerde sık görülen cümle biçimi:
        # "İlgi alanları bilgisayar programlama, e-öğrenme ve proje yönetimidir."
        m = SENTENCE_INTEREST.search(text) or SENTENCE_INTEREST_EN.search(text)
        if not m:
            return []
        chunk = re.sub(r"(?i)(?<=[a-zçğıöşü])(?:dir|dır|dur|dür|tir|tır|tur|tür)$", "", m.group(1).strip())
        chunk = re.sub(r"(?i)(yönetimi|tasarımı|analizi|işlemesi|öğrenmesi|güvenliği|teknolojileri)(?:dir|dır|dur|dür|tir|tır)?$",
                       r"\1", chunk)
        chunk = re.sub(r"\s+(?:ve|ile|and|&)\s+", ", ", chunk)
    chunk = chunk.strip(" :：-–")
    parts = [clean(p).strip(" .|") for p in re.split(r"[,;•·|\n]|\s-\s", chunk)]
    out, seen = [], set()
    for p in parts:
        if fold(p) in JUNK_INTEREST:
            continue
        if 2 < len(p) < 70 and fold(p) not in seen and not re.search(r"@|\d{3}", p):
            seen.add(fold(p))
            out.append(p)
    return out[:12]


DEPT_RE = re.compile(r"((?:[A-ZÇĞİÖŞÜ][\wçğıöşüÇĞİÖŞÜ&\-]*\s+){1,6})([Bb]ölüm(?:ü|üne|ünde|ünden)|[Aa]nabilim [Dd]al[ıi]|[Pp]rogram[ıi])"
                     r"|(Department of(?:\s+[A-Z&][\w\-]*){1,6})")
CURRENT_CUE = re.compile(r"katıl|görev\s+yap|çalışmakta|öğretim üyesi|başkan|joined|currently|serves", re.I)
PAST_CUE = re.compile(r"mezun|lisans|doktora|derecesini|eğitimini|tamamla|almıştır|graduated|ph\.?d|received|degree", re.I)


DEPT_LINE = re.compile(r"^[A-ZÇĞİÖŞÜ][\wçğıöşüÇĞİÖŞÜ&,.\- ]{3,70}"
                       r"(Mühendisliği|Bölümü|Bilimleri|Programı|Anabilim Dalı|Engineering|Sciences?|Department|Studies)$")


def _department(text: str, sel, institution: str = "") -> str:
    dept = _department_raw(text, sel, institution)
    return re.sub(r"^.*?(?:Üniversitesi|ÜNİVERSİTESİ|University)\s+", "", dept).strip() or dept


def _department_raw(text: str, sel, institution: str = "") -> str:
    # Profil kartında adın hemen yanındaki kısa satır: "Prof. Dr. | Endüstri Mühendisliği | ENG 119"
    for seg in [clean(x) for x in text[:600].split("|")]:
        if DEPT_LINE.match(seg) and "Fakülte" not in seg and "Üniversite" not in seg:
            return seg
    title = clean(sel.css("title::text").get() or "")
    parts = [p.strip() for p in re.split(r"\s[|–—-]\s|\|", title) if p.strip()]
    for p in parts:
        if DEPT_WORDS.search(fold(p)) and not STAFF_WORDS.search(fold(p)) and len(p) < 90 \
                and "fakulte" not in fold(p) and "universite" not in fold(p):
            return p
    inst_f = fold(institution).split()[:2]
    best, best_score = "", -99.0
    for m in DEPT_RE.finditer(text):
        if m.group(3):
            phrase = clean(m.group(3))
        else:
            phrase = clean(m.group(1)) + " " + ("Bölümü" if m.group(2).lower().startswith("bölüm") else clean(m.group(2)))
        phrase = re.sub(r"^.*?(?:Üniversitesi|ÜNİVERSİTESİ|University)\s+", "", phrase)
        before = fold(text[max(0, m.start() - 80): m.start()])
        after = text[m.end(): m.end() + 60]
        score = 0.0
        if inst_f and all(t in before.split() for t in inst_f):
            score += 3  # "Ankara Bilim Üniversitesi Bilgisayar Mühendisliği bölümüne"
        if CURRENT_CUE.search(after) or CURRENT_CUE.search(text[max(0, m.start() - 40): m.start()]):
            score += 2
        if PAST_CUE.search(after) or PAST_CUE.search(text[max(0, m.start() - 60): m.start()]):
            score -= 3
        score -= m.start() / 5000  # erken geçen hafif öncelikli
        if score > best_score:
            best, best_score = phrase, score
    return best


INST_RE = re.compile(
    r"((?:[A-ZÇĞİÖŞÜ][\w'’.\-]*\s+){1,5}(?:Teknik\s+|Technical\s+)?(?:Üniversitesi|ÜNİVERSİTESİ|University))"
    r"|(University\s+of(?:\s+[A-Z][\w'’.\-]*){1,4})")


def _institution(sel) -> str:
    """Kurum adı yalnızca site kimliği taşıyan yerlerden okunur (meta, başlık, header/footer);
    biyografideki mezuniyet üniversiteleri karışmasın."""
    sources = [sel.css('meta[property="og:site_name"]::attr(content)').get() or "",
               sel.css("title::text").get() or ""]
    for css in ("footer", "header", ".footer", "#footer", ".navbar-brand", ".logo"):
        for el in sel.css(css)[:2]:
            sources.append(clean(el.get_all_text(separator=" "))[:3000])
    for img in sel.css("img[alt]")[:15]:
        sources.append(img.attrib.get("alt", ""))
    candidates = []
    for source in sources:
        for m in INST_RE.finditer(source or ""):
            candidates.append(clean(m.group(0)))
    if not candidates:
        return ""
    best = max(set(candidates), key=lambda c: (candidates.count(c), -len(c)))
    return tr_title(best) if best.isupper() else best


def tr_title(text: str) -> str:
    text = re.sub(r"[\"“”‘’'\[\]()<>{}*_#|]", "", text).strip(" .,:;-")
    return " ".join(w[:1] + lower_tr(w[1:]) if w.isupper() and len(w) > 1 else w for w in text.split())


def _card_for(sel, name: str):
    """Adın geçtiği en küçük öğeden başlayıp 'kişi kartı' büyüklüğüne kadar tırmanır."""
    best = None
    for el in sel.xpath("//body//*[not(self::script) and not(self::style)]"):
        own = clean(el.text or "")
        if own and name_in_text(name, own):
            best = el
            break
    if best is None:
        for el in sel.css("a, h1, h2, h3, h4, h5, strong, b, span, p, td, div"):
            txt = clean(el.get_all_text(separator=" "))
            if len(txt) < 200 and name_in_text(name, txt):
                best = el
                break
    if best is None:
        return None, ""
    # Yapısal kart tespiti (Scrapling find_similar): isimden yukarı çıkarken, aynı yapıda kardeşleri olan
    # ve yalnızca BU kişinin adını içeren ilk ata = kişi kartı. Unvan yazımına/dile bağlı değildir.
    node = best
    for _ in range(8):
        parent = node.parent
        if parent is None or parent.tag in ("body", "html"):
            break
        try:
            similar = node.find_similar(similarity_threshold=0.3)
        except Exception:  # noqa: BLE001
            similar = []
        node_text = clean(node.get_all_text(separator=" "))
        # kart = isimden fazlasını (unvan, bağlantı, alan…) taşıyan tekrar eden birim
        if len(similar) >= 2 and len(node_text) > len(clean(best.get_all_text(separator=" "))) + 12:
            return node, node_text
        node = parent
    # Yedek: metin uzunluğu ve unvan sayısı sezgisi
    card = best
    for _ in range(8):
        parent = card.parent
        if parent is None or parent.tag in ("body", "html"):
            break
        ptxt = clean(parent.get_all_text(separator=" "))
        titles = len(TITLE_COUNT.findall(ptxt))
        if len(ptxt) > 1500 or titles > 2:
            break
        card = parent
    return card, clean(card.get_all_text(separator=" "))


TITLE_COUNT = re.compile(r"Prof\.|Doç\.|Dr\.\s*Öğr|Öğr\.\s*Gör|Arş\.\s*Gör|Professor|Lecturer|Profesör|Doçent|"
                         r"Doktor Öğretim|Öğretim Üyesi|Öğretim Görevlisi|Araştırma Görevlisi|Assoc\.|Assist\.", re.I)


def _profile_link(card, sel, base: str, name: str) -> str:
    tokens = name_tokens(name)
    scopes = [card] if card is not None else []
    scopes.append(sel)
    for scope in scopes:
        for url, text in _links(scope, base):
            slug = fold(urlparse(url).path.replace("-", " ").replace("_", " ").replace("/", " "))
            if name_in_text(name, text) or (tokens and all(t[:4] in slug for t in tokens)):
                if not SKIP_EXT.search(url) and "mailto" not in url:
                    return url
        if scope is card:
            for url, text in _links(card, base):
                if re.search(r"özgeçmiş|ozgecmis|\bcv\b|profil|profile|detay|more|devam|homepage|home page|"
                             r"web\s*(?:site|sayfa)?|kişisel|kisisel|personal", fold(text) + " " + text, re.I) \
                        and not SKIP_EXT.search(url):
                    return url
    return ""


def _json_hits(obj, name: str, path: str = "$", depth: int = 0):
    """JSON içinde adla eşleşen alt nesneleri (kayıtları) bulur."""
    if depth > 7:
        return
    if isinstance(obj, dict):
        flat = " ".join(str(v) for v in obj.values() if isinstance(v, (str, int)))
        if name_in_text(name, flat):
            yield path, obj
            return
        for k, v in obj.items():
            yield from _json_hits(v, name, f"{path}.{k}", depth + 1)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:500]):
            yield from _json_hits(v, name, f"{path}[{i}]", depth + 1)


def _link_score(url: str, text: str, name: str, root_domain: str) -> float:
    host = urlparse(url).hostname or ""
    if registrable(host) != root_domain or SKIP_EXT.search(url):
        return -1
    blob = fold(f"{url} {text}")
    if BAD_WORDS.search(blob):
        return -1
    score = 0.0
    tokens = name_tokens(name)
    if tokens and all(t in blob for t in tokens):
        score += 50
    if STAFF_WORDS.search(blob):
        score += 6
    if DEPT_WORDS.search(blob):
        score += 2
    if re.search(r"/en/|lang=en", url):
        score -= 1.5
    return score


# -------------------------------------------------------------------- ana akış
async def locate(url: str, name: str, log, llm=None) -> tuple[Profile, dict]:
    profile = Profile(query_name=name)
    report: dict = {"start_url": url, "strategy": [], "rea": None, "crawl": {"pages": 0}, "walls": [],
                    "recipe": {"events": []}}
    domain = registrable(urlparse(url).hostname or "")
    store = recipes.load(domain)
    pk = recipes.person_key(name)
    known = store["people"].get(pk)

    async def rlog(kind: str, msg: str, status: str = "running"):
        report["recipe"]["events"].append({"kind": kind, "detail": msg})
        await log("rea", status, msg)

    # 0) Arama motoru: site:alanadı "Ad Soyad" — başlangıç sayfası okunurken AYNI ANDA
    web_task = asyncio.create_task(_web_person(url, name, log, report))

    # 1) Scrapling her zaman önce: hızlı, ucuz, parmak izi için yeterli
    page: Page | None = None
    try:
        page = await fetch_smart(url, log=lambda m: log("scrape", "running", m))
        report["strategy"].append(page.via)
        await log("scrape", "running", f"Scrapling [{page.via}]: HTTP {page.status}, {len(page.html)//1024} KB HTML.")
        reason = wall_reason(page.status, page.html)
        if reason:
            report["walls"].append({"url": url, "reason": reason})
    except Exception as exc:  # noqa: BLE001
        await log("scrape", "warning", f"Scrapling başlangıç sayfasını okuyamadı: {type(exc).__name__}.")
    static_sel = page.selector if page else None
    static_text = _visible_text(static_sel) if static_sel is not None else ""
    skeleton = recipes.dom_skeleton(static_sel) if static_sel is not None else []

    try:
        web_hit = await web_task
    except Exception:  # noqa: BLE001
        web_hit = None

    # 2) Değişiklik algılama: saklı site haritasıyla kıyas
    chk = recipes.check_page(store, url, skeleton) if skeleton else {"known": False}
    report["recipe"]["start_page"] = chk
    replay = store["replay"].get("person_lookup") or store["replay"].get("listing_api")
    need_rea = rea.available() and web_hit is None  # kişi bulunduysa REA keşfine gerek yok
    if web_hit is not None:
        pass
    elif chk.get("known") and not chk.get("drift"):
        await rlog("cache", f"Site haritası hafızada ({chk['learned_at']} öğrenildi); yapı benzerliği "
                            f"%{chk['similarity']*100:.0f} → değişiklik yok.")
        need_rea = False
        if replay:
            ok = await _try_replay(profile, replay, name, store, report, rlog)
            need_rea = not ok and rea.available()
        elif chk.get("content_origin") == "javascript-render":
            need_rea = rea.available()  # JS sitesi ama tarif yok → REA gerekli
        if not need_rea:
            await rlog("skip", "REA atlandı; Scrapling hızlı yolu kullanılıyor.")
    elif chk.get("known") and chk.get("drift"):
        recipes.event(store, "drift", f"{url}: DOM benzerliği %{chk['dom_similarity']*100:.0f}")
        await rlog("drift", f"DEĞİŞİKLİK ALGILANDI: sayfa yapısı değişmiş (benzerlik %{chk['similarity']*100:.0f} "
                            f"< %{recipes.DRIFT_THRESHOLD*100:.0f}) → REA siteyi yeniden öğreniyor.", "warning")

    # 3) REA: öğren / yeniden öğren
    capture = None
    rea_dom_sel = None
    if need_rea:
        await log("rea", "running", "REA: sayfa gerçek tarayıcıda açılıyor, tüm ağ trafiği Evidence olarak kaydediliyor…")
        capture = await rea.recon(url)
        if capture.ok:
            s = capture.summary()
            report["rea"] = s
            await log("rea", "running",
                      f"REA Evidence {capture.evidence_id[:14]}…: {s['requests']} istek, "
                      f"{len(capture.documents)} belge, {len(capture.api_calls)} XHR/fetch, "
                      f"{len(capture.json_endpoints)} JSON uç noktası, {s['third_party']} 3. taraf izleyici.")
            if capture.dom:
                rea_dom_sel = parse(capture.dom, capture.final_url or url)
        else:
            await log("rea", "warning", f"REA gözlemi tamamlanamadı: {capture.error[:160]}")
    elif not rea.available():
        await log("rea", "warning", "REA CLI bulunamadı (npm install); yalnızca Scrapling kullanılıyor.")

    rea_text = _visible_text(rea_dom_sel) if rea_dom_sel is not None else ""
    if capture is not None and capture.ok:
        if rea_text and len(rea_text) > max(600, len(static_text) * 1.5):
            report["content_origin"] = "javascript-render"
            await log("rea", "running", f"Teşhis: içerik JS ile render ediliyor (statik {len(static_text)} → "
                                        f"render {len(rea_text)} karakter).")
        else:
            report["content_origin"] = "server-html"
            await log("rea", "running", "Teşhis: içerik sunucu tarafında üretilmiş HTML; Scrapling hızlı yolu yeterli.")
        # Gizli API → tarif
        learned = recipes.learn_replay(capture, name, "person_lookup")
        for tx in capture.json_endpoints:
            for path, record in _json_hits(tx.json(), name):
                report["hidden_api"] = {"method": tx.method, "url": tx.url, "path": path}
                await log("rea", "running", f"Gizli API bulundu: {tx.method} {tx.url[:90]} → {path}")
                _absorb_json_record(profile, record, tx.url)
                if not learned:
                    learned = {"purpose": "listing_api", "method": tx.method, "url": tx.url, "query": [],
                               "form": [], "json": None, "returns": "json", "learned_at": recipes._now(),
                               "evidence_id": capture.evidence_id, "hits": 0, "failures": 0}
                break
            if "hidden_api" in report:
                break
        if learned:
            store["replay"][learned["purpose"]] = learned
            recipes.event(store, "learned", f"{learned['method']} {learned['url']}", evidence_id=capture.evidence_id)
            await rlog("learned", f"Tarif öğrenildi: {learned['method']} {learned['url'][:80]} — sonraki çalıştırmada "
                                  f"Scrapling bunu tarayıcısız oynatacak.")
        recipes.remember_page(store, url, skeleton, recipes.api_shape(capture), report.get("content_origin", ""),
                              capture.evidence_id)
        recipes.event(store, "relearned" if chk.get("known") else "mapped", f"{url} haritalandı")
    elif skeleton:
        recipes.remember_page(store, url, skeleton, None)
    await log("rea", "done", "Site yapısı çözümlendi.")

    candidates = []
    if static_sel is not None:
        candidates.append((static_sel, page.url, page.html, static_text))
    if rea_dom_sel is not None:
        candidates.append((rea_dom_sel, capture.final_url or url, capture.dom, rea_text))

    hit = web_hit
    for sel, base, html, text in ([] if hit else candidates):
        if name_in_text(name, text) and navigator.is_person_hit(sel, text, name, base):
            hit = (sel, base, html, text)
            break

    # 4) Kişi hafızası: daha önce bulunduğu sayfa hâlâ geçerli mi?
    if hit is None and known and known.get("listing_url"):
        try:
            kp = await fetch_static(known["listing_url"])
            ktext = _visible_text(kp.selector)
            if name_in_text(name, ktext) and navigator.is_person_hit(kp.selector, ktext, name, kp.url):
                hit = (kp.selector, kp.url, kp.html, ktext)
                await rlog("memory", f"Hafıza: kişi daha önce {known['listing_url']} adresinde bulunmuştu, hâlâ orada "
                                     f"→ crawler atlandı ({known.get('seen', 1)}. görülme).")
            else:
                recipes.event(store, "person_moved", f"{name} artık {known['listing_url']} sayfasında değil")
                await rlog("drift", "DEĞİŞİKLİK: kişi önceki kadro sayfasında artık yok → yeniden taranıyor.", "warning")
        except Exception:  # noqa: BLE001
            pass

    # 5) Başlangıç sayfası sayfalı bir liste mi? → tüm sayfalar paralel
    if hit is None:
        for sel, base, _, text in candidates:
            hit, pages = await navigator.scan_pagination(sel, base, name, log)
            if pages:
                store["staff_pages"] = sorted(set(store.get("staff_pages", [])) | {urldefrag(base)[0], *pages})
            if hit:
                break
    # 6) Hafızadaki kadro sayfaları (ucuz), arama motoru, sonra LLM ajanı + Scrapling Spider yarışı
    if hit is None:
        hit = await navigator.scan_known_staff_pages(store, name, log)
    if hit is None and candidates:
        # Yarış: LLM ajanı (derin, akıllı) ve Scrapling Spider (geniş, paralel) AYNI ANDA çalışır;
        # önce bulan kazanır, diğeri durdurulur.
        seeds = []
        for sel, base, _, _ in candidates:
            seeds.extend(_links(sel, base))
        spider_stop = asyncio.Event()
        racers = {"spider": asyncio.create_task(_crawl(seeds, name, url, log, report, spider_stop))}
        if llm is not None and llm.available:
            start_sel, start_base, start_html, _ = candidates[-1] \
                if report.get("content_origin") == "javascript-render" else candidates[0]
            racers["agent"] = asyncio.create_task(navigator.navigate(start_base, start_sel, start_html, name, llm,
                                                                     store, log, report))
            await log("crawl", "running", "LLM ajanı ve Scrapling Spider paralel başladı; önce bulan kazanır.")
        hit, winner = await _race(racers, {"spider": spider_stop})
        if winner:
            report["race_winner"] = winner
            await log("crawl", "done", f"Kişiyi önce {'LLM ajanı' if winner == 'agent' else 'Scrapling Spider'} buldu; "
                                       "diğeri durduruldu.")

    if hit is None:
        recipes.save(store)
        await log("scrape", "warning", "Kişi kurum sitesinde bulunamadı; kimlik dış kaynaklardan (YÖK/OpenAlex) çözülecek.")
        if static_sel is not None:
            profile.set("institution", _institution(static_sel), "university", url)
        return profile, report

    sel, base, html, text = hit
    profile.found = True
    profile.listing_url = base
    if navigator.is_staff_page(text):
        store["staff_pages"] = sorted(set(store.get("staff_pages", [])) | {urldefrag(base)[0]})
    card, card_text = _card_for(sel, name)
    card = await _adaptive_card(card, html, base, pk, known, log, report)
    if card is not None:
        try:  # Scrapling find_similar: aynı yapıdaki tüm kişi kartları → bu bir kadro listesi mi?
            siblings = card.find_similar(similarity_threshold=0.3)
            if len(siblings) >= 3:
                report["staff_cards"] = len(siblings) + 1
                await log("scrape", "running", f"Scrapling find_similar: sayfada aynı yapıda {len(siblings) + 1} kişi kartı "
                                               "var → kadro listesi doğrulandı.")
                store["staff_pages"] = sorted(set(store.get("staff_pages", [])) | {urldefrag(base)[0]})
        except Exception:  # noqa: BLE001
            pass
    seen_by_ai = (report.get("agent") or {}).get("person") or {}
    for key in ("title", "department", "interests"):
        if seen_by_ai.get(key):
            value = detect_title(seen_by_ai[key]) or seen_by_ai[key] if key == "title" else seen_by_ai[key]
            profile.set(key, value, "llm", base)
    if card is not None and not card_text:
        card_text = clean(card.get_all_text(separator=" "))
    await log("scrape", "running", f"Kişi bulundu: {base}")
    profile.card_text = card_text[:2500]
    if card_text:
        profile.set("title", detect_title(card_text), "university", base)
        profile.set("interests", _interests(card_text), "university", base)
        _external_ids(card.html_content if hasattr(card, "html_content") else str(card), profile, base)
    profile.set("institution", _institution(sel), "university", base)
    profile.set("department", _department(card_text or "", sel, profile.get("institution", "")), "university", base)

    entry = store["people"].setdefault(pk, {"name": name, "seen": 0, "first_seen": recipes._now()})
    entry.update({"listing_url": base, "last_seen": recipes._now(), "seen": entry.get("seen", 0) + 1})
    if card is not None:
        try:
            entry["card_selector"] = card.generate_css_selector
        except Exception:  # noqa: BLE001
            pass

    link = _profile_link(card, sel, base, name)
    if link and link.rstrip("/") != base.rstrip("/"):
        await log("scrape", "running", f"Profil sayfası takip ediliyor: {link}")
        await _read_profile_page(profile, link, name, log, report)
    elif await _read_detail(profile, card, base, name, store, log, report):
        pass
    else:
        profile.source_url = base
        if card is None:  # liste sayfasında başka kişilerin linkleri karışmasın
            _external_ids(html, profile, base)
    if not profile.name:
        profile.name = _display_name(card_text or text, name)
    entry["profile_url"] = profile.source_url
    recipes.save(store)
    return profile, report


async def _web_person(url: str, name: str, log, report: dict):
    """Arama motoruna doğrudan `site:alanadı "Ad Soyad"` — soru yorumu yok, site taranmaz."""
    from . import websearch

    found = await websearch.site_search(url, f'"{strip_titles(name)}"', lambda m: log("crawl", "running", m), k=4)
    if not found:
        return None
    pages = await asyncio.gather(*(fetch_smart(u) for u in found), return_exceptions=True)
    for pg in pages:
        if isinstance(pg, Exception) or pg.status >= 400:
            continue
        t = _visible_text(pg.selector)
        if name_in_text(name, t) and navigator.is_person_hit(pg.selector, t, name, pg.url):
            report["race_winner"] = "websearch"
            await log("crawl", "done", f"Arama motoru kişiyi buldu: {pg.url} (REA keşfi ve site taraması atlandı).")
            return (pg.selector, pg.url, pg.html, t)
    return None


async def _race(tasks: dict[str, asyncio.Task], stops: dict[str, asyncio.Event] | None = None):
    """İlk None olmayan sonucu döndüren görev kazanır; kalanlar durdurulur (spider: sinyal, ajan: iptal)."""
    stops = stops or {}
    pending = set(tasks.values())
    names = {t: n for n, t in tasks.items()}
    try:
        while pending:
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                try:
                    res = t.result()
                except Exception:  # noqa: BLE001
                    res = None
                if res:
                    return res, names[t]
        return None, None
    finally:
        for t in pending:
            if names[t] in stops:
                stops[names[t]].set()  # Scrapling Spider'ı nazikçe durdur
            else:
                t.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)


async def _try_replay(profile: Profile, recipe: dict, name: str, store: dict, report: dict, rlog) -> bool:
    """REA'nın öğrendiği isteği Scrapling ile tarayıcısız oynatır. Başarısızsa drift sayılır."""
    import time as _t

    started = _t.time()
    try:
        resp = await recipes.replay_static(recipe, name)
        data = resp.json() if recipe.get("returns") == "json" else None
    except Exception as exc:  # noqa: BLE001
        resp, data = None, None
        err = type(exc).__name__
    else:
        err = f"HTTP {resp.status}"
    hits = list(_json_hits(data, name)) if data is not None else []
    elapsed = round(_t.time() - started, 2)
    if hits:
        recipe["hits"] = recipe.get("hits", 0) + 1
        _absorb_json_record(profile, hits[0][1], recipe["url"])
        report["recipe"]["replay"] = {"ok": True, "method": recipe["method"], "url": recipe["url"], "elapsed": elapsed}
        recipes.event(store, "replay_ok", f"{recipe['method']} {recipe['url']}", elapsed=elapsed)
        await rlog("replay", f"REA tarifi Scrapling ile tarayıcısız oynatıldı: {recipe['method']} {recipe['url'][:70]} "
                             f"→ {elapsed} sn (tarayıcı açılmadı).")
        return True
    recipe["failures"] = recipe.get("failures", 0) + 1
    report["recipe"]["replay"] = {"ok": False, "error": err, "url": recipe["url"]}
    recipes.event(store, "replay_failed", f"{recipe['url']}: {err}")
    await rlog("drift", f"DEĞİŞİKLİK: kayıtlı API tarifi artık çalışmıyor ({err}) → REA yeniden öğrenecek.", "warning")
    return False


async def _adaptive_card(card, html: str, base: str, pk: str, known: dict | None, log, report: dict):
    """Scrapling adaptive: kişi kartının imzası saklanır; site yapısı değişip eski seçici
    kırılırsa eleman benzerlik puanıyla yeni yapıda yeniden bulunur."""
    from scrapling.parser import Selector

    recipes.ADAPTIVE_DB.parent.mkdir(parents=True, exist_ok=True)
    try:
        asel = Selector(html, url=base, adaptive=True,
                        storage_args={"storage_file": str(recipes.ADAPTIVE_DB), "url": base})
        old = (known or {}).get("card_selector")
        ident = f"card:{pk}"
        if old:
            if asel.css(old):
                report["recipe"]["card"] = "stable"
            else:
                moved = asel.css(old, identifier=ident, adaptive=True, percentage=30)
                if moved:
                    report["recipe"]["card"] = "relocated"
                    await log("rea", "warning", "DEĞİŞİKLİK: kişi kartının eski seçicisi kırılmış → Scrapling adaptive "
                                                "eleman imzasıyla kartı yeni yapıda yeniden buldu.")
                    if card is None:
                        card = moved[0]
        if card is not None:
            asel.css(card.generate_css_selector, identifier=ident, auto_save=True)
    except Exception:  # noqa: BLE001
        pass
    return card


def _display_name(text: str, name: str) -> str:
    tokens = name_tokens(name)
    words = clean(text).split()
    for i in range(len(words)):
        window = words[i:i + len(tokens)]
        if [fold(w) for w in window] == tokens:
            return tr_title(" ".join(window))
    return tr_title(strip_titles(name))


def _absorb_json_record(profile: Profile, record: dict, url: str):
    for key, value in record.items():
        k = fold(str(key))
        if not isinstance(value, (str, int)):
            continue
        v = clean(value)
        if re.search(r"unvan|title|kadro", k) and len(v) < 60:
            profile.set("title", detect_title(v) or v, "rea-json", url)
        elif re.search(r"bolum|department|birim|unit", k):
            profile.set("department", v, "rea-json", url)
        elif re.search(r"ilgi|interest|alan|research", k) and len(v) < 400:
            profile.set("interests", [p.strip() for p in re.split(r"[,;]", v) if p.strip()], "rea-json", url)
        elif re.search(r"orcid", k):
            m = ORCID_RE.search(v)
            if m:
                profile.links["orcid"] = m.group(1)


async def _read_profile_page(profile: Profile, link: str, name: str, log, report: dict):
    try:
        page = await fetch_smart(link, log=lambda m: log("scrape", "running", m))
    except Exception as exc:  # noqa: BLE001
        await log("scrape", "warning", f"Profil sayfası okunamadı ({type(exc).__name__}).")
        profile.source_url = link
        return
    sel, html = page.selector, page.html
    text = _visible_text(sel)
    if len(text) < 400 and rea.available():
        await log("rea", "running", "Profil sayfası zayıf; REA ile render edilip yeniden gözleniyor.")
        cap = await rea.recon(link, settle_ms=2500)
        if cap.ok and cap.dom:
            sel, html = parse(cap.dom, link), cap.dom
            text = _visible_text(sel)
            for tx in cap.json_endpoints:
                for _, record in _json_hits(tx.json(), name):
                    _absorb_json_record(profile, record, tx.url)
                    break
    profile.source_url = page.url or link
    if "scholar" not in profile.links or "orcid" not in profile.links:
        await _personal_site_hop(profile, sel, page.url or link, log)
    box = _person_container(sel, name)
    if box is not None:
        text = clean(box.get_all_text(separator=" | ", ignore_tags=("script", "style", "noscript", "template")))
    _extract_profile(profile, sel, html, text, link, name)
    found = [k for k in ("orcid", "scholar", "yok", "researchgate", "avesis", "scopus") if k in profile.links]
    await log("scrape", "running", "Profil sayfasından dış kimlikler: " + (", ".join(found) if found else "yok"))


PERSONAL_SITE = re.compile(r"kişisel|personal|homepage|home page|web\s*site|web\s*sayfa|website|kendi sayfa", re.I)


async def _personal_site_hop(profile: Profile, sel, base: str, log):
    """Profil sayfasındaki 'Kişisel Web Sitesi' linkine BİR adım gidip Scholar/ORCID kimliklerini arar."""
    for url, text in _links(sel, base):
        if PERSONAL_SITE.search(text) and not SKIP_EXT.search(url) and url.rstrip("/") != base.rstrip("/"):
            try:
                page = await fetch_smart(url)
            except Exception:  # noqa: BLE001
                return
            before = set(profile.links)
            _external_ids(page.html, profile, url)
            new = sorted(set(profile.links) - before)
            await log("scrape", "running", f"Kişisel web sitesi tarandı ({url}): "
                                           + (f"yeni kimlik: {', '.join(new)}" if new else "ek kimlik yok"))
            return


def _extract_profile(profile: Profile, sel, html: str, text: str, link: str, name: str):
    """Profil sayfası VEYA JS ile açılan detay penceresinden alanları çıkarır."""
    profile.page_text = text[:6000]
    profile.set("title", detect_title(text[:1500]), "university", link)
    profile.set("interests", _interests(text), "university", link)
    dept = _department(text[:4000], sel, profile.get("institution", ""))
    if dept:  # kişinin kendi sayfası liste sayfasından daha güvenilir
        profile.set("department", dept, "university", link, override=True)
    profile.set("institution", _institution(sel), "university", link)
    _external_ids(html, profile, link)
    paragraphs = [clean(p.get_all_text(separator=" ")) for p in sel.css("main p, article p, .content p, p")]
    bio = max((p for p in paragraphs if len(p) > 180), key=len, default="")
    if not bio:
        bio = max((clean(x) for x in re.split(r"\s{2,}|\|", text) if len(clean(x)) > 180), key=len, default="")
    profile.set("bio", bio[:1500], "university", link)
    profile.name = _display_name(text, name)


DETAIL_WORDS = re.compile(r"detay|detail|bilgi|özgeçmiş|ozgecmis|\bcv\b|incele|profil|profile|more|devam|göster|view", re.I)


def _detail_button(card):
    """Kartın içindeki, sayfa değiştirmeyen (JS) 'detay' butonunu bulur."""
    if card is None:
        return None
    for el in card.css("a, button, [onclick], [data-id], [data-url]"):
        href = (el.attrib.get("href") or "").strip()
        js_like = (not href or href.startswith(("javascript:", "#")) or any(k.startswith("data-") for k in el.attrib)
                   or "onclick" in el.attrib)
        if js_like and (DETAIL_WORDS.search(clean(el.get_all_text(separator=" "))) or
                        any(k in el.attrib for k in ("data-id", "data-url", "data-personel", "data-person", "onclick"))):
            return el
    return None


def _button_selector(btn) -> str:
    for attr in ("data-id", "data-personel", "data-person", "data-uid", "id"):
        val = btn.attrib.get(attr)
        if val and re.fullmatch(r"[\w-]{1,64}", val) and not (attr == "id" and val.isidentifier() is False):
            if attr == "id":
                continue  # sitede birden çok kartta aynı id olabiliyor
            return f'{btn.tag}[{attr}="{val}"]'
    return btn.generate_css_selector


async def _read_detail(profile: Profile, card, base: str, name: str, store: dict, log, report: dict) -> bool:
    """JS 'Detaylı bilgi' butonu: önce kayıtlı tarif (Scrapling, tarayıcısız), yoksa REA ile öğren."""
    import time as _t

    btn = _detail_button(card)
    if btn is None:
        return False
    attrs = dict(btn.attrib)
    recipe = store["replay"].get("profile_detail")
    html = ""
    if recipe and recipe.get("id_attr") in attrs:
        started = _t.time()
        try:
            resp = await recipes.replay_static(recipe, name, {"id": attrs[recipe["id_attr"]]})
            data = None
            try:
                data = resp.json()
            except Exception:  # noqa: BLE001
                data = None
            html = recipes.html_from_response(data, resp.html_content or "")
        except Exception:  # noqa: BLE001
            html = ""
        elapsed = round(_t.time() - started, 2)
        if html and name_in_text(name, clean(parse(html, base).get_all_text(separator=" "))):
            recipe["hits"] = recipe.get("hits", 0) + 1
            recipes.event(store, "replay_ok", f"profil detayı {recipe['method']} {recipe['url']}", elapsed=elapsed)
            report["recipe"]["detail"] = {"ok": True, "replayed": True, "method": recipe["method"], "url": recipe["url"],
                                          "id_attr": recipe["id_attr"], "elapsed": elapsed}
            await log("rea", "running", f"REA tarifi: 'detay' butonunun isteği Scrapling ile tarayıcısız oynatıldı → "
                                        f"{recipe['method']} {recipe['url']} ({recipe['id_attr']}={attrs[recipe['id_attr']]}, {elapsed} sn).")
        else:
            html = ""
            recipe["failures"] = recipe.get("failures", 0) + 1
            recipes.event(store, "replay_failed", f"profil detayı {recipe['url']}")
            await log("rea", "warning", "DEĞİŞİKLİK: kayıtlı 'detay' tarifi artık çalışmıyor → REA yeniden öğrenecek.")
    if not html and rea.available():
        selector = _button_selector(btn)
        await log("rea", "running", f"Kartta profil linki yok, JS butonu var → REA butona tıklayıp gizli isteği gözlüyor ({selector}).")
        cap = await rea.click_capture(base, selector)
        if cap.ok:
            learned, tx = recipes.learn_detail(cap, attrs)
            if learned:
                store["replay"]["profile_detail"] = learned
                recipes.event(store, "learned", f"profil detayı {learned['method']} {learned['url']}", evidence_id=cap.evidence_id)
                body = "&".join(f"{k}={v}" for k, v in learned["form"] + learned["query"])
                report["recipe"]["detail"] = {"ok": True, "learned": True, "method": learned["method"], "url": learned["url"],
                                              "id_attr": learned["id_attr"], "body": body}
                await log("rea", "running", f"REA gizli isteği çözdü: {learned['method']} {learned['url']} ({body}); "
                                            f"kimlik kartın '{learned['id_attr']}' özniteliğinden okunuyor → tarif kaydedildi, "
                                            f"bu sitedeki diğer kişiler tarayıcısız çekilecek.")
                html = recipes.html_from_response(tx.json(), (tx.response_body or b"").decode("utf-8", "replace"))
            else:
                # tarif çıkmasa da tıklama sonrası DOM'da açılan pencere kullanılabilir
                html = cap.dom
        else:
            await log("rea", "warning", f"REA tıklama gözlemi başarısız: {cap.error[:120]}")
    if not html:
        return False
    sel = parse(html, base)
    text = clean(sel.get_all_text(separator=" ", ignore_tags=("script", "style")))
    _extract_profile(profile, sel, html, text, base, name)
    profile.source_url = base
    return True


async def _crawl(seeds: list[tuple[str, str]], name: str, start_url: str, log, report: dict,
                 stop: asyncio.Event | None = None):
    """Scrapling Spider ile odaklı tarama (REA, JS sayfalarında taramanın içinde devreye girer)."""
    from . import spider

    root = registrable(urlparse(start_url).hostname or "")
    scored: dict[str, float] = {}
    for url, text in seeds:
        score = _link_score(url, text, name, root)
        if score >= 2:
            scored[url] = max(scored.get(url, 0), score)
    if not scored:
        return None
    await log("crawl", "running", f"Scrapling Spider başlıyor: {len(scored)} aday link (alan adı {root}, derinlik "
                                  f"≤{CRAWL_MAX_DEPTH}, en fazla {CRAWL_MAX_PAGES} sayfa, robots.txt'ye uyar).")
    found, pages, rea_used = await spider.crawl(sorted(scored.items(), key=lambda kv: -kv[1]), name, root,
                                                CRAWL_MAX_PAGES, CRAWL_MAX_DEPTH, log, stop)
    report["crawl"] = {"pages": pages, "found_at": found[1] if found else None, "engine": "scrapling.spiders",
                       "rea_in_crawl": rea_used}
    return found


async def llm_enrich(profile: Profile, llm, log):
    """Profil sayfası metninden eksik alanları LLM ile tamamlar (kanıt: sayfa metni)."""
    if not (profile.page_text or profile.card_text) or not llm.available:
        return
    missing = [k for k in ("title", "department", "interests") if not profile.get(k)]
    if not missing:
        return
    schema = {"type": "object", "properties": {
        "title": {"type": "string"}, "department": {"type": "string"},
        "interests": {"type": "array", "items": {"type": "string"}}}, "required": ["title", "department", "interests"]}
    prompt = ("Aşağıdaki üniversite profil sayfası metninden yalnızca METİNDE AÇIKÇA GEÇEN bilgileri çıkar. "
              "Bilmiyorsan boş bırak. E-posta/telefon yazma.\n"
              f"Kişi: {profile.query_name}\nKADRO KARTI:\n{profile.card_text}\n\nPROFİL SAYFASI:\n{profile.page_text[:3000]}\n\n"
              "JSON: {\"title\": akademik unvan, \"department\": bölüm/program, \"interests\": [araştırma ilgi alanları]}")
    data = await llm.json(prompt, schema, timeout=60)
    if not data:
        return
    page = fold(profile.page_text + " " + profile.card_text)
    for key in missing:
        value = data.get(key)
        if key == "interests" and isinstance(value, list):
            value = [clean(v) for v in value if clean(v) and fold(v) in page][:10]
        elif isinstance(value, str):
            value = clean(value) if fold(value) and fold(value) in page else ""
        if value:
            profile.set(key, value, "llm", profile.source_url)
    if any(k in profile.facts and profile.facts[k].source == "llm" for k in missing):
        await log("scrape", "running", "Eksik profil alanları Gemini ile sayfa metninden tamamlandı (metinde doğrulandı).")


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)
