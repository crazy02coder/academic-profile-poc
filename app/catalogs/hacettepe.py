"""Hacettepe Üniversitesi — Proliz OBS Bologna bilgi paketi (bilsis.hacettepe.edu.tr/oibs/bologna).

Ayrıştırma ortak `proliz` modülündedir (program listesi 2 istek, ders planı 1 istek, ders içeriği 1 istek; hepsi düz
GET). Burada yalnız Hacettepe'ye özgü ad temizliği var: liste adları büyük harfli, sonunda birim kodu taşıyan ve
kısaltmalı yazılmış ("ELEKTRİK-ELEKTRONİK MÜH. (357)", "İKTİSAT (İNG.) (374)", "HUKUK FAKÜLTESİ (%30 İngilizce)(766)").
"""
from __future__ import annotations

import re

from . import base, proliz

DOMAINS = ("hacettepe.edu.tr",)
BASE = "https://bilsis.hacettepe.edu.tr/oibs/bologna/"

_CODE = re.compile(r"\s*\(\s*(?:\d+|TAU)\s*\)\s*$", re.I)  # sondaki birim kodu; "(TAU)" Türk-Alman Üniv. ortak programı
_SHORT = [(r"\bMüh\.", "Mühendisliği"), (r"\bÖğrt\.", "Öğretmenliği"), (r"\bTekn\.", "Teknolojileri"),
          (r"\bBil\.\s*Fak\.", "Bilimler Fakültesi"), (r"\s+Pr\.", "")]


def _clean(raw: str) -> str:
    """Kod ve kısaltmalardan arındırılmış, Türkçe büyük/küçük harfli ad; dil varyantı sonda '(İngilizce)' biçiminde."""
    name = _CODE.sub("", base.txt(raw))
    variant = ""
    tail = re.search(r"\s*\(([^()]*)\)$", name)
    if tail:
        name, inner = name[:tail.start()], tail[1].strip()
        key = base.fold(inner)
        if "ing" in key or "english" in key:
            percent = re.search(r"%\s*(\d+)", inner)
            variant = f" (%{percent[1]} İngilizce)" if percent and percent[1] != "100" else " (İngilizce)"
        elif key not in {"turkce", "turkish"}:
            variant = f" ({proliz._title(inner)})"
    name = proliz._title(_CODE.sub("", name))
    for pattern, full in _SHORT:
        name = re.sub(pattern, full, name)
    return base.txt(name) + variant


def _program_name(raw: str) -> str:
    """Tek programlı fakültelerde program fakülte adıyla listelenir: 'Hukuk Fakültesi (%30 İngilizce)' → 'Hukuk (…)'."""
    return re.sub(r"\s+(?:Fakültesi|Faculty)\b", "", _clean(raw))


async def programs(http) -> list[dict]:
    rows = await proliz.programs(http, BASE)
    for row in rows:
        row["name"], row["faculty"] = _program_name(row["name"]), _clean(row["faculty"])
        # İngilizce listede dil varyantı çoğu kez yazılmaz ("LAW" hem Hukuk hem Hukuk (%30 İngilizce)); varyantsız
        # takma ad yanlış programla eşleşmesin diye Türkçe addaki varyant takma ada da eklenir.
        variant = re.search(r" \((?:%\d+ )?İngilizce\)$", row["name"])
        aliases = [_program_name(alias) for alias in row.get("aliases") or []]
        aliases = [alias + variant[0] if variant and alias and not alias.endswith(")") else alias for alias in aliases]
        row["aliases"] = [alias for alias in dict.fromkeys(aliases) if alias and alias != row["name"]]
    return rows


courses, detail = proliz.courses, proliz.detail
