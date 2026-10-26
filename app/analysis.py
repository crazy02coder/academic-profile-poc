"""Kanıta bağlı araştırma profili: alanlar, yöntemler, yıllara göre odak.

Her iddia en az bir yayın kimliğine (P#) dayanmak zorundadır; doğrulayıcı geçersiz
kimlikleri, zaman çizelgesinde dönem dışı kanıtları ve kanıtsız cümleleri eler.
LLM yoksa / doğrulamayı geçemezse sözlük tabanlı mock analiz devreye girer.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

from .text import clean, fold

AREAS = {
    "Yapay Zekâ ve Makine Öğrenmesi": r"machine learning|makine ogrenme|artificial intelligence|yapay zeka|classification|siniflandirma|prediction|tahmin",
    "Derin Öğrenme": r"deep learning|derin ogrenme|neural network|sinir ag|cnn|convolutional|evrisimli|transformer|lstm",
    "Görüntü İşleme ve Bilgisayarlı Görü": r"image|goruntu|vision|detection|tespit|segmentation|hyperspectral|hiperspektral|remote sensing",
    "Doğal Dil İşleme ve LLM": r"natural language|dogal dil|nlp|language model|llm|sentiment|duygu|text|metin",
    "Siber Güvenlik": r"security|guvenlik|attack|saldiri|intrusion|malware|traffic|https|network security",
    "Sağlık Bilişimi": r"medical|tibbi|health|saglik|disease|hastalik|dementia|alzheimer|cancer|kanser|clinical|ecg|eeg|mri",
    "Karar Destek ve Optimizasyon": r"decision|karar|optimization|optimizasyon|multicriteria|mcdm|supplier|tedarik|scheduling",
    "Robotik ve Otonom Sistemler": r"robot|autonomous|otonom|uav|drone|iha|control|kontrol",
    "Enerji ve Elektrik Sistemleri": r"energy|enerji|power|guc|battery|batarya|solar|gunes|grid|sebeke",
    "Eğitim Teknolojileri": r"education|egitim|learning analytics|student|ogrenci|e-learning",
    "Veri Madenciliği ve Analitik": r"data mining|veri madencilig|big data|buyuk veri|analytics|clustering|kumeleme",
    "Ekonomi ve İşletme": r"economic|ekonomi|finance|finans|market|pazar|management|yonetim|business|isletme",
}
METHODS = {
    "Evrişimli sinir ağları (CNN)": r"cnn|convolutional|evrisimli|resnet|vgg|efficientnet|yolo",
    "Transformer / büyük dil modelleri": r"transformer|bert|gpt|llm|large language|vit|vision transformer|attention",
    "Klasik makine öğrenmesi (SVM, RF, k-NN…)": r"svm|support vector|random forest|k-nn|knn|decision tree|xgboost|naive bayes|logistic regression",
    "Transfer öğrenme": r"transfer learning|pre-?trained|fine-?tun|frozen",
    "Çok kriterli karar verme": r"multicriteria|multi-criteria|mcdm|ahp|topsis|electre|fuzzy",
    "İstatistiksel analiz": r"statistical|istatistik|regression|regresyon|anova|hypothesis",
    "Sinyal / spektral işleme": r"signal|sinyal|spectral|spektral|fourier|wavelet|dalgacik",
    "Füzyon / çok kipli öğrenme": r"fusion|fuzyon|multimodal|multi-modal|gated",
    "Optimizasyon / metasezgisel": r"genetic algorithm|genetik|particle swarm|metaheuristic|optimization",
    "Süper çözünürlük": r"super-?resolution|super cozunurluk",
}

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "areas": {"type": "array", "items": {"type": "object", "properties": {
            "label": {"type": "string"}, "text": {"type": "string"},
            "evidence": {"type": "array", "items": {"type": "string"}}}, "required": ["label", "text", "evidence"]}},
        "methods": {"type": "array", "items": {"type": "object", "properties": {
            "label": {"type": "string"}, "text": {"type": "string"},
            "evidence": {"type": "array", "items": {"type": "string"}}}, "required": ["label", "text", "evidence"]}},
        "timeline": {"type": "array", "items": {"type": "object", "properties": {
            "period": {"type": "string"}, "text": {"type": "string"},
            "evidence": {"type": "array", "items": {"type": "string"}}}, "required": ["period", "text", "evidence"]}},
    },
    "required": ["summary", "areas", "methods", "timeline"],
}


def _blob(p: dict) -> str:
    return fold(" ".join([p["title"], *(v["title"] for v in p.get("variants", [])), p.get("abstract", "")[:1500],
                          " ".join(p.get("labels") or [])]))


def _periods(papers: list[dict]) -> list[tuple[int, int]]:
    years = sorted({p["year"] for p in papers if p["year"]})
    if not years:
        return []
    lo, hi = years[0], years[-1]
    span = hi - lo + 1
    size = max(2, -(-span // 4)) if span > 4 else span
    out, start = [], lo
    while start <= hi:
        out.append((start, min(hi, start + size - 1)))
        start += size
    return out


def _period_label(a: int, b: int) -> str:
    return str(a) if a == b else f"{a}–{b}"


def mock(papers: list[dict], profile: dict) -> dict:
    def match(table):
        hits = defaultdict(list)
        for p in papers:
            text = _blob(p)
            for label, rx in table.items():
                if re.search(rx, text):
                    hits[label].append(p["id"])
        return sorted(hits.items(), key=lambda kv: -len(kv[1]))

    areas = [{"label": label, "text": f"{len(ids)} yayında {label.lower()} konusu öne çıkıyor.", "evidence": ids[:4]}
             for label, ids in match(AREAS)[:6]]
    methods = [{"label": label, "text": f"{label} yaklaşımı {len(ids)} yayında kullanılmış.", "evidence": ids[:4]}
               for label, ids in match(METHODS)[:6]]
    timeline = []
    for a, b in _periods(papers):
        bucket = [p for p in papers if p["year"] and a <= p["year"] <= b]
        if not bucket:
            continue
        counts = Counter()
        for p in bucket:
            for label, rx in AREAS.items():
                if re.search(rx, _blob(p)):
                    counts[label] += 1
        top = [label for label, _ in counts.most_common(2)]
        if not top:
            continue
        evid = [p["id"] for p in bucket if any(re.search(AREAS[t], _blob(p)) for t in top)][:4]
        timeline.append({"period": _period_label(a, b),
                         "text": f"{_period_label(a, b)} döneminde {len(bucket)} yayın; odak: {', '.join(top)}.",
                         "evidence": evid})
    name = profile.get("name", "")
    summary = (f"{name} için {len(papers)} benzersiz yayın incelendi; baskın alanlar: "
               f"{', '.join(a['label'] for a in areas[:3]) or 'belirlenemedi'}.")
    return {"summary": summary, "areas": areas, "methods": methods, "timeline": timeline}


def validate(data: dict, papers: list[dict]) -> dict | None:
    by_id = {p["id"]: p for p in papers}
    out = {"summary": clean(data.get("summary", ""))[:600], "areas": [], "methods": [], "timeline": []}
    for key in ("areas", "methods"):
        for item in data.get(key) or []:
            ev = [e for e in dict.fromkeys(str(x).strip() for x in item.get("evidence") or []) if e in by_id]
            if ev and clean(item.get("text")) and clean(item.get("label")):
                out[key].append({"label": clean(item["label"])[:60], "text": clean(item["text"])[:300], "evidence": ev[:5]})
    for item in data.get("timeline") or []:
        years = [int(y) for y in re.findall(r"(?:19|20)\d{2}", str(item.get("period", "")))]
        if not years:
            continue
        lo, hi = min(years), max(years)
        ev = [e for e in dict.fromkeys(str(x).strip() for x in item.get("evidence") or [])
              if e in by_id and by_id[e]["year"] and lo <= by_id[e]["year"] <= hi]
        if ev and clean(item.get("text")):
            out["timeline"].append({"period": _period_label(lo, hi), "text": clean(item["text"])[:300], "evidence": ev[:5]})
    out["timeline"].sort(key=lambda t: t["period"])
    if len(out["areas"]) < 2:
        return None
    return out


async def analyze(papers: list[dict], profile: dict, llm, log) -> dict:
    if not papers:
        return {"mode": "unavailable", "summary": "Yayın bulunamadığı için analiz üretilmedi.",
                "areas": [], "methods": [], "timeline": []}
    sample = sorted(papers, key=lambda p: -(p["year"] or 0))[:40]
    if llm.available:
        lines = []
        for p in sample:
            abstract = clean(p.get("abstract", ""))[:350]
            lines.append(f"[{p['id']}] ({p['year'] or '?'}) {p['title']}" + (f" — {abstract}" if abstract else ""))
        prompt = (
            f"Akademisyen: {profile.get('name')} ({profile.get('title')}, {profile.get('department')}, "
            f"{profile.get('institution')}).\nAşağıda yayınları [P#] kimlikleriyle verilmiştir.\n\n" + "\n".join(lines) +
            "\n\nGÖREV (Türkçe yaz): \n"
            "1) areas: 3-6 ana araştırma alanı. Her biri için tek cümle 'text' ve dayandığı P# listesi 'evidence'.\n"
            "2) methods: kullanılan 2-6 yöntem/teknik, aynı biçimde.\n"
            "3) timeline: yıllara göre odak değişimi; 'period' örn. '2019–2021', tek cümle ve o yıllardaki P# kanıtları.\n"
            "4) summary: 2 cümlelik genel özet.\n"
            "KURAL: Sadece verilen başlık/özetlerde açıkça desteklenen iddialar yaz. Her iddiada evidence ZORUNLU ve "
            "yalnızca listedeki P# kimlikleri kullanılabilir.")
        await log("analysis", "running", f"{llm.model} ile {len(sample)} yayın analiz ediliyor (yapılandırılmış JSON çıktı)…")
        data = await llm.json(prompt, SCHEMA, timeout=240)
        checked = validate(data or {}, papers)
        if checked:
            dropped = sum(len((data or {}).get(k) or []) for k in ("areas", "methods", "timeline")) - \
                sum(len(checked[k]) for k in ("areas", "methods", "timeline"))
            await log("analysis", "running", f"Kanıt doğrulayıcı: {dropped} desteksiz iddia elendi.")
            checked["mode"] = "llm"
            checked["model"] = llm.model
            return checked
        await log("analysis", "warning", "LLM çıktısı kanıt doğrulamasını geçemedi → mock analiz.")
    result = mock(papers, profile)
    result["mode"] = "mock"
    return result
