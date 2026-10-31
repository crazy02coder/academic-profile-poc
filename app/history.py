"""Kalıcı sohbet geçmişi ve profil sonuçları (data/chats, runs/)."""
from __future__ import annotations

import json
import re
import time
import uuid

from .config import ROOT, RUNS_DIR

CHATS_DIR = ROOT / "data" / "chats"


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _safe(cid: str) -> str:
    if not re.fullmatch(r"[a-f0-9]{8,32}", cid or ""):
        raise ValueError("geçersiz kimlik")
    return cid


def create(job_id: str, result: dict) -> dict:
    prof = result["profile"]
    chat = {"id": uuid.uuid4().hex[:12], "job_id": job_id, "name": prof.get("name"), "title": prof.get("title"),
            "institution": prof.get("institution"), "papers": result.get("unique_count", 0),
            "created": _now(), "updated": _now(), "messages": []}
    save(chat)
    return chat


def refresh(cid: str, job_id: str, result: dict) -> dict:
    """Yenilenen profilin özet alanlarını mevcut sohbete yazar (mesajlar korunur); sohbet silinmişse yenisini açar."""
    chat = load(cid) if cid else None
    if not chat:
        return create(job_id, result)
    prof = result["profile"]
    chat.update(name=prof.get("name"), title=prof.get("title"), institution=prof.get("institution"),
                papers=result.get("unique_count", 0))
    save(chat)
    return chat


def save(chat: dict):
    CHATS_DIR.mkdir(parents=True, exist_ok=True)
    chat["updated"] = _now()
    (CHATS_DIR / f"{_safe(chat['id'])}.json").write_text(json.dumps(chat, ensure_ascii=False, indent=1))


def load(cid: str) -> dict | None:
    p = CHATS_DIR / f"{_safe(cid)}.json"
    return json.loads(p.read_text()) if p.exists() else None


def delete(cid: str) -> bool:
    p = CHATS_DIR / f"{_safe(cid)}.json"
    if p.exists():
        p.unlink()
        return True
    return False


def list_all() -> list[dict]:
    if not CHATS_DIR.exists():
        return []
    out = []
    for p in CHATS_DIR.glob("*.json"):
        try:
            c = json.loads(p.read_text())
        except ValueError:
            continue
        first_q = next((m["content"] for m in c["messages"] if m["role"] == "user"), "")
        out.append({k: c.get(k) for k in ("id", "job_id", "name", "title", "institution", "papers", "created", "updated")}
                   | {"messages": len(c["messages"]), "preview": first_q[:80]})
    return sorted(out, key=lambda c: c["updated"], reverse=True)


def save_result(job_id: str, result: dict):
    RUNS_DIR.mkdir(exist_ok=True)
    (RUNS_DIR / f"{_safe(job_id)}.json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str))


def load_result(job_id: str) -> dict | None:
    p = RUNS_DIR / f"{_safe(job_id)}.json"
    return json.loads(p.read_text()) if p.exists() else None


def delete_result(job_id: str):
    p = RUNS_DIR / f"{_safe(job_id)}.json"
    if p.exists():
        p.unlink()
