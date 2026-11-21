"""WhatsApp bildirimi: veri tarifi kontrolleri ve REA site taramasının sonucu seçilen alıcılara gider.

Gönderim bu bilgisayarın WhatsApp'a bağlı cihaz olarak eklenmesiyle yapılır (app/whatsapp.py, QR). Mesaj kullanıcının
kendi numarasından çıkar; alıcılar: kendisi ("Kendine mesaj"), en çok MAX_NUMBERS numara ve en çok MAX_GROUPS grup.
Az alıcı tutulur: gayriresmî istemciden çok kişiye gönderim numaranın engellenmesine yol açabilir.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime

from . import ai_settings, whatsapp

log = logging.getLogger(__name__)
MAX_NUMBERS, MAX_GROUPS = 5, 3
_DEFAULT = {"only_changes": True, "daily": False, "last_daily": 0.0, "to_self": True, "numbers": [], "groups": [], "app_url": ""}
TITLES = ("Prof. Dr.", "Doç. Dr.", "Dr. Öğr. Üyesi", "Dr.", "Öğr. Gör.", "Arş. Gör.", "Arş. Gör. Dr.")
_STATUS = {"ok": "sorunsuz", "changed": "biçim değişti", "broken": "boş alan var", "unknown": "henüz kontrol edilmedi"}


def normalize_phone(raw: str) -> str:
    """Türkiye numarası yerel yazılsa da (05xx…) uluslararası biçime (+905xx…) çevrilir."""
    digits = re.sub(r"\D", "", raw or "")
    if not digits:
        return ""
    if digits.startswith("00"):
        digits = digits[2:]
    elif digits.startswith("0"):
        digits = "90" + digits[1:]
    elif len(digits) == 10 and digits.startswith("5"):
        digits = "90" + digits
    return "+" + digits


def settings() -> dict:
    saved = ai_settings._load().get("notify")
    saved = saved if isinstance(saved, dict) else {}
    out = {k: saved.get(k, v) for k, v in _DEFAULT.items()}
    out["numbers"] = [x for x in out["numbers"] if isinstance(x, dict) and x.get("phone")][:MAX_NUMBERS]
    out["groups"] = [x for x in out["groups"] if isinstance(x, dict) and str(x.get("jid", "")).endswith("@g.us")][:MAX_GROUPS]
    return out


def targets() -> list[dict]:
    s = settings()
    out = [{"kind": "self", "to": "self", "label": "Kendime"}] if s["to_self"] else []
    out += [{"kind": "number", "to": x["phone"], "label": " ".join(p for p in (x.get("title"), x.get("name")) if p) or x["phone"],
             "title": x.get("title") or "", "name": x.get("name") or ""} for x in s["numbers"]]
    out += [{"kind": "group", "to": x["jid"], "label": x.get("name") or "Grup"} for x in s["groups"]]
    return out


def public() -> dict:
    s = settings()
    return {"ready": enabled(), "whatsapp": whatsapp.status(), "only_changes": bool(s["only_changes"]), "daily": bool(s["daily"]),
            "last_daily": s["last_daily"], "to_self": bool(s["to_self"]), "numbers": s["numbers"], "groups": s["groups"],
            "max_numbers": MAX_NUMBERS, "max_groups": MAX_GROUPS, "titles": list(TITLES), "app_url": s["app_url"]}


def save(values: dict) -> dict:
    """Yalnız verilen alanlar değişir. numbers: [{phone, name}], groups: [{jid, name}]."""
    data = ai_settings._load()
    entry = settings()
    for key in ("only_changes", "daily", "to_self"):
        if values.get(key) is not None:
            entry[key] = bool(values[key])
    if values.get("numbers") is not None:
        seen, rows = set(), []
        for item in values["numbers"]:
            phone = normalize_phone(str(item.get("phone") or ""))
            if len(phone) < 11 or phone in seen:
                continue
            seen.add(phone)
            rows.append({"phone": phone, "name": str(item.get("name") or "").strip()[:60],
                         "title": str(item.get("title") or "").strip()[:30]})
        if len(rows) > MAX_NUMBERS:
            raise ValueError(f"En çok {MAX_NUMBERS} numara eklenebilir.")
        entry["numbers"] = rows
    if values.get("app_url") is not None:
        url = str(values["app_url"]).strip().rstrip("/")
        if url and not url.startswith(("http://", "https://")):
            raise ValueError("Uygulama adresi http:// ya da https:// ile başlamalı.")
        entry["app_url"] = url[:200]
    if values.get("groups") is not None:
        rows = [{"jid": str(g.get("jid")), "name": str(g.get("name") or "").strip()[:60]}
                for g in values["groups"] if str(g.get("jid", "")).endswith("@g.us")]
        if len(rows) > MAX_GROUPS:
            raise ValueError(f"En çok {MAX_GROUPS} grup seçilebilir.")
        entry["groups"] = rows
    data["notify"] = entry
    ai_settings._write(data)
    return public()


def enabled() -> bool:
    return whatsapp.ready() and bool(targets())


SIGNATURE = "— Akademik İz asistanı 🎓"
DEVELOPER = "Bahadır Arslan"  # değişiklik kontrol katmanını geliştiren


def greeting(row: dict) -> str:
    """Kayıtlı kişiye unvanı ve adıyla hitap ("Merhaba Prof. Dr. Ayşe Yılmaz,"); kendine ve gruplara genel selam."""
    who = " ".join(p for p in (row.get("title"), row.get("name")) if p)
    return f"👋 Merhaba {who}, ben Akademik İz asistanıyım." if who else "👋 Merhaba, ben Akademik İz asistanıyım."


def compose(row: dict, body: str) -> str:
    return f"{greeting(row)}\n\n{body.strip()}\n\n{SIGNATURE}"


async def send(text: str, plain: bool = False) -> dict:
    """Mesajı tüm alıcılara sırayla gönderir (aralarda kısa bekleme); her alıcıya kendi hitabı ve imza eklenir
    (plain=True: metin olduğu gibi). Hiçbirine gidemezse RuntimeError."""
    if not whatsapp.ready():
        raise RuntimeError("WhatsApp bağlı değil: Ayarlar → Bildirimler → WhatsApp'ı bağla (QR).")
    rows = targets()
    if not rows:
        raise RuntimeError("Alıcı seçilmedi: en az bir alıcı işaretleyin.")
    sent, failed = [], []
    for n, row in enumerate(rows):
        if n:
            await asyncio.sleep(1.5)  # art arda hızlı gönderim engellenme riskini artırır
        try:
            await whatsapp.send(row["to"], (text if plain else compose(row, text))[:3500])
            sent.append(row["label"])
        except Exception as exc:  # noqa: BLE001
            log.warning("WhatsApp: %s alıcısına gönderilemedi: %s", row["label"], exc)
            failed.append(f"{row['label']} ({exc if isinstance(exc, RuntimeError) else type(exc).__name__})")
    if not sent:
        raise RuntimeError("Gönderilemedi: " + "; ".join(failed))
    return {"sent": sent, "failed": failed}


async def try_send(text: str) -> bool:
    """Arka plan bildirimleri için: hata kontrol akışını bozmaz, yalnız günlüğe yazılır."""
    if not enabled():
        return False
    try:
        await send(text)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("WhatsApp bildirimi gönderilemedi: %s", exc)
        return False


_MONTHS = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")


def _when(ts: float | None = None) -> str:
    d = datetime.fromtimestamp(ts) if ts else datetime.now()
    return f"{d.day} {_MONTHS[d.month - 1]} {d:%H:%M}"


def _names(items: list[str], limit: int = 5) -> str:
    items = [str(x) for x in items if x]
    return ", ".join(items[:limit]) + (f" ve {len(items) - limit} alan daha" if len(items) > limit else "")


def _pct_dative(value: int) -> str:
    """Yüzdeye yönelme eki, sayının okunuşuna göre: %59'a, %62'ye, %80'e, %100'e."""
    value = abs(int(value))
    if value % 100 == 0 and value:
        return f"%{value}'e"
    ones = {0: "a", 1: "e", 2: "ye", 3: "e", 4: "e", 5: "e", 6: "ya", 7: "ye", 8: "e", 9: "a"}
    tens = {1: "a", 2: "ye", 3: "a", 4: "a", 5: "ye", 6: "a", 7: "e", 8: "e", 9: "a"}
    suffix = ones[value % 10] if value % 10 or not value else tens[(value // 10) % 10]
    return f"%{value}'{suffix}"


def _link() -> str:
    url = settings()["app_url"]
    return f"\n\n🔗 Kayıt ve karşılaştırma:\n{url}/#/sistem" if url else ""


def _problem(r: dict) -> bool:
    return bool(r.get("error")) or r.get("status") in ("changed", "broken")


def _contract_story(r: dict) -> str:
    """Tek veri kaynağı için açıklama paragrafı."""
    label = r["label"]
    if r.get("error"):
        return (f"⚠️ *{label}*: kaynağa ulaşılamadı ({r['error']}). Önceki tarif korunuyor; site geçici olarak kapalı "
                "olabilir, bir sonraki kontrolde yeniden denenecek.")
    if r.get("status") == "broken":
        return (f"🔴 *{label}*: kaynağın yanıt biçimi değişti ve şu bilgiler boş dönmeye başladı: {_names(r.get('empty') or [])}. "
                "Bu alanlar düzelene kadar ilgili sayfalarda eksik görünecek; Ayarlar → Veri tarifleri → \"Tarifi güncelle\" "
                "ile yeni eşleme öğrenilebilir.")
    if r.get("status") == "changed":
        parts = []
        if r.get("removed"):
            parts.append(f"kaldırılan alanlar: {_names(r['removed'])}")
        if r.get("added"):
            parts.append(f"yeni alanlar: {_names(r['added'])}")
        return (f"🟡 *{label}*: kaynağın yanıt biçimi değişti ({'; '.join(parts)}). Gerekli bilgilerin hepsi hâlâ "
                "okunabiliyor, uygulama çalışmaya devam ediyor.")
    return f"🟢 *{label}*: sorunsuz çalışıyor."


def _contracts_ok(results: list[dict], when: str) -> str:
    """Her şey yolundayken: ölçülen yanıt biçimi benzerliğiyle tek paragraflık durum raporu."""
    sims = [r["similarity"] for r in results if isinstance(r.get("similarity"), (int, float))]
    lines = "\n".join(f"🟢 {r['label']}" + (f" · %{r['similarity'] * 100:.0f}" if isinstance(r.get("similarity"), (int, float)) else "")
                      for r in results)
    if sims:
        measured = (f"📈 {DEVELOPER} tarafından geliştirilen değişiklik kontrol katmanına göre veri kaynaklarının yanıt biçimi "
                    f"benzerliği en düşük %{min(sims) * 100:.0f} (ortalama %{sum(sims) / len(sims) * 100:.0f}) ile önceki "
                    "yapıyla benzer sonuç vermiş olup tarifler değişmeden çalışıyor.")
    else:
        measured = (f"📈 {DEVELOPER} tarafından geliştirilen değişiklik kontrol katmanına göre veri kaynaklarının yanıt "
                    "biçimleri önceki yapıyla aynı olup tarifler değişmeden çalışıyor.")
    return f"{when} tarihindeki kontrolde {measured}\n\n{lines}\n\n✅ Yapmanız gereken bir şey yok."


async def contracts_report(results: list[dict], source: str = "elle yapılan", force: bool = False) -> bool:
    """Veri tarifi sonuçlarını gönderir. Elle yapılan kontrolde (force) her zaman; otomatik kontrolde "yalnız sorun olunca"
    açıksa her şey sorunsuzken mesaj atılmaz."""
    if not results or not enabled():
        return False
    problems = [r for r in results if _problem(r)]
    if not force and settings()["only_changes"] and not problems:
        return False
    when = _when()
    if not problems:
        body = _contracts_ok(results, when)
    else:
        broken = any(r.get("status") == "broken" for r in problems)
        rest = [r["label"] for r in results if not _problem(r)]
        body = (f"🔍 Sistem {when} tarihindeki kontrolde {len(problems)} veri kaynağında değişiklik algıladı:\n\n"
                + "\n\n".join(_contract_story(r) for r in problems)
                + (f"\n\n🟢 Diğer kaynaklar sorunsuz: {', '.join(rest)}." if rest else "")
                + ("\n\n🛠️ Tarifin güncellenmesi gerekiyor." if broken else "\n\n✅ Yapmanız gereken bir şey yok."))
    return await try_send(body + _link())


def _site_story(r: dict) -> str:
    """REA taramasında yapısı değişen bir site için açıklama (yalnız ölçülen değerler yazılır)."""
    from .recipes import DRIFT_THRESHOLD
    site = r.get("domain") or "site"
    sim = r.get("similarity")
    text = f"🌐 *{site}* sitesinin yapısı değişti."
    if r.get("relearned") and r.get("via_api"):
        text += " Akademisyen listesi artık sayfada değil, arka planda bir API isteğiyle yükleniyor."
    measured = (f"sayfa parmak izi benzerliğinin {_pct_dative(round(sim * 100))} düştüğünü (eşik %{DRIFT_THRESHOLD * 100:.0f}) tespit etti"
                if isinstance(sim, (int, float)) else "sayfa yapısının değiştiğini tespit etti")
    text += f"\n\n📉 {DEVELOPER} tarafından geliştirilen değişiklik kontrol katmanı {measured}"
    text += "; eski tarif boş dönmeye başlamıştı." if r.get("old_empty") else "."
    if r.get("relearned"):
        took = f" {r['relearn_seconds']:.0f} saniyede" if r.get("relearn_seconds") else ""
        text += f"\n\n🧠 Tersine mühendislik kütüphanesi REA sayfayı yeniden izledi, veriyi getiren isteği buldu; tarif{took} yeniden öğrenildi"
        total, ok = r.get("verified_of"), r.get("verified")
        if total:
            text += f" ve kayıtlı {total} akademisyenin {ok}'{_count_suffix(ok)} doğru sonuç verdi."
            if ok == total:
                text += "\n\n⚡ Scrapling artık bu tarifle, tarayıcı açmadan çalışıyor."
            else:
                text += f"\n\n⚠️ {total - ok} akademisyen yeni tarifle bulunamadı; kontrol edilmeli."
        else:
            text += ".\n\n⚡ Scrapling artık bu tarifle, tarayıcı açmadan çalışıyor."
    else:
        text += ("\n\n⚠️ REA şu an kullanılamadığı için tarif yeniden öğrenilemedi; tarif güncellenene kadar bu siteden gelen "
                 "bilgiler eksik olabilir.")
    return text


def _count_suffix(value: int) -> str:
    """Sayıya bulunma eki, okunuşa göre: 11'inde, 3'ünde, 6'sında, 10'unda."""
    value = abs(int(value))
    last = value % 10
    if last:
        return {1: "inde", 2: "sinde", 3: "ünde", 4: "ünde", 5: "inde", 6: "sında", 7: "sinde", 8: "inde", 9: "unda"}[last]
    if value == 0:
        return "ında"
    if value % 100 == 0:
        return "ünde"
    return {1: "unda", 2: "sinde", 3: "unda", 4: "ında", 5: "sinde", 6: "ında", 7: "inde", 8: "inde", 9: "ında"}[(value // 10) % 10]


async def scan_report(report: list[dict], force: bool = False, source: str = "elle başlatılan") -> bool:
    """REA site taraması: yapısı değişen ya da açılamayan sayfalar."""
    if not enabled():
        return False
    drift = [r for r in report if r.get("drift")]
    failed = [r for r in report if r.get("error")]
    if not force and settings()["only_changes"] and not drift and not failed:
        return False
    when = _when()
    if not drift and not failed:
        from .recipes import DRIFT_THRESHOLD
        sims = [r["similarity"] for r in report if isinstance(r.get("similarity"), (int, float))]
        if sims:
            measured = (f"📈 {DEVELOPER} tarafından geliştirilen değişiklik kontrol katmanına göre sayfa parmak izi benzerliği "
                        f"en düşük %{min(sims) * 100:.0f} (ortalama %{sum(sims) / len(sims) * 100:.0f}, eşik "
                        f"%{DRIFT_THRESHOLD * 100:.0f}) ile önceki yapıyla benzer sonuç vermiş olup tarifler değişmeden çalışıyor.")
        else:
            measured = "📈 Sayfaların hepsi bilinen yapıda, tarifler çalışıyor."
        body = (f"{when} tarihindeki taramada 📈 {measured[2:].rstrip('.')}; {len(report)} sayfa kontrol edildi."
                "\n\n✅ Yapmanız gereken bir şey yok.")
    else:
        done = all(r.get("relearned") and r.get("verified", 1) == r.get("verified_of", 1) for r in drift)
        body = (f"🔍 Sistem {when} tarihindeki taramada bir değişiklik algıladı"
                + (" ve uyguladı" if drift and done else "") + ":\n\n"
                + "\n\n".join(_site_story(r) for r in drift[:4]))
        if failed:
            body += ("\n\n" if drift else "") + "⚠️ Açılamayan sayfalar: " + ", ".join(
                f"{r.get('domain')} ({r.get('error')})" for r in failed[:5]) + ". Bir sonraki taramada yeniden denenecek."
        body += "\n\n✅ Yapmanız gereken bir şey yok." if done and not failed else "\n\n🛠️ Tarifin kontrol edilmesi gerekiyor."
    return await try_send(body + _link())


def latest_status() -> str:
    """Deneme mesajı: son kontrolün kayıtlı sonucu (kaynaklara yeniden gidilmez), gerçek bildirim biçiminde."""
    from . import contracts
    rows = [r for r in contracts.summary() if r.get("checked_at")]
    if not rows:
        return ("📈 Veri kaynakları henüz kontrol edilmedi. \"Şimdi kontrol et ve gönder\" ile ilk kontrolü yaptığınızda "
                "sonuç bu sohbete gelecek.")
    when = _when(max(r["checked_at"] for r in rows))
    problems = [r for r in rows if _problem(r)]
    if not problems:
        return _contracts_ok(rows, when)
    return (f"🔍 {when} tarihindeki son kontrolde {len(problems)} veri kaynağında değişiklik vardı:\n\n"
            + "\n\n".join(_contract_story(r) for r in problems))


async def check_all_contracts() -> list[dict]:
    from . import contracts
    results = []
    for cid in contracts.CONTRACTS:
        try:
            results.append(await contracts.check(cid))
        except Exception as exc:  # noqa: BLE001
            results.append({"id": cid, "label": contracts.CONTRACTS[cid]["label"], "error": type(exc).__name__})
    return results


async def daily_loop() -> None:
    """Uygulama açıkken günde bir kez veri tariflerini kontrol eder ve (ayara göre) sonucu gönderir."""
    await asyncio.sleep(90)  # açılışta veri indirme ve arayüz istekleri öncelikli
    while True:
        s = settings()
        if s["daily"] and enabled() and time.time() - float(s["last_daily"] or 0) > 20 * 3600:
            data = ai_settings._load()
            entry = settings()
            entry["last_daily"] = time.time()
            data["notify"] = entry
            ai_settings._write(data)
            try:
                await contracts_report(await check_all_contracts(), "otomatik")
            except Exception:  # noqa: BLE001
                log.exception("Günlük kontrol başarısız")
        await asyncio.sleep(1800)
