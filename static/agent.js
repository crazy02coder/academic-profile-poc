// Akademik İz Agent — Chrome eklentisinin yan panelinde çalışan sohbet botu.
// Tarayıcı yetenekleri (sekme içeriği, gezinme, vurgulama, ağ kaydı) eklenti kabuğundan postMessage ile gelir.
const $ = (s, r = document) => r.querySelector(s);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const thread = $("#thread");
const IN_EXTENSION = window.parent !== window;

const state = { page: null, info: null, job: null, learning: false, history: [], lastPerson: "" };

// ------------------------------------------------------------------ eklenti köprüsü
const pending = new Map();
let seq = 0;
function ext(type, payload) {
  return new Promise((resolve, reject) => {
    if (!IN_EXTENSION) { reject(new Error("Bu ekran Chrome eklentisinin yan panelinde çalışır.")); return; }
    const id = ++seq;
    pending.set(id, { resolve, reject });
    window.parent.postMessage({ __aiz: true, id, type, payload }, "*");
    setTimeout(() => { if (pending.has(id)) { pending.delete(id); reject(new Error("Eklenti yanıt vermedi.")); } }, 90000);
  });
}
let tabTimer = null;
window.addEventListener("message", (e) => {
  const d = e.data;
  if (!d || !d.__aiz) return;
  if (d.event === "tab_changed") {
    clearTimeout(tabTimer);
    tabTimer = setTimeout(() => { if (!state.learning) understandPage(); }, 700);
    return;
  }
  const p = pending.get(d.id);
  if (p) { pending.delete(d.id); d.ok ? p.resolve(d.data) : p.reject(new Error(d.error)); }
});

// ----------------------------------------------------------------------- yardımcılar
function addMsg(role, html) {
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  el.innerHTML = `<div class="avatar">${role === "bot" ? "◈" : "●"}</div><div class="bubble">${html}</div>`;
  thread.appendChild(el);
  thread.scrollTop = thread.scrollHeight;
  return $(".bubble", el);
}
function fmt(text) {
  return esc(text).replace(/\[(P\d+)\]/g, (_, id) => `<span class="cite" data-paper="${id}">${id}</span>`)
    .replace(/\[([SD]\d+)\]/g, '<span class="cite">$1</span>').replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/\n/g, "<br>");
}
async function sse(url, body, onEvent) {
  const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const reader = res.body.getReader(); const dec = new TextDecoder(); let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split("\n\n"); buf = parts.pop();
    for (const part of parts) if (part.startsWith("data: ")) onEvent(JSON.parse(part.slice(6)));
  }
}
function stageBox(bubble) {
  const box = document.createElement("div"); box.className = "now"; bubble.appendChild(box);
  return (msg) => { box.textContent = msg; thread.scrollTop = thread.scrollHeight; };
}
function setPill() {
  const pill = $("#pill");
  if (state.job?.result) {
    const p = state.job.result.profile;
    pill.hidden = false;
    pill.innerHTML = `<span>Sohbet bağlamı: <b>${esc(p.name)}</b> · ${state.job.result.unique_count} yayın</span><button id="dropCtx" title="Sayfa moduna dön">×</button>`;
  } else { pill.hidden = true; pill.innerHTML = ""; }
}

