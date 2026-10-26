// Akademik İz — sohbet tarzı arayüz (bağımlılıksız)
const $ = (s, r = document) => r.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const safeUrl = (u) => { try { const x = new URL(u); return ["http:", "https:"].includes(x.protocol) ? x.href : ""; } catch { return ""; } };

const thread = $("#thread");
let jobId = null, result = null, chatId = null;
let chatRequest = null;
let paperRequest = null;

function setChatBusy(value) {
  $("#send").disabled = value || !result;
  document.querySelectorAll(".suggest button").forEach((button) => { button.disabled = value; });
}
const SOURCE_NAMES = { openalex: "OpenAlex", crossref: "Crossref", orcid: "ORCID", yok: "YÖK", scholar: "Scholar" };
const PROV = { university: "kurum sayfası", "rea-json": "REA · gizli API", yok: "YÖK Akademik", openalex: "OpenAlex", scholar: "Scholar", llm: "Gemini (metinde doğrulandı)", consensus: "kaynak uzlaşısı" };

function addMsg(role, html, wide = false) {
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  el.innerHTML = `<div class="avatar">${role === "bot" ? "◈" : "●"}</div><div class="bubble ${wide ? "wide" : ""}">${html}</div>`;
  thread.appendChild(el);
  thread.scrollTop = thread.scrollHeight;
  return $(".bubble", el);
}

async function loadEnv() {
  try {
    const h = await (await fetch("/api/health")).json();
    $("#env").innerHTML = [
      ["REA CLI", h.rea ? "✓ hazır" : "✗ yok"], ["Chromium", h.chromium ? "✓ hazır" : "✗ yok"], ["LLM", h.llm],
    ].map(([k, v]) => `<div><span>${k}</span><span>${esc(v)}</span></div>`).join("");
  } catch { $("#env").textContent = "Sunucuya ulaşılamadı"; }
}

// Kullanıcıya gösterilen sade aşamalar; ham teknik loglar "Teknik ayrıntılar" altında kapalı durur.
const PHASES = [
  ["reverse", "Site yapısı çözümleniyor (tersine mühendislik)"],
  ["scrape", "Site sayfa sayfa taranıyor"],
  ["bot", "Bot koruması aşılıyor"],
  ["collect", "Akademik kaynaklardan yayınlar toplanıyor"],
  ["merge", "Veriler birleştiriliyor ve doğrulanıyor"],
  ["ai", "Yapay zekâ modeli hazırlanıyor"],
];
const PHASE_NOW = {
  reverse: "Sitenin arka planda hangi istekleri kullandığı inceleniyor…",
  scrape: "Sayfalar okunuyor, akademisyen aranıyor…",
  bot: "Sitenin bot koruması aşılıyor…",
  collect: "Yayınlar açık akademik kaynaklardan toplanıyor…",
  merge: "Tekrarlanan kayıtlar birleştiriliyor, bilgiler doğrulanıyor…",
  ai: "Araştırma profili yapay zekâ ile çıkarılıyor…",
};
function phaseOf(ev) {
  if (/duvar|stealth|cloudflare|turnstile|bot koruma|418|403|429/i.test(ev.message)) return "bot";
  return { rea: "reverse", scrape: "scrape", crawl: "scrape", yok: "collect", publications: "collect",
           dedup: "merge", verify: "merge", analysis: "ai" }[ev.step] || "scrape";
}

function busy(v) { ["#go", "#url", "#name"].forEach((s) => ($(s).disabled = v)); }

