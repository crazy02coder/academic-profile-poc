"""OSTİM Teknik Üniversitesi — Proliz OBS Bologna bilgi paketi (obs.ostimteknik.edu.tr). Yapı ve ayrıştırma: catalogs/proliz.py.
Lisans listesi 2 istek (TR+EN adlar), bir programın ders planı 1 istek, ders içeriği ders başına 1 istek."""
from __future__ import annotations

from . import proliz

DOMAINS = ("ostimteknik.edu.tr",)
BASE = "https://obs.ostimteknik.edu.tr/oibs/bologna/"


async def programs(http) -> list[dict]:
    return await proliz.programs(http, BASE)


courses = proliz.courses
detail = proliz.detail
