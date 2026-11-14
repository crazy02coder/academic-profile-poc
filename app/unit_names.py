"""Bir bağlantı metni gerçekten bölüm/program adı mı?

Üniversite sitelerinde fakülte sayfasındaki "bölüm" bağlantıları duyuru ve program başlıklarıyla karışır
("Socrates-Erasmus Programı", "Akademik Destek Programı", "Bölümlerimiz", "… Bölümü 2025 öğrenci alımı").
Siteye özel kural yok: (1) yerel YÖK kayıtlarında görülmüş bölüm adları sözlüğü, (2) ad yapısı (… Mühendisliği,
… Bilimleri, … Bölümü), (3) bölüm adında bulunmayan kelimeler. Ağa istek atmaz.
"""
from __future__ import annotations

import json
import re
import time

from .config import ROOT
from .text import clean, fold

YOK_DIR = ROOT / "data" / "yok"
VOCAB_FILE = ROOT / "data" / "student-view" / "_unit_vocab.json"
VOCAB_TTL = 24 * 3600

# Bölüm adında geçmeyen, duyuru/menü/ofis bağlantılarında geçen kelimeler (katlanmış metin üzerinde).
NOISE = re.compile(
    r"\d|fakulte|yuksekokul|enstitu|dekan|baskanlig|mudurlu|rektor|bulten|kayit|sinav|duyuru|\bhaber(?:ler)?\b|etkinlik|"
    r"erasmus|farabi|mevlana|degisim|oryantasyon|iftar|\bdestek\b|hizmet ici|kampus|\bsektor\b|akreditasyon|komisyon|"
    r"\bkurul|koordinator|ofisi\b|\bofis$|merkez|web sayfa|ders program|yedek|siralama|basvuru|kontenjan|sonuc|mezun|"
    r"ogrenci|personel|kadro|hakkinda|hakkimizda|^iletisim$|ana ?sayfa|bolumlerimiz|^bolumler$|^programlar$|"
    r"anabilim dallari|takvim|yonetmelik|yonerge|\bform(?:lar)?\b|toplanti|seminer|konferans|kongre|calistay|\bpanel\b|"
    r"odul|tebrik|ziyaret|^tanitim|tanitim (?:gun|film|video|toplan)|galeri|video|sosyal medya|kalite|strateji|rapor|ihale|\bilan|\bburs\b|\bstaj|"
    r"hazirlik|yaz okulu|sertifika|\bkurs|egitim yili|ogretim yili|akademik yil|donemi|yariyil|lisansustu|"
    r"yuksek lisans|doktora|tezli|tezsiz|graduate|admission|apply|\bnews\b|\bevents?\b|contact|\babout\b|announce")

# Bölüm adının son kelimesi (yapı): "… Mühendisliği", "… Bilimleri", "… Öğretmenliği", "… Engineering".
HEAD = re.compile(
    r"(?:muhendisligi|muhendislik|ogretmenligi|bilimleri|bilimi|bilgisi|egitimi|edebiyati|dilbilimi|iliskiler|iliskileri|"
    r"yonetimi|isletmeciligi|tasarimi|sanatlari|sanati|teknolojileri|teknolojisi|hizmetleri|terapisi|hukuku|"
    r"tercumanlik|rehberlik|danismanlik|mimarligi|planlama|ekonomisi|bilisimi|sistemleri|calismalari|"
    r"engineering|sciences?|studies|education|administration|relations|design|architecture|economics|management|"
    r"literature|law|medicine|nursing|psychology|sociology|history|philosophy|mathematics|physics|chemistry|"
    r"biology|statistics|finance|linguistics|genetics)$")

# Tek kelimelik ve yaygın bölüm adları: sözlük boşken (yeni kurulum) de çalışsın.
SEED_WORDS = """iktisat isletme hukuk tarih felsefe sosyoloji psikoloji matematik fizik kimya biyoloji istatistik mimarlik
hemsirelik ebelik tip eczacilik muzik resim heykel seramik cografya arkeoloji antropoloji ekonomi maliye
gazetecilik sinema odyoloji ergoterapi gerontoloji aktuerya ekonometri biyomuhendislik antrenorluk rekreasyon"""
SEED_PHRASES = """sanat tarihi|sosyal hizmet|halkla iliskiler|dis hekimligi|veteriner hekimligi|beslenme ve diyetetik|
fizyoterapi ve rehabilitasyon|ic mimarlik|sehir ve bolge planlama|turk dili ve edebiyati|ingiliz dili ve edebiyati|
kamu yonetimi|uluslararasi ticaret|calisma ekonomisi ve endustri iliskileri|radyo televizyon ve sinema|
bilgi ve belge yonetimi|molekuler biyoloji ve genetik|cocuk gelisimi|saglik yonetimi|turizm isletmeciligi|
gastronomi ve mutfak sanatlari|peyzaj mimarligi|ic mimarlik ve cevre tasarimi|endustriyel tasarim|grafik tasarim|
temel egitim|ozel egitim|egitim bilimleri|yabanci diller egitimi|guzel sanatlar egitimi|bilgisayar muhendisligi"""

