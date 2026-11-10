// Kütüphanenin HTML katmanları. Görünüm uygulamanın (style.css) modal, kart, düğme ve klasör tasarımını kullanır;
// 3B sahne bu modülü yalnızca açma fonksiyonları ve layersOpen() üzerinden kullanır.
import { cleanTitle, authorsLine, PALETTE } from "./library-covers.js?v=lib5";

export const $ = (s, root = document) => root.querySelector(s);
export const $$ = (s, root = document) => [...root.querySelectorAll(s)];
export const enc = encodeURIComponent;
export const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const fold = (s) => String(s || "").toLocaleLowerCase("tr").replace(/ı/g, "i").normalize("NFKD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]+/g, " ").trim();
export const orgId = (name) => fold(name).replace(/\s+/g, "-");
export const doiOf = (item) => String(item?.doi || "").replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, "").trim();
export const number = (n) => Number(n || 0).toLocaleString("tr-TR");
export const calm = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
export const titleOf = (item) => cleanTitle(item?.kind === "person" ? item.name : item?.name_tr || item?.title || item?.name || "Başlıksız yayın");
export const safeUrl = (u) => { if (!u || typeof u !== "string") return ""; try { const x = new URL(u, location.href); return ["http:", "https:"].includes(x.protocol) ? x.href : ""; } catch { return ""; } };
const sourceUrl = (item) => safeUrl(item.url) || (doiOf(item) ? `https://doi.org/${doiOf(item)}` : "");
const initials = (n) => String(n || "?").replace(/(prof|doç|doc|dr|öğr|ogr|üyesi|gör|arş)\.?/gi, "").split(/\s+/).filter(Boolean).slice(0, 2).map((x) => x[0]).join("").toLocaleUpperCase("tr");
const EASE = "cubic-bezier(.22,.9,.24,1)";
const APP = (hash) => `/${hash}`; // uygulama rotaları yeni sekmede açılır

const ICONS = {
  search: '<circle cx="11" cy="11" r="7.5"/><line x1="21" y1="21" x2="16.6" y2="16.6"/>',
  x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
  book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>',
  external: '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>',
  star: '<polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>',
  info: '<circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/>',
  sparkle: '<path d="M12 3l1.9 5.8L20 11l-6.1 2.2L12 19l-1.9-5.8L4 11l6.1-2.2z"/>',
  upload: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
  check: '<polyline points="20 6 9 17 4 12"/>',
  arrow: '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="13 6 19 12 13 18"/>',
  back: '<line x1="19" y1="12" x2="5" y2="12"/><polyline points="11 18 5 12 11 6"/>',
  flame: '<path d="M12 22c4 0 7-3 7-7 0-5-4-7-5-11-2 2-3 4-3 6-1-1-2-2-2-4-2 2-4 5-4 9 0 4 3 7 7 7z"/>',
  bookmark: '<path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>',
  clock: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
  users: '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
  map: '<path d="M21 10c0 7-9 13-9 13S3 17 3 10a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/>',
  list: '<line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><circle cx="3.5" cy="6" r="1"/><circle cx="3.5" cy="12" r="1"/><circle cx="3.5" cy="18" r="1"/>',
  building: '<path d="M3 21h18"/><path d="M5 21V10l7-5 7 5v11"/><path d="M9 21v-6h6v6"/><path d="M9 11h.01M15 11h.01"/>',
  monitor: '<rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/>',
  trash: '<polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>',
  file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/>',
};
export const icon = (name) => `<i data-icon="${name}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ""}</svg></i>`;
const avatar = (name, photo, cls = "av") => `<div class="${cls}">${esc(initials(name))}${photo ? `<img src="${esc(photo)}" alt="" loading="lazy" onerror="this.remove()">` : ""}</div>`;
const photoOf = (c) => (c?.job_id ? `/api/jobs/${enc(c.job_id)}/photo?v=2` : "");
const uniLogo = (name, cls = "org-logo") => {
  const id = orgId(name);
  const hue = [...String(name || "")].reduce((a, ch) => (a * 31 + ch.charCodeAt(0)) % 360, 11);
  return `<span class="${cls} organization-logo"><span class="logo-fallback" style="--h:${hue}">${esc(initials(name))}</span>${id ? `<img src="/static/logos/universities/${enc(id)}.png" alt="" loading="lazy" onload="this.parentNode.classList.add('has-logo')" onerror="this.remove()">` : ""}</span>`;
};

// ------------------------------------------------------------------ ağ ve bildirim
export async function api(path, { timeout = 20000, signal, ...options } = {}) {
  const signals = [AbortSignal.timeout(timeout)]; if (signal) signals.push(signal);
  const res = await fetch(path, { ...options, signal: AbortSignal.any(signals) });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `Sunucu yanıtı: ${res.status}`);
  }
  return res.json();
}
export function toast(html, ms = 4200) {
  const host = $("#toasts"); if (!host) return;
  const el = document.createElement("div"); el.className = "toast"; el.innerHTML = html; host.append(el);
  setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 320); }, ms);
}
async function readSse(res, onEvent, signal) {
  const reader = res.body.getReader(), dec = new TextDecoder(); let buf = "";
  const parse = (part) => part.split(/\r?\n/).filter((l) => l.startsWith("data:")).map((l) => l.slice(5).trimStart()).join("\n");
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) { buf += dec.decode(); break; }
      buf += dec.decode(value, { stream: true });
      const parts = buf.split(/\r?\n\r?\n/); buf = parts.pop();
      for (const part of parts) { const data = parse(part); if (data && !signal?.aborted && onEvent(JSON.parse(data)) === false) return; }
    }
    const tail = parse(buf); if (tail) onEvent(JSON.parse(tail));
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock(); }
}

// ------------------------------------------------------------------ ortak durum
export const store = { favorites: [], chats: [], onChange: () => {} };
const readStore = (key) => { try { const v = JSON.parse(localStorage.getItem(key) || "[]"); return Array.isArray(v) ? v : []; } catch { return []; } };
export function rememberPaper(item) {
  if (!item || item.kind === "person" || item.kind === "trend") return;
  const record = { at: Date.now(), title: titleOf(item) };
  for (const k of ["year", "venue", "doi", "url", "source", "citations", "id", "pdf", "topic", "is_oa", "category"]) if (item[k] !== undefined) record[k] = item[k];
  record.authors = (item.authors || []).slice(0, 6); record.abstract = String(item.abstract || "").slice(0, 1500);
  const list = readStore("academic-recent-papers").filter((p) => fold(p.title) !== fold(record.title));
  try { localStorage.setItem("academic-recent-papers", JSON.stringify([record, ...list].slice(0, 24))); } catch { /* depolama kapalı olabilir */ }
  store.onChange("recent");
}
const savedMatch = (item) => store.favorites.find((p) => (doiOf(p) && doiOf(p).toLowerCase() === doiOf(item).toLowerCase()) || fold(p.title) === fold(titleOf(item)));
async function toggleSave(item) {
  const saved = savedMatch(item);
  if (saved) {
    await api(`/api/favorites/papers/${enc(saved.key)}`, { method: "DELETE" });
    store.favorites = store.favorites.filter((p) => p.key !== saved.key);
    toast("Kaydettiklerinden çıkarıldı.");
  } else {
    const clean = { ...item, title: titleOf(item) }; delete clean.kind;
    const result = await api("/api/favorites/papers", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ item: clean }) });
    const record = result.item || result;
    if (record?.key) store.favorites.unshift({ ...clean, ...record, kind: "paper" });
    else store.favorites = ((await api("/api/favorites")).papers || []).map((p) => ({ ...p, kind: "paper" }));
    toast(`${icon("bookmark")}Kaydettiklerine eklendi; rafta da yerini aldı.`);
  }
  store.onChange("favorites");
}

// ------------------------------------------------------------------ katman yığını (Esc en üsttekini kapatır)
const layers = [];
export const layersOpen = () => layers.length > 0;
function pushLayer(close) { layers.push(close); }
function dropLayer(close) { const i = layers.lastIndexOf(close); if (i >= 0) layers.splice(i, 1); }
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape" || !layers.length) return;
  e.preventDefault(); e.stopImmediatePropagation(); layers[layers.length - 1]();
}, true);
function trapFocus(root, e) {
  if (e.key !== "Tab") return;
  const items = $$("button:not([disabled]), input:not([disabled]), select, textarea, a[href]", root).filter((x) => x.getClientRects().length);
  if (!items.length) return;
  const first = items[0], last = items[items.length - 1];
  if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
}

