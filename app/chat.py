"""Profil sohbeti: RAG, CAG ve Hibrit (CAG çekirdek + RAG ayrıntı) bilgi katmanı.

  RAG    — her soruda ilgili yayınlar getirilir: Türkçe-duyarlı BM25 + vektör araması
           (Ollama embedding) Reciprocal Rank Fusion ile birleştirilir. Bağlam küçük.
  CAG    — kişinin TÜM bilgi tabanı (profil, istatistik, analiz, bütün yayınlar ve
           özetler) sabit bir önek olarak verilir. Önek her soruda bayt bayt aynı
           olduğundan Ollama KV önbelleğini yeniden kullanır; arama hatası olmaz.
  Hibrit — CAG çekirdeği (profil + istatistik + analiz + tüm başlıklar, önbellekli)
           + soruya göre RAG ile getirilen özetler (önekten SONRA eklenir, önbelleği bozmaz).
  Otomatik — tam bilgi tabanı CAG bütçesine sığıyorsa CAG, sığmıyorsa Hibrit.
"""
from __future__ import annotations

import math
import os
import re
import time
from collections import Counter
from typing import AsyncIterator

from .text import content_tokens, expand_bilingual, fold, stem_tr

CAG_BUDGET_TOKENS = int(os.getenv("CAG_BUDGET_TOKENS", "8500"))  # 12k bağlama sığacak şekilde
MODES = {"auto": "Otomatik", "rag": "RAG", "cag": "CAG", "hybrid": "Hibrit"}

SYSTEM = ("Sen 'Akademik İz' asistanısın. Kullanıcı tek bir akademisyen hakkında soru soruyor. YALNIZCA verilen "
          "BİLGİ TABANI'ndaki bilgilere dayanarak Türkçe, kısa ve net cevap ver. Bir yayına dayanan her cümlenin "
          "sonuna [P#] koy. Bilgi tabanında olmayan bir şey sorulursa 'Toplanan veride bu bilgi yok' de; uydurma. "
          "E-posta/telefon verme.")


GLOBAL_Q = re.compile(r"\b(kac|sayi|sayisi|toplam|en cok|en az|en fazla|atif|yillara|yil yil|dagilim|kimlerle|kiminle|"
                      r"ortak yazar|birlikte|genel|alanlari|ozetle|ozet|kariyer|unvan|bolum|kurum|orcid|son yayin|"
                      r"en yeni|en son|ilk yayin|liste|tum|butun|hepsi|yonelim|odak|degisim|trend|h index|h-index|"
                      r"how many|most cited|overall|all)\b")
# Türkçe eklemeli: kökler önek olarak eşleşir ("yöntemi", "yöntemlerini" → yontem)
DETAIL_Q = re.compile(r"\b(neden|yontem|teknik|veri ?seti|dataset|deney|detay|ayrinti|anlat|acikla|ne yap|ne bul|"
                      r"bulgu|sonuc|amac|katki|mimari|algoritma|model(?:i|ini|ler)\b|how|method|approach|what did)")


