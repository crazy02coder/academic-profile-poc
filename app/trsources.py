"""Türkiye odaklı akademik kaynaklar.

  TR Dizin (ULAKBİM)   — açık JSON arama uç noktası: ulusal dizindeki makaleler (özet, anahtar kelime,
                         atıf) ve TÜBİTAK projeleri. Yazar adıyla aranır, yazar listesi ad/ORCID ile süzülür.
  OpenAIRE Graph       — anahtarsız API. DergiPark, üniversite açık arşivleri (DSpace/handle), AVESİS,
                         Aperta ve YÖK Açık Bilim kayıtlarını toplar; DergiPark'ın arama sayfası robots.txt
                         ile kapalı olduğundan DergiPark içeriğine buradan ulaşılır.
  YÖK Ulusal Tez Merkezi — arama formu oturuma bağlı bir POST'tur. İstek REA ile gerçek tarayıcıda bir kez
                         gözlemlenir, tarif (data/recipes/tez.yok.gov.tr.json) olarak saklanır ve sonraki
                         aramalarda tarayıcısız tekrar oynatılır; tarif kırılırsa REA yeniden öğrenir.
"""
from __future__ import annotations

import asyncio
import json
import re
from collections import Counter
from urllib.parse import urlparse

import httpx

from . import rea, recipes
from .config import USER_AGENT, chromium_executable
from .sources import record
from .text import clean, name_in_text, name_tokens, title_key

TRDIZIN = "https://search.trdizin.gov.tr/api/defaultSearch/publication/"
TRDIZIN_PAGE = "https://search.trdizin.gov.tr/tr/yayin/detay/"
OPENAIRE = "https://api.openaire.eu/graph/v1/researchProducts"
TEZ = "https://tez.yok.gov.tr/UlusalTezMerkezi/"
TEZ_DOMAIN = "tez.yok.gov.tr"
PROJECT_ROLES = {"MANAGER": "Yürütücü", "RESEARCHER": "Araştırmacı", "ADVISOR": "Danışman"}  # bursiyerler hariç
TRDIZIN_TYPES = {"PAPER": "article", "PROCEEDING": "proceedings", "BOOK": "book", "BOOK_CHAPTER": "book-chapter"}


def _client(timeout: float = 25, **kw) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, follow_redirects=True,
                             headers={"User-Agent": USER_AGENT, "Accept": "application/json"}, **kw)


def _upper_tr(s: str) -> str:
    return s.replace("i", "İ").replace("ı", "I").upper()


def _same_person(name: str, orcid: str, cand_name: str, cand_orcid: str = "") -> bool:
    """ORCID varsa o karar verir; yoksa ad ve soyadların tamamı (sıradan bağımsız) birebir aynı olmalı.

    Bu kaynaklarda kurum bilgisi çoğu zaman yok: "Mesut Onur Ünlü" ile "Mesut Ünlü" gibi fazladan ad
    taşıyan adaylar ayrı kişi sayılır.
    """
    if orcid and cand_orcid:
        return cand_orcid.rsplit("/", 1)[-1] == orcid
    a, b = name_tokens(name), name_tokens(cand_name)
    return bool(a) and sorted(a) == sorted(b)


# ------------------------------------------------------------------------ TR Dizin
def _trdizin_q(q: str) -> str:
    # TR Dizin sorguyu ham JSON'a gömüyor; tırnak/parantez 400 döndürür.
    return re.sub(r'["\\{}\[\]]', " ", q).strip()


async def trdizin_search(client, q: str, limit: int = 100, page: int = 1, doc_type: str = "") -> list[dict]:
    params = {"q": _trdizin_q(q), "order": "relevance-DESC", "page": page, "limit": limit}
    if doc_type:  # ör. "PROJECT": yalnızca TÜBİTAK proje kayıtları
        params["facet-documentType"] = doc_type
    r = await client.get(TRDIZIN, params=params)
    r.raise_for_status()
    return [h["_source"] for h in (r.json().get("hits") or {}).get("hits") or []]


