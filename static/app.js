// Akademik İz — arayüz (bağımlılıksız). Görünümler hash yönlendirmesiyle açılır:
//   #/                      Ana sayfa (tek arama kutusu)
//   #/akademisyenler?q=     YÖK'te ad araması + incelenen profiller
//   #/universiteler         YÖK'teki tüm üniversiteler
//   #/universite/<id>       Fakülte → bölüm → akademisyen (YÖK kurum dizini)
//   #/kurum?u=<url>         Kurum sitesinden okunan dizin (Scrapling + Gemini)
//   #/firmalar, #/firma/<id>
//   #/ara?q=<konu>          Konular
//   #/kutuphane             Favori makaleler ve akademisyenler
//   #/sistem                Servis durumu, REA site tarifleri
//   #/profil/<sohbet-id>    Akademisyen profili; #/is/<iş-id> profil hazırlanırken canlı ilerleme
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
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
  home: '<path d="M3 11.5 12 4l9 7.5"/><path d="M5.5 10v10h13V10"/><path d="M10 20v-6h4v6"/>',
  arrow: '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="13 6 19 12 13 18"/>',
  compass: '<circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/>',
  search: '<circle cx="11" cy="11" r="7.5"/><line x1="21" y1="21" x2="16.6" y2="16.6"/>',
  filter: '<path d="M4 5h16l-6 7v6l-4 2v-8z"/>',
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
  calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>',
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
  dir: null,           // kurum sitesi dizini durumu
  uni: null,           // YÖK üniversite dizini durumu
  candidates: [],      // YÖK ad aramasında bulunan kişiler
  registry: new Map(), // ekrandaki yayınlar: id → { paper, source }
  staffRegistry: new Map(), // sıralamadan bağımsız kadro eylemleri
  lists: {},           // dışa aktarılabilir listeler
  listMeta: {},        // liste → { file: dosya adı kökü, person, title } (dışa aktarmada akademisyen adı)
};
let regSeq = 0;
function reg(paper, source) { const id = `r${++regSeq}`; S.registry.set(id, { paper, source }); return id; }

const view = () => $("#view");
function setView(html, cls = "") {
  S.registry.clear();
  S.staffRegistry.clear();
  const v = view();
  v.innerHTML = `<div class="enter ${cls}">${html}</div>`;
  hydrateIcons(v);
  animateCounts(v);
  v.scrollTop = 0;
  return v.firstElementChild;
}

// ------------------------------------------------------------------- hareket
const calmMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const EASE = "cubic-bezier(.2,.7,.2,1)";
// Sayılar sıfırdan yukarı sayar: count(n) ile yazılan her öğe için.
const count = (n) => `<span data-count="${Number(n) || 0}">${fmtNum(n)}</span>`;
function animateCounts(root = document) {
  if (calmMotion()) return;
  $$("[data-count]", root).forEach((el) => {
    const end = +el.dataset.count;
    delete el.dataset.count;
    if (end < 2) return;
    const start = performance.now(), ms = Math.min(1100, 450 + end * 4);
    const tick = (now) => {
      const t = Math.min(1, (now - start) / ms);
      el.textContent = fmtNum(Math.round(end * (1 - (1 - t) ** 3)));
      if (t < 1) requestAnimationFrame(tick);
    };
    el.textContent = "0";
    requestAnimationFrame(tick);
  });
}
// Sekme değişimi: alt çizgi eski sekmeden yeni sekmeye kayar, içerik gidiş yönünden gelir.
function switchTab(tab) {
  const tabs = $$(".tab", tab.parentElement), prev = tabs.find((x) => x.classList.contains("active"));
  if (prev === tab) return;
  const from = prev?.getBoundingClientRect(), to = tab.getBoundingClientRect();
  const dir = tabs.indexOf(tab) > tabs.indexOf(prev) ? 1 : -1;
  tabs.forEach((x) => x.classList.toggle("active", x === tab));
  $$(".panel").forEach((x) => {
    const on = x.dataset.panel === tab.dataset.tab;
    x.classList.toggle("active", on);
    if (on) x.style.setProperty("--dir", dir);
  });
  if (from && !calmMotion()) {
    tab.animate({ transform: [`translateX(${from.left - to.left}px) scaleX(${from.width / to.width})`, "none"] },
      { duration: 340, easing: EASE, pseudoElement: "::after" });
  }
}
// Arama kutusunda yazılıp silinen örnekler; kutu odaklanınca ya da sayfa değişince durur.
function typePlaceholder(input, phrases) {
  input.placeholder = phrases[0];
  if (calmMotion()) return;
  let i = 0, n = phrases[0].length, back = true, wait = 26;
  const tick = () => {
    if (!input.isConnected || document.activeElement === input || input.value) { if (input.isConnected) setTimeout(tick, 600); return; }
    if (wait > 0) { wait -= 1; setTimeout(tick, 60); return; }
    n += back ? -1 : 1;
    input.placeholder = phrases[i].slice(0, Math.max(0, n)) || " ";
    if (back && n <= 0) { back = false; i = (i + 1) % phrases.length; n = 0; }
    else if (!back && n >= phrases[i].length) { back = true; wait = 26; }
    setTimeout(tick, back ? 26 : 52);
  };
  setTimeout(tick, 600);
}

