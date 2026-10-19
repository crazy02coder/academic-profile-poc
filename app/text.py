"""Türkçe-duyarlı metin normalizasyonu, isim eşleme, unvan ve dil tespiti."""
from __future__ import annotations

import html
import re
import unicodedata

from langdetect import DetectorFactory, detect_langs

DetectorFactory.seed = 0

_TR_MAP = str.maketrans({"İ": "i", "I": "ı", "Ş": "ş", "Ğ": "ğ", "Ü": "ü", "Ö": "ö", "Ç": "ç"})
_ASCII_MAP = str.maketrans({"ı": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c", "â": "a", "î": "i", "û": "u"})

ACADEMIC_TITLES = [
    # (regex, normalize edilmiş Türkçe unvan) — uzun olan önce
    (r"prof(?:es[öo]r)?\.?\s*dr\.?", "Prof. Dr."),
    (r"do[çc](?:ent)?\.?\s*dr\.?", "Doç. Dr."),
    (r"dr\.?\s*[öo]ğ?r(?:etim)?\.?\s*[üu]y(?:esi)?\.?", "Dr. Öğr. Üyesi"),
    (r"doktor\s+[öo]ğretim\s+[üu]yesi", "Dr. Öğr. Üyesi"),
    (r"[öo]ğ?r(?:etim)?\.?\s*g[öo]r(?:evlisi)?\.?\s*dr\.?", "Öğr. Gör. Dr."),
    (r"[öo]ğ?r(?:etim)?\.?\s*g[öo]r(?:evlisi)?\.?", "Öğr. Gör."),
    (r"ar[şs](?:t[ıi]rma)?\.?\s*g[öo]r(?:evlisi)?\.?\s*dr\.?", "Arş. Gör. Dr."),
    (r"ar[şs](?:t[ıi]rma)?\.?\s*g[öo]r(?:evlisi)?\.?", "Arş. Gör."),
    (r"profes[öo]r", "Prof. Dr."),
    (r"do[çc]ent", "Doç. Dr."),
    (r"assoc(?:iate)?\.?\s*prof(?:essor)?\.?(?:\s*dr\.?)?", "Doç. Dr."),
    (r"assist(?:ant)?\.?\s*prof(?:essor)?\.?(?:\s*dr\.?)?|asst\.?\s*prof\.?(?:\s*dr\.?)?", "Dr. Öğr. Üyesi"),
    (r"prof(?:essor)?\.?(?:\s*dr\.?)?", "Prof. Dr."),
    (r"research\s+assistant", "Arş. Gör."),
    (r"lecturer|instructor", "Öğr. Gör."),
    (r"[öo]ğretim\s+[üu]yesi", "Öğretim Üyesi"),
    (r"[öo]ğretim\s+g[öo]revlisi", "Öğr. Gör."),
]
_TITLE_RES = [(re.compile(rf"(?<![\w]){p}(?![\w])", re.I), n) for p, n in ACADEMIC_TITLES]


def clean(value) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value)).replace("\xa0", " ").replace("​", "")
    return re.sub(r"\s+", " ", text).strip()


def lower_tr(value: str) -> str:
    return clean(value).translate(_TR_MAP).lower()


def fold(value: str) -> str:
    """Büyük/küçük harf ve Türkçe karakter duyarsız ASCII anahtar."""
    text = lower_tr(value).translate(_ASCII_MAP)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def strip_titles(name: str) -> str:
    text = clean(name)
    for rx, _ in _TITLE_RES:
        text = rx.sub(" ", text)
    return re.sub(r"\s+", " ", re.sub(r"^[\s,.;:-]+|[\s,.;:-]+$", "", text)).strip()


def detect_title(text: str) -> str:
    """Metinde geçen ilk akademik unvanı (en uzun eşleşme önceliğiyle) döndürür."""
    best: tuple[int, int, str] | None = None
    for rx, normalized in _TITLE_RES:
        m = rx.search(text or "")
        if m:
            key = (m.start(), -(m.end() - m.start()), normalized)
            if best is None or key < best:
                best = key
    return best[2] if best else ""