def _trdizin_record(s: dict) -> dict:
    abstracts = s.get("abstracts") or []
    main = next((a for a in abstracts if a.get("abstract")), abstracts[0] if abstracts else {})
    journal = s.get("journal") if isinstance(s.get("journal"), dict) else {}
    return record(
        "trdizin", source_id=str(s.get("id")), title=main.get("title") or "", year=s.get("publicationYear"),
        doi=s.get("doi") or "", venue=clean(journal.get("name") or ""),
        authors=[clean(a.get("name")) for a in sorted(s.get("authors") or [], key=lambda a: a.get("order") or 0)][:25],
        abstract=clean(main.get("abstract") or "")[:3000], url=f"{TRDIZIN_PAGE}{s.get('id')}",
        citations=s.get("orderCitationCount"), type=TRDIZIN_TYPES.get(s.get("docType"), (s.get("docType") or "").lower()),
        labels=[clean(k) for k in (main.get("keywords") or [])[:4]],
        orgs=[{"name": clean(t), "type": "trdizin"} for a in s.get("authors") or []
              for t in ((a.get("institution") or {}).get("rootTitle") or [])[:1] if t and "ÜNİVERSİTE" not in t.upper()])


async def trdizin_works(profile, log) -> tuple[list[dict], dict | None]:
    name = profile.name or profile.query_name
    orcid = profile.links.get("orcid", "")
    out, projects, seen = [], [], set()
    async with _client() as client:
        for page in (1, 2, 3):
            rows = await trdizin_search(client, name, 100, page)
            for s in rows:
                me = next((a for a in s.get("authors") or [] if _same_person(name, orcid, a.get("name", ""), a.get("orcid", ""))), None)
                if not me or s.get("id") in seen:
                    continue
                seen.add(s.get("id"))
                if s.get("docType") == "PROJECT":
                    main = (s.get("abstracts") or [{}])[0]
                    projects.append({"title": clean(main.get("title")), "year": s.get("publicationYear"),
                                     "role": PROJECT_ROLES.get(me.get("duty"), me.get("duty") or ""),
                                     "number": s.get("projectnumber") or "", "group": s.get("projectGroup") or "",
                                     "abstract": clean(main.get("abstract") or "")[:4000],
                                     "url": f"{TRDIZIN_PAGE}{s.get('id')}"})
                    continue
                out.append(_trdizin_record(s))
            if len(rows) < 100:
                break
    projects.sort(key=lambda p: -(p["year"] or 0))
    if projects:
        profile.yok.setdefault("tr_projects", projects)
    await log("publications", "running", f"TR Dizin (ULAKBİM): {len(out)} yayın, {len(projects)} TÜBİTAK projesi "
                                         f"({sum(bool(r['abstract']) for r in out)} özetli).")
    return out, {"papers": len(out), "projects": len(projects)}


# ------------------------------------------------------------------------ OpenAIRE
_HOSTS = (("dergipark.org.tr", "DergiPark"), ("avesis", "AVESİS"), ("aperta.ulakbim", "Aperta"),
          ("acikbilim.yok.gov.tr", "YÖK Açık Bilim"), ("hdl.handle.net", "Üniversite arşivi"),
          ("acikerisim", "Üniversite arşivi"), ("trdizin", "TR Dizin"), ("arxiv.org", "arXiv"), ("dblp.org", "DBLP"))


def _host_label(url: str) -> str:
    host = urlparse(url).hostname or ""
    return next((label for key, label in _HOSTS if key in host), "")


def _author_orcid(a: dict) -> str:
    pid = (a.get("pid") or {}).get("id") or {}
    return pid.get("value", "") if "orcid" in (pid.get("scheme") or "") else ""