// ------------------------------------------------------------------- tema (açık / koyu)
const storedTheme = () => { try { return localStorage.getItem("theme"); } catch { return null; } };
function applyTheme(next) {
  document.documentElement.dataset.theme = next;
  $('meta[name="theme-color"]')?.setAttribute("content", next === "dark" ? "#000000" : "#ffffff");
  const btn = $("#themeBtn");
  if (btn) { btn.title = next === "dark" ? "Açık temaya geç" : "Koyu temaya geç"; btn.setAttribute("aria-label", btn.title); }
}
// Yeni tema tıklanan noktadan dairesel açılır; desteklemeyen tarayıcıda renkler yumuşakça geçer.
function toggleTheme(ev) {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  try { localStorage.setItem("theme", next); } catch { /* tercih bu oturumla sınırlı kalır */ }
  if (calmMotion()) { applyTheme(next); return; }
  if (!document.startViewTransition) {
    document.documentElement.classList.add("theme-fade");
    applyTheme(next);
    setTimeout(() => document.documentElement.classList.remove("theme-fade"), 360);
    return;
  }
  const x = ev.clientX, y = ev.clientY, r = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
  const vt = document.startViewTransition(() => applyTheme(next));
  vt.ready.then(() => document.documentElement.animate({ clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${r}px at ${x}px ${y}px)`] },
    { duration: 560, easing: EASE, pseudoElement: "::view-transition-new(root)" })).catch(() => {});
}
function setCrumbs(items) {
  $("#crumbs").innerHTML = items.map((c, i) => (i === items.length - 1 ? `<b>${esc(c.label)}</b>`
    : `<a href="${esc(c.href)}">${esc(c.label)}</a>${icon("chevron")}`)).join("");
}
function setNav(key) {
  let active = null;
  $$("[data-nav]").forEach((a) => { const on = a.dataset.nav === key; a.classList.toggle("active", on); if (on) active = a; });
  const pill = $("#navPill");
  if (active?.closest("#nav")) {
    pill.style.opacity = 1; pill.style.height = `${active.offsetHeight}px`; pill.style.transform = `translateY(${active.offsetTop}px)`;
  } else pill.style.opacity = 0;
  $("#app").classList.remove("menu-open");
}

function toast(html, ms = 4200) {
  const el = document.createElement("div");
  el.className = "toast"; el.innerHTML = html;
  $("#toasts").appendChild(el);
  setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 320); }, ms);
}

let busyN = 0;
function busy(d) { busyN += d; document.body.classList.toggle("is-busy", busyN > 0); }
async function api(url, opts = {}) {
  busy(1);
  try {
    const res = await fetch(url, { headers: { "Content-Type": "application/json" }, ...opts });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const error = new Error(typeof err.detail === "string" ? err.detail : `İstek başarısız (HTTP ${res.status}).`);
      error.status = res.status;
      throw error;
    }
    return await res.json();
  } finally { busy(-1); }
}
const post = (url, body) => api(url, { method: "POST", body: JSON.stringify(body) });

// Canlı WoS doğrulaması kendi katmanında kalır; profil, drawer ve yayın filtrelerini değiştirmez.
let wosVerification = null;
function createWosVerification() {
  const dialog = document.createElement("dialog"), launcher = document.createElement("button");
  dialog.className = "wos-verification";
  dialog.setAttribute("aria-labelledby", "wosVerificationTitle");
  dialog.setAttribute("aria-describedby", "wosVerificationDescription");
  dialog.innerHTML = `<header class="wos-verification-head"><div><h2 id="wosVerificationTitle">WoS doğrulaması</h2>
    <p id="wosVerificationDescription">Doğrulamayı tamamlayın; tarama otomatik devam edecek.</p></div>
    <button class="btn sm ghost" type="button" data-wos-hide autofocus>${icon("x")}Şimdilik gizle</button></header>
    <div class="wos-verification-meta"><span data-wos-host></span><span data-wos-title></span>
      <select class="select" data-wos-session aria-label="Bekleyen doğrulama" hidden></select></div>
    <div class="wos-verification-stage" data-wos-stage data-ready="false">
      <canvas tabindex="0" aria-label="Canlı WoS doğrulama ekranı" aria-describedby="wosVerificationHelp" hidden>Canlı WoS doğrulama ekranı</canvas>
      <textarea class="wos-verification-input" tabindex="-1" aria-label="Doğrulama ekranına yazın" autocomplete="off" autocapitalize="off" spellcheck="false"></textarea>
      <div class="wos-verification-cover"><span data-wos-cover>Bağlanıyor…</span></div>
    </div>
    <footer class="wos-verification-footer"><div><span data-wos-status role="status" aria-live="polite">Bağlanıyor…</span>
      <small id="wosVerificationHelp">Ekrana tıklayın veya sürükleyin. Esc paneli gizler.</small></div>
      <div class="wos-verification-actions"><button class="btn sm ghost" type="button" data-wos-keyboard disabled>Klavye</button>
        <button class="btn sm" type="button" data-wos-reconnect hidden>${icon("refresh")}Yeniden bağlan</button>
        <button class="btn sm" type="button" data-wos-cancel disabled>Taramayı atla</button></div></footer>`;
  launcher.type = "button"; launcher.className = "btn wos-verification-launcher"; launcher.hidden = true;
  document.body.append(dialog, launcher);
  const canvas = $("canvas", dialog), keyboard = $("textarea", dialog), stage = $("[data-wos-stage]", dialog);
  const status = $("[data-wos-status]", dialog), cover = $("[data-wos-cover]", dialog);
  const sessions = $("[data-wos-session]", dialog), cancel = $("[data-wos-cancel]", dialog);
  const reconnect = $("[data-wos-reconnect]", dialog), keyboardButton = $("[data-wos-keyboard]", dialog);
  const seen = new Set(), finished = new Set();
  let items = new Map(), selectedId = null, previousFocus = null, socket = null, socketEpoch = 0;
  let ready = false, hasFrame = false, cancelPending = false, composing = false, touchFocus = false;
  let pointerId = null, pendingMove = null, moveTimer = null, lastMove = 0, pendingWheel = null, wheelTimer = null;
  let pollTimer = null, pollRequest = null, reconnectTimer = null, reconnectAttempt = 0, stopped = false;
  let missingTimer = null, missingId = null, listedIds = new Set(), sessionOptions = "";
  const setStatus = (message) => { if (status.textContent !== message) status.textContent = message; cover.textContent = message; };
  const inputReady = () => dialog.open && ready && hasFrame && !cancelPending && socket?.readyState === WebSocket.OPEN;
  const updateControls = () => {
    stage.dataset.ready = String(inputReady());
    canvas.setAttribute("aria-disabled", String(!inputReady()));
    keyboardButton.disabled = !inputReady(); cancel.disabled = !ready || cancelPending;
  };
  const send = (message) => {
    if (socket?.readyState !== WebSocket.OPEN) return false;
    try { socket.send(JSON.stringify(message)); return true; } catch { return false; }
  };
  const release = () => {
    clearTimeout(moveTimer); moveTimer = null; pendingMove = null;
    clearTimeout(wheelTimer); wheelTimer = null; pendingWheel = null;
    const captured = pointerId; pointerId = null;
    if (captured != null && canvas.hasPointerCapture(captured)) canvas.releasePointerCapture(captured);
    if (ready) send({ type: "release" });
  };
  const disconnect = () => {
    clearTimeout(reconnectTimer); reconnectTimer = null;
    release(); socketEpoch += 1; ready = false; hasFrame = false;
    const old = socket; socket = null;
    if (old) { old.onclose = null; old.close(); }
    keyboard.value = ""; composing = false; updateControls();
  };
  const syncList = () => {
    const list = [...items.values()];
    launcher.hidden = !list.length || dialog.open;
    launcher.innerHTML = `${icon("globe")}WoS doğrulaması${list.length > 1 ? ` <span class="count">${list.length}</span>` : ""}`;
    sessions.hidden = list.length < 2;
    const value = selectedId;
    const options = list.map((item, index) => `<option value="${esc(item.id)}">${esc(item.title || item.host || `Doğrulama ${index + 1}`)}</option>`).join("");
    if (sessionOptions !== options) { sessions.innerHTML = options; sessionOptions = options; }
    if (value) sessions.value = value;
  };
  const hide = () => {
    if (!dialog.open) return;
    disconnect(); dialog.close(); syncList();
    if (previousFocus?.isConnected) previousFocus.focus({ preventScroll: true });
    previousFocus = null;
  };
  const showNext = () => {
    if (dialog.open || document.hidden || stopped) return;
    const next = [...items.values()].find((item) => !seen.has(item.id));
    if (next) show(next.id);
  };
  const finish = (id, result, message) => {
    if (finished.has(id)) return;
    if (missingId === id) { clearTimeout(missingTimer); missingTimer = null; missingId = null; }
    finished.add(id); items.delete(id);
    if (selectedId === id) { hide(); selectedId = null; }
    syncList();
    const text = result === "solved" ? "WoS doğrulaması tamamlandı; tarama devam ediyor."
      : result === "cancelled" ? "WoS doğrulaması atlandı."
      : result === "expired" ? "WoS doğrulamasının süresi doldu." : message || "WoS doğrulama oturumu sona erdi.";
    toast(esc(text));
    if (result === "solved") document.dispatchEvent(new CustomEvent("wos-verification-solved", { detail: { id } }));
    showNext();
  };
  const connect = () => {
    if (!dialog.open || !items.has(selectedId) || document.hidden || stopped) return;
    disconnect();
    const id = selectedId, epoch = socketEpoch, current = () => epoch === socketEpoch && selectedId === id && dialog.open;
    setStatus("Canlı ekrana bağlanıyor…"); reconnect.hidden = true;
    const url = new URL(`/api/wos/verification/${encodeURIComponent(id)}/stream`, location.href);
    url.protocol = location.protocol === "https:" ? "wss:" : "ws:";
    let ws;
    try { ws = new WebSocket(url); } catch {
      setStatus("Canlı bağlantı kurulamadı. Yeniden bağlanabilirsiniz."); reconnect.hidden = false; return;
    }
    socket = ws; ws.binaryType = "blob";
    let pendingFrame = null, decoding = false;
    const drawFrame = async () => {
      decoding = true;
      while (pendingFrame && current()) {
        const frame = pendingFrame; pendingFrame = null;
        let bitmap = null, objectUrl = null;
        try {
          if (typeof createImageBitmap === "function") bitmap = await createImageBitmap(frame);
          else {
            objectUrl = URL.createObjectURL(frame);
            bitmap = await new Promise((resolve, reject) => { const image = new Image(); image.onload = () => resolve(image); image.onerror = reject; image.src = objectUrl; });
          }
          if (!current()) break;
          const width = bitmap.width, height = bitmap.height;
          if (!(width > 0 && height > 0 && width <= 8192 && height <= 8192)) continue;
          if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
          canvas.getContext("2d").drawImage(bitmap, 0, 0);
          canvas.hidden = false;
          if (!hasFrame) { hasFrame = true; if (ready && !cancelPending) setStatus("Canlı bağlantı hazır."); }
          updateControls();
        } catch { if (current()) { hasFrame = false; setStatus("Görüntü yenileniyor…"); updateControls(); } }
        finally { bitmap?.close?.(); if (objectUrl) URL.revokeObjectURL(objectUrl); }
      }
      decoding = false;
    };
    ws.onmessage = (event) => {
      if (!current()) return;
      if (event.data instanceof Blob) { pendingFrame = event.data; if (!decoding) void drawFrame(); return; }
      let message;
      try { message = JSON.parse(event.data); } catch { return; }
      if (message.type === "ready") {
        ready = true; reconnectAttempt = 0;
        if (cancelPending) send({ type: "cancel" });
        setStatus(cancelPending ? "Tarama atlanıyor…" : hasFrame ? "Canlı bağlantı hazır." : "Canlı görüntü yükleniyor…");
        updateControls();
      } else if (message.type === "finished") finish(id, message.status, message.message);
      else if (message.type === "busy") { ready = false; setStatus("Bu doğrulama başka bir pencerede açık. Bağlantı yeniden denenecek."); updateControls(); }
      else if (message.type === "error") setStatus(message.message || "Canlı bağlantıda bir sorun oluştu.");
    };
    ws.onclose = (event) => {
      if (!current()) return;
      release(); socket = null; ready = false; updateControls();
      if (event.code === 4404) { finish(id, "ended"); return; }
      reconnect.hidden = false;
      if (event.code === 4403) { setStatus("Bu pencereden canlı bağlantıya izin verilmiyor."); return; }
      if (event.code === 4400) { setStatus("Girdi bağlantısı kapandı. Yeniden bağlanabilirsiniz."); return; }
      setStatus(event.code === 4409 ? "Bu doğrulama başka bir pencerede açık. Bağlantı yeniden denenecek." : "Bağlantı kesildi; yeniden bağlanıyor…");
      const delay = Math.min(10000, 2000 * 2 ** Math.min(reconnectAttempt++, 3));
      reconnectTimer = setTimeout(() => { if (current()) connect(); }, delay);
    };
    ws.onerror = () => { if (current()) setStatus("Canlı bağlantı bekleniyor…"); };
  };
  const show = (id) => {
    const item = items.get(id); if (!item) return;
    if (missingTimer && missingId !== id) { clearTimeout(missingTimer); missingTimer = null; missingId = null; }
    disconnect(); selectedId = id; seen.add(id); hasFrame = false; cancelPending = false; reconnectAttempt = 0;
    canvas.hidden = true;
    $("[data-wos-host]", dialog).textContent = item.host || "Web of Science";
    const title = $("[data-wos-title]", dialog); title.textContent = item.title || ""; title.title = item.title || "";
    if (!dialog.open) { previousFocus = document.activeElement; dialog.showModal(); }
    syncList(); connect();
  };
  const schedulePoll = (delay = 2500) => {
    clearTimeout(pollTimer);
    if (!stopped) pollTimer = setTimeout(poll, delay);
  };
  const poll = async () => {
    if (stopped || pollRequest) return;
    const controller = new AbortController(); pollRequest = controller;
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch("/api/wos/verification", { cache: "no-store", credentials: "same-origin", signal: controller.signal });
      if (!response.ok) return;
      const data = await response.json();
      if (stopped || controller.signal.aborted || !Array.isArray(data.items)) return;
      const previous = items.get(selectedId);
      items = new Map(data.items.filter((item) => typeof item.id === "string" && item.status === "waiting" && !finished.has(item.id)).map((item) => [item.id, item]));
      listedIds = new Set(items.keys());
      if (dialog.open && !items.has(selectedId)) {
        // Son liste yanıtı, socket'in "finished" mesajından önce gelebilir.
        const live = socket && [WebSocket.OPEN, WebSocket.CONNECTING].includes(socket.readyState);
        if (live || (missingTimer && missingId === selectedId)) {
          if (previous) items.set(selectedId, previous);
          if (!missingTimer) {
            const id = selectedId; missingId = id;
            missingTimer = setTimeout(() => {
              missingTimer = null; missingId = null;
              if (!listedIds.has(id)) finish(id, "ended");
            }, 3500);
          }
        } else finish(selectedId, "ended");
      } else if (missingTimer && listedIds.has(missingId)) {
        clearTimeout(missingTimer); missingTimer = null; missingId = null;
      }
      syncList(); showNext();
    } catch { /* Bir geçici listeleme hatası mevcut canlı oturumu kapatmaz. */ }
    finally {
      clearTimeout(timeout); if (pollRequest === controller) pollRequest = null;
      schedulePoll();
    }
  };
  const coords = (event) => {
    const rect = canvas.getBoundingClientRect();
    return { x: Math.max(0, Math.min(1, (event.clientX - rect.left) / Math.max(1, rect.width))), y: Math.max(0, Math.min(1, (event.clientY - rect.top) / Math.max(1, rect.height))) };
  };
  const flushMove = () => {
    clearTimeout(moveTimer); moveTimer = null;
    if (pendingMove && inputReady()) { send(pendingMove); lastMove = performance.now(); }
    pendingMove = null;
  };
  canvas.addEventListener("pointerdown", (event) => {
    if (!inputReady() || event.button !== 0 || pointerId != null) return;
    event.preventDefault(); touchFocus = event.pointerType === "touch";
    canvas.focus({ preventScroll: true }); touchFocus = false;
    pointerId = event.pointerId; canvas.setPointerCapture(pointerId);
    send({ type: "pointer", action: "down", ...coords(event), button: 0 });
  });
  canvas.addEventListener("pointermove", (event) => {
    if (!inputReady() || (pointerId != null && event.pointerId !== pointerId)) return;
    pendingMove = { type: "pointer", action: "move", ...coords(event), button: 0 };
    if (!moveTimer) moveTimer = setTimeout(flushMove, Math.max(0, 50 - (performance.now() - lastMove)));
  });
  canvas.addEventListener("pointerup", (event) => {
    if (pointerId !== event.pointerId) return;
    event.preventDefault(); flushMove();
    if (inputReady()) send({ type: "pointer", action: "up", ...coords(event), button: 0 });
    release();
  });
  canvas.addEventListener("pointercancel", release);
  canvas.addEventListener("lostpointercapture", () => { if (pointerId != null) release(); });
  canvas.addEventListener("contextmenu", (event) => event.preventDefault());
  canvas.addEventListener("wheel", (event) => {
    event.preventDefault(); if (!inputReady()) return;
    const factor = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? canvas.clientHeight : 1;
    const delta = (value) => Math.max(-2000, Math.min(2000, value * factor));
    pendingWheel = { type: "wheel", ...coords(event),
      deltaX: Math.max(-2000, Math.min(2000, (pendingWheel?.deltaX || 0) + delta(event.deltaX))),
      deltaY: Math.max(-2000, Math.min(2000, (pendingWheel?.deltaY || 0) + delta(event.deltaY))) };
    if (!wheelTimer) wheelTimer = setTimeout(() => {
      wheelTimer = null; if (pendingWheel && inputReady()) send(pendingWheel); pendingWheel = null;
    }, 50);
  }, { passive: false });
  canvas.addEventListener("focus", () => { if (!touchFocus && inputReady()) keyboard.focus({ preventScroll: true }); });
  const sendText = (text) => {
    if (!inputReady()) return;
    const clean = Array.from(String(text || "").replace(/[\u0000-\u001f\u007f-\u009f]/g, ""));
    const chars = clean.slice(0, 2048);
    for (let i = 0; i < chars.length; i += 256) send({ type: "text", text: chars.slice(i, i + 256).join("") });
    if (clean.length > chars.length) setStatus("Metnin ilk 2.048 karakteri gönderildi.");
  };
  const flushText = () => { if (!composing && keyboard.value) { sendText(keyboard.value); keyboard.value = ""; } };
  keyboard.addEventListener("compositionstart", () => { composing = true; });
  keyboard.addEventListener("compositionend", () => { composing = false; queueMicrotask(flushText); });
  keyboard.addEventListener("input", flushText);
  keyboard.addEventListener("beforeinput", (event) => {
    if (composing || !inputReady()) return;
    const key = { deleteContentBackward: "Backspace", deleteContentForward: "Delete", insertLineBreak: "Enter", insertParagraph: "Enter" }[event.inputType];
    if (key) { event.preventDefault(); send({ type: "key", key }); }
  });
  const remoteKeys = new Set(["Tab", "Enter", "Backspace", "Delete", "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End", "PageUp", "PageDown", " "]);
  for (const input of [canvas, keyboard]) {
    input.addEventListener("keydown", (event) => {
      if (event.key === "Escape" || event.isComposing || composing || !inputReady()) return;
      if (event.key === "Tab" && event.shiftKey) { event.preventDefault(); $("[data-wos-hide]", dialog).focus(); return; }
      if (event.ctrlKey || event.metaKey || event.altKey) return;
      if (remoteKeys.has(event.key)) { event.preventDefault(); event.stopPropagation(); send({ type: "key", key: event.key === " " ? "Space" : event.key }); }
      else if (input === canvas && Array.from(event.key).length === 1) { event.preventDefault(); sendText(event.key); }
    });
    input.addEventListener("paste", (event) => { if (!inputReady()) return; event.preventDefault(); sendText(event.clipboardData?.getData("text/plain")); keyboard.value = ""; });
    input.addEventListener("blur", (event) => { if (event.relatedTarget !== canvas && event.relatedTarget !== keyboard) release(); });
  }
  $("[data-wos-hide]", dialog).onclick = hide;
  dialog.addEventListener("cancel", (event) => { event.preventDefault(); hide(); });
  sessions.onchange = () => show(sessions.value);
  launcher.onclick = () => show(items.has(selectedId) ? selectedId : items.keys().next().value);
  reconnect.onclick = () => { reconnectAttempt = 0; connect(); };
  keyboardButton.onclick = () => keyboard.focus({ preventScroll: true });
  cancel.onclick = () => { if (!ready || cancelPending) return; release(); cancelPending = send({ type: "cancel" }); setStatus("Tarama atlanıyor…"); updateControls(); };
  window.addEventListener("blur", release);
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) disconnect();
    else { if (dialog.open) connect(); schedulePoll(0); }
  });
  window.addEventListener("pagehide", () => {
    stopped = true; clearTimeout(pollTimer); clearTimeout(missingTimer); missingTimer = null; missingId = null;
    pollRequest?.abort(); disconnect();
  });
  window.addEventListener("pageshow", () => { if (stopped) { stopped = false; if (dialog.open) connect(); schedulePoll(0); } });
  schedulePoll(0);
  return { hide, isOpen: () => dialog.open };
}

const skeleton = (n = 5) => Array.from({ length: n }, () => `<div class="skel-row"><div class="skel"></div><div class="skel-lines"><div class="skel"></div><div class="skel"></div></div></div>`).join("");
const emptyState = (ic, title, text, extra = "") => `<div class="empty"><div class="em-icon">${icon(ic)}</div><h3>${esc(title)}</h3><p>${text}</p>${extra}</div>`;
function avatar(name, photo, cls = "av") {
  const img = safeImg(photo);
  return `<div class="${cls}">${esc(initials(name))}${img ? `<img src="${esc(img)}" alt="" loading="lazy" onerror="this.remove()">` : ""}</div>`;
}
const profilePhoto = (c) => (c.job_id ? `/api/jobs/${encodeURIComponent(c.job_id)}/photo` : "");

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
  $("#cntProfiles").textContent = S.chats.length || "";
}

async function loadFav() {
  try { S.fav = await api("/api/favorites"); } catch { /* sunucu yok */ }
  $("#cntLibrary").textContent = (S.fav.papers.length + S.fav.people.length) || "";
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
      if (location.hash.startsWith("#/kutuphane")) { btn.closest(".paper")?.remove(); }
    } else {
      const src = entry.source || {};
      await post("/api/favorites/papers", { item: { ...p, sources: p.sources, job_id: src.jid, pid: src.pid, person: src.person } });
      btn.classList.add("on"); toast(`${icon("star")} Favori makalelere eklendi.`);
    }
  } catch (e) { toast(esc(e.message)); }
  await loadFav();
  $$("[data-star]").forEach((star) => {
    const current = S.registry.get(star.dataset.star);
    if (current) star.classList.toggle("on", !!favPaper(current.paper));
  });
}

// ------------------------------------------------------------------- yayın kartı, dışa aktarma
const TYPE_TR = { article: "Makale", "journal-article": "Makale", proceedings: "Bildiri", "proceedings-article": "Bildiri", book: "Kitap",
  "book-chapter": "Kitap bölümü", dissertation: "Tez", preprint: "Ön baskı", review: "Derleme", dataset: "Veri seti", software: "Yazılım",
  "conference-paper": "Bildiri", "conference-abstract": "Bildiri özeti", "meeting-abstract": "Bildiri özeti", "meeting abstract": "Bildiri özeti",
  "posted-content": "Ön baskı", report: "Rapor", editorial: "Editöryal", letter: "Mektup", correction: "Düzeltme", erratum: "Düzeltme",
  retraction: "Geri çekme bildirimi", "peer-review": "Hakem değerlendirmesi", "reference-entry": "Başvuru maddesi", standard: "Standart", other: "Diğer" };
const SRC_TR = { openalex: "OpenAlex", crossref: "Crossref", orcid: "ORCID", yok: "YÖK", scholar: "Scholar", semantic_scholar: "Semantic Scholar",
  trdizin: "TR Dizin", openaire: "OpenAIRE", tez: "Tez Merkezi", wos: "WoS" };
function sourceBadges(p) {
  const sources = p.sources || (p.source ? [p.source] : []);
  return sources.map((s) => {
    if (s === "wos") {
      const url = safeUrl(p.wos?.url);
      const indexes = (p.wos?.indexes || []).filter(Boolean).join(" · ");
      const year = p.wos?.year && p.year && p.wos.year !== p.year ? ` · WoS yayın yılı: ${p.wos.year}; listedeki yıl: ${p.year}` : "";
      const title = `Web of Science${indexes ? ` · ${indexes}` : ""}${year}`;
      if (url) return `<a class="badge wos" href="${esc(url)}" target="_blank" rel="noopener" title="${esc(title)}">WoS</a>`;
      return `<span class="badge wos" title="${esc(title)}">WoS</span>`;
    }
    return `<span class="badge ${esc(s)}">${esc(SRC_TR[s] || s)}</span>`;
  }).join("");
}
function publicationKind(p) {
  return p.publication_kind || TYPE_TR[String(p.type || "").toLowerCase().replace(/_/g, "-")] || p.type || "Tür belirtilmemiş";
}
function publicationStatusLabel(p) {
  return p.publication_status?.label || "Süreç bilgisi yok";
}
function publicationStatusHtml(p) {
  const status = p.publication_status || {};
  const tip = [status.source && `Kaynak: ${SRC_TR[status.source] || status.source}`,
    status.evidence && `Kayıt açıklamasındaki beyan: ${status.evidence}`].filter(Boolean).join(" · ");
  const url = safeUrl(status.url), label = esc(publicationStatusLabel(p));
  const attrs = `class="publication-stage"${tip ? ` title="${esc(tip)}"` : ""}`;
  return `<div class="publication-status"><span class="publication-kind">${esc(publicationKind(p))}</span>${url
    ? `<a ${attrs} href="${esc(url)}" target="_blank" rel="noopener">${label}</a>`
    : `<span ${attrs}>${label}</span>`}</div>`;
}
const STAGE_TR = { unknown: "Süreç bilgisi yok", in_preparation: "Gönderime hazırlanıyor", submitted: "Gönderildi",
  under_review: "Değerlendirmede", accepted: "Kabul edildi", in_press: "Baskıda", published: "Yayımlandı" };
const sourceKey = (s) => {
  const key = fold(s).replace(/ /g, "_");
  return { tr_dizin: "trdizin", web_of_science: "wos", google_scholar: "scholar", open_alex: "openalex", open_aire: "openaire" }[key] || key;
};
const publicationSources = (p) => [...new Set((p.sources || (p.source ? [p.source] : [])).map(sourceKey).filter(Boolean))];
function filterPublications(papers, filters = {}) {
  const q = fold(filters.query), from = Number(filters.fromYear) || null, to = Number(filters.toYear) || null;
  const list = papers.filter((p) => {
    const year = Number(p.year) || null;
    return (!q || fold([p.title, p.venue, ...(p.authors || []), ...(p.unit_authors || []), ...(p.variants || []).map((v) => v.title)].join(" ")).includes(q))
      && (!filters.source || publicationSources(p).includes(sourceKey(filters.source)))
      && (!from || (year != null && year >= from)) && (!to || (year != null && year <= to))
      && (!filters.stage || (p.publication_status?.code || "unknown") === filters.stage)
      && (!filters.verification || (filters.verification === "multiple" ? publicationSources(p).length > 1 : publicationSources(p).length <= 1))
      && (!filters.quartile || (filters.quartile === "none" ? !p.quartile : p.quartile?.q === filters.quartile));
  });
  const key = filters.sort || "year", direction = filters.direction || (key === "title" ? "asc" : "desc");
  const value = (p) => ({
    title: p.title || "", stage: `${publicationKind(p)} ${publicationStatusLabel(p)}`,
    source: publicationSources(p).map((s) => SRC_TR[s] || s).sort().join(" "),
    verification: publicationSources(p).length, year: p.year == null ? null : Number(p.year),
    cites: p.citations == null ? null : Number(p.citations), id: Number(String(p.id || "").replace(/^P/, "")) || null,
  })[key];
  if (key !== "rel") list.sort((a, b) => {
    const x = value(a), y = value(b);
    if (x == null && y != null) return 1;
    if (y == null && x != null) return -1;
    const result = typeof x === "string" ? x.localeCompare(y || "", "tr") : (x || 0) - (y || 0);
    return direction === "asc" ? result : -result;
  });
  return list;
}
function publicationHeader(prefix, key, label, filter = "", cls = "") {
  return `<th scope="col" data-dt-column="${key}" class="${cls}" aria-sort="none"><div class="dt-heading">
    <button class="dt-sort" type="button" data-dt-sort="${key}" data-label="${esc(label)}" title="${esc(label)} sütununu sırala">${esc(label)}<span class="dt-sort-indicator" aria-hidden="true">↕</span></button>
    ${filter ? `<button class="dt-filter-toggle" type="button" data-dt-filter="${filter}" popovertarget="${prefix}${filter}Popover" aria-label="${esc(label)} filtresi" title="${esc(label)} filtresi" aria-expanded="false">${icon("filter")}</button>` : ""}
    </div></th>`;
}
function publicationFilterPopovers(prefix) {
  const select = (suffix, label) => `<label class="dt-field">${label}<select class="dt-input" id="${prefix}${suffix}"><option value="">Tümü</option></select></label>`;
  const panels = [
    ["Title", "Başlık ve dergi", `<label class="dt-field">Başlık, yazar veya yayın yeri<input class="dt-input" type="search" id="${prefix}Filter" placeholder="Ara…" autocomplete="off"></label>${select("Quart", "Dergi çeyreği")}`],
    ["Stage", "Yayın durumu", select("Stage", "Aşama")],
    ["Year", "Yıl aralığı", `<div class="dt-year-range"><label class="dt-field">İlk yıl<input class="dt-input" id="${prefix}FromYear" type="number" min="1" max="9999" placeholder="Örn. 2020"></label><label class="dt-field">Son yıl<input class="dt-input" id="${prefix}ToYear" type="number" min="1" max="9999" placeholder="Örn. 2026"></label></div>`],
    ["Source", "Yayın kaynağı", select("Source", "Kaynak")],
    ["Verification", "Kaynak doğrulaması", `<label class="dt-field">Kaynak sayısı<select class="dt-input" id="${prefix}Verification"><option value="">Tümü</option><option value="multiple">Birden fazla kaynak</option><option value="single">Tek kaynak</option></select></label>`],
  ];
  return panels.map(([key, label, fields]) => `<div id="${prefix}${key}Popover" class="dt-filter-popover" popover="auto" role="dialog" aria-labelledby="${prefix}${key}Label">
    <strong id="${prefix}${key}Label">${label}</strong>${fields}<div class="dt-popover-actions"><button class="dt-reset" type="button" data-dt-reset="${key}">Temizle</button><button class="dt-done" type="button" popovertarget="${prefix}${key}Popover" popovertargetaction="hide">Tamam</button></div></div>`).join("");
}
function fillFilterOptions(select, options, allLabel) {
  if (!select) return;
  const selected = select.value;
  if (selected && !options.some(([value]) => value === selected)) options.push([selected, select.selectedOptions?.[0]?.textContent || STAGE_TR[selected] || SRC_TR[selected] || selected]);
  select.innerHTML = `<option value="">${esc(allLabel)}</option>${options.map(([value, label]) => `<option value="${esc(value)}">${esc(label)}</option>`).join("")}`;
  select.value = selected;
}
function syncPublicationFilters(prefix, papers) {
  const sources = [...new Set(papers.flatMap(publicationSources))].sort();
  fillFilterOptions($(`#${prefix}Source`), sources.map((s) => [s, SRC_TR[s] || s]), "Tüm kaynaklar");
  const stages = [...new Set(papers.map((p) => p.publication_status?.code || "unknown"))];
  fillFilterOptions($(`#${prefix}Stage`), stages.map((s) => [s, STAGE_TR[s] || s]), "Tüm aşamalar");
  const counts = publicationQuartiles(papers), quartile = $(`#${prefix}Quart`);
  if (quartile) {
    fillFilterOptions(quartile, ["Q1", "Q2", "Q3", "Q4"].filter((q) => counts[q]).map((q) => [q, `${counts.src} ${q} (${counts[q]})`]).concat([["none", `Çeyreği yok (${papers.length - counts.total})`]]), "Tüm çeyrekler");
    quartile.closest(".dt-field").hidden = !counts.total && !quartile.value;
  }
}
function readPublicationFilters(prefix) {
  const value = (suffix) => $(`#${prefix}${suffix}`)?.value || "";
  return { query: value("Filter"), source: value("Source"), fromYear: value("FromYear"), toYear: value("ToYear"), stage: value("Stage"), quartile: value("Quart"), verification: value("Verification") };
}
function publicationTableHtml(prefix, listKey, rowId = `${prefix}Rows`) {
  return `<div class="card publication-datatable"><div class="tbl-wrap"><table class="tbl publication-table" aria-label="Yayınlar"><thead><tr>
    <th scope="col">#</th>${publicationHeader(prefix, "title", "Başlık", "Title")}${publicationHeader(prefix, "stage", "Durum", "Stage", "pub-status-cell")}
    ${publicationHeader(prefix, "year", "Yıl", "Year")}${publicationHeader(prefix, "source", "Kaynak", "Source")}${publicationHeader(prefix, "verification", "Doğrulama", "Verification")}
    ${publicationHeader(prefix, "cites", "Atıf")}<th scope="col" aria-label="Favori"></th></tr></thead><tbody id="${rowId}"></tbody></table></div>
    <div class="dt-footer"><span id="${prefix}Count" class="dt-count" role="status" aria-live="polite"></span><button class="dt-reset" id="${prefix}Clear" type="button" hidden>Filtreleri temizle</button>
      <div class="dt-pagination"><label>Sayfada <select class="dt-page-size" id="${prefix}PageSize" aria-label="Sayfa başına yayın"><option value="25">25</option><option value="50">50</option><option value="100">100</option><option value="all">Tümü</option></select></label>
      <button class="dt-page-btn" type="button" id="${prefix}Prev" aria-label="Önceki sayfa">‹</button><span id="${prefix}Page" class="dt-page-number"></span><button class="dt-page-btn" type="button" id="${prefix}Next" aria-label="Sonraki sayfa">›</button></div>
      <button class="dt-export" data-export="${listKey}" type="button" title="Filtreye uyan tüm yayınları dışa aktar">${icon("download")}Dışa aktar</button></div>
    ${publicationFilterPopovers(prefix)}</div>`;
}
function publicationRows(list, sourceFor = () => ({}), prefix = "pub", offset = 0) {
  return list.map((p, i) => {
    const id = reg(p, sourceFor(p)), sources = publicationSources(p);
    return `<tr id="${esc(prefix)}-${esc(p.id || i + offset + 1)}"><td class="faint">${esc(/^P\d+$/.test(p.id || "") ? p.id : i + offset + 1)}</td>
      <td><div class="t-title" data-open="${id}">${esc(p.title)}</div>
        ${p.venue || p.quartile || p.jcr ? `<div class="variants">${esc(p.venue)}${p.quartile ? ` <span class="q-badge ${esc(String(p.quartile.q || "").toLowerCase())}" title="${esc(quartileAreas(p))}. ${esc(p.quartile.source)} Scopus tabanlıdır; WoS/JCR çeyreği değildir.">${esc(quartileLabel(p))}</span>` : ""} ${jcrBadge(p)}</div>` : ""}
        ${p.unit_authors?.length ? `<div class="variants">Birimdeki yazar: ${esc(p.unit_authors.join(", "))}</div>` : ""}
        ${p.variants?.length > 1 ? `<div class="variants">↳ ${p.variants.slice(1).map((v) => `${esc(v.title)} (${esc(v.lang)})`).join(" · ")}</div>` : ""}</td>
      <td class="pub-status-cell">${publicationStatusHtml(p)}</td><td>${esc(p.year || "—")}</td>
      <td><div class="chips">${sourceBadges(p)}</div></td>
      <td>${p.verified ? `<span class="vb ok">✓ ${sources.length > 1 ? sources.length + " kaynak" : (p.runs_seen || 1) + ". kez"}</span>` : `<span class="vb">${sources.length > 1 ? sources.length + " kaynak" : "tek kaynak"}</span>`}${p.is_new ? `<span class="newb">YENİ</span>` : ""}</td>
      <td>${fmtNum(p.citations)}</td><td><button class="star ${favPaper(p) ? "on" : ""}" data-star="${id}" type="button" title="Favorilere ekle">${icon("star")}</button></td></tr>`;
  }).join("") || `<tr><td colspan="8">${emptyState("file", "Yayın yok", "Filtreyi değiştirin.")}</td></tr>`;
}
function mountPublicationTable(host, prefix, listKey, papers, defaultSort = "year", options = {}) {
  let all = papers, page = 0, sort = defaultSort, direction = defaultSort === "title" ? "asc" : "desc";
  host.innerHTML = publicationTableHtml(prefix, listKey, options.rowId);
  const tbody = $(`#${options.rowId || `${prefix}Rows`}`, host), wrap = $(".tbl-wrap", host);
  const sourceFor = options.sourceFor || ((p) => {
    const ref = p.profile_refs?.find((x) => x.job_id && x.pid);
    return ref ? { jid: ref.job_id, pid: ref.pid, person: ref.name } : (p.job_id && p.pid ? { jid: p.job_id, pid: p.pid, person: p.person } : {});
  });
  const groups = { Title: ["Filter", "Quart"], Stage: ["Stage"], Year: ["FromYear", "ToYear"], Source: ["Source"], Verification: ["Verification"] };
  const fields = Object.values(groups).flat();
  const draw = () => {
    const filters = readPublicationFilters(prefix), list = filterPublications(all, { ...filters, sort, direction });
    S.lists[listKey] = list;
    const size = Number($(`#${prefix}PageSize`, host).value) || Math.max(list.length, 1), pages = Math.max(1, Math.ceil(list.length / size));
    page = Math.min(page, pages - 1);
    const offset = page * size;
    $$('[data-open]', tbody).forEach((row) => S.registry.delete(row.dataset.open));
    tbody.innerHTML = publicationRows(list.slice(offset, offset + size), sourceFor, prefix, offset);
    $(`#${prefix}Count`, host).textContent = list.length ? `${fmtNum(offset + 1)}–${fmtNum(Math.min(offset + size, list.length))} / ${fmtNum(list.length)} yayın${list.length !== all.length ? ` · toplam ${fmtNum(all.length)}` : ""}` : `0 / ${fmtNum(all.length)} yayın`;
    $(`#${prefix}Page`, host).textContent = `${page + 1} / ${pages}`;
    $(`#${prefix}Prev`, host).disabled = page === 0;
    $(`#${prefix}Next`, host).disabled = page >= pages - 1;
    $(`#${prefix}Clear`, host).hidden = !Object.values(filters).some(Boolean);
    $$("[data-dt-sort]", host).forEach((button) => {
      const selected = button.dataset.dtSort === sort;
      button.closest("th").setAttribute("aria-sort", selected ? (direction === "asc" ? "ascending" : "descending") : "none");
      $(".dt-sort-indicator", button).textContent = selected ? (direction === "asc" ? "↑" : "↓") : "↕";
      const nextDirection = selected ? (direction === "asc" ? "desc" : "asc") : (["year", "cites", "verification"].includes(button.dataset.dtSort) ? "desc" : "asc");
      button.title = `${button.dataset.label}: ${nextDirection === "asc" ? "artan" : "azalan"} sırala`;
      button.setAttribute("aria-label", button.title);
    });
    $$("[data-dt-filter]", host).forEach((button) => {
      const active = groups[button.dataset.dtFilter].some((suffix) => $(`#${prefix}${suffix}`, host).value);
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-label", `${button.closest("th").querySelector(".dt-sort").dataset.label} filtresi${active ? " · etkin" : ""}`);
    });
    hydrateIcons(tbody);
  };
  const update = (next) => {
    const scroll = host.closest(".drawer-body") || view(), top = scroll.scrollTop, left = wrap.scrollLeft;
    all = next; syncPublicationFilters(prefix, all); draw(); scroll.scrollTop = top; wrap.scrollLeft = left;
  };
  const reset = (suffixes) => { suffixes.forEach((suffix) => { $(`#${prefix}${suffix}`, host).value = ""; }); page = 0; draw(); };
  for (const suffix of fields) {
    const input = $(`#${prefix}${suffix}`, host);
    input.addEventListener(input.tagName === "SELECT" ? "change" : "input", () => { page = 0; draw(); });
  }
  $$("[data-dt-sort]", host).forEach((button) => {
    button.onclick = () => {
      const key = button.dataset.dtSort;
      direction = sort === key ? (direction === "asc" ? "desc" : "asc") : (["year", "cites", "verification"].includes(key) ? "desc" : "asc");
      sort = key; page = 0; draw();
    };
  });
  $$("[data-dt-reset]", host).forEach((button) => { button.onclick = () => reset(groups[button.dataset.dtReset]); });
  $(`#${prefix}Clear`, host).onclick = () => reset(fields);
  $(`#${prefix}PageSize`, host).onchange = () => { page = 0; draw(); };
  const move = (step) => { page += step; draw(); host.scrollIntoView({ block: "start", behavior: "instant" }); };
  $(`#${prefix}Prev`, host).onclick = () => move(-1);
  $(`#${prefix}Next`, host).onclick = () => move(1);
  $$("[data-dt-filter]", host).forEach((button) => {
    const popover = $(`#${button.getAttribute("popovertarget")}`, host);
    const position = () => {
      const rect = button.getBoundingClientRect(), width = popover.offsetWidth, height = popover.offsetHeight;
      popover.style.left = `${Math.max(8, Math.min(rect.right - width, innerWidth - width - 8))}px`;
      popover.style.top = `${Math.max(8, rect.bottom + height + 8 < innerHeight ? rect.bottom + 6 : rect.top - height - 6)}px`;
    };
    popover.addEventListener("toggle", (event) => {
      button.setAttribute("aria-expanded", event.newState === "open" ? "true" : "false");
      if (event.newState === "open") { position(); $("input, select", popover)?.focus({ preventScroll: true }); }
    });
    popover.addEventListener("keydown", (event) => {
      if (event.key === "Escape") { event.stopPropagation(); event.preventDefault(); popover.hidePopover(); button.focus({ preventScroll: true }); }
      if (event.key === "Enter" && event.target.tagName === "INPUT") { event.preventDefault(); popover.hidePopover(); button.focus({ preventScroll: true }); }
    });
  });
  wrap.addEventListener("scroll", () => { $$(".dt-filter-popover:popover-open", host).forEach((p) => p.hidePopover()); }, { passive: true });
  syncPublicationFilters(prefix, all); draw(); hydrateIcons(host);
  const reveal = (id) => {
    let list = filterPublications(all, { ...readPublicationFilters(prefix), sort, direction });
    if (!list.some((p) => p.id === id) && all.some((p) => p.id === id)) {
      reset(fields); list = filterPublications(all, { sort, direction });
    }
    const index = list.findIndex((p) => p.id === id);
    if (index < 0) return;
    const size = Number($(`#${prefix}PageSize`, host).value) || Math.max(list.length, 1);
    page = Math.floor(index / size); draw();
  };
  host.publicationTable = { update, draw, reveal };
  return host.publicationTable;
}
async function pollSnapshots(load, active, apply, running, next) {
  let snapshot = await load();
  while (active()) {
    apply(snapshot);
    if (!running(snapshot)) return;
    await new Promise((resolve) => setTimeout(resolve, 2500));
    if (!active()) return;
    snapshot = await next(snapshot);
  }
}
const staffSources = (p) => [...new Set((p.sources || []).map(sourceKey).filter(Boolean))];
const staffMetric = (p, key) => p[key] == null || p[key] === "" || !Number.isFinite(Number(p[key])) ? null : Number(p[key]);
function filterStaff(people, filters = {}) {
  const q = fold(filters.query), key = filters.sort === "citations" ? "citations" : "article_count";
  return people.map((person, index) => ({ person, index })).filter(({ person: p }) =>
    (!q || fold(p.name).includes(q)) && (!filters.source || (filters.source === "unknown" ? !staffSources(p).length : staffSources(p).includes(sourceKey(filters.source)))))
    .sort((a, b) => {
      if (filters.sort !== "name") {
        const x = staffMetric(a.person, key), y = staffMetric(b.person, key);
        if (x == null && y != null) return 1;
        if (y == null && x != null) return -1;
        if (x != null && y != null && x !== y) return y - x;
      }
      return (a.person.name || "").localeCompare(b.person.name || "", "tr") || a.index - b.index;
    });
}
function mountStaffList(host, prefix, people, options = {}) {
  let all = people, ids = [];
  const filters = options.filters || {};
  host.innerHTML = `<div class="staff-filters"><div class="input slim">${icon("search")}<input id="${prefix}StaffQuery" placeholder="Akademisyen adı" aria-label="Kadroda isim ara" value="${esc(filters.query || "")}"></div>
    <select class="select" id="${prefix}StaffSource" aria-label="Kadro yayın kaynağı"><option value="">Tüm kaynaklar</option></select>
    <select class="select" id="${prefix}StaffSort" aria-label="Kadro sıralaması"><option value="article_count">Makale sayısı</option><option value="citations">Atıf sayısı</option><option value="name">İsim</option></select></div>
    <p class="faint staff-count" id="${prefix}StaffCount"></p><div id="${prefix}StaffRows"></div>`;
  const input = $(`#${prefix}StaffQuery`), source = $(`#${prefix}StaffSource`), sort = $(`#${prefix}StaffSort`), body = $(`#${prefix}StaffRows`);
  sort.value = filters.sort || "article_count";
  const syncSources = () => {
    const values = [...new Set(all.flatMap(staffSources))].sort().map((s) => [s, SRC_TR[s] || s]);
    if (all.some((p) => !staffSources(p).length)) values.push(["unknown", "Kaynak bilgisi yok"]);
    fillFilterOptions(source, values, "Tüm kaynaklar");
  };
  syncSources(); source.value = filters.source || "";
  const draw = () => {
    Object.assign(filters, { query: input.value, source: source.value, sort: sort.value });
    const list = filterStaff(all, filters);
    ids.forEach((id) => S.staffRegistry.delete(id)); ids = [];
    body.innerHTML = list.map(({ person: p }, i) => {
      const id = `staff-${++regSeq}`; ids.push(id);
      S.staffRegistry.set(id, { person: p, mode: options.mode, page: options.page, institution: options.institution });
      const metrics = [["article_count", "makale"], ["citations", "atıf"]].map(([key, label]) => {
        const value = staffMetric(p, key); return value == null ? `${label === "makale" ? "Makale" : "Atıf"} sayısı bilinmiyor` : `${fmtNum(value)} ${label}`;
      }).join(" · ");
      const state = { pending: p.status ? "Sırada" : "Profil henüz toplanmadı", running: "Toplanıyor", done: "Tamamlandı", partial: "Kısmi sonuç", error: "Alınamadı" }[p.status || p.state];
      return `<div class="person staff-person" style="--i:${Math.min(i, 24)}">${avatar(p.name, p.photo)}
        <div class="p-main"><b>${esc(p.name)}</b><span>${esc([p.title, p.department].filter(Boolean).join(" · "))}</span>
          <span class="staff-metrics">${esc(metrics)}</span>${staffSources(p).length ? `<div class="chips">${sourceBadges({ sources: staffSources(p) })}</div>` : ""}${state ? `<span class="faint">${esc(state)}</span>` : ""}</div>
        <div class="p-act">${p.email ? `<a class="icon-btn" href="mailto:${esc(p.email)}" title="${esc(p.email)}">${icon("mail")}</a>` : ""}
          ${safeUrl(p.site_url || p.url) ? `<a class="icon-btn" href="${esc(safeUrl(p.site_url || p.url))}" target="_blank" rel="noopener" title="Kişinin kaynak sayfası">${icon("external")}</a>` : ""}
          <button class="btn sm ${p.chat_id ? "" : "primary"}" data-staff-open="${id}" type="button">${p.chat_id ? "Aç" : "Profil"}</button></div></div>`;
    }).join("") || `<div class="col-empty">Filtreye uygun akademisyen yok.</div>`;
    $(`#${prefix}StaffCount`).textContent = `${fmtNum(list.length)} / ${fmtNum(all.length)} akademisyen`;
    if (options.countElement) options.countElement.textContent = all.length;
    hydrateIcons(body);
  };
  input.oninput = draw; source.onchange = draw; sort.onchange = draw; draw(); hydrateIcons(host);
  return { update(next) { const top = host.scrollTop; all = next; syncSources(); draw(); host.scrollTop = top; }, draw };
}
function openStaffProfile(id) {
  const entry = S.staffRegistry.get(id); if (!entry) return;
  const p = entry.person;
  if (p.chat_id) { closeDrawer(); location.hash = `#/profil/${p.chat_id}`; return; }
  closeDrawer();
  if (entry.mode === "yok" || /akademik\.yok\.gov\.tr/.test(safeUrl(p.url))) {
    startFromYok({ ...p, university: p.university || entry.institution || "" });
  } else startJob(p.site_url || p.url || entry.page, p.name);
}
function paperCard(p, source, i = 0) {
  const id = reg(p, source);
  const authors = (p.authors || []).slice(0, 6).join(", ") + ((p.authors || []).length > 6 ? " vd." : "");
  return `<article class="paper" style="--i:${Math.min(i, 20)}">
    <div class="p-body">
      <div class="p-title" data-open="${id}">${esc(p.title)}</div>
      <div class="p-meta">${authors ? `${esc(authors)} · ` : ""}${p.venue ? `<b>${esc(p.venue)}</b> · ` : ""}${esc(p.year || "Yıl yok")}</div>
      ${p.unit_authors?.length ? `<div class="p-meta">Birimdeki yazar: <b>${esc(p.unit_authors.join(", "))}</b></div>` : ""}
      ${p.person ? `<div class="p-meta">Akademisyen: <b>${esc(p.person)}</b></div>` : ""}
      ${p.abstract ? `<div class="p-abs">${esc(p.abstract)}</div>` : ""}
      <div class="p-tags">${p.publication_kind || p.type ? `<span class="chip">${esc(publicationKind(p))}</span>` : ""}
        ${sourceBadges(p)}
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
// Çeyrek yayının yılına ve alana göre değişir: alanlar farklıysa aralık yazılır (SJR 2024 Q1–Q2), "en iyi" tek başına gösterilmez
function quartileLabel(p) {
  const k = p.quartile;
  if (!k) return "";
  const qs = [...new Set((k.categories || []).map((c) => c.q))].sort();
  const range = qs.length > 1 ? `${qs[0]}–${qs.at(-1)}` : (qs[0] || k.q);
  return `${k.source} ${k.year} ${range}`;
}
function jcrBadge(p) {
  const j = p.jcr;
  if (!j?.categories?.length || !safeUrl(j.url)) return "";
  const qs = [...new Set(j.categories.map((c) => c.q))].sort();
  const range = qs.length > 1 ? `${qs[0]}–${qs.at(-1)}` : qs[0];
  const year = j.year ? String(j.year) : "yıl belirtilmemiş";
  const checked = j.checked_at ? new Date(j.checked_at).toLocaleDateString("tr-TR") : "";
  const tip = `${j.categories.map((c) => `${c.name}: ${c.q} ${c.edition || ""}`).join("; ")}. JCR yılı: ${year}. WoS'tan kontrol: ${checked}. Yayın yılının çeyreği olduğu varsayılmaz.`;
  return `<a class="q-badge jcr" href="${esc(safeUrl(j.url))}" target="_blank" rel="noopener" title="${esc(tip)}">JCR${j.year ? ` ${esc(j.year)}` : ""} ${esc(range)}</a>`;
}

let wosProfileWatch = null;
const wosFinishNotices = new Set();
async function loadWos(r, drawPubs) {
  const tbody = $("#pubs");
  if (!tbody) return;
  if (wosProfileWatch?.tbody === tbody && wosProfileWatch.active()) { wosProfileWatch.wake(); return; }
  wosProfileWatch?.stop();
  let disposed = false, removed = false, request = null, wakeDelay = null, wakeRequested = false, publicationRevision;
  const active = () => !disposed && tbody.isConnected && S.result === r;
  const delay = (ms) => new Promise((resolve) => {
    const finish = () => { clearTimeout(timer); if (wakeDelay === finish) wakeDelay = null; resolve(); };
    const timer = setTimeout(finish, ms); wakeDelay = finish;
    if (!active() || wakeRequested) finish();
  });
  const endpoint = `/api/jobs/${encodeURIComponent(r.job_id)}/wos`;
  const read = async (method) => {
    const controller = new AbortController(); request = controller;
    const timeout = setTimeout(() => controller.abort(), 15000);
    try { return await api(endpoint, { method, ...(method === "POST" ? { body: "{}" } : {}), signal: controller.signal }); }
    finally { clearTimeout(timeout); if (request === controller) request = null; }
  };
  const notifyFailure = (data) => {
    const report = data.publications || {}, reason = data.reason || report.reason || "";
    const status = ["blocked", "error"].includes(data.status) ? data.status : report.status;
    if (!["blocked", "error"].includes(status)) return;
    const key = `${r.job_id}:${status}:${data.finished_at ?? data.revision ?? report.at ?? ""}:${reason}`;
    if (wosFinishNotices.has(key)) return;
    wosFinishNotices.add(key);
    const reasons = {
      access_unavailable: "WoS erişimi sağlanamadı.", search_unavailable: "WoS araması tamamlanamadı.",
      human_verification: "WoS insan doğrulaması istiyor.", manual_expired: "WoS doğrulamasının süresi doldu.",
      manual_cancelled: "WoS doğrulaması atlandı.", time_budget: "WoS taraması ayrılan sürede tamamlanamadı.",
      queue_timeout: "WoS tarama sırası zaman aşımına uğradı.",
    };
    toast(esc(data.message || report.message || reasons[reason] || "WoS kontrolü tamamlanamadı; alınan yayınlar korunuyor."), 7000);
  };
  const apply = (data) => {
    let changed = false;
    const update = data.publication_update;
    if (Array.isArray(update?.publications) && (data.revision == null || data.revision !== publicationRevision)) {
      for (const key of ["publications", "unique_count", "raw_count", "by_source", "paper_verification", "languages", "summary"]) {
        if (Object.hasOwn(update, key)) r[key] = update[key];
      }
      publicationRevision = data.revision;
      changed = true;
    }
    if (data.items && typeof data.items === "object") {
      for (const p of r.publications) {
        const next = data.items[p.id];
        if (JSON.stringify(p.jcr) !== JSON.stringify(next)) changed = true;
        delete p.jcr; if (next) p.jcr = next;
      }
    }
    if (changed) {
      const scroller = view(), top = scroller.scrollTop, left = tbody.closest(".tbl-wrap").scrollLeft;
      updatePublicationStats(r); drawPubs();
      scroller.scrollTop = top; tbody.closest(".tbl-wrap").scrollLeft = left;
    }
  };
  const watch = {
    tbody, active, running: false,
    stop() { disposed = true; request?.abort(); wakeDelay?.(); tbody.dataset.wosLoading = "0"; },
    wake() {
      if (!active() || removed) return;
      wakeRequested = true;
      if (watch.running) wakeDelay?.();
      else void run(true);
    },
  };
  const run = async (getFirst = false) => {
    if (!active() || removed || watch.running) return;
    watch.running = true; tbody.dataset.wosLoading = "1";
    let method = getFirst ? "GET" : "POST", failures = 0, idleRestarts = 0;
    try {
      while (active()) {
        wakeRequested = false;
        let data;
        try { data = await read(method); }
        catch (error) {
          if (!active()) break;
          if ([404, 410].includes(error.status)) {
            removed = true;
            notifyFailure({ status: "error", reason: "profile_missing", message: "WoS kontrolü durdu: profil kaydına artık ulaşılamıyor." });
            break;
          }
          // POST yanıtı kaybolduysa önce mevcut işi sor; ikinci bir iş başlatma.
          method = "GET";
          await delay(Math.min(15000, 2500 * 2 ** Math.min(failures++, 3)));
          continue;
        }
        if (!active()) break;
        failures = 0; apply(data);
        if (["running", "pending"].includes(data.status)) {
          method = "GET"; await delay(2500); continue;
        }
        if (wakeRequested) { method = "GET"; continue; }
        if (data.status === "idle") {
          // Sunucu yeniden başlamış olabilir. Normal POST en fazla iki kez;
          // sonra GET ile bekle, sürekli yeni tarama başlatma.
          if (idleRestarts < 2) {
            idleRestarts += 1; await delay(2500 * idleRestarts); method = "POST";
          } else {
            notifyFailure({ status: "error", reason: "job_interrupted", message: "WoS taraması yeniden başlayamadı; bağlantı izlenmeye devam ediyor." });
            method = "GET"; await delay(15000);
          }
          continue;
        }
        notifyFailure(data);
        break;
      }
    } finally {
      watch.running = false; tbody.dataset.wosLoading = "0";
      if (wakeRequested && active() && !removed) void run(true);
    }
  };
  wosProfileWatch = watch;
  await run();
}
document.addEventListener("wos-verification-solved", () => wosProfileWatch?.wake());

function publicationQuartiles(publications) {
  const counts = { total: 0, src: "" };
  publications.forEach((p) => {
    if (!p.quartile) return;
    counts[p.quartile.q] = (counts[p.quartile.q] || 0) + 1;
    counts.total++; counts.src = p.quartile.source;
  });
  return counts;
}
const sourceDistribution = (r) => Object.entries(r.by_source || {}).map(([k, v]) => `${SRC_TR[k] || k} ${v}`).join(" · ") || "—";
const quartileDistribution = (r, counts) => `${["Q1", "Q2", "Q3", "Q4"].map((k) => `${k} ${counts[k] || 0}`).join(" · ")} · çeyreği yok ${r.publications.length - counts.total}`;
function updatePublicationStats(r) {
  const values = {
    "#profilePubCount": fmtNum(r.unique_count),
    '[data-tab="pubs"] .n': fmtNum(r.unique_count),
    "#profileCitesCount": fmtNum(r.publications.reduce((sum, p) => sum + (p.citations || 0), 0)),
    "#profileSources": sourceDistribution(r),
    "#profileSummary": r.summary || "",
  };
  const counts = publicationQuartiles(r.publications);
  values["#profileQuartiles"] = quartileDistribution(r, counts);
  for (const [selector, value] of Object.entries(values)) {
    const el = $(selector); if (el) el.textContent = value;
  }
  syncPublicationFilters("pub", r.publications);
}

const quartileAreas = (p) => (p.quartile?.categories || []).map((c) => `${c.name} (${c.q})`).join("; ");
// Excel (.xlsx) dosyası: bağımlılıksız, sıkıştırmasız ZIP içinde en küçük OOXML çalışma kitabı
const CRC_T = Array.from({ length: 256 }, (_, n) => { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; return c >>> 0; });
const crc32 = (b) => { let c = 0xffffffff; for (const x of b) c = CRC_T[(c ^ x) & 0xff] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; };
function zipStore(files) {
  const enc = new TextEncoder(), parts = [], central = [];
  let off = 0;
  const u16 = (v) => [v & 255, (v >>> 8) & 255], u32 = (v) => [v & 255, (v >>> 8) & 255, (v >>> 16) & 255, (v >>> 24) & 255];
  for (const [name, text] of files) {
    const n = enc.encode(name), d = enc.encode(text), c = crc32(d);
    const common = [...u16(20), ...u16(0x0800), ...u16(0), ...u16(0), ...u16(0x21), ...u32(c), ...u32(d.length), ...u32(d.length), ...u16(n.length), ...u16(0)];
    const local = new Uint8Array([...u32(0x04034b50), ...common]);
    parts.push(local, n, d);
    central.push(new Uint8Array([...u32(0x02014b50), ...u16(20), ...common, ...u16(0), ...u16(0), ...u16(0), ...u32(0), ...u32(off)]), n);
    off += local.length + n.length + d.length;
  }
  const size = central.reduce((s, x) => s + x.length, 0);
  return new Blob([...parts, ...central, new Uint8Array([...u32(0x06054b50), 0, 0, 0, 0, ...u16(files.length), ...u16(files.length), ...u32(size), ...u32(off), 0, 0])]);
}
function exportXlsx(list, name, meta = {}) {
  const cols = [["Başlık", (p) => p.title, 60], ["Yazarlar", (p) => (p.authors || []).join("; "), 40], ["Yıl", (p) => +p.year || "", 8], ["Yayın tarihi", (p) => p.date ? isoToTr(p.date) : "", 13],
    ["Kategori", catLabel, 16], ["Yayın yeri", (p) => p.venue, 32], ["Dergi çeyreği", (p) => quartileLabel(p), 18], ["Çeyrek alanları", quartileAreas, 36], ["Tür", publicationKind, 18], ["Durum", publicationStatusLabel, 38], ["DOI", (p) => normDoi(p.doi), 26],
    ["Atıf", (p) => p.citations ?? "", 8], ["Kaynak", (p) => (p.sources || [p.source]).filter(Boolean).map((s) => SRC_TR[s] || s).join(" + "), 22],
    ["Akademisyen", (p) => (p.unit_authors || []).join("; ") || p.person || meta.person || "", 24]];
  const x = (v) => String(v ?? "").replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g, "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").slice(0, 32000);
  const ref = (c, r) => `${String.fromCharCode(65 + c)}${r}`;
  const cell = (v, c, r, s = 0) => typeof v === "number" && Number.isFinite(v) ? `<c r="${ref(c, r)}" s="${s}"><v>${v}</v></c>`
    : `<c r="${ref(c, r)}" s="${s}" t="inlineStr"><is><t xml:space="preserve">${x(v)}</t></is></c>`;
  const rows = [`<row r="1">${cols.map(([h], c) => cell(h, c, 1, 1)).join("")}</row>`,
    ...list.map((p, i) => `<row r="${i + 2}">${cols.map(([, f], c) => cell(f(p), c, i + 2)).join("")}</row>`)];
  const last = ref(cols.length - 1, list.length + 1);
  const sheet = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
<cols>${cols.map(([, , w], c) => `<col min="${c + 1}" max="${c + 1}" width="${w}" customWidth="1"/>`).join("")}</cols>
<sheetData>${rows.join("")}</sheetData><autoFilter ref="A1:${last}"/></worksheet>`;
  const title = x([meta.person, meta.note].filter(Boolean).join(" · ") || "Yayınlar");
  const files = [
    ["[Content_Types].xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/></Types>`],
    ["_rels/.rels", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/></Relationships>`],
    ["docProps/core.xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>${title}</dc:title><dc:creator>Akademik İz</dc:creator></cp:coreProperties>`],
    ["xl/workbook.xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Yayınlar" sheetId="1" r:id="rId1"/></sheets><definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0" hidden="1">'Yayınlar'!$A$1:$${last.replace(/(\d+)$/, "$$$1")}</definedName></definedNames></workbook>`],
    ["xl/_rels/workbook.xml.rels", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>`],
    ["xl/styles.xml", `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFEDEDED"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="2"><xf fontId="0" fillId="0" borderId="0" xfId="0"/><xf fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>`],
    ["xl/worksheets/sheet1.xml", sheet],
  ];
  const blob = zipStore(files);
  const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: `${name}.xlsx` });
  document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
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
  const header = `${head}% ${list.length} yayın${meta.note ? " · " + meta.note : ""} · Akademik İz · ${new Date().toLocaleDateString("tr-TR")}\n\n`;
  download(`${name}.bib`, header + entries.join("\n\n"), "application/x-bibtex;charset=utf-8");
}
const exportButtons = (listKey) => `<button class="btn sm" data-export="${listKey}" type="button">${icon("download")}Dışa aktar</button>`;

