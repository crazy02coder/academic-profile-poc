/* Sesli araştırma asistanı (Konu bul / Danışman bul).
 *
 * Tarayıcı mikrofonu 16 kHz PCM olarak /ws/assistant'a gider; sunucu Gemini Live'a köprü kurar ve 24 kHz ses, yazıya
 * dökülmüş konuşma, araç sonuçları (yayın ve akademisyen kartları, web sonuçları) gönderir. Ortadaki küre asistanın
 * durumuna göre nefes alır: boşta yavaş, dinlerken mikrofon sesine, konuşurken kendi sesine göre büyür; düşünürken döner.
 * Kullanıcı yazarak da konuşabilir ve belge (PDF, Word, metin) verebilir.
 */
(function () {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const safe = (u) => (/^https?:\/\//i.test(u || "") ? u : "");
  const ICON = {
    mic: '<path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3Z"/><path d="M19 11a7 7 0 0 1-14 0M12 18v3"/>',
    micOff: '<path d="m3 3 18 18M9 9v3a3 3 0 0 0 5.1 2.1M15 9.3V6a3 3 0 0 0-5.7-1.3"/><path d="M19 11a7 7 0 0 1-1.2 3.9M5 11a7 7 0 0 0 10.8 5.9M12 18v3"/>',
    send: '<path d="m4 12 16-8-6 16-2.5-6.5L4 12Z"/>',
    clip: '<path d="m21 11-8.5 8.5a5 5 0 0 1-7-7L14 4a3.5 3.5 0 0 1 5 5l-8.5 8.5a2 2 0 0 1-3-3L15 7"/>',
    stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
    ext: '<path d="M14 4h6v6M20 4l-9 9M19 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h5"/>',
  };
  const svg = (name) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">${ICON[name]}</svg>`;
  const STATUS = { idle: "Hazır", connecting: "Bağlanıyor…", listening: "Dinliyorum", thinking: "Düşünüyor…", speaking: "Konuşuyor", muted: "Mikrofon kapalı", ended: "Görüşme bitti" };
  const TOOL_LABEL = { find_topics: "Yayınlar aranıyor…", find_advisors: "Akademisyenler aranıyor…", web_search: "Web'de aranıyor…" };
  let active = null;
  // Sohbet geçmişi tarayıcıda saklanır (sayfa başına): sayfa yenilense ya da bağlantı kopsa da konuşma kaybolmaz ve
  // yeniden bağlanınca asistana bağlam olarak verilir.
  const store = {
    key: (mode) => `va-history-${mode}`,
    load(mode) { try { const v = JSON.parse(localStorage.getItem(this.key(mode)) || "{}"); return { messages: v.messages || [], results: v.results || [] }; } catch { return { messages: [], results: [] }; } },
    save(mode, data) { try { localStorage.setItem(this.key(mode), JSON.stringify({ messages: data.messages.slice(-60), results: data.results.slice(0, 4) })); } catch { /* depolama dolu ya da kapalı */ } },
    clear(mode) { try { localStorage.removeItem(this.key(mode)); } catch { /* yok */ } },
  };

  /* ---------------------------------------------------------------- nefes alan küre */
  // Renk sürekli döner (renk tekerleği); hız ve büyüyüp küçülme duruma göre değişir:
  // düşünürken hızlı dönüp belirgin nabız atar, konuşurken yavaşlar, beklerken sakin nefes alır.
  const MOTION = {  // hue: derece/sn, pulse: büyüme genliği, rate: nabız hızı
    idle: { hue: 14, pulse: 0.06, rate: 1.3 }, muted: { hue: 8, pulse: 0.04, rate: 1.0 },
    listening: { hue: 22, pulse: 0.04, rate: 1.8 }, speaking: { hue: 9, pulse: 0.035, rate: 1.4 },
    thinking: { hue: 95, pulse: 0.11, rate: 3.2 }, connecting: { hue: 70, pulse: 0.09, rate: 2.6 },
  };
  class Orb {
    constructor(canvas) {
      this.canvas = canvas; this.ctx = canvas.getContext("2d");
      this.state = "idle"; this.level = 0; this.born = performance.now(); this.spin = 0; this.shown = 0;
      this.hue = 220; this.last = 0; this.pulse = 0.06; this.rate = 1.3; this.phase = 0; this.hueSpeed = 14;
    }
    resize() {
      const r = this.canvas.getBoundingClientRect(), dpr = Math.min(window.devicePixelRatio || 1, 2);
      this.canvas.width = Math.round(r.width * dpr); this.canvas.height = Math.round(r.height * dpr);
      this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0); this.w = r.width; this.h = r.height;
    }
    color(shift, alpha, light = 52) {
      return `hsla(${((this.hue + shift) % 360).toFixed(1)}, 82%, ${light}%, ${Math.max(0, Math.min(1, alpha)).toFixed(3)})`;
    }
    draw(now, target) {
      const { ctx } = this;
      if (!this.w) this.resize();
      const dt = this.last ? Math.min(0.05, (now - this.last) / 1000) : 0; this.last = now;
      const t = (now - this.born) / 1000;
      // durum değişince hız ve genlik yumuşakça geçer
      const m = MOTION[this.state] || MOTION.idle;
      this.hueSpeed += (m.hue - this.hueSpeed) * 0.05; this.pulse += (m.pulse - this.pulse) * 0.05; this.rate += (m.rate - this.rate) * 0.05;
      this.hue = (this.hue + this.hueSpeed * dt) % 360;
      this.phase += this.rate * dt;
      this.level += (target - this.level) * 0.18;
      this.shown = Math.min(1, this.shown + 0.025);  // karşılama: küre yavaşça belirir
      const appear = 1 - Math.pow(1 - this.shown, 3);
      const cx = this.w / 2, cy = this.h / 2, base = Math.min(this.w, this.h) * 0.27 * appear;
      const grow = Math.sin(this.phase) * this.pulse;  // büyüyüp küçülme
      const energy = this.state === "listening" || this.state === "speaking" ? this.level : 0;
      ctx.clearRect(0, 0, this.w, this.h);
      // dış hale: kürenin nabzıyla genişler, saydamlığı nefesle değişir
      for (let i = 3; i >= 1; i--) {
        const r = base * (1.25 + i * 0.22 + energy * 0.5 + grow * 2.4);
        ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.fillStyle = this.color(i * 25, 0.05 / i + energy * 0.05 + (grow + this.pulse) * 0.12, 60);
        ctx.fill();
      }
      // dalgalanan gövde
      const points = 96;
      ctx.beginPath();
      for (let i = 0; i <= points; i++) {
        const ang = (i / points) * Math.PI * 2;
        const wobble = Math.sin(ang * 3 + t * 1.3) * 0.035 + Math.sin(ang * 5 - t * 1.9) * 0.02 + Math.sin(ang * 7 + t * 2.7) * energy * 0.09;
        const r = base * (1 + grow + energy * 0.28 + wobble);
        const x = cx + Math.cos(ang) * r, y = cy + Math.sin(ang) * r;
        i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
      }
      const grad = ctx.createRadialGradient(cx - base * 0.35, cy - base * 0.4, base * 0.1, cx, cy, base * 1.3);
      grad.addColorStop(0, "rgba(255,255,255,0.85)");
      grad.addColorStop(0.35, this.color(0, 0.95));
      grad.addColorStop(1, this.color(55, 0.88, 46));
      ctx.fillStyle = grad; ctx.fill();
      // düşünürken dönen yaylar
      if (this.state === "thinking" || this.state === "connecting") {
        this.spin += 0.05;
        ctx.lineWidth = 3; ctx.lineCap = "round";
        for (let k = 0; k < 3; k++) {
          ctx.beginPath();
          ctx.strokeStyle = this.color(k * 40, 0.7 - k * 0.18);
          const r = base * (1.18 + k * 0.12 + grow), st = this.spin * (1 + k * 0.4) + k * 2;
          ctx.arc(cx, cy, r, st, st + Math.PI * (0.5 + k * 0.15));
          ctx.stroke();
        }
      }
    }
  }

  /* ---------------------------------------------------------------- asistan */
  class Assistant {
    constructor(root, mode) {
      this.root = root; this.mode = mode; this.state = "idle";
      this.micLevel = 0; this.playLevel = 0; this.playHead = 0; this.nodes = []; this.muted = false;
      this.recvRate = 24000; this.sendRate = 16000;
      this.saved = store.load(mode); this.retries = 0;
      this.render();
      this.orb = new Orb($(".va-orb", root));
      this.loop = this.loop.bind(this);
      requestAnimationFrame(this.loop);
      window.addEventListener("resize", () => this.orb.resize());
    }

    render() {
      const topic = this.mode === "topic";
      this.root.innerHTML = `
        <div class="va-main">
          <div class="va-stage">
            <canvas class="va-orb" aria-hidden="true"></canvas>
            <div class="va-id"><b class="va-name">Asistan</b><span class="va-status" role="status">${topic ? "Hangi konuda yayın arıyorsun?" : "Danışmanını birlikte bulalım."}</span></div>
            <button type="button" class="btn primary va-start">${svg("mic")}Asistanla konuş</button>
            <p class="va-note faint">Mikrofon izni istenir. Sesli konuşmak istemezsen aşağıya yazabilirsin.</p>
          </div>
          <div class="va-chat" aria-live="polite"></div>
          <form class="va-bar" autocomplete="off">
            <input type="file" class="va-file" accept=".pdf,.docx,.txt,.md,.csv" hidden>
            <button type="button" class="icon-btn va-attach" title="Belge ekle (PDF, Word, metin)" aria-label="Belge ekle">${svg("clip")}</button>
            <input class="va-text" placeholder="${topic ? "ör. deprem sonrası hasar tespiti üzerine son yayınlar" : "ör. tarımda drone görüntüsüyle hastalık tespiti için danışman"}" maxlength="2000">
            <button type="button" class="icon-btn va-mic" title="Mikrofonu kapat / aç" aria-label="Mikrofon" hidden>${svg("mic")}</button>
            <button type="submit" class="icon-btn va-send" title="Gönder" aria-label="Gönder">${svg("send")}</button>
            <button type="button" class="icon-btn va-end" title="Görüşmeyi bitir" aria-label="Görüşmeyi bitir" hidden>${svg("stop")}</button>
          </form>
          <button type="button" class="link va-new" hidden>Yeni sohbet başlat</button>
        </div>
        <aside class="va-results"><div class="va-empty faint">${topic ? "Bulunan yayınlar burada listelenecek." : "Önerilen akademisyenler burada listelenecek."}</div></aside>`;
      $(".va-start", this.root).onclick = () => this.start(true);
      $(".va-bar", this.root).onsubmit = (e) => { e.preventDefault(); this.sendText(); };
      $(".va-mic", this.root).onclick = () => this.setMuted(!this.muted);
      $(".va-end", this.root).onclick = () => this.stop(true);
      $(".va-attach", this.root).onclick = () => $(".va-file", this.root).click();
      $(".va-file", this.root).onchange = (e) => { const f = e.target.files?.[0]; e.target.value = ""; if (f) this.sendDocument(f); };
      $(".va-new", this.root).onclick = () => this.reset();
      this.restore();
      fetch("/api/settings/assistant").then((r) => r.json()).then((cfg) => {
        $(".va-name", this.root).textContent = cfg.name || "Asistan";
        if (!cfg.ready) this.setStatus("Sesli asistan için Ayarlar'da Gemini anahtarı girin.");
      }).catch(() => {});
    }

    setState(state, label) {
      this.state = state; this.orb.state = state;
      this.root.dataset.state = state;
      this.setStatus(label || STATUS[state] || "");
    }
    setStatus(text) { const el = $(".va-status", this.root); if (el) el.textContent = text; }

    async start(withMic, resume = false) {
      if (this.ws) return;
      this.root.classList.add("va-live");
      $(".va-start", this.root).hidden = true; $(".va-note", this.root).hidden = true;
      $(".va-end", this.root).hidden = false;
      this.setState("connecting");
      if (!this.playCtx) try {
        this.playCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: this.recvRate });
        if (this.playCtx.state === "suspended") await this.playCtx.resume();
        this.analyser = this.playCtx.createAnalyser(); this.analyser.fftSize = 512;
        this.analyser.connect(this.playCtx.destination); this.analyserData = new Uint8Array(this.analyser.fftSize);
      } catch { /* ses çalınamazsa yazı yine görünür */ }
      const proto = location.protocol === "https:" ? "wss" : "ws";
      this.ws = new WebSocket(`${proto}://${location.host}/ws/assistant?mode=${this.mode}`);
      this.ws.onmessage = (e) => this.onMessage(e);
      const ws = this.ws;
      ws.onclose = () => { if (this.ws === ws) this.dropped(); };
      ws.onerror = () => this.setStatus("Bağlantı kurulamadı.");
      await new Promise((resolve) => { ws.onopen = resolve; setTimeout(resolve, 8000); });
      // İlk mesaj: önceki konuşma (asistan kaldığı yerden devam etsin) ve bunun kendiliğinden yeniden bağlanma olup olmadığı.
      if (ws.readyState === 1) ws.send(JSON.stringify({ type: "hello", resume, history: this.saved.messages.slice(-24) }));
      if (withMic && !this.micStream) {
        try { await this.startMic(); $(".va-mic", this.root).hidden = false; }
        catch { this.muted = true; this.addNote("Mikrofon izni verilmedi; yazarak konuşabilirsin."); }
      }
    }

    async startMic() {
      this.micStream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
      this.micCtx = new (window.AudioContext || window.webkitAudioContext)();
      if (this.micCtx.state === "suspended") await this.micCtx.resume();
      const src = this.micCtx.createMediaStreamSource(this.micStream);
      const code = `class MicProc extends AudioWorkletProcessor {
        constructor() { super(); this.ratio = sampleRate / ${this.sendRate}; this.acc = 0; }
        process(inputs) {
          const ch = inputs[0][0]; if (!ch) return true;
          const out = []; let level = 0;
          for (let i = 0; i < ch.length; i++) {
            level += ch[i] * ch[i]; this.acc += 1;
            if (this.acc >= this.ratio) { this.acc -= this.ratio; const s = Math.max(-1, Math.min(1, ch[i])); out.push(s < 0 ? s * 0x8000 : s * 0x7fff); }
          }
          if (out.length) { const buf = new Int16Array(out); this.port.postMessage({ pcm: buf.buffer, level: Math.sqrt(level / ch.length) }, [buf.buffer]); }
          return true;
        }
      }
      registerProcessor('va-mic', MicProc);`;
      const url = URL.createObjectURL(new Blob([code], { type: "application/javascript" }));
      await this.micCtx.audioWorklet.addModule(url); URL.revokeObjectURL(url);
      this.worklet = new AudioWorkletNode(this.micCtx, "va-mic");
      this.worklet.port.onmessage = (e) => {
        this.micLevel = Math.min(1, Math.pow(e.data.level * 4.2, 0.75));
        if (!this.muted && this.ws?.readyState === 1) this.ws.send(JSON.stringify({ type: "audio", pcm: b64(e.data.pcm) }));
      };
      src.connect(this.worklet);
      const sink = this.micCtx.createGain(); sink.gain.value = 0; this.worklet.connect(sink); sink.connect(this.micCtx.destination);
    }

    onMessage(e) {
      let m; try { m = JSON.parse(e.data); } catch { return; }
      switch (m.type) {
        case "ready":
          $(".va-name", this.root).textContent = m.name || "Asistan";
          this.readyAt = Date.now();
          console.info("[asistan] model:", m.model);
          this.recvRate = m.receive_rate || this.recvRate;
          this.setState(this.muted ? "muted" : "listening");
          break;
        case "state": this.setState(m.state, m.tool ? TOOL_LABEL[m.tool] : ""); break;
        case "audio": this.play(m.pcm); break;
        case "interrupted": this.cutAudio(); break;
        case "partial": this.bubble(m.speaker, m.text, true); break;
        case "message": this.bubble(m.speaker, m.text, false); break;
        case "turn_complete": if (this.state === "thinking") this.setState(this.muted ? "muted" : "listening"); break;
        case "results": this.results(m); break;
        case "document": this.addNote(`📎 ${m.name} okundu (${m.chars.toLocaleString("tr-TR")} karakter).`); break;
        case "error": this.addNote(m.message, true); this.setStatus(m.message); break;
        case "reconnect": this.reconnectWanted = true; break;
      }
    }

    /* ---- ses çalma ---- */
    play(pcm64) {
      if (!this.playCtx) return;
      const bytes = unb64(pcm64), int16 = new Int16Array(bytes), f32 = new Float32Array(int16.length);
      for (let i = 0; i < int16.length; i++) f32[i] = int16[i] / 0x8000;
      const buf = this.playCtx.createBuffer(1, f32.length, this.recvRate);
      buf.copyToChannel(f32, 0);
      const node = this.playCtx.createBufferSource();
      node.buffer = buf; node.connect(this.analyser);
      const now = this.playCtx.currentTime;
      if (this.playHead < now) this.playHead = now + 0.03;
      node.start(this.playHead); this.playHead += buf.duration;
      this.nodes.push(node);
      node.onended = () => {
        this.nodes = this.nodes.filter((n) => n !== node);
        if (!this.nodes.length && this.state === "speaking") this.setState(this.muted ? "muted" : "listening");
      };
      if (this.state !== "speaking") this.setState("speaking");
    }
    cutAudio() {  // kullanıcı söze girdi: sıradaki ses atılır
      this.nodes.forEach((n) => { try { n.stop(); } catch { /* bitti */ } });
      this.nodes = []; this.playHead = 0;
      this.setState(this.muted ? "muted" : "listening");
    }

    /* ---- sohbet ---- */
    bubble(speaker, text, partial) {
      if (!text) return;
      const chat = $(".va-chat", this.root), who = speaker === "user" ? "user" : "bot";
      let el = chat.querySelector(`.va-msg.${who}.partial`);
      if (!el) {
        el = document.createElement("div");
        el.className = `va-msg ${who}`;
        chat.appendChild(el);
      }
      el.textContent = text;
      el.classList.toggle("partial", partial);
      chat.scrollTop = chat.scrollHeight;
      if (!partial) {
        this.saved.messages.push({ speaker: who === "user" ? "user" : "assistant", text, at: Date.now() });
        store.save(this.mode, this.saved);
        $(".va-new", this.root).hidden = false;
      }
    }
    restore() {  // önceki konuşmayı ve son sonuçları çiz
      const chat = $(".va-chat", this.root);
      this.saved.messages.forEach((msg) => {
        const el = document.createElement("div");
        el.className = `va-msg ${msg.speaker === "user" ? "user" : "bot"} old`;
        el.textContent = msg.text;
        chat.appendChild(el);
      });
      if (this.saved.messages.length) {
        const note = document.createElement("div");
        note.className = "va-msg note"; note.textContent = "Önceki konuşma · asistan kaldığınız yerden devam eder";
        chat.prepend(note);
        $(".va-new", this.root).hidden = false;
        chat.scrollTop = chat.scrollHeight;
      }
      [...this.saved.results].reverse().forEach((r) => this.results(r, false));
    }
    reset() {  // yeni sohbet: geçmiş silinir, görüşme açıksa yeniden başlar
      const live = Boolean(this.ws);
      this.saved = { messages: [], results: [] }; store.clear(this.mode);
      $(".va-chat", this.root).innerHTML = "";
      $(".va-results", this.root).innerHTML = `<div class="va-empty faint">${this.mode === "topic" ? "Bulunan yayınlar burada listelenecek." : "Önerilen akademisyenler burada listelenecek."}</div>`;
      $(".va-new", this.root).hidden = true;
      if (live) { this.closeConnection(); this.start(!this.muted); }
    }
    addNote(text, error) {
      const chat = $(".va-chat", this.root), el = document.createElement("div");
      el.className = `va-msg note${error ? " err" : ""}`; el.textContent = text;
      chat.appendChild(el); chat.scrollTop = chat.scrollHeight;
    }
    async sendText() {
      const input = $(".va-text", this.root), text = input.value.trim();
      if (!text) return;
      if (!this.ws) { await this.start(false); }
      if (this.ws?.readyState === 1) { this.ws.send(JSON.stringify({ type: "text", text })); input.value = ""; }
    }
    async sendDocument(file) {
      if (file.size > 10e6) { this.addNote(`${file.name}: 10 MB'tan büyük belge gönderilemez.`, true); return; }
      if (!this.ws) await this.start(false);
      const data = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(",")[1] || "");
        reader.onerror = reject; reader.readAsDataURL(file);
      });
      this.addNote(`📎 ${file.name} gönderiliyor…`);
      if (this.ws?.readyState === 1) this.ws.send(JSON.stringify({ type: "document", name: file.name, data }));
    }
    setMuted(muted) {
      this.muted = muted;
      $(".va-mic", this.root).innerHTML = svg(muted ? "micOff" : "mic");
      $(".va-mic", this.root).classList.toggle("off", muted);
      if (this.ws?.readyState === 1) this.ws.send(JSON.stringify({ type: "mute", value: muted }));
      if (this.state === "listening" || this.state === "muted") this.setState(muted ? "muted" : "listening");
    }

    /* ---- sonuç kartları ---- */
    results(m, remember = true) {
      const box = $(".va-results", this.root);
      if (remember) { this.saved.results.unshift(m); this.saved.results = this.saved.results.slice(0, 4); store.save(this.mode, this.saved); }
      $(".va-empty", box)?.remove();
      const head = `<div class="va-res-head"><b>${esc(m.kind === "topics" ? "Yayınlar" : m.kind === "advisors" ? "Akademisyenler" : "Web")}</b>
        <span>${esc(m.query)}${m.university ? " · " + esc(m.university) : ""}${m.total ? ` · ${m.total} sonuç` : ""}</span>
        ${m.link ? `<a class="va-more" href="${esc(m.link)}">Tamamını aç</a>` : ""}</div>`;
      let body = "";
      if (m.kind === "topics") {
        body = m.items.map((p, i) => {
          const url = safe(p.doi ? `https://doi.org/${p.doi}` : p.url);
          return `<article class="va-card" style="--i:${i}"><h4>${url ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(p.title)}</a>` : esc(p.title)}</h4>
            <p class="va-meta">${esc([p.year, p.venue, p.citations ? p.citations + " atıf" : ""].filter(Boolean).join(" · "))}</p>
            ${p.authors?.length ? `<p class="va-sub">${esc(p.authors.join(", "))}</p>` : ""}
            ${p.abstract ? `<p class="va-abs">${esc(p.abstract)}</p>` : ""}</article>`;
        }).join("");
      } else if (m.kind === "advisors") {
        body = m.items.map((a, i) => {
          const href = a.chat_id ? `#/profil/${encodeURIComponent(a.chat_id)}` : `#/akademisyenler?q=${encodeURIComponent(a.name)}`;
          return `<article class="va-card va-person" style="--i:${i}"><div class="va-av">${esc(initials(a.name))}</div><div>
            <h4><a href="${esc(href)}">${esc([a.title, a.name].filter(Boolean).join(" "))}</a>${a.match ? `<span class="va-match">%${a.match}</span>` : ""}</h4>
            <p class="va-meta">${esc([a.institution, a.department].filter(Boolean).join(" · "))}</p>
            <p class="va-sub">${esc([`${a.works} ilgili yayın`, a.last_year ? `son ${a.last_year}` : "", a.theses ? `${a.theses} tez` : ""].filter(Boolean).join(" · "))}</p>
            ${a.topics?.length ? `<div class="va-chips">${a.topics.map((t) => `<span>${esc(t)}</span>`).join("")}</div>` : ""}</div></article>`;
        }).join("");
      } else {
        body = (m.text ? `<p class="va-abs va-web">${esc(m.text).replace(/\n/g, "<br>")}</p>` : "")
          + (m.links || []).map((l, i) => `<article class="va-card" style="--i:${i}"><h4><a href="${esc(safe(l.url))}" target="_blank" rel="noopener">${esc(l.title || l.url)} ${svg("ext")}</a></h4>${l.snippet ? `<p class="va-sub">${esc(l.snippet)}</p>` : ""}</article>`).join("");
      }
      const group = document.createElement("section");
      group.className = "va-group";
      group.innerHTML = head + body;
      box.prepend(group);
    }

    loop(now) {
      if (!this.root.isConnected) { this.stop(false); return; }  // sayfadan çıkıldı: mikrofon ve bağlantı kapanır
      if (this.analyser) {
        this.analyser.getByteTimeDomainData(this.analyserData);
        let sum = 0;
        for (let i = 0; i < this.analyserData.length; i++) { const v = (this.analyserData[i] - 128) / 128; sum += v * v; }
        this.playLevel = Math.min(1, Math.pow(Math.sqrt(sum / this.analyserData.length) * 3.5, 0.75));
      }
      const target = this.state === "speaking" ? this.playLevel : this.state === "listening" ? this.micLevel : 0;
      this.orb.draw(now, target);
      if ((this.frame = (this.frame || 0) + 1) % 12 === 0) this.root.style.setProperty("--va-a", this.orb.color(0, 1));
      this.raf = requestAnimationFrame(this.loop);
    }

    closeConnection() {
      const ws = this.ws; this.ws = null;
      try { ws?.close(); } catch { /* kapalı */ }
      this.cutAudio();
    }
    dropped() {
      // Model bağlantıyı kapattı: konuşma birkaç saniyeden uzun sürdüyse mikrofon açık kalarak kendiliğinden yeniden
      // bağlanılır (geçmiş asistana verilir, selam tekrarlanmaz). Art arda kopmada dur.
      this.ws = null; this.cutAudio();
      const lived = this.readyAt && Date.now() - this.readyAt > 3000;
      if (this.root.isConnected && (this.reconnectWanted || lived) && this.retries < 3) {
        this.retries = lived ? 1 : this.retries + 1;
        this.reconnectWanted = false;
        this.addNote("Bağlantı yenileniyor…");
        setTimeout(() => this.start(false, true), 600);
        return;
      }
      this.stop(false);
    }
    stop(byUser) {
      this.closeConnection();
      try { this.micStream?.getTracks().forEach((t) => t.stop()); } catch { /* yok */ }
      try { this.micCtx?.close(); } catch { /* yok */ }
      try { this.playCtx?.close(); } catch { /* yok */ }
      this.micStream = this.micCtx = this.playCtx = this.analyser = null;
      if (!this.root.isConnected) { cancelAnimationFrame(this.raf); if (active === this) active = null; return; }
      this.root.classList.remove("va-live");
      $(".va-start", this.root).hidden = false; $(".va-end", this.root).hidden = true; $(".va-mic", this.root).hidden = true;
      $(".va-start", this.root).innerHTML = `${svg("mic")}${byUser ? "Yeniden konuş" : "Yeniden bağlan"}`;
      this.setState("ended");
    }
  }

  function initials(name) { return String(name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase(); }
  function b64(buffer) { const bytes = new Uint8Array(buffer); let s = ""; for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]); return btoa(s); }
  function unb64(str) { const bin = atob(str), out = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i); return out.buffer; }

  /** Sayfaya asistan paneli ekler: mode "topic" (Konu bul) ya da "advisor" (Danışman bul). */
  window.mountAssistant = function (mode, host) {
    if (!host) return null;
    if (active && !active.root.isConnected) active.stop(false);
    const root = document.createElement("section");
    root.className = "card va";
    root.dataset.state = "idle";
    const head = host.querySelector(":scope > .section-head");  // sayfa başlığının hemen altına
    if (head) head.after(root); else host.prepend(root);
    active = new Assistant(root, mode === "advisor" ? "advisor" : "topic");
    return active;
  };
})();
