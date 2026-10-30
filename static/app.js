// Akademik İz — kurumsal arayüz (bağımlılıksız). Görünümler hash yönlendirmesiyle açılır:
//   #/                      Keşfet (üniversite linki + isteğe bağlı akademisyen adı)
//   #/kurum?u=<url>         Fakülte → bölüm → akademisyen dizini
//   #/profil/<sohbet-id>    Akademisyen profili (YÖK + yayınlar + asistan)
//   #/is/<iş-id>            Profil çıkarılırken canlı ilerleme
//   #/ara?q=<konu>          Konu araması
//   #/favori-makaleler, #/favori-akademisyenler, #/universiteler, #/firmalar, #/firma/<id>
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const safeUrl = (u) => { if (!u || typeof u !== "string") return ""; try { const x = new URL(u, location.href); return ["http:", "https:"].includes(x.protocol) ? x.href : ""; } catch { return ""; } };
const safeImg = (u) => (/^data:image\/(png|jpe?g|gif|webp);base64,[A-Za-z0-9+/=]+$/.test(u || "") ? u : safeUrl(u));
const fold = (s) => String(s || "").toLocaleLowerCase("tr").replace(/ı/g, "i").normalize("NFKD").replace(/[̀-ͯ]/g, "")
  .replace(/[^a-z0-9]+/g, " ").trim();
const normDoi = (d) => String(d || "").toLowerCase().replace(/^https?:\/\/(dx\.)?doi\.org\//, "").trim();
const initials = (n) => (n || "?").replace(/(prof|doç|doc|dr|öğr|ogr|üyesi|gör|arş)\.?/gi, "").split(/\s+/).filter(Boolean).slice(0, 2).map((x) => x[0]).join("").toLocaleUpperCase("tr");
const fmtNum = (n) => (n == null ? "—" : Number(n).toLocaleString("tr-TR"));

// ------------------------------------------------------------------- simgeler
const ICONS = {
  compass: '<circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/>',
  search: '<circle cx="11" cy="11" r="7.5"/><line x1="21" y1="21" x2="16.6" y2="16.6"/>',
  building: '<path d="M3 21h18"/><path d="M5 21V10l7-5 7 5v11"/><path d="M9 21v-6h6v6"/><path d="M9 11h.01M15 11h.01"/>',
  bookmark: '<path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>',
  users: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
  user: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
  star: '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>',
  plus: '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
  x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
  chevron: '<polyline points="9 18 15 12 9 6"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
  mail: '<rect x="2" y="4" width="20" height="16" rx="2"/><polyline points="22 6 12 13 2 6"/>',
  external: '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>',
  globe: '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
  layers: '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/>',
  refresh: '<polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>',
  message: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
  send: '<line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>',
  trash: '<polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
  menu: '<line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
  info: '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>',
  sparkle: '<path d="M12 3l1.9 5.8L20 11l-6.1 2.2L12 19l-1.9-5.8L4 11l6.1-2.2z"/>',
  clock: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
  book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>',
  award: '<circle cx="12" cy="8" r="7"/><polyline points="8.21 13.89 7 23 12 20 17 23 15.79 13.88"/>',
  briefcase: '<rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>',
  cap: '<path d="M22 10 12 5 2 10l10 5 10-5z"/><path d="M6 12v5c3 2 9 2 12 0v-5"/>',
};
const icon = (name) => `<i data-icon="${name}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">${ICONS[name] || ""}</svg></i>`;
function hydrateIcons(root = document) {
  $$("i[data-icon]:empty", root).forEach((el) => { el.outerHTML = icon(el.dataset.icon); });
}

// ------------------------------------------------------------------- durum
const S = {
  fav: { papers: [], people: [] }, chats: [],
  result: null, jobId: null, chatId: null, chatRequest: null, paperRequest: null,
  jobs: {},            // iş id → { node, es, name, done }
  dir: null,           // kurum dizini durumu
  registry: new Map(), // ekrandaki yayınlar: id → { paper, source }
  lists: {},           // dışa aktarılabilir listeler
  listMeta: {},        // liste → { file: dosya adı kökü, person, title } (dışa aktarmada akademisyen adı)
};
let regSeq = 0;
function reg(paper, source) { const id = `r${++regSeq}`; S.registry.set(id, { paper, source }); return id; }

const view = () => $("#view");
function setView(html, cls = "") {
  S.registry.clear();
  const v = view();
  v.innerHTML = `<div class="enter ${cls}">${html}</div>`;
  hydrateIcons(v);
  v.scrollTop = 0;
  return v.firstElementChild;
}
function setCrumbs(items) {
  $("#crumbs").innerHTML = items.map((c, i) => (i === items.length - 1 ? `<b>${esc(c.label)}</b>`
    : `<a href="${esc(c.href)}">${esc(c.label)}</a>${icon("chevron")}`)).join("");
}
function setNav(key) {
  $$(".nav a").forEach((a) => a.classList.toggle("active", a.dataset.nav === key));
  $("#app").classList.remove("menu-open");
}

function toast(html, ms = 4200) {
  const el = document.createElement("div");
  el.className = "toast"; el.innerHTML = html;
  $("#toasts").appendChild(el);
  setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 320); }, ms);
}

async function api(url, opts = {}) {
  const res = await fetch(url, { headers: { "Content-Type": "application/json" }, ...opts });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(typeof err.detail === "string" ? err.detail : `İstek başarısız (HTTP ${res.status}).`);
  }
  return res.json();
}
const post = (url, body) => api(url, { method: "POST", body: JSON.stringify(body) });

const skeleton = (n = 5) => Array.from({ length: n }, () => `<div class="skel-row"><div class="skel"></div><div class="skel-lines"><div class="skel"></div><div class="skel"></div></div></div>`).join("");
const emptyState = (ic, title, text, extra = "") => `<div class="empty"><div class="em-icon">${icon(ic)}</div><h3>${esc(title)}</h3><p>${text}</p>${extra}</div>`;
function avatar(name, photo, cls = "av") {
  const img = safeImg(photo);
  return `<div class="${cls}">${img ? `<img src="${esc(img)}" alt="" loading="lazy">` : esc(initials(name))}</div>`;
}

// ------------------------------------------------------------------- ortam, geçmiş, favoriler
async function loadEnv() {
  const el = $("#env");
  try {
    const h = await api("/api/health");
    el.className = `env ${h.llm_ready ? "ok" : "warn"}`;
    el.innerHTML = `<span class="dot"></span><span title="REA ${h.rea ? "hazır" : "yok"} · Chromium ${h.chromium ? "hazır" : "yok"}">${esc(h.llm)}</span>`;
  } catch { el.className = "env warn"; el.innerHTML = `<span class="dot"></span><span>Sunucuya ulaşılamadı</span>`; }
}

async function loadChats() {
  try { S.chats = await api("/api/chats"); } catch { S.chats = []; }
  $("#history").innerHTML = S.chats.length ? S.chats.slice(0, 40).map((c) => `
    <div class="h-item ${c.id === S.chatId ? "active" : ""}" data-chat="${esc(c.id)}" title="${esc(c.name)} · ${esc(c.institution || "")}">
      ${avatar(c.name, (S.fav.people.find((p) => p.chat_id === c.id) || {}).photo)}
      <div class="h-main"><b>${esc(c.name || "?")}</b><span>${esc(c.institution || c.preview || "")}</span></div>
      <button class="h-del" data-delchat="${esc(c.id)}" type="button" aria-label="Sil">${icon("x")}</button></div>`).join("")
    : `<div class="empty-side">Henüz arama yok.</div>`;
}

async function loadFav() {
  try { S.fav = await api("/api/favorites"); } catch { /* sunucu yok */ }
  $("#cntPapers").textContent = S.fav.papers.length || "";
  $("#cntPeople").textContent = S.fav.people.length || "";
}
const favPaper = (p) => S.fav.papers.find((f) => (p.doi && f.doi && normDoi(f.doi) === normDoi(p.doi)) || fold(f.title) === fold(p.title));
const favPerson = (key) => S.fav.people.find((f) => f.key === key);

async function toggleStar(btn) {
  const entry = S.registry.get(btn.dataset.star);
  if (!entry) return;
  const p = entry.paper, hit = favPaper(p);
  btn.classList.add("pop"); setTimeout(() => btn.classList.remove("pop"), 400);
  try {
    if (hit) {
      await api(`/api/favorites/papers/${encodeURIComponent(hit.key)}`, { method: "DELETE" });
      btn.classList.remove("on"); toast("Favorilerden çıkarıldı.");
      if (location.hash.startsWith("#/favori-makaleler")) { btn.closest(".paper")?.remove(); }
    } else {
      const src = entry.source || {};
      await post("/api/favorites/papers", { item: { ...p, sources: p.sources, job_id: src.jid, pid: src.pid, person: src.person } });
      btn.classList.add("on"); toast(`${icon("star")} Favori makalelere eklendi.`);
    }
  } catch (e) { toast(esc(e.message)); }
  await loadFav();
}

// ------------------------------------------------------------------- yayın kartı, dışa aktarma
const TYPE_TR = { article: "Makale", "journal-article": "Makale", proceedings: "Bildiri", "proceedings-article": "Bildiri", book: "Kitap",
  "book-chapter": "Kitap bölümü", dissertation: "Tez", preprint: "Ön baskı", review: "Derleme", dataset: "Veri seti" };
const SRC_TR = { openalex: "OpenAlex", crossref: "Crossref", orcid: "ORCID", yok: "YÖK", scholar: "Scholar", semantic_scholar: "Semantic Scholar",
  trdizin: "TR Dizin", openaire: "OpenAIRE", tez: "Tez Merkezi" };
function paperCard(p, source, i = 0) {
  const id = reg(p, source);
  const authors = (p.authors || []).slice(0, 6).join(", ") + ((p.authors || []).length > 6 ? " vd." : "");
  const srcs = p.sources || (p.source ? [p.source] : []);
  return `<article class="paper" style="--i:${Math.min(i, 20)}">
    <div class="p-body">
      <div class="p-title" data-open="${id}">${esc(p.title)}</div>
      <div class="p-meta">${authors ? `${esc(authors)} · ` : ""}${p.venue ? `<b>${esc(p.venue)}</b> · ` : ""}${esc(p.year || "Yıl yok")}</div>
      ${p.unit_authors?.length ? `<div class="p-meta">Birimdeki yazar: <b>${esc(p.unit_authors.join(", "))}</b></div>` : ""}
      ${p.person ? `<div class="p-meta">Akademisyen: <b>${esc(p.person)}</b></div>` : ""}
      ${p.abstract ? `<div class="p-abs">${esc(p.abstract)}</div>` : ""}
      <div class="p-tags">${p.type ? `<span class="chip">${esc(TYPE_TR[p.type] || p.type)}</span>` : ""}
        ${srcs.map((s) => `<span class="badge ${esc(s)}">${esc(SRC_TR[s] || s)}</span>`).join("")}
        ${p.doi ? `<a class="chip" href="https://doi.org/${esc(normDoi(p.doi))}" target="_blank" rel="noopener">DOI ${icon("external")}</a>` : ""}</div>
    </div>
    <div class="p-side">
      <button class="star ${favPaper(p) ? "on" : ""}" data-star="${id}" type="button" title="Favorilere ekle">${icon("star")}</button>
      ${p.citations != null ? `<div class="cites"><b>${fmtNum(p.citations)}</b> atıf</div>` : ""}
    </div></article>`;
}

function download(name, text, type) {
  const blob = new Blob([text], { type });
  const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: name });
  document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
function exportCsv(list, name, meta = {}) {
  const cols = [["Başlık", (p) => p.title], ["Yazarlar", (p) => (p.authors || []).join("; ")], ["Yıl", (p) => p.year],
    ["Yayın yeri", (p) => p.venue], ["Tür", (p) => TYPE_TR[p.type] || p.type], ["DOI", (p) => normDoi(p.doi)],
    ["Atıf", (p) => p.citations], ["Kaynak", (p) => (p.sources || [p.source]).filter(Boolean).map((s) => SRC_TR[s] || s).join("+")],
    ["Akademisyen", (p) => (p.unit_authors || []).join("; ") || p.person || meta.person || ""]];
  const cell = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const rows = [cols.map(([h]) => cell(h)).join(";"), ...list.map((p) => cols.map(([, f]) => cell(f(p))).join(";"))];
  download(`${name}.csv`, "﻿" + rows.join("\r\n"), "text/csv;charset=utf-8");
}
function exportBib(list, name, meta = {}) {
  const used = new Set();
  const entries = list.map((p) => {
    const last = fold((p.authors || ["anon"])[0]).split(" ").pop() || "anon";
    let key = `${last}${p.year || ""}${fold(p.title).split(" ").find((w) => w.length > 3) || ""}`;
    while (used.has(key)) key += "a";
    used.add(key);
    const kind = /proceed|bildiri/i.test(p.type || "") ? "inproceedings" : /book/i.test(p.type || "") ? "book" : "article";
    const f = { title: p.title, author: (p.authors || []).join(" and "), year: p.year,
      [kind === "inproceedings" ? "booktitle" : "journal"]: p.venue, doi: normDoi(p.doi) };
    return `@${kind}{${key},\n${Object.entries(f).filter(([, v]) => v).map(([k, v]) => `  ${k} = {${String(v).replace(/[{}]/g, "")}}`).join(",\n")}\n}`;
  });
  const head = meta.person ? `% ${[meta.title, meta.person].filter(Boolean).join(" ")}${meta.institution ? " — " + meta.institution : ""}\n` : "";
  const header = `${head}% ${list.length} yayın · Akademik İz · ${new Date().toLocaleDateString("tr-TR")}\n\n`;
  download(`${name}.bib`, header + entries.join("\n\n"), "application/x-bibtex;charset=utf-8");
}
const exportButtons = (listKey) => `<button class="btn sm" data-export="csv" data-list="${listKey}" type="button">${icon("download")}CSV</button>
  <button class="btn sm" data-export="bib" data-list="${listKey}" type="button">${icon("download")}BibTeX</button>`;

