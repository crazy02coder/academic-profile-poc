"""Yayın takibi: takip edilen akademisyen yeni bir yayın yayımlayınca WhatsApp bildirimi.

Kaynak: OpenAlex (ORCID ya da OpenAlex yazar kimliğiyle; ad ile takip edilmez, aynı adlı kişiler karışır).
Canlı test kaynağı (test_source) aynı OpenAlex biçimini taklit eder; oradaki "Yeni yayın" anında görünür.

Kurallar:
  * İlk takipte mesaj atılmaz: o anki yayınlar "bilinen" olarak saklanır.
  * OpenAlex'te yayın tarihi son 60 günden eski olan kayıt yeni sayılmaz (geç indekslenen eski makale).
  * Aynı yayın kimliğinden tanınır, iki kez bildirilmez. Aynı kontrolde birden çok yeni yayın tek mesajda toplanır.
  * OpenAlex günde bir kez (uygulama açıkken), test kaynağı dakikada bir kontrol edilir.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, timedelta

from . import ai_settings, notify, test_source

log = logging.getLogger(__name__)
NEW_WINDOW_DAYS = 60
OPENALEX_EVERY = 20 * 3600
TEST_EVERY = 60
_LOCK = asyncio.Lock()


def _base(source: str) -> str:
    if source == "test":
        return test_source.url() + "/openalex" if test_source.enabled() else ""
    from .sources import OPENALEX
    return OPENALEX


def _params(source: str) -> dict:
    if source == "test":
        return {}
    from .config import OPENALEX_PARAMS
    return dict(OPENALEX_PARAMS)


def follows() -> list[dict]:
    saved = ai_settings._load().get("follows")
    return [f for f in saved if isinstance(f, dict) and f.get("author_id")] if isinstance(saved, list) else []


def _write(rows: list[dict]) -> None:
    data = ai_settings._load()
    data["follows"] = rows
    ai_settings._write(data)


def public() -> list[dict]:
    return [{k: f.get(k) for k in ("key", "name", "title", "institution", "source", "author_id", "orcid", "added_at",
                                   "last_check", "last_new", "error")} | {"known": len(f.get("known") or [])} for f in follows()]


def _client(source: str):
    if source == "test":
        return test_source.client()
    from .sources import _client
    return _client()


async def _resolve(client, source: str, author_id: str, orcid: str) -> dict:
    """OpenAlex yazar kaydı: kimlikle ya da ORCID ile."""
    ref = author_id.rsplit("/", 1)[-1] if author_id else f"orcid:{orcid}"
    r = await client.get(f"{_base(source)}/authors/{ref}", params=_params(source))
    if r.status_code != 200:
        raise RuntimeError("OpenAlex'te bu yazar bulunamadı." if r.status_code == 404 else f"OpenAlex yanıt vermedi (HTTP {r.status_code}).")
    return r.json()


async def _works(client, source: str, author_id: str, since: str = "", pages: int = 1) -> list[dict]:
    out = []
    flt = f"author.id:{author_id}" + (f",from_publication_date:{since}" if since else "")
    for page in range(1, pages + 1):
        r = await client.get(f"{_base(source)}/works", params={"filter": flt, "per-page": 200, "page": page,
                                                               "sort": "publication_date:desc", **_params(source)})
        if r.status_code != 200:
            raise RuntimeError(f"Yayınlar okunamadı (HTTP {r.status_code}).")
        rows = r.json().get("results") or []
        out += rows
        if len(rows) < 200:
            break
    return out


def _wid(work: dict) -> str:
    return str(work.get("id") or "").rsplit("/", 1)[-1]


async def follow(name: str, author_id: str = "", orcid: str = "", source: str = "openalex", title: str = "",
                 institution: str = "") -> dict:
    """Takibe ekler ve o anki yayınları "bilinen" olarak kaydeder (ilk takipte bildirim yok)."""
    if source == "test" and not test_source.enabled():
        raise RuntimeError("Önce Ayarlar → Sistem'de test API adresini girin.")
    if not author_id and not orcid:
        raise RuntimeError("Bu akademisyenin ORCID ya da OpenAlex kimliği yok; yayınları güvenilir biçimde takip edilemez.")
    async with _LOCK:
        async with _client(source) as client:
            author = await _resolve(client, source, author_id, orcid)
            aid = _wid(author)
            works = await _works(client, source, aid, pages=3)
        if source == "test" and not title:
            title = await test_source.current_title()
        rows = [f for f in follows() if not (f["author_id"] == aid and f.get("source") == source)]
        entry = {"key": f"{source}:{aid}", "name": name or author.get("display_name") or "", "title": title, "institution":
                 institution or ", ".join(i.get("display_name", "") for i in author.get("last_known_institutions") or []),
                 "source": source, "author_id": aid, "orcid": orcid or str(author.get("orcid") or "").rsplit("/", 1)[-1],
                 "known": [_wid(w) for w in works], "added_at": time.time(), "last_check": time.time(), "last_new": 0, "error": ""}
        _write([*rows, entry])
    return entry


def unfollow(key: str) -> bool:
    rows = follows()
    kept = [f for f in rows if f.get("key") != key]
    _write(kept)
    return len(kept) < len(rows)


# ------------------------------------------------------------------ mesaj
def _quartile(work: dict) -> str:
    q = ((work.get("x_test") or {}).get("quartile") or "").upper()
    if q:
        return q
    src = (work.get("primary_location") or {}).get("source") or {}
    try:
        from .quartiles import annotate
        paper = {"year": work.get("publication_year"), "issn": src.get("issn") or ([src["issn_l"]] if src.get("issn_l") else []),
                 "venue": src.get("display_name") or ""}
        annotate([paper])
        return str((paper.get("quartile") or {}).get("q") or "").upper()
    except Exception:  # noqa: BLE001
        return ""


def _points(work: dict, quartile: str) -> tuple[float, str]:
    """Doçentlik puanına katkı (uygulamadaki puan tablosuyla): (puan, açıklama). Hesaplanamazsa (0, "")."""
    try:
        from .academic_score import classify, criteria
        c = criteria()
        src = (work.get("primary_location") or {}).get("source") or {}
        kind = "proceedings" if src.get("type") == "conference" else "article"
        labels = ["Uluslararası", (work.get("x_test") or {}).get("yok_tur") or ""]
        key = classify({"type": kind, "labels": labels, "quartile": {"q": quartile} if quartile else None})
        if not key:
            return 0, ""
        base = next((float(k["puan"][key]) for k in c["docentlik"]["kalemler"].values() if isinstance(k.get("puan"), dict) and key in k["puan"]), 0)
        n = max(1, len(work.get("authorships") or []))
        share = float(c.get("yazar_payi", {}).get(str(min(n, 4)), 1 / n))
        detail = (quartile or ("bildiri" if kind == "proceedings" else "makale")) + f", {n} yazar"
        return round(base * share, 1), detail
    except Exception:  # noqa: BLE001
        return 0, ""


_MONTHS = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")


def _date_tr(value: str) -> str:
    try:
        d = date.fromisoformat(value[:10])
        return f"{d.day} {_MONTHS[d.month - 1]} {d.year}"
    except (TypeError, ValueError):
        return value or ""


def _work_block(f: dict, work: dict) -> str:
    src = (work.get("primary_location") or {}).get("source") or {}
    quartile = _quartile(work)
    others = [a.get("author", {}).get("display_name") or a.get("raw_author_name") for a in work.get("authorships") or []
              if not str((a.get("author") or {}).get("id") or "").endswith(f["author_id"])]
    others = [o for o in others if o and o != f["name"]]
    lines = [f"*{work.get('display_name') or work.get('title')}*"]
    venue = " · ".join(x for x in (src.get("display_name"), quartile, _date_tr(work.get("publication_date") or "")) if x)
    if venue:
        lines.append(f"📰 {venue}")
    if others:
        lines.append("👥 Ortak yazarlar: " + ", ".join(others[:6]) + (f" ve {len(others) - 6} kişi daha" if len(others) > 6 else ""))
    if work.get("doi"):
        lines.append(f"🔗 {work['doi']}")
    pts, why = _points(work, quartile)
    if pts:
        lines.append(f"🏅 Doçentlik puanına katkısı: {pts:g} puan ({why})")
    return "\n".join(lines)


def _message(f: dict, works: list[dict], new_title: str = "") -> str:
    who = " ".join(x for x in (new_title or f.get("title"), f["name"]) if x)
    where = f" ({f['institution']})" if f.get("institution") else ""
    head = (f"📄 Takip ettiğiniz {who}{where} yeni bir yayın yayımladı:" if len(works) == 1
            else f"📄 Takip ettiğiniz {who}{where} {len(works)} yeni yayın yayımladı:")
    body = head + "\n\n" + "\n\n".join(_work_block(f, w) for w in works)
    if new_title and f.get("title") and new_title != f["title"]:
        body += f"\n\n🎓 Unvanı {f['title']} → {new_title} olarak güncellendi. Tebrikler!"
    return body


# ------------------------------------------------------------------ kontrol
async def check(sources: tuple[str, ...] = ("openalex", "test")) -> list[dict]:
    """Takip edilenlerin yeni yayınlarını bulur, bildirir. Dönen: [{key, name, new: [başlık…], sent, error}]."""
    report = []
    async with _LOCK:
        rows = follows()
        since = (date.today() - timedelta(days=120)).isoformat()
        cutoff = (date.today() - timedelta(days=NEW_WINDOW_DAYS)).isoformat()
        for f in rows:
            source = f.get("source") or "openalex"
            if source not in sources or not _base(source):
                continue
            item = {"key": f["key"], "name": f["name"], "new": [], "sent": False, "error": ""}
            try:
                async with _client(source) as client:
                    works = await _works(client, source, f["author_id"], since)
                known = set(f.get("known") or [])
                fresh = [w for w in works if _wid(w) not in known
                         and (source == "test" or (w.get("publication_date") or "") >= cutoff)]
                f["known"] = list(known | {_wid(w) for w in works})[-2000:]
                f["last_check"], f["error"] = time.time(), ""
                if fresh:
                    new_title = await test_source.current_title() if source == "test" else ""
                    item["new"] = [w.get("display_name") or w.get("title") for w in fresh]
                    item["sent"] = await notify.try_send(_message(f, fresh, new_title))
                    f["last_new"] = time.time()
                    if new_title:
                        f["title"] = new_title
            except Exception as exc:  # noqa: BLE001
                f["error"] = str(exc)[:200] if isinstance(exc, RuntimeError) else type(exc).__name__
                item["error"] = f["error"]
            report.append(item)
        _write(rows)
    return report


async def ensure_test_follow() -> None:
    """Test kaynağı açıksa test akademisyeni (Bahadır Arslan) kendiliğinden takipte olur; ilk takipte mevcut yayınlar
    bilinen sayılır, sonra eklenen her makale bildirilir."""
    if not test_source.enabled() or any(f.get("source") == "test" for f in follows()):
        return
    p = test_source.TEST_PERSON
    try:
        await follow(p["name"], p["author_id"], p["orcid"], "test", "", p["institution"])
        log.info("Test akademisyeni yayın takibine alındı")
    except Exception as exc:  # noqa: BLE001 — Render uykudaysa bir sonraki turda yeniden denenir
        log.warning("Test akademisyeni takibe alınamadı: %s", exc)


async def loop() -> None:
    """Test kaynağı dakikada bir, OpenAlex günde bir kez (uygulama açıkken)."""
    await asyncio.sleep(30)
    last_openalex = 0.0
    while True:
        try:
            await ensure_test_follow()
            if any(f.get("source") == "test" for f in follows()) and test_source.enabled():
                await check(("test",))
            if time.time() - last_openalex > OPENALEX_EVERY and any(f.get("source", "openalex") == "openalex" for f in follows()):
                last_openalex = time.time()
                await check(("openalex",))
        except Exception:  # noqa: BLE001
            log.exception("Yayın takibi kontrolü başarısız")
        await asyncio.sleep(TEST_EVERY)
