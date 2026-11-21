"""Sesli araştırma asistanı: Konu bul ve Danışman bul sayfalarında sesli ya da yazılı soru–cevap.

Tarayıcı ile Gemini Live arasında köprü (WebSocket /ws/assistant): tarayıcı mikrofonu 16 kHz PCM olarak gönderir, model
24 kHz ses ve yazıya dökülmüş metinle cevap verir. Model şu araçları çağırabilir:

  find_topics(query)                 Konu bul'un kaynakları (OpenAlex, Crossref, Semantic Scholar, TR Dizin, OpenAIRE)
  find_advisors(topic, university)   Danışman bul (OpenAlex yayınları + YÖK)
  web_search(query, mode)            Genel web araması: Gemini'nin Google arama bağlamı, olmazsa Serper / DDGS

Kullanıcı belge de verebilir (PDF, Word, metin): metni çıkarılır ve sohbete bağlam olarak eklenir. Asistanın adı, sesi,
konuşma tonu ve hitabı Ayarlar → Asistan bölümünden gelir (ai_settings.assistant()).
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import re
import time
import zipfile
from datetime import datetime

from fastapi import WebSocket, WebSocketDisconnect

from . import ai_settings

log = logging.getLogger(__name__)

# Canlı ses modelleri, tercih sırasıyla: bağlantı kurulamazsa sıradaki denenir (Ayarlar'da elle model verilirse önce o).
LIVE_MODELS = ("models/gemini-2.5-flash-native-audio-latest", "models/gemini-2.5-flash-native-audio-preview-12-2025",
               "models/gemini-3.1-flash-live-preview", "models/gemini-3.8-live")
# google-genai'nin varsayılan canlı uç noktası 404 veriyor (2026-11); v1beta ile bağlanılır.
LIVE_API_VERSION = "v1beta"
SEND_RATE, RECEIVE_RATE = 16000, 24000
MAX_DOCUMENT_BYTES = 10_000_000
MAX_DOCUMENT_CHARS = 30_000

# Gemini Live'ın hazır sesleri: (görünen ad, cinsiyet, karakter).
VOICES = {
    "Kore": ("Kore", "kadın", "kararlı, net"),
    "Aoede": ("Aoede", "kadın", "ferah, sıcak"),
    "Leda": ("Leda", "kadın", "genç, enerjik"),
    "Zephyr": ("Zephyr", "kadın", "parlak, canlı"),
    "Puck": ("Puck", "erkek", "neşeli, hareketli"),
    "Charon": ("Charon", "erkek", "bilgilendirici, sakin"),
    "Fenrir": ("Fenrir", "erkek", "heyecanlı, güçlü"),
    "Orus": ("Orus", "erkek", "kararlı, olgun"),
}
TONES = {
    "samimi": "Sıcak ve samimi konuş; bir araştırma arkadaşı gibi. Kısa cümleler kur, gerektiğinde küçük bir espri yapabilirsin.",
    "resmi": "Kibar ve resmî konuş; bir üniversite danışmanı gibi. Net, ölçülü ve saygılı ol.",
    "neşeli": "Enerjik ve neşeli konuş; merak uyandır, cesaretlendir. Abartma, bilgiyi doğru ver.",
    "sakin": "Sakin, yavaş ve güven veren bir tonda konuş; acele ettirme, adım adım ilerle.",
}
# Kürenin renk paletleri (ana renk, ikinci renk); arayüz static/assistant.js'te aynı adlarla çizer.
COLORS = {"mavi": ("#1d4ed8", "#0f766e"), "turkuaz": ("#0e7490", "#14b8a6"), "mor": ("#6d28d9", "#db2777"),
          "turuncu": ("#ea580c", "#f59e0b"), "yeşil": ("#15803d", "#65a30d"), "gece": ("#1e293b", "#6366f1")}
MODES = {
    "topic": ("Konu bul", "Kullanıcı bir araştırma konusunda yayın, makale ve kaynak arıyor. Konuyu netleştirmesine yardım et "
              "(alt konu, yıl aralığı, yöntem), sonra find_topics aracını çağır. Sonuçlardan en ilgili 3–5 yayını başlık, "
              "yıl ve dergiyle kısaca anlat; tam liste ekranda kartlar olarak görünür."),
    "advisor": ("Danışman bul", "Kullanıcı tez ya da TÜBİTAK 2209-A projesi için danışman arıyor. Önce konusunu ve varsa "
                "üniversitesini öğren, sonra find_advisors aracını çağır. En uygun 3–5 akademisyeni unvan, kurum ve neden uygun "
                "olduklarıyla (son yayınları, yönettiği tezler) anlat; tam liste ekranda kartlar olarak görünür."),
}

TOOLS = [
    {"name": "find_topics",
     "description": "Akademik yayın araması (OpenAlex, Crossref, Semantic Scholar, TR Dizin, OpenAIRE). Kullanıcı bir konuda "
                    "makale, yayın ya da literatür istediğinde çağır. Türkçe konu da olur; İngilizceye kendisi çevirir.",
     "parameters": {"type": "OBJECT", "properties": {
         "query": {"type": "STRING", "description": "Araştırma konusu, ör. 'deprem sonrası hasar tespiti'"}},
         "required": ["query"]}},
    {"name": "find_advisors",
     "description": "Bir konuda son yıllarda yayın yapmış, tez yönetmiş Türkiye'deki akademisyenleri sıralar. Kullanıcı tez ya "
                    "da proje danışmanı istediğinde çağır.",
     "parameters": {"type": "OBJECT", "properties": {
         "topic": {"type": "STRING", "description": "Tez ya da proje konusu"},
         "university": {"type": "STRING", "description": "İsteğe bağlı: üniversite adı, ör. 'OSTİM Teknik Üniversitesi'"},
         "mode": {"type": "STRING", "description": "'tez' (varsayılan) ya da '2209' (TÜBİTAK 2209-A)"}},
         "required": ["topic"]}},
    {"name": "web_search",
     "description": "Genel web araması: güncel bilgi, burs ve çağrı tarihleri, bölüm sayfaları, haberler. Akademik yayın için "
                    "find_topics'i tercih et. Kipler: 'search' (varsayılan), 'news' (güncel haberler), 'research' (ayrıntılı).",
     "parameters": {"type": "OBJECT", "properties": {
         "query": {"type": "STRING", "description": "Arama sorgusu"},
         "mode": {"type": "STRING", "description": "search | news | research"}},
         "required": ["query"]}},
]


def _persona() -> dict:
    cfg = ai_settings.assistant()
    voice = cfg["voice"] if cfg["voice"] in VOICES else "Kore"
    return {**cfg, "voice": voice, "gender": VOICES[voice][1]}


def _history_text(history: list[dict]) -> str:
    rows = []
    for item in history[-24:]:
        text = " ".join(str(item.get("text") or "").split())[:600]
        if text:
            rows.append(f"{'Kullanıcı' if item.get('speaker') == 'user' else 'Sen'}: {text}")
    return "\n".join(rows)


def _system_prompt(mode: str, history: list[dict] | None = None) -> str:
    p = _persona()
    title, task = MODES.get(mode, MODES["topic"])
    address = "Kullanıcıya 'siz' diye hitap et." if p["address"] == "siz" else "Kullanıcıya 'sen' diye hitap et."
    now = datetime.now()
    return "\n".join([
        f"Sen {p['name']}'sın: Akademik İz uygulamasının sesli araştırma asistanı. Şu an '{title}' sayfasındasın.",
        f"Bugün {now.strftime('%d.%m.%Y')}, saat {now.strftime('%H:%M')}.",
        f"Görevin: {task}",
        TONES.get(p["tone"], TONES["samimi"]),
        address,
        "Her zaman Türkçe konuş (kullanıcı başka dilde konuşursa o dilde devam et). Sesli konuştuğun için kısa tut: genelde 1–3 "
        "cümle. Uzun listeleri sesli okuma; 'ekranda listeledim' de ve en önemlilerini söyle.",
        "Yayın, kişi, tarih ya da sayı uydurma: bilgi araçlardan gelmediyse 'bilmiyorum' de ya da arama yap. Araç sonucu boşsa "
        "bunu açıkça söyle ve konuyu daraltmayı ya da genişletmeyi öner.",
        "Kullanıcı belge paylaşırsa önce ne olduğunu bir cümleyle özetle, sonra belgeye göre konu ya da danışman önerebileceğini söyle.",
        "E-posta, telefon gibi kişisel iletişim bilgisi verme.",
        p["extra"].strip(),
        ("Bu kullanıcıyla daha önce konuştunuz; konuşmanın son kısmı aşağıda. Kaldığın yerden devam et, aynı şeyleri "
         "yeniden sorma:\n" + _history_text(history)) if history else "",
    ]).strip()


# ------------------------------------------------------------------ araçlar
def _short(text, limit=160) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


async def _find_topics(args: dict, llm) -> tuple[str, dict]:
    from . import library
    query = _short(args.get("query"), 200)
    if len(query) < 3:
        return "Konu çok kısa; biraz daha ayrıntı iste.", {}
    snap = await asyncio.wait_for(library.topic_search(query, llm), 60)
    papers = (snap or {}).get("papers") or []
    cards = [{"title": _short(p.get("title"), 220), "year": p.get("year") or "", "venue": _short(p.get("venue"), 90),
              "authors": [_short(a, 40) for a in (p.get("authors") or [])[:4]], "citations": p.get("citations") or 0,
              "doi": p.get("doi") or "", "url": p.get("url") or "", "abstract": _short(p.get("abstract"), 420),
              "sources": p.get("sources") or []} for p in papers[:12]]
    if not cards:
        return f"'{query}' için yayın bulunamadı.", {}
    lines = [f"'{query}' için {len(papers)} yayın bulundu (ekranda ilk {len(cards)} gösteriliyor). En ilgili olanlar:"]
    for i, c in enumerate(cards[:8], 1):
        lines.append(f"{i}. {c['title']} ({c['year']}; {c['venue'] or 'dergi yok'}; {c['citations']} atıf; yazarlar: {', '.join(c['authors'][:3])})")
        if c["abstract"]:
            lines.append(f"   Özet: {c['abstract'][:240]}")
    return "\n".join(lines), {"kind": "topics", "query": query, "total": len(papers), "items": cards,
                              "link": f"#/ara?q={query}"}


async def _find_advisors(args: dict) -> tuple[str, dict]:
    from . import advisors, yokdir
    from .text import fold
    topic = _short(args.get("topic"), 300)
    if len(topic) < 3:
        return "Konu çok kısa; tez ya da proje konusunu biraz daha anlatmasını iste.", {}
    mode = "2209" if str(args.get("mode") or "").strip() == "2209" else "tez"
    uni_id, uni_name = "", ""
    wanted = fold(args.get("university") or "")
    if wanted:
        unis = await yokdir.university_list()
        hit = next((u for u in unis if fold(u["name"]) == wanted), None) or next((u for u in unis if wanted in fold(u["name"])), None)
        if hit:
            uni_id, uni_name = hit["id"], hit["name"]
    found = await asyncio.wait_for(advisors.find(topic, uni_id, mode, english=topic), 45)
    items = found.get("items") or []
    cards = [{"name": x["name"], "title": x.get("title") or "", "institution": x.get("institution") or "",
              "department": x.get("department") or "", "works": x.get("works") or 0, "citations": x.get("citations") or 0,
              "last_year": x.get("last_year") or "", "theses": x.get("theses"), "match": x.get("match"),
              "topics": x.get("topics") or [], "samples": [_short(s.get("title"), 140) for s in (x.get("samples") or [])[:2]],
              "chat_id": x.get("chat_id") or "", "yok_url": x.get("yok_url") or ""} for x in items[:12]]
    scope = f" ({uni_name})" if uni_name else ""
    if not cards:
        return f"'{topic}'{scope} için uygun akademisyen bulunamadı. {found.get('message') or ''}".strip(), {}
    lines = [f"'{topic}'{scope} için {len(items)} akademisyen bulundu (ekranda ilk {len(cards)}). En uygunlar:"]
    for i, c in enumerate(cards[:8], 1):
        extra = f", {c['theses']} tez yönetmiş" if c["theses"] else ""
        lines.append(f"{i}. {c['title']} {c['name']} — {c['institution']}; {c['works']} ilgili yayın, son {c['last_year']}{extra}. "
                     f"Örnek yayın: {'; '.join(c['samples'][:1])}")
    return "\n".join(lines), {"kind": "advisors", "query": topic, "university": uni_name, "total": len(items), "items": cards,
                              "link": f"#/danisman?mode={mode}&uni={uni_id}&q={topic}"}


async def _web_search(args: dict) -> tuple[str, dict]:
    """Önce Gemini'nin Google arama bağlamı (kaynaklı, güncel); olmazsa anahtarlı arama servisi (Serper) ya da DDGS."""
    import httpx
    query = _short(args.get("query"), 300)
    mode = str(args.get("mode") or "search").lower()
    if not query:
        return "Arama sorgusu boş.", {}
    prompt = {"news": f"Bugünün güncel haberleri: {query}. Kısa madde madde, tarihleriyle.",
              "research": f"Ayrıntılı ve doğru açıkla: {query}. Arka plan, temel bilgiler ve güncel durum."}.get(mode, query)
    cfg = ai_settings.resolved("gemini")
    if cfg.get("key"):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(f"{cfg['base_url']}/models/{cfg['fast_model'] or cfg['model']}:generateContent",
                                      headers={"x-goog-api-key": cfg["key"]},
                                      json={"contents": [{"parts": [{"text": prompt + " (Türkçe cevap ver.)"}]}],
                                            "tools": [{"google_search": {}}]})
            r.raise_for_status()
            cand = (r.json().get("candidates") or [{}])[0]
            text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts") or []).strip()
            chunks = (cand.get("groundingMetadata") or {}).get("groundingChunks") or []
            links = [{"title": _short((c.get("web") or {}).get("title"), 90), "url": (c.get("web") or {}).get("uri", "")}
                     for c in chunks if (c.get("web") or {}).get("uri")][:6]
            if text:
                return text, {"kind": "web", "query": query, "text": text, "links": links}
        except Exception as exc:  # noqa: BLE001 — yedek arama denenir
            log.info("Gemini arama bağlamı kullanılamadı: %s", type(exc).__name__)
    from . import websearch
    rows = []
    for provider in [p for p in websearch.provider_order() if p in ("serper", "google_cse", "ddgs")]:
        try:
            rows = await websearch._provider(provider, query)
        except Exception:  # noqa: BLE001
            rows = []
        if rows:
            break
    if not rows:
        return f"'{query}' için web sonucu bulunamadı.", {}
    links = [{"title": _short(r.get("title"), 90), "url": r.get("url", ""), "snippet": _short(r.get("snippet"), 200)} for r in rows[:8]]
    text = "\n".join(f"{i}. {x['title']} — {x['snippet']} ({x['url']})" for i, x in enumerate(links, 1))
    return f"Web sonuçları ({query}):\n{text}", {"kind": "web", "query": query, "text": "", "links": links}