// ------------------------------------------------------------------- yayın ayrıntısı (modal)
function openModal(html) {
  $("#modalBody").innerHTML = html; hydrateIcons($("#modalBody"));
  $("#modal").hidden = false;
}
function closeModal() { S.paperRequest?.abort(); S.paperRequest = null; $("#modal").hidden = true; }

function formatAnswer(text) {
  return esc(text).replace(/\[(P\d+)\]/g, (_, id) => `<span class="cite" data-pub="${id}">${id}</span>`)
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/\n/g, "<br>");
}

async function readSse(res, onEvent, signal) {
  const reader = res.body.getReader(); const dec = new TextDecoder(); let buf = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) { buf += dec.decode(); break; }
      buf += dec.decode(value, { stream: true });
      const parts = buf.split(/\r?\n\r?\n/); buf = parts.pop();
      for (const part of parts) {
        const data = part.split(/\r?\n/).filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trimStart()).join("\n");
        if (data && !signal?.aborted && onEvent(JSON.parse(data)) === false) return;
      }
    }
    const tail = buf.split(/\r?\n/).filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trimStart()).join("\n");
    if (tail) onEvent(JSON.parse(tail));
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
}

async function openPaper(regId) {
  const entry = S.registry.get(regId);
  if (!entry) return;
  const p = entry.paper, src = entry.source || {};
  S.paperRequest?.abort();
  const controller = new AbortController(); S.paperRequest = controller;
  const srcs = p.sources || (p.source ? [p.source] : []);
  openModal(`<div class="m-kicker">${srcs.map((s) => `<span class="badge ${esc(s)}">${esc(SRC_TR[s] || s)}</span>`).join("")}
      <span>${esc(p.year || "")}</span>${p.citations != null ? `<span>· ${fmtNum(p.citations)} atıf</span>` : ""}</div>
    <h2 class="m-title">${esc(p.title)}</h2>
    <div id="mMeta" class="muted">${esc(p.venue || "")}</div>
    <div class="m-h">Türkçe özet</div><div id="mSum" class="m-sum typing"></div>
    <div class="m-h">Özet (abstract)</div><div id="mAbs" class="m-abs muted"><div class="loading-line"><span class="spinner"></span>Kaynak okunuyor…</div></div>
    <div id="mLinks" class="chips" style="margin-top:16px"></div>
    <div id="mStages" class="stages"></div>`);
  const sumEl = $("#mSum"), absEl = $("#mAbs"), stages = $("#mStages"), meta = $("#mMeta"), links = $("#mLinks");
  let text = "", failure = "";
  const timer = setTimeout(() => controller.abort(), 210000);
  try {
    const res = src.jid && src.pid
      ? await fetch(`/api/jobs/${src.jid}/papers/${src.pid}`, { signal: controller.signal })
      : await fetch("/api/paper", { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ paper: p }), signal: controller.signal });
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${res.status}`); }
    await readSse(res, (m) => {
      if (S.paperRequest !== controller) return false;
      if (m.stage) stages.insertAdjacentHTML("beforeend", `<div>› ${esc(m.stage)}</div>`);
      if (m.meta) {
        const d = m.meta;
        meta.innerHTML = `${esc(d.journal || "")}${d.date ? " · " + esc(d.date) : ""}<br><span class="faint">${esc((d.authors || []).slice(0, 14).join(", "))}</span>
          ${d.keywords?.length ? `<div class="chips" style="margin-top:10px">${d.keywords.map((k) => `<span class="chip">${esc(k)}</span>`).join("")}</div>` : ""}
          ${Object.entries(d.bibliography || {}).map(([k, v]) => `<div class="faint"><b>${esc(k)}:</b> ${esc(v)}</div>`).join("")}`;
        absEl.innerHTML = `${d.tldr ? `<div class="notice" style="margin-bottom:10px">${icon("sparkle")}<div><b>TL;DR:</b> ${esc(d.tldr)}</div></div>` : ""}${esc(d.abstract || "Bu kayıtta özet metni alınamadı.")}
          <div class="faint" style="margin-top:8px">${esc(d.source_note || "")}</div>`;
        links.innerHTML = [safeUrl(d.final_url) && `<a class="btn sm" href="${esc(safeUrl(d.final_url))}" target="_blank" rel="noopener">${icon("external")}${esc(d.source_label || "Kaynağa git")}</a>`,
          safeUrl(d.pdf) && `<a class="btn sm" href="${esc(safeUrl(d.pdf))}" target="_blank" rel="noopener">${icon("file")}PDF</a>`].filter(Boolean).join("");
        hydrateIcons($("#modalBody"));
      }
      if (m.delta) { text += m.delta; sumEl.innerHTML = formatAnswer(text); }
      if (m.error) failure = m.error;
      return m.done ? false : undefined;
    }, controller.signal);
    if (failure) throw new Error(failure);
    if (!text) sumEl.textContent = "Özet metni bulunamadığı için Türkçe özet üretilmedi.";
  } catch (e) {
    if (e.name === "AbortError" && S.paperRequest !== controller) return;
    if (!text) sumEl.textContent = "Yayın ayrıntısı tamamlanamadı.";
    stages.insertAdjacentHTML("beforeend", `<div style="color:var(--warn)">${esc(e.name === "AbortError" ? "Bekleme süresi doldu." : e.message)}</div>`);
  } finally {
    clearTimeout(timer); sumEl.classList.remove("typing");
    if (S.paperRequest === controller) S.paperRequest = null;
  }
}

// =================================================================== KEŞFET
function viewHome() {
  setCrumbs([{ label: "Keşfet" }]);
  const recentUnis = [];
  const people = S.chats.slice(0, 6);
  setView(`
    <section class="hero">
      <div class="hero-inner">
        <span class="eyebrow">${icon("sparkle")} Kurum ve akademisyen keşfi</span>
        <h1>Bir üniversitenin akademik kadrosunu<br>dakikalar içinde keşfedin.</h1>
        <p class="lead">Üniversite bağlantısını girin: fakülteler, bölümler ve akademisyenler önünüze gelsin. Bir isim de yazarsanız doğrudan
          o akademisyenin YÖK profili, yayınları ve yapay zekâ analizi hazırlanır.</p>
      </div>
      <form class="discover-form" id="discoverForm" autocomplete="off">
        <div class="field"><label for="dUrl">Üniversite bağlantısı</label>
          <div class="input">${icon("globe")}<input id="dUrl" type="url" required placeholder="https://www.ankarabilim.edu.tr"></div></div>
        <div class="field"><label for="dName">Akademisyen adı <small>(isteğe bağlı)</small></label>
          <div class="input">${icon("user")}<input id="dName" placeholder="Ad Soyad"></div></div>
        <button class="btn primary" type="submit">${icon("compass")}Keşfet</button>
      </form>
      <div class="form-hint">
        <span>${icon("layers")} Fakülte → bölüm → akademisyen</span>
        <span>${icon("file")} Bölüm ve fakülte yayın listeleri</span>
        <span>${icon("cap")} YÖK profili, dersler, tezler, iş birlikleri</span>
      </div>
    </section>

    <form class="card quick-search" id="quickSearch">
      <span class="label">veya konu arayın</span>
      <div class="input">${icon("search")}<input id="qsInput" placeholder="ör. göğüs hastalıkları, derin öğrenme, uzaktan eğitim"></div>
      <button class="btn" type="submit">Ara</button>
    </form>

    <div class="home-cols">
      <div class="card list-card">
        <div class="lc-head"><h3>Son incelenen akademisyenler</h3><a href="#/favori-akademisyenler" class="faint">Favoriler →</a></div>
        <div class="stagger">${people.length ? people.map((c, i) => `<div class="person-row" style="--i:${i}" data-chat="${esc(c.id)}">
            ${avatar(c.name, (S.fav.people.find((p) => p.chat_id === c.id) || {}).photo)}
            <div class="pr-main"><b>${esc(c.name)}</b><span>${esc(c.title || "")} ${c.institution ? "· " + esc(c.institution) : ""}</span></div>
            <span class="chip">${fmtNum(c.papers)} yayın</span></div>`).join("")
          : `<div class="empty-side" style="padding:14px">Henüz bir akademisyen incelenmedi.</div>`}</div>
      </div>
      <div class="card list-card" id="homeUnis">
        <div class="lc-head"><h3>Keşfedilen üniversiteler</h3><a href="#/universiteler" class="faint">Tümü →</a></div>
        <div>${skeleton(3)}</div>
      </div>
    </div>

    <div class="grid-3" style="margin-top:18px">
      <div class="card feature"><div class="fi">${icon("layers")}</div><div><h4>Kurum dizini</h4><p>Sitenin menüsünden fakülte ve bölümleri Gemini seçer, Scrapling okur; her bağlantı sayfada doğrulanır.</p></div></div>
      <div class="card feature"><div class="fi">${icon("sparkle")}</div><div><h4>Kendini onaran erişim</h4><p>REA sitenin gizli isteklerini öğrenir; site değişince yeniden öğrenip veriyi yine getirir.</p></div></div>
      <div class="card feature"><div class="fi">${icon("book")}</div><div><h4>Birleştirilmiş yayınlar</h4><p>YÖK, TR Dizin, DergiPark, Tez Merkezi, OpenAlex, Crossref, ORCID ve Scholar tek listede; TR↔EN aynı çalışmalar birleşir.</p></div></div>
    </div>`);
  void recentUnis;
  $("#discoverForm").addEventListener("submit", (e) => {
    e.preventDefault();
    const url = $("#dUrl").value.trim(), name = $("#dName").value.trim();
    if (!safeUrl(url)) { toast("Geçerli bir bağlantı girin (https://…)."); return; }
    if (name) startJob(url, name);
    else location.hash = `#/kurum?u=${encodeURIComponent(url)}`;
  });
  $("#quickSearch").addEventListener("submit", (e) => {
    e.preventDefault();
    const q = $("#qsInput").value.trim();
    if (q) location.hash = `#/ara?q=${encodeURIComponent(q)}`;
  });
  api("/api/universities").then((u) => {
    const box = $("#homeUnis > div:last-child");
    if (!box) return;
    box.innerHTML = u.directory.length ? `<div class="stagger">${u.directory.slice(0, 6).map((x, i) => `
      <div class="person-row" style="--i:${i}" data-org="${esc(x.home || "https://" + x.domain)}">
        <div class="av" style="background:linear-gradient(140deg,#1e3a8a,#0f766e)">${icon("building")}</div>
        <div class="pr-main"><b>${esc(x.name)}</b><span>${esc(x.domain)} · ${x.faculties} fakülte · ${x.people} akademisyen</span></div>
        ${icon("chevron")}</div>`).join("")}</div>`
      : `<div class="empty-side" style="padding:14px">Henüz keşfedilen üniversite yok. Yukarıya bir bağlantı girin.</div>`;
    hydrateIcons(box);
  }).catch(() => {});
}

// =================================================================== YENİ AKADEMİSYEN
function newPersonModal(prefUrl = "", prefName = "") {
  openModal(`<h2>Yeni akademisyen</h2><p class="muted" style="margin:6px 0 0">Kurumun akademik kadro ya da kişi sayfası bağlantısını ve adı girin.
      Profil, yayınlar ve YÖK bilgileri birlikte hazırlanır.</p>
    <form id="npForm" class="form-grid" autocomplete="off">
      <div class="field"><label for="npUrl">Üniversite / kadro bağlantısı</label>
        <div class="input">${icon("globe")}<input id="npUrl" type="url" required placeholder="https://…/akademik-kadro" value="${esc(prefUrl)}"></div></div>
      <div class="field"><label for="npName">Akademisyen adı</label>
        <div class="input">${icon("user")}<input id="npName" required placeholder="Ad Soyad" value="${esc(prefName)}"></div></div>
      <div class="actions" style="justify-content:flex-end"><button type="button" class="btn ghost" data-close>Vazgeç</button>
        <button class="btn primary" type="submit">${icon("sparkle")}Profili hazırla</button></div>
    </form>`);
  $("#npForm").addEventListener("submit", (e) => {
    e.preventDefault();
    const url = $("#npUrl").value.trim(), name = $("#npName").value.trim();
    if (!safeUrl(url) || name.length < 2) { toast("Bağlantı ve ad gerekli."); return; }
    closeModal(); startJob(url, name);
  });
  setTimeout(() => (prefUrl ? $("#npName") : $("#npUrl"))?.focus(), 50);
}

// =================================================================== İŞ (profil hazırlanıyor)
const PHASES = [["reverse", "Site yapısı çözümleniyor"], ["scrape", "Akademisyen sitede aranıyor"], ["bot", "Bot koruması aşılıyor"],
  ["collect", "YÖK ve akademik kaynaklardan bilgiler toplanıyor"], ["merge", "Yayınlar birleştiriliyor ve doğrulanıyor"]];
const PHASE_NOW = { reverse: "Sitenin arka planda kullandığı istekler inceleniyor…", scrape: "Sayfalar okunuyor, akademisyen aranıyor…",
  bot: "Sitenin bot koruması aşılıyor…", collect: "YÖK profili, dersler, tezler ve yayınlar toplanıyor…",
  merge: "Tekrarlanan kayıtlar birleştiriliyor, bilgiler kaynaklar arasında doğrulanıyor…", ai: "Araştırma profili çıkarılıyor…" };
