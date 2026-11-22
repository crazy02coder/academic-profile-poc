"""Canlı test kaynağı (akademik-iz-poc-test): jüri gösterimi için YÖK Akademik ve OpenAlex benzeri test API'si.

Ayarlar → Sistem'den adresi girilince:
  * Veri tarifleri'ne "Test API · kadro listesi" eklenir (YÖK ayrıştırıcısıyla okunur; test API'sinde yanıt biçimi
    değiştirilince "Kontrol et" farkı bulur, "Tarifi güncelle" yeni eşlemeyi öğrenir).
  * "Test sitesini REA'ya öğret" Hogwarts kadro sayfasını REA site tariflerine ekler; sayfa yapısı değiştirilince
    "Değişiklikleri tara" farkı bulur ve REA tarifi yeniden öğrenir.
  * Yayın takibine test akademisyeni (Bahadır Arslan) eklenebilir; test API'sindeki "Yeni yayın" bir dakika içinde
    bildirime dönüşür.
"""
from __future__ import annotations

from urllib.parse import urlparse

import httpx

from . import ai_settings

TEST_PERSON = {"name": "Bahadır Arslan", "author_id": "A9990000001", "orcid": "0009-0000-0000-0001",
               "institution": "Hogwarts Üniversitesi", "yok_name": "BAHADIR ARSLAN"}
SITE_PAGE = "/hogwarts/akademik-kadro"
DEFAULT_URL = "https://akademik-iz-poc-test.onrender.com"  # jüri gösterimi için canlı test API'si (Ayarlar'dan değiştirilebilir)


def url() -> str:
    """Kayıtlı adres; hiç kaydedilmediyse varsayılan canlı test API'si. Boş kaydedilirse test kaynağı kapalıdır."""
    saved = ai_settings._load().get("test_source")
    if not isinstance(saved, dict) or "url" not in saved:
        return DEFAULT_URL
    return str(saved.get("url") or "").rstrip("/")


def enabled() -> bool:
    return bool(url())


def save(value: str) -> dict:
    value = (value or "").strip().rstrip("/")
    if value and not value.startswith(("http://", "https://")):
        raise ValueError("Adres http:// ya da https:// ile başlamalı.")
    data = ai_settings._load()
    data["test_source"] = {"url": value}
    ai_settings._write(data)
    return public()


def public() -> dict:
    return {"url": url(), "enabled": enabled(), "site_page": url() + SITE_PAGE if url() else "", "person": TEST_PERSON}


def client(timeout: float = 60) -> httpx.AsyncClient:
    # Render'ın ücretsiz sunucusu uykudaysa ilk istek ~50 sn sürebilir.
    return httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers={"Accept": "application/json"})


async def staff_sample() -> dict:
    """Test API'sinin YÖK benzeri kadro listesinden ilk satır (veri tarifi denetimi için)."""
    if not enabled():
        raise ValueError("Test API adresi girilmedi.")
    async with client() as c:
        r = await c.get(f"{url()}/api/akademisyen/list", params={"page": 1, "length": 1})
        r.raise_for_status()
        body = r.json()
    rows = ((body.get("data") or {}).get("data") if isinstance(body.get("data"), dict) else body.get("data")) or []
    if not rows:
        raise ValueError("test API'sinden örnek kayıt gelmedi")
    return rows[0]


async def current_title() -> str:
    """Test akademisyeninin YÖK benzeri listedeki güncel unvanı (unvan değişikliğini bildirmek için)."""
    from .sources import YOK_TITLES
    try:
        row = await staff_sample()
    except Exception:  # noqa: BLE001
        return ""
    raw = str(row.get("kadroUnvanAdi") or "")
    return YOK_TITLES.get(raw, raw)


async def learn_site() -> dict:
    """Hogwarts kadro sayfasını REA site tariflerine ekler: sayfa parmak izi ve sayfada bulunan akademisyen saklanır.
    Sonraki "Değişiklikleri tara" bu parmak iziyle kıyaslar."""
    from . import recipes
    from .net import fetch_static

    if not enabled():
        raise ValueError("Test API adresi girilmedi.")
    page_url = url() + SITE_PAGE
    page = await fetch_static(page_url, timeout=60)
    skeleton = recipes.dom_skeleton(page.selector)
    host = urlparse(page_url).hostname or "test"
    store = recipes.load(host)
    recipes.remember_page(store, page_url, skeleton, None, "html")
    pk = recipes.person_key(TEST_PERSON["name"])
    entry = store["people"].setdefault(pk, {"name": TEST_PERSON["name"], "seen": 0, "first_seen": recipes._now()})
    entry.update({"listing_url": page_url, "last_seen": recipes._now(), "seen": entry.get("seen", 0) + 1})
    recipes.event(store, "learned", f"{page_url}: test sitesi öğretildi ({len(skeleton)} yapı öğesi)")
    recipes.save(store)
    found = TEST_PERSON["name"] in (page.html or "")
    return {"url": page_url, "domain": host, "elements": len(skeleton), "person_on_page": found}