def est_tokens(text: str) -> int:
    return max(1, len(text) // 3)  # Türkçe/İngilizce karışık metin için kaba tahmin


def _doc(p: dict) -> str:
    return " ".join([p["title"], *(v["title"] for v in p.get("variants", [])), p.get("venue") or "",
                     p.get("abstract", "")[:1200], " ".join(p.get("labels") or []), " ".join(p.get("authors") or [])])


class Knowledge:
    """Bir profil sonucunun sohbet için hazırlanmış hali (iş başına bir kez kurulur)."""

    def __init__(self, result: dict):
        self.result = result
        self.prof = result["profile"]
        self.papers = result["publications"]
        self.by_id = {p["id"]: p for p in self.papers}
        self.docs = [content_tokens(_doc(p)) for p in self.papers]
        self.df = Counter(t for d in self.docs for t in set(d))
        self.avg = (sum(len(d) for d in self.docs) / len(self.docs)) if self.docs else 1
        self.vectors: list[list[float]] | None = None
        self.core = self._core()
        self.full = self._full()

    # ---------------------------------------------------------------- CAG metinleri
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
            f"YAYIN SAYISI: {len(papers)} benzersiz ({self.result.get('raw_count')} ham kayıt) | YILLARA GÖRE: "
            + ", ".join(f"{y}:{c}" for y, c in sorted(years.items())),
            f"ANALİZ ÖZETİ: {an.get('summary', '')}",
            "ALANLAR: " + "; ".join(f"{a['label']} [{','.join(a['evidence'])}]" for a in an.get("areas", [])),
            "YÖNTEMLER: " + "; ".join(f"{a['label']} [{','.join(a['evidence'])}]" for a in an.get("methods", [])),
            "ODAK DEĞİŞİMİ: " + "; ".join(f"{t['period']}: {t['text']}" for t in an.get("timeline", [])),
            "EN ÇOK ATIF: " + "; ".join(f"[{p['id']}] {p['citations']}" for p in top_cited),
            "SIK ORTAK YAZARLAR: " + ", ".join(f"{a} ({c})" for a, c in coauth.most_common(10)),
        ]

    def _core(self) -> str:
        lines = self._header() + ["", "TÜM YAYINLAR (kimlik, yıl, dergi, atıf, dil, kaynak):"]
        for p in self.papers:
            lines.append(f"[{p['id']}] {p['year'] or '?'} | {p['title']} | {p.get('venue') or '-'} | atıf "
                         f"{p.get('citations') or 0} | {'/'.join(p.get('languages', []))} | {'+'.join(p.get('sources', []))}")
        return "\n".join(lines)

    def _full(self) -> str:
        lines = [self.core, "", "YAYIN ÖZETLERİ:"]
        for p in self.papers:
            if p.get("abstract"):
                lines.append(f"[{p['id']}] {p['abstract'][:900]}")
        return "\n".join(lines)

    # ----------------------------------------------------------------- RAG getirme
    def bm25(self, question: str) -> list[tuple[float, str]]:
        q = [stem_tr(t) for t in expand_bilingual(content_tokens(question))]
        n = len(self.docs)
        scores = []
        for p, d in zip(self.papers, self.docs):
            tf = Counter(d)
            s = 0.0
            for t in q:
                if t in tf:
                    idf = math.log(1 + (n - self.df[t] + 0.5) / (self.df[t] + 0.5))
                    s += idf * tf[t] * 2.2 / (tf[t] + 1.2 * (0.25 + 0.75 * len(d) / self.avg))
            if s > 0:
                scores.append((s, p["id"]))
        return sorted(scores, reverse=True)

    async def dense(self, question: str, llm) -> list[tuple[float, str]]:
        if not llm.available or not llm.embed_model or not self.papers:
            return []
        nomic = llm.embed_model.startswith("nomic")
        if self.vectors is None:
            texts = [("search_document: " if nomic else "") + _doc(p)[:1500] for p in self.papers]
            self.vectors = await llm.embed(texts) or []
        if not self.vectors:
            return []
        # İngilizce ağırlıklı embedding modelleri için TR→EN sorgu genişletme
        extra = " ".join(t for t in expand_bilingual(content_tokens(question)) if t.isascii())
        qv = await llm.embed([("search_query: " if nomic else "") + f"{question} {extra}"])
        if not qv:
            return []
        q = qv[0]
        qn = math.sqrt(sum(x * x for x in q)) or 1
        out = []
        for p, v in zip(self.papers, self.vectors):
            vn = math.sqrt(sum(x * x for x in v)) or 1
            out.append((sum(a * b for a, b in zip(q, v)) / (qn * vn), p["id"]))
        return sorted(out, reverse=True)

    async def retrieve(self, question: str, llm, k: int = 6) -> tuple[list[dict], dict]:
        """BM25 + vektör → RRF (k=60)."""
        lex = self.bm25(question)
        den = await self.dense(question, llm)
        fused: dict[str, float] = {}
        for ranking in (lex[:30], den[:30]):
            for rank, (_, pid) in enumerate(ranking):
                fused[pid] = fused.get(pid, 0.0) + 1.0 / (60 + rank + 1)
        ids = [pid for pid, _ in sorted(fused.items(), key=lambda kv: -kv[1])][:k] or [p["id"] for p in self.papers[:k]]
        info = {"retriever": "BM25+vektör (RRF)" if den else "BM25", "lexical_hits": len(lex),
                "dense": bool(den), "retrieved": ids}
        return [self.by_id[i] for i in ids], info

    def choose(self, mode: str, question: str = "") -> tuple[str, str]:
        """(yöntem, gerekçe). Elle seçim yoksa SORU TİPİNE göre yönlendirir:

          bütüne bakan (sayma, sıralama, dağılım, profil) → CAG (bütün liste gerekir)
          belirli konu/ayrıntı (bir yöntem, bir çalışma, bir terim) → RAG (birkaç yayın yeter)
          ikisi birden ("en çok atıf alan makalesinde ne yaptı") → Hibrit
        Tam bilgi tabanı CAG bütçesine sığmıyorsa CAG yerine Hibrit kullanılır.
        """
        if mode in ("rag", "cag", "hybrid"):
            return mode, "elle seçildi"
        fits = est_tokens(self.full) <= CAG_BUDGET_TOKENS
        whole = "cag" if fits else "hybrid"
        q = fold(question)
        is_global = bool(GLOBAL_Q.search(q))
        is_detail = bool(DETAIL_Q.search(q))
        hits = self.bm25(question)
        topical = bool(hits) and hits[0][0] >= 2.5  # soruda yayınlarda geçen belirgin bir konu var
        if is_global and (is_detail or topical and len(hits) <= 6):
            return "hybrid", "hem bütüne hem ayrıntıya bakan soru"
        if is_global:
            return whole, "bütüne bakan soru (sayma/sıralama/genel profil)"
        if is_detail or topical:
            return "rag", "belirli bir konu/ayrıntı sorusu"
        return whole, "genel soru"