// Kaynakların karışık tür adlarını birkaç anlaşılır kategoriye indirger
const PUB_CATS = [["article", "Makale"], ["proceedings", "Bildiri"], ["book", "Kitap / kitap bölümü"], ["thesis", "Tez"],
  ["preprint", "Ön baskı"], ["data", "Veri seti"], ["other", "Diğer"], ["none", "Türü belirtilmemiş"]];
function pubCat(p) {
  const t = fold(p.type || "");
  if (!t) return "none";
  if (/review|editorial|erratum|paratext|reference|supplement|presentation|deliverable|patent|software/.test(t) && !/^review$/.test(t)) return "other";
  if (/article|^review$|data paper|data-paper/.test(t)) return /data/.test(t) ? "data" : "article";
  if (/proceed|conference|bildiri/.test(t)) return "proceedings";
  if (/book|chapter|monograph/.test(t)) return "book";
  if (/thesis|dissertation|tez/.test(t)) return "thesis";
  if (/preprint|posted/.test(t)) return "preprint";
  if (/data/.test(t)) return "data";
  return "other";
}
const catLabel = (p) => Object.fromEntries(PUB_CATS)[pubCat(p)];

// Yayın tarihi aralığı: kesin gün yoksa ay, o da yoksa yılın tamamı. Dönüş: [ilk gün, son gün] "YYYY-MM-DD"
function pubSpan(p) {
  const d = String(p.date || ""), y = +p.year || +d.slice(0, 4);
  if (!y) return null;
  if (/^\d{4}-\d{2}-\d{2}$/.test(d)) return [d, d];
  if (/^\d{4}-\d{2}$/.test(d)) return [`${d}-01`, `${d}-${String(new Date(+d.slice(0, 4), +d.slice(5, 7), 0).getDate()).padStart(2, "0")}`];
  return [`${y}-01-01`, `${y}-12-31`];
}
const isoToTr = (iso) => iso.split("-").reverse().join(".");
function trToIso(text, end = false) {
  const m = String(text || "").trim().match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$/);
  if (!m) return "";
  const [d, mo, y] = [+m[1], +m[2], +m[3]], dt = new Date(y, mo - 1, d);
  return dt.getFullYear() === y && dt.getMonth() === mo - 1 && dt.getDate() === d ? `${y}-${String(mo).padStart(2, "0")}-${String(d).padStart(2, "0")}` : "";
}
const pubDateTr = (p) => p.date ? isoToTr(p.date) : (p.year || "");

