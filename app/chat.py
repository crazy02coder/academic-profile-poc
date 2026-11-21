"""Profil sohbeti: kişinin bilgi tabanı doğrudan modele verilir.

Bilgi tabanı (profil, istatistik, analiz, bütün yayınlar ve özetler) sistem talimatından sonra sabit bir önek olarak
gönderilir; önek her soruda bayt bayt aynı olduğundan sağlayıcının örtük önbelleği tekrarlarda kullanılır. Ayrı bir
getirme (arama, gömme vektörü) adımı yoktur. Bilgi tabanı CHAT_BUDGET_TOKENS sınırını aşarsa yayın listesinin tamamı
korunur, özetler listedeki sırayla sığdığı kadar eklenir.
"""
from __future__ import annotations

import logging
import os
import re
from collections import Counter
from typing import AsyncIterator

from .text import fold

# Modele verilen bilgi tabanının üst sınırı (ücretsiz katmanın dakika token sınırını zorlamamak için).
BUDGET_TOKENS = int(os.getenv("CHAT_BUDGET_TOKENS", "30000"))
logger = logging.getLogger(__name__)

SYSTEM = ("Sen 'Akademik İz' asistanısın. Kullanıcı tek bir akademisyen hakkında soru soruyor. Türkçe, kısa ve net "
          "cevap ver. Önce verilen BİLGİ TABANI'na dayan; bir yayına dayanan her cümlenin sonuna [P#] koy. "
          "Soru bilgi tabanında doğrudan yoksa cevapsız bırakma: bilgi tabanındaki verilerden akıl yürüterek çıkarım yap "
          "(ör. yaş sorulursa lisans/doktora yıllarından yaklaşık bir aralık hesapla ve hesabı bir cümleyle göster) ya da "
          "yaygın bilinen genel bilgini kullan; böyle cümlelerde bunun 'tahmin' ya da 'genel bilgi' olduğunu açıkça yaz. "
          "Bilgi tabanında olmayan yayın, proje, ödül, tarih ya da sayı uydurma. Çıkarım yapacak hiçbir dayanak yoksa "
          "bunu söyle ve kullanıcının neye bakabileceğini öner. E-posta/telefon verme.")


