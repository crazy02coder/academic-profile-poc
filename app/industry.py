"""Sanayi ve Ar-Ge iş birlikleri: hangi akademisyen hangi firmayla çalışmış (kanıtıyla).

Kamuya açık izler toplanır ve Sanayi ve Teknoloji Bakanlığı'nın Ar-Ge / Tasarım Merkezi listesiyle
(data/arge_merkezleri.json, scripts/import_arge.py) eşleştirilir:
  * ortak yayın   — OpenAlex'te kurum türü "company" olan ortak yazar; TR Dizin'de firma adlı yazar kurumu
  * deneyim       — YÖK "Üniversite Dışı Deneyim" (YÖK'ün "Ticari (Özel)" etiketi ya da resmi listede firma)
  * proje/patent  — YÖK proje ve patent satırlarında, TR Dizin projelerinde geçen firma
Sonuç eksik olabilir ama her satır kanıta dayanır: gizli sözleşmeler ve yayına dönüşmeyen işler görünmez.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache

from .config import ROOT
from .text import clean, fold

CENTERS_PATH = ROOT / "data" / "arge_merkezleri.json"

# Firma adının hukuki ekleri: eşleştirmede yok sayılır.
LEGAL = set("""sanayi sanayii san ve tic ticaret anonim sirketi sirket as a s ltd sti limited ins insaat taahhut ithalat
ihracat pazarlama dis danismanlik musavirlik uretim imalat inc co corp company gmbh llc plc srl sa ag bv
subesi sube yerleskesi""".split())
# Tek başına firma kimliği olamayacak kadar genel kelimeler (ilk kelime bunlardansa iki kelime aranır).
GENERIC = set("""turk turkiye anadolu ege akdeniz karadeniz marmara trakya global ulusal uluslararasi yeni ileri akilli
dijital teknoloji teknolojileri teknolojik savunma enerji elektrik elektronik makine makina otomotiv kimya gida
tekstil yazilim bilisim bilgi medikal saglik ilac sistem sistemleri muhendislik endustri endustriyel tarim mimarlik
tasarim arge inovasyon grup holding plastik metal celik demir kablo cam boya ambalaj mobilya ev aletleri beyaz esya
hava uzay deniz kara otomasyon yapi beton cimento kagit seramik dokum hassas optik veri akademi ar ge proje
mekatronik robotik havacilik uydu radar enerjisi yenilenebilir gunes ruzgar petrol maden madencilik lojistik
medya iletisim finans banka sigorta yatirim ortak yonetim hizmetleri
united international general national american european turkish advanced applied smart digital research
technologies technology systems solutions industries industry engineering services group""".split())
# OpenAlex/yayınlarda geçen yabancı ya da kısa adlar → listedeki firma adının kelimeleri
ALIASES = {"turkish aerospace": "tusas", "turk havacilik ve uzay": "tusas", "turk telekom": "turk telekomunikasyon",
           "ford otosan": "ford otomotiv", "tofas": "tofas turk otomobil", "ayesas": "aydin yazilim"}
UNIVERSITY = re.compile(r"universit|üniversite|college|institute of technology|hastane|hospital|bakanl|ministry", re.I)
# Firma değil: meslek odaları, borsalar, dernek/vakıf/birlikler, yerel yönetimler
NON_FIRM = re.compile(r"\b(odas[ıi]|borsas[ıi]|derne[ğg]i|vakf[ıi]|birli[ğg]i|belediye|valili|kalk[ıi]nma ajans)", re.I)
# Proje özetinde firmanın iş birliği bağlamında anıldığını gösteren ifadeler
COOP_CUE = re.compile(r"paydaş|ortağ|ortak|iş ?birliğ|birlikte|konsorsiyum|firma|bünyesinde|partner|collaborat|cooperat", re.I)
# Markanın hemen ardından gelen bu kelimeler adın firma olarak yazıldığını gösterir ("ASELSAN A.Ş. için…")
FIRM_SUFFIX = {"a", "as", "ltd", "sti", "anonim", "sirketi", "san", "inc", "gmbh", "corp", "llc"}
# Kayıtlı sonuçlardaki iş birliği listesinin sürümü: kural değişince eski profiller yeniden hesaplanır
VERSION = 2
COMPANY_MARK = re.compile(r"\b(a\.?\s?ş\.?|a\.?\s?s\.?|ltd|şti|sti|şirket|sirket|inc\.?|gmbh|llc|corp\.?|"
                          r"sanayi ve ticaret|san\.? ve tic\.?)\b", re.I)


def _tokens(name: str) -> list[str]:
    name = re.split(r"\s[-–]\s|\(", name)[0]  # "Aselsan A.Ş. - HBT Sektör Başkanlığı (Macunköy)" → firma kısmı
    return [t for t in _words(name) if t not in LEGAL]


def _words(text: str) -> list[str]:
    return re.sub(r"[^0-9a-z]+", " ", fold(text)).split()


@lru_cache(maxsize=1)
def _index() -> tuple[dict, dict]:
    """(marka anahtarı → firma grubu, ilk kelime → marka anahtarları)."""
    if not CENTERS_PATH.exists():
        return {}, {}
    data = json.loads(CENTERS_PATH.read_text())
    cities = {fold(c["city"]) for c in data["centers"]}
    groups: dict[tuple, dict] = {}
    for c in data["centers"]:
        core = _tokens(c["name"])
        if not core:
            continue
        one = core[0]
        weak = one in GENERIC or one in cities or len(one) < 4 or one.isdigit() or not one.isalpha()
        key = tuple(core[:2]) if weak and len(core) > 1 else (one,)
        if weak and len(key) < 2:
            continue  # tek genel kelimelik ad güvenle eşleştirilemez
        # Görünen ad: markanın listedeki yazımı ("Aselsan", "Türk Traktör"); merkezler ayrıca listelenir
        brand = " ".join(re.split(r"\s[-–]\s|\(", c["name"])[0].replace(".", " ").split()[:len(key)])
        g = groups.setdefault(key, {"name": brand, "key": key, "centers": [], "cities": set(), "sectors": set(),
                                    "kinds": set(), "nexts": set()})
        g["nexts"].update(core[len(key):len(key) + 1])
        g["centers"].append(c["name"])
        g["cities"].add(c["city"])
        g["sectors"].add(c["sector"])
        g["kinds"].add(c["kind"])
    by_first: dict[str, list[tuple]] = {}
    for key in groups:
        by_first.setdefault(key[0], []).append(key)
    return groups, by_first


def match(org: str) -> dict | None:
    """Kurum/firma metnini resmi Ar-Ge/Tasarım Merkezi listesindeki firmayla eşleştirir."""
    if not org or UNIVERSITY.search(org) or NON_FIRM.search(org):
        return None
    groups, by_first = _index()
    text = " " + " ".join(_words(re.sub(r"\([^)]*\)", " ", org))) + " "  # "(Turkey)" gibi ülke ekleri atılır
    for alias, target in ALIASES.items():
        text = text.replace(f" {alias} ", f" {target} ")
    toks = text.split()
    for i, t in enumerate(toks):
        for key in by_first.get(t, []):
            if tuple(toks[i:i + len(key)]) != key:
                continue
            # Tek kelimelik marka soyadı da olabilir ("Aktaş Isı Sistemleri" ≠ "Aktaş Hava Süspansiyon"):
            # ardından gelen kelime listedekiyle aynı, genel bir kelime ya da hiç olmamalı.
            nxt = next((w for w in toks[i + len(key):] if w not in LEGAL), None)
            suffixed = i + len(key) < len(toks) and toks[i + len(key)] in FIRM_SUFFIX
            if len(key) == 1 and not suffixed and nxt and nxt not in GENERIC and nxt not in groups[key]["nexts"]:
                continue
            return groups[key]
    return None


def _capitalized(part: str, g: dict) -> bool:
    """Firma adı metinde özel ad olarak yazılmış mı ("ASELSAN", "Aselsan"; "bant genişliği" değil)."""
    firsts = {g["key"][0]} | {alias.split()[0] for alias, target in ALIASES.items() if match(target) is g}
    return any(w[0].isupper() and fold(w) in firsts for w in re.findall(r"\w+", part))


def mentions(text: str) -> list[tuple[dict, str]]:
    """Proje özetinde iş birliği ifadesiyle anılan resmi listedeki firmalar: [(firma, alıntı cümle)].

    "proje paydaşlarından ASELSAN…", "Türk ortak Aselsan ile yakın çalışarak…" gibi cümleler sayılır;
    firmanın yalnızca anıldığı ("sonuçlar Arçelik'in sonuçlarıyla tutarlı") cümleler sayılmaz.
    """
    out, seen = [], set()
    for sent in re.split(r"(?<=[.!?])\s+(?=[A-ZÇĞİÖŞÜ])", clean(text)):
        if not COOP_CUE.search(sent):
            continue
        for part in re.split(r"[,;:()]", sent):
            # "Özyeğin Üniversitesi'nin … Türk ortak Aselsan ile": üniversite adı atılır, firma aranır
            g = match(re.sub(r"(?i)(\S+\s+)?\S*niversit\S*", " ", part))
            if g and g["name"] not in seen and _capitalized(part, g):
                seen.add(g["name"])
                out.append((g, sent if len(sent) <= 320 else sent[:317] + "…"))
    return out


def centers_info() -> dict:
    if not CENTERS_PATH.exists():
        return {"available": False}
    data = json.loads(CENTERS_PATH.read_text())
    return {"available": True, "count": len(data["centers"]), "imported": data.get("imported"), "source": data.get("source")}


def _row_text(row: dict) -> str:
    return clean(" · ".join(str(v) for k, v in row.items() if v and k not in ("url", "group", "labels")
                            and not isinstance(v, (list, dict))))


def collaborations(papers: list[dict], profile: dict) -> list[dict]:
    found: dict[str, dict] = {}

    def add(org: str, kind: str, text: str, pub: str = "", force: bool = False):
        org = clean(org)
        if not org or NON_FIRM.search(org):
            return
        official = match(org)
        if not official and not force and not COMPANY_MARK.search(org):
            return
        key = "m:" + official["name"] if official else "o:" + " ".join(_tokens(org))
        entry = found.setdefault(key, {
            "name": official["name"] if official else org, "official": bool(official), "evidence": [],
            "kinds": sorted(official["kinds"]) if official else [], "cities": sorted(official["cities"]) if official else [],
            "sectors": sorted(official["sectors"]) if official else [], "centers": len(official["centers"]) if official else 0})
        if not any(e["type"] == kind and e["text"] == text and e.get("pub") == pub for e in entry["evidence"]):
            entry["evidence"].append({"type": kind, "text": text, "pub": pub, "org": org})

    for p in papers:
        for o in p.get("orgs") or []:
            # OpenAlex "company" türü kesin firmadır; TR Dizin kurum adı ancak resmi listede ya da firma ekiyle sayılır
            add(o.get("name", ""), "Ortak yayın", f"{p.get('year') or '?'} · {p['title']}", p.get("id", ""),
                force=o.get("type") == "company")
    yok = profile.get("yok") or {}
    sec = yok.get("sections") or {}
    for row in sec.get("experience") or []:
        labels = " ".join(row.get("labels") or [])
        add(row.get("title", ""), "Üniversite dışı deneyim", " · ".join(x for x in (labels, row.get("detail")) if x),
            force="Ticari" in labels or "Özel" in labels)
    # Serbest metinde ("Bant genişliği", "Nokta bulutu") sıradan kelimeler firma adına benzer: yalnızca
    # metinde firma eki (A.Ş., Ltd. Şti.…) geçen proje/patent satırları eşleştirilir.
    for key, kind in (("projects", "Proje"), ("patents", "Patent")):
        for row in sec.get(key) or []:
            text = _row_text(row)
            for part in re.split(r"[;,·|]", text):
                if COMPANY_MARK.search(part) and (official := match(part)):
                    add(official["name"], kind, text)
    # TÜBİTAK (ARDEB) projeleri: hoca proje ekibinde, firma özette iş birliği ifadesiyle geçiyor
    for pr in yok.get("tr_projects") or []:
        for g, sent in mentions(f"{pr.get('title', '')}. {pr.get('abstract', '')}"):
            add(g["name"], "TÜBİTAK projesi", f"{pr.get('year') or '?'} · {pr.get('title')} "
                f"({pr.get('role') or 'ekipte'}{', ' + pr['group'] if pr.get('group') else ''}) — “{sent}”")
    out = list(found.values())
    for e in out:
        e["pubs"] = sorted({ev["pub"] for ev in e["evidence"] if ev["pub"]}, key=lambda x: int(x[1:]) if x[1:].isdigit() else 0)
    return sorted(out, key=lambda e: (not e["official"], -len(e["evidence"]), e["name"]))