# ------------------------------------------------------------------ belgeler
def document_text(name: str, raw: bytes) -> str:
    """PDF, Word (.docx) ya da düz metin belgesinin metni (en çok MAX_DOCUMENT_CHARS)."""
    lower = name.lower()
    if lower.endswith(".pdf") or raw[:5] == b"%PDF-":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        text = "\n".join((page.extract_text() or "") for page in reader.pages[:60])
    elif lower.endswith(".docx") or raw[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            xml = archive.read("word/document.xml").decode("utf-8", errors="replace")
        xml = re.sub(r"</w:p>", "\n", xml)
        text = re.sub(r"<[^>]+>", "", xml)
    else:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("windows-1254", errors="replace")
    text = re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", text)).strip()
    return text[:MAX_DOCUMENT_CHARS]


# ------------------------------------------------------------------ canlı bağlantı
def _client():
    from google import genai
    key = ai_settings.resolved("gemini").get("key")
    if not key:
        raise PermissionError("Sesli asistan için Ayarlar'da bir Gemini anahtarı girin.")
    return genai.Client(api_key=key, http_options={"api_version": LIVE_API_VERSION})


_WORKING_MODEL: dict = {"name": ""}
# Oturum sırasında sesi reddeden (1007 "CONTENT_TYPE_AUDIO is not supported") modeller: bu sunucu açık kaldıkça atlanır.
_BAD_MODELS: set[str] = set()


class _Live:
    """Canlı oturum aç: modeller sırayla denenir; ilk açılan hatırlanır (sonraki oturumlar doğrudan onu kullanır)."""

    def __init__(self, config):
        self.config, self.cm, self.model = config, None, ""

    async def __aenter__(self):
        client = _client()
        chosen = ai_settings.assistant().get("live_model")
        order = [m for m in dict.fromkeys(x for x in (chosen, _WORKING_MODEL["name"], *LIVE_MODELS) if x) if m not in _BAD_MODELS]
        error = None
        for model in order:
            cm = client.aio.live.connect(model=model, config=self.config)
            try:
                session = await cm.__aenter__()
            except Exception as exc:  # noqa: BLE001 — bu model bu anahtarla açılmıyor: sıradaki
                error = exc
                log.info("Canlı model açılamadı: %s (%s)", model, str(exc)[:120])
                continue
            self.cm, self.model = cm, model
            _WORKING_MODEL["name"] = model
            return session
        raise error or RuntimeError("Canlı ses modeli açılamadı.")

    async def __aexit__(self, *exc):
        if self.cm:
            return await self.cm.__aexit__(*exc)
        return False


def _speech_config(voice: str):
    from google.genai import types
    return types.SpeechConfig(language_code="tr-TR",
                              voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)))