function phaseOf(ev) {
  if (/duvar|stealth|cloudflare|turnstile|bot koruma|418|403|429/i.test(ev.message)) return "bot";
  return { rea: "reverse", scrape: "scrape", crawl: "scrape", yok: "collect", publications: "collect", dedup: "merge", verify: "merge", analysis: "ai" }[ev.step] || "scrape";
}

async function startJob(url, name) {
  let job;
  try { job = await post("/api/jobs", { url, name }); } catch (e) { toast(esc(e.message)); return; }
  const node = document.createElement("div");
  node.className = "card job enter";
  node.innerHTML = `<div class="m-kicker"><span class="spinner"></span>Profil hazırlanıyor</div>
    <h2 style="margin-top:10px">${esc(name)}</h2><div class="job-sub">${esc(url)}</div>
    <div class="progress"><div></div></div>
    <div class="steps">${PHASES.map(([k, l]) => `<div class="step" data-phase="${k}" ${k === "bot" ? "hidden" : ""}><span class="dot"></span>${esc(l)}</div>`).join("")}</div>
    <div class="now"></div>
    <details class="tech"><summary>Teknik ayrıntılar</summary><div class="log"></div></details>`;
  S.jobs[job.id] = { node, name, done: false };
  location.hash = `#/is/${job.id}`;
  const order = PHASES.map(([k]) => k);
  const es = new EventSource(`/api/jobs/${job.id}/events`);
  S.jobs[job.id].es = es;
  es.onmessage = (e) => {
    const ev = JSON.parse(e.data);
    if (ev.type === "log") {
      const phase = phaseOf(ev), st = $(`.step[data-phase="${phase}"]`, node);
      if (st) {
        st.hidden = false;
        $$(".step.running", node).forEach((x) => {
          if (x !== st && (order.indexOf(x.dataset.phase) < order.indexOf(phase) || x.dataset.phase === "bot")) { x.className = "step done"; $(".dot", x).textContent = "✓"; }
        });
        if (!st.classList.contains("done")) st.className = "step running";
        $(".now", node).textContent = PHASE_NOW[phase] || "";
        $(".progress div", node).style.width = `${Math.max(8, ((order.indexOf(phase) + 1) / order.length) * 92)}%`;
      }
      const line = document.createElement("div");
      line.className = ev.status === "warning" ? "warning" : "";
      line.innerHTML = `<span class="t">${ev.t.toFixed(1).padStart(5)}s</span> <span class="s">${esc(ev.step)}</span> ${esc(ev.message)}`;
      const log = $(".log", node); log.appendChild(line); log.scrollTop = log.scrollHeight;
    } else if (ev.type === "result") {
      finish(ev.data);
    } else if (ev.type === "error") {
      S.jobs[job.id].failed = true;
      $(".now", node).innerHTML = `<div class="notice err">${icon("info")}<div>${esc(ev.message)}</div></div>`; hydrateIcons(node);
    } else if (ev.type === "end") { es.close(); }
  };
  function finish(r) {
    if (S.jobs[job.id].done) return;
    S.jobs[job.id].done = true;
    $(".progress div", node).style.width = "100%";
    $$(".step:not([hidden])", node).forEach((x) => { x.className = "step done"; $(".dot", x).textContent = "✓"; });
    loadChats();
    if (location.hash === `#/is/${job.id}`) { S.result = r; S.chatId = r.chat_id; location.hash = `#/profil/${r.chat_id}`; }
    else toast(`${icon("user")} <span><b>${esc(r.profile.name)}</b> profili hazır. <a href="#/profil/${esc(r.chat_id)}">Aç</a></span>`, 8000);
  }
  // Telefon ekranı kapanınca ya da tünel bağlantıyı kesince canlı akış kopar; iş sunucuda sürer.
  // Bu durumda sonuç hazır olana kadar birkaç saniyede bir sorulur (en fazla 10 dk).
  es.onerror = () => {
    es.close();
    if (S.jobs[job.id].done || S.jobs[job.id].failed || S.jobs[job.id].polling) return;
    S.jobs[job.id].polling = true;
    $(".now", node).textContent = "Bağlantı koptu; işlem sunucuda sürüyor, sonuç bekleniyor…";
    const until = Date.now() + 600000;
    const poll = async () => {
      if (S.jobs[job.id].done) return;
      try {
        const res = await fetch(`/api/jobs/${job.id}/result`);
        if (res.ok) { finish(await res.json()); return; }
      } catch { /* ağ geri gelene kadar dene */ }
      if (Date.now() < until) setTimeout(poll, 3000);
      else $(".now", node).textContent = "Sonuç alınamadı; profil hazırsa soldaki son aramalarda görünür.";
    };
    poll();
  };
}

function viewJob(jid) {
  const job = S.jobs[jid];
  setCrumbs([{ label: "Keşfet", href: "#/" }, { label: job ? job.name : "Profil" }]);
  if (!job) { setView(emptyState("clock", "Bu iş bulunamadı", "Sayfa yenilendiği için ilerleme bilgisi kayboldu. Tamamlanan profiller sol menüdeki son aramalarda.")); return; }
  const v = view(); v.innerHTML = ""; v.appendChild(job.node); v.scrollTop = 0;
}

// =================================================================== KURUM DİZİNİ
async function viewDirectory(url) {
  if (!safeUrl(url)) { location.hash = "#/"; return; }
  const host = new URL(url).hostname;
  if (!S.dir || S.dir.url !== url) S.dir = { url, host, data: null, fac: null, dep: null, deps: null, staff: null };
  const d = S.dir;
  setCrumbs([{ label: "Keşfet", href: "#/" }, { label: "Üniversiteler", href: "#/universiteler" }, { label: d.data?.name || host }]);
  setView(`
    <div class="card org-head">
      <div class="org-logo">${icon("building")}</div>
      <div><h1 id="orgName">${esc(d.data?.name || host)}</h1>
        <div class="meta"><span>${icon("globe")} <a href="${esc(safeUrl(url))}" target="_blank" rel="noopener">${esc(host)}</a></span><span id="orgMeta"></span></div></div>
      <div class="actions"><button class="btn sm" id="orgRefresh" type="button">${icon("refresh")}Yenile</button>
        <button class="btn sm primary" id="orgNewPerson" type="button">${icon("plus")}Akademisyen ara</button></div>
    </div>
    <div class="miller">
      <section class="card col" id="colFac">
        <div class="col-head"><span class="ch-icon">${icon("layers")}</span><h3>Fakülteler</h3><span class="count" id="nFac"></span></div>
        <div class="col-filter"><div class="input">${icon("search")}<input data-filter="colFac" placeholder="Fakültelerde ara"></div></div>
        <div class="col-body">${skeleton(7)}</div></section>
      <section class="card col" id="colDep">
        <div class="col-head"><span class="ch-icon">${icon("grid")}</span><h3>Bölümler</h3><span class="count" id="nDep"></span></div>
        <div class="col-filter"><div class="input">${icon("search")}<input data-filter="colDep" placeholder="Bölümlerde ara"></div></div>
        <div class="col-body"><div class="col-empty">Soldan bir fakülte seçin.</div></div></section>
      <section class="card col" id="colStaff">
        <div class="col-head"><span class="ch-icon">${icon("users")}</span><h3>Akademisyenler</h3><span class="count" id="nStaff"></span></div>
        <div class="col-filter"><div class="input">${icon("search")}<input data-filter="colStaff" placeholder="Akademisyenlerde ara"></div></div>
        <div class="col-body"><div class="col-empty">Bir bölüm seçin.</div></div></section>
    </div>`);
  $("#orgRefresh").onclick = () => loadFaculties(true);
  $("#orgNewPerson").onclick = () => newPersonModal(d.staff?.page || url);
  if (d.data) { renderFaculties(); if (d.deps) renderDeps(); if (d.staff) renderStaff(); }
  else loadFaculties(false);
}

async function loadFaculties(refresh) {
  const d = S.dir;
  $("#colFac .col-body").innerHTML = `<div class="loading-line"><span class="spinner"></span>Site menüsü okunuyor, fakülteler seçiliyor…</div>${skeleton(6)}`;
  try {
    d.data = await post("/api/directory/faculties", { url: d.url, refresh });
    d.fac = null; d.deps = null; d.staff = null;
    renderFaculties();
    $("#colDep .col-body").innerHTML = `<div class="col-empty">Soldan bir fakülte seçin.</div>`;
    $("#colStaff .col-body").innerHTML = `<div class="col-empty">Bir bölüm seçin.</div>`;
  } catch (e) {
    $("#colFac .col-body").innerHTML = `<div class="col-empty">${esc(e.message)}<br><br><button class="btn sm" onclick="loadFaculties(true)">Tekrar dene</button></div>`;
  }
}

function unitRow(u, kind, i, active) {
  return `<div class="unit ${active ? "active" : ""}" data-unit="${kind}" data-i="${i}" style="--i:${Math.min(i, 24)}" data-q="${esc(fold(u.name))}">
    <div class="u-main"><b>${esc(u.name)}</b><span>${esc(u.url.replace(/^https?:\/\//, ""))}</span></div>
    <div class="u-act"><button class="btn sm" data-unitpapers="${kind}" data-i="${i}" type="button" title="Bu birimin yayınları">${icon("file")}Yayınlar</button></div>
    ${icon("chevron")}</div>`;
}

function renderFaculties() {
  const d = S.dir, items = d.data.items || [];
  $("#orgName").textContent = d.data.name || d.host;
  $("#orgMeta").textContent = `${items.length} birim · ${d.data.method === "gemini" ? "Gemini ile seçildi" : "kurallarla seçildi"} · ${d.data.at || ""}`;
  setCrumbs([{ label: "Keşfet", href: "#/" }, { label: "Üniversiteler", href: "#/universiteler" }, { label: d.data.name || d.host }]);
  $("#nFac").textContent = items.length;
  $("#colFac .col-body").innerHTML = items.length ? `<div class="stagger">${items.map((u, i) => unitRow(u, "fac", i, d.fac === i)).join("")}</div>`
    : `<div class="col-empty">Fakülte bağlantısı bulunamadı. Fakültelerin listelendiği sayfanın bağlantısını girerek tekrar deneyin.</div>`;
  hydrateIcons($("#colFac"));
}

async function selectFaculty(i) {
  const d = S.dir; d.fac = i; d.dep = null; d.staff = null;
  $$("#colFac .unit").forEach((x) => x.classList.toggle("active", +x.dataset.i === i));
  $("#colDep .col-body").innerHTML = `<div class="loading-line"><span class="spinner"></span>Fakülte sayfası okunuyor…</div>${skeleton(6)}`;
  $("#colStaff .col-body").innerHTML = `<div class="col-empty">Bir bölüm seçin.</div>`; $("#nStaff").textContent = "";
  try {
    d.deps = await post("/api/directory/departments", { url: d.data.items[i].url });
    if (d.fac === i) renderDeps();
  } catch (e) { $("#colDep .col-body").innerHTML = `<div class="col-empty">${esc(e.message)}</div>`; }
}

function renderDeps() {
  const d = S.dir, items = d.deps.items || [];
  $("#nDep").textContent = items.length;
  $("#colDep .col-body").innerHTML = items.length ? `<div class="stagger">${items.map((u, i) => unitRow(u, "dep", i, d.dep === i)).join("")}</div>`
    : `<div class="col-empty">Bu fakültede bölüm bağlantısı bulunamadı.<br><br><button class="btn sm" data-facstaff type="button">${icon("users")}Fakülte kadrosunu göster</button></div>`;
  hydrateIcons($("#colDep"));
}

async function selectDept(i, unitUrl) {
  const d = S.dir; d.dep = i;
  $$("#colDep .unit").forEach((x) => x.classList.toggle("active", +x.dataset.i === i));
  $("#colStaff .col-body").innerHTML = `<div class="loading-line"><span class="spinner"></span>Akademik kadro sayfası aranıyor…</div>${skeleton(6)}`;
  try {
    d.staff = await post("/api/directory/staff", { url: unitUrl || d.deps.items[i].url });
    if (d.dep === i) renderStaff();
  } catch (e) { $("#colStaff .col-body").innerHTML = `<div class="col-empty">${esc(e.message)}</div>`; }
}

function renderStaff() {
  const d = S.dir, items = d.staff.items || [];
  $("#nStaff").textContent = items.length;
  $("#colStaff .col-body").innerHTML = items.length ? `<div class="stagger">${items.map((p, i) => `
    <div class="person" style="--i:${Math.min(i, 24)}" data-q="${esc(fold(p.name))}">
      ${avatar(p.name, p.photo)}
      <div class="p-main"><b>${esc(p.name)}</b><span>${esc(p.title || "")}</span></div>
      <div class="p-act">
        ${p.email ? `<a class="icon-btn" href="mailto:${esc(p.email)}" title="${esc(p.email)}">${icon("mail")}</a>` : ""}
        ${safeUrl(p.url) ? `<a class="icon-btn" href="${esc(safeUrl(p.url))}" target="_blank" rel="noopener" title="Kurum sayfası">${icon("external")}</a>` : ""}
        <button class="btn sm primary" data-profile="${i}" type="button">Profil</button></div></div>`).join("")}</div>
    <div class="faint" style="padding:10px 12px">Kaynak: <a href="${esc(safeUrl(d.staff.page))}" target="_blank" rel="noopener">${esc((d.staff.page || "").replace(/^https?:\/\//, ""))}</a></div>`
    : `<div class="col-empty">Bu birimde akademisyen listesi bulunamadı.${safeUrl(d.staff.page) ? `<br><a href="${esc(safeUrl(d.staff.page))}" target="_blank" rel="noopener">Sayfayı aç</a>` : ""}</div>`;
  hydrateIcons($("#colStaff"));
}