// ------------------------------------------------------------------ uygulama modalı (#modal, style.css)
let modalPrev = null, modalAbort = null, modalCloseHook = null;
const modal = () => $("#modal");
function closeModalNow() {
  const m = modal(); if (!m || m.hidden) return;
  modalAbort?.abort(); modalAbort = null;
  dropLayer(closeModalNow);
  const done = () => { m.hidden = true; m.classList.remove("closing"); const hook = modalCloseHook; modalCloseHook = null; hook?.(); if (modalPrev?.isConnected) modalPrev.focus({ preventScroll: true }); modalPrev = null; };
  if (calm()) { done(); return; }
  m.classList.add("closing"); setTimeout(done, 170);
}
export const closeModal = closeModalNow;
export function openModal(html, { wide = false, onClose = null } = {}) {
  const m = modal(), box = $(".modal-box", m), wasHidden = m.hidden;
  modalAbort?.abort(); modalAbort = new AbortController();
  if (wasHidden) { modalPrev = document.activeElement; pushLayer(closeModalNow); modalCloseHook = onClose; }
  else if (onClose) modalCloseHook = onClose;
  box.classList.toggle("lib-wide", wide);
  $("#modalBody").innerHTML = html;
  const title = $("h2", box); box.removeAttribute("aria-labelledby");
  if (title) { title.id ||= "modalTitle"; box.setAttribute("aria-labelledby", title.id); }
  m.classList.remove("closing"); m.hidden = false; box.scrollTop = 0;
  if (wasHidden && !calm()) box.animate([{ opacity: 0, transform: "translateY(14px) scale(.97)" }, { opacity: 1, transform: "none" }], { duration: 320, easing: EASE });
  else if (!calm()) $("#modalBody").animate([{ opacity: 0, transform: "translateX(10px)" }, { opacity: 1, transform: "none" }], { duration: 220, easing: EASE });
  requestAnimationFrame(() => { if (!m.hidden) $("input:not([disabled]), button:not(.modal-x)", box)?.focus({ preventScroll: true }); });
  return modalAbort.signal;
}
export function bindModalShell() {
  const m = modal();
  $("#modalClose", m).onclick = closeModalNow;
  m.addEventListener("pointerdown", (e) => { if (e.target === m) closeModalNow(); });
  m.addEventListener("keydown", (e) => trapFocus($(".modal-box", m), e));
}

// ------------------------------------------------------------------ makale modalı (uygulamadaki openPaper ile aynı düzen)
const SRC = { openalex: "OpenAlex", crossref: "Crossref", trdizin: "TR Dizin", semantic_scholar: "Semantic Scholar", yok: "YÖK", openaire: "OpenAIRE", wos: "WoS", scholar: "Scholar" };
function badges(item) {
  const list = item.sources || (item.source ? [item.source] : []);
  const out = list.map((s) => `<span class="badge ${esc(String(s).toLowerCase())}">${esc(SRC[String(s).toLowerCase()] || s)}</span>`);
  if (!out.length && /^W\d+$/.test(item.id || "")) out.push('<span class="badge openalex">OpenAlex</span>');
  if (item.is_oa || item.pdf) out.push('<span class="badge trdizin">Açık erişim</span>');
  return out.join("");
}
function paperRow(item, i) {
  const authors = authorsLine(item, 3), venue = cleanTitle(item.venue || item.source || "");
  return `<div class="paper lib-row" data-row="${i}" tabindex="0" role="button">
    <div class="p-body"><div class="p-title">${esc(titleOf(item))}</div>
      <div class="p-meta">${esc(authors)}${venue ? `${authors ? " · " : ""}<b>${esc(venue)}</b>` : ""}${item.year ? ` · ${esc(item.year)}` : ""}</div>
      ${item.abstract ? `<div class="p-abs">${esc(item.abstract)}</div>` : ""}
      ${item.reason ? `<div class="p-tags"><span class="chip blue">${icon("sparkle")}${esc(item.reason)}</span></div>` : ""}</div>
    <div class="p-side">${item.citations != null ? `<span class="lib-cites"><b>${number(item.citations)}</b> atıf</span>` : ""}${item.is_oa || item.pdf ? '<span class="chip teal">Açık erişim</span>' : ""}</div></div>`;
}
function bindRows(root, items, back, onPick = null) {
  $$("[data-row]", root).forEach((row) => {
    const go = () => (onPick ? onPick(items[+row.dataset.row]) : openPaper(items[+row.dataset.row], { back }));
    row.onclick = go; row.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } };
  });
}