async def preview(name: str, voice: str, tone: str) -> bytes:
    """Ayarlar'daki "Sesi dene": seçilen ses ve tonla kısa bir tanıtım cümlesi (WAV, 24 kHz mono)."""
    import wave
    from google.genai import types
    voice = voice if voice in VOICES else "Kore"
    config = types.LiveConnectConfig(response_modalities=["AUDIO"], speech_config=_speech_config(voice),
                                     system_instruction=f"Sen {name or 'Ada'}'sın, Akademik İz'in araştırma asistanı. "
                                                        + TONES.get(tone, TONES["samimi"]))
    chunks: list[bytes] = []
    async with _Live(config) as session:
        await session.send_client_content(turns={"role": "user", "parts": [{"text": (
            "Kendini bir cümleyle tanıt: adını söyle ve Konu bul ile Danışman bul sayfalarında yayın ve danışman bulmaya "
            "yardım ettiğini anlat. Yalnızca bu cümleyi söyle.")}]}, turn_complete=True)

        async def collect():
            async for msg in session.receive():
                if msg.data:
                    chunks.append(msg.data)
                if msg.server_content and msg.server_content.turn_complete:
                    return
        await asyncio.wait_for(collect(), 25)
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RECEIVE_RATE)
        wav.writeframes(b"".join(chunks))
    return out.getvalue()


