"""Patentler: EPO Open Patent Services (Espacenet verisi; EP, WO ve TR ulusal yayınları dahil).

Ücretsiz anahtar gerekir (.env: EPO_KEY, EPO_SECRET; developers.epo.org → My Apps). Anahtar yoksa modül
kapalıdır (enabled() False) ve arayüzde patent sekmesi görünmez. EPO sınırı: ~10 arama/dk, haftada 4 GB.

Akademisyen: buluş sahibi adıyla aranır. Patentlerde ORCID olmadığı için aynı adlı başka kişiler karışabilir;
başvuru sahibi kişinin kendi kurumu (YÖK görev geçmişi dahil) ya da kendisiyse kesin, değilse "olası" sayılır.
2017 öncesi (SMK 6769'dan önce) akademisyen buluşlarında başvuru sahibi çoğunlukla akademisyenin kendisidir.
Firma: başvuru sahibi adıyla aranır.
"""
from __future__ import annotations

import asyncio
import io
import json
import re
import time

import httpx

from . import yokdir
from .config import EPO_KEY, EPO_SECRET, ROOT
from .text import fold, lower_tr, name_score, name_tokens, strip_titles

OPS = "https://ops.epo.org/3.2"
VERSION = 2  # sonuç biçimi: değişince kayıtlı profillerin patentleri yeniden alınır
TEXT_DIR = ROOT / "data" / "patents"  # açıklama metinleri (yayımlanmış belge değişmez: süresiz önbellek)
FULLTEXT = ("EP", "WO")  # OPS tam metni (açıklama) yalnız bu yayınlarda var; TR'de yalnız özet
PAGES_DIR = TEXT_DIR / "pages"  # özgün belgenin taranmış sayfaları (PNG)
DOC_ORDER = ("TR", "WO", "EP")  # özgün belge önce Türkçe yayından
_TOKEN = {"value": "", "exp": 0.0}
UNI_WORDS = {"universitesi", "university", "univ", "universite"}  # EPODOC "ÜNİVERSİTESİ"ni "UNIV" diye kısaltır


class PatentError(Exception):
    pass


def enabled() -> bool:
    return bool(EPO_KEY and EPO_SECRET)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=30)


async def _token(client) -> str:
    if _TOKEN["value"] and time.time() < _TOKEN["exp"] - 60:
        return _TOKEN["value"]
    r = await client.post(f"{OPS}/auth/accesstoken", auth=(EPO_KEY, EPO_SECRET),
                          data={"grant_type": "client_credentials"})
    if r.status_code in (400, 401, 403):
        raise PatentError("EPO anahtarı geçersiz (.env: EPO_KEY / EPO_SECRET)")
    r.raise_for_status()
    d = r.json()
    _TOKEN.update(value=d["access_token"], exp=time.time() + int(d.get("expires_in") or 1200))
    return _TOKEN["value"]


# ------------------------------------------------------------------ OPS JSON yardımcıları
def _list(x) -> list:
    return x if isinstance(x, list) else [x] if x else []


def _t(x) -> str:
    if isinstance(x, dict):
        return str(x.get("$", ""))
    if isinstance(x, list):
        return " ".join(_t(i) for i in x)
    return str(x or "")


async def _search(client, cql: str, limit: int) -> tuple[list[dict], int]:
    """Biblio araması: (exchange-document listesi, toplam yayın sayısı). Sonuç yoksa EPO 404 döner."""
    docs, total = [], 0
    for start in range(1, limit + 1, 100):
        r = await client.get(f"{OPS}/rest-services/published-data/search/biblio",
                             params={"q": cql, "Range": f"{start}-{min(start + 99, limit)}"},
                             headers={"Authorization": f"Bearer {await _token(client)}", "Accept": "application/json"})
        if r.status_code == 404:
            break
        if r.status_code in (403, 429):
            raise PatentError("EPO arama sınırı doldu (dakikada ~10 arama); biraz sonra tekrar deneyin")
        r.raise_for_status()
        res = r.json()["ops:world-patent-data"]["ops:biblio-search"]
        total = int(res.get("@total-result-count") or 0)
        for e in _list((res.get("ops:search-result") or {}).get("exchange-documents")):
            docs += _list(e.get("exchange-document"))
        if start + 99 >= min(total, limit):
            break
    return docs, total