def _openaire_record(x: dict) -> dict:
    doi = next((p["value"] for p in x.get("pids") or [] if p.get("scheme") == "doi"), "")
    urls = [u for i in x.get("instances") or [] for u in i.get("urls") or []]
    local = next((u for u in urls if _host_label(u)), "")
    container = x.get("container") or {}
    cites = ((x.get("indicators") or {}).get("citationImpact") or {}).get("citationCount")
    desc = clean(re.sub(r"<[^>]+>", " ", " ".join((x.get("descriptions") or [])[:1])))
    return record(
        "openaire", source_id=x.get("id", ""), title=x.get("mainTitle") or "", year=(x.get("publicationDate") or "")[:4],
        date=x.get("publicationDate"),
        doi=doi, venue=clean(container.get("name") or x.get("publisher") or ""),
        authors=[clean(a.get("fullName")) for a in sorted(x.get("authors") or [], key=lambda a: a.get("rank") or 99)][:25],
        abstract=desc[:3000], url=local or (urls[0] if urls else ""), citations=cites,
        type=((x.get("instances") or [{}])[0].get("type") or "").lower(),
        labels=sorted({_host_label(u) for u in urls if _host_label(u)}))


async def openaire_works(profile, log) -> tuple[list[dict], dict | None]:
    name = profile.name or profile.query_name
    orcid = profile.links.get("orcid", "")
    out, hosts = [], Counter()
    async with _client() as client:
        for page in (1, 2, 3):
            r = await client.get(OPENAIRE, params={"authorFullName": name, "pageSize": 100, "page": page,
                                                   "type": "publication"})
            if r.status_code != 200:
                break
            rows = r.json().get("results") or []
            for x in rows:
                mine = any(_same_person(name, orcid, a.get("fullName") or "", _author_orcid(a)) for a in x.get("authors") or [])
                if not mine or not x.get("mainTitle"):
                    continue
                # Açık arşivlerde tezlerin danışmanı da "yazar" listesine girer: tezde ilk yazar kişi değilse alma.
                kind = " ".join(i.get("type") or "" for i in x.get("instances") or []).lower()
                first = sorted(x.get("authors") or [], key=lambda a: a.get("rank") or 99)[:1]
                if "thesis" in kind and not (first and _same_person(name, orcid, first[0].get("fullName") or "", _author_orcid(first[0]))):
                    continue
                rec = _openaire_record(x)
                hosts.update(rec["labels"])
                out.append(rec)
            if len(rows) < 100:
                break
    detail = ", ".join(f"{k} {v}" for k, v in hosts.most_common(6))
    await log("publications", "running", f"OpenAIRE (DergiPark, üniversite arşivleri, AVESİS…): {len(out)} kayıt"
                                         f"{' · ' + detail if detail else ''}.")
    return out, {"records": len(out), "hosts": dict(hosts)}


# ------------------------------------------------------------------------ YÖK Ulusal Tez Merkezi
def _tez_cards(html: str) -> list[dict]:
    """Sonuç sayfası: kartlar (kayitno/tezno, başlık, PDF) + sayfaya gömülü referenceData (yazar, yıl, tür…)."""
    m = re.search(r"referenceData\s*=\s*(\{.*?\})\s*;", html, re.S)
    try:  # sayfadaki JS nesnesi sonda fazladan virgül bırakıyor
        ref = json.loads(re.sub(r",\s*([}\]])", r"\1", m.group(1))) if m else {}
    except ValueError:
        ref = {}
    out = []
    for card in re.finditer(r'data-index="(\d+)"\s+data-kayitno="([^"]+)"\s+data-tezno="([^"]+)"(.*?)(?=data-index="\d+"\s+data-kayitno|$)',
                            html, re.S):
        idx, kayit, tezno, body = card.groups()
        meta = (ref.get(idx) or {}).get("meta") or {}
        alt = re.search(r'card-info"\s+style="font-style:\s*italic">\s*(.*?)\s*</div>', body, re.S)
        no = re.search(r"Tez No:</strong>\s*(\d+)", body)
        pdf = re.search(r'href="(TezGoster\?key=[^"]+)"', body)
        out.append({"kayitno": kayit, "tezno": tezno, "no": no.group(1) if no else "",
                    "title": clean(meta.get("title") or ""), "alt_title": clean(re.sub(r"<[^>]+>", "", alt.group(1))) if alt else "",
                    "author": clean(meta.get("author") or ""), "year": meta.get("year") or "",
                    "type": clean(meta.get("type") or ""), "lang": clean(meta.get("lang") or ""),
                    "subject": clean(meta.get("subject") or ""), "university": clean((meta.get("yer") or "").strip(" /")),
                    "pdf": TEZ + pdf.group(1) if pdf else ""})
    return out


