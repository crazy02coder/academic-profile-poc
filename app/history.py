"""Kalıcı sohbet geçmişi ve profil sonuçları (data/chats, runs/)."""
from __future__ import annotations

import json
import re
import time
import uuid

from .config import ROOT, RUNS_DIR
from .text import fold

CHATS_DIR = ROOT / "data" / "chats"
ORCID_RE = re.compile(r"\d{4}-\d{4}-\d{4}-\d{3}[\dXx]")
YOK_ID_RE = re.compile(r"authorId=([0-9A-Fa-f]+)")


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


def same_person(a: dict, b: dict) -> bool:
    """İki profil aynı kişi mi? Önce YÖK kimliği, sonra ORCID; ikisi de yoksa ad + kurum. Aynı adlı farklı kişiler ayrı kalır."""
    def ids(prof: dict) -> tuple[str, str]:
        links = prof.get("links") or {}
        yok = YOK_ID_RE.search(links.get("yok") or "")
        orcid = ORCID_RE.search(f"{prof.get('orcid') or ''} {links.get('orcid') or ''}")
        return (yok[1].upper() if yok else "", orcid[0].upper() if orcid else "")
    for x, y in zip(ids(a), ids(b)):
        if x and y:
            return x == y
    name_a, name_b = fold(a.get("name") or ""), fold(b.get("name") or "")
    inst_a, inst_b = fold(a.get("institution") or ""), fold(b.get("institution") or "")
    return bool(name_a and name_a == name_b and inst_a and inst_b and (inst_a in inst_b or inst_b in inst_a))


def find_same(prof: dict) -> dict | None:
    """Bu kişinin mevcut kaydı (yeni bir profil, kayıt çoğaltmak yerine onun üzerine yazılır)."""
    for chat in list_all():
        other = load_result(chat["job_id"])
        if other and same_person(prof, other.get("profile") or {}):
            return chat
    return None


def remap_citations(messages: list[dict], old: dict, new: dict) -> list[dict]:
    """[P#] yayın listesindeki sıradır; liste değişince eski cevaplar başka yayını göstermesin.

    Yayın yeni listede varsa numarası güncellenir, yoksa atıf yerine yayının adı yazılır."""
    def doi(p: dict) -> str:
        return (p.get("doi") or "").lower().replace("https://doi.org/", "")
    before = {p.get("id"): p for p in old.get("publications") or []}
    now: dict[str, str] = {}
    for p in new.get("publications") or []:
        for key in (doi(p), fold(p.get("title") or "")):
            if key:
                now.setdefault(key, p.get("id"))

    def swap(m: re.Match) -> str:
        p = before.get(m[1])
        if not p:
            return m[0]
        found = now.get(doi(p)) or now.get(fold(p.get("title") or ""))
        return f"[{found}]" if found else f"“{p.get('title')}”"
    return [{**m, "content": re.sub(r"\[(P\d+)\]", swap, m["content"])} if m.get("role") == "assistant" else m for m in messages]


def refresh(cid: str, job_id: str, result: dict) -> dict:
    """Yenilenen profilin özet alanlarını mevcut sohbete yazar (mesajlar korunur); sohbet silinmişse yenisini açar."""
    chat = load(cid) if cid else None
    if not chat:
        return create(job_id, result)
    old = load_result(chat["job_id"])
    if old:
        chat["messages"] = remap_citations(chat["messages"], old, result)
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