async function start() {
  const url = $("#url").value.trim(), name = $("#name").value.trim();
  if (!url || !name) { addMsg("bot", "Lütfen hem kadro linkini hem akademisyen adını gir."); return; }
  addMsg("user", `<b>${esc(name)}</b><br><span class="prov">${esc(url)}</span>`);
  busy(true); $("#question").disabled = true; $("#send").disabled = true; result = null; chatId = null;

  const res = await fetch("/api/jobs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url, name }) });
  if (!res.ok) { addMsg("bot", `⚠ ${esc((await res.json()).detail || "İstek reddedildi")}`); busy(false); return; }
  const job = await res.json(); jobId = job.id;

  const bubble = addMsg("bot", `<div class="steps">${PHASES.map(([k, label]) =>
    `<div class="step" data-phase="${k}" ${k === "bot" ? "hidden" : ""}><span class="dot"></span>${esc(label)}</div>`).join("")}</div>
    <div class="now"></div>
    <details class="tech"><summary>Teknik ayrıntılar</summary><div class="log"></div></details>`, true);
  const log = $(".log", bubble);
  const now = $(".now", bubble);

  const es = new EventSource(`/api/jobs/${jobId}/events`);
  es.onmessage = (e) => {
    const ev = JSON.parse(e.data);
    if (ev.type === "log") {
      const phase = phaseOf(ev);
      const st = $(`.step[data-phase="${phase}"]`, bubble);
      if (st) {
        st.hidden = false;
        // sıradaki aşamaya geçildiyse öncekiler tamamlandı
        const order = PHASES.map(([k]) => k);
        [...bubble.querySelectorAll(".step.running")].forEach((x) => {
          if (x !== st && order.indexOf(x.dataset.phase) < order.indexOf(phase)) { x.className = "step done"; $(".dot", x).textContent = "✓"; }
          if (x !== st && x.dataset.phase === "bot") { x.className = "step done"; $(".dot", x).textContent = "✓"; }
        });
        if (!st.classList.contains("done") || ev.status === "running") {
          st.className = `step ${ev.status === "warning" ? "running" : ev.status}`;
          $(".dot", st).textContent = ev.status === "done" ? "✓" : "";
        }
        now.textContent = PHASE_NOW[phase] || "";
      }
      const line = document.createElement("div");
      line.className = ev.status === "warning" ? "warning" : "";
      line.innerHTML = `<span class="t">${ev.t.toFixed(1).padStart(5)}s</span> <span class="s">${esc(ev.step)}</span> ${esc(ev.message)}`;
      log.appendChild(line); log.scrollTop = log.scrollHeight; thread.scrollTop = thread.scrollHeight;
    } else if (ev.type === "result") {
      [...bubble.querySelectorAll(".step:not([hidden])")].forEach((x) => { x.className = "step done"; $(".dot", x).textContent = "✓"; });
      now.textContent = "";
      result = ev.data; chatId = result.chat_id; render(result); loadChats();
    } else if (ev.type === "error") {
      addMsg("bot", `⚠ ${esc(ev.message)}`);
    } else if (ev.type === "end") {
      es.close(); busy(false);
    }
  };
  es.onerror = () => { es.close(); busy(false); };
}

function evidence(ids) {
  return (ids || []).map((id) => {
    const p = result.publications.find((x) => x.id === id);
    return p ? `<a class="ev" href="#" data-paper="${esc(id)}" title="${esc(p.title)}">${esc(id)} · ${esc(p.title)}</a>` : "";
  }).join("");
}

function claims(items, tl = false) {
  if (!items?.length) return `<p class="prov">Desteklenen bir çıkarım bulunamadı.</p>`;
  return items.map((c) => `<div class="claim">${tl ? `<strong>${esc(c.period)}</strong>` : `<strong>${esc(c.label)}</strong>`}${esc(c.text)}<div>${evidence(c.evidence)}</div></div>`).join("");
}

function vbadge(key) {
  const v = result.profile.verification?.[key];
  if (!v) return "";
  const cls = { "doğrulandı": "ok", "tek kaynak": "single", "çelişki": "conflict", "değişti": "changed" }[v.status] || "single";
  const icon = { "doğrulandı": "✓", "tek kaynak": "·", "çelişki": "⚠", "değişti": "↻" }[v.status] || "";
  const alt = v.alternatives?.length ? ` | alternatif: ${v.alternatives.map((a) => `${a.value} (${a.sources.join("+")})`).join("; ")}` : "";
  return `<span class="vb ${cls}" title="Kaynaklar: ${esc(v.sources.join(", "))} · ${v.runs_seen}. çalıştırma · güven ${Math.round(v.confidence * 100)}%${esc(alt)}">${icon} ${esc(v.status)} · ${v.sources.length} kaynak</span>`;
}

function prov(key) {
  const p = result.profile.provenance?.[key];
  if (!p) return "";
  const src = PROV[p.source] || p.source; const u = safeUrl(p.url);
  return ` <span class="prov">· ${u ? `<a href="${u}" target="_blank" rel="noopener">${esc(src)}</a>` : esc(src)}</span>`;
}

function render(r) {
  const p = r.profile, a = r.analysis;
  const initials = (p.name || "?").split(" ").filter(Boolean).slice(0, 2).map((x) => x[0]).join("");
  const links = Object.entries(p.links || {}).map(([k, v]) => {
    const href = k === "orcid" ? `https://orcid.org/${v}` : safeUrl(v);
    return href ? `<a class="chip alt" href="${href}" target="_blank" rel="noopener">${esc(k.toUpperCase())} ↗</a>` : "";
  }).join("");
  const ok = r.unique_count > 0;
  const rec = r.recon || {};
  const reaLines = [];
  const rcp = rec.recipe || {};
  if (rec.rea) reaLines.push(`<b>REA keşfi</b> (${esc(rec.rea.evidence_id?.slice(0, 18))}…): ${rec.rea.requests} istek · ${rec.rea.api_calls.length} XHR/fetch · ${rec.rea.third_party} izleyici · içerik kaynağı: <b>${esc(rec.content_origin || "?")}</b>`);
  if (rec.hidden_api) reaLines.push(`<b>Gizli API</b>: ${esc(rec.hidden_api.method)} ${esc(rec.hidden_api.url)} → ${esc(rec.hidden_api.path)}`);
  (rec.agent?.steps || []).forEach((st, i) => reaLines.push(`<b>Ajan kararı ${i + 1}</b> (Gemini): ${esc(st.action)} ${st.chosen.map((u) => esc(u)).join(" · ")} <span class="prov">— ${esc(st.reason)}</span>`));
  if (rec.agent?.found_at) reaLines.push(`<b>Ajan</b>: <span class="ev-ok">kişi bulundu → ${esc(rec.agent.found_at)}</span>`);
  if (rcp.detail) reaLines.push(`<b>Detay butonu</b>: ${rcp.detail.replayed ? `<span class="ev-ok">tarif tarayıcısız oynatıldı (${rcp.detail.elapsed} sn)</span>` : `REA öğrendi → ${esc(rcp.detail.method)} ${esc(rcp.detail.url)} (${esc(rcp.detail.body || "")}, kimlik: ${esc(rcp.detail.id_attr)})`}`);
  if (rec.crawl?.pages) reaLines.push(`<b>Crawler</b>: ${rec.crawl.pages} sayfa → ${esc(rec.crawl.found_at || "bulunamadı")}`);
  if (rec.yok_rea) reaLines.push(`<b>YÖK formu (REA)</b>: ${esc(rec.yok_rea.method)} ${esc(rec.yok_rea.url)} · gövde: ${esc(rec.yok_rea.body)}`);
  if (rcp.start_page?.known) reaLines.push(`<b>Değişiklik algılama</b>: başlangıç sayfası yapı benzerliği %${Math.round(rcp.start_page.similarity * 100)} → ${rcp.start_page.drift ? '<span class="ev-drift">DEĞİŞMİŞ, REA yeniden öğrendi</span>' : '<span class="ev-ok">değişmemiş, REA atlandı</span>'}`);
  if (rcp.replay) reaLines.push(`<b>Tarif tekrarı</b>: ${rcp.replay.ok ? `<span class="ev-ok">✓ ${esc(rcp.replay.method)} ${esc(rcp.replay.url)} · ${rcp.replay.elapsed} sn, tarayıcısız</span>` : `<span class="ev-drift">✗ ${esc(rcp.replay.error)}</span>`}`);
  if (rcp.card) reaLines.push(`<b>Scrapling adaptive</b>: kişi kartı ${rcp.card === "relocated" ? '<span class="ev-drift">yapı değişmiş, benzerlikle yeniden bulundu</span>' : '<span class="ev-ok">aynı seçiciyle bulundu</span>'}`);
  (rcp.events || []).forEach((e) => reaLines.push(`<span class="${e.kind === "drift" ? "ev-drift" : "ev-ok"}">• ${esc(e.detail)}</span>`));
  if (rec.yok_rea?.replayed) reaLines.push(`<b>YÖK tarifi</b>: <span class="ev-ok">REA'sız tekrar oynatıldı (${rec.yok_rea.elapsed} sn)</span>`);
  (rec.walls || []).forEach((w) => reaLines.push(`<b>Duvar</b>: ${esc(w.url)} (${esc(w.reason)}) → stealth ile aşıldı`));

  const html = `
  <div class="done-banner ${ok ? "" : "partial"}"><div class="big">${ok ? "✓ Tamamlandı" : "⚠ Kısmi sonuç"}</div>
    <div>${esc(r.summary)}<br><span class="prov">${r.elapsed}s · ${esc(r.llm)}</span></div></div>

  <div class="card"><div class="head"><div class="initials">${esc(initials)}</div><div>
    <h2>${esc(p.name)}</h2>
    <p>${esc(p.title || "Unvan bulunamadı")}${vbadge("title")}${prov("title")}</p>
    <p>${esc(p.department || "Bölüm bulunamadı")}${vbadge("department")}${prov("department")}</p>
    <p>${esc(p.institution || "Kurum bulunamadı")}${vbadge("institution")}${prov("institution")}</p>
    ${p.orcid ? `<p class="prov">ORCID ${esc(p.orcid)}${vbadge("orcid")}</p>` : ""}</div></div>
    <div class="chips" style="margin-top:12px">${links}${safeUrl(p.source_url) ? `<a class="chip alt" href="${safeUrl(p.source_url)}" target="_blank" rel="noopener">Kurum profili ↗</a>` : ""}</div>
    <div class="kpis">
      <div class="kpi"><b>${r.raw_count}</b><span>ham kayıt</span></div>
      <div class="kpi"><b>${r.unique_count}</b><span>benzersiz yayın</span></div>
      <div class="kpi"><b>${r.dedup.cross_lang}</b><span>TR↔EN birleştirme</span></div>
      <div class="kpi"><b>${r.paper_verification?.verified ?? 0}/${r.unique_count}</b><span>doğrulanmış yayın</span></div>
      <div class="kpi"><b>${Object.entries(r.by_source).map(([k, v]) => `${SOURCE_NAMES[k] || k}:${v}`).join(" ") || "-"}</b><span>kaynak dağılımı</span></div>
      <div class="kpi"><b>${Object.entries(r.languages).map(([k, v]) => `${k} ${v}`).join(" · ") || "-"}</b><span>yayın dili</span></div>
    </div>
    ${p.verification?.interests?.length ? `<h3 style="margin-top:14px">İlgi alanları · kaynak teyidiyle</h3><div class="chips">${p.verification.interests.slice(0, 12).map((x) =>
      `<span class="chip alt" title="${esc(x.sources.join(", "))} · ${x.runs_seen}. çalıştırma">${esc(x.value)}${x.sources.length > 1 || x.runs_seen > 1 ? `<sup>✓${x.sources.length}</sup>` : ""}</span>`).join("")}</div>`
      : p.interests?.length ? `<h3 style="margin-top:14px">İlgi alanları${prov("interests")}</h3><div class="chips">${p.interests.map((x) => `<span class="chip alt">${esc(x)}</span>`).join("")}</div>` : ""}
  </div>

  <div class="card"><h3>Araştırma alanları <span class="badge mode">${a.mode === "llm" || a.mode === "ollama" ? "GEMINI · " + esc(a.model) : a.mode === "mock" ? "MOCK ANALİZ" : "ANALİZ YOK"}</span></h3>
    <div class="chips" style="margin-bottom:8px">${a.areas.map((x) => `<span class="chip">${esc(x.label)}</span>`).join("")}</div>
    ${a.summary ? `<p>${esc(a.summary)}</p>` : ""}${claims(a.areas)}</div>

  <div class="grid2" style="margin-top:14px">
    <div class="card"><h3>Yöntemler</h3>${claims(a.methods)}</div>
    <div class="card"><h3>Yıllara göre odak değişimi</h3><div class="timeline">${claims(a.timeline, true)}</div></div>
  </div>

  <div class="card"><h3>Yayınlar · ${r.raw_count} ham kayıt, ${r.unique_count} benzersiz yayın</h3>
    <div class="filters"><input id="pubFilter" placeholder="Başlıkta ara…"></div>
    <div style="overflow-x:auto"><table><thead><tr><th>#</th><th>Başlık</th><th>Yıl</th><th>Dil</th><th>Kaynak</th><th>Doğrulama</th><th>Atıf</th></tr></thead>
    <tbody id="pubs">${r.publications.map((x) => `<tr id="pub-${esc(x.id)}" data-q="${esc((x.title + " " + x.variants.map((v) => v.title).join(" ")).toLowerCase())}">
      <td>${esc(x.id)}</td>
      <td><a href="#" data-paper="${esc(x.id)}">${esc(x.title)}</a>
        ${x.variants.length > 1 ? `<div class="variants">↳ birleştirilen varyantlar: ${x.variants.slice(1).map((v) => `${esc(v.title)} (${esc(v.lang)}, ${esc(SOURCE_NAMES[v.source] || v.source)})`).join(" · ")}</div>` : ""}
        ${x.venue ? `<div class="variants">${esc(x.venue)}</div>` : ""}</td>
      <td>${esc(x.year || "—")}</td><td>${esc(x.language_names.join(", "))}</td>
      <td>${x.sources.map((s) => `<span class="badge">${esc(SOURCE_NAMES[s] || s)}</span>`).join(" ")}</td>
      <td>${x.verified ? `<span class="vb ok">✓ ${x.sources.length > 1 ? x.sources.length + " kaynak" : x.runs_seen + ". kez"}</span>` : `<span class="vb single">tek kaynak</span>`}${x.is_new ? `<span class="newb">YENİ</span>` : ""}</td>
      <td>${esc(x.citations ?? "—")}</td></tr>`).join("")}</tbody></table></div></div>

  ${reaLines.length ? `<details class="card tech-card"><summary><h3>Teknik iz · REA + Scrapling</h3></summary><div class="recon">${reaLines.map((l) => `<div>${l}</div>`).join("")}</div></details>` : ""}

  <div class="suggest">${["En çok atıf alan yayınları hangileri?", "Son yıllarda hangi konulara yöneldi?", "Hangi yöntemleri kullanıyor?", "En sık kimlerle çalışıyor?"].map((q) => `<button type="button" data-q="${esc(q)}">${esc(q)}</button>`).join("")}</div>`;
  addMsg("bot", html, true);
  $("#question").disabled = false; $("#send").disabled = false;
  $("#question").placeholder = `${p.name} hakkında bir şey sor…`; $("#question").focus();
}

const MODE_NAMES = { auto: "Otomatik", rag: "RAG", cag: "CAG", hybrid: "Hibrit" };
function metaLine(m) {
  if (!m || !m.mode) return "";
  const k = (n) => (n >= 1000 ? (n / 1000).toFixed(1) + "k" : n);
  const parts = [`<b>${esc(MODE_NAMES[m.mode] || m.mode)}</b>${m.route && m.route !== "elle seçildi" ? ` <span class="why">· ${esc(m.route)}</span>` : ""}`,
    `bağlam ~${k(m.context_tokens)} token`];
  if (m.prompt_eval_s != null) parts.push(`prompt işleme ${m.prompt_eval_s} sn${m.mode !== "rag" ? " (aynı önek → KV önbelleği)" : ""}`);
  if (m.retriever) parts.push(`${esc(m.retriever)} → ${(m.retrieved || []).map((id) => `<span class="cite" data-pub="${esc(id)}">${esc(id)}</span>`).join(" ")}`);
  if (m.ttft != null) parts.push(`ilk token ${m.ttft} sn`);
  if (m.total_s != null) parts.push(`toplam ${m.total_s} sn`);
  if (m.model === "mock") parts.push("mock (LLM kapalı)");
  return `<div class="meta">${parts.join(" · ")}</div>`;
}

function formatAnswer(text) {
  return esc(text).replace(/\[(P\d+)\]/g, (_, id) => `<span class="cite" data-pub="${id}">${id}</span>`)
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/\n/g, "<br>");
}