# ------------------------------------------------------------------ oturum
class AssistantSession:
    def __init__(self, ws: WebSocket, mode: str, llm):
        self.ws, self.mode, self.llm = ws, mode if mode in MODES else "topic", llm
        self.session = None
        self.audio: asyncio.Queue = asyncio.Queue(maxsize=200)
        self.muted = False
        self.history: list[dict] = []  # tarayıcının sakladığı önceki konuşma (yeniden bağlanınca bağlam olarak verilir)
        self.resume = False            # bağlantı koptuktan sonra kendiliğinden yeniden bağlanma: selamlama yapılmaz
        self.model = ""

    async def send(self, obj: dict) -> None:
        try:
            await self.ws.send_text(json.dumps(obj, ensure_ascii=False))
        except Exception:  # noqa: BLE001 — tarayıcı kapandıysa
            pass

    def _config(self):
        from google.genai import types
        p = _persona()
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            input_audio_transcription={}, output_audio_transcription={},
            system_instruction=_system_prompt(self.mode, self.history),
            tools=[{"function_declarations": TOOLS}],
            speech_config=_speech_config(p["voice"]),
            context_window_compression=types.ContextWindowCompressionConfig(sliding_window=types.SlidingWindow()),
        )

    async def _tool(self, call):
        from google.genai import types
        name, args = call.name, dict(call.args or {})
        await self.send({"type": "state", "state": "thinking", "tool": name})
        started = time.time()
        try:
            if name == "find_topics":
                result, card = await _find_topics(args, self.llm)
            elif name == "find_advisors":
                result, card = await _find_advisors(args)
            elif name == "web_search":
                result, card = await _web_search(args)
            else:
                result, card = f"Bilinmeyen araç: {name}", {}
        except asyncio.TimeoutError:
            result, card = "Arama zaman aşımına uğradı; kullanıcıdan konuyu daraltmasını iste.", {}
        except Exception as exc:  # noqa: BLE001
            log.exception("Asistan aracı başarısız: %s", name)
            result, card = f"Araç çalışmadı ({type(exc).__name__}).", {}
        if card:
            await self.send({"type": "results", "tool": name, "seconds": round(time.time() - started, 1), **card})
        return types.FunctionResponse(id=call.id, name=name, response={"result": result})

    async def _to_gemini(self):
        from google.genai import types
        while True:
            pcm = await self.audio.get()
            if self.session:
                await self.session.send_realtime_input(audio=types.Blob(data=pcm, mime_type=f"audio/pcm;rate={SEND_RATE}"))

    async def _from_gemini(self):
        heard, said = [], []
        while True:
            async for msg in self.session.receive():
                if msg.data:
                    await self.send({"type": "audio", "pcm": base64.b64encode(msg.data).decode("ascii")})
                content = msg.server_content
                if content:
                    if content.interrupted:
                        await self.send({"type": "interrupted"})
                    if content.input_transcription and content.input_transcription.text:
                        heard.append(content.input_transcription.text)
                        await self.send({"type": "partial", "speaker": "user", "text": "".join(heard).strip()})
                    if content.output_transcription and content.output_transcription.text:
                        said.append(content.output_transcription.text)
                        await self.send({"type": "partial", "speaker": "assistant", "text": "".join(said).strip()})
                    if content.turn_complete:
                        if heard:
                            await self.send({"type": "message", "speaker": "user", "text": "".join(heard).strip()})
                        if said:
                            await self.send({"type": "message", "speaker": "assistant", "text": "".join(said).strip()})
                        heard, said = [], []
                        await self.send({"type": "turn_complete"})
                if msg.tool_call:
                    responses = [await self._tool(call) for call in msg.tool_call.function_calls]
                    await self.session.send_tool_response(function_responses=responses)

    async def _from_browser(self):
        while True:
            data = json.loads(await self.ws.receive_text())
            kind = data.get("type")
            if kind == "audio":
                if not self.muted:
                    try:
                        self.audio.put_nowait(base64.b64decode(data.get("pcm") or ""))
                    except asyncio.QueueFull:
                        pass
            elif kind == "text":
                text = str(data.get("text") or "").strip()[:2000]
                if text and self.session:
                    await self.send({"type": "message", "speaker": "user", "text": text})
                    await self.send({"type": "state", "state": "thinking"})
                    await self.session.send_client_content(turns={"role": "user", "parts": [{"text": text}]}, turn_complete=True)
            elif kind == "mute":
                self.muted = bool(data.get("value"))
            elif kind == "document":
                await self._document(str(data.get("name") or "belge"), str(data.get("data") or ""))

    async def _document(self, name: str, b64: str):
        try:
            raw = base64.b64decode(b64)
            if len(raw) > MAX_DOCUMENT_BYTES:
                raise ValueError("Belge 10 MB'tan büyük.")
            text = await asyncio.to_thread(document_text, name, raw)
            if len(text) < 20:
                raise ValueError("Belgeden metin çıkarılamadı (taranmış görüntü olabilir).")
        except Exception as exc:  # noqa: BLE001
            await self.send({"type": "error", "message": f"{name}: {exc}"})
            return
        await self.send({"type": "document", "name": name, "chars": len(text)})
        await self.send({"type": "state", "state": "thinking"})
        await self.session.send_client_content(turns={"role": "user", "parts": [{"text": (
            f"[Kullanıcı bir belge paylaştı: {name}]\n---\n{text}\n---\n"
            "Belgenin ne olduğunu bir iki cümleyle özetle ve buna göre nasıl yardım edebileceğini sor.")}]}, turn_complete=True)

    async def _greet(self):
        await asyncio.sleep(0.3)
        if self.resume:
            return  # bağlantı yenilendi: kullanıcı konuşmaya devam ediyor, yeniden selam verilmez
        if self.history:
            await self.session.send_client_content(turns={"role": "user", "parts": [{"text": (
                "[GERİ DÖNÜŞ] Kullanıcı sohbete geri döndü. Kısaca 'tekrar hoş geldin' de ve kaldığınız konuyu bir cümleyle "
                "hatırlatıp devam etmek isteyip istemediğini sor. Araç çağırma.")}]}, turn_complete=True)
            return
        hour = datetime.now().hour
        part = "Günaydın" if 5 <= hour < 12 else "İyi günler" if hour < 18 else "İyi akşamlar"
        ask = "hangi konuda yayın aradığını" if self.mode == "topic" else "tez ya da proje konusunu ve üniversiteni"
        await self.session.send_client_content(turns={"role": "user", "parts": [{"text": (
            f"[AÇILIŞ] Kullanıcıyı '{part}' diyerek kısaca karşıla, kendini adınla tanıt ve {ask} sor. "
            "Tek kısa cümle; araç çağırma.")}]}, turn_complete=True)

    async def _hello(self):
        """Tarayıcının ilk mesajı: önceki konuşma ve yeniden bağlanma bilgisi (en çok 2 sn beklenir)."""
        try:
            data = json.loads(await asyncio.wait_for(self.ws.receive_text(), 2))
        except (asyncio.TimeoutError, ValueError):
            return
        if data.get("type") == "hello":
            items = data.get("history") if isinstance(data.get("history"), list) else []
            self.history = [{"speaker": "user" if x.get("speaker") == "user" else "assistant", "text": str(x.get("text") or "")[:1200]}
                            for x in items[-40:] if isinstance(x, dict)]
            self.resume = bool(data.get("resume"))

    async def run(self):
        if not ai_settings.resolved("gemini").get("key"):
            await self.send({"type": "error", "message": "Sesli asistan için Ayarlar'da bir Gemini anahtarı girin."})
            return
        await self._hello()
        live = _Live(self._config())
        async with live as session:
            self.session, self.model = session, live.model
            log.info("Asistan oturumu açıldı: %s", live.model)
            p = _persona()
            await self.send({"type": "ready", "name": p["name"], "voice": p["voice"], "gender": p["gender"], "model": live.model,
                             "color": p.get("color") or "mavi", "send_rate": SEND_RATE, "receive_rate": RECEIVE_RATE})
            tasks = [asyncio.create_task(t) for t in (self._to_gemini(), self._from_gemini(), self._from_browser(), self._greet())]
            try:
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
                for task in done:
                    if task.exception() and not isinstance(task.exception(), WebSocketDisconnect):
                        raise task.exception()
            finally:
                for task in tasks:
                    task.cancel()