def _parties(items: list, key: str) -> dict:
    """{"show": okunur adlar (özgün yazım), "raw": EPODOC adları ("OEZTUERK MEHMET [TR]", eşleştirme için)}."""
    out = {"original": [], "epodoc": []}
    for p in items:
        name = clean_name(_t((p.get(key) or {}).get("name")))
        fmt = p.get("@data-format", "")
        if name and fmt in out and name not in out[fmt]:
            out[fmt].append(name)
    return {"show": [re.sub(r"\s*\[[A-Z]{2}\]$", "", n) for n in out["original"] or out["epodoc"]],
            "raw": out["epodoc"] or out["original"]}


def clean_name(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip(" ,;")


def _doc(d: dict) -> dict:
    b = d.get("bibliographic-data") or {}
    ids = _list((b.get("publication-reference") or {}).get("document-id"))
    docdb = next((i for i in ids if i.get("@document-id-type") == "docdb"), ids[0] if ids else {})
    number = f"{d.get('@country') or _t(docdb.get('country'))}{d.get('@doc-number') or _t(docdb.get('doc-number'))}"
    kind = d.get("@kind") or _t(docdb.get("kind"))
    titles = {t.get("@lang", ""): _t(t) for t in _list(b.get("invention-title")) if _t(t)}
    abstracts = {("tr" if a.get("@lang") == "ol" else a.get("@lang", "")): " ".join(_t(p) for p in _list(a.get("p")))
                 for a in _list(d.get("abstract") or b.get("abstract"))}
    parties = b.get("parties") or {}
    return {"family": d.get("@family-id") or number, "number": number, "kind": kind, "date": _t(docdb.get("date")),
            "titles": titles, "abstracts": {k: v for k, v in abstracts.items() if v},
            "applicants": _parties(_list((parties.get("applicants") or {}).get("applicant")), "applicant-name"),
            "inventors": _parties(_list((parties.get("inventors") or {}).get("inventor")), "inventor-name")}


def _families(docs: list[dict]) -> list[dict]:
    """Aynı buluşun TR/EP/WO yayınları tek satırda: en erken yıl, tüm numaralar, en dolu taraf bilgisi."""
    fams: dict[str, list[dict]] = {}
    for d in map(_doc, docs):
        fams.setdefault(d["family"], []).append(d)
    out = []
    for members in fams.values():
        members.sort(key=lambda m: m["date"] or "99999999")
        richest = max(members, key=lambda m: (len(m["inventors"]["raw"]), len(m["applicants"]["raw"])))
        titles = {k: v for m in reversed(members) for k, v in m["titles"].items()}
        abstracts = {k: v for m in reversed(members) for k, v in m["abstracts"].items()}
        first = members[0]
        out.append({
            "title": titles.get("tr") or titles.get("en") or next(iter(titles.values()), "Başlıksız"),
            "title_en": titles.get("en", "") if titles.get("tr") else "",
            "abstract": abstracts.get("tr") or abstracts.get("en") or next(iter(abstracts.values()), ""),
            "year": first["date"][:4], "numbers": [f"{m['number']} {m['kind']}".strip() for m in members],
            "countries": sorted({m["number"][:2] for m in members}),
            "applicants": richest["applicants"]["show"], "inventors": richest["inventors"]["show"],
            "_raw": richest["applicants"]["raw"] + richest["inventors"]["raw"],
            "_inventors": richest["inventors"]["raw"], "_applicants": richest["applicants"]["raw"],
            "url": f"https://worldwide.espacenet.com/patent/search?q=pn%3D{first['number']}{first['kind']}"})
    return sorted(out, key=lambda f: f["year"], reverse=True)


def _public(f: dict) -> dict:
    return {k: v for k, v in f.items() if not k.startswith("_")}


# ------------------------------------------------------------------ ad eşleştirme
def _norm(name: str) -> str:
    """EPODOC adları Ö/Ü'yü OE/UE yazar ("OEZTUERK"); ülke kodu atılır. İki tarafa da uygulanır."""
    return fold(re.sub(r"\[[A-Z]{2}\]", " ", name)).replace("oe", "o").replace("ue", "u")


def same_person(a: str, b: str) -> bool:
    a, b = _norm(a), _norm(b)
    return max(name_score(a, b), name_score(b, a)) >= 0.9


async def _universities() -> list[tuple[str, set]]:
    """YÖK üniversite listesi (ad, ayırt edici kelimeler); kurum adları buna göre tek üniversiteye indirgenir."""
    try:
        async with yokdir._client() as client:
            unis = await yokdir.universities(client)
    except httpx.HTTPError:
        return []
    return [(u["name"], set(_norm(u["name"]).split()) - UNI_WORDS) for u in unis]


def _university_of(text: str, unis: list[tuple[str, set]]) -> str | None:
    """Metindeki üniversite: kelimeleri metinde bulunan en uzun ad ("Ankara Bilim", "Ankara"dan önce gelir).
    Kirli kurum adlarında da çalışır ("Social Media OSTİM Teknik Üniversitesi")."""
    words = set(_norm(text).split())
    if not words & UNI_WORDS:
        return None
    best = max((u for u in unis if u[1] and u[1] <= words), key=lambda u: len(u[1]), default=None)
    return best[0] if best else None


def _inst_match(applicants: list[str], institutions: list[str], unis: list[tuple[str, set]]) -> bool:
    mine = {_university_of(i, unis) for i in institutions if i} - {None}
    return bool(mine) and any(_university_of(a, unis) in mine for a in applicants)


def _cql_terms(field: str, name: str) -> list[str]:
    """Her ad parçası için koşul; Ö/Ü içerenlerde EPODOC yazımı (OE/UE) da denenir."""
    out = []
    for raw in strip_titles(name).split():
        plain = fold(raw)
        if len(plain) < 2:
            continue
        epodoc = fold(lower_tr(raw).replace("ö", "oe").replace("ü", "ue"))
        out.append(f"{field}={plain}" if epodoc == plain else f"({field}={plain} or {field}={epodoc})")
    return out


# ------------------------------------------------------------------ akademisyen
async def person_patents(name: str, institutions: list[str]) -> dict:
    """Buluş sahibi olarak geçtiği patentler: {"items": kesin, "possible": yalnız ad eşleşmesi, "total"}."""
    tokens = name_tokens(name)
    if len(tokens) < 2:
        return {"items": [], "possible": [], "total": 0}
    parts = strip_titles(name).split()
    # soyad + ilk ad (ikinci ad patentte yazılmamış olabilir)
    cql = " and ".join(_cql_terms("in", parts[-1]) + _cql_terms("in", parts[0]))
    async with _client() as client:
        docs, total = await _search(client, cql, 200)
    unis = await _universities()
    items, possible = [], []
    for f in _families(docs):
        if not any(same_person(name, inv) for inv in f["_inventors"]):
            continue
        turkish = "TR" in f["countries"] or any("[TR]" in x for x in f["_raw"])
        if not turkish:
            continue
        own = _inst_match(f["_applicants"], institutions, unis) or any(same_person(name, a) for a in f["_applicants"])
        (items if own else possible).append(_public(f) | {"match": "kurum" if own else "ad"})
    return {"items": items, "possible": possible, "total": total}


# ------------------------------------------------------------------ firma
async def firm_patents(names: list[str], academics: list[str]) -> dict:
    """Firmanın başvuru sahibi olduğu patentler; buluş sahipleri arasındaki bilinen akademisyenler işaretlenir."""
    seen, out, total = set(), [], 0
    async with _client() as client:
        for name in names[:3]:
            short = " ".join(name.split()[:4])
            words = [t for t in _norm(short).split() if len(t) > 1]
            if not words:
                continue
            docs, n = await _search(client, " and ".join(_cql_terms("pa", short)), 200)
            total += n
            for f in _families(docs):
                if f["url"] in seen or not any(set(words) <= set(_norm(a).split()) for a in f["_applicants"]):
                    continue
                seen.add(f["url"])
                found = sorted({a for a in academics for inv in f["_inventors"] if same_person(a, inv)})
                out.append(_public(f) | {"academics": found})
    return {"items": sorted(out, key=lambda f: f["year"], reverse=True), "total": total}


# ------------------------------------------------------------------ açıklama (isteğe bağlı, tek patent)
async def description(numbers: list[str]) -> dict:
    """Patent ailesinin açıklama metni: EP/WO yayınından (OPS tam metin). TR yayınlarında tam metin yoktur.
    Yalnız kullanıcı açınca istenir; sonuç süresiz saklanır."""
    pubs = [n.replace(" ", "") for n in numbers]
    for pub in sorted(pubs, key=lambda n: (n[:2] not in FULLTEXT, n[:2] != "WO")):
        if pub[:2] not in FULLTEXT:
            break
        m = re.fullmatch(r"([A-Z]{2})(\d+)([A-Z]\d?)", pub)
        if not m:
            continue
        path = TEXT_DIR / f"{pub}.json"
        if path.exists():
            return json.loads(path.read_text())
        async with _client() as client:
            r = await client.get(f"{OPS}/rest-services/published-data/publication/docdb/{'.'.join(m.groups())}/description",
                                 headers={"Authorization": f"Bearer {await _token(client)}", "Accept": "application/json"})
        if r.status_code == 404:
            continue
        if r.status_code in (403, 429):
            raise PatentError("EPO istek sınırı doldu; biraz sonra tekrar deneyin")
        r.raise_for_status()
        doc = (r.json()["ops:world-patent-data"].get("ftxt:fulltext-documents") or {}).get("ftxt:fulltext-document") or {}
        desc = _list(doc.get("description"))[0] if doc.get("description") else {}
        out = {"text": "\n".join(_t(p) for p in _list(desc.get("p")) if _t(p)), "lang": desc.get("@lang", "").lower(),
               "source": pub}
        TEXT_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(out, ensure_ascii=False))
        return out
    return {"text": "", "lang": "", "source": ""}