// --------------------------------------------------------------------- sayfayı anla
async function understandPage() {
  let snap;
  try { snap = await ext("snapshot"); }
  catch (err) { addMsg("bot", `Bu sekmeyi okuyamıyorum (${esc(err.message)}). Normal bir web sayfasına geç.`); return; }
  if (state.page && state.page.url === snap.url && state.info) return;
  state.page = snap;
  const res = await fetch("/api/page/understand", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: snap.url, html: snap.html }) });
  const info = await res.json(); state.info = info;
  const host = new URL(snap.url).hostname;
  let html = `<b>${esc(info.title || host)}</b><br><span class="prov">${esc(host)}${info.institution ? " · " + esc(info.institution) : ""}</span><br>`;
  if (info.page_type === "staff_list") {
    html += `Bu sayfada <b>${info.people.length} akademisyen</b> var${info.pagination ? ` (ve ${info.pagination} sayfa daha)` : ""}. Kimin akademik profilini çıkarayım?
      <div class="people"><input id="pf" placeholder="İsim süz…">${info.people.map((p) => `<button data-person="${esc(p.name)}" title="${esc(p.title)}">${esc(p.name)}</button>`).join("")}</div>`;
  } else if (info.page_type === "person_profile") {
    const p = info.people[0];
    html += `Bu sayfa <b>${esc(p.title)} ${esc(p.name)}</b> kişisine ait görünüyor.
      <div class="acts"><button class="primary" data-person="${esc(p.name)}">Akademik profilini çıkar</button></div>`;
  } else if (info.page_type === "listing") {
    html += `Sayfada <b>${info.items} tekrar eden öğe</b> var (örn. ${esc(info.item_preview.slice(0, 2).join(", "))}). Tabloya çıkarabilirim.`;
  } else {
    html += `Bu sayfada akademik kadro görmedim.`;
    if (info.suggestions.length) html += ` Kadro/fakülte sayfası olabilecek yerler:<div class="acts">${info.suggestions.map((s) =>
      `<button data-go="${esc(s.url)}">${esc(s.text)}</button>`).join("")}</div>`;
  }
  html += `<div class="acts">
    <button data-act="summary">Sayfayı özetle</button><button data-act="find">Sitede bul…</button>
    <button data-act="extract">Tabloya çıkar</button><button data-act="atlas">Sitenin anlam haritası</button>
    <button data-act="apis">Gizli API'ler (REA)</button></div>`;
  addMsg("bot", html);
}

// -------------------------------------------------------------- akademik profil (iş hattı)
const PHASES = [["reverse", "Site yapısı çözümleniyor (tersine mühendislik)"], ["scrape", "Site sayfa sayfa taranıyor"],
  ["bot", "Bot koruması aşılıyor"], ["collect", "Akademik kaynaklardan yayınlar toplanıyor"],
  ["merge", "Veriler birleştiriliyor ve doğrulanıyor"], ["ai", "Yapay zekâ modeli hazırlanıyor"]];
function phaseOf(ev) {
  if (/duvar|stealth|cloudflare|turnstile|bot koruma|418|403|429/i.test(ev.message)) return "bot";
  return { rea: "reverse", scrape: "scrape", crawl: "scrape", yok: "collect", publications: "collect",
           dedup: "merge", verify: "merge", analysis: "ai" }[ev.step] || "scrape";
}
async function startProfile(name) {
  state.lastPerson = name;
  addMsg("user", `${esc(name)} — akademik profil`);
  const snap = state.page || await ext("snapshot");
  const res = await fetch("/api/jobs", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: snap.url, name, html: snap.html }) });
  if (!res.ok) { addMsg("bot", "İş başlatılamadı."); return; }
  const job = await res.json();
  const bubble = addMsg("bot", `<div class="steps small">${PHASES.map(([k, l]) =>
    `<div class="step" data-phase="${k}" ${k === "bot" ? "hidden" : ""}><span class="dot"></span>${esc(l)}</div>`).join("")}</div>`);
  const now = stageBox(bubble);
  const es = new EventSource(`/api/jobs/${job.id}/events`);
  es.onmessage = (e) => {
    const ev = JSON.parse(e.data);
    if (ev.type === "log") {
      const ph = phaseOf(ev); const order = PHASES.map(([k]) => k);
      const st = $(`.step[data-phase="${ph}"]`, bubble);
      if (st) {
        st.hidden = false;
        bubble.querySelectorAll(".step.running").forEach((x) => {
          if (x !== st && (order.indexOf(x.dataset.phase) < order.indexOf(ph) || x.dataset.phase === "bot")) { x.className = "step done"; $(".dot", x).textContent = "✓"; }
        });
        st.className = "step running";
      }
      now(ev.message.length > 110 ? ev.message.slice(0, 110) + "…" : ev.message);
    } else if (ev.type === "result") {
      bubble.querySelectorAll(".step:not([hidden])").forEach((x) => { x.className = "step done"; $(".dot", x).textContent = "✓"; });
      now("");
      state.job = { jid: job.id, chatId: ev.data.chat_id, result: ev.data };
      setPill(); renderProfile(ev.data);
    } else if (ev.type === "error") { now(ev.message); }
    else if (ev.type === "end") es.close();
  };
}
function renderProfile(r) {
  const p = r.profile, a = r.analysis;
  const vb = (k) => { const v = p.verification?.[k]; return v ? ` <span class="vb ${v.status === "doğrulandı" ? "ok" : "single"}">${v.status === "doğrulandı" ? "✓" : "·"}</span>` : ""; };
  addMsg("bot", `<div class="prof"><div class="done-banner" style="padding:10px 12px"><div class="big" style="font-size:18px">✓ Tamamlandı</div>
      <div style="font-size:12.5px">${esc(r.summary)}</div></div>
    <h2 style="margin-top:10px">${esc(p.name)}</h2><p>${esc(p.title || "")}${vb("title")}</p><p>${esc(p.department || "")}${vb("department")}</p>
    <p>${esc(p.institution || "")}${vb("institution")}</p>
    <div class="chips" style="margin:8px 0">${a.areas.map((x) => `<span class="chip">${esc(x.label)}</span>`).join("")}</div>
    ${a.summary ? `<div style="font-size:12.5px">${esc(a.summary)}</div>` : ""}
    <h3 class="m-h">Son yayınlar</h3>${r.publications.slice(0, 8).map((x) =>
      `<div class="pub-li" data-paper="${esc(x.id)}">${esc(x.title)} <small>· ${esc(x.year || "")} · ${esc(x.citations ?? 0)} atıf</small></div>`).join("")}
    <div class="acts"><button data-act="report">Tam raporu ana pencerede aç</button>
      <button data-q="En çok atıf alan yayınları hangileri?">En çok atıf?</button>
      <button data-q="Son yıllarda hangi konulara yöneldi?">Son yönelimi?</button></div></div>`);
  $("#question").placeholder = `${p.name} hakkında sor…`;
}