async function ask(question) {
  if (!question || !result || chatRequest) return;
  jobId = result.job_id || jobId;
  const controller = new AbortController();
  chatRequest = controller;
  setChatBusy(true);
  addMsg("user", esc(question));
  const bubble = addMsg("bot", `<div class="answer typing"></div><div class="prov chat-stage" role="status">Yanıt hazırlanıyor…</div>`, false);
  const out = $(".answer", bubble);
  const stage = $(".chat-stage", bubble);
  let text = "";
  let completed = false, failure = "", reader = null;
  const deadline = setTimeout(() => controller.abort(), 150000);
  try {
    const res = await fetch(`/api/jobs/${jobId}/chat`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, chat_id: chatId, mode: "auto" }), signal: controller.signal,
    });
    if (!res.ok) {
      const error = await res.json().catch(() => ({}));
      throw new Error(typeof error.detail === "string" ? error.detail : `İstek başarısız (HTTP ${res.status}).`);
    }
    if (!res.body) throw new Error("Sunucu cevap akışı açmadı.");
    reader = res.body.getReader();
    const dec = new TextDecoder(); let buf = "";
    const event = (part) => {
      const data = part.split(/\r?\n/).filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trimStart()).join("\n");
      if (!data) return;
      const msg = JSON.parse(data);
      if (msg.chat_id) chatId = msg.chat_id;
      if (msg.stage) stage.textContent = msg.stage;
      if (msg.delta) {
        text += msg.delta; out.innerHTML = formatAnswer(text); out.classList.remove("typing");
        stage.textContent = ""; thread.scrollTop = thread.scrollHeight;
      }
      if (msg.error) failure = msg.error;
      if (msg.done) { completed = true; out.insertAdjacentHTML("afterend", metaLine(msg.meta)); }
    };
    while (!completed) {
      const { value, done } = await reader.read();
      if (done) { buf += dec.decode(); if (buf.trim()) event(buf); break; }
      buf += dec.decode(value, { stream: true });
      const parts = buf.split(/\r?\n\r?\n/); buf = parts.pop();
      for (const part of parts) event(part);
    }
    if (failure) throw new Error(failure);
    if (!completed) throw new Error("Cevap tamamlanmadan bağlantı kesildi. Soruyu yeniden gönderebilirsin.");
    if (!text.trim()) throw new Error("Model boş cevap döndürdü.");
  } catch (error) {
    if (!text) out.textContent = "Cevap alınamadı.";
    stage.textContent = error.name === "AbortError"
      ? "Cevap bekleme süresi doldu veya sohbet değiştirildi."
      : `Hata: ${error.message}`;
  } finally {
    clearTimeout(deadline);
    if (reader) { await reader.cancel().catch(() => {}); reader.releaseLock(); }
    out.classList.remove("typing");
    if (chatRequest === controller) { chatRequest = null; setChatBusy(false); }
    loadChats();
  }
}