export async function openPaper(item, { back = null } = {}) {
  if (!item) return;
  rememberPaper(item);
  const title = titleOf(item), saved = !!savedMatch(item), doi = doiOf(item);
  const signal = openModal(`${back ? `<button class="btn ghost sm lib-back" type="button" data-back>${icon("back")}${esc(back.label || "Geri")}</button>` : ""}
    <div class="m-kicker">${badges(item)}<span>${esc(item.year || "")}</span>${item.citations != null ? `<span>· ${number(item.citations)} atıf</span>` : ""}</div>
    <h2 class="m-title">${esc(title)}</h2>
    <div id="mMeta" class="muted">${esc(cleanTitle(item.venue || ""))}</div>
    ${item.reason ? `<div class="notice lib-why">${icon("sparkle")}<div><b>Neden bu?</b> ${esc(item.reason)}</div></div>` : ""}
    <div id="mAuthors">${authorsLine(item, 12) ? `<div class="m-h">Yazarlar</div><div class="muted">${esc(authorsLine(item, 12))}</div>` : ""}</div>
    <div class="m-h">Türkçe özet</div><div id="mSum" class="m-sum typing"></div>
    <div class="m-h">Özet (abstract)</div><div id="mAbs" class="m-abs muted">${item.abstract ? esc(item.abstract) : '<div class="loading-line"><span class="spinner"></span>Kaynak okunuyor…</div>'}</div>
    <div class="chips lib-links" id="mLinks">
      ${item.pdf || doi || item.archive ? `<button class="btn sm primary" type="button" data-pdf>${icon("book")}PDF oku</button>` : ""}
      ${item.source === "Bağış" ? "" : `<button class="btn sm ${saved ? "saved" : ""}" type="button" data-save aria-pressed="${saved}">${icon("star")}${saved ? "Kaydedildi" : "Kaydet"}</button>`}
      ${sourceUrl(item) ? `<a class="btn sm" href="${esc(sourceUrl(item))}" target="_blank" rel="noopener">${icon("external")}Kaynağa git</a>` : ""}
      <a class="btn sm ghost" href="${esc(APP(`#/ara?q=${enc(title)}`))}" target="_blank" rel="noopener">${icon("search")}Akademik İz'de aç</a>
    </div><div id="mStages" class="stages"></div>`, { wide: false });
  const body = $("#modalBody");
  $("[data-back]", body)?.addEventListener("click", () => back.open());
  $("[data-pdf]", body)?.addEventListener("click", () => openPdf(item));
  $("[data-save]", body)?.addEventListener("click", async (e) => {
    const btn = e.currentTarget; btn.disabled = true;
    try { await toggleSave(item); const on = !!savedMatch(item); btn.classList.toggle("saved", on); btn.setAttribute("aria-pressed", on); btn.innerHTML = `${icon("star")}${on ? "Kaydedildi" : "Kaydet"}`; }
    catch (err) { toast(esc(err.message)); } finally { btn.disabled = false; }
  });
  if (doi) loadAuthors(doi, signal);
  const sum = $("#mSum"), abs = $("#mAbs"), stages = $("#mStages");
  if (item.source === "Bağış" || item.archive) {
    sum.classList.remove("typing"); sum.textContent = item.note || "Bu kayıt arşiv katından; özet yerine kitabı açıp okuyabilirsin.";
    if (!item.abstract) abs.textContent = "Özet bilgisi yok."; return;
  }
  let text = "", failure = "";
  try {
    const paper = { title, doi, url: item.url || "", venue: item.venue || "", year: item.year || null, authors: (item.authors || []).map((a) => (typeof a === "string" ? a : a?.name || "")).filter(Boolean), abstract: item.abstract || "", citations: item.citations ?? null, source: item.source || "openalex", pdf: item.pdf || "" };
    const res = await fetch("/api/paper", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ paper }), signal: AbortSignal.any([signal, AbortSignal.timeout(210000)]) });
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${res.status}`); }
    await readSse(res, (m) => {
      if (signal.aborted) return false;
      if (m.stage) stages.insertAdjacentHTML("beforeend", `<div>› ${esc(m.stage)}</div>`);
      if (m.meta) {
        const d = m.meta;
        if (d.journal || d.date) $("#mMeta").textContent = [d.journal, d.date].filter(Boolean).join(" · ");
        if (d.abstract || d.tldr) abs.innerHTML = `${d.tldr ? `<div class="notice" style="margin-bottom:10px">${icon("sparkle")}<div><b>TL;DR:</b> ${esc(d.tldr)}</div></div>` : ""}${esc(d.abstract || item.abstract || "")}`;
        else if (!item.abstract) abs.textContent = "Bu kayıtta özet metni alınamadı.";
        const pdf = safeUrl(d.pdf); if (pdf) item.pdf ||= pdf;
        if (pdf && !$("[data-pdf]", body)) { $("#mLinks").insertAdjacentHTML("afterbegin", `<button class="btn sm primary" type="button" data-pdf>${icon("book")}PDF oku</button>`); $("[data-pdf]", body).onclick = () => openPdf(item); }
      }
      if (m.delta) { text += m.delta; sum.innerHTML = esc(text).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/\n/g, "<br>"); }
      if (m.error) failure = m.error;
      return m.done ? false : undefined;
    }, signal);
    if (failure) throw new Error(failure);
    if (!text) sum.textContent = "Özet metni bulunamadığı için Türkçe özet üretilmedi.";
  } catch (e) {
    if (signal.aborted) return;
    if (!text) sum.textContent = "Türkçe özet şu an üretilemedi.";
    if (!item.abstract && abs.querySelector(".spinner")) abs.textContent = "Özet alınamadı.";
    stages.insertAdjacentHTML("beforeend", `<div style="color:var(--warn)">${esc(e.name === "TimeoutError" ? "Bekleme süresi doldu." : e.message)}</div>`);
  } finally { sum.classList.remove("typing"); }
}
async function loadAuthors(doi, signal) {
  try {
    const d = await api(`/api/paper/authors?doi=${enc(doi)}`, { signal, timeout: 30000 });
    const host = $("#mAuthors"); if (!host?.isConnected || !d.items?.length) return;
    const tr = (a) => (a.institutions || []).some((i) => i.country === "TR") ? 0 : 1;
    const items = d.items.map((a, i) => ({ ...a, i })).sort((x, y) => tr(x) - tr(y) || x.i - y.i).slice(0, 12);
    host.innerHTML = `<div class="m-h">Yazarlar ve kurumları <small class="faint">${d.items.length} yazar</small></div><div class="m-authors">${items.map((a) => {
      const c = store.chats.find((x) => fold(x.name) === fold(a.name));
      const href = c ? APP(`#/profil/${enc(c.id)}`) : APP(`#/akademisyenler?q=${enc(a.name)}`);
      const insts = (a.institutions || []).map((i) => i.uni_id ? `<a class="m-inst tr" href="${esc(APP(`#/universite/${enc(i.uni_id)}`))}" target="_blank" rel="noopener">${esc(i.name)}</a>` : `<span class="m-inst">${esc(i.name)}</span>`).join("");
      return `<div class="m-author"><a class="m-author-name" href="${esc(href)}" target="_blank" rel="noopener">${avatar(a.name, c ? photoOf(c) : "", "av m-av")}<span>${esc(a.name)}</span>${c ? '<i class="chip teal">profil</i>' : ""}</a>${insts ? `<div class="m-insts">${insts}</div>` : ""}</div>`;
    }).join("")}</div>`;
  } catch { /* yazar ayrıntısı isteğe bağlı */ }
}

// ------------------------------------------------------------------ PDF okuyucu (uygulamadaki gibi kitap açılışı)
export async function openPdf(item) {
  const title = titleOf(item);
  const layer = document.createElement("div"); layer.className = "pdf-layer";
  layer.innerHTML = `<div class="pdf-scrim"></div><section class="pdf-reader" role="dialog" aria-modal="true" aria-label="PDF okuyucu">
    <header><span class="pdf-ic">${icon("book")}</span><b>${esc(title)}</b><span class="spacer"></span><a class="btn sm" target="_blank" rel="noopener" data-ext hidden>${icon("external")}Yeni sekmede aç</a>
      <button class="icon-btn" type="button" data-close aria-label="Kapat">${icon("x")}</button></header>
    <div class="pdf-body"><div class="loading-line"><span class="spinner"></span>PDF açılıyor; yayıncı kapattıysa açık erişim kopyası aranıyor…</div></div></section>`;
  document.body.append(layer);
  const reader = $(".pdf-reader", layer), body = $(".pdf-body", layer), ctrl = new AbortController();
  let objectUrl = "";
  const flip = (open) => [{ transformOrigin: "0% 50%", transform: open ? "perspective(1800px) rotateY(-80deg)" : "none", opacity: open ? 0 : 1 }, { transformOrigin: "0% 50%", transform: open ? "none" : "perspective(1800px) rotateY(-80deg)", opacity: open ? 1 : 0 }];
  if (!calm()) { reader.animate(flip(true), { duration: 640, easing: "cubic-bezier(.2,.8,.2,1)" }); $(".pdf-scrim", layer).animate([{ opacity: 0 }, { opacity: 1 }], { duration: 320 }); }
  const close = () => {
    dropLayer(close); ctrl.abort();
    const done = () => { if (objectUrl) URL.revokeObjectURL(objectUrl); layer.remove(); };
    if (calm()) { done(); return; }
    $(".pdf-scrim", layer).animate([{ opacity: 1 }, { opacity: 0 }], { duration: 300, fill: "forwards" });
    reader.animate(flip(false), { duration: 380, easing: "cubic-bezier(.5,0,.8,.4)", fill: "forwards" }).finished.then(done, done);
  };
  pushLayer(close);
  layer.addEventListener("click", (e) => { if (e.target.closest("[data-close]") || e.target.classList.contains("pdf-scrim")) close(); });
  try {
    const local = /^\/api\/library\/donations\/[a-f0-9]{32}\/pdf$/.test(item.pdf || "");
    const get = (url) => fetch(local ? item.pdf : `/api/pdf?url=${enc(safeUrl(url) || "")}&doi=${enc(doiOf(item))}`, { signal: AbortSignal.any([ctrl.signal, AbortSignal.timeout(120000)]) });
    let res = await get(item.pdf || "");
    if (!res.ok && !local) {
      const found = await api(`/api/library/resolve-pdf?doi=${enc(doiOf(item))}&url=${enc(sourceUrl(item))}`, { timeout: 90000, signal: ctrl.signal }).catch(() => ({}));
      if (found.pdf) res = await get(found.pdf);
    }
    if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.detail || "Bu yayının açık erişim PDF'i bulunamadı."); }
    const blob = await res.blob();
    if (!blob.type.includes("pdf")) throw new Error("Sunucu okunabilir bir PDF döndürmedi.");
    objectUrl = URL.createObjectURL(blob);
    if (!layer.isConnected) { URL.revokeObjectURL(objectUrl); return; }
    body.innerHTML = `<iframe class="pdf-frame" src="${objectUrl}" title="${esc(title)}"></iframe>`;
    const ext = $("[data-ext]", layer), src = safeUrl(res.headers.get("X-Source-Url") || item.pdf || "");
    if (src && !local) { ext.href = src; ext.hidden = false; }
    try { localStorage.setItem("akademik-okuma-devam", JSON.stringify({ ...item, title, at: Date.now() })); } catch { /* isteğe bağlı */ }
  } catch (e) {
    if (ctrl.signal.aborted || !layer.isConnected) return;
    const landing = sourceUrl(item);
    body.innerHTML = `<div class="pdf-fail">${icon("info")}<h3>PDF açılamadı</h3><p>${esc(e.message)}</p>${landing ? `<a class="btn primary" href="${esc(landing)}" target="_blank" rel="noopener">${icon("external")}Yayıncı sayfasına git</a>` : ""}</div>`;
  }
}

// ------------------------------------------------------------------ raf listesi ve gündem konusu
export function openList({ title, subtitle = "", emblem = "book", items = [], empty = "Bu raf henüz boş.", onPick = null }) {
  const reopen = () => openList({ title, subtitle, emblem, items, empty, onPick });
  openModal(`<div class="modal-heading"><span class="modal-emblem">${icon(emblem)}</span><div><h2>${esc(title)}</h2><p class="muted">${esc(subtitle || `${items.length} içerik · okumak için seç`)}</p></div></div>
    ${items.length ? `<div class="card lib-list">${items.map(paperRow).join("")}</div>` : `<div class="empty"><div class="em-icon">${icon(emblem)}</div><h3>${esc(title)}</h3><p>${esc(empty)}</p></div>`}`, { wide: true });
  bindRows($("#modalBody"), items, { label: title, open: reopen }, onPick);
}

export async function openTopic(topic) {
  const name = cleanTitle(topic.name_tr || topic.name || "Konu");
  const reopen = () => openTopic(topic);
  const signal = openModal(`<div class="m-kicker"><span class="badge openalex">Türkiye gündemi</span>${topic.growth != null ? `<span class="chip teal lib-growth">${icon("flame")}+%${number(topic.growth)}</span>` : ""}${topic.count ? `<span>· son 12 ayda ${number(topic.count)} yayın</span>` : ""}</div>
    <h2 class="m-title">${esc(name)}</h2>${topic.name && topic.name !== name ? `<div class="muted">${esc(topic.name)}</div>` : ""}
    ${topic.reason ? `<div class="notice lib-why">${icon("sparkle")}<div><b>Neden bu?</b> ${esc(topic.reason)}</div></div>` : ""}
    <div class="m-h">Türkiye adresli son yayınlar</div><div id="topicList"><div class="loading-line"><span class="spinner"></span>OpenAlex'ten getiriliyor…</div></div>
    <div class="chips lib-links"><a class="btn sm" href="${esc(APP(`#/ara?q=${enc(name)}`))}" target="_blank" rel="noopener">${icon("search")}Akademik İz'de bu konuyu ara</a></div>`, { wide: true });
  try {
    const r = await api(topic.id ? `/api/topic-works?id=${enc(topic.id)}` : `/api/topic-works?q=${enc(name)}`, { timeout: 90000, signal });
    const items = (r.items || []).map((x) => ({ ...x, kind: "paper" }));
    const host = $("#topicList"); if (!host?.isConnected) return;
    host.innerHTML = items.length ? `${r.scope === "world" ? '<p class="faint">Türkiye adresli yayın az; dünya geneli gösteriliyor.</p>' : ""}<div class="card lib-list">${items.map(paperRow).join("")}</div>` : '<p class="muted">Bu konuda yayın bulunamadı.</p>';
    bindRows(host, items, { label: name, open: reopen });
  } catch (e) { if (!signal.aborted) $("#topicList").innerHTML = `<p class="muted">${esc(e.message)}</p>`; }
}

