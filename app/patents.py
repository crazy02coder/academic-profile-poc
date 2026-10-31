"""Patentler: EPO Open Patent Services (Espacenet verisi; EP, WO ve TR ulusal yayınları dahil).

Ücretsiz anahtar gerekir (.env: EPO_KEY, EPO_SECRET; developers.epo.org → My Apps). Anahtar yoksa modül
kapalıdır (enabled() False) ve arayüzde patent sekmesi görünmez. EPO sınırı: ~10 arama/dk, haftada 4 GB.

Akademisyen: buluş sahibi adıyla aranır. Patentlerde ORCID olmadığı için aynı adlı başka kişiler karışabilir;
başvuru sahibi kişinin kendi kurumu (YÖK görev geçmişi dahil) ya da kendisiyse kesin, değilse "olası" sayılır.
2017 öncesi (SMK 6769'dan önce) akademisyen buluşlarında başvuru sahibi çoğunlukla akademisyenin kendisidir.
Firma: başvuru sahibi adıyla aranır.
"""
from __future__ import annotations

import re
import time

import httpx

from . import yokdir
from .config import EPO_KEY, EPO_SECRET
from .text import fold, lower_tr, name_score, name_tokens, strip_titles

OPS = "https://ops.epo.org/3.2"
VERSION = 1  # sonuç biçimi: değişince kayıtlı profillerin patentleri yeniden alınır
_TOKEN = {"value": "", "exp": 0.0}


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
    abstracts = {a.get("@lang", ""): " ".join(_t(p) for p in _list(a.get("p"))) for a in _list(b.get("abstract"))}
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
    return [(u["name"], set(_norm(u["name"]).split()) - {"universitesi", "university"}) for u in unis]


def _university_of(text: str, unis: list[tuple[str, set]]) -> str | None:
    """Metindeki üniversite: kelimeleri metinde bulunan en uzun ad ("Ankara Bilim", "Ankara"dan önce gelir).
    Kirli kurum adlarında da çalışır ("Social Media OSTİM Teknik Üniversitesi")."""
    words = set(_norm(text).split())
    if "universitesi" not in words and "university" not in words:
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