// ------------------------------------------------------------------------- soru-cevap
async function ask(question, deep = false, scope = "site") {
  addMsg("user", esc(question));
  const bubble = addMsg("bot", `<div class="answer typing"></div>`);
  const out = $(".answer", bubble); let text = ""; let meta = null;
  if (state.job?.result) {
    await sse(`/api/jobs/${state.job.jid}/chat`, { question, chat_id: state.job.chatId, mode: "auto" }, (m) => {
      if (m.chat_id) state.job.chatId = m.chat_id;
      if (m.delta) { text += m.delta; out.innerHTML = fmt(text); thread.scrollTop = thread.scrollHeight; }
      if (m.done) meta = m.meta;
    });
    if (meta) out.insertAdjacentHTML("afterend", `<div class="meta"><b>${esc({ cag: "CAG", rag: "RAG", hybrid: "Hibrit" }[meta.mode] || meta.mode)}</b> · ${esc(meta.route || "")}</div>`);
  } else {
    const snap = state.page || await ext("snapshot");
    const st = stageBox(bubble);
    let person = "", suggestFind = "";
    await sse("/api/page/ask", { url: snap.url, html: snap.html, question, history: state.history, deep, scope }, (m) => {
      if (m.stage) st(m.stage);
      if (m.meta) meta = m.meta;
      if (m.person) person = m.person;
      if (m.suggest_find) suggestFind = m.suggest_find;
      if (m.delta) { st(""); text += m.delta; out.innerHTML = fmt(text); thread.scrollTop = thread.scrollHeight; }
      if (m.error) st(m.error);
    });
    if (meta) {
      const cited = new Set([...text.matchAll(/\[([SD]\d+)\]/g)].map((x) => x[1]));
      const srcs = (meta.sources || []).filter((x) => cited.has(x.id));
      const uniq = [...new Map(srcs.map((x) => [x.url, x])).values()];
      const label = { cag: "CAG", rag: "RAG", lookup: "Kişi araması", live: "Site asistanı" }[meta.mode] || meta.mode;
      const how = meta.mode === "live" ? (meta.found ? `kaynak: ${esc((meta.path || []).join(" → "))}` : "bulunamadı") : `${meta.pages} sayfa, ${meta.chunks} parça${esc(meta.detail || "")}`;
      out.insertAdjacentHTML("afterend", `<div class="meta"><b>${label}</b> · ${how}</div>
        ${uniq.length ? `<div class="acts">${uniq.map((x) => `<button data-go="${esc(x.url)}">↗ ${esc(x.page)}</button>`).join("")}</div>` : ""}
        <div class="acts">${person ? `<button class="primary" data-person="${esc(person)}">${esc(person)} — akademik profilini çıkar</button>` : ""}

        </div>`);
    }
    state.history.push({ role: "user", content: question }, { role: "assistant", content: text });
  }
  out.classList.remove("typing");
}

