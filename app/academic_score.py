"""Doçentlik ve akademik teşvik puan tahmini: kayıtlı profildeki yayın, çeyrek, tez ve ders verisinden.

Puan tablosu app/criteria/akademik_puan.json dosyasındadır ve taslaktır; resmî ÜAK tablosuyla doğrulanmalıdır.
"""
from __future__ import annotations
import json
import re
from datetime import date
from pathlib import Path

CRITERIA = Path(__file__).parent / "criteria" / "akademik_puan.json"
CATS = {"q1": "SCI/SSCI/AHCI · Q1", "q2": "SCI/SSCI/AHCI · Q2", "q3": "SCI/SSCI/AHCI · Q3", "q4": "SCI/SSCI/AHCI · Q4",
        "sci_noq": "SCI/SSCI/AHCI · çeyrek bilinmiyor", "intl_other": "ESCI / Scopus / alan endeksi", "intl_hakemli": "Diğer uluslararası hakemli",
        "trdizin": "TR Dizin", "ulusal_other": "Diğer ulusal hakemli", "book_intl": "Uluslararası kitap", "book_nat": "Ulusal kitap",
        "chapter_intl": "Uluslararası kitap bölümü", "chapter_nat": "Ulusal kitap bölümü", "conf_intl": "Uluslararası bildiri", "conf_nat": "Ulusal bildiri"}


def criteria() -> dict:
    return json.loads(CRITERIA.read_text(encoding="utf-8"))


def _low(v) -> str:
    return str(v or "").replace("İ", "i").replace("I", "ı").lower()


def _year(v) -> int:
    m = re.search(r"(19|20)\d\d", str(v or ""))
    return int(m[0]) if m else 0


def classify(p: dict) -> str:
    kind = _low(p.get("publication_kind") or p.get("type"))
    labels = _low(" | ".join(map(str, p.get("labels") or [])))
    intl = "uluslararası" in labels or (p.get("lang") and p.get("lang") != "tr")
    if "tez" in kind or "thesis" in kind or "dissert" in kind or "ön baskı" in kind or "preprint" in kind:
        return ""
    if "bildiri" in kind or "proceed" in kind or "conference" in kind:
        return "conf_intl" if "uluslararası" in labels else "conf_nat"
    if "bölüm" in kind or "chapter" in kind:
        return "chapter_intl" if intl else "chapter_nat"
    if "kitap" in kind or kind == "book":
        return "book_intl" if intl else "book_nat"
    if "makale" in kind or "article" in kind:
        if re.search(r"\bsci\b|sci-exp|ssci|ahci|a&hci|science citation|arts & humanities", labels) or p.get("wos"):
            q = _low((p.get("quartile") or {}).get("q") if isinstance(p.get("quartile"), dict) else "")
            return q if q in ("q1", "q2", "q3", "q4") else "sci_noq"
        if isinstance(p.get("quartile"), dict) and _low(p["quartile"].get("q")) in ("q1", "q2", "q3", "q4") and "tr dizin" not in labels:
            return _low(p["quartile"]["q"])  # SJR/JCR çeyreği olan dergi
        if re.search(r"esci|scopus|emerging|alan endeks", labels):
            return "intl_other"
        if "tr dizin" in labels or "ulakbim" in labels:
            return "trdizin"
        return "intl_hakemli" if "uluslararası" in labels else "ulusal_other"
    return ""


def _share(n: int, table: dict) -> float:
    n = max(1, n)
    return float(table.get(str(n), 1 / n))


def _rows(result: dict, c: dict) -> list[dict]:
    out = []
    for p in result.get("publications") or []:
        cat = classify(p)
        if not cat or not p.get("title"):
            continue
        n = len(p.get("authors") or []) or 1
        try:
            cites = int(p.get("citations") or 0)
        except (TypeError, ValueError):
            cites = 0
        out.append({"id": p.get("id"), "title": p["title"], "year": _year(p.get("year")), "venue": p.get("venue") or "", "cat": cat, "cat_label": CATS[cat],
                    "authors": n, "share": round(_share(n, c["yazar_payi"]), 3), "citations": cites})
    return out


def _phd_year(result: dict) -> int:
    yok = (result.get("profile") or {}).get("yok") or {}
    years = [_year(str(e.get("period") or "").split("-")[-1]) for e in yok.get("education") or [] if "doktora" in _low(e.get("role")) or "tıpta uzmanlık" in _low(e.get("role"))]
    return max([y for y in years if y], default=0)


def _theses(result: dict) -> dict:
    yok = (result.get("profile") or {}).get("yok") or {}
    rows = (yok.get("sections") or {}).get("theses") or []
    out = {"doktora": 0, "yuksek_lisans": 0}
    for r in rows:
        text = _low(" ".join([str(r.get("group") or ""), *map(str, r.get("labels") or [])]))
        if "devam" in text:
            continue
        if "doktora" in text or "sanatta yeterlik" in text or "uzmanlık" in text:
            out["doktora"] += 1
        elif "yüksek" in text:
            out["yuksek_lisans"] += 1
    if not rows:
        for t in (yok.get("tez_merkezi") or {}).get("advised") or []:
            out["doktora" if "doktora" in _low(t.get("type") or t.get("kind") or t.get("title")) else "yuksek_lisans"] += 1
    return out


def _courses(result: dict) -> int:
    yok = (result.get("profile") or {}).get("yok") or {}
    return len({(r.get("Dönem"), r.get("Ders Adı")) for r in (yok.get("sections") or {}).get("courses") or [] if r.get("Ders Adı")})