// Dışa aktarma penceresi: tarih aralığı (gün.ay.yıl) her listede, kategori seçimi akademisyen profilinde
function exportModal(listKey) {
  const list = S.lists[listKey] || [];
  if (!list.length) { toast("Dışa aktarılacak yayın yok."); return; }
  const meta = S.listMeta[listKey] || {};
  const spans = list.map(pubSpan).filter(Boolean);
  const first = spans.length ? spans.map((x) => x[0]).sort()[0] : "", last = spans.length ? spans.map((x) => x[1]).sort().at(-1) : "";
  const noDate = list.length - spans.length, exact = list.filter((p) => /^\d{4}-\d{2}-\d{2}$/.test(p.date || "")).length;
  const cats = PUB_CATS.map(([k, l]) => [k, l, list.filter((p) => pubCat(p) === k).length]).filter(([, , n]) => n);
  openModal(`<h2>Yayınları dışa aktar</h2>
    <p class="muted" style="margin:6px 0 0">${esc(meta.person || meta.file || "Liste")} · ${fmtNum(list.length)} yayın${first ? ` · ${first.slice(0, 4)}–${last.slice(0, 4)}` : ""}</p>
    <form id="exForm" class="form-grid" autocomplete="off" novalidate>
      ${first ? `<div class="ex-row">
        <div class="field"><label for="exFrom">Başlangıç tarihi <small>gün.ay.yıl</small></label>
          <div class="input">${icon("calendar")}<input id="exFrom" inputmode="numeric" maxlength="10" placeholder="gg.aa.yyyy" value="${isoToTr(first)}"></div></div>
        <div class="field"><label for="exTo">Bitiş tarihi <small>gün.ay.yıl</small></label>
          <div class="input">${icon("calendar")}<input id="exTo" inputmode="numeric" maxlength="10" placeholder="gg.aa.yyyy" value="${isoToTr(last)}"></div></div></div>
        <p class="faint ex-note">${fmtNum(exact)} yayının tam tarihi biliniyor. Yalnız ayı ya da yılı bilinen yayınlar, o ay ya da yıl aralığa değiyorsa eklenir.</p>` : ""}
      ${noDate ? `<label class="ex-check"><input type="checkbox" id="exNoYear" checked> Tarihi bilinmeyen ${fmtNum(noDate)} yayını da ekle</label>` : ""}
      ${meta.cats && cats.length > 1 ? `<div class="field"><label>Kategori <small>· en az birini seçin</small></label><div class="ex-cats">
        ${cats.map(([k, l, n]) => `<label class="ex-check"><input type="checkbox" name="exCat" value="${k}" checked> ${esc(l)} <span class="faint">${fmtNum(n)}</span></label>`).join("")}</div></div>` : ""}
      <div class="field"><label>Biçim</label><div class="ex-cats">
        <label class="ex-check"><input type="radio" name="exFmt" value="xlsx" checked> Excel <span class="faint">.xlsx</span></label>
        <label class="ex-check"><input type="radio" name="exFmt" value="bib"> BibTeX <span class="faint">Zotero, Mendeley</span></label></div></div>
      <div class="actions" style="justify-content:flex-end"><span class="faint" id="exCount"></span><span class="spacer"></span>
        <button type="button" class="btn ghost" data-close>Vazgeç</button>
        <button class="btn primary" id="exGo" type="submit">${icon("download")}İndir</button></div>
    </form>`);
  const form = $("#exForm");
  // Yazarken noktaları kendisi koyar: 01022020 → 01.02.2020
  form.querySelectorAll("#exFrom, #exTo").forEach((inp) => inp.addEventListener("input", () => {
    const digits = inp.value.replace(/\D/g, "").slice(0, 8);
    if (/^[\d.]*$/.test(inp.value) && inp.value.length >= (+inp.dataset.len || 0)) inp.value = [digits.slice(0, 2), digits.slice(2, 4), digits.slice(4)].filter(Boolean).join(".");
    inp.dataset.len = inp.value.length; update();
  }));
  const pick = () => {
    const fIn = $("#exFrom"), tIn = $("#exTo");
    let from = fIn ? trToIso(fIn.value) : "", to = tIn ? trToIso(tIn.value) : "";
    const bad = (fIn && !from) || (tIn && !to);
    fIn?.closest(".input").classList.toggle("bad", !!fIn && !from); tIn?.closest(".input").classList.toggle("bad", !!tIn && !to);
    if (from && to && from > to) [from, to] = [to, from];
    const withNoDate = $("#exNoYear")?.checked ?? true;
    const on = new Set([...form.querySelectorAll('[name="exCat"]:checked')].map((x) => x.value));
    const useCats = !!form.querySelector('[name="exCat"]');
    const out = bad ? [] : list.filter((p) => {
      const sp = pubSpan(p);
      return (sp ? (!from || (sp[1] >= from && sp[0] <= to)) : withNoDate) && (!useCats || on.has(pubCat(p)));
    });
    return { out, from, to, on, useCats, bad };
  };
  const update = () => {
    const { out, bad } = pick();
    $("#exCount").textContent = bad ? "Tarihi gün.ay.yıl biçiminde yazın (ör. 01.02.2020)." : `${fmtNum(out.length)} yayın indirilecek`;
    $("#exGo").disabled = !out.length;
  };
  form.addEventListener("change", update); update();
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const { out, from, to, on, useCats } = pick();
    if (!out.length) return;
    const stem = fold(meta.file || listKey).replace(/ /g, "-").slice(0, 60) || "akademik-iz";
    const range = first && (from !== first || to !== last) ? `-${from}_${to}` : "";
    const catPart = useCats && on.size < cats.length ? `-${[...on].join("-")}` : "";
    const name = `${stem}-yayinlar${range}${catPart}-${new Date().toISOString().slice(0, 10)}`;
    const note = [range && `${isoToTr(from)}–${isoToTr(to)}`, catPart && cats.filter(([k]) => on.has(k)).map(([, l]) => l).join(", ")].filter(Boolean).join(" · ");
    (form.querySelector('[name="exFmt"]:checked').value === "xlsx" ? exportXlsx : exportBib)(out, name, { ...meta, note });
    closeModal(); toast(`${fmtNum(out.length)} yayın indirildi.`);
  });
}

