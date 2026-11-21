"""WhatsApp'a bağlı cihaz olarak bağlanma (QR) ve kullanıcının kendi numarasına ("Kendine mesaj") gönderme.

crazy02coder/Mcp projesindeki whatsapp-web.js yaklaşımının Python karşılığı: neonize (whatsmeow) tarayıcı açmadan
WhatsApp Web protokolüyle bağlanır. Telefonda WhatsApp → Bağlı cihazlar → Cihaz bağla ile QR okutulur; oturum
yerel diskte (.whatsapp.db) saklanır, uygulama yeniden açıldığında QR gerekmez. Mesaj yalnız bağlı hesabın kendi
numarasına gönderilir; başka numaraya gönderme yoktur.
"""
from __future__ import annotations

import asyncio
import logging
import time

from .ai_settings import ROOT

log = logging.getLogger(__name__)
DB = ROOT / ".whatsapp.db"

# state: off (bağlı değil) | connecting | qr (okutulmayı bekliyor) | ready | error
_state: dict = {"state": "off", "qr": "", "qr_at": 0.0, "phone": "", "error": ""}
_client = None
_lock = asyncio.Lock()


def available() -> bool:
    try:
        import neonize  # noqa: F401
        return True
    except Exception:  # noqa: BLE001 — paket ya da yerel kütüphane yok
        return False


def paired() -> bool:
    """Daha önce QR okutulmuş bir oturum diskte var mı (açılışta kendiliğinden bağlanmak için)."""
    return DB.exists() and DB.stat().st_size > 0


def status() -> dict:
    out = {k: _state[k] for k in ("state", "error")}
    phone = _state["phone"]
    out["phone"] = f"+{phone[:2]} {phone[2:5]} ••• {phone[-2:]}" if len(phone) > 7 else phone
    # QR kodu ~20 sn'de bir yenilenir; eskiyen kod gösterilmez
    out["qr"] = _state["qr"] if _state["state"] == "qr" and time.time() - _state["qr_at"] < 60 else ""
    out["available"] = available()
    out["paired"] = paired()
    return out


def ready() -> bool:
    return _state["state"] == "ready" and _client is not None


def _set(**kw) -> None:
    _state.update(kw)


async def connect() -> dict:
    """Bağlanır; oturum yoksa QR üretir (status()["qr"] → SVG data URI)."""
    global _client
    async with _lock:
        if _client is not None and _state["state"] in ("connecting", "qr", "ready"):
            return status()
        if not available():
            _set(state="error", error="WhatsApp bileşeni (neonize) kurulu değil.")
            return status()
        import segno
        from neonize.aioze.client import NewAClient
        from neonize.events import ConnectedEv, DisconnectedEv, LoggedOutEv, PairStatusEv, TemporaryBanEv
        from neonize.proto.waCompanionReg.WAWebProtobufsCompanionReg_pb2 import DeviceProps

        client = NewAClient(str(DB), props=DeviceProps(os="Akademik İz", platformType=DeviceProps.DESKTOP))

        async def on_qr(_c, data: bytes):
            _set(state="qr", qr=segno.make_qr(data).svg_data_uri(scale=6, border=2), qr_at=time.time(), error="")

        async def on_connected(c, _ev):
            phone = ""
            try:
                me = await c.get_me()
                phone = me.JID.User
            except Exception:  # noqa: BLE001
                log.exception("WhatsApp: kendi numara okunamadı")
            _set(state="ready", qr="", phone=phone, error="")
            log.info("WhatsApp bağlandı")

        async def on_pair(_c, ev):
            if getattr(ev, "Error", ""):
                _set(state="error", error=f"Eşleştirme başarısız: {ev.Error}")

        async def on_logged_out(_c, _ev):
            # Telefondan "cihazın bağlantısını kes" yapıldı: oturum geçersiz, yeniden QR gerekir.
            await _drop(forget=True)
            _set(state="off", error="WhatsApp oturumu telefondan kapatıldı; yeniden bağlayın.")

        async def on_disconnected(_c, _ev):
            if _state["state"] == "ready":
                _set(state="connecting")  # whatsmeow kendiliğinden yeniden bağlanır

        async def on_ban(_c, ev):
            _set(state="error", error=f"WhatsApp geçici olarak engelledi ({getattr(ev, 'Code', '')}).")

        client.qr(on_qr)
        client.event(ConnectedEv)(on_connected)
        client.event(PairStatusEv)(on_pair)
        client.event(LoggedOutEv)(on_logged_out)
        client.event(DisconnectedEv)(on_disconnected)
        client.event(TemporaryBanEv)(on_ban)
        _client = client
        _set(state="connecting", error="", qr="")
        try:
            task = await client.connect()
        except Exception as exc:  # noqa: BLE001
            _client = None
            _set(state="error", error=f"Bağlanılamadı ({type(exc).__name__}).")
            return status()

        def done(t: asyncio.Task):
            if t.cancelled():
                return
            exc = t.exception()
            if exc and _client is client:
                _set(state="error", error=f"Bağlantı kapandı ({type(exc).__name__}: {str(exc)[:120]}).")
        task.add_done_callback(done)
        return status()