_VOCAB: set[str] | None = None


def key(name: str) -> str:
    """Karşılaştırma biçimi: "Bilgisayar Mühendisliği Bölümü (İngilizce)" → "bilgisayar muhendisligi"."""
    text = fold(clean(name)).replace("-", " ")
    text = re.sub(r"[()%.,/]|\b(?:bolumu|bolum|anabilim dali|ana bilim dali|programi|pr|ve|and|of|department|"
                  r"ingilizce|turkce|english|turkish|tam burslu|burslu|ucretli|ikinci ogretim|uzaktan ogretim|"
                  r"indirimli|acik ?ogretim)\b", " ", text)
    return " ".join(text.split())


def _build() -> set[str]:
    words = {key(x) for x in SEED_WORDS.split()} | {key(x) for x in SEED_PHRASES.replace("\n", " ").split("|") if x.strip()}
    if YOK_DIR.exists():
        for path in YOK_DIR.glob("*.json"):
            kind = path.name.split("-")[0]
            try:
                if kind in {"unistaff", "people2", "depstaff", "staff"}:
                    for found in re.findall(r'"department(?:_raw)?":\s*"([^"\\]{3,90})"', path.read_text(encoding="utf-8")):
                        words.add(key(found))
                elif kind in {"deps4", "deps3", "depsall"} and not path.name.endswith("-links.json"):
                    data = json.loads(path.read_text(encoding="utf-8")).get("data")
                    words |= {key(x) for x in (data if isinstance(data, (dict, list)) else []) if isinstance(x, str)}
            except (OSError, ValueError):
                continue
    return {w for w in words if 2 < len(w) < 80 and not NOISE.search(w)}


def vocab() -> set[str]:
    """Bilinen bölüm adları (karşılaştırma biçiminde). Günde bir yeniden kurulur; dosyada saklanır."""
    global _VOCAB
    if _VOCAB is None:
        try:
            saved = json.loads(VOCAB_FILE.read_text(encoding="utf-8"))
            if time.time() - saved["ts"] < VOCAB_TTL:
                _VOCAB = set(saved["words"])
        except (OSError, ValueError, KeyError, TypeError):
            pass
        if _VOCAB is None:
            _VOCAB = _build()
            _save()
    return _VOCAB


def _save() -> None:
    try:
        VOCAB_FILE.parent.mkdir(parents=True, exist_ok=True)
        VOCAB_FILE.write_text(json.dumps({"ts": time.time(), "words": sorted(_VOCAB or ())}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def add(names) -> None:
    """YÖK'ten gelen bölüm adları sözlüğe hemen eklenir (aynı oturumda diğer fakültelerin site listesi doğrulanır)."""
    words = vocab()
    new = {key(n) for n in names or [] if isinstance(n, str)} - words
    new = {w for w in new if 2 < len(w) < 80}
    if new:
        words |= new
        _save()


def is_noise(name: str) -> bool:
    """Bölüm adı olamayacak bağlantı metni (duyuru, ofis, menü başlığı, lisansüstü program…)."""
    text = fold(clean(name)).replace("-", " ")
    return len(text) < 3 or len(text.split()) > 7 or bool(NOISE.search(text))


def looks_like_department(name: str) -> bool:
    """Gerçek bölüm/program adı mı: gürültü kelimesi yok ve (sözlükte var | "… Bölümü/Anabilim Dalı" | yapısı uygun)."""
    if is_noise(name):
        return False
    text = fold(clean(name)).replace("-", " ")
    short = key(name)
    if not short:
        return False
    if short in vocab() or re.search(r"(?:bolumu|anabilim dali|ana bilim dali)$", text):
        return True
    return bool(HEAD.search(short))