// ----------------------------------------------------------------------------- bul
async function find(query) {
  addMsg("user", `Bul: ${esc(query)}`);
  const bubble = addMsg("bot", "Siteyi tarıyorum…"); const st = stageBox(bubble);
  const snap = state.page || await ext("snapshot");
  let result = null;
  await sse("/api/page/find", { url: snap.url, html: snap.html, query }, (m) => { if (m.stage) st(m.stage); if ("result" in m) result = m.result; if (m.error) st(m.error); });
  st("");
  if (!result) { bubble.innerHTML = `"${esc(query)}" için sitede bir sayfa bulamadım. Farklı kelimelerle dener misin?`; return; }
  bubble.innerHTML = `Buldum${result.pages ? ` (${result.pages} sayfa tarandı)` : ""}: <b>${esc(result.title)}</b><br><span class="prov">${esc(result.url)}</span>
    <div class="acts"><button class="primary" data-go="${esc(result.url)}" data-hl="${esc(result.person ? result.person.split(" ").slice(-1)[0] : query)}">Oraya götür</button>
    ${result.person ? `<button data-person="${esc(result.person)}">${esc(result.person)} — akademik profilini çıkar</button>` : ""}</div>`;
}

// ---------------------------------------------------------------------- veri çıkar
async function extract() {
  addMsg("user", "Sayfadaki listeyi tabloya çıkar");
  const bubble = addMsg("bot", "Tekrar eden öğeler aranıyor…"); const st = stageBox(bubble);
  const snap = state.page || await ext("snapshot");
  let result = null;
  await sse("/api/page/extract", { url: snap.url, html: snap.html }, (m) => { if (m.stage) st(m.stage); if ("result" in m) result = m.result; });
  st("");
  if (!result || !result.rows.length) { bubble.innerHTML = "Bu sayfada tablo olarak çıkarılabilecek tekrar eden bir yapı bulamadım."; return; }
  const cols = Object.keys(result.rows[0]).filter((c) => c !== "metin");
  const csv = [cols.concat("metin").join(",")].concat(result.rows.map((r) => cols.concat("metin").map((c) => `"${String(r[c] ?? "").replace(/"/g, '""')}"`).join(","))).join("\n");
  const href = URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" }));
  bubble.innerHTML = `<b>${result.rows.length} satır</b> (${result.pages.length} sayfa, Scrapling yapı eşleştirmesi).
    <div style="overflow-x:auto"><table class="mini-table"><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr>
    ${result.rows.slice(0, 8).map((r) => `<tr>${cols.map((c) => `<td>${esc(String(r[c] ?? "").slice(0, 60))}</td>`).join("")}</tr>`).join("")}</table></div>
    <div class="acts"><a class="chip alt" href="${href}" download="tablo.csv">CSV indir ↓</a></div>`;
}