def _details(papers: list[dict]) -> str:
    return "\n".join(f"[{p['id']}] ({p['year'] or '?'}; {p.get('venue') or '-'}; atıf {p.get('citations') or 0}) "
                     f"{p['title']} — {p.get('abstract', '')[:600]}" for p in papers)


async def answer(kb: Knowledge, question: str, history: list[dict], llm, mode: str, meta: dict) -> AsyncIterator[str]:
    """Seçilen moda göre bağlamı kurar, cevabı akıtır; `meta`ya ölçümleri yazar."""
    started = time.time()
    used, why = kb.choose(mode, question)
    meta.update({"mode": used, "route": why, "requested": mode, "full_tokens": est_tokens(kb.full)})
    if used == "cag":
        prefix = SYSTEM + "\n\nBİLGİ TABANI (tam, önbellekli):\n" + kb.full
        tail = ""
    elif used == "hybrid":
        papers, info = await kb.retrieve(question, llm)
        meta.update(info)
        prefix = SYSTEM + "\n\nBİLGİ TABANI (çekirdek, önbellekli):\n" + kb.core
        tail = "SORUYLA İLGİLİ AYRINTILAR (RAG):\n" + _details(papers) + "\n\n"
    else:  # rag
        papers, info = await kb.retrieve(question, llm)
        meta.update(info)
        prefix = SYSTEM + "\n\nBİLGİ TABANI (yalnız getirilen):\n" + "\n".join(kb._header()[:4])
        tail = "GETİRİLEN YAYINLAR (RAG):\n" + _details(papers) + "\n\n"
    meta["context_tokens"] = est_tokens(prefix + tail)
    meta["retrieval_s"] = round(time.time() - started, 2)

    if llm.available:
        messages = [{"role": "system", "content": prefix}]
        for h in history[-6:]:
            if h.get("role") in ("user", "assistant") and h.get("content"):
                messages.append({"role": h["role"], "content": str(h["content"])[:2000]})
        messages.append({"role": "user", "content": tail + "SORU: " + question})
        stats: dict = {}
        try:
            async for piece in llm.stream_chat(messages, stats):
                yield piece
            meta.update(stats)
            if stats.get("prompt_tokens"):
                meta["context_tokens"] = stats["prompt_tokens"]  # tahmin yerine gerçek sayı
            # KV önbelleği etkisi prompt işleme süresinde görülür (aynı önek → düşük prompt_eval_s)
            meta["model"] = llm.model
            return
        except Exception:  # noqa: BLE001
            yield "\n\n_(Yerel model yanıt vermedi; erişim tabanlı cevap:)_\n\n"
    meta["model"] = "mock"
    for piece in await _mock_answer(kb, question, llm):
        yield piece


async def _mock_answer(kb: Knowledge, question: str, llm) -> list[str]:
    prof, papers = kb.prof, kb.papers
    q = fold(question)
    if re.search(r"kac|sayi|how many|toplam", q):
        years = Counter(p["year"] for p in papers if p["year"])
        return [f"{prof['name']} için {len(papers)} benzersiz yayın bulundu. Yıllara göre: "
                + ", ".join(f"{y}: {c}" for y, c in sorted(years.items())) + "."]
    if re.search(r"atif|cited|citation|etkili", q):
        top = sorted([p for p in papers if p.get("citations")], key=lambda p: -p["citations"])[:5]
        return ["En çok atıf alan yayınlar:\n" + "\n".join(f"- {p['title']} — {p['citations']} atıf [{p['id']}]" for p in top)]
    if re.search(r"son|guncel|latest|recent|yeni", q):
        return ["En güncel yayınlar:\n" + "\n".join(f"- ({p['year']}) {p['title']} [{p['id']}]" for p in papers[:5])]
    hits, _ = await kb.retrieve(question, llm, k=5)
    return ["Sorunla en ilgili yayınlar (mock mod — yerel LLM kapalı):\n"
            + "\n".join(f"- ({p['year'] or '?'}) {p['title']} [{p['id']}]" for p in hits)]