async function openUnitPapers(kind, i) {
  const d = S.dir, unit = kind === "fac" ? d.data.items[i] : d.deps.items[i];
  openDrawer(`<h2>${esc(unit.name)}</h2><p>${kind === "fac" ? "Fakülte" : "Bölüm"} yayınları · ${esc(d.data.name || d.host)}</p>`,
    `<div class="loading-line"><span class="spinner"></span>${kind === "fac" ? "Bölüm kadroları okunuyor ve akademisyenler OpenAlex'te eşleştiriliyor. Büyük fakültelerde bir iki dakika sürebilir…"
      : "Akademisyenler OpenAlex'te eşleştiriliyor…"}</div>${skeleton(6)}`);
  try {
    const r = await post("/api/directory/papers", { url: unit.url, level: kind === "fac" ? "faculty" : "department", name: unit.name });
    const listKey = `unit-${fold(unit.name).replace(/ /g, "-")}`;
    S.lists[listKey] = r.papers;
    S.listMeta[listKey] = { file: `${unit.name} ${d.data.name || d.host}` };
    const years = [...new Set(r.papers.map((p) => p.year).filter(Boolean))].sort((a, b) => b - a);
    $("#drawerBody").innerHTML = `
      <div class="stat-row"><div class="stat"><b>${fmtNum(r.papers.length)}</b><span>yayın</span></div>
        <div class="stat"><b>${r.matched}/${r.people}</b><span>akademisyen eşleşti</span></div>
        <div class="stat"><b>${fmtNum(r.papers.reduce((s, p) => s + (p.citations || 0), 0))}</b><span>toplam atıf</span></div></div>
      <div class="notice" style="margin-bottom:14px">${icon("info")}<div>Hızlı liste OpenAlex'ten. Bir akademisyenin YÖK dahil tam listesi için dizinde <b>Profil</b> düğmesini kullanın.
        ${r.missing.length ? `<br><span class="faint">OpenAlex'te eşleşmeyen: ${esc(r.missing.slice(0, 12).join(", "))}${r.missing.length > 12 ? "…" : ""}</span>` : ""}
        ${r.loose?.length ? `<br><span class="faint">Bu kurumda OpenAlex yayını yok, yalnızca adla eşleşti (o adla tek yazar): ${esc(r.loose.join(", "))}</span>` : ""}</div></div>
      <div class="toolbar"><div class="input">${icon("search")}<input id="dwFilter" placeholder="Başlık ya da yazar ara"></div>
        <select class="select" id="dwYear"><option value="">Tüm yıllar</option>${years.map((y) => `<option>${y}</option>`).join("")}</select>
        ${exportButtons(listKey)}</div>
      <div class="card" id="dwList"></div>`;
    hydrateIcons($("#drawerBody"));
    const draw = () => {
      const q = fold($("#dwFilter").value), y = $("#dwYear").value;
      const list = r.papers.filter((p) => (!y || String(p.year) === y) && (!q || fold(`${p.title} ${(p.authors || []).join(" ")}`).includes(q)));
      S.lists[listKey] = list;
      $("#dwList").innerHTML = list.length ? `<div class="stagger">${list.slice(0, 300).map((p, n) => paperCard(p, {}, n)).join("")}</div>`
        : emptyState("file", "Yayın bulunamadı", "Filtreyi değiştirin.");
      hydrateIcons($("#dwList"));
    };
    $("#dwFilter").oninput = draw; $("#dwYear").onchange = draw; draw();
  } catch (e) {
    $("#drawerBody").innerHTML = `<div class="notice err">${icon("info")}<div>${esc(e.message)}</div></div>`; hydrateIcons($("#drawerBody"));
  }
}

function openDrawer(head, body) {
  $("#drawerTitle").innerHTML = head; $("#drawerBody").innerHTML = body; hydrateIcons($("#drawer"));
  $("#drawer").classList.add("open"); $("#drawer").setAttribute("aria-hidden", "false");
}
function closeDrawer() { $("#drawer").classList.remove("open"); $("#drawer").setAttribute("aria-hidden", "true"); }

// =================================================================== PROFİL
async function viewProfile(cid) {
  setCrumbs([{ label: "Keşfet", href: "#/" }, { label: "Akademisyen" }]);
  let chat = null;
  if (!(S.result && S.result.chat_id === cid)) {
    setView(`<div class="card card-pad">${skeleton(4)}</div>`);
    try {
      const data = await api(`/api/chats/${encodeURIComponent(cid)}`);
      if (!data.result) { setView(emptyState("user", "Profil sonucu bulunamadı", "Bu sohbetin profil sonucu silinmiş olabilir.")); return; }
      S.result = data.result; chat = data.chat;
    } catch { setView(emptyState("user", "Profil bulunamadı", "Bu kayıt silinmiş olabilir.")); return; }
  }
  S.chatId = cid; S.jobId = S.result.job_id;
  renderProfile(S.result, chat);
  $$(".h-item").forEach((x) => x.classList.toggle("active", x.dataset.chat === cid));
}

function vbadge(key) {
  const v = S.result.profile.verification?.[key];
  if (!v) return "";
  const cls = { "doğrulandı": "ok", "çelişki": "conflict", "değişti": "changed" }[v.status] || "";
  const ic = { "doğrulandı": "✓", "çelişki": "⚠", "değişti": "↻" }[v.status] || "·";
  const alt = v.alternatives?.length ? ` | alternatif: ${v.alternatives.map((a) => `${a.value} (${a.sources.join("+")})`).join("; ")}` : "";
  return `<span class="vb ${cls}" title="${esc(`Kaynaklar: ${v.sources.join(", ")} · güven %${Math.round(v.confidence * 100)}${alt}`)}">${ic} ${esc(v.status)}</span>`;
}
function evidence(ids) {
  return (ids || []).map((id) => {
    const p = S.result.publications.find((x) => x.id === id);
    return p ? `<a class="ev" href="#" data-open="${reg(p, { jid: S.result.job_id, pid: p.id, person: S.result.profile.name })}" title="${esc(p.title)}">${esc(id)} · ${esc(p.title)}</a>` : "";
  }).join("");
}
function claims(items, tl = false) {
  if (!items?.length) return `<p class="muted">Desteklenen bir çıkarım bulunamadı.</p>`;
  return items.map((c) => `<div class="claim"><strong>${esc(tl ? c.period : c.label)}</strong>${esc(c.text)}<div>${evidence(c.evidence)}</div></div>`).join("");
}
function timeline(items, cls = "") {
  if (!items?.length) return `<p class="muted">Kayıt yok.</p>`;
  return `<ul class="timeline ${cls}">${items.map((x) => `<li><div class="tl-period">${esc(x.period)}</div>
    ${x.role ? `<div class="tl-role">${esc(x.role)}</div>` : ""}<div class="tl-place">${esc(x.place)}</div>
    ${x.unit ? `<div class="tl-unit">${esc(x.unit)}</div>` : ""}${x.note ? `<div class="tl-note">${esc(x.note)}</div>` : ""}</li>`).join("")}</ul>`;
}
function sectionView(rows, cls = "") {
  if (!rows?.length) return `<p class="muted">Kayıt yok.</p>`;
  if ("period" in rows[0]) return timeline(rows, cls);
  if ("title" in rows[0] && "labels" in rows[0]) {
    return `<div class="list-rows">${rows.map((r) => `<div class="list-row"><div class="chips" style="margin-bottom:6px">${(r.labels || []).map((l) => `<span class="chip">${esc(l)}</span>`).join("")}</div>
      <b>${esc(r.title)}</b>${r.detail ? `<span>${esc(r.detail)}</span>` : ""}${r.extra ? `<div class="faint">${esc(r.extra)}</div>` : ""}</div>`).join("")}</div>`;
  }
  const groups = {};
  rows.forEach((r) => (groups[r.group || ""] ||= []).push(r));
  return Object.entries(groups).map(([g, list]) => {
    const cols = Object.keys(list[0]).filter((k) => !["group", "url"].includes(k));
    const longest = cols.reduce((a, k) => (String(list[0][k] || "").length > String(list[0][a] || "").length ? k : a), cols[0]);
    return `${g ? `<div class="group-title">${esc(g)} · ${list.length}</div>` : ""}<div class="tbl-wrap"><table class="tbl"><thead><tr>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead>
      <tbody>${list.map((r) => `<tr>${cols.map((c) => `<td>${c === longest && safeUrl(r.url) ? `<a href="${esc(safeUrl(r.url))}" target="_blank" rel="noopener">${esc(r[c])}</a>` : esc(r[c])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  }).join("");
}

function renderProfile(r, chat) {
  const p = r.profile, a = r.analysis, y = p.yok || {}, sec = y.sections || {};
  const key = r.job_id;
  const isFav = !!favPerson(key);
  setCrumbs([{ label: "Keşfet", href: "#/" }, ...(p.institution ? [{ label: p.institution, href: "#/universiteler" }] : []), { label: p.name }]);
  const links = [
    y.email && `<a class="chip blue" href="mailto:${esc(y.email)}">${icon("mail")}${esc(y.email)}</a>`,
    p.orcid && `<a class="chip teal" href="https://orcid.org/${esc(p.orcid)}" target="_blank" rel="noopener">ORCID ${esc(p.orcid)}</a>`,
    safeUrl(p.links?.yok) && `<a class="chip" href="${esc(safeUrl(p.links.yok))}" target="_blank" rel="noopener">${icon("cap")}YÖK Akademik</a>`,
    safeUrl(p.links?.scholar) && `<a class="chip" href="${esc(safeUrl(p.links.scholar))}" target="_blank" rel="noopener">Google Scholar</a>`,
    safeUrl(p.source_url) && `<a class="chip" href="${esc(safeUrl(p.source_url))}" target="_blank" rel="noopener">${icon("building")}Kurum sayfası</a>`,
  ].filter(Boolean).join("");
  const totalCites = r.publications.reduce((s, x) => s + (x.citations || 0), 0);
  const tez = y.tez_merkezi || {}, trProjects = y.tr_projects || [];
  const nTheses = Math.max((sec.theses || []).length, (tez.advised || []).length);
  const tabs = [
    ["overview", "Genel bakış", ""], ["pubs", "Yayınlar", r.unique_count], ["career", "Akademik geçmiş", (y.career || []).length + (y.education || []).length],
    ["courses", "Dersler", (sec.courses || []).length], ["theses", "Tezler", nTheses],
    ["more", "Projeler ve diğer", ["projects", "awards", "patents", "memberships", "art"].reduce((s, k) => s + (sec[k] || []).length, 0)],
    ["collab", "İş birlikleri", (y.collaborators || []).length + (r.industry || []).length],
    ...(trProjects.length ? [["tubitak", "TÜBİTAK", trProjects.length]] : []), ["chat", "Asistan", ""],
  ];
  const otherSections = [["projects", "Projeler", "briefcase"], ["awards", "Ödüller", "award"], ["patents", "Patentler", "file"],
    ["memberships", "Üyelikler", "users"], ["art", "Sanatsal faaliyetler", "sparkle"]];
  const pubSrc = (x) => ({ jid: r.job_id, pid: x.id, person: p.name });
  S.lists.pubs = r.publications;
  S.listMeta.pubs = { file: p.name, person: p.name, title: p.title, institution: p.institution };

  const root = setView(`
    <section class="card profile-hero">
      <div class="ph-band"></div>
      <div class="ph-body">
        <div class="ph-photo">${safeImg(y.photo) ? `<img src="${esc(safeImg(y.photo))}" alt="${esc(p.name)}">` : avatar(p.name, "")}</div>
        <div class="ph-info">
          <div class="ph-title">${esc(p.title || "Unvan bilinmiyor")}${vbadge("title")}</div>
          <h1>${esc(p.name)}</h1>
          <div class="ph-lines"><span>${esc(p.department || "Bölüm bilinmiyor")}${vbadge("department")}</span>
            <span>${esc(p.institution || "Kurum bilinmiyor")}${vbadge("institution")}</span></div>
          <div class="ph-links">${links}</div>
        </div>
        <div class="ph-actions">
          <button class="btn ${isFav ? "" : "primary"}" id="favPersonBtn" type="button">${icon("star")}${isFav ? "Favorilerde" : "Favorilere ekle"}</button>
          <button class="btn" data-tabgo="chat" type="button">${icon("message")}Asistana sor</button>
        </div>
      </div>
      <div class="kpis">
        <div class="kpi"><b>${fmtNum(r.unique_count)}</b><span>benzersiz yayın</span></div>
        <div class="kpi"><b>${fmtNum(totalCites)}</b><span>toplam atıf</span></div>
        <div class="kpi"><b>${fmtNum((sec.courses || []).length)}</b><span>ders</span></div>
        <div class="kpi"><b>${fmtNum(nTheses)}</b><span>yönetilen tez</span></div>
        <div class="kpi"><b>${fmtNum((y.collaborators || []).length)}</b><span>iş birliği</span></div>
        <div class="kpi"><b>${Object.entries(r.by_source || {}).map(([k, v]) => `${SRC_TR[k] || k} ${v}`).join(" · ") || "—"}</b><span>kaynak dağılımı</span></div>
      </div>
    </section>

    <div class="tabs" role="tablist">${tabs.map(([k, l, n], i) => `<button class="tab ${i === 0 ? "active" : ""}" data-tab="${k}" type="button">${esc(l)}${n !== "" && n != null ? `<span class="n">${fmtNum(n)}</span>` : ""}</button>`).join("")}</div>

    <div class="panel active" data-panel="overview"><div class="stack">
      <div class="stack" id="analysisBox">${analysisHtml(a)}</div>
      ${(p.verification?.interests?.length || p.interests?.length) ? `<div class="card card-pad"><div class="card-title">İlgi alanları</div><div class="chips">
        ${(p.verification?.interests?.length ? p.verification.interests.slice(0, 16).map((x) => `<span class="chip" title="${esc(x.sources.join(", "))}">${esc(x.value)}${x.sources.length > 1 ? `<sup>✓${x.sources.length}</sup>` : ""}</span>`)
          : p.interests.map((x) => `<span class="chip">${esc(x)}</span>`)).join("")}</div></div>` : ""}
      ${(r.industry || []).length ? `<div class="card card-pad"><div class="card-title">${icon("building")}Sanayi iş birlikleri<span class="spacer"></span>
        <button class="btn sm" data-tabgo="collab" type="button">Kanıtları gör</button></div><div class="chips">${r.industry.map((x) =>
          `<span class="chip ${x.official ? "teal" : ""}">${x.official ? "✓ " : ""}${esc(x.name)}</span>`).join("")}</div></div>` : ""}
      ${techTrace(r)}
      <p class="faint">${esc(r.summary || "")} · ${r.elapsed ?? "?"} sn · ${esc(r.llm || "")}${y.updated ? ` · YÖK son güncelleme ${esc(y.updated)}` : ""}</p>
    </div></div>

    <div class="panel" data-panel="pubs">
      <div class="toolbar"><div class="input">${icon("search")}<input id="pubFilter" placeholder="Başlıkta ara"></div>
        <select class="select" id="pubSort"><option value="year">En yeni</option><option value="cites">En çok atıf</option><option value="title">Başlık</option></select>
        ${exportButtons("pubs")}</div>
      <div class="card"><div class="tbl-wrap"><table class="tbl"><thead><tr><th style="width:52px">#</th><th>Başlık</th><th>Yıl</th><th>Kaynak</th><th>Doğrulama</th><th>Atıf</th><th></th></tr></thead>
        <tbody id="pubs"></tbody></table></div></div>
    </div>

    <div class="panel" data-panel="career"><div class="grid-2">
      <div class="card card-pad"><div class="card-title">${icon("briefcase")}Akademik görevler</div>${timeline(y.career)}</div>
      <div class="card card-pad"><div class="card-title">${icon("cap")}Öğrenim</div>${timeline(y.education, "teal")}</div>
      <div class="card card-pad"><div class="card-title">${icon("award")}İdari görevler</div>${sectionView(sec.admin, "gold")}</div>
      <div class="card card-pad"><div class="card-title">${icon("building")}Üniversite dışı deneyim</div>${sectionView(sec.experience)}</div>
    </div>${!y.career ? `<div class="notice warn" style="margin-top:16px">${icon("info")}<div>Bu profil YÖK ayrıntıları eklenmeden önce hazırlanmış. Güncel bilgiler için profili yeniden oluşturun.</div></div>` : ""}</div>

    <div class="panel" data-panel="courses"><div class="card card-pad">${sectionView(sec.courses)}</div></div>
    <div class="panel" data-panel="theses"><div class="stack">
      ${tez.own?.length ? `<div class="card card-pad"><div class="card-title">${icon("cap")}Kendi tezleri<span class="spacer"></span><span class="badge tez">Tez Merkezi</span></div>${thesisList(tez.own, false)}</div>` : ""}
      ${tez.advised?.length ? `<div class="card card-pad"><div class="card-title">${icon("users")}Danışmanlık yaptığı tezler<span class="spacer"></span><span class="count">${tez.advised.length}</span><span class="badge tez">Tez Merkezi</span></div>${thesisList(tez.advised, true)}</div>`
        : `<div class="card card-pad"><div class="card-title">${icon("users")}Yönetilen tezler<span class="spacer"></span><span class="badge yok">YÖK</span></div>${sectionView(sec.theses)}</div>`}
    </div></div>
    <div class="panel" data-panel="more"><div class="grid-2">
      ${otherSections.map(([k, l, ic]) => `<div class="card card-pad"><div class="card-title">${icon(ic)}${l}<span class="spacer"></span><span class="count">${(sec[k] || []).length || ""}</span></div>${sectionView(sec[k])}</div>`).join("")}</div></div>

    <div class="panel" data-panel="collab"><div class="stack"><div id="industryBox">${industryHtml(r.industry)}</div>${(y.collaborators || []).length ? `<div class="collabs stagger">${y.collaborators.map((c, i) => `
      <div class="collab" style="--i:${i}">${avatar(c.name, c.photo)}<div class="c-main"><div class="c-title">${esc(c.title)}</div><b>${esc(c.name)}</b>
        <span>${esc(c.institution)}</span><span class="faint">${esc(c.unit)}</span>
        <div class="chips" style="margin-top:8px"><a class="chip" href="${esc(safeUrl(c.url))}" target="_blank" rel="noopener">${icon("cap")}YÖK</a></div></div></div>`).join("")}</div>`
      : `<div class="card">${emptyState("users", "İş birliği bilgisi yok", "YÖK'te birlikte çalıştığı kişi kaydı bulunamadı ya da profil eski sürümle hazırlandı.")}</div>`}</div></div>

    <div class="panel" data-panel="tubitak"><div class="card card-pad" id="tubitakBox">${tubitakHtml(trProjects, r.industry)}</div></div>

    <div class="panel" data-panel="chat"><div class="card chat-wrap">
      <div class="thread" id="thread"><div class="msg bot">${avatar("İz", "")}<div class="bubble">Merhaba! <b>${esc(p.name)}</b> hakkında yayınlar, dersler, tezler, iş birlikleri ya da araştırma alanları üzerine soru sorabilirsiniz.
        Cevaplar yalnızca toplanan kaynaklara dayanır ve yayın kimlikleriyle gösterilir.</div></div></div>
      <div class="suggest">${["En çok atıf alan yayınları hangileri?", "Hangi dersleri veriyor?", "Danışmanlık yaptığı tezler hangi konularda?", "TÜBİTAK projeleri neler?", "Hangi firmalarla çalışmış?", "Son yıllarda hangi konulara yöneldi?", "En sık kimlerle çalışıyor?"].map((q) => `<button class="chip" data-ask="${esc(q)}" type="button">${esc(q)}</button>`).join("")}</div>
      <form class="composer" id="askForm"><div class="input">${icon("message")}<input id="question" placeholder="${esc(p.name)} hakkında bir şey sorun…" autocomplete="off"></div>
        <button class="btn primary" id="send" type="submit">${icon("send")}Gönder</button></form>
    </div></div>`);

  const tbody = $("#pubs");
  const drawPubs = () => {
    const q = fold($("#pubFilter").value), sort = $("#pubSort").value;
    let list = r.publications.filter((x) => !q || fold(`${x.title} ${x.variants.map((v) => v.title).join(" ")} ${x.venue || ""}`).includes(q));
    list = [...list].sort(sort === "cites" ? (m, n) => (n.citations || 0) - (m.citations || 0) : sort === "title" ? (m, n) => m.title.localeCompare(n.title, "tr") : () => 0);
    S.lists.pubs = list;
    tbody.innerHTML = list.map((x) => {
      const id = reg(x, pubSrc(x));
      return `<tr id="pub-${esc(x.id)}"><td class="faint">${esc(x.id)}</td>
        <td><div class="t-title" data-open="${id}">${esc(x.title)}</div>
          ${x.venue ? `<div class="variants">${esc(x.venue)}</div>` : ""}
          ${x.variants.length > 1 ? `<div class="variants">↳ ${x.variants.slice(1).map((v) => `${esc(v.title)} (${esc(v.lang)})`).join(" · ")}</div>` : ""}</td>
        <td>${esc(x.year || "—")}</td>
        <td><div class="chips">${x.sources.map((s) => `<span class="badge ${esc(s)}">${esc(SRC_TR[s] || s)}</span>`).join("")}</div></td>
        <td>${x.verified ? `<span class="vb ok">✓ ${x.sources.length > 1 ? x.sources.length + " kaynak" : x.runs_seen + ". kez"}</span>` : `<span class="vb">tek kaynak</span>`}${x.is_new ? `<span class="newb">YENİ</span>` : ""}</td>
        <td>${fmtNum(x.citations)}</td>
        <td><button class="star ${favPaper(x) ? "on" : ""}" data-star="${id}" type="button" title="Favorilere ekle">${icon("star")}</button></td></tr>`;
    }).join("") || `<tr><td colspan="7">${emptyState("file", "Yayın yok", "Filtreyi değiştirin.")}</td></tr>`;
    hydrateIcons(tbody);
  };
  $("#pubFilter").oninput = drawPubs; $("#pubSort").onchange = drawPubs; drawPubs();

  $("#favPersonBtn").onclick = async () => {
    const btn = $("#favPersonBtn");
    try {
      if (favPerson(key)) { await api(`/api/favorites/people/${encodeURIComponent(key)}`, { method: "DELETE" }); toast("Favorilerden çıkarıldı."); }
      else {
        await post("/api/favorites/people", { item: { name: p.name, title: p.title, institution: p.institution, department: p.department,
          photo: y.photo, email: y.email, chat_id: r.chat_id, job_id: r.job_id, papers: r.unique_count } });
        toast(`${icon("star")} Favori akademisyenlere eklendi.`);
      }
      await loadFav();
      const on = !!favPerson(key);
      btn.className = `btn ${on ? "" : "primary"}`; btn.innerHTML = `${icon("star")}${on ? "Favorilerde" : "Favorilere ekle"}`;
    } catch (e) { toast(esc(e.message)); }
  };
  $("#askForm").addEventListener("submit", (e) => { e.preventDefault(); const q = $("#question").value.trim(); $("#question").value = ""; ask(q); });
  if (chat?.messages?.length) {
    chat.messages.forEach((m) => addMsg(m.role === "user" ? "user" : "bot", m.role === "user" ? esc(m.content) : `<div class="answer">${formatAnswer(m.content)}</div>${metaLine(m.meta)}`));
  }
  // eski profiller ya da değişen eşleştirme kuralı: kayıtlı veriden yeniden hesaplanır (dış istek yok)
  if (!r.industry || r.industry_v !== INDUSTRY_V) refreshIndustry(true);
  void root;
}

// Sanayi iş birlikleri: YÖK deneyim/proje/patent, TR Dizin projeleri ve ortak yazar kurumlarından,
// Sanayi ve Teknoloji Bakanlığı Ar-Ge / Tasarım Merkezi listesiyle eşleştirilerek çıkarılır.
function industryHtml(list) {
  const head = `<div class="card-title">${icon("building")}Sanayi ve Ar-Ge iş birlikleri<span class="spacer"></span>
    <button class="icon-btn" data-industry type="button" title="Yeniden hesapla">${icon("refresh")}</button></div>`;
  if (!list) return `<div class="card card-pad">${head}<div class="loading-line"><span class="spinner"></span>Hesaplanıyor…</div></div>`;
  if (!list.length) return `<div class="card card-pad">${head}<p class="muted" style="margin:0">Yayın, YÖK deneyimi, proje ve patent kayıtlarında firma izi bulunamadı.
    Gizli sözleşmeler ve yayına dönüşmeyen işler bu kaynaklarda görünmez.</p></div>`;
  return `<div class="card card-pad">${head}
    <p class="muted" style="margin:0 0 6px">✓ işaretli firmalar Sanayi ve Teknoloji Bakanlığı Ar-Ge / Tasarım Merkezi listesinde kayıtlı.</p>
    ${list.map((x) => `<div class="thesis"><b>${esc(x.name)}</b>
      <div class="chips">${x.official ? `<span class="chip teal">✓ ${esc(x.kinds.join(" · ") || "Ar-Ge Merkezi")}</span>` : `<span class="chip">Listede yok</span>`}
        ${x.cities.slice(0, 3).map((c) => `<span class="chip">${esc(c)}</span>`).join("")}
        ${x.sectors.slice(0, 2).map((c) => `<span class="chip blue">${esc(c)}</span>`).join("")}
        ${x.centers > 1 ? `<span class="chip">${x.centers} merkez</span>` : ""}</div>
      ${x.evidence.map((e) => `<div class="variants"><b style="display:inline;font-size:inherit">${esc(e.type)}:</b> ${esc(e.text)}
        ${e.pub ? `<span class="cite" data-pub="${esc(e.pub)}">${esc(e.pub)}</span>` : ""}${e.org && e.org !== x.name ? ` <span class="faint">(${esc(e.org)})</span>` : ""}</div>`).join("")}</div>`).join("")}</div>`;
}

const INDUSTRY_V = 2;  // app/industry.py VERSION

// Akademisyenin TÜBİTAK (ARDEB) projeleri; özetinde iş birliği yapılan resmi Ar-Ge firması geçiyorsa işaretlenir.
function tubitakHtml(projects, industry) {
  const firmsOf = (title) => (industry || []).filter((e) => e.evidence.some((v) => v.type === "TÜBİTAK projesi" && v.text.includes(title)));
  return `<div class="card-title">${icon("briefcase")}TÜBİTAK projeleri<span class="spacer"></span><span class="count">${projects.length}</span><span class="badge trdizin">TR Dizin</span></div>
    ${projects.map((x) => `<div class="thesis"><b>${esc(x.title)}</b><div class="chips"><span class="chip">${esc(x.year || "")}</span>${x.role ? `<span class="chip blue">${esc(x.role)}</span>` : ""}${x.group ? `<span class="chip">${esc(x.group)}</span>` : ""}${x.number ? `<span class="chip">No ${esc(x.number)}</span>` : ""}
      ${firmsOf(x.title).map((f) => `<span class="chip teal">${icon("building")}${esc(f.name)}</span>`).join("")}
      <a class="chip" href="${esc(safeUrl(x.url))}" target="_blank" rel="noopener">TR Dizin ${icon("external")}</a></div>
      ${x.abstract ? `<details><summary>Proje özeti</summary><div class="abs">${esc(x.abstract)}</div></details>` : ""}</div>`).join("")}`;
}

async function refreshIndustry(quiet) {
  const r = S.result, box = $("#industryBox");
  if (!r || !box) return;
  box.innerHTML = industryHtml(null); hydrateIcons(box);
  try {
    const d = await post(`/api/jobs/${r.job_id}/industry`, {});
    if (S.result !== r) return;
    r.industry = d.industry; r.industry_v = d.industry_v;
    if (!quiet) toast(`${icon("building")} ${d.industry.length} firma bulundu (${fmtNum(d.centers.count || 0)} resmi merkez içinde).`);
  } catch (e) { if (!quiet) toast(esc(e.message)); }
  const now = $("#industryBox");
  if (now && S.result === r) { now.innerHTML = industryHtml(r.industry || []); hydrateIcons(now); }
  const tb = $("#tubitakBox");
  if (tb && S.result === r) { tb.innerHTML = tubitakHtml(r.profile.yok?.tr_projects || [], r.industry); hydrateIcons(tb); }
}

// Yapay zekâ analizi isteğe bağlıdır: profil hemen açılır, analiz düğmeyle üretilir.
function analysisHtml(a) {
  if (a.mode === "unavailable") return "";
  if (a.mode === "pending") {
    return `<div class="card card-pad"><div class="card-title">${icon("sparkle")}Araştırma analizi</div>
      <p class="muted" style="margin:0 0 14px">Yayınlardan araştırma alanları, yöntemler ve yıllara göre odak değişimi çıkarılır.
        Her iddia yayın kimlikleriyle kanıtlanır. Yaklaşık 10 saniye sürer.</p>
      <button class="btn primary" data-analyze type="button">${icon("sparkle")}Yapay zekâ ile analiz et</button></div>`;
  }
  return `<div class="card card-pad"><div class="card-title">${icon("sparkle")}Araştırma özeti<span class="spacer"></span>
      <span class="chip ${a.mode === "mock" ? "gold" : "blue"}">${a.mode === "mock" ? "Kural tabanlı analiz" : "Gemini · " + esc(a.model || "")}</span>
      <button class="icon-btn" data-analyze type="button" title="Yeniden analiz et">${icon("refresh")}</button></div>
      ${a.summary ? `<p class="summary-text">${esc(a.summary)}</p>` : ""}
      <div class="chips" style="margin-bottom:14px">${(a.areas || []).map((x) => `<span class="chip blue">${esc(x.label)}</span>`).join("")}</div>
      ${claims(a.areas)}</div>
    <div class="grid-2">
      <div class="card card-pad"><div class="card-title">Yöntemler</div>${claims(a.methods)}</div>
      <div class="card card-pad"><div class="card-title">Yıllara göre odak</div>${claims(a.timeline, true)}</div>
    </div>`;
}

async function runAnalysis() {
  const box = $("#analysisBox"), r = S.result;
  if (!box || !r || S.analyzing) return;
  S.analyzing = true;
  box.innerHTML = `<div class="card card-pad"><div class="card-title">${icon("sparkle")}Araştırma analizi</div>
    <div class="loading-line"><span class="spinner"></span>Gemini ${fmtNum(r.unique_count)} yayını inceliyor, iddialar kanıtlarla doğrulanıyor…</div>${skeleton(3)}</div>`;
  hydrateIcons(box);
  try {
    const a = await post(`/api/jobs/${r.job_id}/analyze`, {});
    if (S.result !== r) return;
    r.analysis = a;
    box.innerHTML = analysisHtml(a); hydrateIcons(box);
    toast(`${icon("sparkle")} Analiz hazır.`);
  } catch (e) {
    box.innerHTML = analysisHtml(r.analysis); hydrateIcons(box);
    toast(esc(e.message));
  } finally { S.analyzing = false; }
}

function thesisList(items, advised) {
  return items.map((x) => `<div class="thesis"><b>${esc(x.title)}</b>${x.alt_title ? `<div class="alt">${esc(x.alt_title)}</div>` : ""}
    <div class="chips"><span class="chip">${esc(x.year)}</span><span class="chip ${x.type === "Doktora" ? "gold" : "blue"}">${esc(x.type)}</span>
      ${advised ? `<span class="chip">${icon("user")}${esc(x.author)}</span>` : ""}<span class="chip">${esc(x.university)}</span>
      ${safeUrl(x.pdf) ? `<a class="chip teal" href="${esc(safeUrl(x.pdf))}" target="_blank" rel="noopener">${icon("file")}PDF</a>` : ""}</div>
    ${x.abstract_tr ? `<details><summary>Türkçe özet</summary><div class="abs">${esc(x.abstract_tr)}</div></details>` : ""}
    ${x.abstract_en ? `<details><summary>English abstract</summary><div class="abs">${esc(x.abstract_en)}</div></details>` : ""}</div>`).join("");
}

function techTrace(r) {
  const rec = r.recon || {}, rcp = rec.recipe || {}, lines = [];
  if (rec.rea) lines.push(`<b>REA keşfi</b>: ${rec.rea.requests} istek · ${rec.rea.api_calls.length} XHR/fetch · içerik: <b>${esc(rec.content_origin || "?")}</b>`);
  if (rec.hidden_api) lines.push(`<b>Gizli API</b>: ${esc(rec.hidden_api.method)} ${esc(rec.hidden_api.url)}`);
  if (rcp.detail) lines.push(`<b>Detay butonu</b>: ${rcp.detail.replayed ? `<span class="ev-ok">tarif tarayıcısız oynatıldı (${rcp.detail.elapsed} sn)</span>` : `REA öğrendi → ${esc(rcp.detail.method)} ${esc(rcp.detail.url)}`}`);
  if (rec.yok_rea) lines.push(`<b>YÖK araması</b>: ${rec.yok_rea.replayed ? `<span class="ev-ok">REA tarifi tekrar oynatıldı (${rec.yok_rea.elapsed} sn)</span>` : `REA formu çözdü → ${esc(rec.yok_rea.method)} ${esc(rec.yok_rea.url)}`}`);
  if (rcp.start_page?.known) lines.push(`<b>Değişiklik algılama</b>: yapı benzerliği %${Math.round(rcp.start_page.similarity * 100)} → ${rcp.start_page.drift ? '<span class="ev-drift">değişmiş, REA yeniden öğrendi</span>' : '<span class="ev-ok">değişmemiş</span>'}`);
  if (rcp.replay) lines.push(`<b>Tarif tekrarı</b>: ${rcp.replay.ok ? `<span class="ev-ok">✓ ${esc(rcp.replay.url)} · ${rcp.replay.elapsed} sn</span>` : `<span class="ev-drift">✗ ${esc(rcp.replay.error)}</span>`}`);
  if (rcp.card) lines.push(`<b>Scrapling adaptive</b>: ${rcp.card === "relocated" ? '<span class="ev-drift">kart benzerlikle yeniden bulundu</span>' : '<span class="ev-ok">aynı seçici</span>'}`);
  if (rec.crawl?.pages) lines.push(`<b>Tarama</b>: ${rec.crawl.pages} sayfa → ${esc(rec.crawl.found_at || "bulunamadı")}`);
  (rec.walls || []).forEach((w) => lines.push(`<b>Duvar</b>: ${esc(w.url)} (${esc(w.reason)}) → aşıldı`));
  return lines.length ? `<details class="card card-pad tech-card"><summary>${icon("settings")}Teknik iz · REA + Scrapling</summary><div class="recon">${lines.map((l) => `<div>${l}</div>`).join("")}</div></details>` : "";
}

// ------------------------------------------------------------------- asistan
const MODE_NAMES = { rag: "RAG", cag: "CAG", hybrid: "Hibrit" };
function metaLine(m) {
  if (!m || !m.mode) return "";
  const parts = [`<b>${esc(MODE_NAMES[m.mode] || m.mode)}</b>${m.route ? ` · ${esc(m.route)}` : ""}`];
  if (m.retrieved?.length) parts.push(m.retrieved.map((id) => `<span class="cite" data-pub="${esc(id)}">${esc(id)}</span>`).join(" "));
  if (m.ttft != null) parts.push(`ilk token ${m.ttft} sn`);
  if (m.total_s != null) parts.push(`toplam ${m.total_s} sn`);
  return `<div class="meta">${parts.join(" · ")}</div>`;
}
function addMsg(role, html) {
  const thread = $("#thread"); if (!thread) return null;
  const el = document.createElement("div");
  el.className = `msg ${role}`;
  el.innerHTML = `${role === "bot" ? avatar("İz", "") : ""}<div class="bubble">${html}</div>`;
  thread.appendChild(el); thread.scrollTop = thread.scrollHeight;
  return $(".bubble", el);
}
async function ask(question) {
  if (!question || !S.result || S.chatRequest) return;
  const controller = new AbortController(); S.chatRequest = controller;
  $("#send").disabled = true;
  addMsg("user", esc(question));
  const bubble = addMsg("bot", `<div class="answer typing"></div><div class="faint stage">Yanıt hazırlanıyor…</div>`);
  const out = $(".answer", bubble), stage = $(".stage", bubble);
  let text = "", meta = null, failure = "";
  const timer = setTimeout(() => controller.abort(), 150000);
  try {
    const res = await fetch(`/api/jobs/${S.result.job_id}/chat`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, chat_id: S.chatId, mode: "auto" }), signal: controller.signal });
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${res.status}`); }
    await readSse(res, (m) => {
      if (m.chat_id) S.chatId = m.chat_id;
      if (m.stage) stage.textContent = m.stage;
      if (m.delta) { text += m.delta; out.innerHTML = formatAnswer(text); stage.textContent = ""; $("#thread").scrollTop = 1e9; }
      if (m.error) failure = m.error;
      if (m.done) { meta = m.meta; return false; }
    }, controller.signal);
    if (failure) throw new Error(failure);
    if (meta) out.insertAdjacentHTML("afterend", metaLine(meta));
  } catch (e) {
    if (!text) out.textContent = "Cevap alınamadı.";
    stage.textContent = e.name === "AbortError" ? "Bekleme süresi doldu." : `Hata: ${e.message}`;
  } finally {
    clearTimeout(timer); out.classList.remove("typing");
    if (S.chatRequest === controller) S.chatRequest = null;
    if ($("#send")) $("#send").disabled = false;
    loadChats();
  }
}

// =================================================================== KONU ARAMASI
async function viewSearch(q) {
  setCrumbs([{ label: "Keşfet", href: "#/" }, { label: "Konu araması" }]);
  setView(`<div class="section-head"><div><h1>Konu araması</h1><p>OpenAlex, Crossref, Semantic Scholar, TR Dizin ve OpenAIRE (DergiPark, üniversite arşivleri) aynı anda taranır; aynı yayın tek satırda birleşir.</p></div></div>
    <form class="card quick-search" id="searchForm" style="margin-top:0">
      <div class="input">${icon("search")}<input id="sInput" value="${esc(q)}" placeholder="ör. göğüs hastalıkları, makine öğrenmesi, deprem mühendisliği"></div>
      <button class="btn primary" type="submit">Ara</button></form>
    <div id="sResults" style="margin-top:18px"></div>`);
  $("#searchForm").addEventListener("submit", (e) => {
    e.preventDefault(); const v = $("#sInput").value.trim();
    if (v.length >= 3) location.hash = `#/ara?q=${encodeURIComponent(v)}`;
  });
  if (!q) {
    $("#sResults").innerHTML = emptyState("search", "Bir konu yazın", "Türkçe yazdığınız konu İngilizceye de çevrilerek aranır.");
    hydrateIcons($("#sResults")); $("#sInput").focus(); return;
  }
  const box = $("#sResults");
  box.innerHTML = `<div class="card"><div class="loading-line"><span class="spinner"></span>Akademik kaynaklar taranıyor…</div>${skeleton(6)}</div>`;
  let r;
  try { r = await api(`/api/search?q=${encodeURIComponent(q)}`); } catch (e) { box.innerHTML = `<div class="notice err">${icon("info")}<div>${esc(e.message)}</div></div>`; hydrateIcons(box); return; }
  if (location.hash !== `#/ara?q=${encodeURIComponent(q)}`) return;
  const all = r.papers;
  box.innerHTML = `
    <div class="src-status">${Object.entries(r.sources).map(([k, v]) => `<span class="chip ${typeof v === "number" ? "teal" : "gold"}">${esc(k)}: ${typeof v === "number" ? v + " sonuç" : esc(v)}</span>`).join("")}
      ${r.english ? `<span class="chip blue">EN: ${esc(r.english)}</span>` : ""}<span class="chip">${r.elapsed} sn</span></div>
    <div class="toolbar"><div class="input">${icon("search")}<input id="sFilter" placeholder="Sonuçlarda süz"></div>
      <select class="select" id="sSort"><option value="rel">En ilgili</option><option value="year">En yeni</option><option value="cites">En çok atıf</option></select>
      ${exportButtons("search")}</div>
    <div class="card" id="sList"></div>`;
  hydrateIcons(box);
  const draw = () => {
    const f = fold($("#sFilter").value), sort = $("#sSort").value;
    let list = all.filter((p) => !f || fold(`${p.title} ${(p.authors || []).join(" ")} ${p.venue || ""}`).includes(f));
    if (sort === "year") list = [...list].sort((a, b) => (b.year || 0) - (a.year || 0));
    if (sort === "cites") list = [...list].sort((a, b) => (b.citations || 0) - (a.citations || 0));
    S.lists.search = list;
    S.listMeta.search = { file: `arama ${q}` };
    $("#sList").innerHTML = list.length ? `<div class="stagger">${list.map((p, i) => paperCard(p, {}, i)).join("")}</div>`
      : emptyState("search", "Sonuç yok", "Farklı bir ifade deneyin.");
    hydrateIcons($("#sList"));
  };
  $("#sFilter").oninput = draw; $("#sSort").onchange = draw; draw();
}