// ------------------------------------------------------------------ masa bilgisayarı: konu bulucu
export function openPc({ onClose }) {
  const layer = document.createElement("div"); layer.className = "lib-pc-layer";
  const recent = readStore("academic-recent-views").filter((x) => x.kind === "topic").slice(0, 6);
  layer.innerHTML = `<section class="lib-monitor" role="dialog" aria-modal="true" aria-labelledby="pcTitle">
    <div class="lib-monitor-screen">
      <header class="lib-os"><img src="/static/brand-mark.svg" alt=""><b>Akademik İz</b><span>Konu bulucu</span><span class="spacer"></span><button class="btn sm" type="button" data-close>${icon("x")}Bilgisayardan kalk</button></header>
      <div class="lib-os-body">
        <span class="eyebrow">KONU BULUCU</span><h1 id="pcTitle">Ne okumak istiyorsun?</h1>
        <p class="muted">Türkçe yazabilirsin; konu İngilizceye çevrilip OpenAlex'te aranır, en çok atıf alanlar önde gelir.</p>
        <form class="lib-search" data-form><div class="input">${icon("search")}<input name="q" autocomplete="off" placeholder="ör. deprem mühendisliği, makine öğrenmesi, göğüs hastalıkları" aria-label="Konu"></div><button class="btn primary" type="submit">Ara</button></form>
        ${recent.length ? `<div class="chips lib-recent">${recent.map((x) => `<button class="chip" type="button" data-q="${esc(x.name || x.id)}">${esc(x.name || x.id)}</button>`).join("")}</div>` : ""}
        <div data-results aria-live="polite"></div>
      </div></div><div class="lib-monitor-chin"></div></section>`;
  document.body.append(layer);
  const ctrl = { abort: null }, input = $("input", layer), results = $("[data-results]", layer);
  if (!calm()) $(".lib-monitor", layer).animate([{ opacity: 0, transform: "scale(.86)" }, { opacity: 1, transform: "none" }], { duration: 420, easing: EASE });
  const close = () => { dropLayer(close); ctrl.abort?.abort(); layer.remove(); onClose?.(); };
  pushLayer(close);
  layer.addEventListener("keydown", (e) => trapFocus(layer, e));
  $("[data-close]", layer).onclick = close;
  async function search(q) {
    q = q.trim(); if (q.length < 3) return;
    input.value = q; ctrl.abort?.abort(); ctrl.abort = new AbortController();
    results.innerHTML = '<div class="loading-line"><span class="spinner"></span>Aranıyor…</div>';
    try {
      const r = await api(`/api/topic-works?q=${enc(q)}`, { timeout: 90000, signal: ctrl.abort.signal });
      const items = (r.items || []).map((x) => ({ ...x, kind: "paper" }));
      results.innerHTML = items.length ? `${r.scope === "world" ? '<p class="faint">Türkiye adresli yayın az; dünya geneli gösteriliyor.</p>' : ""}<div class="card lib-list">${items.map(paperRow).join("")}</div>
        <p class="faint"><a href="${esc(APP(`#/ara?q=${enc(q)}`))}" target="_blank" rel="noopener">Akademik İz'de bütün kaynaklarda ara ${icon("arrow")}</a></p>` : '<p class="muted">Yayın bulunamadı.</p>';
      bindRows(results, items, null);
      const views = readStore("academic-recent-views").filter((x) => !(x.kind === "topic" && fold(x.name) === fold(q)));
      try { localStorage.setItem("academic-recent-views", JSON.stringify([{ kind: "topic", id: q, name: q, at: Date.now() }, ...views].slice(0, 30))); } catch { /* isteğe bağlı */ }
    } catch (e) { if (!ctrl.abort.signal.aborted) results.innerHTML = `<p class="muted">${esc(e.message)}</p>`; }
  }
  $("[data-form]", layer).onsubmit = (e) => { e.preventDefault(); search(input.value); };
  $$("[data-q]", layer).forEach((b) => { b.onclick = () => search(b.dataset.q); });
  setTimeout(() => input.focus(), 120);
}