// ------------------------------------------------------------ sohbet geçmişi
async function loadChats() {
  let rows = [];
  try { rows = await (await fetch("/api/chats")).json(); } catch { /* sunucu yok */ }
  $("#chats").innerHTML = rows.length ? rows.map((c) => `
    <div class="chat-item ${c.id === chatId ? "active" : ""}" data-chat="${esc(c.id)}">
      <div class="ci-main"><b>${esc(c.name || "?")}</b><span>${esc(c.preview || c.institution || "")}</span>
      <small>${esc(c.updated)} · ${c.messages / 2 | 0} soru · ${c.papers} yayın</small></div>
      <button class="ci-del" data-del="${esc(c.id)}" title="Sohbeti sil">×</button></div>`).join("")
    : `<div class="prov">Henüz sohbet yok.</div>`;
}

function resetThread() {
  chatRequest?.abort();
  chatRequest = null;
  thread.innerHTML = "";
  result = null; chatId = null; jobId = null;
  $("#question").disabled = true; $("#send").disabled = true; $("#question").placeholder = "Önce bir profil oluşturun…";
}

async function openChat(cid) {
  const res = await fetch(`/api/chats/${cid}`);
  if (!res.ok) { loadChats(); return; }
  const { chat, result: r } = await res.json();
  resetThread();
  if (!r) { addMsg("bot", "Bu sohbetin profil sonucu bulunamadı."); return; }
  result = r; chatId = chat.id; jobId = chat.job_id;
  addMsg("user", `<b>${esc(r.profile.name)}</b><br><span class="prov">${esc(r.recon?.start_url || "")}</span>`);
  render(r);
  for (const m of chat.messages) {
    if (m.role === "user") addMsg("user", esc(m.content));
    else addMsg("bot", `<div class="answer">${formatAnswer(m.content)}</div>${metaLine(m.meta)}`);
  }
  loadChats();
}