// =================================================================== FAVORİLER, ÜNİVERSİTELER
async function viewFavPapers() {
  setCrumbs([{ label: "Kütüphanem" }, { label: "Favori makaleler" }]);
  await loadFav();
  const list = [...S.fav.papers].reverse();
  S.lists.fav = list;
  S.listMeta.fav = { file: "favori makaleler" };
  setView(`<div class="section-head"><div><h1>Favori makaleler</h1><p>${list.length} makale kaydedildi.</p></div>
      <div class="actions">${list.length ? exportButtons("fav") : ""}</div></div>
    <div class="card">${list.length ? `<div class="stagger">${list.map((p, i) => paperCard(p, p.job_id && p.pid ? { jid: p.job_id, pid: p.pid, person: p.person } : {}, i)).join("")}</div>`
      : emptyState("bookmark", "Henüz favori makale yok", "Yayın listelerinde ☆ simgesine tıklayarak makaleleri buraya ekleyin.")}</div>`);
}

async function viewFavPeople() {
  setCrumbs([{ label: "Kütüphanem" }, { label: "Favori akademisyenler" }]);
  await loadFav();
  const list = [...S.fav.people].reverse();
  setView(`<div class="section-head"><div><h1>Favori akademisyenler</h1><p>${list.length} akademisyen.</p></div></div>
    ${list.length ? `<div class="collabs stagger">${list.map((p, i) => `<div class="collab" style="--i:${i};cursor:pointer" data-chat="${esc(p.chat_id || "")}">
      ${avatar(p.name, p.photo)}<div class="c-main"><div class="c-title">${esc(p.title || "")}</div><b>${esc(p.name)}</b>
      <span>${esc(p.institution || "")}</span><span class="faint">${esc(p.department || "")}</span>
      <div class="chips" style="margin-top:8px"><span class="chip">${fmtNum(p.papers)} yayın</span>
        <button class="chip" data-unfav="${esc(p.key)}" type="button">${icon("x")}Çıkar</button></div></div></div>`).join("")}</div>`
      : `<div class="card">${emptyState("users", "Henüz favori akademisyen yok", "Bir profil sayfasında “Favorilere ekle” düğmesini kullanın.")}</div>`}`);
}

