"""REA tarifleri (site recipes) ve değişiklik algılama.

Fikir: REA bir siteyi gözlemlediğinde "veri hangi istekten geliyor"u öğrenir.
Bu bilgi alan adı başına bir TARİF olarak saklanır:
  * replay   — REA'nın yakaladığı istek (GET/POST, gövde), içindeki ad parametresi
               {name} şablonuna çevrilir; sonraki çalıştırmalarda Scrapling bunu
               tarayıcı açmadan (veya stealth bağlamında page.request ile) tekrar oynatır.
  * pages    — sayfa başına yapısal parmak izi (DOM iskeleti + API uç noktaları) ve
               kişinin bulunduğu liste/profil URL'leri.
  * events   — öğrenme, yeniden öğrenme, drift (yapı değişikliği), tekrar oynatma
               başarısı/başarısızlığı geçmişi.

Değişiklik algılama: yeni parmak izi saklanan ile Jaccard benzerliğiyle kıyaslanır.
Benzerlik eşiğin altındaysa "drift" kaydedilir ve REA yeniden öğrenmeye gönderilir;
eşiğin üstündeyse REA atlanır ve Scrapling hızlı yolu kullanılır.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qsl, quote_plus, urlencode, urlparse, urlunparse

from .config import ROOT
from .text import fold, name_in_text

RECIPES_DIR = ROOT / "data" / "recipes"
ADAPTIVE_DB = ROOT / "data" / "scrapling_adaptive.db"
DRIFT_THRESHOLD = 0.80  # bu benzerliğin altı = yapı değişti


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _path(domain: str) -> Path:
    return RECIPES_DIR / f"{re.sub(r'[^a-z0-9.-]', '_', domain.lower())}.json"


def load(domain: str) -> dict:
    p = _path(domain)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except ValueError:
            pass
    return {"domain": domain, "replay": {}, "pages": {}, "people": {}, "events": []}


def save(store: dict):
    RECIPES_DIR.mkdir(parents=True, exist_ok=True)
    store["events"] = store["events"][-200:]
    _path(store["domain"]).write_text(json.dumps(store, ensure_ascii=False, indent=1))


def event(store: dict, kind: str, detail: str, **extra):
    store["events"].append({"at": _now(), "kind": kind, "detail": detail, **extra})


def all_stores() -> list[dict]:
    if not RECIPES_DIR.exists():
        return []
    out = []
    for p in sorted(RECIPES_DIR.glob("*.json")):
        try:
            out.append(json.loads(p.read_text()))
        except ValueError:
            continue
    return out


# ------------------------------------------------------------------ parmak izi
def dom_skeleton(sel) -> list[str]:
    """Metinden bağımsız yapı: en sık 300 'etiket.sınıf' imzası."""
    sigs = Counter()
    try:
        for el in sel.css("body *"):
            if el.tag in ("script", "style", "noscript", "svg", "path"):
                continue
            cls = ".".join(sorted(c for c in (el.attrib.get("class") or "").split() if not re.search(r"\d{3,}", c))[:3])
            sigs[f"{el.tag}.{cls}" if cls else el.tag] += 1
    except Exception:  # noqa: BLE001
        return []
    return [s for s, _ in sigs.most_common(300)]


def api_shape(capture) -> list[str]:
    """REA Evidence'tan uç nokta imzaları: METHOD host/path (+ JSON üst anahtarları)."""
    out = []
    for tx in capture.api_calls + [t for t in capture.documents if t.method == "POST"]:
        u = urlparse(tx.url)
        path = re.sub(r"/\d+", "/:id", u.path)
        sig = f"{tx.method} {u.netloc}{path}"
        data = tx.json()
        if isinstance(data, dict):
            sig += " {" + ",".join(sorted(data.keys())[:12]) + "}"
        elif isinstance(data, list) and data and isinstance(data[0], dict):
            sig += " [{" + ",".join(sorted(data[0].keys())[:12]) + "}]"
        out.append(sig)
    return sorted(set(out))