// ------------------------------------------------------------------ bağış istasyonu
const CATEGORIES = { muhendislik: "Mühendislik", tip: "Tıp ve Sağlık", sosyal: "Sosyal Bilimler", temel: "Fen Bilimleri", sanat: "Sanat ve Edebiyat", tarih: "Tarih", egitim: "Eğitim", hukuk: "Hukuk ve Ekonomi", klasikler: "Klasikler", genel: "Genel" };
const STEPS = ["Dosya kontrol ediliyor", "Metin çıkarılıyor", "OCR", "Künye aranıyor", "Kategori atanıyor", "Rafa yerleştirildi"];
const tokens = () => { try { return JSON.parse(localStorage.getItem("akademik-bagis-tokenlari") || "{}") || {}; } catch { return {}; } };
const saveTokens = (v) => { try { localStorage.setItem("akademik-bagis-tokenlari", JSON.stringify(v)); } catch { /* isteğe bağlı */ } };
export function openDonation({ onScan, onDone }) {
  openModal(`<div class="modal-heading"><span class="modal-emblem">${icon("upload")}</span><div><h2>Bağış istasyonu</h2><p class="muted">PDF'ini bağışla; arşiv katında herkes okuyabilsin. Dosya bu sunucuda taranır, dışarı gönderilmez.</p></div></div>
    <form class="lib-donate" data-form novalidate>
      <label class="lib-drop" data-drop><input type="file" accept=".pdf,application/pdf" data-file hidden>
        <span class="lib-drop-ic">${icon("file")}</span><b data-drop-title>PDF'i buraya bırak ya da seç</b><small data-drop-sub>En fazla 40 MB · 300 sayfa · taranmış sayfalara yerel OCR</small></label>
      <div class="lib-fields">
        <div class="field lib-span"><label for="dTitle">Başlık</label><div class="input"><input id="dTitle" name="title" maxlength="500" placeholder="Dosyadan otomatik doldurulur"></div></div>
        <div class="field"><label for="dAuthors">Yazarlar</label><div class="input"><input id="dAuthors" name="authors" placeholder="Virgülle ayır"></div></div>
        <div class="field"><label for="dYear">Yıl</label><div class="input"><input id="dYear" name="year" inputmode="numeric" maxlength="4"></div></div>
        <div class="field lib-span"><label for="dCat">Kategori</label><select class="select" id="dCat" name="category"><option value="">Otomatik öner</option>${Object.entries(CATEGORIES).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select></div>
      </div>
      <ol class="lib-steps" data-steps hidden>${STEPS.map((s) => `<li>${icon("check")}<span>${s}</span></li>`).join("")}</ol><p class="faint" data-step-note></p>
      <div class="modal-footer"><button class="btn" type="button" data-cancel>Vazgeç</button><button class="btn primary" type="submit" data-submit disabled>${icon("upload")}Tara ve bağışla</button></div>
    </form><div data-mine></div>`);
  const body = $("#modalBody"), form = $("[data-form]", body), file = $("[data-file]", body), drop = $("[data-drop]", body), submit = $("[data-submit]", body);
  let selected = null, busy = false;
  const ready = () => { submit.disabled = busy || !selected; };
  const choose = (f) => {
    if (!f) return;
    if (!/\.pdf$/i.test(f.name) || f.size > 40 * 1024 * 1024) { toast("En fazla 40 MB boyutunda bir PDF seç."); return; }
    selected = f; drop.classList.add("has-file");
    $("[data-drop-title]", body).textContent = f.name; $("[data-drop-sub]", body).textContent = `${(f.size / 1048576).toFixed(1)} MB · değiştirmek için tıkla`;
    if (!form.elements.title.value) form.elements.title.value = f.name.replace(/\.pdf$/i, "").replace(/[_-]+/g, " ").trim();
    ready();
  };
  file.onchange = () => choose(file.files[0]);
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); choose(e.dataTransfer.files[0]); });
  $("[data-cancel]", body).onclick = closeModal;
  const mark = (step, note = "") => {
    const index = step.startsWith("OCR") ? 2 : Math.max(0, STEPS.findIndex((s) => step.startsWith(s)));
    $$("[data-steps] li", body).forEach((li, i) => { li.className = i < index ? "done" : i === index ? "active" : ""; });
    $("[data-step-note]", body).textContent = note || step;
  };
  form.onsubmit = async (e) => {
    e.preventDefault(); if (!selected || busy) return;
    busy = true; ready(); onScan?.(true); $("[data-steps]", body).hidden = false; mark("Dosya kontrol ediliyor");
    try {
      const data = new FormData(form); data.set("file", selected);
      const r = await api("/api/library/donations", { method: "POST", body: data, timeout: 180000 });
      const t = tokens(); t[r.id] = r.owner_token; saveTokens(t);
      for (let i = 0; i < 900; i++) {
        const job = await api(`/api/library/jobs/${enc(r.job_id)}`);
        if (!body.isConnected) break;
        mark(job.step || "", job.step);
        if (job.status === "error") throw new Error(job.step || "PDF işlenemedi.");
        if (job.status === "done") { $$("[data-steps] li", body).forEach((li) => { li.className = "done"; }); toast(`${icon("check")}Bağışın arşiv katında, ${esc(job.category_name || CATEGORIES[job.category] || "Genel")} rafında.`); onDone?.(r.id, job); break; }
        await new Promise((res) => setTimeout(res, 1000));
      }
    } catch (err) { $("[data-step-note]", body).textContent = err.message; toast(esc(err.message)); }
    finally { busy = false; onScan?.(false); ready(); mine(); }
  };
  async function mine() {
    const host = $("[data-mine]", body); if (!host) return;
    const t = tokens(), ids = Object.keys(t); if (!ids.length) { host.innerHTML = ""; return; }
    const rows = (await Promise.all(ids.map((id) => api(`/api/library/donations/${enc(id)}`).catch(() => null)))).filter(Boolean);
    if (!host.isConnected) return;
    host.innerHTML = rows.length ? `<div class="m-h">Bu tarayıcıdan bağışladıkların</div><div class="card lib-list">${rows.map((d) => `<div class="paper"><div class="p-body"><div class="p-title">${esc(d.title)}</div><div class="p-meta">${esc(CATEGORIES[d.category] || "Genel")} · ${esc(d.pages || "?")} sayfa${d.status && d.status !== "done" ? ` · ${d.status === "error" ? "işlenemedi" : "işleniyor"}` : ""}${d.ocr && d.ocr !== "none" ? ` · OCR: ${esc(d.ocr)}` : ""}</div></div><div class="p-side"><button class="btn sm ghost" type="button" data-remove="${esc(d.id)}">${icon("trash")}Kaldır</button></div></div>`).join("")}</div>` : "";
    $$("[data-remove]", host).forEach((b) => b.onclick = async () => {
      const id = b.dataset.remove, all = tokens();
      try { await api(`/api/library/donations/${enc(id)}`, { method: "DELETE", headers: { "X-Owner-Token": all[id] || "" } }); delete all[id]; saveTokens(all); onDone?.(); mine(); toast("Bağış kaldırıldı."); }
      catch (err) { toast(esc(err.message)); }
    });
  }
  mine();
}

// ------------------------------------------------------------------ akademisyen rehberi (AVM kat planı kiosku)
const BLOCK_COLORS = ["#2563eb", "#7c3aed", "#0d9488", "#db2777", "#ea580c", "#16a34a", "#0891b2", "#9333ea", "#ca8a04", "#dc2626", "#4f46e5", "#059669"];
// "Ankara University" ile "Ankara Üniversitesi" aynı kurum: anahtar Türkçe biçimden üretilir, Türkçe ad gösterilir.
const trInstitution = (name) => String(name || "").trim().replace(/^University of (.+)$/i, "$1 University").replace(/\bUniversity\b/gi, "Üniversitesi").replace(/\bTechnical\b/gi, "Teknik");
export const groupsOf = (people) => {
  const map = new Map();
  for (const c of people) {
    const key = orgId(trInstitution(c.institution)) || "_";
    if (!map.has(key)) map.set(key, { key, name: c.institution || "Kurumu bilinmeyen", items: [] });
    const g = map.get(key); g.items.push(c);
    if (/Üniversitesi/.test(c.institution || "") && !/Üniversitesi/.test(g.name)) g.name = c.institution;
  }
  return [...map.values()].sort((a, b) => b.items.length - a.items.length || a.name.localeCompare(b.name, "tr")).map((g, i) => ({ ...g, no: i + 1, color: BLOCK_COLORS[i % BLOCK_COLORS.length] }));
};
const interestsOf = (c) => [...new Map((c.interests || []).map((v) => String(v || "").replace(/\s+[0-9A-F]{16}$/, "").trim()).filter((s) => s.length > 2).map((x) => [fold(x), x])).values()];
const shortName = (name) => String(name).replace(/Üniversitesi/g, "Ünv.").replace(/Teknik/g, "Tek.").replace(/Enstitüsü/g, "Enst.");
let universityIds = null;
async function universityId(name) {
  try {
    universityIds ||= api("/api/universities", { timeout: 30000 }).then((r) => new Map((r.items || []).map((u) => [fold(u.name), u.id])));
    return (await universityIds).get(fold(name)) || "";
  } catch { universityIds = null; return ""; }
}