def docentlik(result: dict) -> dict:
    c = criteria(); d = c["docentlik"]; K = d["kalemler"]
    rows, phd = _rows(result, c), _phd_year(result)
    where = {}
    for key in ("makale_intl", "makale_ulusal", "kitap", "toplanti"):
        for cat in K[key]["puan"]:
            where[cat] = key
    items = {k: {"key": k, "label": v["ad"], "points": 0.0, "after": 0.0, "count": 0, "cap": v.get("tavan"), "min": v.get("asgari"), "rows": []} for k, v in K.items()}
    for r in rows:
        key = where.get(r["cat"])
        if not key:
            continue
        r["points"] = round(K[key]["puan"][r["cat"]] * r["share"], 2)
        r["after_phd"] = not phd or r["year"] >= phd
        it = items[key]; it["points"] += r["points"]; it["count"] += 1; it["rows"].append(r)
        if r["after_phd"]:
            it["after"] += r["points"]
    cites = sum(r["citations"] for r in rows)
    items["atif"].update(points=cites * K["atif"]["atif_basina"], count=cites, note=f"{cites} atıf (kaynaklardaki toplam)")
    th = _theses(result)
    items["tez"].update(points=sum(th[k] * K["tez"]["puan"][k] for k in th), count=sum(th.values()), note=f"{th['doktora']} doktora · {th['yuksek_lisans']} yüksek lisans (tamamlanan)")
    courses = _courses(result)
    items["egitim"].update(points=courses * K["egitim"]["ders_basina"], count=courses, note=f"{courses} dönemlik ders")
    for it in items.values():
        raw = it["points"]
        if it["cap"] is not None and raw > it["cap"]:
            it["points"] = it["cap"]; it["capped_from"] = round(raw, 1)
            it["after"] = min(it["after"], it["cap"])
        if it["key"] in ("atif", "tez", "egitim"):
            it["after"] = it["points"]
        it["points"] = round(it["points"], 1); it["after"] = round(it["after"], 1)
        it["rows"] = sorted(it["rows"], key=lambda r: (-r["points"], -r["year"]))
        it["ok"] = it["min"] is None or it["points"] >= it["min"]
    total = round(sum(i["points"] for i in items.values()), 1); after = round(sum(i["after"] for i in items.values()), 1)
    checks = [{"label": f"Toplam en az {d['toplam_asgari']} puan", "have": total, "need": d["toplam_asgari"], "ok": total >= d["toplam_asgari"]},
              {"label": f"Doktora sonrası en az {d['doktora_sonrasi_asgari']} puan", "have": after, "need": d["doktora_sonrasi_asgari"], "ok": after >= d["doktora_sonrasi_asgari"]}]
    checks += [{"label": f"{i['label']}: en az {i['min']} puan", "have": i["points"], "need": i["min"], "ok": i["ok"]} for i in items.values() if i["min"] is not None]
    noq = sum(1 for r in rows if r["cat"] == "sci_noq")
    notes = []
    if not phd:
        notes.append("Doktora yılı YÖK öğrenim bilgisinde bulunamadı; tüm yayınlar doktora sonrası sayıldı.")
    if noq:
        notes.append(f"{noq} SCI/SSCI makalesinin dergi çeyreği bulunamadı; en düşük çeyrek puanıyla sayıldı.")
    notes.append("Tezden üretilmiş yayın, başlıca yazar, proje ve patent kalemleri otomatik ayırt edilemiyor; elle ekle.")
    return {"total": total, "after_phd": after, "phd_year": phd, "need": d["toplam_asgari"], "need_after": d["doktora_sonrasi_asgari"],
            "items": list(items.values()), "checks": checks, "missing": [x for x in checks if not x["ok"]], "notes": notes,
            "verified": bool(c.get("dogrulandi")), "criteria_note": c.get("_not", "")}


def tesvik(result: dict, year: int | None = None) -> dict:
    c = criteria(); t = c["tesvik"]; K = t["kalemler"]
    year = year or date.today().year - 1
    items = {k: {"key": k, "label": v["ad"], "points": 0.0, "count": 0, "cap": v["tavan"], "rows": []} for k, v in K.items()}
    for r in _rows(result, c):
        if r["year"] != year:
            continue
        sci = r["cat"] in t["q_katsayi"]
        key = "teblig" if r["cat"].startswith("conf") else "yayin"
        base = K[key]["puan"].get("sci" if sci else r["cat"])
        if base is None:
            continue
        r["points"] = round(base * (t["q_katsayi"][r["cat"]] if sci else 1) * r["share"], 2)
        items[key]["points"] += r["points"]; items[key]["count"] += 1; items[key]["rows"].append(r)
    for it in items.values():
        if it["points"] > it["cap"]:
            it["capped_from"] = round(it["points"], 1); it["points"] = it["cap"]
        it["points"] = round(it["points"], 1); it["rows"].sort(key=lambda r: -r["points"])
    total = min(t["tavan"], round(sum(i["points"] for i in items.values()), 1))
    return {"year": year, "total": total, "need": t["asgari"], "max": t["tavan"], "ok": total >= t["asgari"], "items": list(items.values()),
            "notes": ["Yalnız yayın ve tebliğ kalemleri hesaplanır; proje, atıf, patent, ödül ve sergi puanlarını elle ekle.",
                      "Teşvikte yayının ilgili takvim yılında yayımlanmış olması gerekir; yıl bilgisi kaynak kaydından alındı."]}