def _learn_tez_recipe(name: str) -> tuple[dict | None, str]:
    """REA: formu gerçek tarayıcıda doldurup gönderir, gizli POST'u tarif olarak çıkarır."""
    exe = chromium_executable()
    if not exe or not rea.available():
        return None, "REA veya Chromium yok"
    cap = rea.run_scenario_sync({
        "browser": {"mode": "launch", "executable_path": exe, "headless": True},
        "start_url": {"url": TEZ + "tarama.jsp", "query": []},
        "environment": {"locale": "tr-TR", "timezone": "Europe/Istanbul", "service_workers": "allow"},
        "actions": [
            {"step_id": "settle", "action": "wait_for_timeout", "duration_ms": 1500},
            {"step_id": "fill", "action": "fill", "timeout_ms": 8000,
             "locator": {"kind": "css", "selector": "form[name=GForm] input[name=DanismanAdSoyad]"},
             "value": {"source": "literal", "value": name}},
            {"step_id": "submit", "action": "click", "timeout_ms": 8000,
             "locator": {"kind": "css", "selector": "form[name=GForm] button.btn-search"}},
            {"step_id": "after", "action": "wait_for_timeout", "duration_ms": 3500},
        ],
        "capture": {"at_end": ["dom", "url"], "events": ["network"],
                    "network": {"request_body": True, "response_body": False, "header_values": False}},
    }, timeout=90)
    if not cap.ok:
        return None, cap.error or "REA gözlemi başarısız"
    learned = recipes.learn_replay(cap, name, "tez_search")
    return learned, cap.evidence_id


async def _tez_search(client, recipe: dict, field: str, name: str) -> list[dict] | None:
    """Tarifi tekrar oynatır. field: 'DanismanAdSoyad' (danışman) ya da 'AdSoyad' (yazar). None = tarif kırık."""
    form = {k: ("" if v == "{name}" else v) for k, v in recipe.get("form", [])}
    form[field] = name
    await client.get(TEZ + "tarama.jsp")  # oturum çerezi
    r = await client.post(recipe["url"], data=form, headers={"Referer": TEZ + "tarama.jsp"})
    if r.status_code != 200 or "BEKLENMED" in r.text.upper():
        return None  # sunucu isteği tanımadı: form/alanlar değişmiş
    return _tez_cards(r.text) if "referenceData" in r.text else []


async def _tez_detail(client, card: dict, sem) -> dict:
    async with sem:
        r = await client.get(TEZ + "tezBilgiDetay.jsp", params={"kayitNo": card["kayitno"], "tezNo": card["tezno"]})
    try:
        d = r.json()
    except ValueError:
        return card
    card["advisor"] = clean(re.sub(r"<[^>]+>", " ", d.get("danisman") or "").replace("Danışman:", ""))
    card["place"] = clean(d.get("yer") or "")
    card["abstract_tr"] = clean(d.get("trOzet") or "")[:3000]
    card["abstract_en"] = clean(d.get("enOzet") or "")[:3000]
    return card