async function deleteChat(cid) {
  if (!confirm("Bu sohbet ve kullanılmayan profil sonucu kalıcı olarak silinsin mi?")) return;
  await fetch(`/api/chats/${cid}`, { method: "DELETE" });
  if (cid === chatId) resetThread();
  loadChats();
}

async function openPaper(pid) {
  const p = result?.publications.find((x) => x.id === pid);
  if (!p) return;
  paperRequest?.abort();
  const controller = new AbortController();
  paperRequest = controller;
  const jid = result.job_id || jobId;
  const modal = $("#modal"), body = $("#modalBody");
  modal.hidden = false;
  body.innerHTML = `<div class="prov">${esc(pid)} · ${esc(p.year || "")} · ${p.sources.map((s) => esc(SOURCE_NAMES[s] || s)).join(" + ")}</div>
    <h2 class="m-title">${esc(p.title)}</h2><div id="mMeta" class="prov">${esc(p.venue || "")}</div>
    <div id="mStages" class="log small"></div>
    <h3 class="m-h">Türkçe özet</h3><div id="mSum" class="answer typing"></div>
    <h3 class="m-h">Özet (abstract)</h3><div id="mAbs" class="m-abs prov">Kaynak okunuyor…</div>
    <div id="mLinks" class="chips" style="margin-top:12px"></div>`;
  const stages = $("#mStages", body), metaEl = $("#mMeta", body), sumEl = $("#mSum", body);
  const absEl = $("#mAbs", body), linksEl = $("#mLinks", body);
  let text = "", reader = null, completed = false, failure = "", timedOut = false;
  const deadline = setTimeout(() => { timedOut = true; controller.abort(); }, 210000);
  try {
    const res = await fetch(`/api/jobs/${jid}/papers/${pid}`, { signal: controller.signal });
    if (!res.ok) {
      const error = await res.json().catch(() => ({}));
      throw new Error(typeof error.detail === "string" ? error.detail : `İstek başarısız (HTTP ${res.status}).`);
    }
    if (!res.body) throw new Error("Sunucu ayrıntı akışı açmadı.");
    reader = res.body.getReader();
    const dec = new TextDecoder(); let buf = "";
    const event = (part) => {
      const data = part.split(/\r?\n/).filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trimStart()).join("\n");
      if (!data || controller.signal.aborted || paperRequest !== controller) return;
      const m = JSON.parse(data);
      if (m.stage) stages.insertAdjacentHTML("beforeend", `<div>› ${esc(m.stage)}</div>`);
      if (m.meta) {
        const d = m.meta;
        metaEl.innerHTML = `${esc(d.journal || "")} ${d.date ? "· " + esc(d.date) : ""}<br>${esc((d.authors || []).slice(0, 12).join(", "))}`
          + (d.keywords?.length ? `<div class="chips" style="margin-top:8px">${d.keywords.map((k) => `<span class="chip">${esc(k)}</span>`).join("")}</div>` : "")
          + Object.entries(d.bibliography || {}).map(([label, value]) => `<div><b>${esc(label)}:</b> ${esc(value)}</div>`).join("");
        absEl.textContent = d.abstract || "Bu kayıtta özet metni alınamadı.";
        if (d.tldr) absEl.insertAdjacentHTML("beforebegin", `<div class="prov"><b>TL;DR (Semantic Scholar):</b> ${esc(d.tldr)}</div>`);
        if (d.s2_citations != null) metaEl.insertAdjacentHTML("beforeend", `<div class="prov">Semantic Scholar atıf: ${esc(d.s2_citations)}</div>`);
        absEl.insertAdjacentHTML("beforeend", `<div class="prov" style="margin-top:6px">${esc(d.source_note)}</div>`);
        linksEl.innerHTML = [safeUrl(d.final_url) && `<a class="chip alt" href="${safeUrl(d.final_url)}" target="_blank" rel="noopener">${esc(d.source_label || "Kaynağa git")} ↗</a>`,
          safeUrl(d.pdf) && `<a class="chip alt" href="${safeUrl(d.pdf)}" target="_blank" rel="noopener">PDF ↗</a>`].filter(Boolean).join("");
      }
      if (m.delta) { text += m.delta; sumEl.innerHTML = formatAnswer(text); sumEl.classList.remove("typing"); }
      if (m.error) failure = m.error;
      if (m.done) completed = true;
    };
    while (!completed) {
      const { value, done } = await reader.read();
      if (done) { buf += dec.decode(); if (buf.trim()) event(buf); break; }
      buf += dec.decode(value, { stream: true });
      const parts = buf.split(/\r?\n\r?\n/); buf = parts.pop();
      for (const part of parts) event(part);
    }
    if (failure) throw new Error(failure);
    if (!completed) throw new Error("Yayın ayrıntısı tamamlanmadan bağlantı kesildi.");
    if (!text) sumEl.textContent = "Özet metni alınamadı.";
  } catch (error) {
    if (error.name === "AbortError" && !timedOut) return;
    if (!text) sumEl.textContent = "Yayın ayrıntısı tamamlanamadı.";
    stages.insertAdjacentHTML("beforeend", `<div class="warning">${esc(timedOut ? "Yayın ayrıntısı bekleme süresi doldu." : error.message)}</div>`);
  } finally {
    clearTimeout(deadline);
    if (reader) { await reader.cancel().catch(() => {}); reader.releaseLock(); }
    sumEl.classList.remove("typing");
    if (paperRequest === controller) paperRequest = null;
  }
}

