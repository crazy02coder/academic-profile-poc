"""Kütüphane için ortak başlık, kategori ve atomik önbellek yardımcıları."""
from __future__ import annotations
import html
import json
import re
import uuid
from pathlib import Path

CATEGORY_MAP = {
    "muhendislik": ("Mühendislik", "#334155", "engineering technology computer software artificial intelligence mühendis yazılım bilgisayar sanayi"),
    "tip": ("Tıp ve Sağlık", "#7f354b", "medicine medical health nursing clinical tıp sağlık hastalık"),
    "sosyal": ("Sosyal Bilimler", "#695a88", "social sociology psychology politics sosyal sosyoloji psikoloji siyaset"),
    "temel": ("Fen Bilimleri", "#4338ca", "science physics chemistry mathematics biology fizik kimya matematik biyoloji"),
    "sanat": ("Sanat ve Edebiyat", "#7b426b", "art literature poetry music language sanat edebiyat şiir müzik dil"),
    "tarih": ("Tarih", "#78563d", "history archaeology tarih arkeoloji"),
    "egitim": ("Eğitim", "#3d6474", "education teaching learning eğitim öğretim"),
    "hukuk": ("Hukuk ve Ekonomi", "#455d46", "law economics business hukuk ekonomi işletme"),
    "klasikler": ("Klasikler", "#62534d", "classics fiction novel klasik roman"),
    "genel": ("Genel", "#52525b", "general genel"),
}
GREEK = dict(zip("alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma tau upsilon phi chi psi omega".split(), "αβγδεζηθικλμνξοπρστυφχψω"))
SUPER = str.maketrans("0123456789+-=()ni", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ")
SUB = str.maketrans("0123456789+-=()aehijklmnoprstuvx", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ")

def clean_title(value: str) -> str:
    value = html.unescape(str(value or ""))
    value = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", "", value, flags=re.S | re.I)
    value = re.sub(r"<sup[^>]*>(.*?)</sup>", lambda m: m[1].translate(SUPER), value, flags=re.I)
    value = re.sub(r"<sub[^>]*>(.*?)</sub>", lambda m: m[1].translate(SUB), value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    for _ in range(4):
        value = re.sub(r"\\(?:hbox|mathrm|text|textrm|mathbf|mathit)\s*\{([^{}]*)\}", r"\1", value)
        value = re.sub(r"\\sqrt\s*\{([^{}]*)\}", r"√\1", value)
        value = re.sub(r"\^\s*\{([^{}]*)\}", lambda m: m[1].translate(SUPER), value)
        value = re.sub(r"_\s*\{([^{}]*)\}", lambda m: m[1].translate(SUB), value)
    symbols = GREEK | {"rightarrow": "→", "leftarrow": "←", "pm": "±", "times": "×", "cdot": "·", "leq": "≤", "geq": "≥", "infty": "∞"}
    value = re.sub(r"\\([a-zA-Z]+)", lambda m: symbols.get(m[1], ""), value)
    value = re.sub(r"\^([\w+-])", lambda m: m[1].translate(SUPER), value)
    value = re.sub(r"_([\w+-])", lambda m: m[1].translate(SUB), value)
    return re.sub(r"\s+", " ", re.sub(r"[${}\\]", "", value)).strip().rstrip(". ")

def category_for(text: str) -> str:
    text = str(text).lower()
    scored = [(sum(text.count(word) for word in spec[2].split()), key) for key, spec in CATEGORY_MAP.items()]
    score, key = max(scored)
    return key if score else "genel"

def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
