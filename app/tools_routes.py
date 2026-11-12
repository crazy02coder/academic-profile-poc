"""Araçlar: doçentlik/teşvik puan hesabı ve danışman bulucu."""
from __future__ import annotations
import asyncio
import re
import httpx
from fastapi import APIRouter, HTTPException, Query
from . import academic_score, advisors, history, library
from .llm import LLM

router = APIRouter(prefix="/api/tools")


@router.get("/score/{job_id}")
async def score(job_id: str, year: int | None = Query(None, ge=2015, le=2100)):
    if not re.fullmatch(r"[A-Za-z0-9_-]{4,64}", job_id):
        raise HTTPException(404)
    result = await asyncio.to_thread(history.load_result, job_id)
    if not result:
        raise HTTPException(404, "Profil kaydı bulunamadı.")
    prof = result.get("profile") or {}
    return {"person": {k: prof.get(k) or "" for k in ("name", "title", "institution", "department")},
            "docentlik": academic_score.docentlik(result), "tesvik": academic_score.tesvik(result, year)}


@router.get("/advisors")
async def advisor_search(q: str = Query(..., min_length=3, max_length=400), uni: str = Query("", max_length=80), mode: str = "tez"):
    mode = "2209" if mode == "2209" else "tez"
    if mode == "2209" and not uni:
        raise HTTPException(422, "2209-A için kendi üniversiteni seç.")
    english = ""
    if not q.isascii():
        try:
            english = await asyncio.wait_for(library._translate(q, await LLM().probe()), 25)
        except Exception:  # noqa: BLE001  çeviri yoksa Türkçe metinle aranır
            english = ""
    try:
        return await advisors.find(q, uni, mode, english)
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"Kaynağa ulaşılamadı ({type(exc).__name__}).") from None