export function openKiosk(people) {
  const groups = groupsOf(people);
  const layer = document.createElement("div"); layer.className = "kiosk-layer";
  layer.innerHTML = `<div class="kiosk-scrim"></div><section class="kiosk-device" role="dialog" aria-modal="true" aria-label="Akademisyen rehberi">
    <div class="kiosk-camera"></div>
    <div class="kiosk-screen">
      <header class="kiosk-top"><img src="/static/brand-mark.svg" alt=""><div><b>AKADEMİSYEN REHBERİ</b><span>Akademik İz Kütüphanesi · Üst kat</span></div><span class="spacer"></span><time data-clock></time><button class="kiosk-x" type="button" data-close aria-label="Rehberi kapat">${icon("x")}</button></header>
      <div class="kiosk-search"><div class="input">${icon("search")}<input data-q placeholder="Akademisyen, üniversite veya ilgi alanı ara" aria-label="Rehberde ara"></div>
        <div class="kiosk-tabs" role="tablist">${[["plan", "map", "Kat planı"], ["folders", "grid", "Klasörler"], ["list", "list", "Liste"]].map(([k, ic, l]) => `<button type="button" role="tab" data-view="${k}">${icon(ic)}${l}</button>`).join("")}</div></div>
      <div class="kiosk-main">
        <aside class="kiosk-legend"><div class="kiosk-letters" data-letters></div><ol data-legend></ol></aside>
        <div class="kiosk-stage" data-stage></div>
      </div>
      <footer class="kiosk-foot">${icon("users")}${people.length} akademisyen · ${groups.length} kurum<span class="spacer"></span>Kuruma, kişiye ya da yayına dokun</footer>
      <div class="kiosk-idle" data-idle hidden><img src="/static/brand-mark.svg" alt=""><b>Akademisyen Rehberi</b><span>Başlamak için ekrana dokunun</span></div>
    </div></section>`;
  document.body.append(layer);
  const device = $(".kiosk-device", layer), stage = $("[data-stage]", layer), q = $("[data-q]", layer);
  let view = "plan", letter = "", idleTimer = 0, clockTimer = 0;
  if (!calm()) { device.animate([{ opacity: 0, transform: "translateY(40px) scale(.94)" }, { opacity: 1, transform: "none" }], { duration: 520, easing: EASE }); $(".kiosk-scrim", layer).animate([{ opacity: 0 }, { opacity: 1 }], { duration: 400 }); }
  const close = () => {
    dropLayer(close); clearTimeout(idleTimer); clearInterval(clockTimer);
    const done = () => layer.remove();
    if (calm()) { done(); return; }
    device.animate([{ opacity: 1, transform: "none" }, { opacity: 0, transform: "translateY(30px) scale(.95)" }], { duration: 300, easing: "ease-in", fill: "forwards" }).finished.then(done, done);
  };
  pushLayer(close);
  layer.addEventListener("keydown", (e) => trapFocus(device, e));
  $("[data-close]", layer).onclick = close;
  $(".kiosk-scrim", layer).onclick = close;
  const tick = () => { $("[data-clock]", layer).textContent = new Date().toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" }); };
  tick(); clockTimer = setInterval(tick, 20000);
  const idle = () => { clearTimeout(idleTimer); $("[data-idle]", layer).hidden = true; idleTimer = setTimeout(() => { if (layer.isConnected && !stage.querySelector(".kiosk-folder")) $("[data-idle]", layer).hidden = false; }, 60000); };
  layer.addEventListener("pointerdown", idle); layer.addEventListener("keydown", idle); idle();
  $("[data-idle]", layer).onclick = idle;

  const letters = [...new Set(groups.map((g) => g.name[0]?.toLocaleUpperCase("tr")).filter(Boolean))].sort((a, b) => a.localeCompare(b, "tr"));
  $("[data-letters]", layer).innerHTML = ["Tümü", ...letters].map((l) => `<button type="button" data-letter="${esc(l === "Tümü" ? "" : l)}">${esc(l)}</button>`).join("");
  $$("[data-letter]", layer).forEach((b) => b.onclick = () => { letter = b.dataset.letter; draw(); });
  $$("[data-view]", layer).forEach((b) => b.onclick = () => { view = b.dataset.view; draw(); });
  q.oninput = () => draw();

  const matches = (g) => {
    const query = fold(q.value);
    if (letter && g.name[0]?.toLocaleUpperCase("tr") !== letter) return false;
    if (!query) return true;
    return fold(`${g.name} ${g.items.map((c) => `${c.name} ${interestsOf(c).join(" ")}`).join(" ")}`).includes(query);
  };
  function draw() {
    const list = groups.filter(matches);
    $$("[data-view]", layer).forEach((b) => b.setAttribute("aria-selected", b.dataset.view === view));
    $$("[data-letter]", layer).forEach((b) => b.classList.toggle("on", b.dataset.letter === letter));
    $("[data-legend]", layer).innerHTML = list.map((g) => `<li><button type="button" data-group="${esc(g.key)}"><span class="kiosk-no" style="--c:${g.color}">${g.no}</span><span class="kiosk-lname">${esc(g.name)}</span><small>${g.items.length}</small></button></li>`).join("") || '<li class="kiosk-none">Eşleşen kurum yok</li>';
    if (!people.length) stage.innerHTML = `<div class="kiosk-empty">${icon("users")}<b>Rehber henüz boş</b><span>Uygulamada akademisyen inceledikçe burada kurum kurum listelenir.</span><a class="btn" href="${APP("#/akademisyenler")}" target="_blank" rel="noopener">Akademisyen ara</a></div>`;
    else if (view === "plan") drawPlan(list);
    else if (view === "folders") drawFolders(list);
    else drawPeopleList(list);
    $$("[data-group]", layer).forEach((b) => b.onclick = () => openGroup(groups.find((g) => g.key === b.dataset.group), b));
  }
  function drawPlan(list) {
    const span = (n) => (n >= 8 ? "big" : n >= 4 ? "mid" : n >= 2 ? "small" : "tiny");
    stage.innerHTML = `<div class="kiosk-plan"><div class="kiosk-floor-label">ÜST KAT · KURUMLAR</div><div class="kiosk-blocks">${list.map((g) => `<button type="button" class="kiosk-block ${span(g.items.length)}" data-group="${esc(g.key)}" style="--c:${g.color}">
        <span class="kiosk-no" style="--c:${g.color}">${g.no}</span>${uniLogo(g.name, "kiosk-logo")}<b>${esc(shortName(g.name))}</b><small>${g.items.length} akademisyen</small></button>`).join("") || '<p class="kiosk-none">Bu filtrede kurum yok.</p>'}</div></div>`;
  }
  function drawFolders(list) {
    stage.innerHTML = `<div class="folder-grid kiosk-folders">${list.map((g) => {
      const preview = g.items.slice(0, g.items.length > 9 ? 8 : 9), more = g.items.length - preview.length;
      return `<button type="button" class="folder" data-group="${esc(g.key)}" aria-label="${esc(g.name)}: ${g.items.length} profil"><span class="folder-box"><span class="folder-icons">${preview.map((c) => `<span class="fi-cell">${avatar(c.name, photoOf(c))}</span>`).join("")}${more > 0 ? `<span class="fi-cell fi-more">+${more}</span>` : ""}</span></span><span class="folder-label"><b>${esc(g.name)}</b></span></button>`;
    }).join("")}</div>`;
  }
  function drawPeopleList(list) {
    const query = fold(q.value);
    const rows = list.flatMap((g) => g.items.map((c) => ({ c, g }))).filter(({ c, g }) => !query || fold(`${c.name} ${g.name} ${interestsOf(c).join(" ")}`).includes(query)).sort((a, b) => a.c.name.localeCompare(b.c.name, "tr"));
    stage.innerHTML = `<div class="kiosk-rows">${rows.map(({ c, g }) => `<button type="button" class="kiosk-row" data-person="${esc(c.id)}">${avatar(c.name, photoOf(c))}<span><b>${esc(c.name)}</b><small>${esc(c.title || "")} · ${esc(g.name)}</small></span><span class="kiosk-no" style="--c:${g.color}">${g.no}</span></button>`).join("") || '<p class="kiosk-none">Eşleşen akademisyen yok.</p>'}</div>`;
    $$("[data-person]", stage).forEach((b) => b.onclick = () => { const c = people.find((x) => x.id === b.dataset.person); openPerson(c, groups.find((g) => g.items.includes(c))); });
  }
  function openGroup(g, origin) {
    if (!g) return;
    const block = $(`.kiosk-block[data-group="${CSS.escape(g.key)}"]`, stage);
    const panel = document.createElement("div"); panel.className = "kiosk-folder";
    panel.innerHTML = `<header>${uniLogo(g.name, "kiosk-logo lg")}<div class="fo-title"><h2>${esc(g.name)}</h2><span><span class="kiosk-no" style="--c:${g.color}">${g.no}</span> ${g.items.length} incelenen profil · kişiye dokun, yayınlarını gör</span></div>
      <div class="input slim">${icon("search")}<input placeholder="Bu klasörde ara" aria-label="Klasörde ara"></div><button class="kiosk-x" type="button" data-fclose aria-label="Klasörü kapat">${icon("x")}</button></header>
      <div class="kiosk-folder-body"><div class="pcard-grid" data-cards></div></div>`;
    stage.append(panel);
    const cards = $("[data-cards]", panel);
    const render = (list) => {
      cards.innerHTML = list.map((c) => `<button type="button" class="pcard" data-person="${esc(c.id)}">${avatar(c.name, photoOf(c), "av pcard-av")}<span class="pcard-name">${esc(c.name)}</span><span class="pcard-sub">${esc(c.title || "")}</span></button>`).join("") || '<p class="kiosk-none">Eşleşen akademisyen yok.</p>';
      $$("[data-person]", cards).forEach((b) => b.onclick = () => openPerson(g.items.find((c) => c.id === b.dataset.person), g));
    };
    render(g.items);
    $("input", panel).oninput = (e) => { const v = fold(e.target.value); render(g.items.filter((c) => !v || fold(`${c.name} ${interestsOf(c).join(" ")}`).includes(v))); };
    const src = (origin?.isConnected ? origin : block)?.getBoundingClientRect();
    if (src && !calm()) {
      const to = panel.getBoundingClientRect();
      panel.animate([{ transform: `translate(${src.left + src.width / 2 - (to.left + to.width / 2)}px, ${src.top + src.height / 2 - (to.top + to.height / 2)}px) scale(${Math.max(.05, src.width / to.width)}, ${Math.max(.05, src.height / to.height)})`, opacity: .5, borderRadius: "28px" }, { transform: "none", opacity: 1, borderRadius: "22px" }], { duration: 560, easing: EASE });
    }
    const closePanel = () => { dropLayer(closePanel); const end = () => panel.remove(); if (calm()) end(); else panel.animate([{ opacity: 1, transform: "none" }, { opacity: 0, transform: "scale(.92)" }], { duration: 220, fill: "forwards" }).finished.then(end, end); };
    pushLayer(closePanel);
    $("[data-fclose]", panel).onclick = closePanel;
  }
  async function openPerson(c, g) {
    if (!c) return;
    stage.querySelector(".kiosk-person")?.remove();
    const card = document.createElement("div"); card.className = "kiosk-person";
    const ints = interestsOf(c).slice(0, 6);
    card.innerHTML = `<button class="kiosk-x" type="button" data-pclose aria-label="Kapat">${icon("x")}</button>
      <header class="kp-head">${avatar(c.name, photoOf(c), "av kiosk-av")}<div><span class="kiosk-title">${esc(c.title || "")}</span><h2>${esc(c.name)}</h2>
        <p><span class="kiosk-no" style="--c:${g?.color || "#2563eb"}">${g?.no || "•"}</span>${esc(c.institution || "")}<span data-dept></span></p></div></header>
      ${ints.length ? `<div class="chips">${ints.map((x) => `<span class="chip">${esc(x)}</span>`).join("")}</div>` : ""}
      <div class="kp-stats" data-stats><span><b>${number(c.papers)}</b><small>yayın</small></span></div>
      <div class="kp-h">Son yayınlar</div>
      <div class="kp-pubs" data-pubs><div class="kp-loading"><span class="spinner"></span>Yayınlar yükleniyor…</div></div>
      <div class="kiosk-actions"><a class="btn primary" href="${esc(APP(`#/profil/${enc(c.id)}`))}" target="_blank" rel="noopener">${icon("external")}Profili aç</a><span data-uni></span></div>`;
    stage.append(card);
    if (!calm()) card.animate([{ opacity: 0, transform: "translateX(28px)" }, { opacity: 1, transform: "none" }], { duration: 360, easing: EASE });
    const closeCard = () => { dropLayer(closeCard); card.remove(); };
    pushLayer(closeCard);
    $("[data-pclose]", card).onclick = closeCard;
    universityId(c.institution).then((id) => {
      if (id && card.isConnected) $("[data-uni]", card).innerHTML = `<a class="btn" href="${esc(APP(`#/universite/${enc(id)}`))}" target="_blank" rel="noopener">${icon("building")}Üniversite sayfası</a>`;
    });
    const host = $("[data-pubs]", card);
    if (!c.job_id) { host.innerHTML = `<p class="kp-empty">Bu profilin yayın kaydı yok. Profili açıp tarayabilirsin.</p>`; return; }
    try {
      const r = await api(`/api/library/person/${enc(c.job_id)}?limit=14`);
      if (!card.isConnected) return;
      if (r.department) $("[data-dept]", card).textContent = ` · ${r.department}`;
      $("[data-stats]", card).innerHTML = [[r.total, "yayın"], [r.citations, "atıf"], [r.q1, "Q1 makale"], ...(r.kinds || []).slice(0, 1).map(([k, n]) => [n, k.toLocaleLowerCase("tr")])]
        .map(([n, l]) => `<span><b>${number(n)}</b><small>${esc(l)}</small></span>`).join("");
      const items = r.items || [];
      host.innerHTML = items.length ? items.map((p, i) => `<button type="button" class="kp-pub" data-pub="${i}"><span class="kp-year">${esc(p.year || "—")}</span><span class="kp-body"><b>${esc(cleanTitle(p.title))}</b>
          <small>${esc([cleanTitle(p.venue), p.kind].filter(Boolean).join(" · "))}</small></span><span class="kp-side">${p.quartile ? `<span class="kp-q kp-${esc(p.quartile.toLowerCase())}">${esc(p.quartile)}</span>` : ""}${p.citations ? `<small>${number(p.citations)} atıf</small>` : ""}</span></button>`).join("")
        + (r.total > items.length ? `<a class="kp-more" href="${esc(APP(`#/profil/${enc(c.id)}`))}" target="_blank" rel="noopener">Tüm ${number(r.total)} yayını profilde gör ${icon("arrow")}</a>` : "")
        : `<p class="kp-empty">Kayıtlı yayın bulunamadı.</p>`;
      $$("[data-pub]", host).forEach((b) => b.onclick = () => {
        const p = items[Number(b.dataset.pub)];
        openPaper({ title: p.title, doi: p.doi, url: p.url, venue: p.venue, year: p.year, authors: p.authors, citations: p.citations });
      });
    } catch (e) {
      if (card.isConnected) host.innerHTML = `<p class="kp-empty">${esc(e.message || "Yayınlar alınamadı.")}</p>`;
    }
  }
  draw();
  setTimeout(() => q.focus({ preventScroll: true }), 200);
}

// ------------------------------------------------------------------ arşiv okuyucu (eski kağıt)
export async function openArchiveReader(item, { onClose } = {}) {
  const title = cleanTitle(item.title || "Adsız kitap"), authors = authorsLine(item, 3);
  const layer = document.createElement("div"); layer.className = "archive-reader";
  layer.innerHTML = `<div class="ar-desk"></div><section class="ar-book" role="dialog" aria-modal="true" aria-label="${esc(title)}">
    <header class="ar-head"><div><b>${esc(title)}</b><span>${esc(authors)}${item.year ? ` · ${esc(item.year)}` : ""}</span></div>
      <span class="ar-pill">${esc(item.source || "Açık erişim")}</span>${item.license ? `<span class="ar-pill soft" title="${esc(item.license)}">${esc(String(item.license).slice(0, 40))}</span>` : ""}
      <span class="spacer"></span><button class="ar-btn" type="button" data-sepia aria-pressed="true">Sepya</button><a class="ar-btn" data-download hidden download>${icon("download")}İndir</a><button class="ar-btn" type="button" data-close>${icon("x")}Kapat</button></header>
    <div class="ar-pages" data-pages><div class="ar-loading"><span class="spinner"></span>Kitap raftan indiriliyor…</div></div>
    <footer class="ar-foot" data-foot hidden><button class="ar-btn" type="button" data-prev aria-label="Önceki sayfa">←</button><span data-page></span><button class="ar-btn" type="button" data-next aria-label="Sonraki sayfa">→</button></footer></section>`;
  document.body.append(layer);
  const book = $(".ar-book", layer), pages = $("[data-pages]", layer), ctrl = new AbortController();
  let objectUrl = "", textPages = [], page = 0, sepia = true;
  if (!calm()) book.animate([{ opacity: 0, transform: "perspective(1600px) rotateX(18deg) translateY(60px) scale(.9)" }, { opacity: 1, transform: "none" }], { duration: 620, easing: EASE });
  const close = () => {
    dropLayer(close); ctrl.abort();
    const done = () => { if (objectUrl) URL.revokeObjectURL(objectUrl); layer.remove(); onClose?.(); };
    if (calm()) { done(); return; }
    book.animate([{ opacity: 1, transform: "none" }, { opacity: 0, transform: "translateY(50px) scale(.94)" }], { duration: 320, easing: "ease-in", fill: "forwards" }).finished.then(done, done);
  };
  pushLayer(close);
  $("[data-close]", layer).onclick = close;
  $("[data-sepia]", layer).onclick = (e) => { sepia = !sepia; layer.classList.toggle("plain", !sepia); e.currentTarget.setAttribute("aria-pressed", sepia); e.currentTarget.textContent = sepia ? "Sepya" : "Normal"; };
  const show = (delta = 0) => {
    if (!textPages.length) return;
    page = Math.max(0, Math.min(textPages.length - 1, page + delta * 2));
    const left = textPages[page] || "", right = textPages[page + 1] || "";
    pages.innerHTML = `<article class="ar-page left"><div>${esc(left)}</div><span class="ar-no">${page + 1}</span></article><article class="ar-page right"><div>${esc(right)}</div><span class="ar-no">${right ? page + 2 : ""}</span></article>`;
    if (delta && !calm()) $(delta > 0 ? ".ar-page.right" : ".ar-page.left", pages).animate([{ transformOrigin: delta > 0 ? "0% 50%" : "100% 50%", transform: `perspective(1400px) rotateY(${delta > 0 ? 70 : -70}deg)`, opacity: .3 }, { transformOrigin: delta > 0 ? "0% 50%" : "100% 50%", transform: "none", opacity: 1 }], { duration: 420, easing: EASE });
    $("[data-page]", layer).textContent = `${page + 1}–${Math.min(page + 2, textPages.length)} / ${textPages.length}`;
  };
  $("[data-prev]", layer).onclick = () => show(-1); $("[data-next]", layer).onclick = () => show(1);
  layer.addEventListener("keydown", (e) => { if (e.key === "ArrowRight") show(1); if (e.key === "ArrowLeft") show(-1); });
  layer.tabIndex = -1; layer.focus();
  try {
    if (item.text_url && !item.pdf) {
      const r = await api(`/api/library/oa-books/text?url=${enc(item.text_url)}`, { timeout: 60000, signal: ctrl.signal });
      let rest = String(r.text || "").replace(/\r/g, "").replace(/\n{3,}/g, "\n\n").trim();
      while (rest) { let cut = rest.lastIndexOf(" ", 1700); if (cut < 400) cut = Math.min(1700, rest.length); textPages.push(rest.slice(0, cut)); rest = rest.slice(cut).trimStart(); }
      if (!textPages.length) textPages = ["Bu kayıtta okunabilir metin yok."];
      $("[data-foot]", layer).hidden = false; show(0);
      objectUrl = URL.createObjectURL(new Blob([r.text || ""], { type: "text/plain;charset=utf-8" }));
    } else if (!item.pdf && item.source !== "Bağış" && !doiOf(item)) {
      // Katalog kaydı (çoğu DOAB): tam metin yayıncının sitesinde.
      pages.innerHTML = `<div class="ar-fail"><b>${esc(title)}</b><p>${esc(String(item.abstract || "Bu kitabın tam metni yayıncının sitesinde, açık erişimle okunabilir.").slice(0, 900))}</p>${safeUrl(item.url) ? `<a class="ar-btn" href="${esc(safeUrl(item.url))}" target="_blank" rel="noopener">${icon("external")}Yayıncı sayfasında oku</a>` : ""}</div>`;
      return;
    } else {
      const local = item.source === "Bağış" && /^[a-f0-9]{32}$/.test(item.id || "");
      const load = async (pdfUrl) => {
        pages.innerHTML = '<div class="ar-loading"><span class="spinner"></span>Kitap raftan indiriliyor…</div>';
        const url = local ? `/api/library/donations/${enc(item.id)}/pdf` : `/api/pdf?url=${enc(safeUrl(pdfUrl) || "")}&doi=${enc(doiOf(item))}`;
        const res = await fetch(url, { signal: AbortSignal.any([ctrl.signal, AbortSignal.timeout(120000)]) });
        if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(typeof e.detail === "string" ? e.detail : "Kitabın PDF'i alınamadı (çok büyük ya da kapalı olabilir)."); }
        const blob = await res.blob(); if (!blob.type.includes("pdf")) throw new Error("PDF biçimi doğrulanamadı.");
        if (objectUrl) URL.revokeObjectURL(objectUrl);
        objectUrl = URL.createObjectURL(blob);
        pages.innerHTML = `<div class="ar-pdf"><iframe src="${objectUrl}" title="${esc(title)}"></iframe></div>`;
        const dl = $("[data-download]", layer); dl.href = objectUrl;
      };
      const parts = Array.isArray(item.parts) ? item.parts.filter(safeUrl) : [];
      if (parts.length > 1) {
        // TÜBA Açık Ders: haftalık ders notları
        const sel = document.createElement("select"); sel.className = "ar-btn ar-part"; sel.setAttribute("aria-label", "Hafta seç");
        sel.innerHTML = parts.map((u, i) => `<option value="${i}">${i + 1}. hafta</option>`).join("");
        $(".ar-head .spacer", layer).before(sel);
        sel.onchange = () => load(parts[+sel.value]).catch((err) => { if (!ctrl.signal.aborted) pages.innerHTML = `<div class="ar-fail"><b>Bu hafta açılamadı</b><p>${esc(err.message)}</p></div>`; });
      }
      await load(parts[0] || item.pdf);
    }
    const dl = $("[data-download]", layer); dl.href = objectUrl; dl.download = `${title.slice(0, 80)}.${item.text_url && !item.pdf ? "txt" : "pdf"}`; dl.hidden = false;
    try { localStorage.setItem("akademik-okuma-devam", JSON.stringify({ ...item, title, archive: true, at: Date.now() })); } catch { /* isteğe bağlı */ }
  } catch (e) {
    if (ctrl.signal.aborted) return;
    pages.innerHTML = `<div class="ar-fail"><b>Bu kitap şu an açılamadı</b><p>${esc(e.message)}</p>${safeUrl(item.url) ? `<a class="ar-btn" href="${esc(safeUrl(item.url))}" target="_blank" rel="noopener">${icon("external")}Kaynağında aç</a>` : ""}</div>`;
  }
}

// ------------------------------------------------------------------ üzerine gelince kart
export function hoverCard(item, x, y) {
  const el = $("#hoverCard"); if (!el) return;
  if (!item) { el.hidden = true; el.dataset.key = ""; return; }
  const key = item.doi || item.id || item.title || item.name;
  if (el.dataset.key !== key) {
    el.dataset.key = key;
    const meta = item.kind === "trend" ? `+%${number(item.growth)} büyüme · ${number(item.count)} yayın` : [cleanTitle(item.venue || item.source || ""), item.year].filter(Boolean).join(" · ");
    el.innerHTML = `<b>${esc(titleOf(item))}</b>${meta ? `<span>${esc(meta)}</span>` : ""}${item.reason ? `<span class="why">${icon("sparkle")}${esc(item.reason)}</span>` : ""}<small>${item.archive ? "Tıkla · raftan al ve oku" : "Tıkla · aç"}</small>`;
  }
  el.hidden = false;
  const w = el.offsetWidth, h = el.offsetHeight;
  el.style.transform = `translate(${Math.min(innerWidth - w - 12, x + 18)}px, ${Math.min(innerHeight - h - 12, y + 18)}px)`;
}
export { PALETTE };