// --------------------------------------------------------------- gizli API'ler (REA)
function apiList(calls) {
  return calls.slice(0, 20).map((c) => `<div class="api-row"><b>${esc(c.method)}</b> ${esc(c.status || "")} ${esc(c.path)} ${c.json ? `<span class="prov">JSON ${esc(c.shape)}</span>` : ""}${c.body ? `<br><span class="prov">gövde: ${esc(c.body)}</span>` : ""}</div>`).join("");
}
async function apis() {
  addMsg("user", "Sitenin gizli API'lerini göster");
  const bubble = addMsg("bot", "REA çalışıyor…"); const st = stageBox(bubble);
  const snap = state.page || await ext("snapshot");
  let result = null;
  await sse("/api/page/apis", { url: snap.url }, (m) => { if (m.stage) st(m.stage); if ("result" in m) result = m.result; });
  st("");
  if (!result?.ok) { bubble.innerHTML = `REA gözlemi tamamlanamadı: ${esc(result?.error || "")}`; return; }
  bubble.innerHTML = `REA <b>${result.requests}</b> isteği kaydetti (kanıt ${esc(result.evidence_id.slice(0, 16))}…). Site içi XHR/fetch ve belge istekleri:
    ${apiList(result.calls.filter((c) => c.same_site)) || '<div class="prov">Site içi API yok; içerik sunucu HTML\'i.</div>'}
    <div class="prov" style="margin-top:6px">Butonların arkasındaki istekleri öğretmek için üstteki <b>● Öğren</b>'e bas, sayfada gezin/tıkla, sonra durdur.</div>`;
}
async function toggleLearn() {
  const btn = $("#learn");
  if (!state.learning) {
    try { await ext("learnStart"); } catch (err) { addMsg("bot", `Öğrenme modu açılamadı: ${esc(err.message)}`); return; }
    state.learning = true; btn.classList.add("on"); btn.textContent = "■ Durdur";
    addMsg("bot", "Öğrenme modu açık. Sayfada normal şekilde gezin, butonlara tıkla; REA ağ trafiğini kaydediyor. Bitince <b>■ Durdur</b>'a bas. (Chrome üstte 'hata ayıklanıyor' şeridi gösterir.)");
    return;
  }
  state.learning = false; btn.classList.remove("on"); btn.textContent = "● Öğren";
  const bubble = addMsg("bot", "Kayıt REA'ya gönderiliyor…"); const st = stageBox(bubble);
  let rec;
  try { rec = await ext("learnStop"); } catch (err) { bubble.textContent = `Kayıt alınamadı: ${err.message}`; return; }
  const lastClick = (rec.clicks || []).slice(-1)[0];
  const snap = state.page || { url: "" };
  let result = null;
  await sse("/api/page/learn", { url: snap.url, har: rec.har, name: state.lastPerson, attrs: lastClick ? lastClick.attrs : {} },
    (m) => { if (m.stage) st(m.stage); if ("result" in m) result = m.result; if (m.error) st(m.error); });
  st("");
  if (!result) return;
  bubble.innerHTML = `REA gerçek tarayıcından gelen <b>${result.requests}</b> isteği çözdü (kanıt ${esc((result.evidence_id || "").slice(0, 16))}…).
    ${result.learned.length ? `<div style="margin-top:6px"><b>Öğrenilen tarifler:</b>${result.learned.map((l) => `<div class="api-row"><b>${esc(l.method)}</b> ${esc(l.url)} <span class="prov">(${esc(l.purpose)})</span></div>`).join("")}</div>
      <div class="prov">Bu sitede bundan sonra bu istekler Scrapling ile tarayıcısız tekrar oynatılacak.</div>` : '<div class="prov">Ad veya kimlik içeren bir istek yakalanmadı; gözlenen API\'ler hafızaya eklendi.</div>'}
    ${apiList(result.calls.filter((c) => c.same_site))}`;
}

// ------------------------------------------------------------------------ anlam haritası
async function showAtlas() {
  addMsg("user", "Sitenin anlam haritasını göster");
  const bubble = addMsg("bot", "Harita hazırlanıyor…"); const st = stageBox(bubble);
  const snap = state.page || await ext("snapshot");
  let r = null;
  await sse("/api/page/atlas", { url: snap.url, html: snap.html }, (m) => { if (m.stage) st(m.stage); if ("result" in m) r = m.result; });
  st("");
  if (!r) { bubble.textContent = "Harita çıkarılamadı."; return; }
  bubble.innerHTML = `<b>${esc(r.root)}</b> — ${r.total} adres anlamına göre gruplandı:` + r.categories.map((c) =>
    `<details class="tech" style="margin-top:6px"><summary><b>${esc(c.name)}</b> · ${c.count}</summary>${c.examples.map((e) =>
      `<div class="api-row"><a href="#" data-go="${esc(e.u)}">${esc(e.t || e.u)}</a></div>`).join("")}</details>`).join("") +
    `<div class="prov" style="margin-top:6px">Sorularında bot önce bu haritaya bakar; örn. "Bilgisayar mühendisliği ders programı nerede?"</div>`;
}