// ------------------------------------------------------------------- yayın ayrıntısı (modal)
function openModal(html) {
  $("#modalBody").innerHTML = html; hydrateIcons($("#modalBody"));
  $("#modal").classList.remove("closing");
  $("#modal").hidden = false;
}
function closeModal() {
  S.paperRequest?.abort(); S.paperRequest = null;
  const m = $("#modal");
  if (m.hidden) return;
  if (calmMotion()) { m.hidden = true; return; }
  m.classList.add("closing");
  setTimeout(() => { if (m.classList.contains("closing")) { m.hidden = true; m.classList.remove("closing"); } }, 170);
}

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
  openModal(`<div class="m-kicker">${sourceBadges(p)}
      <span>${esc(p.year || "")}</span>${p.citations != null ? `<span>· ${fmtNum(p.citations)} atıf</span>` : ""}</div>
    <h2 class="m-title">${esc(p.title)}</h2>
    <div id="mMeta" class="muted">${esc(p.venue || "")}</div>
    <div class="m-publication-status">${publicationStatusHtml(p)}</div>
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

// =================================================================== ANA SAYFA
function viewHome() {
  setCrumbs([{ label: "Ana sayfa" }]);
  const recent = S.chats.slice(0, 5);
  const entries = [["#/akademisyenler", "users", "Akademisyenler", "cProfiles", "profil incelendi"], ["#/universiteler", "building", "Üniversiteler", "cUnis", "üniversite, YÖK'ten"],
    ["#/firmalar", "briefcase", "Firmalar", "cFirms", "Ar-Ge ve tasarım firması"], ["#/ara", "book", "Konular", "", "Bir alanda yazılmış yayınlar"]];
  setView(`
    <section class="hero">
      <div class="hero-bg" aria-hidden="true"><span></span><span></span></div>
      <h1 class="rise" style="--i:0">Akademisyen, üniversite, firma ya da konu.<br>Hepsi tek aramada.</h1>
      <p class="lead rise" style="--i:1">YÖK, TR Dizin, OpenAlex, TÜBİTAK ve patent kayıtları kanıtlarıyla bir arada.</p>
      <div class="omni rise" id="omni" style="--i:2">
        <div class="input">${icon("search")}<input id="omniQ" autocomplete="off" aria-label="Ara" spellcheck="false"></div>
        <div class="omni-pop" id="omniPop" hidden></div>
      </div>
      <div class="hero-try rise" style="--i:3"><span>Dene:</span>${["Şimşek Demir", "TED Üniversitesi", "Aselsan", "derin öğrenme"].map((x) => `<button class="chip" type="button" data-try="${esc(x)}">${esc(x)}</button>`).join("")}</div>
    </section>
    <div class="entry-grid stagger">${entries.map(([href, ic, title, id, sub], i) => `<a class="card entry" href="${href}" style="--i:${i + 3}">
      <span class="fi">${icon(ic)}</span><b>${title}</b><span class="e-sub">${id ? `<span id="${id}">—</span> ` : ""}${sub}</span><span class="e-go">${icon("arrow")}</span></a>`).join("")}</div>
    ${recent.length ? `<div class="card list-card" style="margin-top:18px">
      <div class="lc-head"><h3>Son incelenenler</h3><a href="#/akademisyenler" class="faint">Tümü →</a></div>
      <div class="stagger">${recent.map((c, i) => profileRow(c, i + 6)).join("")}</div></div>` : ""}`);
  setupOmni();
  api("/api/overview").then((o) => {
    [["cProfiles", o.profiles], ["cUnis", o.universities], ["cFirms", o.firms]].forEach(([id, n]) => {
      const el = document.getElementById(id);
      if (el) { el.dataset.count = n; el.textContent = fmtNum(n); animateCounts(el.parentElement); }
    });
  }).catch(() => {});
}

// Tek arama kutusu: yerel öneriler (profil, üniversite, firma) + "akademisyen ara" ve "konu ara" eylemleri.
function setupOmni() {
  const input = $("#omniQ"), pop = $("#omniPop");
  typePlaceholder(input, ["Şimşek Demir", "Orta Doğu Teknik Üniversitesi", "Aselsan", "derin öğrenme", "Ömer Nezih Gerek"]);
  let seq = 0, timer, active = 0;
  const links = () => $$(".omni-item", pop);
  const mark = () => links().forEach((a, i) => a.classList.toggle("on", i === active));
  const draw = (q, d) => {
    const eq = encodeURIComponent(q);
    const rows = [
      ...d.people.map((c) => ({ g: "İncelenen akademisyenler", href: `#/profil/${c.id}`, av: avatar(c.name, profilePhoto(c)), t: c.name, s: [c.title, c.institution].filter(Boolean).join(" · ") })),
      ...d.universities.map((u) => ({ g: "Üniversiteler", href: `#/universite/${u.id}`, ic: "building", t: u.name, s: "Fakülte, bölüm, kadro" })),
      ...d.firms.map((f) => ({ g: "Firmalar", href: `#/firma/${f.id}`, ic: "briefcase", t: f.name, s: f.cities.join(", ") })),
      { g: "Ara", href: `#/akademisyenler?q=${eq}`, ic: "users", t: `“${q}” adlı akademisyeni ara`, s: "YÖK Akademik" },
      { g: "Ara", href: `#/ara?q=${eq}`, ic: "book", t: `“${q}” konusunu ara`, s: "Yayınlar" },
    ];
    let group = "";
    pop.innerHTML = rows.map((r, i) => {
      const head = r.g !== group ? `<div class="omni-g">${esc(r.g)}</div>` : "";
      group = r.g;
      return `${head}<a class="omni-item" href="${esc(r.href)}" style="--i:${i}">${r.av || `<span class="fi">${icon(r.ic)}</span>`}<span class="oi-main"><b>${esc(r.t)}</b>${r.s ? `<span>${esc(r.s)}</span>` : ""}</span></a>`;
    }).join("");
    hydrateIcons(pop); active = 0; mark(); pop.hidden = false;
  };
  const search = async () => {
    const q = input.value.trim(), mine = ++seq;
    if (fold(q).length < 2) { pop.hidden = true; return; }
    let d;
    try { d = await api(`/api/lookup?q=${encodeURIComponent(q)}`); } catch { d = { people: [], universities: [], firms: [] }; }
    if (mine === seq && input.isConnected) draw(q, d);
  };
  input.oninput = () => { clearTimeout(timer); timer = setTimeout(search, 160); };
  input.onfocus = () => { if (input.value.trim() && pop.innerHTML) pop.hidden = false; };
  input.onkeydown = (e) => {
    const all = links();
    if (e.key === "Escape") { pop.hidden = true; return; }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (all.length) { active = (active + (e.key === "ArrowDown" ? 1 : -1) + all.length) % all.length; mark(); all[active].scrollIntoView({ block: "nearest" }); }
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (!pop.hidden && all[active]) { location.hash = all[active].getAttribute("href"); return; }
      const q = input.value.trim();
      if (q) location.hash = `#/akademisyenler?q=${encodeURIComponent(q)}`;
    }
  };
  $$("[data-try]").forEach((b) => { b.onclick = () => { input.value = b.dataset.try; input.focus(); search(); }; });
}

// YÖK'ün alan kodlarını ve metinden yanlış ayrılmış parçaları ilgi alanı listelerinden temizler
function cleanInterest(v) {
  const s = String(v || "").replace(/\s+[0-9A-F]{16}$/, "").trim();
  return s.length > 2 && !/^(include|but are not limited to|theses)$/i.test(s) ? s : "";
}
const chatInterests = (c) => [...new Map((c.interests || []).map(cleanInterest).filter(Boolean).map((x) => [fold(x), x])).values()];

function profileRow(c, i = 0) {
  const ints = chatInterests(c);
  return `<div class="person-row" style="--i:${Math.min(i, 24)}" data-chat="${esc(c.id)}" data-q="${esc(fold(`${c.name} ${c.institution || ""}`))}" data-ints="${esc(ints.map(fold).join("|"))}">
    ${avatar(c.name, profilePhoto(c))}
    <div class="pr-main"><b>${esc(c.name || "?")}</b><span>${esc([c.title, c.institution].filter(Boolean).join(" · "))}</span>
      ${ints.length ? `<span class="faint">${esc(ints.slice(0, 3).join(" · "))}</span>` : ""}</div>
    <span class="chip">${fmtNum(c.papers)} yayın</span>
    <button class="h-del" data-delchat="${esc(c.id)}" type="button" aria-label="Sil" title="Profili sil">${icon("x")}</button></div>`;
}

// =================================================================== AKADEMİSYENLER
const existingChat = (p) => S.chats.find((c) => fold(c.name) === fold(p.name)
  && (!c.institution || fold(c.institution).includes(fold(p.university)) || fold(p.university).includes(fold(c.institution))));
const startFromYok = (p) => startJob(p.university, p.name, () => post("/api/jobs", { name: p.name, yok_url: p.url, university: p.university, department: p.department || p.faculty || "", email: p.email || "" }));

async function viewPeople(q = "") {
  setCrumbs([{ label: "Ana sayfa", href: "#/" }, { label: "Akademisyenler" }]);
  await loadChats();
  // Filtre seçenekleri: en çok kişide geçen alan üstte; aynı alan yazım farkıyla tekrar etmez
  const interestMap = new Map();
  S.chats.forEach((c) => chatInterests(c).forEach((x) => {
    const e = interestMap.get(fold(x)) || [fold(x), x, 0];
    e[2]++; interestMap.set(fold(x), e);
  }));
  const interestOpts = [...interestMap.values()].sort((a, b) => b[2] - a[2] || a[1].localeCompare(b[1], "tr"));
  setView(`<div class="section-head"><div><h1>Akademisyenler</h1><p>Adı YÖK'te arayın, doğru kişiyi seçin; profil tüm kaynaklardan hazırlansın.</p></div>
      <div class="actions"><button class="btn ghost sm" type="button" data-byurl>${icon("globe")}Site bağlantısıyla başlat</button></div></div>
    <form class="card quick-search" id="pSearch"><div class="input">${icon("search")}<input id="pQ" value="${esc(q)}" placeholder="Ad Soyad, ör. Şimşek Demir" autocomplete="off"></div>
      <button class="btn primary" type="submit">YÖK'te ara</button></form>
    <div id="pResults"></div>
    <div class="row-head"><h3>İncelenen profiller</h3><span class="count">${S.chats.length}</span><span class="spacer"></span>
      ${S.chats.length ? `${interestOpts.length ? `<select class="select int-select" id="pInterest" aria-label="İlgi alanı"><option value="">Tüm ilgi alanları</option>${interestOpts.map(([k, l, n]) => `<option value="${esc(k)}">${esc(l)} (${n})</option>`).join("")}</select>` : ""}
        <div class="input slim">${icon("search")}<input data-filter="pList" placeholder="Listede ara"></div><button class="link" type="button" data-clearall>Tümünü sil</button>` : ""}</div>
    <div class="card list-card" id="pList">${S.chats.length ? `<div class="stagger">${S.chats.map(profileRow).join("")}</div>`
      : emptyState("users", "Henüz profil yok", "Yukarıdan bir akademisyen arayın.")}</div>`);
  $("#pSearch").addEventListener("submit", (e) => {
    e.preventDefault();
    const v = $("#pQ").value.trim();
    if (fold(v).length < 3) { toast("En az 3 harf yazın."); return; }
    const next = `#/akademisyenler?q=${encodeURIComponent(v)}`;
    if (location.hash === next) searchPeople(v); else location.hash = next;
  });
  const intSel = $("#pInterest");
  if (intSel) intSel.onchange = () => {
    let shown = 0;
    $$("#pList .person-row").forEach((row) => {
      const hit = !intSel.value || row.dataset.ints.split("|").includes(intSel.value);
      row.classList.toggle("int-off", !hit); shown += hit;
    });
    $(".row-head .count").textContent = shown;
  };
  if (q) searchPeople(q); else $("#pQ").focus();
}

async function searchPeople(q) {
  const box = $("#pResults");
  box.innerHTML = `<div class="card list-card result-card"><div class="loading-line"><span class="spinner"></span>YÖK Akademik'te aranıyor…</div>${skeleton(2)}</div>`;
  let items;
  try { ({ items } = await api(`/api/people/search?q=${encodeURIComponent(q)}`)); }
  catch (e) { box.innerHTML = `<div class="notice err result-card">${icon("info")}<div>${esc(e.message)}</div></div>`; hydrateIcons(box); return; }
  if (!box.isConnected) return;
  S.candidates = items;
  box.innerHTML = items.length ? `<div class="card list-card result-card"><div class="lc-head"><h3>YÖK'te bulunanlar</h3><span class="count">${items.length}</span></div>
      <div class="stagger">${items.map(candidateRow).join("")}</div></div>`
    : `<div class="card result-card">${emptyState("search", `“${q}” YÖK'te bulunamadı`, "Yazımı kontrol edin. Akademisyen YÖK'te yoksa kurum sitesinin bağlantısıyla başlatabilirsiniz; aradığınız bir konuysa Konular'a bakın.",
      `<div class="actions" style="justify-content:center;margin-top:14px"><button class="btn sm" type="button" data-byurl="${esc(q)}">${icon("globe")}Site bağlantısıyla başlat</button>
       <a class="btn sm" href="#/ara?q=${encodeURIComponent(q)}">${icon("book")}Konu olarak ara</a></div>`)}</div>`;
  hydrateIcons(box);
}

function candidateRow(p, i) {
  const chat = existingChat(p);
  return `<div class="person-row plain" style="--i:${Math.min(i, 24)}">${avatar(p.name, p.photo)}
    <div class="pr-main"><b>${esc(p.name)}</b><span>${esc([p.title, p.university].filter(Boolean).join(" · "))}</span>
      <span class="faint">${esc([p.faculty, p.department].filter(Boolean).join(" / "))}</span></div>
    ${p.orcid ? `<a class="chip teal hide-sm" href="https://orcid.org/${esc(p.orcid)}" target="_blank" rel="noopener">ORCID</a>` : ""}
    ${chat ? `<button class="btn sm" type="button" data-chat="${esc(chat.id)}">Profili aç</button>` : `<button class="btn sm primary" type="button" data-candidate="${i}">${icon("sparkle")}Profil çıkar</button>`}</div>`;
}

// =================================================================== YENİ AKADEMİSYEN
function newPersonModal(prefUrl = "", prefName = "") {
  openModal(`<h2>Site bağlantısıyla başlat</h2><p class="muted" style="margin:6px 0 0">YÖK'te bulunmayan kişiler için: kurumun kadro ya da kişi sayfası bağlantısını ve adı girin.</p>
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

async function startJob(sub, name, create, verb = "hazırlanıyor") {
  let job;
  try { job = await (create ? create() : post("/api/jobs", { url: sub, name })); } catch (e) { toast(esc(e.message)); return; }
  const node = document.createElement("div");
  node.className = "card job enter";
  node.innerHTML = `<div class="m-kicker"><span class="spinner"></span>Profil ${verb}</div>
    <h2 style="margin-top:10px">${esc(name)}</h2><div class="job-sub">${esc(sub)}</div>
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
    loadFav();
    if (location.hash === `#/is/${job.id}`) { S.result = r; S.chatId = r.chat_id; location.hash = `#/profil/${r.chat_id}`; return; }
    if (S.result?.chat_id === r.chat_id) {  // yenilenen profil o sırada açıksa yerinde güncellenir
      S.result = r;
      if (location.hash === `#/profil/${r.chat_id}`) renderProfile(r, null);
    }
    toast(`${icon("user")} <span><b>${esc(r.profile.name)}</b> profili hazır. <a href="#/profil/${esc(r.chat_id)}">Aç</a></span>`, 8000);
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
      else $(".now", node).textContent = "Sonuç alınamadı; profil hazırsa Akademisyenler listesinde görünür.";
    };
    poll();
  };
}

function viewJob(jid) {
  const job = S.jobs[jid];
  setCrumbs([{ label: "Ana sayfa", href: "#/" }, { label: job ? job.name : "Profil" }]);
  if (!job) { setView(emptyState("clock", "Bu iş bulunamadı", "Sayfa yenilendiği için ilerleme bilgisi kayboldu. Tamamlanan profiller Akademisyenler listesinde.")); return; }
  const v = view(); v.innerHTML = ""; v.appendChild(job.node); v.scrollTop = 0;
}

// =================================================================== ÜNİVERSİTELER (YÖK)
async function viewUnis() {
  setCrumbs([{ label: "Ana sayfa", href: "#/" }, { label: "Üniversiteler" }]);
  setView(`<div class="section-head"><div><h1>Üniversiteler</h1><p id="uSub">YÖK Akademik'teki üniversiteler. Birini seçin: fakülte, bölüm, kadro.</p></div></div>
    <div class="toolbar"><div class="input">${icon("search")}<input id="uQ" data-filter="uGrid" placeholder="Üniversite ara" autocomplete="off"></div></div>
    <div id="uGrid" class="uni-grid">${skeleton(6)}</div>`);
  let u;
  try { u = await api("/api/universities"); } catch (e) { $("#uGrid").innerHTML = `<div class="card">${emptyState("building", "Liste alınamadı", esc(e.message))}</div>`; hydrateIcons($("#uGrid")); return; }
  const grid = $("#uGrid");
  if (!grid) return;
  $("#uSub").textContent = `YÖK Akademik'teki ${u.items.length} üniversite. Birini seçin: fakülte, bölüm, kadro.`;
  grid.classList.add("stagger");
  grid.innerHTML = u.items.map((x, i) => `<a class="card uni-card" href="#/universite/${esc(x.id)}" style="--i:${Math.min(i, 12)}" data-q="${esc(fold(x.name))}">
    <span class="uni-mark">${esc(initials(x.name.replace(/Üniversitesi/g, "")))}</span><span class="uc-main"><b>${esc(x.name)}</b>${x.people.length ? `<span>${x.people.length} profil incelendi</span>` : ""}</span>${icon("chevron")}</a>`).join("");
  hydrateIcons(grid);
}

async function viewUni(uid) {
  setCrumbs([{ label: "Ana sayfa", href: "#/" }, { label: "Üniversiteler", href: "#/universiteler" }, { label: "…" }]);
  if (S.uni?.id !== uid) S.uni = { id: uid, data: null, fac: null, facData: null, dep: null };
  const d = S.uni, col = (id, ic, title, ph, body) => `<section class="card col" id="${id}">
      <div class="col-head"><span class="ch-icon">${icon(ic)}</span><h3>${title}</h3><span class="count" id="${id}N"></span></div>
      <div class="col-filter"><div class="input">${icon("search")}<input data-filter="${id}" placeholder="${ph}"></div></div>
      <div class="col-body">${body}</div></section>`;
  setView(`<div class="card org-head">
      <div class="org-logo">${icon("building")}</div>
      <div style="min-width:0"><h1 id="uName">${esc(d.data?.name || "Üniversite")}</h1><div class="meta" id="uMeta"></div></div>
      <div class="actions" id="uAct"></div></div>
    <div class="miller">${col("colFac", "layers", "Fakülteler", "Fakültelerde ara", skeleton(7))}
      ${col("colDep", "grid", "Bölümler", "Bölümlerde ara", `<div class="col-empty">Soldan bir fakülte seçin.</div>`)}
      ${col("colStaff", "users", "Akademisyenler", "Akademisyenlerde ara", `<div class="col-empty">Bir bölüm seçin.</div>`)}</div>`);
  const facultyColumn = $("#colFac");
  if (!d.data) {
    try { d.data = await api(`/api/universities/${encodeURIComponent(uid)}`); }
    catch (e) { if (facultyColumn.isConnected) $(".col-body", facultyColumn).innerHTML = `<div class="col-empty">${esc(e.message)}</div>`; return; }
    if (S.uni !== d || !facultyColumn.isConnected) return;
  }
  renderUni();
  if (d.facData) { renderYokDeps(); if (d.dep != null) renderYokStaff(); }
}

function renderUni() {
  const d = S.uni, items = d.data.items;
  setCrumbs([{ label: "Ana sayfa", href: "#/" }, { label: "Üniversiteler", href: "#/universiteler" }, { label: d.data.name }]);
  $("#uName").textContent = d.data.name;
  $("#uMeta").innerHTML = `<span>Kaynak: YÖK Akademik</span>${d.data.home ? `<span>${esc(new URL(d.data.home).hostname.replace(/^www\./, ""))}</span>` : ""}`;
  $("#uAct").innerHTML = d.data.home ? `<a class="btn sm" href="${esc(safeUrl(d.data.home))}" target="_blank" rel="noopener">${icon("globe")}Kurum sitesi</a>
    <button class="btn sm primary" id="uNewPerson" type="button">${icon("plus")}Akademisyen ara</button>` : "";
  if ($("#uNewPerson")) $("#uNewPerson").onclick = () => newPersonModal(d.data.home);
  hydrateIcons($("#uAct"));
  $("#colFacN").textContent = items.length;
  $("#colFac .col-body").innerHTML = items.length ? `<div class="stagger">${items.map((u, i) => `<div class="unit ${d.fac === i ? "active" : ""}" data-unit="yfac" data-i="${i}" style="--i:${Math.min(i, 24)}" data-q="${esc(fold(u.name))}">
      <div class="u-main"><b>${esc(u.name)}</b></div>${icon("chevron")}</div>`).join("")}</div>` : `<div class="col-empty">Bu üniversitenin birimleri YÖK'te listelenmemiş.</div>`;
  hydrateIcons($("#colFac"));
}

async function selectYokFaculty(i) {
  const d = S.uni, fac = d.data.items[i], request = Symbol("faculty"), hash = location.hash;
  d.facRequest = request; d.fac = i; d.dep = null; d.facData = null;
  const body = $("#colDep .col-body");
  const active = () => S.uni === d && d.facRequest === request && body.isConnected && location.hash === hash;
  $$("#colFac .unit").forEach((x) => x.classList.toggle("active", +x.dataset.i === i));
  body.innerHTML = `<div class="loading-line"><span class="spinner"></span>Kadro YÖK'ten alınıyor…</div>${skeleton(6)}`;
  $("#colStaff .col-body").innerHTML = `<div class="col-empty">Bir bölüm seçin.</div>`;
  $("#colStaffN").textContent = ""; $("#colDepN").textContent = "";
  try {
    const data = await api(`/api/universities/${encodeURIComponent(d.id)}/faculty?name=${encodeURIComponent(fac.raw)}`);
    if (!active()) return;
    d.facData = data; renderYokDeps();
  } catch (e) { if (active()) body.innerHTML = `<div class="col-empty">${esc(e.message)}</div>`; }
}

