"""Display record types and explicitly stated manuscript status, without network calls.

An archive's description can describe a related manuscript. Its submission status
does not describe the software/data deposit itself, and a DOI/index match is not
evidence of peer review. Unknown lifecycle states stay unknown.
"""
from __future__ import annotations

import re
from html import unescape


KINDS = {
    "article": "Makale", "journal-article": "Makale", "journal article": "Makale",
    "review": "Derleme", "conference-paper": "Bildiri", "conference paper": "Bildiri",
    "proceedings": "Bildiri", "proceedings-article": "Bildiri", "proceedings paper": "Bildiri",
    "meeting abstract": "Toplantı özeti", "meeting-abstract": "Toplantı özeti",
    "book": "Kitap", "book-chapter": "Kitap bölümü", "book chapter": "Kitap bölümü",
    "dissertation": "Tez", "thesis": "Tez", "master thesis": "Yüksek lisans tezi",
    "doctoral thesis": "Doktora tezi", "software": "Yazılım", "dataset": "Veri seti",
    "data-set": "Veri seti", "preprint": "Ön baskı", "posted-content": "Ön baskı",
    "report": "Rapor", "editorial": "Editöryal yazı", "letter": "Mektup",
    "erratum": "Düzeltme", "correction": "Düzeltme", "patent": "Patent",
}
SOURCES = {"openalex": "OpenAlex", "crossref": "Crossref", "wos": "WoS", "yok": "YÖK",
           "orcid": "ORCID", "openaire": "OpenAIRE", "scholar": "Google Scholar"}
ARCHIVES = {"software", "dataset", "data-set"}
PREPRINTS = {"preprint", "posted-content"}
QUOTES = re.compile(r'“[^”]*”|«[^»]*»|"[^"]*"|‘[^’]*’|\*{1,2}[^*]+\*{1,2}')
COMPANION = re.compile(
    r"^(?:code\b|scripts\b|analysis code\b|data\b|dataset\b|software\b|"
    r"companion (?:archive|repository|data|code)\b|supplementary (?:code|data|material)\b)", re.I)
SUBJECT = re.compile(r"\b(?:manuscript|paper|letter|article)\b", re.I)
DIRECT = re.compile(r"^(?:this|the|our)\s+(?:manuscript|paper|preprint|article)\b", re.I)
PATTERNS = (
    ("in_preparation", "gönderime hazırlanıyor", r"\bprepared for submission\b"),
    ("under_review", "değerlendirmede", r"\b(?:under (?:peer )?review|undergoing peer review)\b"),
    ("submitted", "gönderildi", r"\bsubmitted (?:to|for publication)\b"),
    ("accepted", "kabul edildi", r"\baccepted for publication\b"),
    ("in_press", "baskıda", r"\bin press\b"),
)
# These phrases change a status assertion into negation, history or intention.
QUALIFIER = re.compile(
    r"\b(?:not|never|no longer|previously|formerly|was|were|will|would|could|may|might|"
    r"if|once|before|after|until|when|whether|withdrawn|retracted|rejected|"
    r"to be|yet to be|expected to be|planned to be)\b", re.I)


def kind(paper: dict) -> str:
    value = str(paper.get("type") or "").strip().lower()
    return KINDS.get(value, "Diğer" if value else "Türü belirtilmemiş")


def describe(paper: dict) -> dict:
    """Use only explicit introductory metadata, never arbitrary abstract keywords.

    The original sentence and its source remain available for inspection. We do
    not treat an indexed record, date or verification count as publication status.
    """
    unknown = {"code": "unknown", "label": "Süreç bilgisi yok", "scope": "record",
               "evidence": "", "source": "", "url": ""}
    record_type = str(paper.get("type") or "").strip().lower()
    if record_type not in ARCHIVES | PREPRINTS:
        return unknown
    abstract = unescape(re.sub(r"<[^>]*>", " ", str(paper.get("abstract") or "")))
    abstract = re.sub(r"\s+", " ", abstract).strip()
    # Mask quoted titles before inspecting prose; a title may itself mention review.
    masked = QUOTES.sub(lambda m: " " * (len(m[0]) - 1) + "]", abstract)
    # The first metadata sentence only. Do not split initials such as "I. Avcibas".
    end = re.search(r'(?<=[a-z0-9)\]])[.!?](?=\s+[A-Z]|$)', masked)
    stop = min(end.end() if end else len(masked), 1200)
    intro, evidence = masked[:stop], abstract[:stop]
    subject = SUBJECT.search(intro)
    related = record_type in ARCHIVES and COMPANION.match(intro) and subject
    direct = record_type in PREPRINTS and DIRECT.match(intro)
    if not (related or direct):
        return unknown
    if intro.endswith("?"):
        return unknown
    assertions = []
    for code, label, pattern in PATTERNS:
        for match in re.finditer(pattern, intro, re.I):
            if subject and match.start() < subject.end():
                continue
            # Inspect the whole assertion between its subject and status. This
            # catches negated/conditional claims even across a long quoted title.
            context = intro[subject.end() if subject else 0:match.start()]
            if QUALIFIER.search(context + " " + intro[match.end():]):
                continue
            # A comma/parenthesis introduces companion metadata. Without this,
            # an unquoted title such as "Under Review: ..." is not an assertion.
            if related and not re.search(r"[,;(]\s*(?:currently\s+)?$", context, re.I):
                continue
            if direct and not re.fullmatch(r"\s+(?:is|has been)\s+(?:currently\s+)?", context, re.I):
                continue
            assertions.append((code, label))
    assertions = list(dict.fromkeys(assertions))
    if len(assertions) != 1:
        return unknown
    code, label = assertions[0]
    # Older merged records did not retain abstract provenance. Do not assign a
    # borrowed description to whichever source happened to win deduplication.
    sources = paper.get("sources") or [paper.get("source")]
    source = paper.get("abstract_source") or (paper.get("source") if len(sources) == 1 else "") or "Kaydedilen açıklama"
    url = paper.get("abstract_url") or (paper.get("url") if len(sources) == 1 else "") or ""
    return {"code": code, "label": f"İlgili makale: {label}" if related else label[:1].upper() + label[1:],
            "scope": "related_manuscript" if related else "record", "evidence": evidence,
            "source": SOURCES.get(source, source), "url": url}


def annotate(papers: list[dict]) -> None:
    for paper in papers:
        paper["publication_kind"] = kind(paper)
        paper["publication_status"] = describe(paper)