async def tez_works(profile, log) -> tuple[list[dict], dict | None]:
    name = profile.name or profile.query_name
    upper = _upper_tr(name)
    store = recipes.load(TEZ_DOMAIN)
    recipe = store["replay"].get("tez_search")
    had_recipe = bool(recipe)
    async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        advised = await _tez_search(client, recipe, "DanismanAdSoyad", upper) if recipe else None
        if advised is None:
            if recipe:
                recipe["failures"] = recipe.get("failures", 0) + 1
                recipes.event(store, "replay_failed", f"POST {recipe['url']}")
                await log("publications", "warning", "DEĞİŞİKLİK: Tez Merkezi tarifi çalışmadı → REA formu yeniden gözlemleyecek.")
            else:
                await log("publications", "running", "YÖK Tez Merkezi: tarif yok → REA arama formunu gerçek tarayıcıda gözlemliyor.")
            learned, evidence = await asyncio.to_thread(_learn_tez_recipe, upper)
            if not learned:
                recipes.save(store)
                await log("publications", "warning", f"YÖK Tez Merkezi atlandı ({evidence}).")
                return [], None
            store["replay"]["tez_search"] = recipe = learned
            recipes.event(store, "relearned" if had_recipe else "learned", f"POST {learned['url']}", evidence_id=evidence)
            await log("publications", "running", f"REA Tez Merkezi formunun gizli isteğini çözdü: POST {learned['url']} "
                                                  "→ tarif kaydedildi, sonraki aramalar tarayıcısız.")
            advised = await _tez_search(client, recipe, "DanismanAdSoyad", upper) or []
        else:
            recipe["hits"] = recipe.get("hits", 0) + 1
            recipes.event(store, "replay_ok", f"POST {recipe['url']}")
        own = await _tez_search(client, recipe, "AdSoyad", upper) or []
        recipes.save(store)
        own = [c for c in own if _same_person(name, "", c["author"])]
        sem = asyncio.Semaphore(5)
        details = await asyncio.gather(*(_tez_detail(client, c, sem) for c in (own + advised)[:60]), return_exceptions=True)
    details = [d for d in details if isinstance(d, dict)]
    own = [d for d in details if d in own]
    # Danışman alanında kişi gerçekten geçmeli (aynı adlı başka hocanın tezleri elenir)
    advised = [d for d in details if d not in own and (not d.get("advisor") or name_in_text(name, d["advisor"]))]
    profile.yok.setdefault("tez_merkezi", {"own": own, "advised": advised})
    records = [record("tez", source_id=c["no"], title=c["title"], year=c["year"], authors=[c["author"]],
                      venue=c["university"], abstract=c.get("abstract_tr") or c.get("abstract_en") or "",
                      url=c["pdf"] or TEZ + "tarama.jsp", type="dissertation", labels=[c["type"]] if c["type"] else [])
               for c in own]
    with_abs = sum(bool(c.get("abstract_tr") or c.get("abstract_en")) for c in advised)
    await log("publications", "running", f"YÖK Tez Merkezi: kendi tezi {len(own)}, danışmanlık yaptığı {len(advised)} tez "
                                         f"({with_abs} özetli).")
    return records, {"own": len(own), "advised": len(advised)}


# ------------------------------------------------------------------------ başlıkla özet (DOI'siz yayınlar)
async def abstract_by_title(title: str, year=None) -> dict:
    """TR Dizin ve OpenAIRE'de başlığı birebir eşleşen kaydın özetini döndürür."""
    key = title_key(title)
    async with _client() as client:
        tr, oa = await asyncio.gather(trdizin_search(client, title, 10),
                                      client.get(OPENAIRE, params={"mainTitle": title, "pageSize": 10}),
                                      return_exceptions=True)
    for s in tr if isinstance(tr, list) else []:
        for a in s.get("abstracts") or []:
            if title_key(a.get("title") or "") == key and a.get("abstract"):
                return {"abstract": clean(a["abstract"]), "keywords": a.get("keywords") or [],
                        "url": f"{TRDIZIN_PAGE}{s.get('id')}", "source": "TR Dizin"}
    if isinstance(oa, httpx.Response) and oa.status_code == 200:
        for x in oa.json().get("results") or []:
            if title_key(x.get("mainTitle") or "") == key and x.get("descriptions"):
                rec = _openaire_record(x)
                return {"abstract": rec["abstract"], "keywords": [], "url": rec["url"],
                        "source": "OpenAIRE" + (f" ({rec['labels'][0]})" if rec["labels"] else "")}
    return {}