function renderYokDeps() {
  const d = S.uni, f = d.facData;
  $("#colDepN").textContent = f.departments.length;
  const row = (name, n, i, q) => `<div class="unit ${d.dep === i ? "active" : ""}" data-unit="ydep" data-i="${i}" style="--i:${Math.min(i + 1, 24)}" data-q="${esc(q)}">
    <div class="u-main"><b>${esc(name)}</b><span>${n} akademisyen</span></div>
    <div class="u-act"><button class="btn sm" data-yokpapers="${i}" type="button" title="Bu birimin yayınları">${icon("file")}Yayınlar</button></div>${icon("chevron")}</div>`;
  $("#colDep .col-body").innerHTML = `<div class="stagger">${row("Tüm fakülte", f.people.length, -1, "tum fakulte")}${f.departments.map((x, i) => row(x.name, x.count, i, fold(x.name))).join("")}</div>`;
  hydrateIcons($("#colDep"));
}

const yokStaff = () => { const d = S.uni; return d.dep < 0 ? d.facData.people : d.facData.people.filter((p) => p.department === d.facData.departments[d.dep].key); };
function selectYokDept(i) {
  S.uni.dep = i;
  $$("#colDep .unit").forEach((x) => x.classList.toggle("active", +x.dataset.i === i));
  renderYokStaff();
}
function renderYokStaff() {
  const d = S.uni, people = yokStaff(), host = $("#colStaff .col-body");
  $("#colStaff .col-filter").hidden = true;
  d.staffFilters ||= {};
  d.staffController = mountStaffList(host, "yok", people, { filters: d.staffFilters, mode: "yok", institution: d.data.name, countElement: $("#colStaffN") });
}

function openYokPapers(i) {
  const d = S.uni, f = d.facData, fac = d.data.items[d.fac], dep = i < 0 ? null : f.departments[i];
  const name = dep ? dep.name : fac.name;
  unitPapersDrawer(name, `${dep ? "Bölüm" : "Fakülte"} yayınları · ${d.data.name}`, `${d.data.name} ${name}`,
    "Kadro yayınları akademisyen profilleri üzerinden kaynaklardan toplanıyor…",
    (refresh = false) => post("/api/universities/papers", { uid: d.id, faculty: fac.raw, department: dep ? dep.key : null, refresh }));
}

// =================================================================== KURUM SİTESİ DİZİNİ
async function viewDirectory(url) {
  if (!safeUrl(url)) { location.hash = "#/"; return; }
  const host = new URL(url).hostname;
  if (!S.dir || S.dir.url !== url) S.dir = { url, host, data: null, fac: null, dep: null, deps: null, staff: null };
  const d = S.dir;
  setCrumbs([{ label: "Ana sayfa", href: "#/" }, { label: "Üniversiteler", href: "#/universiteler" }, { label: d.data?.name || host }]);
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
  $("#orgMeta").textContent = `${items.length} birim · ${d.data.method === "gemini" ? "Yapay zekâ ile seçildi" : "kurallarla seçildi"} · ${d.data.at || ""}`;
  setCrumbs([{ label: "Ana sayfa", href: "#/" }, { label: "Üniversiteler", href: "#/universiteler" }, { label: d.data.name || d.host }]);
  $("#nFac").textContent = items.length;
  $("#colFac .col-body").innerHTML = items.length ? `<div class="stagger">${items.map((u, i) => unitRow(u, "fac", i, d.fac === i)).join("")}</div>`
    : `<div class="col-empty">Fakülte bağlantısı bulunamadı. Fakültelerin listelendiği sayfanın bağlantısını girerek tekrar deneyin.</div>`;
  hydrateIcons($("#colFac"));
}

async function selectFaculty(i) {
  const d = S.dir, request = Symbol("faculty"), hash = location.hash;
  d.facRequest = request; d.staffRequest = null; d.fac = i; d.dep = null; d.staff = null;
  const body = $("#colDep .col-body"), active = () => S.dir === d && d.facRequest === request && body.isConnected && location.hash === hash;
  $$("#colFac .unit").forEach((x) => x.classList.toggle("active", +x.dataset.i === i));
  body.innerHTML = `<div class="loading-line"><span class="spinner"></span>Fakülte sayfası okunuyor…</div>${skeleton(6)}`;
  $("#colStaff .col-body").innerHTML = `<div class="col-empty">Bir bölüm seçin.</div>`; $("#nStaff").textContent = "";
  try {
    const data = await post("/api/directory/departments", { url: d.data.items[i].url });
    if (!active()) return;
    d.deps = data; renderDeps();
  } catch (e) { if (active()) body.innerHTML = `<div class="col-empty">${esc(e.message)}</div>`; }
}

function renderDeps() {
  const d = S.dir, items = d.deps.items || [];
  $("#nDep").textContent = items.length;
  $("#colDep .col-body").innerHTML = items.length ? `<div class="stagger">${items.map((u, i) => unitRow(u, "dep", i, d.dep === i)).join("")}</div>`
    : `<div class="col-empty">Bu fakültede bölüm bağlantısı bulunamadı.<br><br><button class="btn sm" data-facstaff type="button">${icon("users")}Fakülte kadrosunu göster</button></div>`;
  hydrateIcons($("#colDep"));
}

async function selectDept(i, unitUrl) {
  const d = S.dir, request = Symbol("staff"), hash = location.hash;
  d.staffRequest = request; d.dep = i;
  const body = $("#colStaff .col-body"), active = () => S.dir === d && d.staffRequest === request && body.isConnected && location.hash === hash;
  $$("#colDep .unit").forEach((x) => x.classList.toggle("active", +x.dataset.i === i));
  body.innerHTML = `<div class="loading-line"><span class="spinner"></span>Akademik kadro sayfası aranıyor…</div>${skeleton(6)}`;
  try {
    const data = await post("/api/directory/staff", { url: unitUrl || d.deps.items[i].url });
    if (!active()) return;
    d.staff = data; renderStaff();
  } catch (e) { if (active()) body.innerHTML = `<div class="col-empty">${esc(e.message)}</div>`; }
}

function renderStaff() {
  const d = S.dir, host = $("#colStaff .col-body");
  $("#colStaff .col-filter").hidden = true;
  d.staffFilters ||= {};
  d.staffController = mountStaffList(host, "directory", d.staff.items || [], { filters: d.staffFilters, mode: "directory", page: d.staff.page, institution: d.data?.name, countElement: $("#nStaff") });
}

function openUnitPapers(kind, i) {
  const d = S.dir, unit = kind === "fac" ? d.data.items[i] : d.deps.items[i];
  unitPapersDrawer(unit.name, `${kind === "fac" ? "Fakülte" : "Bölüm"} yayınları · ${d.data.name || d.host}`, `${unit.name} ${d.data.name || d.host}`,
    "Kadro yayınları akademisyen profilleri üzerinden kaynaklardan toplanıyor…",
    (refresh = false) => post("/api/directory/papers", { url: unit.url, level: kind === "fac" ? "faculty" : "department", name: unit.name, refresh }));
}

async function unitPapersDrawer(name, sub, file, waiting, load) {
  const request = Symbol("unit"), routeHash = location.hash;
  S.unitRequest = request;
  openDrawer(`<div class="unit-drawer-heading"><h2>${esc(name)}</h2><button id="unitRescan" class="btn sm" type="button" disabled aria-busy="true"><span class="spinner" aria-hidden="true"></span>Tekrar tara</button></div><p>${esc(sub)}</p>`, `<div id="unitProgress" class="loading-line" role="status" aria-live="polite"><span class="spinner"></span>Kayıtlı yayınlar yükleniyor…</div>
    <div id="unitStats"></div><div id="unitErrors"></div>
    <details class="unit-staff"><summary>Akademik kadro <span id="unitStaffTotal"></span></summary><div id="unitStaff"></div></details>
    <div id="unitTable"></div>`);
  $("#drawer").classList.add("publication-drawer");
  const body = $("#drawerBody"), rescan = $("#unitRescan");
  const active = () => S.unitRequest === request && body.isConnected && rescan.isConnected && location.hash === routeHash && $("#drawer").classList.contains("open");
  const listKey = `unit-${fold(file).replace(/ /g, "-")}`;
  S.listMeta[listKey] = { file };
  const table = mountPublicationTable($("#unitTable"), "dw", listKey, []);
  const staff = mountStaffList($("#unitStaff"), "unit", [], { institution: sub, mode: "directory" });
  let paperRevision, staffRevision, loadEpoch = 0, busy = false;
  const setBusy = (value) => {
    busy = value; rescan.disabled = value; rescan.setAttribute("aria-busy", String(value));
    rescan.innerHTML = `${value ? '<span class="spinner" aria-hidden="true"></span>' : icon("refresh")}Tekrar tara`;
    if (!value) hydrateIcons(rescan);
  };
  const apply = (r) => {
    const papers = r.papers || [], people = r.staff || [], total = r.total_people ?? r.people ?? people.length;
    const complete = r.completed ?? r.matched ?? 0;
    const state = r.status === "running" ? "Kaynaklar taranıyor" : r.cached
      ? `Kayıtlı sonuçlar${r.status === "error" ? " · toplama tamamlanamadı" : r.status === "partial" ? " · kısmi sonuç" : r.status === "cancelled" ? " · tarama durduruldu" : ""}`
      : r.status === "error" ? "Toplama tamamlanamadı" : r.status === "partial" ? "Kısmi sonuç" : r.status === "cancelled" ? "Tarama durduruldu" : "Toplama tamamlandı";
    $("#unitProgress").innerHTML = `${r.status === "running" ? '<span class="spinner"></span>' : ""}${state} · ${fmtNum(complete)} / ${fmtNum(total)} akademisyen tamamlandı`;
    $("#unitStats").innerHTML = `<div class="stat-row"><div class="stat"><b>${fmtNum(papers.length)}</b><span>birleştirilmiş yayın</span></div>
      <div class="stat"><b>${fmtNum(r.matched ?? 0)} / ${fmtNum(total)}</b><span>profili eşleşen akademisyen</span></div>
      <div class="stat"><b>${fmtNum(papers.reduce((sum, p) => sum + (Number(p.citations) || 0), 0))}</b><span>toplam atıf</span></div></div>
      <p class="faint">${esc(sourceDistribution(r))}</p>`;
    const errors = (r.errors || []).map((e) => typeof e === "string" ? e : [e.name, e.error].filter(Boolean).join(": "));
    errors.push(...(r.warnings || []).map((e) => typeof e === "string" ? e : [e.name, e.message].filter(Boolean).join(": ")));
    if (r.cache_error) errors.push(r.cache_error);
    if (r.missing?.length) errors.push(`Eşleşmeyen veya tamamlanamayan: ${r.missing.join(", ")}`);
    $("#unitErrors").innerHTML = errors.length ? `<div class="notice warn"><div>${errors.map(esc).join("<br>")}</div></div>` : "";
    $("#unitStaffTotal").textContent = `(${fmtNum(people.length)})`;
    const nextPapers = JSON.stringify(papers), nextStaff = JSON.stringify(people);
    if (paperRevision !== nextPapers) { paperRevision = nextPapers; table.update(papers); }
    if (staffRevision !== nextStaff) {
      staffRevision = nextStaff; staff.update(people);
      const merge = (items) => items.map((person) => {
        const latest = people.find((p) => (p.person_key && p.person_key === person.person_key)
          || (p.url && p.url === person.url && fold(p.name) === fold(person.name)));
        if (!latest) return person;
        const next = { ...person };
        for (const key of ["publication_count", "article_count", "citations", "sources", "chat_id", "job_id", "status"]) if (Object.hasOwn(latest, key)) next[key] = latest[key];
        return next;
      });
      if (S.uni?.facData?.people && location.hash.startsWith("#/universite/")) {
        S.uni.facData.people = merge(S.uni.facData.people);
        if (S.uni.dep != null) S.uni.staffController?.update(yokStaff());
      }
      if (S.dir?.staff?.items && location.hash.startsWith("#/kurum")) {
        S.dir.staff.items = merge(S.dir.staff.items); S.dir.staffController?.update(S.dir.staff.items);
      }
    }
  };
  const run = async (refresh = false) => {
    if (!active() || busy) return;
    const epoch = ++loadEpoch, current = () => active() && epoch === loadEpoch;
    setBusy(true);
    $("#unitProgress").innerHTML = `<span class="spinner"></span>${refresh ? esc(waiting) : "Kayıtlı yayınlar yükleniyor…"}`;
    try {
      await pollSnapshots(() => load(refresh), current, apply, (r) => r.status === "running" && !!r.job_id,
        (r) => api(`/api/units/papers/${encodeURIComponent(r.job_id)}`));
    } catch (e) {
      if (!current()) return;
      $("#unitProgress").textContent = "Sonuç güncellemesi durdu; alınan yayınlar gösteriliyor.";
      $("#unitErrors").innerHTML = `<div class="notice err"><div>${esc(e.message)}</div></div>`;
    } finally {
      if (current()) setBusy(false);
    }
  };
  rescan.onclick = () => run(true);
  await run(false);
}

function openDrawer(head, body) {
  $("#drawer").classList.remove("publication-drawer");
  $("#drawerTitle").innerHTML = head; $("#drawerBody").innerHTML = body; hydrateIcons($("#drawer"));
  $("#drawer").classList.add("open"); $("#drawer").setAttribute("aria-hidden", "false");
}
function closeDrawer() { S.unitRequest = null; $("#drawer").classList.remove("open", "publication-drawer"); $("#drawer").setAttribute("aria-hidden", "true"); }

// =================================================================== PROFİL
async function viewProfile(cid) {
  setCrumbs([{ label: "Ana sayfa", href: "#/" }, { label: "Akademisyenler", href: "#/akademisyenler" }, { label: "…" }]);
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
  setCrumbs([{ label: "Ana sayfa", href: "#/" }, { label: "Akademisyenler", href: "#/akademisyenler" }, { label: p.name }]);
  const links = [
    y.email && `<a class="chip blue" href="mailto:${esc(y.email)}">${icon("mail")}${esc(y.email)}</a>`,
    p.orcid && `<a class="chip teal" href="https://orcid.org/${esc(p.orcid)}" target="_blank" rel="noopener">ORCID ${esc(p.orcid)}</a>`,
    safeUrl(p.links?.yok) && `<a class="chip" href="${esc(safeUrl(p.links.yok))}" target="_blank" rel="noopener">${icon("cap")}YÖK Akademik</a>`,
    safeUrl(p.links?.scholar) && `<a class="chip" href="${esc(safeUrl(p.links.scholar))}" target="_blank" rel="noopener">Google Scholar</a>`,
    safeUrl(p.source_url) && `<a class="chip" href="${esc(safeUrl(p.source_url))}" target="_blank" rel="noopener">${icon("building")}Kurum sayfası</a>`,
  ].filter(Boolean).join("");
  const totalCites = r.publications.reduce((s, x) => s + (x.citations || 0), 0);
  // h-index kaynağa göre gösterilir: kaynaklar farklı yayınları sayar, tek sayıya indirilmez
  const qCounts = publicationQuartiles(r.publications);
  const srcMeta = r.recon?.sources_meta || {};
  const hIndex = [["scholar", "Scholar"], ["openalex", "OpenAlex"]].filter(([k]) => srcMeta[k]?.h_index != null).map(([k, l]) => [srcMeta[k].h_index, l]);
  const tez = y.tez_merkezi || {}, trProjects = y.tr_projects || [];
  const nTheses = Math.max((sec.theses || []).length, (tez.advised || []).length);
  const tabs = [
    ["overview", "Genel bakış", ""], ["pubs", "Yayınlar", r.unique_count], ["career", "Akademik geçmiş", (y.career || []).length + (y.education || []).length],
    ["courses", "Dersler", (sec.courses || []).length], ["theses", "Tezler", nTheses],
    ["more", "Projeler ve diğer", ["projects", "awards", "patents", "memberships", "art"].reduce((s, k) => s + (sec[k] || []).length, 0)],
    ["collab", "İş birlikleri", (y.collaborators || []).length + (r.industry || []).length],
    ...(trProjects.length ? [["tubitak", "TÜBİTAK", trProjects.length]] : []), ["patents", "Patentler", patentCount(r.patents)],
    ["chat", "Asistan", ""],
  ];
  const otherSections = [["projects", "Projeler", "briefcase"], ["awards", "Ödüller", "award"], ["patents", "Patentler", "file"],
    ["memberships", "Üyelikler", "users"], ["art", "Sanatsal faaliyetler", "sparkle"]];
  const pubSrc = (x) => ({ jid: r.job_id, pid: x.id, person: p.name });
  S.lists.pubs = r.publications;
  S.listMeta.pubs = { file: p.name, person: p.name, title: p.title, institution: p.institution, cats: true };

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
          <button class="btn" id="refreshProfileBtn" type="button" title="Kaynaklardan baştan topla: yeni yayınlar, fotoğraf, güncel bilgiler. Sohbet ve favori korunur.">${icon("refresh")}Yenile</button>
        </div>
      </div>
      <div class="kpis">
        <div class="kpi"><b id="profilePubCount">${count(r.unique_count)}</b><span>benzersiz yayın</span></div>
        <div class="kpi"><b id="profileCitesCount">${count(totalCites)}</b><span>toplam atıf</span></div>
        <div class="kpi"><b>${count((sec.courses || []).length)}</b><span>ders</span></div>
        ${hIndex.length ? `<div class="kpi kpi-h" title="Kaynaklar farklı yayınları saydığı için değerler farklı olabilir. Web of Science ve Scopus değerleri dahil değildir.">${hIndex.map(([v, l]) => `<b>${count(v)}<small>${esc(l)}</small></b>`).join("")}<span>h-index</span></div>` : ""}
        <div class="kpi"><b>${count(nTheses)}</b><span>yönetilen tez</span></div>
        <div class="kpi"><b>${count((y.collaborators || []).length)}</b><span>iş birliği</span></div>
        ${qCounts.total ? `<div class="kpi src"><b id="profileQuartiles">${quartileDistribution(r, qCounts)}</b><span>dergi çeyreği · ${esc(qCounts.src)}, yayın yılına göre, derginin en iyi alanı (Scopus tabanlı, WoS/JCR değildir)</span></div>` : ""}
        <div class="kpi src"><b id="profileSources">${esc(sourceDistribution(r))}</b><span>kaynak dağılımı</span></div>
      </div>
    </section>

    <div class="tabs" role="tablist">${tabs.map(([k, l, n], i) => `<button class="tab ${i === 0 ? "active" : ""}" data-tab="${k}" type="button" ${k === "patents" && !n ? "hidden" : ""}>${esc(l)}${n !== "" && n != null ? `<span class="n">${fmtNum(n)}</span>` : ""}</button>`).join("")}</div>

    <div class="panel active" data-panel="overview"><div class="stack">
      <div class="stack" id="analysisBox">${analysisHtml(a)}</div>
      ${(p.verification?.interests?.length || p.interests?.length) ? `<div class="card card-pad"><div class="card-title">İlgi alanları</div><div class="chips">
        ${(p.verification?.interests?.length ? p.verification.interests.filter((x) => cleanInterest(x.value)).slice(0, 16).map((x) => `<span class="chip" title="${esc(x.sources.join(", "))}">${esc(cleanInterest(x.value))}${x.sources.length > 1 ? `<sup>✓${x.sources.length}</sup>` : ""}</span>`)
          : p.interests.filter(cleanInterest).map((x) => `<span class="chip">${esc(cleanInterest(x))}</span>`)).join("")}</div></div>` : ""}
      ${(r.industry || []).length ? `<div class="card card-pad"><div class="card-title">${icon("building")}Sanayi iş birlikleri<span class="spacer"></span>
        <button class="btn sm" data-tabgo="collab" type="button">Kanıtları gör</button></div><div class="chips">${r.industry.map((x) =>
          `<span class="chip ${x.official ? "teal" : ""}">${x.official ? "✓ " : ""}${esc(x.name)}</span>`).join("")}</div></div>` : ""}
      ${techTrace(r)}
      <p class="faint"><span id="profileSummary">${esc(r.summary || "")}</span> · ${r.elapsed ?? "?"} sn · ${esc(r.llm || "")}${y.updated ? ` · YÖK son güncelleme ${esc(y.updated)}` : ""}</p>
    </div></div>

    <div class="panel" data-panel="pubs"><div id="profilePublications"></div></div>

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
    <div class="panel" data-panel="patents"><div class="card card-pad" id="patentsBox">${r.patents ? personPatentsHtml(r.patents) : ""}</div></div>

    <div class="panel" data-panel="chat"><div class="card chat-wrap">
      <div class="thread" id="thread"><div class="msg bot">${avatar("İz", "")}<div class="bubble">Merhaba! <b>${esc(p.name)}</b> hakkında yayınlar, dersler, tezler, iş birlikleri ya da araştırma alanları üzerine soru sorabilirsiniz.
        Cevaplar yalnızca toplanan kaynaklara dayanır ve yayın kimlikleriyle gösterilir.</div></div></div>
      <div class="suggest">${["En çok atıf alan yayınları hangileri?", "Hangi dersleri veriyor?", "Danışmanlık yaptığı tezler hangi konularda?", "TÜBİTAK projeleri neler?", "Hangi firmalarla çalışmış?", "Son yıllarda hangi konulara yöneldi?", "En sık kimlerle çalışıyor?"].map((q) => `<button class="chip" data-ask="${esc(q)}" type="button">${esc(q)}</button>`).join("")}</div>
      <form class="composer" id="askForm"><div class="input">${icon("message")}<input id="question" placeholder="${esc(p.name)} hakkında bir şey sorun…" autocomplete="off"></div>
        <button class="btn primary" id="send" type="submit">${icon("send")}Gönder</button></form>
    </div></div>`);

  const publicationTable = mountPublicationTable($("#profilePublications"), "pub", "pubs", r.publications, "year", { rowId: "pubs", sourceFor: pubSrc });
  const drawPubs = () => publicationTable.update(r.publications);

  $("#refreshProfileBtn").onclick = () => startJob(p.institution || p.source_url || "", p.name, () => post(`/api/jobs/${r.job_id}/refresh`, {}), "yenileniyor");
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
  if (r.patents_v !== PATENTS_V && !S.patentsOff) loadPatents();
  loadWos(r, drawPubs);
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

// Patentler (EPO Open Patent Services). Anahtar (.env EPO_KEY/EPO_SECRET) yoksa sekme hiç görünmez.
const PATENTS_V = 2;  // app/patents.py VERSION
const patentCount = (d) => (d?.items?.length || 0) + (d?.possible?.length || 0);
const UNI_RX = /[üu]n[iı]versit|university/i;
const PAT = [];  // modalda açılacak patentler (data-patent dizini)
function patentRow(x) {
  PAT.push(x);
  return `<div class="thesis"><b><a href="#" data-patent="${PAT.length - 1}" title="Özgün belgeyi aç">${esc(x.title)}</a></b>${x.title_en ? `<div class="faint">${esc(x.title_en)}</div>` : ""}
    <div class="chips"><span class="chip">${esc(x.year || "?")}</span>
      ${x.applicants.map((a) => `<span class="chip ${UNI_RX.test(a) ? "blue" : "teal"}">${icon(UNI_RX.test(a) ? "cap" : "building")}${esc(a)}</span>`).join("")}
      ${(x.academics || []).map((a) => `<span class="chip gold">${icon("user")}${esc(a)}</span>`).join("")}
      ${safeUrl(x.url) ? `<a class="chip" href="${esc(safeUrl(x.url))}" target="_blank" rel="noopener">${esc(x.numbers[0])} ${icon("external")}</a>` : ""}</div>
    <div class="faint" style="margin-top:6px">Buluş sahipleri: ${esc(x.inventors.join(", ") || "—")}${x.numbers.length > 1 ? ` · diğer yayınları: ${esc(x.numbers.slice(1).join(", "))}` : ""}</div>
    ${x.abstract || hasFulltext(x) ? `<details class="pat-text" data-pnums="${esc(x.numbers.join("|"))}"><summary>${hasFulltext(x) ? "Özet ve açıklama" : "Özet"}</summary>
      ${x.abstract ? `<div class="abs">${esc(x.abstract)}</div>` : ""}${hasFulltext(x) ? `<div class="pat-desc"></div>` : ""}</details>` : ""}</div>`;
}
// Patent modalı: künye, özet ve özgün belgenin taranmış sayfaları (EPO; sayfalar kaydırdıkça yüklenir).
async function openPatent(x) {
  openModal(`<div class="pat-modal"><h2 style="padding-right:44px">${esc(x.title)}</h2>${x.title_en ? `<div class="faint">${esc(x.title_en)}</div>` : ""}
    <div class="chips" style="margin:12px 0 8px"><span class="chip">${esc(x.year || "?")}</span>${x.numbers.map((n) => `<span class="chip">${esc(n)}</span>`).join("")}
      ${x.applicants.map((a) => `<span class="chip ${UNI_RX.test(a) ? "blue" : "teal"}">${icon(UNI_RX.test(a) ? "cap" : "building")}${esc(a)}</span>`).join("")}
      ${safeUrl(x.url) ? `<a class="chip" href="${esc(safeUrl(x.url))}" target="_blank" rel="noopener">Espacenet ${icon("external")}</a>` : ""}</div>
    <div class="faint">Buluş sahipleri: ${esc(x.inventors.join(", ") || "—")}</div>
    ${x.abstract ? `<div class="group-title" style="margin-top:16px">Özet</div><div class="abs">${esc(x.abstract)}</div>` : ""}
    <div class="group-title" style="margin-top:18px">Özgün belge</div>
    <div id="patPages"><div class="loading-line"><span class="spinner"></span>Belge EPO'dan alınıyor…</div></div></div>`);
  let d;
  try { d = await api(`/api/patents/document?${x.numbers.map((n) => `n=${encodeURIComponent(n)}`).join("&")}`); }
  catch (err) { d = { pages: 0, error: err.message }; }
  const box = $("#patPages");
  if (!box || $("#modal").hidden) return;
  box.innerHTML = d.pages ? `<div class="faint">${esc(d.source)} · ${d.pages} sayfa</div>
    ${Array.from({ length: d.pages }, (_, i) => `<img class="pat-page" loading="lazy" alt="Sayfa ${i + 1}" src="/api/patents/page/${encodeURIComponent(d.source)}/${i + 1}.png">`).join("")}`
    : `<p class="faint">${esc(d.error || "Bu patentin taranmış belgesi EPO'da yok.")}</p>`;
}