def name_tokens(name: str) -> list[str]:
    return [t for t in fold(strip_titles(name)).split() if len(t) > 1]


def name_in_text(name: str, text: str) -> bool:
    """Tüm ad parçaları metinde kelime olarak geçiyor mu? (sıra bağımsız)"""
    tokens = name_tokens(name)
    if not tokens:
        return False
    words = set(fold(text).split())
    return all(t in words for t in tokens)


def name_score(expected: str, candidate: str) -> float:
    """0..1 — soyad eşleşmesi zorunlu, ad/ikinci ad toleranslı."""
    a, b = name_tokens(expected), name_tokens(candidate)
    if not a or not b:
        return 0.0
    if a[-1] not in b:
        # 'Şimşek M.' biçimi veya çift soyad için son token tüm adayda aransın
        if not any(a[-1] == t for t in b):
            return 0.0
    hits = 0.0
    for t in a[:-1]:
        if t in b:
            hits += 1
        elif any(x[:1] == t[:1] and len(x) <= 2 for x in b):  # baş harf
            hits += 0.6
    first_part = hits / max(1, len(a) - 1) if len(a) > 1 else 1.0
    extra = max(0, len(b) - len(a)) * 0.05
    return max(0.0, min(1.0, 0.5 + 0.5 * first_part - extra))


TR_CHARS = set("çğıöşüÇĞİÖŞÜ")


def detect_language(title: str, abstract: str = "") -> tuple[str, float]:
    """(iso-kod, güven). Kısa başlıklar için Türkçe karakter sezgisi eklenir."""
    text = clean(f"{title}. {abstract[:600]}")
    if len(text) < 8:
        return "und", 0.0
    tr_hits = sum(ch in TR_CHARS for ch in title)
    try:
        langs = detect_langs(text)
    except Exception:  # noqa: BLE001
        langs = []
    top = langs[0] if langs else None
    if tr_hits >= 2 and (not top or top.lang != "tr"):
        return "tr", 0.75
    # ASCII'ye dökülmüş Türkçe başlıklar (ç/ş/ğ yok): işlev kelimesi + ek ipuçları
    words = fold(title).split()
    cues = sum(w in {"ve", "ile", "icin", "bir", "uzerine", "uzerinde", "olarak", "yontemi", "kullanarak"} for w in words)
    suffixy = sum(bool(re.search(r"(lari|leri|nin|nın|sinin|ması|mesi|lik|ligi|inde|inda)$", w)) for w in words)
    if (cues + suffixy) >= 2 and (not top or top.lang in {"az", "tk", "tr", "uz", "id", "so", "sw", "fi", "et", "hu"}):
        return "tr", 0.7
    if top and top.lang in {"az", "tk"} and tr_hits:
        return "tr", round(top.prob, 2)
    if top is None:
        return "und", 0.0
    if top.prob < 0.6 and len(text) < 60:
        return "und", round(top.prob, 2)
    return top.lang, round(top.prob, 2)


LANG_NAMES = {"tr": "Türkçe", "en": "İngilizce", "de": "Almanca", "fr": "Fransızca", "es": "İspanyolca",
              "it": "İtalyanca", "ru": "Rusça", "ar": "Arapça", "fa": "Farsça", "und": "Belirsiz"}


def doi_key(value: str | None) -> str:
    if not value:
        return ""
    m = re.search(r"10\.\d{4,9}/\S+", str(value), re.I)
    return m.group(0).rstrip(".,;)").lower() if m else ""


def title_key(title: str) -> str:
    return fold(title)


STOP = set(
    "a an the of in on for and or to with by from at as is are using based via into its their this that "
    "ve ile bir bu icin olarak uzerine uzerinde da de ki veya gibi olan nasil hangi nedir mi mu midir "
    "hakkinda neler kim kimler ne en cok daha".split()
)