async def serve(ws: WebSocket, mode: str, llm) -> None:
    await ws.accept()
    session = AssistantSession(ws, mode, llm)
    try:
        await session.run()
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        if "1007" in message or "1011" in message or "1008" in message or "ConnectionClosed" in type(exc).__name__:
            # Model bağlantıyı kapattı (ör. 1007 "audio content type not supported"): sesi reddeden model bırakılır,
            # tarayıcı konuşmayı kaybetmeden kendiliğinden yeniden bağlanır.
            if "CONTENT_TYPE_AUDIO" in message and session.model:
                _BAD_MODELS.add(session.model)
                if _WORKING_MODEL["name"] == session.model:
                    _WORKING_MODEL["name"] = ""
            log.warning("Asistan bağlantısı model tarafından kapandı (%s): %s", session.model, message[:200])
            await session.send({"type": "reconnect", "reason": message[:200]})
        else:
            log.exception("Asistan oturumu kapandı")
            if "API key" in message or "403" in message or "401" in message:
                message = "Gemini anahtarı geçersiz ya da sesli modele erişimi yok (Ayarlar → Yapay zekâ)."
            await session.send({"type": "error", "message": message[:300]})
    finally:
        try:
            await ws.close()
        except Exception:  # noqa: BLE001
            pass