// ------------------------------------------------------------------------ yayın detayı
async function openPaper(pid) {
  const r = state.job?.result; const p = r?.publications.find((x) => x.id === pid);
  if (!p) return;
  $("#modal").hidden = false;
  const body = $("#modalBody");
  body.innerHTML = `<div class="prov">${esc(pid)} · ${esc(p.year || "")}</div><h2 class="m-title">${esc(p.title)}</h2>
    <div id="mSt" class="now"></div><h3 class="m-h">Qwen özeti</h3><div id="mSum" class="answer typing"></div>
    <h3 class="m-h">Özet</h3><div id="mAbs" class="m-abs prov">…</div><div id="mLinks" class="acts"></div>`;
  let text = "";
  const res = await fetch(`/api/jobs/${state.job.jid}/papers/${pid}`);
  const reader = res.body.getReader(); const dec = new TextDecoder(); let buf = "";
  for (;;) {
    const { value, done } = await reader.read(); if (done) break;
    buf += dec.decode(value, { stream: true }); const parts = buf.split("\n\n"); buf = parts.pop();
    for (const part of parts) {
      if (!part.startsWith("data: ")) continue;
      const m = JSON.parse(part.slice(6));
      if (m.stage) $("#mSt").textContent = m.stage;
      if (m.meta) { $("#mAbs").textContent = m.meta.abstract || "Özet bulunamadı."; $("#mLinks").innerHTML = m.meta.final_url ? `<button data-go="${esc(m.meta.final_url)}">Sekmede aç</button>` : ""; }
      if (m.delta) { text += m.delta; $("#mSum").innerHTML = fmt(text); }
    }
  }
  $("#mSt").textContent = ""; $("#mSum").classList.remove("typing");
}

// -------------------------------------------------------------------------- niyet
async function route(text) {
  const t = text.toLocaleLowerCase("tr");
  const m = t.match(/^(?:bul|ara|nerede|git)\s*[:\-]?\s*(.+)$/) || t.match(/^(.+?)\s+(?:nerede|sayfasını bul|sayfası nerede|'?[iıuü]? bul)\??$/);
  if (m) return find(m[1].replace(/['’]?[iıuü]?$/, "").trim());
  if (/tablo|csv|listeyi çıkar|veriyi çıkar/.test(t)) return extract();
  if (/api|istek|tersine|network|ağ trafi/.test(t)) return apis();
  const prof = t.match(/^(.+?)\s+(?:için\s+)?(?:akademik\s+)?profil/);
  if (prof && !state.job) return startProfile(text.slice(0, prof[1].length).trim());
  return ask(text);
}

// ------------------------------------------------------------------------- olaylar
document.addEventListener("click", async (e) => {
  const t = e.target.closest("button, a, .pub-li, .cite");
  if (!t) return;
  if (t.id === "dropCtx") { state.job = null; setPill(); $("#question").placeholder = "Bir şey sor ya da 'X'i bul' de…"; addMsg("bot", "Sayfa moduna döndüm."); return; }
  if (t.id === "modalClose") { $("#modal").hidden = true; return; }
  if (t.id === "learn") return toggleLearn();
  if (t.id === "refresh") { state.info = null; state.page = null; return understandPage(); }
  if (t.dataset.person) return startProfile(t.dataset.person);
  if (t.dataset.paper) return openPaper(t.dataset.paper);
  if (t.dataset.go) {
    e.preventDefault();
    await ext("navigate", { url: t.dataset.go });
    if (t.dataset.hl) await ext("highlight", { text: t.dataset.hl }).catch(() => {});
    state.page = null; state.info = null; return understandPage();
  }
  if (t.dataset.q) return ask(t.dataset.q);
  if (t.dataset.deep) return ask(t.dataset.deep, true);
  if (t.dataset.findq) return find(t.dataset.findq);
  const act = t.dataset.act;
  if (act === "summary") return ask("Bu sayfayı kısaca özetle.", false, "page");
  if (act === "find") { $("#question").value = "bul: "; $("#question").focus(); return; }
  if (act === "extract") return extract();
  if (act === "apis") return apis();
  if (act === "atlas") return showAtlas();
  if (act === "report") return window.open(`/?chat=${state.job.chatId}`, "_blank");
});
document.addEventListener("input", (e) => {
  if (e.target.id !== "pf") return;
  const q = e.target.value.toLocaleLowerCase("tr");
  e.target.parentElement.querySelectorAll("button").forEach((b) => (b.style.display = b.textContent.toLocaleLowerCase("tr").includes(q) ? "" : "none"));
});
$("#ask").addEventListener("submit", (e) => { e.preventDefault(); const q = $("#question").value.trim(); $("#question").value = ""; if (q) route(q); });
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") $("#modal").hidden = true; });

if (IN_EXTENSION) {
  addMsg("bot", "Merhaba! Açık olan sayfaya bakıyorum…");
  understandPage();
} else {
  thread.innerHTML = `<div class="notice">Bu ekran <b>Akademik İz Agent</b> Chrome eklentisinin yan panelinde çalışır.<br>
    Ana penceredeki <b>Agent</b> bölümünden eklentiyi indirip kurabilirsin.</div>`;
}