# ------------------------------------------------------------------------ konu araması
async def trdizin_topic(client, q: str, n: int) -> list[dict]:
    rows = await trdizin_search(client, q, n)
    return [{**_trdizin_record(s), "language": ""} for s in rows if s.get("docType") != "PROJECT"]


async def openaire_topic(client, q: str, n: int) -> list[dict]:
    r = await client.get(OPENAIRE, params={"search": q, "pageSize": n, "type": "publication"})
    r.raise_for_status()
    return [_openaire_record(x) for x in r.json().get("results") or [] if x.get("mainTitle")]



# ------------------------------------------------------------------------ TÜBİTAK TEYDEB (PRODİS)
# Açık Bilim kapsamında herkese açık "Tamamlanmış Projeler" sorgusu (giriş/CAPTCHA yok). Firmanın sanayi
# Ar-Ge projelerini verir; proje ekibi ve üniversite ortağı bu kayıtlarda yer almaz.
TEYDEB = "https://eteydeb.tubitak.gov.tr/teydebtamamlanmisprojeler.htm"
TEYDEB_FIELDS = {"Proje Adı": "title", "Kuruluş Adı": "firm", "Kuruluş İli": "city", "Anahtar Kelimeler": "keywords",
                 "Proje Başlama-Bitiş Tarihi": "dates", "Bilimsel Teknolojik Faaliyet Alanı": "field",
                 "Ar-Ge Çalışmalarının Yürütüleceği Sektör": "rd_sector", "Proje Çıktılarının Kullanılacağı Sektör": "out_sector",
                 "Projenin Özeti": "summary", "Projenin Amacı": "aim", "Proje Çıktılarının Teknik Özellikleri": "outputs"}


def _teydeb_rows(html: str) -> list[dict]:
    from html import unescape
    out = []
    for block in re.findall(r'id="projeBilgileri_\d+".*?</table>', html, re.S):
        row = {}
        for label, value in re.findall(r"<td><b>(.*?)</b></td>\s*<td>(.*?)</td>", block, re.S):
            key = TEYDEB_FIELDS.get(re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", label))).strip(" :"))
            if key:
                row[key] = clean(unescape(re.sub(r"<[^>]+>", " ", value)))
        if row.get("title"):
            start, _, end = (row.get("dates") or "").partition("-")
            row["year"] = int(end[-4:]) if end[-4:].isdigit() else None
            row["start"], row["end"] = start.strip(), end.strip()
            row["keywords"] = [k.strip() for k in (row.get("keywords") or "").split(",") if k.strip()]
            out.append(row)
    return out


async def teydeb_projects(firm_name: str = "", pages: int = 5, **fields) -> list[dict]:
    """TEYDEB tamamlanmış projeleri: kuruluş adıyla ya da form alanlarıyla (anahtarKelimeler=, projeAdi=…).

    Sayfa başına 10 kayıt; site yavaş olduğu için ilk sayfadan toplam okunur, kalan sayfalar paralel istenir.
    """
    params = {"submit": "Ara", **{k: _upper_tr(v) if k == "projeAdi" else v for k, v in fields.items() if v}}
    if firm_name:
        params["kurulusAdi"] = _upper_tr(firm_name)
    async with _client(timeout=60) as client:
        async def page(n: int) -> str:
            r = await client.get(TEYDEB, params={**params, "d-16544-p": n})
            r.raise_for_status()
            return r.text

        first = await page(1)
        m = re.search(r"Toplam\s*([\d.]+)\s*kay", re.sub(r"<[^>]+>", " ", first))
        total = int(m.group(1).replace(".", "")) if m else 0
        rest = await asyncio.gather(*(page(n) for n in range(2, min(pages, -(-total // 10)) + 1)))
    return [row for html in (first, *rest) for row in _teydeb_rows(html)]