async function viewUnis() {
  setCrumbs([{ label: "Keşfet", href: "#/" }, { label: "Üniversiteler" }]);
  setView(`<div class="section-head"><div><h1>Üniversiteler</h1><p>Keşfedilen kurum dizinleri ve incelenen akademisyenlerin kurumları.</p></div>
      <div class="actions"><a class="btn primary" href="#/">${icon("plus")}Yeni üniversite</a></div></div><div id="uBody">${skeleton(4)}</div>`);
  let u;
  try { u = await api("/api/universities"); } catch (e) { $("#uBody").textContent = e.message; return; }
  $("#uBody").innerHTML = `
    ${u.directory.length ? `<div class="grid-3 stagger">${u.directory.map((x, i) => `<div class="card org-head" style="--i:${i};cursor:pointer;margin:0" data-org="${esc(x.home || "https://" + x.domain)}">
        <div class="org-logo">${icon("building")}</div><div style="min-width:0"><h3 style="font-size:15px">${esc(x.name)}</h3>
        <div class="meta"><span>${esc(x.domain)}</span></div>
        <div class="chips" style="margin-top:8px"><span class="chip blue">${x.faculties} fakülte</span><span class="chip teal">${x.departments} bölüm</span><span class="chip gold">${x.people} akademisyen</span></div></div></div>`).join("")}</div>`
      : `<div class="card">${emptyState("building", "Henüz kurum dizini yok", "Keşfet sayfasına bir üniversite bağlantısı girin.", `<a class="btn primary" href="#/">Keşfet</a>`)}</div>`}
    ${u.from_profiles.length ? `<h3 style="margin:28px 0 12px">İncelenen akademisyenlerin kurumları</h3><div class="stack">${u.from_profiles.map((g) => `
      <div class="card card-pad"><div class="card-title">${icon("building")}${esc(g.institution)}<span class="spacer"></span><span class="count">${g.people.length}</span></div>
      <div class="chips">${g.people.map((p) => `<button class="chip" data-chat="${esc(p.chat_id)}" type="button">${icon("user")}${esc(p.name)}</button>`).join("")}</div></div>`).join("")}</div>` : ""}`;
  hydrateIcons($("#uBody"));
}