function closeModal() {
  paperRequest?.abort();
  paperRequest = null;
  $("#modal").hidden = true;
}

document.addEventListener("click", (e) => {
  const pp = e.target.closest("[data-paper]");
  if (pp) { e.preventDefault(); openPaper(pp.dataset.paper); return; }
  if (e.target.id === "modal" || e.target.id === "modalClose") { closeModal(); return; }
  const pub = e.target.closest("[data-pub]");
  if (pub) {
    e.preventDefault();
    const row = document.getElementById(`pub-${pub.dataset.pub}`);
    if (row) { row.scrollIntoView({ behavior: "smooth", block: "center" }); row.classList.add("flash"); setTimeout(() => row.classList.remove("flash"), 1600); }
  }
  const sug = e.target.closest(".suggest button");
  if (sug) ask(sug.dataset.q);
  const del = e.target.closest("[data-del]");
  if (del) { e.stopPropagation(); deleteChat(del.dataset.del); return; }
  const item = e.target.closest("[data-chat]");
  if (item) openChat(item.dataset.chat);
});
document.addEventListener("input", (e) => {
  if (e.target.id !== "pubFilter") return;
  const q = e.target.value.toLowerCase();
  document.querySelectorAll("#pubs tr").forEach((tr) => (tr.style.display = tr.dataset.q.includes(q) ? "" : "none"));
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });
$("#form").addEventListener("submit", (e) => { e.preventDefault(); start(); });
$("#newChat").addEventListener("click", () => { resetThread(); loadChats(); $("#name").focus(); });
$("#clearAll").addEventListener("click", async () => {
  if (!confirm("Tüm sohbet geçmişi ve profil sonuçları silinsin mi?")) return;
  await fetch("/api/chats", { method: "DELETE" }); resetThread(); loadChats();
});
$("#scan").addEventListener("click", async () => {
  addMsg("user", "Bilinen sitelerde değişiklik taraması yap.");
  const b = addMsg("bot", `<div class="answer typing">Scrapling ile bilinen sayfalar yoklanıyor; yapı değişen olursa REA yeniden öğrenecek…</div>`);
  const rows = await (await fetch("/api/recipes/check", { method: "POST" })).json();
  if (!rows.length) { b.innerHTML = "Henüz öğrenilmiş site yok. Önce bir profil çıkar."; return; }
  b.innerHTML = `<b>Değişiklik taraması</b><table><thead><tr><th>Sayfa</th><th>Benzerlik</th><th>Durum</th></tr></thead><tbody>${rows.map((r) =>
    `<tr><td>${esc(r.url)}</td><td>${r.similarity != null ? Math.round(r.similarity * 100) + "%" : "—"}</td><td>${r.error ? "⚠ " + esc(r.error) : r.drift ? `<span class="vb conflict">DEĞİŞMİŞ${r.relearned ? " · REA yeniden öğrendi" : ""}</span>` : `<span class="vb ok">✓ değişmemiş</span>`}</td></tr>`).join("")}</tbody></table>`;
});
$("#recipes").addEventListener("click", async () => {
  const rows = await (await fetch("/api/recipes")).json();
  addMsg("user", "Öğrenilen site tariflerini göster.");
  addMsg("bot", rows.length ? rows.map((st) => `<div class="card"><h3>${esc(st.domain)}</h3>
    ${Object.entries(st.replay).map(([k, r]) => `<div class="recon"><b>${esc(k)}</b>: ${esc(r.method)} ${esc(r.url)} · öğrenildi ${esc(r.learned_at)} · ${r.hits} başarılı tekrar · ${r.failures} kırılma</div>`).join("") || '<div class="prov">Tekrar oynatılabilir istek yok (sunucu-HTML site).</div>'}
    <div class="recon">${st.pages.length} sayfa parmak izi · ${Object.keys(st.people).length} kişi hafızada</div>
    <div class="recon">${st.events.slice(-8).map((e) => `<div class="${e.kind.includes("drift") || e.kind.includes("fail") ? "ev-drift" : ""}">${esc(e.at)} · ${esc(e.kind)} · ${esc(e.detail)}</div>`).join("")}</div></div>`).join("")
    : "Henüz öğrenilmiş site tarifi yok.", true);
});
$("#ask").addEventListener("submit", (e) => { e.preventDefault(); if (chatRequest) return; const q = $("#question").value.trim(); $("#question").value = ""; ask(q); });
loadEnv();
loadChats();
{ const cid = new URLSearchParams(location.search).get("chat"); if (cid) openChat(cid); }