def jaccard(a: list[str], b: list[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / max(1, len(sa | sb))


def page_key(url: str) -> str:
    u = urlparse(url)
    return f"{u.netloc}{u.path.rstrip('/') or '/'}"


def check_page(store: dict, url: str, skeleton: list[str], api: list[str] | None = None) -> dict:
    """Saklı parmak iziyle kıyaslar, sonucu döndürür (kaydetmez)."""
    prev = store["pages"].get(page_key(url))
    if not prev:
        return {"known": False}
    dom_sim = jaccard(prev.get("skeleton", []), skeleton)
    api_sim = jaccard(prev.get("api", []), api) if api is not None and prev.get("api") is not None else None
    sims = [dom_sim] + ([api_sim] if api_sim is not None else [])
    sim = min(sims)
    return {"known": True, "dom_similarity": round(dom_sim, 3), "api_similarity": api_sim if api_sim is None else round(api_sim, 3),
            "similarity": round(sim, 3), "drift": sim < DRIFT_THRESHOLD, "learned_at": prev.get("learned_at"),
            "content_origin": prev.get("content_origin")}


def remember_page(store: dict, url: str, skeleton: list[str], api: list[str] | None, content_origin: str = "",
                  evidence_id: str = ""):
    key = page_key(url)
    prev = store["pages"].get(key, {})
    store["pages"][key] = {
        "url": url, "skeleton": skeleton, "api": api if api is not None else prev.get("api"),
        "content_origin": content_origin or prev.get("content_origin", ""),
        "evidence_id": evidence_id or prev.get("evidence_id", ""),
        "learned_at": _now() if api is not None else prev.get("learned_at", _now()),
        "checked_at": _now(), "checks": prev.get("checks", 0) + 1,
        "hash": hashlib.sha1("|".join(skeleton).encode()).hexdigest()[:12],
    }


# --------------------------------------------------------------- tekrar oynatma
def _template_value(value: str, name: str) -> str | None:
    """Parametre değeri aranan adı içeriyorsa {name} şablonuna çevrilir."""
    if name_in_text(name, value):
        return "{name}"
    return None


def learn_replay(capture, name: str, purpose: str) -> dict | None:
    """REA Evidence içinden adın gönderildiği isteği bulup şablonlaştırır.

    Öncelik: JSON dönen XHR/fetch > form POST (document). Ad, sorgu parametresinde
    veya gövdede geçmelidir; geçmiyorsa istek kişiye özgü değildir ve tarif olmaz.
    """
    candidates = [t for t in capture.api_calls if t.json() is not None] + \
                 [t for t in capture.documents if t.method == "POST"]
    for tx in candidates:
        u = urlparse(tx.url)
        query = parse_qsl(u.query, keep_blank_values=True)
        body = parse_qsl(tx.request_body or "", keep_blank_values=True) if tx.request_body and "=" in tx.request_body else []
        q_tpl = [(k, _template_value(v, name) or v) for k, v in query]
        b_tpl = [(k, _template_value(v, name) or v) for k, v in body]
        json_body = None
        if tx.request_body and tx.request_body.strip().startswith("{"):
            try:
                json_body = json.loads(tx.request_body)
            except ValueError:
                json_body = None
            if json_body is not None:
                json_body = {k: ("{name}" if isinstance(v, str) and name_in_text(name, v) else v) for k, v in json_body.items()}
        templated = any(v == "{name}" for _, v in q_tpl + b_tpl) or \
            (json_body is not None and "{name}" in json_body.values())
        if not templated:
            continue
        return {
            "purpose": purpose, "method": tx.method, "resource_type": tx.resource_type,
            "url": urlunparse(u._replace(query="")), "query": q_tpl, "form": b_tpl, "json": json_body,
            "returns": "json" if tx.json() is not None else "html",
            "learned_at": _now(), "evidence_id": capture.evidence_id, "hits": 0, "failures": 0,
        }
    return None


def render_replay(recipe: dict, name: str, variables: dict | None = None) -> tuple[str, str, dict | None, dict | None]:
    """(method, url, form, json) — {name} gerçek adla, {id} karttan okunan kimlikle doldurulur."""
    values = {"{name}": name, **{"{" + k + "}": str(v) for k, v in (variables or {}).items()}}

    def fill(v):
        return values.get(v, v) if isinstance(v, str) else v

    query = [(k, fill(v)) for k, v in recipe.get("query", [])]
    url = recipe["url"] + (("?" + urlencode(query, quote_via=quote_plus)) if query else "")
    form = {k: fill(v) for k, v in recipe.get("form", [])} or None
    js = {k: fill(v) for k, v in recipe["json"].items()} if recipe.get("json") else None
    return recipe["method"], url, form, js


async def replay_static(recipe: dict, name: str, variables: dict | None = None, verify=None):
    """Scrapling AsyncFetcher ile tarayıcısız tekrar oynatma (duvarsız siteler için)."""
    from scrapling.fetchers import AsyncFetcher

    from .net import TR_HEADERS, augmented_bundle

    method, url, form, js = render_replay(recipe, name, variables)
    headers = {**TR_HEADERS, **({"X-Requested-With": "XMLHttpRequest"} if recipe.get("resource_type") in ("xhr", "fetch") else {})}
    kwargs = dict(impersonate="chrome", stealthy_headers=True, timeout=20, retries=1, headers=headers)
    bundle = verify or augmented_bundle()
    if bundle:
        kwargs["verify"] = bundle
    if method == "POST":
        if js is not None:
            kwargs["json"] = js
        elif form:
            kwargs["data"] = form
        return await AsyncFetcher.post(url, **kwargs)
    return await AsyncFetcher.get(url, **kwargs)


def replay_in_browser(page, recipe: dict, name: str) -> dict:
    """Stealth tarayıcı bağlamında (çerezler/oturum korunarak) page.request ile tekrar oynatır.

    Playwright APIRequestContext kullanılır: sayfa gezintisi, render ve kaynak yükleme yok.
    """
    method, url, form, js = render_replay(recipe, name)
    started = time.time()
    if method == "POST":
        resp = page.request.post(url, data=js) if js is not None else page.request.post(url, form=form or {})
    else:
        resp = page.request.get(url)
    return {"status": resp.status, "url": resp.url, "text": resp.text(), "elapsed": round(time.time() - started, 2)}


def learn_detail(capture, attrs: dict) -> tuple[dict | None, object]:
    """'Detaylı bilgi' butonu tıklandığında giden XHR/fetch isteğini tarif yapar.

    Butonun özniteliklerinden (data-id, data-personel, href…) birinin değeri istek
    parametresinde geçiyorsa o parametre {id} şablonuna çevrilir ve hangi öznitelikten
    okunacağı (`id_attr`) kaydedilir. Böylece aynı sitedeki BAŞKA kişiler için de
    kartın butonundan kimlik okunup istek tarayıcısız tekrar edilir.
    """
    values = {v: k for k, v in attrs.items() if isinstance(v, str) and v.strip() and len(v) <= 64
              and k not in ("class", "style", "href", "title", "role", "target")}
    for tx in capture.api_calls:
        if tx.response_body is None or tx.status not in (200, None):
            continue
        u = urlparse(tx.url)
        query = parse_qsl(u.query, keep_blank_values=True)
        body = parse_qsl(tx.request_body or "", keep_blank_values=True) if tx.request_body and "=" in (tx.request_body or "") else []
        id_attr = None

        def tpl(pairs):
            nonlocal id_attr
            out = []
            for k, v in pairs:
                if v in values and id_attr is None:
                    id_attr = values[v]
                    out.append((k, "{id}"))
                else:
                    out.append((k, v))
            return out

        q_tpl, b_tpl = tpl(query), tpl(body)
        json_body = None
        if id_attr is None and tx.request_body and tx.request_body.strip().startswith("{"):
            try:
                jb = json.loads(tx.request_body)
                for k, v in jb.items():
                    if str(v) in values:
                        id_attr = values[str(v)]
                        jb[k] = "{id}"
                        json_body = jb
                        break
            except ValueError:
                pass
        if id_attr is None:
            continue
        return ({"purpose": "profile_detail", "method": tx.method, "resource_type": tx.resource_type,
                 "url": urlunparse(u._replace(query="")), "query": q_tpl, "form": b_tpl, "json": json_body,
                 "id_attr": id_attr, "returns": "json" if tx.json() is not None else "html",
                 "learned_at": _now(), "evidence_id": capture.evidence_id, "hits": 0, "failures": 0}, tx)
    return None, None


def html_from_response(data, raw: str = "") -> str:
    """JSON içindeki en uzun HTML parçasını (modal içerikleri) veya ham HTML'i döndürür."""
    best = ""

    def walk(x):
        nonlocal best
        if isinstance(x, str) and "<" in x and len(x) > len(best):
            best = x
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    if data is not None:
        walk(data)
    return best or raw


def person_key(name: str) -> str:
    return fold(name).replace(" ", "-")