// =================================================================== FİRMALAR
// Sanayi ve Teknoloji Bakanlığı Ar-Ge / Tasarım Merkezi listesindeki firmalar ve onlarla çalışan akademisyenler.
async function viewFirms(q = "", sector = "", city = "") {
  setCrumbs([{ label: "Keşfet", href: "#/" }, { label: "Firmalar" }]);
  setView(`<div class="section-head"><div><h1>Firmalar</h1><p>Resmi Ar-Ge ve Tasarım Merkezi olan firmalar. Bir firma seçin, onunla çalışan akademisyenleri görün.</p></div></div>
    <div class="toolbar"><div class="input">${icon("search")}<input id="firmQ" placeholder="Firma adı (ör. Aselsan, Arçelik)" value="${esc(q)}"></div>
      <select class="select" id="firmSector"><option value="">Tüm sektörler</option></select>
      <select class="select" id="firmCity"><option value="">Tüm iller</option></select></div>
    <div id="fBody">${skeleton(4)}</div>`);
  let timer;
  const load = async () => {
    const qs = new URLSearchParams({ q: $("#firmQ").value.trim(), sector: $("#firmSector").value, city: $("#firmCity").value });
    history.replaceState(null, "", `#/firmalar?${qs}`);
    let d;
    try { d = await api(`/api/firms?${qs}`); } catch (e) { $("#fBody").textContent = e.message; return; }
    if (!d.available) {
      $("#fBody").innerHTML = `<div class="card">${emptyState("briefcase", "Ar-Ge merkezi listesi yüklenmemiş",
        "Bakanlığın Excel listelerini indirip scripts/import_arge.py ile data/arge_merkezleri.json dosyasını oluşturun.")}</div>`;
      return;
    }
    const fill = (sel, values, cur) => { if (sel.options.length > 1) return; sel.insertAdjacentHTML("beforeend", values.map((v) => `<option ${v === cur ? "selected" : ""}>${esc(v)}</option>`).join("")); };
    fill($("#firmSector"), d.sectors, sector); fill($("#firmCity"), d.cities, city);
    $("#fBody").innerHTML = `<p class="faint" style="margin:0 0 12px">${fmtNum(d.count)} firma${d.count > d.items.length ? `, ilk ${d.items.length} gösteriliyor` : ""} · toplam ${fmtNum(d.total)} firma, ${fmtNum(d.info.count)} merkez · liste ${esc(d.info.imported || "")}</p>
      ${d.items.length ? `<div class="grid-3 stagger">${d.items.map((x, i) => `<a class="card org-head" style="--i:${i};margin:0;color:inherit;text-decoration:none" href="#/firma/${esc(x.id)}">
        <div class="org-logo">${icon("briefcase")}</div><div style="min-width:0"><h3 style="font-size:15px">${esc(x.name)}</h3>
        <div class="meta"><span>${esc(x.sectors.join(", "))}</span></div>
        <div class="chips" style="margin-top:8px"><span class="chip teal">${x.centers.length} merkez</span><span class="chip">${esc(x.cities.slice(0, 2).join(", "))}${x.cities.length > 2 ? "…" : ""}</span>
          ${x.profiles ? `<span class="chip gold">${icon("user")}${x.profiles} profil</span>` : ""}${x.academics ? `<span class="chip blue">${x.academics} akademisyen</span>` : ""}</div></div></a>`).join("")}</div>`
        : `<div class="card">${emptyState("search", "Firma bulunamadı", "Aramayı ya da filtreleri değiştirin.")}</div>`}`;
    hydrateIcons($("#fBody"));
  };
  $("#firmQ").oninput = () => { clearTimeout(timer); timer = setTimeout(load, 250); };
  $("#firmSector").onchange = load; $("#firmCity").onchange = load;
  load();
}

async function viewFirm(fid, refresh = false) {
  setCrumbs([{ label: "Keşfet", href: "#/" }, { label: "Firmalar", href: "#/firmalar" }, { label: "…" }]);
  setView(`<div id="firmHead">${skeleton(1)}</div><div class="card card-pad"><div class="loading-line"><span class="spinner"></span>
    OpenAlex ve TR Dizin'de firmayla ortak yayınlar taranıyor, profiller kontrol ediliyor…</div>${skeleton(3)}</div>`);
  let d;
  try { d = await api(`/api/firms/${encodeURIComponent(fid)}${refresh ? "?refresh=1" : ""}`); }
  catch (e) { setView(`<div class="card">${emptyState("briefcase", "Firma açılamadı", esc(e.message))}</div>`); return; }
  const f = d.firm;
  setCrumbs([{ label: "Keşfet", href: "#/" }, { label: "Firmalar", href: "#/firmalar" }, { label: f.name }]);
  const people = d.academics;
  const paperRow = (x) => `<div class="variants">${safeUrl(x.url) ? `<a href="${esc(safeUrl(x.url))}" target="_blank" rel="noopener">${esc(x.title)}</a>` : esc(x.title)}
    · ${esc(x.year || "?")} · ${esc(x.source)}${x.role ? ` · ${esc(x.role)}` : ""}${x.firm_people?.length ? ` · <span class="faint">firmadan: ${esc(x.firm_people.join(", "))}</span>` : ""}
    ${x.quote ? `<div class="faint" style="font-style:italic;margin-top:2px">“${esc(x.quote)}”</div>` : ""}</div>`;
  setView(`<section class="card org-head"><div class="org-logo">${icon("briefcase")}</div><div style="min-width:0;flex:1">
      <h1>${esc(f.name)}</h1><div class="meta"><span>${esc(f.sectors.join(", "))}</span><span>${esc(f.cities.join(", "))}</span></div>
      <div class="chips" style="margin-top:8px">${f.kinds.map((k) => `<span class="chip teal">✓ ${esc(k)}</span>`).join("")}</div>
      <details style="margin-top:10px"><summary class="faint" style="cursor:pointer">${f.centers.length} kayıtlı merkez</summary>
        <ul style="margin:8px 0 0;padding-left:18px">${f.centers.map((c) => `<li class="faint">${esc(c)}</li>`).join("")}</ul></details></div>
      <button class="btn" id="firmRefresh" type="button">${icon("refresh")}Yeniden tara</button></section>
    ${d.errors.map((e) => `<div class="notice warn" style="margin-bottom:14px">${icon("info")}<div>${esc(e)}. Sonuç eksik olabilir; bu sonuç saklanmadı, sonra tekrar açın.</div></div>`).join("")}
    <div class="stat-row"><div class="stat"><b>${fmtNum(people.length)}</b><span>akademisyen</span></div>
      <div class="stat"><b>${fmtNum(d.papers)}</b><span>ortak yayın ve proje</span></div>
      <div class="stat"><b>${Object.entries(d.by_source).map(([k, v]) => `${esc(k)} ${v}`).join(" · ") || "—"}</b><span>kaynak · ${esc(d.updated)}</span></div></div>
    <div class="tabs" role="tablist"><button class="tab active" data-tab="people" type="button">Akademisyenler<span class="n">${fmtNum(people.length)}</span></button>
      <button class="tab" data-tab="tubitak" type="button">TÜBİTAK<span class="n" id="tubitakN">${fmtNum(d.ardeb.length)}</span></button></div>
    <div class="panel" data-panel="tubitak"><div class="stack">
      <div class="card card-pad" id="teydebBox"><div class="card-title">${icon("briefcase")}TÜBİTAK TEYDEB projeleri</div>
        <div class="loading-line"><span class="spinner"></span>PRODİS'ten firmanın tamamlanmış sanayi Ar-Ge projeleri alınıyor (site yavaş, ~30 sn)…</div></div>
      <div class="card card-pad"><div class="card-title">${icon("cap")}TÜBİTAK ARDEB projeleri<span class="spacer"></span><span class="count">${d.ardeb.length}</span><span class="badge trdizin">TR Dizin</span></div>
        <p class="muted" style="margin:0 0 6px">Üniversitelerin yürüttüğü, özetinde firmanın iş birliği ifadesiyle (paydaş, ortak, birlikte…) geçtiği projeler.</p>
        ${d.ardeb.map((x) => `<div class="thesis"><b>${esc(x.title)}</b><div class="chips"><span class="chip">${esc(x.year || "")}</span>${x.group ? `<span class="chip">${esc(x.group)}</span>` : ""}${x.number ? `<span class="chip">No ${esc(x.number)}</span>` : ""}
          ${x.team.map((m) => `<span class="chip ${m.role === "Yürütücü" ? "blue" : ""}">${icon("user")}${esc(m.name)} · ${esc(m.role)}</span>`).join("")}
          ${safeUrl(x.url) ? `<a class="chip" href="${esc(safeUrl(x.url))}" target="_blank" rel="noopener">TR Dizin ${icon("external")}</a>` : ""}</div>
          <div class="faint" style="font-style:italic;margin-top:6px">“${esc(x.quote)}”</div></div>`).join("") || `<p class="faint" style="margin:0">Özetinde bu firmanın iş birliği olarak geçtiği ARDEB projesi bulunamadı.</p>`}</div>
    </div></div>
    <div class="panel active" data-panel="people">
    ${people.length ? `<div class="toolbar"><div class="input">${icon("search")}<input id="firmPeopleQ" placeholder="Akademisyen ya da üniversite ara"></div></div>
      <div class="stack" id="firmPeople">${people.map((p, i) => `<div class="card card-pad" data-fold="${esc(fold(p.name + " " + p.institution))}">
        <div class="collab" style="padding:0;border:0;box-shadow:none;background:none">${avatar(p.name, "")}<div class="c-main">
          ${p.title ? `<div class="c-title">${esc(p.title)}</div>` : ""}<b>${esc(p.name)}</b><span>${esc(p.institution || "Kurum bilinmiyor")}</span>
          <div class="chips" style="margin-top:8px">${p.sources.map((s) => `<span class="chip ${s === "Profil" ? "gold" : "blue"}">${esc(s)}</span>`).join("")}
            ${p.papers.length ? `<span class="chip">${p.papers.length} kanıt</span>` : ""}
            ${p.chat_id ? `<button class="chip teal" data-chat="${esc(p.chat_id)}" type="button">${icon("user")}Profili aç</button>`
              : `<button class="chip" data-newperson="${esc(p.name)}" type="button">${icon("sparkle")}Profil çıkar</button>`}</div></div></div>
        ${p.evidence.map((e) => `<div class="variants"><b style="display:inline;font-size:inherit">${esc(e.type)}:</b> ${esc(e.text)}</div>`).join("")}
        ${p.papers.slice(0, 3).map(paperRow).join("")}
        ${p.papers.length > 3 ? `<details><summary class="faint" style="cursor:pointer;margin-top:6px">${p.papers.length - 3} yayın daha</summary>${p.papers.slice(3).map(paperRow).join("")}</details>` : ""}
      </div>`).join("")}</div>`
      : `<div class="card">${emptyState("users", "Akademisyen bulunamadı",
        "Açık kaynaklarda bu firmayla ortak yayını olan akademisyen yok ya da firma yayınlarda farklı adla geçiyor. Gizli sözleşmeler ve yayına dönüşmeyen işler görünmez.")}</div>`}</div>`);
  $("#firmRefresh").onclick = () => viewFirm(fid, true);
  loadTeydeb(fid, refresh, d.ardeb.length);
  const pq = $("#firmPeopleQ");
  if (pq) pq.oninput = () => { const q = fold(pq.value); $$("#firmPeople > [data-fold]").forEach((n) => { n.hidden = !!q && !n.dataset.fold.includes(q); }); };
}