// Açıklama (tam metin) yalnız EP/WO yayınlarında var; detay açılınca istenir, sunucuda süresiz saklanır.
const hasFulltext = (x) => x.numbers.some((n) => /^(EP|WO)/.test(n));
document.addEventListener("toggle", async (e) => {
  const det = e.target;
  if (!det.matches?.("details.pat-text") || !det.open || det.dataset.loaded) return;
  const box = $(".pat-desc", det);
  if (!box) return;
  det.dataset.loaded = "1";
  box.innerHTML = `<div class="loading-line"><span class="spinner"></span>Açıklama EPO'dan alınıyor…</div>`;
  try {
    const q = det.dataset.pnums.split("|").map((n) => `n=${encodeURIComponent(n)}`).join("&");
    const d = await api(`/api/patents/description?${q}`);
    const text = d.text.length > 12000 ? `${d.text.slice(0, 12000)}…` : d.text;
    box.innerHTML = d.text ? `<div class="group-title" style="margin-top:12px">Açıklama · ${esc(d.source)}${d.lang && d.lang !== "tr" ? ` (${esc(d.lang.toUpperCase())})` : ""}</div><div class="abs">${esc(text)}</div>
      ${d.text.length > 12000 ? `<div class="faint" style="margin-top:6px">Metnin devamı Espacenet'te.</div>` : ""}`
      : `<div class="faint" style="margin-top:10px">Bu patentin açıklama metni EPO'da yok.</div>`;
  } catch (err) { delete det.dataset.loaded; box.innerHTML = `<div class="faint" style="margin-top:10px">${esc(err.message)}</div>`; }
}, true);
function personPatentsHtml(d) {
  return `<div class="card-title">${icon("file")}Patentler<span class="spacer"></span><span class="count">${d.items.length}</span><span class="badge">EPO</span></div>
    <p class="muted" style="margin:0 0 6px">Buluş sahibi olarak geçtiği patentler (Espacenet; TR, EP ve WO yayınları). Aynı buluşun farklı ülkelerdeki yayınları tek satırdadır.</p>
    ${d.items.map(patentRow).join("") || (d.possible.length ? "" : `<p class="faint" style="margin:0">Patent bulunamadı.</p>`)}
    ${d.possible.length ? `<details ${d.items.length ? "" : "open"} style="margin-top:10px"><summary class="faint" style="cursor:pointer">${d.possible.length} olası eşleşme: adı tutuyor ama başvuru sahibi kendi kurumu değil (aynı adlı başka biri olabilir)</summary>
      ${d.possible.map(patentRow).join("")}</details>` : ""}`;
}
async function loadPatents() {
  const r = S.result;
  let d;
  try { d = await post(`/api/jobs/${r.job_id}/patents`, {}); } catch { return; }  // EPO sınırı/ağ: sessizce sonra
  if (!d.enabled) { S.patentsOff = true; return; }
  r.patents = d.patents; r.patents_v = d.patents_v;
  const box = $("#patentsBox"), tab = $(`.tab[data-tab="patents"]`);
  if (S.result !== r || !box || !tab) return;
  box.innerHTML = personPatentsHtml(d.patents); hydrateIcons(box);
  const n = patentCount(d.patents);
  tab.hidden = !n;
  if ($(".n", tab)) $(".n", tab).textContent = fmtNum(n);
}
async function loadFirmPatents(fid, refresh) {
  let d;
  try { d = await api(`/api/firms/${encodeURIComponent(fid)}/patents${refresh ? "?refresh=1" : ""}`); } catch { return; }
  const box = $("#firmPatentsBox"), tab = $(`.tab[data-tab="patents"]`);
  if (!d.enabled || !box || !tab || !location.hash.startsWith(`#/firma/${fid}`)) return;
  tab.hidden = !d.items.length && !d.error;
  $("#patentsN").textContent = fmtNum(d.items.length);
  box.innerHTML = `<div class="card-title">${icon("file")}Patentler<span class="spacer"></span><span class="count">${d.items.length}</span><span class="badge">EPO</span></div>
    <p class="muted" style="margin:0 0 6px">Firmanın başvuru sahibi olduğu patentler (Espacenet; TR, EP ve WO). Mavi: ortak başvuru sahibi üniversite · sarı: buluş sahipleri arasında bu sayfadaki akademisyen.</p>
    ${d.error ? `<div class="notice warn">${icon("info")}<div>${esc(d.error)}.</div></div>` : ""}
    ${d.total > 200 ? `<p class="faint" style="margin:0 0 6px">EPO'da ${fmtNum(d.total)} yayın var; ilk 200 yayın gösteriliyor.</p>` : ""}
    ${d.items.map(patentRow).join("")}`;
  hydrateIcons(box);
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
      <span class="chip ${a.mode === "mock" ? "gold" : "blue"}">${a.mode === "mock" ? "Kural tabanlı analiz" : "Yapay zekâ · " + esc(a.model || "")}</span>
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
    <div class="loading-line"><span class="spinner"></span>Yapay zekâ ${fmtNum(r.unique_count)} yayını inceliyor, iddialar kanıtlarla doğrulanıyor…</div>${skeleton(3)}</div>`;
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
function topicProgress(wos) {
  if (!wos) return "";
  const count = wos.total == null ? `${fmtNum(wos.checked || 0)} kayıt incelendi` : `${fmtNum(wos.total)} kayıttan ${fmtNum(wos.checked || 0)} kayıt incelendi`;
  const state = { pending: "WoS sırası bekleniyor", running: "WoS taranıyor", done: "WoS taraması tamamlandı", partial: "WoS kısmi sonuç", blocked: "WoS erişimi sağlanamadı", error: "WoS taraması tamamlanamadı" }[wos.status] || "WoS";
  const reason = { record_limit: `Tarama ilk ${wos.limit || 20} kayıtla sınırlı.`, time_budget: "Tarama süresi doldu.", queue_timeout: "Tarama sırası için bekleme süresi doldu.", results_not_fully_loaded: "WoS sonuçlarının bir bölümü yüklenemedi.", access_unavailable: "Diğer kaynaklardan alınan yayınlar gösteriliyor." }[wos.reason] || "";
  return `${["pending", "running"].includes(wos.status) ? '<span class="spinner"></span>' : ""}${esc(state)} · ${esc(count)}${reason ? ` · ${esc(reason)}` : ""}`;
}
async function viewSearch(q) {
  setCrumbs([{ label: "Ana sayfa", href: "#/" }, { label: "Konular" }]);
  setView(`<div class="section-head"><div><h1>Konular</h1><p>OpenAlex, Crossref, Semantic Scholar, TR Dizin, OpenAIRE ve WoS kayıtları kaynaklarıyla birleştirilir.</p></div></div>
    <form class="card quick-search" id="searchForm" style="margin-top:0">
      <div class="input">${icon("search")}<input id="sInput" value="${esc(q)}" placeholder="ör. göğüs hastalıkları, makine öğrenmesi, deprem mühendisliği"></div>
      <button class="btn primary" type="submit">Ara</button></form>
    <div id="sResults" style="margin-top:18px"></div>`);
  $("#searchForm").addEventListener("submit", (e) => {
    e.preventDefault(); const value = $("#sInput").value.trim();
    if (value.length < 3) return;
    const hash = `#/ara?q=${encodeURIComponent(value)}`;
    if (location.hash === hash) viewSearch(value); else location.hash = hash;
  });
  const box = $("#sResults"), routeHash = location.hash;
  if (!q) {
    box.innerHTML = emptyState("search", "Bir konu yazın", "Türkçe yazdığınız konu İngilizceye de çevrilerek aranır.");
    hydrateIcons(box); $("#sInput").focus(); return;
  }
  box.innerHTML = `<div id="topicSources" class="src-status"></div><div id="topicProgress" class="loading-line" role="status" aria-live="polite"><span class="spinner"></span>Akademik kaynaklar taranıyor…</div><div id="topicError"></div><div id="topicTable"></div>`;
  const active = () => box.isConnected && location.hash === routeHash;
  S.listMeta.search = { file: `arama ${q}` };
  const table = mountPublicationTable($("#topicTable"), "s", "search", [], "rel");
  let revision;
  const apply = (r) => {
    $("#topicSources").innerHTML = Object.entries(r.sources || {}).map(([source, value]) => `<span class="chip ${typeof value === "number" ? "teal" : "gold"}">${esc(SRC_TR[sourceKey(source)] || source)}: ${typeof value === "number" ? fmtNum(value) + " sonuç" : esc(value)}</span>`).join("")
      + (r.english ? `<span class="chip blue">EN: ${esc(r.english)}</span>` : "") + (r.elapsed != null ? `<span class="chip">${esc(r.elapsed)} sn</span>` : "");
    $("#topicProgress").innerHTML = topicProgress(r.wos);
    const next = r.revision ?? JSON.stringify(r.papers || []);
    if (next !== revision) { revision = next; table.update(r.papers || []); }
  };
  try {
    await pollSnapshots(() => api(`/api/search?q=${encodeURIComponent(q)}`), active, apply,
      (r) => !!r.search_id && ["pending", "running"].includes(r.wos?.status),
      (r) => api(`/api/search/${encodeURIComponent(r.search_id)}`));
  } catch (e) {
    if (!active()) return;
    $("#topicProgress").textContent = "Arama güncellenemedi; alınan sonuçlar gösteriliyor.";
    $("#topicError").innerHTML = `<div class="notice err"><div>${esc(e.message)}</div></div>`;
  }
}

// =================================================================== KÜTÜPHANEM
async function viewLibrary(tab = "papers") {
  setCrumbs([{ label: "Ana sayfa", href: "#/" }, { label: "Kütüphanem" }]);
  await loadFav();
  const papers = [...S.fav.papers].reverse(), people = [...S.fav.people].reverse();
  S.lists.fav = papers;
  S.listMeta.fav = { file: "favori makaleler" };
  setView(`<div class="section-head"><div><h1>Kütüphanem</h1><p>Kaydettiğiniz makaleler ve akademisyenler.</p></div>
      <div class="actions">${papers.length ? exportButtons("fav") : ""}</div></div>
    <div class="tabs" role="tablist"><button class="tab ${tab === "papers" ? "active" : ""}" data-tab="papers" type="button">Makaleler<span class="n">${papers.length}</span></button>
      <button class="tab ${tab === "people" ? "active" : ""}" data-tab="people" type="button">Akademisyenler<span class="n">${people.length}</span></button></div>
    <div class="panel ${tab === "papers" ? "active" : ""}" data-panel="papers"><div class="card">${papers.length ? `<div class="stagger">${papers.map((p, i) => paperCard(p, p.job_id && p.pid ? { jid: p.job_id, pid: p.pid, person: p.person } : {}, i)).join("")}</div>`
      : emptyState("bookmark", "Henüz favori makale yok", "Yayın listelerinde ☆ simgesine tıklayarak makaleleri buraya ekleyin.")}</div></div>
    <div class="panel ${tab === "people" ? "active" : ""}" data-panel="people">${people.length ? `<div class="collabs stagger">${people.map((p, i) => `<div class="collab" style="--i:${i};cursor:pointer" data-chat="${esc(p.chat_id || "")}">
      ${avatar(p.name, p.photo)}<div class="c-main"><div class="c-title">${esc(p.title || "")}</div><b>${esc(p.name)}</b>
      <span>${esc(p.institution || "")}</span><span class="faint">${esc(p.department || "")}</span>
      <div class="chips" style="margin-top:8px"><span class="chip">${fmtNum(p.papers)} yayın</span>
        <button class="chip" data-unfav="${esc(p.key)}" type="button">${icon("x")}Çıkar</button></div></div></div>`).join("")}</div>`
      : `<div class="card">${emptyState("users", "Henüz favori akademisyen yok", "Bir profil sayfasında “Favorilere ekle” düğmesini kullanın.")}</div>`}</div>`);
}

// =================================================================== SİSTEM
async function viewSystem() {
  setCrumbs([{ label: "Ana sayfa", href: "#/" }, { label: "Ayarlar" }]);
  setView(`<div class="section-head"><div><h1>Ayarlar</h1><p>Kullanılacak yapay zekâ, servislerin durumu ve REA'nın öğrendiği site tarifleri.</p></div></div>
    <div class="card card-pad ai-card" id="aiCard">${skeleton(3)}</div>
    <div class="grid-2"><div class="card card-pad"><div class="card-title">${icon("info")}Durum</div><div id="sysState">${skeleton(3)}</div></div>
      <div class="card card-pad"><div class="card-title">${icon("settings")}Site tarifleri</div>
        <p class="muted" style="margin:0 0 14px">REA sitelerin arka plandaki isteklerini öğrenir; site değişince yeniden öğrenir.</p>
        <div class="actions"><button class="btn sm" type="button" data-recipes>Öğrenilen tarifler</button><button class="btn sm" type="button" data-scan>Değişiklikleri tara</button></div></div></div>`);
  aiSettingsCard();
  let h = null;
  try { h = await api("/api/health"); } catch { /* aşağıda gösterilir */ }
  const box = $("#sysState");
  if (!box) return;
  const row = (name, ok, text) => `<div class="sys-row"><span class="dot ${ok ? "ok" : "warn"}"></span><b>${esc(name)}</b><span class="muted">${esc(text)}</span></div>`;
  box.innerHTML = h ? [row("Yapay zekâ", h.llm_ready, h.llm), row("REA", h.rea, h.rea ? "Hazır" : "Kurulu değil"), row("Tarayıcı", h.chromium, h.chromium ? "Hazır" : "Kurulu değil"),
    row("Patentler (EPO)", h.patents, h.patents ? "Anahtar tanımlı" : "Anahtar yok; patent sekmeleri kapalı")].join("") : `<p class="muted">Sunucuya ulaşılamadı.</p>`;
}

// Yapay zekâ sağlayıcısı. Anahtar sunucuda kalır; arayüze yalnızca "kayıtlı mı" bilgisi gelir.
async function aiSettingsCard() {
  const card = $("#aiCard");
  let cfg;
  try { cfg = await api("/api/settings/ai"); } catch { if (card) card.innerHTML = `<p class="muted">Ayarlar okunamadı.</p>`; return; }
  if (!card?.isConnected) return;
  const NOTES = {
    gemini: "Google AI Studio anahtarı.",
    openai: "platform.openai.com anahtarı. ChatGPT Plus üyeliği API anahtarı yerine geçmez.",
    anthropic: "console.anthropic.com anahtarı. Claude'da gömme modeli olmadığı için sohbet yayınları kelime aramasıyla bulur.",
    custom: "OpenAI uyumlu her sunucu olur (Ollama, LM Studio, vLLM…). Anahtar gerekmiyorsa boş bırakın.",
  };
  card.innerHTML = `<div class="card-title">${icon("settings")}Yapay zekâ</div>
    <form class="ai-form" id="aiForm" autocomplete="off">
      <div class="field"><label for="aiProvider">Sağlayıcı</label><select class="select" id="aiProvider">
        ${Object.entries(cfg.providers).map(([k, p]) => `<option value="${k}" ${k === cfg.provider ? "selected" : ""}>${esc(p.label)}</option>`).join("")}</select></div>
      <div class="field" id="aiUrlField"><label for="aiUrl">API adresi</label><div class="input"><input id="aiUrl" placeholder="http://localhost:11434/v1"></div></div>
      <div class="field"><label for="aiKey">API anahtarı</label><div class="input"><input id="aiKey" type="password" autocomplete="new-password"></div></div>
      <div class="field"><label for="aiModel">Model</label><div class="input"><input id="aiModel" list="aiModels"></div><datalist id="aiModels"></datalist></div>
      <div class="field" id="aiEmbedField"><label for="aiEmbed">Gömme modeli <small>isteğe bağlı</small></label><div class="input"><input id="aiEmbed" list="aiModels"></div></div>
    </form>
    <p class="muted ai-note" id="aiNote"></p>
    <div class="actions"><button class="btn primary sm" type="button" id="aiSave">Kaydet ve kullan</button>
      <button class="btn sm" type="button" id="aiList">Bağlantıyı dene</button>
      <button class="btn sm" type="button" id="aiClear">Anahtarı sil</button></div>
    <p class="muted ai-note" id="aiStatus" role="status"></p>
    <p class="faint ai-note">Anahtar yalnızca bu bilgisayarda saklanır. Taranan sayfa metinleri, yayın bilgileri ve sohbet soruları seçtiğiniz sağlayıcıya gönderilir.</p>`;
  const fill = () => {
    const name = $("#aiProvider").value, p = cfg.providers[name];
    $("#aiEmbedField").hidden = name !== "custom";
    $("#aiUrl").value = p.base_url || "";
    $("#aiUrl").placeholder = name === "custom" ? "http://localhost:11434/v1" : "Sağlayıcının API adresi";
    $("#aiModel").value = p.model || "";
    $("#aiEmbed").value = p.embed_model || "";
    $("#aiKey").value = "";
    $("#aiKey").placeholder = p.has_key ? "Kayıtlı; değiştirmek için yazın" : "Anahtarı yapıştırın";
    $("#aiClear").hidden = !p.has_key;
    $("#aiModels").innerHTML = "";
    $("#aiNote").textContent = NOTES[name];
    $("#aiStatus").textContent = "";
  };
  const values = (extra = {}) => ({ provider: $("#aiProvider").value, key: $("#aiKey").value, base_url: $("#aiUrl").value,
    model: $("#aiModel").value, embed_model: $("#aiEmbed").value, ...extra });
  const status = (text) => { $("#aiStatus").textContent = text; };
  const save = async (extra) => {
    status("Kaydediliyor ve bağlanılıyor…");
    try {
      const r = await post("/api/settings/ai", values(extra));
      cfg = r;
      const label = r.label;
      fill();
      status(r.ready ? `Kullanımda: ${label}` : label);
      loadEnv();
    } catch (e) { status(e.message || "Kaydedilemedi."); }
  };
  fill();
  $("#aiProvider").addEventListener("change", fill);
  $("#aiList").addEventListener("click", async () => {
    status("Bağlanılıyor…");
    try {
      const r = await post("/api/settings/ai/models", values());
      if (!r.ok) return status(r.error);
      $("#aiModels").innerHTML = r.models.map((m) => `<option value="${esc(m)}">`).join("");
      status(r.models.length ? `Bağlantı başarılı. ${r.models.length} model bulundu; Model kutusundan seçebilirsiniz.` : "Bağlantı başarılı; sunucu model listesi vermedi, model adını yazın.");
    } catch (e) { status(e.message || "Bağlanılamadı."); }
  });
  $("#aiSave").addEventListener("click", () => save({}));
  $("#aiClear").addEventListener("click", () => save({ key: "", clear_key: true }));
}

// =================================================================== FİRMALAR
// Sanayi ve Teknoloji Bakanlığı Ar-Ge / Tasarım Merkezi listesindeki firmalar ve onlarla çalışan akademisyenler.
async function viewFirms(q = "", sector = "", city = "", area = "") {
  setCrumbs([{ label: "Ana sayfa", href: "#/" }, { label: "Firmalar" }]);
  setView(`<div class="section-head"><div><h1>Firmalar</h1><p>Resmi Ar-Ge ve Tasarım Merkezi olan firmalar. Bir firma seçin, onunla çalışan akademisyenleri görün.</p></div></div>
    <div class="toolbar"><div class="input">${icon("search")}<input id="firmQ" placeholder="Firma adı (ör. Aselsan, Arçelik)" value="${esc(q)}"></div>
      <select class="select" id="firmSector"><option value="">Tüm sektörler</option></select>
      <select class="select" id="firmCity"><option value="">Tüm iller</option></select>
      <select class="select" id="firmArea" aria-label="Çalışma alanı" hidden><option value="">Tüm çalışma alanları</option></select></div>
    <div id="fBody">${skeleton(4)}</div>`);
  let timer;
  const load = async () => {
    const qs = new URLSearchParams({ q: $("#firmQ").value.trim(), sector: $("#firmSector").value, city: $("#firmCity").value, area: $("#firmArea").value || area });
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
    if (d.areas?.length && $("#firmArea").options.length === 1) {
      $("#firmArea").insertAdjacentHTML("beforeend", d.areas.map((x) => `<option value="${esc(x.name)}" ${x.name === area ? "selected" : ""}>${esc(x.name)} (${x.count})</option>`).join(""));
      $("#firmArea").hidden = false;
    }
    $("#fBody").innerHTML = `<p class="faint" style="margin:0 0 12px">${fmtNum(d.count)} firma${d.count > d.items.length ? `, ilk ${d.items.length} gösteriliyor` : ""} · toplam ${fmtNum(d.total)} firma, ${fmtNum(d.info.count)} merkez · liste ${esc(d.info.imported || "")}</p>
      ${d.items.length ? `<div class="grid-3 stagger">${d.items.map((x, i) => `<a class="card org-head" style="--i:${i};margin:0;color:inherit;text-decoration:none" href="#/firma/${esc(x.id)}">
        <div class="org-logo">${icon("briefcase")}</div><div style="min-width:0"><h3 style="font-size:15px">${esc(x.name)}</h3>
        <div class="meta"><span>${esc(x.sectors.join(", "))}</span></div>
        ${x.areas?.tags?.length ? `<div class="faint" style="margin-top:6px;font-size:12.5px">${esc(x.areas.tags.slice(0, 3).map((t) => t.name).join(" · "))}</div>` : ""}
        <div class="chips" style="margin-top:8px"><span class="chip teal">${x.centers.length} merkez</span><span class="chip">${esc(x.cities.slice(0, 2).join(", "))}${x.cities.length > 2 ? "…" : ""}</span>
          ${x.profiles ? `<span class="chip gold">${icon("user")}${x.profiles} profil</span>` : ""}${x.academics ? `<span class="chip blue">${x.academics} akademisyen</span>` : ""}</div></div></a>`).join("")}</div>`
        : `<div class="card">${emptyState("search", "Firma bulunamadı", "Aramayı ya da filtreleri değiştirin.")}</div>`}`;
    hydrateIcons($("#fBody"));
  };
  $("#firmQ").oninput = () => { clearTimeout(timer); timer = setTimeout(load, 250); };
  $("#firmSector").onchange = load; $("#firmCity").onchange = load; $("#firmArea").onchange = () => { area = ""; load(); };
  load();
}

async function viewFirm(fid, refresh = false) {
  setCrumbs([{ label: "Ana sayfa", href: "#/" }, { label: "Firmalar", href: "#/firmalar" }, { label: "…" }]);
  setView(`<div id="firmHead">${skeleton(1)}</div><div class="card card-pad"><div class="loading-line"><span class="spinner"></span>
    OpenAlex ve TR Dizin'de firmayla ortak yayınlar taranıyor, profiller kontrol ediliyor…</div>${skeleton(3)}</div>`);
  let d;
  try { d = await api(`/api/firms/${encodeURIComponent(fid)}${refresh ? "?refresh=1" : ""}`); }
  catch (e) { setView(`<div class="card">${emptyState("briefcase", "Firma açılamadı", esc(e.message))}</div>`); return; }
  const f = d.firm;
  setCrumbs([{ label: "Ana sayfa", href: "#/" }, { label: "Firmalar", href: "#/firmalar" }, { label: f.name }]);
  const people = d.academics;
  const paperRow = (x) => `<div class="variants">${safeUrl(x.url) ? `<a href="${esc(safeUrl(x.url))}" target="_blank" rel="noopener">${esc(x.title)}</a>` : esc(x.title)}
    · ${esc(x.year || "?")} · ${esc(x.source)}${x.role ? ` · ${esc(x.role)}` : ""}${x.firm_people?.length ? ` · <span class="faint">firmadan: ${esc(x.firm_people.join(", "))}</span>` : ""}
    ${x.quote ? `<div class="faint" style="font-style:italic;margin-top:2px">“${esc(x.quote)}”</div>` : ""}</div>`;
  setView(`<section class="card org-head"><div class="org-logo">${icon("briefcase")}</div><div style="min-width:0;flex:1">
      <h1>${esc(f.name)}</h1><div class="meta"><span>${esc(f.sectors.join(", "))}</span><span>${esc(f.cities.join(", "))}</span></div>
      <div class="chips" style="margin-top:8px">${f.kinds.map((k) => `<span class="chip teal">✓ ${esc(k)}</span>`).join("")}</div>
      ${f.areas?.tags?.length ? `<div class="m-h" style="margin:14px 0 6px">Çalışma alanları</div><div class="chips">${f.areas.tags.map((t) => `<a class="chip blue" href="#/firmalar?area=${encodeURIComponent(t.name)}">${esc(t.name)}<sup>${t.count}</sup></a>`).join("")}</div>
        ${f.areas.topics?.length ? `<div class="chips" style="margin-top:6px">${f.areas.topics.map((t) => `<span class="chip">${esc(t.name)}<sup>${t.count}</sup></span>`).join("")}</div>` : ""}
        <p class="faint" style="margin:6px 0 0;font-size:12.5px">Firmanın ${fmtNum(f.areas.papers)} yayınının OpenAlex konularından; yayın dışı çalışmaları kapsamaz.</p>` : ""}
      <details style="margin-top:10px"><summary class="faint" style="cursor:pointer">${f.centers.length} kayıtlı merkez</summary>
        <ul style="margin:8px 0 0;padding-left:18px">${f.centers.map((c) => `<li class="faint">${esc(c)}</li>`).join("")}</ul></details></div>
      <button class="btn" id="firmRefresh" type="button">${icon("refresh")}Yeniden tara</button></section>
    ${d.errors.map((e) => `<div class="notice warn" style="margin-bottom:14px">${icon("info")}<div>${esc(e)}. Sonuç eksik olabilir; bu sonuç saklanmadı, sonra tekrar açın.</div></div>`).join("")}
    <div class="stat-row"><div class="stat"><b>${fmtNum(people.length)}</b><span>akademisyen</span></div>
      <div class="stat"><b>${fmtNum(d.papers)}</b><span>ortak yayın ve proje</span></div>
      <div class="stat src"><b>${Object.entries(d.by_source).map(([k, v]) => `${esc(k)} ${v}`).join(" · ") || "—"}</b><span>kaynak · ${esc(d.updated)}</span></div></div>
    <div class="tabs" role="tablist"><button class="tab active" data-tab="people" type="button">Akademisyenler<span class="n">${fmtNum(people.length)}</span></button>
      <button class="tab" data-tab="tubitak" type="button">TÜBİTAK<span class="n" id="tubitakN">${fmtNum(d.ardeb.length)}</span></button>
      <button class="tab" data-tab="patents" type="button" hidden>Patentler<span class="n" id="patentsN">0</span></button></div>
    <div class="panel" data-panel="patents"><div class="card card-pad" id="firmPatentsBox"></div></div>
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
  loadFirmPatents(fid, refresh);
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
  wosProfileWatch?.stop();
  const [path, qs] = (location.hash || "#/").slice(1).split("?");
  const params = new URLSearchParams(qs || "");
  const parts = path.split("/").filter(Boolean);
  closeDrawer();
  if (parts[0] !== "profil") S.chatRequest?.abort();
  if (parts[0] === "favori-makaleler" || parts[0] === "favori-akademisyenler") {
    location.replace(`#/kutuphane?tab=${parts[0] === "favori-makaleler" ? "papers" : "people"}`); return undefined;
  }
  setNav({ akademisyenler: "akademisyenler", profil: "akademisyenler", is: "akademisyenler", universiteler: "universiteler", universite: "universiteler", kurum: "universiteler",
    firmalar: "firmalar", firma: "firmalar", ara: "ara", kutuphane: "kutuphane", sistem: "sistem" }[parts[0]] || (parts.length ? "" : "home"));
  switch (parts[0]) {
    case "ara": return viewSearch(params.get("q") || "");
    case "kurum": return viewDirectory(params.get("u") || "");
    case "profil": return viewProfile(parts[1]);
    case "is": return viewJob(parts[1]);
    case "akademisyenler": return viewPeople(params.get("q") || "");
    case "kutuphane": return viewLibrary(params.get("tab") || "papers");
    case "sistem": return viewSystem();
    case "universiteler": return viewUnis();
    case "universite": return viewUni(parts[1]);
    case "firmalar": return viewFirms(params.get("q") || "", params.get("sector") || "", params.get("city") || "", params.get("area") || "");
    case "firma": return viewFirm(parts[1]);
    default: return viewHome();
  }
}

document.addEventListener("click", async (e) => {
  const t = e.target;
  const open = t.closest("[data-open]");
  if (open) { e.preventDefault(); openPaper(open.dataset.open); return; }
  const pat = t.closest("[data-patent]");
  if (pat) { e.preventDefault(); openPatent(PAT[+pat.dataset.patent]); return; }
  const star = t.closest("[data-star]");
  if (star) { toggleStar(star); return; }
  const del = t.closest("[data-delchat]");
  if (del) {
    e.stopPropagation();
    if (!confirm("Bu arama ve profil sonucu kalıcı olarak silinsin mi?")) return;
    await api(`/api/chats/${del.dataset.delchat}`, { method: "DELETE" }).catch(() => {});
    if (del.dataset.delchat === S.chatId) { S.result = null; S.chatId = null; }
    await loadChats();
    const row = del.closest(".person-row");
    if (row && !calmMotion()) { await row.animate([{ opacity: 1 }, { opacity: 0, transform: "translateX(16px)" }], { duration: 200, easing: EASE }).finished; }
    route(); return;
  }
  const unfav = t.closest("[data-unfav]");
  if (unfav) {
    e.stopPropagation();
    await api(`/api/favorites/people/${encodeURIComponent(unfav.dataset.unfav)}`, { method: "DELETE" }).catch(() => {});
    await loadFav(); viewLibrary("people"); return;
  }
  const chat = t.closest("[data-chat]");
  if (chat && chat.dataset.chat) { location.hash = `#/profil/${chat.dataset.chat}`; return; }
  const np = t.closest("[data-newperson]");
  if (np) { location.hash = `#/akademisyenler?q=${encodeURIComponent(np.dataset.newperson)}`; return; }
  const cand = t.closest("[data-candidate]");
  if (cand) { startFromYok(S.candidates[+cand.dataset.candidate]); return; }
  const byUrl = t.closest("[data-byurl]");
  if (byUrl) { newPersonModal("", byUrl.dataset.byurl || ""); return; }
  if (t.closest("[data-recipes]")) { showRecipes(); return; }
  if (t.closest("[data-scan]")) { scanChanges(); return; }
  if (t.closest("[data-clearall]")) {
    if (!confirm("Tüm profil sonuçları silinsin mi? Favoriler korunur.")) return;
    await api("/api/chats", { method: "DELETE" }).catch(() => {});
    S.result = null; S.chatId = null; await loadChats(); route(); return;
  }
  if (!t.closest("#omni") && $("#omniPop")) $("#omniPop").hidden = true;
  const org = t.closest("[data-org]");
  if (org) { location.hash = `#/kurum?u=${encodeURIComponent(org.dataset.org)}`; return; }
  const tab = t.closest("[data-tab]");
  if (tab) {
    switchTab(tab);
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
    $("#profilePublications")?.publicationTable?.reveal(cite.dataset.pub);
    const row = document.getElementById(`pub-${cite.dataset.pub}`);
    if (row) { row.scrollIntoView({ behavior: "smooth", block: "center" }); row.classList.add("flash"); setTimeout(() => row.classList.remove("flash"), 1600); }
    return;
  }
  const exp = t.closest("[data-export]");
  if (exp) {
    exportModal(exp.dataset.export);
    return;
  }
  const yp = t.closest("[data-yokpapers]");
  if (yp) { e.stopPropagation(); openYokPapers(+yp.dataset.yokpapers); return; }
  const up = t.closest("[data-unitpapers]");
  if (up) { e.stopPropagation(); openUnitPapers(up.dataset.unitpapers, +up.dataset.i); return; }
  if (t.closest("[data-facstaff]")) { const d = S.dir; selectDept(-1, d.data.items[d.fac].url); return; }
  const staffOpen = t.closest("[data-staff-open]");
  if (staffOpen) { openStaffProfile(staffOpen.dataset.staffOpen); return; }
  const prof = t.closest("[data-profile]");
  if (prof) {
    const d = S.dir, person = d.staff.items[+prof.dataset.profile];
    startJob(d.staff.page || person.url, person.name); return;
  }
  const unit = t.closest(".unit");
  if (unit) {
    ({ fac: selectFaculty, dep: selectDept, yfac: selectYokFaculty, ydep: selectYokDept })[unit.dataset.unit](+unit.dataset.i);
    return;
  }
  if (t.closest("[data-close]") || t.id === "modal" || t.closest("#modalClose")) { closeModal(); return; }
  if (t.closest("#drawerClose")) { closeDrawer(); return; }
});

document.addEventListener("input", (e) => {
  const f = e.target.dataset?.filter;
  if (!f) return;
  const q = fold(e.target.value);
  $$(`#${f} [data-q]`).forEach((el) => { el.style.display = !q || el.dataset.q.includes(q) ? "" : "none"; });
});
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  if (wosVerification?.isOpen()) { e.preventDefault(); wosVerification.hide(); return; }
  const filter = $(".dt-filter-popover:popover-open");
  if (filter) {
    e.preventDefault(); filter.hidePopover();
    $(`[popovertarget="${filter.id}"].dt-filter-toggle`)?.focus({ preventScroll: true });
    return;
  }
  closeModal(); closeDrawer();
});
$("#menuBtn").addEventListener("click", () => $("#app").classList.toggle("menu-open"));
$("#scrim").addEventListener("click", () => $("#app").classList.remove("menu-open"));
$("#themeBtn").addEventListener("click", toggleTheme);
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", (e) => { if (!storedTheme()) applyTheme(e.matches ? "dark" : "light"); });
window.addEventListener("hashchange", route);

(async () => {
  hydrateIcons();
  wosVerification = createWosVerification();
  const legacy = new URLSearchParams(location.search).get("chat");
  if (legacy) { history.replaceState(null, "", `/#/profil/${legacy}`); }
  loadEnv();
  applyTheme(document.documentElement.dataset.theme);
  await Promise.all([loadFav(), loadChats()]);
  route();
  document.fonts?.ready.then(() => { const a = $("#nav a.active"); if (a) setNav(a.dataset.nav); $("#navPill").classList.add("ready"); });
})();
