"""Canlı test kurumu (Hogwarts Üniversitesi · Bahadır Arslan) için statik veriyi üretir.

    python scripts/build_hogwarts_demo.py [../akademik-iz-poc-test]

Test projesinin YÖK benzeri yanıtları (veri.py'den, sunucu açmadan) app/demo/hogwarts_yok.json'a kopyalanır; Bahadır
Arslan'ın profili uygulamanın kendi YÖK okuyucusuyla (sources.yok_profile_api) bu kopyadan üretilip
app/demo/hogwarts_profile.json'a yazılır; üniversite logosu static/logos/universities/hogwarts-universitesi.png.
Ağa çıkmaz. veri.py değişince yeniden çalıştırın.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import hogwarts  # noqa: E402

TEST_URL = "https://akademik-iz-poc-test.onrender.com"


def load_test_app(path: Path):
    sys.path.insert(0, str(path))
    spec = importlib.util.spec_from_file_location("poc_test_app", path / "app.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["komutlar"].AYAR_DOSYASI = Path(tempfile.mkdtemp()) / "ayar.json"  # varsayılan ayar: YÖK "yeni", makale yok
    return mod


def snapshot(T) -> dict:
    """Test API'sinin YÖK yanıtlarından Hogwarts kopyası; kimlikler YÖK'ün gerçek kimlikleriyle çakışmasın diye
    "hogwarts-" önekiyle değiştirilir (kişinin 16 haneli authorGuidId'si aynı kalır)."""
    from fastapi.testclient import TestClient
    c = TestClient(T.app)
    V = T.V
    guid = V.GUID

    def data(path, **params):
        return c.get("/api" + path, params=params).json()["data"]

    uni = data("/university/list")["data"][0]
    row = data("/akademisyen/list", page=1, length=1)["data"][0]
    row.update(univId=hogwarts.BIRIM, fakulteId=hogwarts.FAKULTE_ID, bolumId=hogwarts.BOLUM_ID)
    out = {"university": uni, "home": f"{TEST_URL}/hogwarts",
           "faculties": [{"label": V.FAKULTE, "value": hogwarts.FAKULTE_ID}],
           "departments": [{"label": V.BOLUM, "value": hogwarts.BOLUM_ID}],
           "list_row": row}
    detail = data("/akademisyen/detay", authorGuidId=guid)
    detail.update(univId=hogwarts.BIRIM, fakulteId=hogwarts.FAKULTE_ID, bolumId=hogwarts.BOLUM_ID)
    out["/akademisyen/detay"] = detail
    for path in ("/akademisyen/ogrenim/bilgiler", "/deneyim/akademik/gorev", "/deneyim/idari/gorev", "/deneyim/universite/disi",
                 "/odul/list", "/uyelik/list", "/sanatsal/faaliyet/list", "/ders/list", "/patent/list", "/yayin/list",
                 "/surdurulebilirlik/list", "/analiz/wos-yillik-istatistik", "/analiz/yayin-tur-kapsam-dagilimi",
                 "/analiz/total-count-by-academician"):
        out[path] = data(path, authorGuidId=guid, page=1, length=1000)
    for tur in ("1", "2", "3"):
        out[f"/yayin/list?yayinAnaTurId={tur}"] = data("/yayin/list", authorGuidId=guid, yayinAnaTurId=tur)
    projects = data("/proje/list", authorGuidId=guid)
    for i, p in enumerate(projects["data"]):
        pid = f"hogwarts-proje-{i}"
        detail = data("/proje/detay", projeId=p["projeId"])
        p["projeId"] = detail["projeId"] = pid
        out[f"/proje/detay?projeId={pid}"] = detail
    out["/proje/list"] = projects
    out["/akademisyen/birlikte/calisanlar/{guid}"] = data(f"/akademisyen/birlikte/calisanlar/{guid}")
    out["/tez/yurt/ici/yonetilen/{guid}"] = data(f"/tez/yurt/ici/yonetilen/{guid}")
    return out


def _pub(i: int, rec: dict, veri_pubs: dict) -> dict:
    src = veri_pubs.get(rec["title"], {})
    kind = {"article": "Makale", "proceedings": "Bildiri", "book": "Kitap"}.get(rec["type"], "Makale")
    q = src.get("ceyrek") or ""
    return {**rec, "citations": None, "date": src.get("tarih", ""), "lang": "tr", "lang_conf": 0.9, "sources": ["yok"],
            "variants": [{"title": rec["title"], "lang": "tr", "source": "yok"}], "languages": ["tr"], "language_names": ["Türkçe"],
            "id": f"P{i}", "runs_seen": 1, "verified": False, "is_new": False, "publication_kind": kind,
            "publication_status": {"code": "unknown", "label": "Süreç bilgisi yok", "scope": "record", "evidence": "", "source": "", "url": ""},
            **({"quartile": {"q": q, "source": "Test", "year": int(src["tarih"][:4]), "journal": rec["venue"], "categories": []}} if q else {})}


async def build_profile(T) -> dict:
    from app.sources import YOK_PROFILE, yok_profile_api
    V = T.V
    got = await yok_profile_api("Bahadır Arslan", "Hogwarts Üniversitesi", YOK_PROFILE + V.GUID, lambda m: None, fast=True)
    prof, extra = got["profile"], got["extra"]
    veri_pubs = {y["baslik"]: y for y in V.YAYINLAR}
    pubs = [_pub(i, r, veri_pubs) for i, r in enumerate(sorted(got["records"], key=lambda r: -(r.get("year") or 0)), 1)]
    title = "Arş. Gör."
    one = lambda value, src="yok": {"value": value, "confidence": 0.5, "status": "tek kaynak", "sources": [src], "runs_seen": 1, "alternatives": []}  # noqa: E731
    yok_url = YOK_PROFILE + V.GUID
    profile = {
        "name": "Bahadır Arslan", "query_name": "Bahadır Arslan", "title": title, "department": "Yazılım Mühendisliği Bölümü",
        "institution": "Hogwarts Üniversitesi", "interests": prof["keywords"], "bio": V.OZGECMIS, "orcid": prof["orcid"],
        "links": {"yok": yok_url, "orcid": prof["orcid"], "institution": f"{TEST_URL}/hogwarts/akademisyen/bahadir-arslan"},
        "source_url": f"{TEST_URL}/hogwarts/akademisyen/bahadir-arslan", "listing_url": f"{TEST_URL}/hogwarts/akademik-kadro",
        "found": True, "provenance": {k: {"source": "yok", "url": yok_url} for k in ("title", "department", "institution", "interests", "bio")},
        "verification": {"title": one(title), "institution": one("Hogwarts Üniversitesi"), "orcid": one(prof["orcid"]),
                         "department": one("Yazılım Mühendisliği Bölümü"), "interests": [one(k) for k in prof["keywords"]]},
        "yok": {**extra, "area": prof["area"], "field": prof["field"], "keywords": prof["keywords"], "researcher_id": "",
                "email": V.EPOSTA, "updated": time.strftime("%Y-%m-%d")},
        "site": {"url": f"{TEST_URL}/hogwarts/akademisyen/bahadir-arslan", "photo": f"{TEST_URL}/static/bahadir.jpg", "title": title,
                 "unit_url": f"{TEST_URL}/hogwarts", "faculty": "Mühendislik Fakültesi", "department": "Yazılım Mühendisliği Bölümü"},
        "photo": extra.get("photo") or "",
    }
    return {
        "profile": profile, "publications": pubs, "raw_count": len(pubs), "unique_count": len(pubs),
        "dedup": {"doi": 0, "exact": 0, "fuzzy": 0, "cross_lang": 0, "llm_checked": 0, "raw": len(pubs), "unique": len(pubs)},
        "analysis": {"mode": "pending", "summary": "", "areas": [], "methods": [], "timeline": []},
        "paper_verification": {"previous_runs": 0, "new": 0, "removed": 0, "multi_source": 0, "verified": 0},
        "languages": {"Türkçe": len(pubs)}, "by_source": {"yok": len(pubs)},
        "recon": {"start_url": f"{TEST_URL}/hogwarts/akademik-kadro", "strategy": [], "rea": None, "crawl": {"pages": 0}, "walls": [],
                  "recipe": {"events": []}, "sources_meta": {"openalex": {"id": V.OPENALEX_AUTHOR, "display_name": "Bahadır Arslan",
                                                                          "works_count": len(pubs), "cited_by_count": 0, "h_index": 0,
                                                                          "topics": ["Web Scraping", "Software Engineering"],
                                                                          "institutions": ["Hogwarts Üniversitesi"]}}, "yok_rea": None},
        "llm": "", "summary": f"Bahadır Arslan için {len(pubs)} yayın derlendi (canlı test kurumu).", "elapsed": 0.0,
        "industry": [], "industry_v": 2,
        "input": {"url": "", "name": "Bahadır Arslan", "yok_url": yok_url, "university": "Hogwarts Üniversitesi",
                  "department": "Yazılım Mühendisliği Bölümü", "email": V.EPOSTA, "light": False, "orcid": prof["orcid"]},
        "job_id": hogwarts.JOB_ID, "chat_id": hogwarts.CHAT_ID, "created": time.strftime("%Y-%m-%d %H:%M:%S"), "demo": True,
    }


def draw_logo(path: Path) -> None:
    """Özgün arma: dört bölmeli kalkan ve H (test sitesindeki hogwarts.svg ile aynı tasarım)."""
    from PIL import Image, ImageDraw, ImageFont
    s = 4  # yumuşak kenar için büyük çizip küçült
    W, H = 240 * s, 240 * s
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shield = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(shield)
    top, left, right, bottom = 20 * s, 40 * s, 200 * s, 225 * s
    pts = [(left, top), (right, top), (right, 120 * s)]
    for t in range(0, 101):  # alt kavis
        x = right - (right - left) * t / 100
        y = 120 * s + (bottom - 120 * s) * (1 - ((x - (left + right) / 2) / ((right - left) / 2)) ** 2)
        pts.append((x, y))
    pts += [(left, 120 * s)]
    d.polygon(pts, fill=255)
    quad = Image.new("RGBA", (W, H))
    q = ImageDraw.Draw(quad)
    cx, cy = (left + right) // 2, 120 * s
    q.rectangle([0, 0, cx, cy], fill="#8b1e1e")
    q.rectangle([cx, 0, W, cy], fill="#1e5a32")
    q.rectangle([0, cy, cx, H], fill="#d4a017")
    q.rectangle([cx, cy, W, H], fill="#1f3a6e")
    img.paste(quad, (0, 0), shield)
    edge = ImageDraw.Draw(img)
    edge.line(pts + [pts[0]], fill="#c9a54c", width=8 * s, joint="curve")
    r = 42 * s
    edge.ellipse([cx - r, cy - r, cx + r, cy + r], fill="#f3e3c3", outline="#c9a54c", width=7 * s)
    try:
        font = ImageFont.truetype("georgiab.ttf", 58 * s)
    except OSError:
        font = ImageFont.load_default()
    edge.text((cx, cy + 2 * s), "H", fill="#3b2a1a", font=font, anchor="mm")
    img.resize((240, 240), Image.LANCZOS).save(path)


def main() -> None:
    test_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "akademik-iz-poc-test"
    T = load_test_app(test_dir.resolve())
    hogwarts.DIR.mkdir(parents=True, exist_ok=True)
    (hogwarts.DIR / "hogwarts_yok.json").write_text(json.dumps(snapshot(T), ensure_ascii=False, indent=1), encoding="utf-8")
    hogwarts._yok.cache_clear()
    result = asyncio.run(build_profile(T))
    (hogwarts.DIR / "hogwarts_profile.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    hogwarts._profile.cache_clear()
    draw_logo(ROOT / "static" / "logos" / "universities" / f"{hogwarts.UNI_ID}.png")
    print(f"Yazıldı: app/demo/hogwarts_yok.json, app/demo/hogwarts_profile.json ({result['unique_count']} yayın), "
          f"static/logos/universities/{hogwarts.UNI_ID}.png")


if __name__ == "__main__":
    main()