def est_tokens(text: str) -> int:
    return max(1, len(text) // 3)  # Türkçe/İngilizce karışık metin için kaba tahmin


class Knowledge:
    """Bir profil sonucunun sohbet için hazırlanmış hali (iş başına bir kez kurulur)."""

    def __init__(self, result: dict):
        self.result = result
        self.prof = result["profile"]
        self.papers = result["publications"]
        self.core = self._core()
        self.full = self._full()

    # ---------------------------------------------------------------- bilgi tabanı metinleri
    def _header(self) -> list[str]:
        prof, papers, an = self.prof, self.papers, self.result["analysis"]
        years = Counter(p["year"] for p in papers if p["year"])
        top_cited = sorted([p for p in papers if p.get("citations")], key=lambda p: -p["citations"])[:8]
        me = fold(prof["name"]).split()
        coauth = Counter(a for p in papers for a in p.get("authors") or []
                         if fold(a) and not all(t in fold(a).split() for t in me))
        ver = prof.get("verification") or {}
        return [
            f"AD: {prof['name']} | UNVAN: {prof.get('title')} | BÖLÜM: {prof.get('department')} | "
            f"KURUM: {prof.get('institution')} | ORCID: {prof.get('orcid') or '-'}",
            "DOĞRULAMA: " + "; ".join(f"{k}={v.get('status')}({'+'.join(v.get('sources', []))})"
                                      for k, v in ver.items() if k != "interests"),
            f"İLGİ ALANLARI: {', '.join(prof.get('interests') or [])}",
            self._h_index_line(),
            f"YAYIN SAYISI: {len(papers)} benzersiz ({self.result.get('raw_count')} ham kayıt) | YILLARA GÖRE: "
            + ", ".join(f"{y}:{c}" for y, c in sorted(years.items())),
            f"ANALİZ ÖZETİ: {an.get('summary', '')}",
            "ALANLAR: " + "; ".join(f"{a['label']} [{','.join(a['evidence'])}]" for a in an.get("areas", [])),
            "YÖNTEMLER: " + "; ".join(f"{a['label']} [{','.join(a['evidence'])}]" for a in an.get("methods", [])),
            "ODAK DEĞİŞİMİ: " + "; ".join(f"{t['period']}: {t['text']}" for t in an.get("timeline", [])),
            "EN ÇOK ATIF: " + "; ".join(f"[{p['id']}] {p['citations']}" for p in top_cited),
            "SIK ORTAK YAZARLAR: " + ", ".join(f"{a} ({c})" for a, c in coauth.most_common(10)),
            *self._yok_lines(),
        ]

    def _h_index_line(self) -> str:
        """Kaynaklar farklı yayınları saydığı için değerler tek sayıya indirilmez."""
        meta = (self.result.get("recon") or {}).get("sources_meta") or {}
        values = [f"{label}={meta[k]['h_index']}" for k, label in (("scholar", "Google Scholar"), ("openalex", "OpenAlex"))
                  if (meta.get(k) or {}).get("h_index") is not None]
        return ("H-INDEX (kaynağa göre; değerleri kaynak adıyla ver, Web of Science/Scopus değeri yok): "
                + ("; ".join(values) or "toplanan veride yok"))

    def _yok_lines(self) -> list[str]:
        """YÖK profilindeki yayın dışı bilgiler: sohbet 'hangi dersleri veriyor?' gibi sorulara cevap verebilsin."""
        yok = self.prof.get("yok") or {}
        if not yok and not self.result.get("industry"):
            return []

        def timeline(items):
            return "; ".join(f"{x['period']} {x['role']} — {x['place']} {x['unit']}".strip() for x in items)

        def rows(items, limit=40):
            return "; ".join(" | ".join(str(v) for k, v in r.items() if v and k not in ("url", "group")) for r in items[:limit])

        sec = yok.get("sections") or {}
        out = [f"YÖK GÖREV GEÇMİŞİ: {timeline(yok.get('career') or [])}",
               f"YÖK ÖĞRENİM: {timeline(yok.get('education') or [])}"]
        for key, label in (("admin", "İDARİ GÖREVLER"), ("courses", "VERDİĞİ DERSLER"), ("theses", "YÖNETTİĞİ TEZLER"),
                           ("projects", "PROJELER"), ("awards", "ÖDÜLLER"), ("patents", "PATENTLER"),
                           ("memberships", "ÜYELİKLER"), ("experience", "ÜNİVERSİTE DIŞI DENEYİM"), ("art", "SANATSAL")):
            if sec.get(key):
                out.append(f"YÖK {label} ({len(sec[key])}): {rows(sec[key])}")
        if yok.get("collaborators"):
            out.append("YÖK BİRLİKTE ÇALIŞTIĞI KİŞİLER: " + "; ".join(
                f"{c['title']} {c['name']} ({c['institution']})" for c in yok["collaborators"]))
        if yok.get("tr_projects"):
            out.append(f"TR DİZİN TÜBİTAK PROJELERİ ({len(yok['tr_projects'])}): " + "; ".join(
                f"{p['year'] or '?'} {p['title']} ({p['role']}{', ' + p['group'] if p['group'] else ''})" for p in yok["tr_projects"]))
        for e in self.result.get("industry") or []:
            out.append(f"SANAYİ İŞ BİRLİĞİ: {e['name']}"
                       f"{' (resmi ' + '/'.join(e['kinds']) + ', ' + ', '.join(e['cities'][:3]) + ')' if e['official'] else ''} — "
                       + "; ".join(f"{ev['type']}: {ev['text']}" + (f" [{ev['pub']}]" if ev['pub'] else "") for ev in e["evidence"][:6]))
        tez = yok.get("tez_merkezi") or {}
        for key, label in (("own", "KENDİ TEZLERİ"), ("advised", "DANIŞMANLIK YAPTIĞI TEZLER")):
            if tez.get(key):
                out.append(f"YÖK TEZ MERKEZİ {label} ({len(tez[key])}): " + "; ".join(
                    f"{t['year']} {t['type']} — {t['title']} — {t['author']} ({t['university']})" for t in tez[key]))
        return out

    def _core(self) -> str:
        lines = self._header() + ["", "TÜM YAYINLAR (kimlik, yıl, dergi, atıf, dil, kaynak):"]
        for p in self.papers:
            lines.append(f"[{p['id']}] {p['year'] or '?'} | {p['title']} | {p.get('venue') or '-'} | atıf "
                         f"{p.get('citations') or 0} | {'/'.join(p.get('languages', []))} | {'+'.join(p.get('sources', []))}"
                         + (f" | dergi çeyreği {p['quartile']['source']} {p['quartile']['year']}: "
                            + ", ".join(f"{c['name']} {c['q']}" for c in p["quartile"]["categories"]) if p.get("quartile") else ""))
        return "\n".join(lines)

    def _full(self) -> str:
        """Çekirdek + yayın özetleri. Bütçe aşılırsa özetler listedeki sırayla sığdığı kadar eklenir; kalanların
        yalnız künyesi (çekirdekteki satırı) modele gider."""
        lines, used, left = [self.core, "", "YAYIN ÖZETLERİ:"], est_tokens(self.core), 0
        for p in self.papers:
            if not p.get("abstract"):
                continue
            line = f"[{p['id']}] {p['abstract'][:900]}"
            if used + est_tokens(line) > BUDGET_TOKENS:
                left += 1
                continue
            used += est_tokens(line)
            lines.append(line)
        if left:
            lines.append(f"(Bağlam sınırı nedeniyle {left} yayının özeti eklenmedi; künyeleri yukarıdaki listededir.)")
        self.trimmed = left
        return "\n".join(lines)



async def answer(kb: Knowledge, question: str, history: list[dict], llm, meta: dict, on_stage=None) -> AsyncIterator[str]:
    """Bilgi tabanını önek olarak verip cevabı akıtır; `meta`ya ölçümleri yazar."""
    prefix = SYSTEM + "\n\nBİLGİ TABANI:\n" + kb.full
    meta.update({"context_tokens": est_tokens(prefix), "trimmed_abstracts": kb.trimmed})

    if llm.available:
        if on_stage:
            await on_stage("Model cevabı hazırlıyor…")
        messages = [{"role": "system", "content": prefix}]
        for h in history[-6:]:
            if h.get("role") in ("user", "assistant") and h.get("content"):
                messages.append({"role": h["role"], "content": str(h["content"])[:2000]})
        messages.append({"role": "user", "content": "SORU: " + question})
        stats: dict = {}
        try:
            async for piece in llm.stream_chat(messages, stats, fast=True):
                yield piece
            meta.update(stats)
            if stats.get("prompt_tokens"):
                meta["context_tokens"] = stats["prompt_tokens"]  # tahmin yerine gerçek sayı
            meta["model"] = stats.get("model") or llm.model
            return
        except Exception as exc:  # noqa: BLE001
            meta["model_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
            logger.exception("Model profil sohbetine cevap veremedi")
            yield "\n\n_(Model yanıt vermedi; kural tabanlı cevap:)_\n\n"
    meta["model"] = "mock"
    for piece in _mock_answer(kb, question):
        yield piece


def _mock_answer(kb: Knowledge, question: str) -> list[str]:
    prof, papers = kb.prof, kb.papers
    q = fold(question)
    if re.search(r"h ?ind(ex|eks)", q):
        return ["h-index: " + kb._h_index_line().split(": ", 1)[1] + "."]
    if re.search(r"kac|sayi|how many|toplam", q):
        years = Counter(p["year"] for p in papers if p["year"])
        return [f"{prof['name']} için {len(papers)} benzersiz yayın bulundu. Yıllara göre: "
                + ", ".join(f"{y}: {c}" for y, c in sorted(years.items())) + "."]
    if re.search(r"atif|cited|citation|etkili", q):
        top = sorted([p for p in papers if p.get("citations")], key=lambda p: -p["citations"])[:5]
        return ["En çok atıf alan yayınlar:\n" + "\n".join(f"- {p['title']} — {p['citations']} atıf [{p['id']}]" for p in top)]
    if re.search(r"son|guncel|latest|recent|yeni", q):
        return ["En güncel yayınlar:\n" + "\n".join(f"- ({p['year']}) {p['title']} [{p['id']}]" for p in papers[:5])]
    # Yapay zekâ kapalıyken soru anlaşılamaz: başlığında sorudaki kelimeler geçen yayınlar, yoksa en yeniler.
    words = {w for w in q.split() if len(w) > 3}
    hits = [p for p in papers if words & set(fold(p["title"]).split())][:5] or papers[:5]
    return ["Yapay zekâ kapalı; soruyla ilgili olabilecek yayınlar:\n"
            + "\n".join(f"- ({p['year'] or '?'}) {p['title']} [{p['id']}]" for p in hits)]