# ------------------------------------------------------------------ özgün belge (taranmış sayfalar)
def _pub_parts(pub: str) -> tuple[str, str, str] | None:
    m = re.fullmatch(r"([A-Z]{2})(\d{4,14})([A-Z]\d?)", pub.replace(" ", ""))
    return m.groups() if m else None


def _headers(token: str, accept: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": accept}


async def document(numbers: list[str]) -> dict:
    """Ailenin özgün belgesi: {"source": yayın no, "pages": sayfa sayısı}; önce TR, sonra WO/EP. Yoksa pages 0."""
    pubs = sorted({n.replace(" ", "") for n in numbers},
                  key=lambda n: DOC_ORDER.index(n[:2]) if n[:2] in DOC_ORDER else len(DOC_ORDER))
    async with _client() as client:
        for pub in pubs[:4]:
            parts = _pub_parts(pub)
            if not parts:
                continue
            path = TEXT_DIR / f"{pub}.doc.json"
            if path.exists():
                info = json.loads(path.read_text())
            else:
                r = await client.get(f"{OPS}/rest-services/published-data/publication/docdb/{'.'.join(parts)}/images",
                                     headers=_headers(await _token(client), "application/json"))
                if r.status_code in (403, 429):
                    raise PatentError("EPO istek sınırı doldu; biraz sonra tekrar deneyin")
                pages = 0
                if r.status_code == 200:
                    inquiry = r.json()["ops:world-patent-data"]["ops:document-inquiry"]
                    full = next((i for res in _list(inquiry.get("ops:inquiry-result"))
                                 for i in _list(res.get("ops:document-instance")) if i.get("@desc") == "FullDocument"), None)
                    pages = int((full or {}).get("@number-of-pages") or 0)
                elif r.status_code != 404:
                    r.raise_for_status()
                info = {"source": pub, "pages": pages}
                TEXT_DIR.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(info))
            if info["pages"]:
                return info
    return {"source": "", "pages": 0}


def _png(tiff: bytes) -> bytes:
    """Faks (CCITT) TIFF sayfa → ekrana uygun gri tonlu PNG (1240 px genişlik)."""
    from PIL import Image

    img = Image.open(io.BytesIO(tiff)).convert("L")
    img = img.resize((1240, round(img.height * 1240 / img.width)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


async def page(pub: str, n: int) -> bytes:
    """Özgün belgenin n. sayfası (PNG); süresiz saklanır."""
    parts = _pub_parts(pub)
    if not parts:
        raise PatentError("Geçersiz yayın numarası")
    path = PAGES_DIR / f"{''.join(parts)}-{n}.png"
    if path.exists():
        return path.read_bytes()
    async with _client() as client:
        r = await client.get(f"{OPS}/rest-services/published-data/images/{'/'.join(parts)}/fullimage.tiff",
                             params={"Range": str(n)}, headers=_headers(await _token(client), "image/tiff"))
    if r.status_code == 404:
        raise PatentError("Sayfa bulunamadı")
    if r.status_code in (403, 429):
        raise PatentError("EPO istek sınırı doldu; biraz sonra tekrar deneyin")
    r.raise_for_status()
    png = await asyncio.to_thread(_png, r.content)
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)
    return png