// Firmanın TEYDEB projeleri ayrı istekle gelir (PRODİS yavaş); sayfa beklemeden açılır.
async function loadTeydeb(fid, refresh, nArdeb) {
  let t;
  try { t = await api(`/api/firms/${encodeURIComponent(fid)}/teydeb${refresh ? "?refresh=1" : ""}`); } catch (e) { t = { projects: [], error: e.message }; }
  const box = $("#teydebBox");
  if (!box || !location.hash.startsWith(`#/firma/${fid}`)) return;
  $("#tubitakN").textContent = fmtNum(nArdeb + t.projects.length);
  box.innerHTML = `<div class="card-title">${icon("briefcase")}TÜBİTAK TEYDEB projeleri<span class="spacer"></span><span class="count">${t.projects.length}</span><span class="badge">PRODİS</span></div>
    <p class="muted" style="margin:0 0 6px">Firmanın tamamlanmış sanayi Ar-Ge projeleri (TÜBİTAK Açık Bilim). Bu kayıtlarda proje ekibi ve üniversite ortağı yer almaz.</p>
    ${t.error ? `<div class="notice warn">${icon("info")}<div>${esc(t.error)}. Sonra tekrar deneyin.</div></div>` : ""}
    ${t.projects.map((x) => `<div class="thesis"><b>${esc(x.title)}</b><div class="chips"><span class="chip">${esc(x.start || "")} – ${esc(x.end || "")}</span>
        ${x.field ? `<span class="chip blue">${esc(x.field)}</span>` : ""}${x.rd_sector ? `<span class="chip">${esc(x.rd_sector)}</span>` : ""}</div>
      ${x.keywords.length ? `<div class="chips" style="margin-top:6px">${x.keywords.slice(0, 10).map((k) => `<span class="chip teal">${esc(k)}</span>`).join("")}</div>` : ""}
      ${x.summary ? `<details><summary>Proje özeti</summary><div class="abs">${esc(x.summary)}${x.aim ? `\n\nAmaç: ${esc(x.aim)}` : ""}</div></details>` : ""}</div>`).join("")
      || (t.error ? "" : `<p class="faint" style="margin:0">PRODİS'te bu firma adıyla tamamlanmış proje bulunamadı.</p>`)}`;
  hydrateIcons(box);
}

// =================================================================== site araçları
async function showRecipes() {
  const rows = await api("/api/recipes").catch(() => []);
  openModal(`<h2>Öğrenilen site tarifleri</h2><p class="muted">REA'nın keşfettiği gizli istekler; Scrapling bunları tarayıcısız tekrar oynatır.</p>
    <div class="stack" style="margin-top:16px">${rows.length ? rows.map((st) => `<div class="card card-pad"><div class="card-title">${icon("globe")}${esc(st.domain)}</div>
      ${Object.entries(st.replay).map(([k, r]) => `<div class="recon"><b>${esc(k)}</b>: ${esc(r.method)} ${esc(r.url)}<br>öğrenildi ${esc(r.learned_at)} · <span class="ev-ok">${r.hits} başarılı tekrar</span> · ${r.failures} kırılma</div>`).join("") || '<div class="faint">Tekrar oynatılabilir istek yok (sunucu HTML site).</div>'}
      <div class="recon">${st.pages.length} sayfa parmak izi · ${Object.keys(st.people).length} kişi hafızada</div>
      <div class="recon">${st.events.slice(-6).map((e) => `<div class="${/drift|fail/.test(e.kind) ? "ev-drift" : ""}">${esc(e.at)} · ${esc(e.kind)} · ${esc(e.detail)}</div>`).join("")}</div></div>`).join("")
      : emptyState("settings", "Henüz tarif yok", "Bir profil çıkarıldığında REA'nın öğrendikleri burada görünür.")}</div>`);
}
async function scanChanges() {
  openModal(`<h2>Değişiklik taraması</h2><div class="loading-line"><span class="spinner"></span>Bilinen sayfalar yoklanıyor; yapı değişen olursa REA yeniden öğrenecek…</div>`);
  const rows = await api("/api/recipes/check", { method: "POST" }).catch(() => []);
  openModal(`<h2>Değişiklik taraması</h2>${rows.length ? `<div class="tbl-wrap" style="margin-top:14px"><table class="tbl"><thead><tr><th>Sayfa</th><th>Benzerlik</th><th>Durum</th></tr></thead><tbody>${rows.map((r) =>
    `<tr><td style="word-break:break-all">${esc(r.url)}</td><td>${r.similarity != null ? Math.round(r.similarity * 100) + "%" : "—"}</td><td>${r.error ? `<span class="vb conflict">${esc(r.error)}</span>` : r.drift ? `<span class="vb conflict">Değişmiş${r.relearned ? " · REA yeniden öğrendi" : ""}</span>` : `<span class="vb ok">✓ değişmemiş</span>`}</td></tr>`).join("")}</tbody></table></div>`
    : emptyState("settings", "Öğrenilmiş site yok", "Önce bir profil çıkarın.")}`);
}

// =================================================================== yönlendirme ve olaylar
function route() {
  const [path, qs] = (location.hash || "#/").slice(1).split("?");
  const params = new URLSearchParams(qs || "");
  const parts = path.split("/").filter(Boolean);
  closeDrawer();
  if (parts[0] !== "profil") S.chatRequest?.abort();
  setNav({ ara: "ara", universiteler: "universiteler", kurum: "universiteler", firmalar: "firmalar", firma: "firmalar", "favori-makaleler": "favori-makaleler",
    "favori-akademisyenler": "favori-akademisyenler" }[parts[0]] || (parts.length ? "" : "home"));
  switch (parts[0]) {
    case "ara": return viewSearch(params.get("q") || "");
    case "kurum": return viewDirectory(params.get("u") || "");
    case "profil": return viewProfile(parts[1]);
    case "is": return viewJob(parts[1]);
    case "favori-makaleler": return viewFavPapers();
    case "favori-akademisyenler": return viewFavPeople();
    case "universiteler": return viewUnis();
    case "firmalar": return viewFirms(params.get("q") || "", params.get("sector") || "", params.get("city") || "");
    case "firma": return viewFirm(parts[1]);
    default: return viewHome();
  }
}

document.addEventListener("click", async (e) => {
  const t = e.target;
  const open = t.closest("[data-open]");
  if (open) { e.preventDefault(); openPaper(open.dataset.open); return; }
  const star = t.closest("[data-star]");
  if (star) { toggleStar(star); return; }
  const del = t.closest("[data-delchat]");
  if (del) {
    e.stopPropagation();
    if (!confirm("Bu arama ve profil sonucu kalıcı olarak silinsin mi?")) return;
    await api(`/api/chats/${del.dataset.delchat}`, { method: "DELETE" }).catch(() => {});
    if (del.dataset.delchat === S.chatId) { S.result = null; S.chatId = null; location.hash = "#/"; }
    loadChats(); return;
  }
  const unfav = t.closest("[data-unfav]");
  if (unfav) {
    e.stopPropagation();
    await api(`/api/favorites/people/${encodeURIComponent(unfav.dataset.unfav)}`, { method: "DELETE" }).catch(() => {});
    await loadFav(); viewFavPeople(); return;
  }
  const chat = t.closest("[data-chat]");
  if (chat && chat.dataset.chat) { location.hash = `#/profil/${chat.dataset.chat}`; return; }
  const np = t.closest("[data-newperson]");
  if (np) { newPersonModal("", np.dataset.newperson); return; }
  const org = t.closest("[data-org]");
  if (org) { location.hash = `#/kurum?u=${encodeURIComponent(org.dataset.org)}`; return; }
  const tab = t.closest("[data-tab]");
  if (tab) {
    $$(".tab").forEach((x) => x.classList.toggle("active", x === tab));
    $$(".panel").forEach((x) => x.classList.toggle("active", x.dataset.panel === tab.dataset.tab));
    if (tab.dataset.tab === "chat") setTimeout(() => $("#question")?.focus(), 60);
    return;
  }
  const tabgo = t.closest("[data-tabgo]");
  if (tabgo) { $(`.tab[data-tab="${tabgo.dataset.tabgo}"]`)?.click(); $(".tabs")?.scrollIntoView({ behavior: "smooth" }); return; }
  if (t.closest("[data-analyze]")) { runAnalysis(); return; }
  if (t.closest("[data-industry]")) { refreshIndustry(false); return; }
  const askBtn = t.closest("[data-ask]");
  if (askBtn) { ask(askBtn.dataset.ask); return; }
  const cite = t.closest("[data-pub]");
  if (cite) {
    $(`.tab[data-tab="pubs"]`)?.click();
    const row = document.getElementById(`pub-${cite.dataset.pub}`);
    if (row) { row.scrollIntoView({ behavior: "smooth", block: "center" }); row.classList.add("flash"); setTimeout(() => row.classList.remove("flash"), 1600); }
    return;
  }
  const exp = t.closest("[data-export]");
  if (exp) {
    const list = S.lists[exp.dataset.list] || [];
    if (!list.length) { toast("Dışa aktarılacak yayın yok."); return; }
    const meta = S.listMeta[exp.dataset.list] || {};
    const stem = fold(meta.file || exp.dataset.list).replace(/ /g, "-").slice(0, 60) || "akademik-iz";
    const name = `${stem}-yayinlar-${new Date().toISOString().slice(0, 10)}`;
    (exp.dataset.export === "csv" ? exportCsv : exportBib)(list, name, meta);
    return;
  }
  const up = t.closest("[data-unitpapers]");
  if (up) { e.stopPropagation(); openUnitPapers(up.dataset.unitpapers, +up.dataset.i); return; }
  if (t.closest("[data-facstaff]")) { const d = S.dir; selectDept(-1, d.data.items[d.fac].url); return; }
  const prof = t.closest("[data-profile]");
  if (prof) {
    const d = S.dir, person = d.staff.items[+prof.dataset.profile];
    startJob(d.staff.page || person.url, person.name); return;
  }
  const unit = t.closest(".unit");
  if (unit) { unit.dataset.unit === "fac" ? selectFaculty(+unit.dataset.i) : selectDept(+unit.dataset.i); return; }
  if (t.closest("[data-close]") || t.id === "modal" || t.closest("#modalClose")) { closeModal(); return; }
  if (t.closest("#drawerClose")) { closeDrawer(); return; }
});

document.addEventListener("input", (e) => {
  const f = e.target.dataset?.filter;
  if (!f) return;
  const q = fold(e.target.value);
  $$(`#${f} [data-q]`).forEach((el) => { el.style.display = !q || el.dataset.q.includes(q) ? "" : "none"; });
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape") { closeModal(); closeDrawer(); } });
$("#newBtn").addEventListener("click", () => newPersonModal(S.dir?.staff?.page || ""));
$("#menuBtn").addEventListener("click", () => $("#app").classList.toggle("menu-open"));
$("#scrim").addEventListener("click", () => $("#app").classList.remove("menu-open"));
$("#recipesBtn").addEventListener("click", showRecipes);
$("#scanBtn").addEventListener("click", scanChanges);
$("#clearAll").addEventListener("click", async () => {
  if (!confirm("Tüm aramalar ve profil sonuçları silinsin mi? Favoriler korunur.")) return;
  await api("/api/chats", { method: "DELETE" }).catch(() => {});
  S.result = null; S.chatId = null; loadChats(); location.hash = "#/";
});
window.addEventListener("hashchange", route);

(async () => {
  hydrateIcons();
  const legacy = new URLSearchParams(location.search).get("chat");
  if (legacy) { history.replaceState(null, "", `/#/profil/${legacy}`); }
  loadEnv();
  await Promise.all([loadFav(), loadChats()]);
  route();
})();