async def send(target: str, text: str) -> None:
    """target: "self" (kendi numara, "Kendine mesaj"), "+905…" (kişi) ya da "…@g.us" (bağlı hesabın üye olduğu grup)."""
    if not ready():
        raise RuntimeError("WhatsApp bağlı değil (Ayarlar → Bildirimler → WhatsApp'ı bağla).")
    from neonize.utils.jid import build_jid
    if target == "self":
        phone = _state["phone"]
        if not phone:
            me = await _client.get_me()
            phone = me.JID.User
            _set(phone=phone)
        jid = build_jid(phone)
    elif target.endswith("@g.us"):
        jid = build_jid(target.split("@", 1)[0], "g.us")
    else:
        digits = "".join(ch for ch in target if ch.isdigit())
        if len(digits) < 10:
            raise RuntimeError("Numara geçersiz.")
        jid = build_jid(digits)
    await asyncio.wait_for(_client.send_message(jid, text), 30)


async def send_self(text: str) -> None:
    await send("self", text)


async def groups() -> list[dict]:
    """Bağlı hesabın üye olduğu gruplar (alıcı seçimi için)."""
    if not ready():
        raise RuntimeError("WhatsApp bağlı değil.")
    from neonize.utils.jid import Jid2String
    rows = await asyncio.wait_for(_client.get_joined_groups(), 20)
    out = [{"jid": Jid2String(g.JID), "name": g.GroupName.Name or "Adsız grup", "members": len(g.Participants)} for g in rows]
    return sorted(out, key=lambda g: g["name"].lower())


async def _drop(forget: bool = False) -> None:
    global _client
    client, _client = _client, None
    if client is not None:
        for step in ("disconnect", "stop"):
            try:
                await asyncio.wait_for(getattr(client, step)(), 5)
            except Exception:  # noqa: BLE001
                pass
    if forget:
        for path in (DB, DB.with_name(DB.name + "-wal"), DB.with_name(DB.name + "-shm")):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                log.warning("WhatsApp oturum dosyası silinemedi: %s", path)


async def logout() -> dict:
    """Bağlı cihazı WhatsApp'tan çıkarır ve yerel oturumu siler."""
    if _client is not None and _state["state"] == "ready":
        try:
            await asyncio.wait_for(_client.logout(), 10)
        except Exception:  # noqa: BLE001
            log.warning("WhatsApp çıkışı sunucuya iletilemedi; yerel oturum yine de silinir")
    await _drop(forget=True)
    _set(state="off", qr="", phone="", error="")
    return status()


async def shutdown() -> None:
    await _drop(forget=False)