# ------------------------------------------------------------ Türkçe optimizasyonu
# Eklemeli Türkçe için hafif kök bulucu: katlanmış (ASCII) token üzerinde en uzun ek
# soyulur, kök en az 4 harf kalır. Tam morfolojik analiz değildir; arama/eşleştirme
# için "siniflandirmasi ~ siniflandirma", "aglarinda ~ ag" gibi recall kazandırır.
_TR_SUFFIXES = sorted(set(
    "lerinden larindan lerinde larinda lerini larini lerine larina leriyle lariyla "
    "sinin sinin sinda sinde sindan sinden siyla siyle "
    "lerin larin leri lari ler lar "
    "nin nin nun nun in in un un "
    "den dan ten tan de da te ta "
    "yle yla ile "
    "si su sı i u "
    "ligi likleri lik luk lugu "
    "mesi masi me ma "
    "yi yu ye ya".split()), key=len, reverse=True)


def stem_tr(token: str) -> str:
    t = token
    for _ in range(2):  # en fazla iki ek katmanı
        for suf in _TR_SUFFIXES:
            if t.endswith(suf) and len(t) - len(suf) >= 4:
                t = t[: -len(suf)]
                break
        else:
            break
    return t


# TR↔EN akademik terim sözlüğü (köklenmiş TR → EN). Çapraz dil eşleştirme ve
# Türkçe soru → İngilizce özet aramasında sorgu genişletme için kullanılır.
TR_EN = {
    "yapay": "artificial", "zeka": "intelligence", "makine": "machine", "ogren": "learning", "ogrenme": "learning",
    "derin": "deep", "goruntu": "image", "isleme": "processing", "isle": "processing", "sinifland": "classification",
    "siniflandirma": "classification", "tespit": "detection", "tani": "diagnosis", "ag": "network", "sinir": "neural",
    "evrisim": "convolutional", "evrisimli": "convolutional", "analiz": "analysis", "yontem": "method", "veri": "data",
    "madencilig": "mining", "madencili": "mining", "dogal": "natural", "dil": "language", "tahmin": "prediction",
    "sistem": "system", "uygulama": "application", "guvenlik": "security", "hiperspektral": "hyperspectral",
    "uzaktan": "remote", "algilama": "sensing", "karar": "decision", "destek": "support", "optimizasyon": "optimization",
    "egitim": "education", "saglik": "health", "enerji": "energy", "kontrol": "control", "duygu": "sentiment",
    "muzik": "music", "degerlendir": "evaluation", "karsilastir": "comparison", "gercek": "real", "zaman": "time",
    "hedef": "target", "ozetle": "summarization", "metin": "text", "robot": "robot", "otonom": "autonomous",
    "tedarik": "supplier", "secim": "selection", "kumele": "clustering", "kumeleme": "clustering", "tibbi": "medical",
    "hastalik": "disease", "kanser": "cancer", "beyin": "brain", "goru": "vision", "bilgisayar": "computer",
    "cozunurluk": "resolution", "sinyal": "signal", "ag trafik": "traffic", "trafik": "traffic", "saldiri": "attack",
    "atif": "citation", "yayin": "publication", "makale": "article", "dergi": "journal", "yil": "year",
    "bildiri": "proceedings", "ortak": "co", "yazar": "author", "model": "model", "buyuk": "large",
}
EN_TR = {v: k for k, v in TR_EN.items()}


def content_tokens(text: str, stem: bool = True) -> list[str]:
    out = []
    for t in fold(text).split():
        if len(t) <= 2 or t in STOP:
            continue
        out.append(stem_tr(t) if stem else t)
    return out


def _tr_lookup(token: str) -> str | None:
    if token in TR_EN:
        return TR_EN[token]
    best = None
    for k, v in TR_EN.items():  # kök ↔ sözlük girdisi iki yönlü önek eşleşmesi
        if len(k) >= 4 and len(token) >= 4 and (token.startswith(k) or k.startswith(token)):
            if best is None or len(k) > len(best[0]):
                best = (k, v)
    return best[1] if best else None


def expand_bilingual(tokens: list[str]) -> list[str]:
    """Türkçe sorgu tokenlarına İngilizce karşılıklarını (ve tersini) ekler."""
    out = list(tokens)
    for t in tokens:
        en = _tr_lookup(t)
        if en:
            out.append(en)
        elif t in EN_TR:
            out.append(EN_TR[t])
    return out
