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
  dots: '<circle cx="5" cy="12" r="1.7"/><circle cx="12" cy="12" r="1.7"/><circle cx="19" cy="12" r="1.7"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
  home: '<path d="M3 11.5 12 4l9 7.5"/><path d="M5.5 10v10h13V10"/><path d="M10 20v-6h4v6"/>',
  arrow: '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="13 6 19 12 13 18"/>',
  compass: '<circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/>',
  search: '<circle cx="11" cy="11" r="7.5"/><line x1="21" y1="21" x2="16.6" y2="16.6"/>',
  filter: '<path d="M4 5h16l-6 7v6l-4 2v-8z"/>',
  map: '<path d="M21 10c0 7-9 13-9 13S3 17 3 10a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>',
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
  heart: '<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8l1 1.1L12 21l7.8-7.5 1-1.1a5.5 5.5 0 0 0 0-7.8z"/>',
  code: '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/><line x1="14" y1="4" x2="10" y2="20"/>',
  atom: '<circle cx="12" cy="12" r="1.6"/><ellipse cx="12" cy="12" rx="10" ry="4"/><ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(60 12 12)"/><ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(120 12 12)"/>',
  leaf: '<path d="M11 20A7 7 0 0 1 4 13c0-6 6-10 16-10 0 10-4 16-10 16z"/><path d="M4 21c4-5 7-8 12-11"/>',
  scale: '<path d="M12 3v18"/><path d="M5 21h14"/><path d="M3 7h18"/><path d="M6 7l-3 7a3 3 0 0 0 6 0z"/><path d="M18 7l-3 7a3 3 0 0 0 6 0z"/>',
  flame: '<path d="M12 22c4 0 7-3 7-7 0-5-4-7-5-11-2 2-3 4-3 6-1-1-2-2-2-4-2 2-4 5-4 9 0 4 3 7 7 7z"/>',
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
  fav: { papers: [], people: [], universities: [], firms: [] }, chats: [],
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
// Geçiş grameri: her etkileşim türünün kendi ekran geçişi var, karışmaz.
//   cube        → sayfalama (akademisyen/üniversite listeleri)
//   box         → menüler arası sayfa geçişi (CSS: html.tx-box)
//   perspective → listeden detaya gidiş, geri dönüşte ters (CSS: html.tx-perspective)
//   windmill    → firma önizleme modalı
//   squeeze     → yana açılan detay paneli (yayın özeti)
//   flip        → okuma köşesi: raftaki kitap/dergi kapağı
const TX = {
  cubeFrame(angle, r) { return `translateZ(${-r}px) rotateY(${angle}deg) translateZ(${r}px)`; },
  cube(el, dir, phase) {
    const r = Math.max(160, el.offsetWidth || 600) / 2, [a, b] = phase === "in" ? [dir * 90, 0] : [0, -dir * 90];
    return el.animate([
      { transform: TX.cubeFrame(a, r), filter: `brightness(${phase === "in" ? .72 : 1})` },
      { transform: TX.cubeFrame(b, r), filter: `brightness(${phase === "in" ? 1 : .72})` },
    ], { duration: 620, easing: "cubic-bezier(.65,0,.35,1)" });
  },
  windmill(el) {
    const o = "50% 240%";
    return el.animate([
      { transformOrigin: o, transform: "rotate(-26deg)", opacity: 0 },
      { transformOrigin: o, transform: "rotate(2.5deg)", opacity: 1, offset: .7 },
      { transformOrigin: o, transform: "rotate(-.6deg)", opacity: 1, offset: .88 },
      { transformOrigin: o, transform: "none", opacity: 1 },
    ], { duration: 680, easing: "cubic-bezier(.2,.8,.25,1)" });
  },
  windmillOut(el) {
    return el.animate([{ transformOrigin: "50% 240%", transform: "none", opacity: 1 }, { transformOrigin: "50% 240%", transform: "rotate(20deg)", opacity: 0 }],
      { duration: 320, easing: "cubic-bezier(.5,0,.9,.4)", fill: "forwards" });
  },
  // Yeni panel kenarından genişler; yanındaki alan aynı anda sıkışır (FLIP genişlik oranıyla)
  squeeze(el, { origin = "100% 50%", delay = 0, from = .08 } = {}) {
    return el.animate([{ transformOrigin: origin, transform: `scaleX(${from})`, opacity: 0, filter: "blur(2px)" },
      { transformOrigin: origin, transform: "scaleX(1.02)", opacity: 1, filter: "none", offset: .8 }, { transformOrigin: origin, transform: "none", opacity: 1 }],
      { duration: 520, delay, easing: "cubic-bezier(.3,.9,.3,1)", fill: "backwards" });
  },
  squeezeFrom(el, ratio, origin = "0% 50%") {
    return el.animate([{ transformOrigin: origin, transform: `scaleX(${ratio})` }, { transformOrigin: origin, transform: "none" }], { duration: 520, easing: "cubic-bezier(.3,.9,.3,1)" });
  },
  // Okuma köşesi için: kapak sol kenarından menteşe gibi açılır
  flip(el, { delay = 0 } = {}) {
    return el.animate([{ transformOrigin: "0% 50%", transform: "perspective(1400px) rotateY(0deg)" }, { transformOrigin: "0% 50%", transform: "perspective(1400px) rotateY(-165deg)" }],
      { duration: 900, delay, easing: "cubic-bezier(.6,.05,.3,1)", fill: "forwards" });
  },
};
// Sayılar sıfırdan yukarı sayar: count(n) ile yazılan her öğe için.
const count = (n) => `<span data-count="${Number(n) || 0}">${fmtNum(n)}</span>`;
function animateCounts(root = document) {
  if (calmMotion()) return;
  $$("[data-count]", root).forEach((el) => {
    const end = +el.dataset.count;
    delete el.dataset.count;
    if (end < 2) return;
    const start = performance.now(), ms = Math.min(1900, 1000 + end * 3);
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
  syncSidebar();
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
  const { quiet = false, ...requestOptions } = opts;
  if (!quiet) busy(1);
  try {
    const res = await fetch(url, { headers: { "Content-Type": "application/json" }, ...requestOptions });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const error = new Error(typeof err.detail === "string" ? err.detail : `İstek başarısız (HTTP ${res.status}).`);
      error.status = res.status;
      throw error;
    }
    return await res.json();
  } finally { if (!quiet) busy(-1); }
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
  let verificationActive = false, probeRequested = false, pollFailures = 0;
  const schedulePoll = (delay = 2500) => {
    clearTimeout(pollTimer);
    pollTimer = null;
    // Yalnız kullanıcının başlattığı veya sunucuda zaten çalışan WoS işi uyandırır.
    if (!stopped && !document.hidden && (probeRequested || (pollFailures < 3 && (verificationActive || items.size)))) {
      pollTimer = setTimeout(poll, delay);
    }
  };
  const requestProbe = () => {
    if (stopped) return;
    pollFailures = 0;
    // Yanıt alınırken yeni iş başladıysa eski "boş" yanıtın bildirimi yutmasını önle.
    if (pollRequest) { probeRequested = true; return; }
    if (pollTimer) return;
    probeRequested = true; schedulePoll(0);
  };
  const poll = async () => {
    pollTimer = null;
    if (stopped || document.hidden || pollRequest) return;
    probeRequested = false;
    const controller = new AbortController(); pollRequest = controller;
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch("/api/wos/verification", { cache: "no-store", credentials: "same-origin", signal: controller.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (stopped || controller.signal.aborted) return;
      if (!Array.isArray(data.items)) throw new Error("Geçersiz doğrulama durumu");
      pollFailures = 0;
      verificationActive = Boolean(data.active_jobs || data.pending_jobs);
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
    } catch { if (!stopped && !document.hidden) pollFailures += 1; /* Geçici hata canlı oturumu kapatmaz; tekrarlar sınırlıdır. */ }
    finally {
      clearTimeout(timeout); if (pollRequest === controller) pollRequest = null;
      schedulePoll(probeRequested ? 0 : pollFailures ? Math.min(15000, 2500 * 2 ** pollFailures) : 2500);
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
    if (document.hidden) {
      probeRequested = probeRequested || Boolean(pollRequest);
      disconnect(); clearTimeout(pollTimer); pollTimer = null; pollRequest?.abort();
    }
    else { if (dialog.open) connect(); schedulePoll(0); }
  });
  window.addEventListener("pagehide", () => {
    probeRequested = probeRequested || Boolean(pollRequest);
    stopped = true; clearTimeout(pollTimer); pollTimer = null; clearTimeout(missingTimer); missingTimer = null; missingId = null;
    pollRequest?.abort(); disconnect();
  });
  window.addEventListener("pageshow", () => { if (stopped) { stopped = false; if (dialog.open) connect(); schedulePoll(0); } });
  document.addEventListener("wos-work-requested", requestProbe);
  return { hide, isOpen: () => dialog.open };
}

const skeleton = (n = 5) => Array.from({ length: n }, () => `<div class="skel-row"><div class="skel"></div><div class="skel-lines"><div class="skel"></div><div class="skel"></div></div></div>`).join("");
const emptyState = (ic, title, text, extra = "") => `<div class="empty"><div class="em-icon">${icon(ic)}</div><h3>${esc(title)}</h3><p>${text}</p>${extra}</div>`;
function avatar(name, photo, cls = "av") {
  const img = safeImg(photo);
  return `<div class="${cls}">${esc(initials(name))}${img ? `<img src="${esc(img)}" alt="" loading="lazy" onerror="this.remove()">` : ""}</div>`;
}
const profilePhoto = (c) => (c.job_id ? `/api/jobs/${encodeURIComponent(c.job_id)}/photo?v=2` : "");

const orgId = (name) => fold(name).replace(/\s+/g, "-");
const organizationColors = new Map();
function organizationColor(img) {
  const url = img.currentSrc || img.src;
  if (organizationColors.has(url)) return organizationColors.get(url);
  let color = null;
  try {
    // Beyaz zemin ve siyah yazı yerine logodaki baskın renkli alanı kullan.
    const canvas = document.createElement("canvas"); canvas.width = canvas.height = 48;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context || !img.naturalWidth || !img.naturalHeight) return null;
    const scale = Math.min(48 / img.naturalWidth, 48 / img.naturalHeight);
    context.drawImage(img, 0, 0, img.naturalWidth * scale, img.naturalHeight * scale);
    const pixels = context.getImageData(0, 0, 48, 48).data, buckets = new Map();
    for (let i = 0; i < pixels.length; i += 4) {
      const [r, g, b, a] = pixels.subarray(i, i + 4);
      const high = Math.max(r, g, b), low = Math.min(r, g, b), saturation = high ? (high - low) / high : 0;
      if (a < 160 || high < 35 || low > 225 || saturation < .2) continue;
      const key = `${r >> 5}:${g >> 5}:${b >> 5}`, weight = saturation * a / 255;
      const bucket = buckets.get(key) || { weight: 0, r: 0, g: 0, b: 0 };
      bucket.weight += weight; bucket.r += r * weight; bucket.g += g * weight; bucket.b += b * weight;
      buckets.set(key, bucket);
    }
    const best = [...buckets.values()].sort((a, b) => b.weight - a.weight)[0];
    if (best) color = `rgb(${[best.r, best.g, best.b].map((v) => Math.round(v / best.weight)).join(", ")})`;
  } catch { /* Renk okunamasa da logo gösterilir; kurum için renk uydurulmaz. */ }
  organizationColors.set(url, color);
  return color;
}
function logoVisible(img) {
  try {
    const c = document.createElement("canvas"); c.width = c.height = 32;
    const x = c.getContext("2d", { willReadFrequently: true });
    x.drawImage(img, 0, 0, 32, 32);
    const d = x.getImageData(0, 0, 32, 32).data; let ink = 0;
    for (let i = 0; i < d.length; i += 4) if (d[i + 3] > 60 && Math.min(d[i], d[i + 1], d[i + 2]) < 225) ink++;
    return ink > 10;  // ≈%1: beyaz zemin için çizilmiş beyaz logo ya da boş görsel
  } catch { return true; }
}
function applyOrganizationBrand(img) {
  const local = (img.currentSrc || img.src).includes("/static/logos/");
  if (!img.naturalWidth || img.naturalWidth < 8 || (!local && !logoVisible(img))) { img.parentNode?.removeChild(img); return; }
  img.parentElement.classList.add("has-logo");
  // Renk/filigran yalnız profil ve kurum kapağında hesaplanır (listelerde canvas maliyeti yok)
  const card = img.closest(".identity-hero[data-org-brand]");
  if (!card) return;
  const url = new URL(img.currentSrc || img.src, location.href);
  if (url.origin !== location.origin || !/^\/(api\/organization-logo|static\/logos)\//.test(url.pathname)) return;
  card.style.setProperty("--org-logo", `url("${url.href}")`);
  const color = organizationColor(img);
  if (color) { card.style.setProperty("--org-color", color); card.classList.add("has-org-color"); }
  card.classList.add("has-org-logo");
}
function organizationLogo(kind, id, name, cls = "org-logo") {
  const remote = `/api/organization-logo/${kind}/${encodeURIComponent(id)}?v=6`;
  const src = kind === "universities" ? `/static/logos/universities/${encodeURIComponent(id)}.png` : remote;
  return `<span class="${cls} organization-logo" title="${esc(name || "Kurum")}"><span class="logo-fallback" style="--h:${[...String(name || "")].reduce((a, ch) => (a * 31 + ch.charCodeAt(0)) % 360, 11)}">${esc(initials(name))}</span>${id ? `<img src="${src}" data-remote="${remote}" alt="" loading="lazy" decoding="async" onload="applyOrganizationBrand(this)" onerror="logoFallback(this)">` : ""}</span>`;
}
// Yerel YÖK logosu yoksa sunucudaki logo toplayıcıya düş
function logoFallback(img) {
  if (img.dataset.remote && !img.src.includes("/api/organization-logo/")) { img.src = img.dataset.remote; return; }
  img.remove();
}
function organizationSaveButton(kind, id) {
  const on = (S.fav[kind] || []).some((x) => x.key === id);
  return `<button class="btn sm org-save ${on ? "saved" : ""}" data-save-org="${kind}" data-org-id="${esc(id)}" type="button" aria-pressed="${on}">${icon("bookmark")}${on ? "Kütüphanemde" : "Kaydet"}</button>`;
}
async function toggleOrganization(btn) {
  const kind = btn.dataset.saveOrg, id = btn.dataset.orgId;
  btn.disabled = true;
  try {
    if ((S.fav[kind] || []).some((x) => x.key === id)) {
      await api(`/api/favorites/${kind}/${encodeURIComponent(id)}`, { method: "DELETE" });
      toast("Kütüphaneden çıkarıldı.");
    } else {
      await post(`/api/favorites/${kind}`, { item: { id } });
      toast(`${icon("bookmark")}Kütüphanene kaydedildi.`);
    }
    await loadFav();
  if (seq !== S.routeSeq) return;
    if (location.hash.startsWith("#/kutuphane")) { viewLibrary(kind); return; }
    btn.outerHTML = organizationSaveButton(kind, id);
  } catch (e) { toast(esc(e.message)); btn.disabled = false; }
}

function syncSidebar() {
  const mobile = matchMedia("(max-width: 860px)").matches;
  const expanded = mobile ? $("#app").classList.contains("menu-open") : !$("#app").classList.contains("side-collapsed");
  const btn = $("#menuBtn");
  btn.setAttribute("aria-expanded", String(expanded));
  btn.setAttribute("aria-label", expanded ? "Menüyü daralt" : "Menüyü aç");
  btn.title = expanded ? "Menüyü daralt" : "Menüyü aç";
  $("#side").inert = mobile && !expanded;
  const active = $("#nav a.active");
  if (active) { $("#navPill").style.height = `${active.offsetHeight}px`; $("#navPill").style.transform = `translateY(${active.offsetTop}px)`; }
}
function toggleSidebar() {
  if (matchMedia("(max-width: 860px)").matches) $("#app").classList.toggle("menu-open");
  else {
    const on = $("#app").classList.toggle("side-collapsed");
    try { localStorage.setItem("sidebar-collapsed", on ? "1" : "0"); } catch { /* tercih */ }
  }
  syncSidebar();
}
function setupSidebar() {
  try { $("#app").classList.toggle("side-collapsed", localStorage.getItem("sidebar-collapsed") === "1"); } catch { /* tercih */ }
  $$("[data-nav]").forEach((el) => { el.title = el.querySelector(".nav-label")?.textContent.trim() || el.textContent.trim(); el.setAttribute("aria-label", el.title); });
  matchMedia("(max-width: 860px)").addEventListener("change", syncSidebar);
  $("#app").addEventListener("transitionend", (event) => {
    if (event.target === $("#app") && event.propertyName === "grid-template-columns") syncSidebar();
  });
  syncSidebar();
}
function showWelcome() {
  try { if (sessionStorage.getItem("academic-welcome-v2")) return; sessionStorage.setItem("academic-welcome-v2", "1"); } catch { /* oturum depolaması kapalı */ }
  const box = document.createElement("aside");
  box.className = "welcome-toast";
  box.setAttribute("aria-label", "Akademik İz'e hoş geldiniz");
  box.innerHTML = `<div class="welcome-symbol"><img src="/static/brand-mark.svg" alt=""></div><div class="welcome-copy"><span class="eyebrow">KEŞFET · İLİŞKİLENDİR · KAYDET</span><strong>Bilginin izini birlikte sürelim.</strong><p>Akademisyenler, üniversiteler ve firmalar.<br>Kaynaklarıyla, tek yerde.</p><a href="#/" class="welcome-link">Keşfetmeye başla ${icon("arrow")}</a></div><button class="icon-btn" type="button" aria-label="Karşılama mesajını kapat">${icon("x")}</button><div class="welcome-timer"></div>`;
  document.body.appendChild(box);
  const close = () => { clearTimeout(timer); box.classList.add("leaving"); setTimeout(() => box.remove(), 280); };
  let timer = setTimeout(close, 9000);
  $("button", box).onclick = close;
  $("a", box).onclick = close;
  box.onmouseenter = box.onfocusin = () => { clearTimeout(timer); box.classList.add("paused"); };
  box.onmouseleave = box.onfocusout = () => { timer = setTimeout(close, 5000); box.classList.remove("paused"); };
}

const PROFILE_SOURCES = ["yok", "openalex", "crossref", "orcid", "scholar", "trdizin", "openaire", "tez", "wos"];
const TOPIC_SOURCES = ["openalex", "crossref", "semantic_scholar", "trdizin", "openaire", "wos"];
const REFRESH_SECTIONS = [
  ["profile", "YÖK profili", "Kimlik, unvan, kurum ve fotoğraf", "user"],
  ["institution", "Kurum sayfası", "Üniversite sitesindeki profil bilgileri", "building"],
  ["publications", "Yayınlar", "Seçtiğin akademik kaynaklar", "book"],
  ["career", "Akademik geçmiş", "Görevler, eğitim ve deneyim", "award"],
  ["courses", "Dersler", "YÖK'teki ders kayıtları", "layers"],
  ["theses", "Tezler", "YÖK ve Tez Merkezi kayıtları", "file"],
  ["projects", "Projeler ve diğer", "TÜBİTAK, projeler ve faaliyetler", "grid"],
  ["industry", "İş birlikleri", "Akademisyenler ve firmalar", "users"],
  ["patents", "Patentler", "YÖK ve varsa EPO kayıtları", "briefcase"],
];
const refreshNotices = new Set();
function sourcePicker(id, available, selected, action = false) {
  const on = new Set(Array.isArray(selected) ? selected : available);
  return `<details class="source-picker" id="${id}"><summary class="btn sm">${icon("layers")}Kaynaklar <span class="source-count">${available.filter((s) => on.has(s)).length}</span>${icon("chevron")}</summary><div class="source-menu"><b>Hangi kaynaklar taransın?</b><p>Seçim, yeni taramada kullanılacak kaynakları belirler.</p><div class="source-options">${available.map((s) => `<label><input type="checkbox" name="scan-source" value="${s}" ${on.has(s) ? "checked" : ""}><span>${esc(SRC_TR[s] || s)}</span></label>`).join("")}</div><div class="source-menu-foot"><button class="link" type="button" data-sources-all>Tümünü seç</button><button class="btn sm primary" type="button" data-sources-apply>${action ? "Seçilenleri tara" : "Uygula"}</button></div></div></details>`;
}
function selectedSources(root) { return $$("input[name=scan-source]:checked", root).map((el) => el.value); }
function bindSourcePicker(root, onApply) {
  if (!root) return;
  const update = () => { const count = selectedSources(root).length; $(".source-count", root).textContent = count; $("[data-sources-apply]", root).disabled = !count; };
  root.addEventListener("change", update);
  $("[data-sources-all]", root).onclick = () => { $$("input", root).forEach((el) => { el.checked = true; }); update(); };
  $("[data-sources-apply]", root).onclick = () => { const sources = selectedSources(root); if (sources.length) { root.open = false; onApply(sources); } };
  update();
}
async function runProfileRefresh(r, sections, sources) {
  wosProfileWatch?.stop();
  await startJob(r.profile.institution || r.profile.source_url || "", r.profile.name,
    () => post(`/api/jobs/${r.job_id}/refresh`, { sections, sources }), "yenileniyor", sections,
    sections.includes("publications") && sources.includes("wos"));
}
function refreshProfileModal(r) {
  const prefs = r.refresh_preferences || {};
  const chosen = new Set(prefs.sections || ["publications"]);
  openModal(`<form id="refreshForm"><div class="modal-heading"><span class="modal-emblem">${icon("refresh")}</span><div><h2 id="refreshTitle">Neyi yenileyelim?</h2><p class="muted">${esc(r.profile.name)} · Yalnız seçtiğin bilgiler taranır.</p></div></div><div class="refresh-grid">${REFRESH_SECTIONS.map(([id, title, desc, ic]) => `<label class="refresh-choice"><input type="checkbox" name="section" value="${id}" ${chosen.has(id) ? "checked" : ""}><span class="choice-icon">${icon(ic)}</span><span><b>${title}</b><small>${desc}</small></span></label>`).join("")}</div><fieldset class="refresh-sources" id="refreshSources"><legend>Yayın kaynakları</legend><div class="source-options">${PROFILE_SOURCES.map((s) => `<label><input type="checkbox" name="scan-source" value="${s}" ${(prefs.sources || PROFILE_SOURCES).includes(s) ? "checked" : ""}><span>${esc(SRC_TR[s] || s)}</span></label>`).join("")}</div></fieldset><p class="refresh-note">Seçmediğin bilgiler, sohbetin ve kayıtlı yayınların korunur.</p><div class="modal-footer"><button class="btn" type="button" data-close>Vazgeç</button><button class="btn primary" id="refreshSubmit" type="submit">${icon("refresh")}Seçilenleri yenile</button></div></form>`);
  $(".modal-box").setAttribute("aria-labelledby", "refreshTitle");
  const form = $("#refreshForm");
  const update = () => {
    const sections = $$("[name=section]:checked", form).map((el) => el.value);
    $("#refreshSources").hidden = !sections.includes("publications");
    $("#refreshSubmit").disabled = !sections.length || sections.includes("publications") && !selectedSources(form).length;
  };
  form.onchange = update;
  form.onsubmit = (e) => { e.preventDefault(); const sections = $$("[name=section]:checked", form).map((el) => el.value); if (!sections.length) return; const sources = selectedSources(form); closeModal(); runProfileRefresh(r, sections, sources); };
  update();
}

// ------------------------------------------------------------------- ortam, geçmiş, favoriler
async function loadEnv() {
  const el = $("#env");
  try {
    const h = await api("/api/health");
    el.className = `env ${h.llm_ready ? "ok" : "warn"}`;
    el.innerHTML = `<span class="dot"></span><span title="REA ${h.rea ? "hazır" : "yok"} · Chromium ${h.chromium ? "hazır" : "yok"}">${esc(h.llm)}</span>`;
    // Normal açılış isteğinin yerel iş özeti: boşta doğrulama isteği gönderme.
    const activity = h.wos_activity;
    if (activity && (activity.active_jobs || activity.pending_jobs || activity.waiting_verifications)) {
      document.dispatchEvent(new Event("wos-work-requested"));
    }
  } catch { el.className = "env warn"; el.innerHTML = `<span class="dot"></span><span>Sunucuya ulaşılamadı</span>`; }
}

async function loadChats() {
  try { S.chats = await api("/api/chats"); } catch { S.chats = []; }
  $("#cntProfiles").textContent = S.chats.length || "";
}

async function loadFav() {
  try { S.fav = { papers: [], people: [], universities: [], firms: [], ...await api("/api/favorites") }; } catch { /* sunucu yok */ }
  $("#cntLibrary").textContent = Object.values(S.fav).reduce((n, items) => n + (Array.isArray(items) ? items.length : 0), 0) || "";
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
      S.staffRegistry.set(id, { person: p, mode: options.mode, page: options.page, institution: options.institution, onRefresh: options.onRefresh });
      const metrics = [["article_count", "makale"], ["citations", "atıf"]].map(([key, label]) => {
        const value = staffMetric(p, key); return value == null ? `${label === "makale" ? "Makale" : "Atıf"} sayısı bilinmiyor` : `${fmtNum(value)} ${label}`;
      }).join(" · ");
      const state = { idle: "Taranmadı · Yenile ile tara", pending: p.status ? "Sırada" : "Profil henüz toplanmadı", running: "Toplanıyor", done: "Tamamlandı", partial: "Kısmi sonuç", error: "Alınamadı", missing: "Eşleşmedi", cancelled: "Durduruldu" }[p.status || p.state];
      const busyRow = ["pending", "running"].includes(p.status);
      const refreshBtn = options.onRefresh && p.person_key ? `<button class="btn sm ${p.status === "idle" ? "primary" : ""}" data-staff-refresh="${id}" type="button" ${busyRow ? "disabled" : ""} title="Bu akademisyeni kaynaklardan tara (WoS hariç)">${busyRow ? '<span class="spinner" aria-hidden="true"></span>' : icon("refresh")}Yenile</button>` : "";
      return `<div class="person staff-person" style="--i:${Math.min(i, 24)}">${avatar(p.name, p.photo)}
        <div class="p-main"><b>${esc(p.name)}</b>${options.mode === "yok" ? staffRoles(p).map((r) => `<span class="role-badge ${/^(Dekan|Bölüm Başkanı)$/.test(r) ? "lead" : ""}">${esc(r)}</span>`).join("") : ""}<span>${esc([p.title, p.department].filter(Boolean).join(" · "))}</span>
          <span class="staff-metrics">${esc(metrics)}</span>${staffSources(p).length ? `<div class="chips">${sourceBadges({ sources: staffSources(p) })}</div>` : ""}${state ? `<span class="faint">${esc(state)}</span>` : ""}</div>
        <div class="p-act">${p.email ? `<a class="icon-btn" href="mailto:${esc(p.email)}" title="${esc(p.email)}">${icon("mail")}</a>` : ""}
          ${safeUrl(p.site_url || p.url) ? `<a class="icon-btn" href="${esc(safeUrl(p.site_url || p.url))}" target="_blank" rel="noopener" title="Kişinin kaynak sayfası">${icon("external")}</a>` : ""}
          ${refreshBtn}<button class="btn sm ${p.chat_id || refreshBtn ? "" : "primary"}" data-staff-open="${id}" type="button">${p.chat_id ? "Aç" : "Profil"}</button></div></div>`;
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
    try { return await api(endpoint, { method, ...(method === "POST" ? { body: "{}" } : {}), signal: controller.signal, quiet: true }); }
    finally { clearTimeout(timeout); if (request === controller) request = null; }
  };
  const notifyFailure = (data) => {
    const report = data.publications || {}, reason = data.reason || report.reason || "";
    const status = ["blocked", "error", "partial"].includes(data.status) ? data.status : report.status;
    if (!["blocked", "error", "partial"].includes(status)) return;
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
    const scanState = $("#profileWosState");
    if (scanState) {
      const running = ["running", "pending"].includes(data.status);
      const phases = { queued: "WoS sırası bekleniyor", publications: "WoS yayınları alınıyor", quartiles: "JCR bilgileri kontrol ediliyor" };
      const label = running ? `${phases[data.phase] || "WoS taranıyor"}${data.total ? ` · ${data.checked || 0}/${data.total}` : ""}`
        : ["partial", "error", "blocked"].includes(data.status) ? "WoS kısmen tamamlandı · alınan kayıtlar korundu" : "";
      scanState.innerHTML = `${running ? '<span class="spinner"></span>' : ""}${esc(label)}`;
    }
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
    let method = "GET", failures = 0;
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
          // Durum isteğini sınırlı sayıda yeniden dene; yeni tarama başlatma.
          method = "GET";
          if (++failures >= 5) { notifyFailure({ status: "error", reason: "connection_lost", message: "WoS durum bağlantısı kesildi. Kayıtlı veriler korunuyor." }); break; }
          await delay(Math.min(15000, 2500 * 2 ** Math.min(failures, 3)));
          continue;
        }
        if (!active()) break;
        failures = 0; apply(data);
        if (["running", "pending"].includes(data.status)) {
          document.dispatchEvent(new Event("wos-work-requested"));
          method = "GET"; await delay(document.hidden ? 15000 : 4000); continue;
        }
        if (wakeRequested) { method = "GET"; continue; }
        if (data.status === "idle") {
          // Kayıtlı profili açmak yeni tarama başlatmaz. Yenile seçimi sunucuda başlatır.
          break;
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
let modalPreviousFocus = null;
// Bütün modallar klasör gibi açılır: tıklanan öğenin kutusundan büyür, kapanırken oraya geri küçülür.
let modalTap = null, modalTapAt = 0, modalOrigin = null;
document.addEventListener("pointerdown", (e) => {
  if (e.target.closest("#modal")) return;
  modalTap = e.target.closest("button, a, [role=button], .card, article, li, tr, .bubble") || null; modalTapAt = performance.now();
}, true);
const FOLDER_EASE = "cubic-bezier(.22,.9,.24,1)";
function folderTransform(from, to) {
  const sx = Math.max(.04, from.width / to.width), sy = Math.max(.04, from.height / to.height);
  return `translate(${from.left + from.width / 2 - (to.left + to.width / 2)}px, ${from.top + from.height / 2 - (to.top + to.height / 2)}px) scale(${sx}, ${sy})`;
}
function modalGrow(box) {
  box.style.animation = "none";
  if (calmMotion()) return;
  const src = modalTap?.isConnected && performance.now() - modalTapAt < 2500 ? modalTap : null;
  const rect = src?.getBoundingClientRect();
  modalOrigin = rect && rect.width > 4 && rect.height > 4 ? src : null;
  if (!modalOrigin) {
    box.animate([{ opacity: 0, transform: "translateY(14px) scale(.97)" }, { opacity: 1, transform: "none" }], { duration: 320, easing: FOLDER_EASE });
    return;
  }
  modalOrigin.classList.add("opening");
  box.animate([{ transform: folderTransform(rect, box.getBoundingClientRect()), borderRadius: "28px", opacity: .6 }, { transform: "none", borderRadius: "20px", opacity: 1 }],
    { duration: 620, easing: FOLDER_EASE });
  $("#modalBody").animate([{ opacity: 0, transform: "scale(.96)" }, { opacity: 1, transform: "none" }], { duration: 420, delay: 260, easing: FOLDER_EASE, fill: "backwards" });
}
function openModal(html) {
  $(".welcome-toast")?.remove();
  const modal = $("#modal"), box = $(".modal-box", modal), wasHidden = modal.hidden;
  if (modal.hidden) modalPreviousFocus = document.activeElement;
  $("#modalBody").innerHTML = html; hydrateIcons($("#modalBody"));
  box.removeAttribute("aria-labelledby");
  const title = $("h2", box);
  if (title) { title.id ||= "modalTitle"; box.setAttribute("aria-labelledby", title.id); }
  modal.classList.remove("closing"); modal.hidden = false;
  $("#app").inert = true;
  if (wasHidden) modalGrow(box);
  requestAnimationFrame(() => { if (!modal.hidden) $("input:not([disabled]), button", box)?.focus({ preventScroll: true }); });
}
function closeModal() {
  S.paperRequest?.abort(); S.paperRequest = null;
  const modal = $("#modal");
  if (modal.hidden) return;
  const finish = () => {
    modal.hidden = true; modal.classList.remove("closing"); $("#app").inert = false;
    if (modalPreviousFocus?.isConnected) modalPreviousFocus.focus({ preventScroll: true });
    modalPreviousFocus = null;
  };
  const origin = modalOrigin; modalOrigin = null;
  const done = () => { origin?.classList.remove("opening"); finish(); };
  if (calmMotion()) { done(); return; }
  const box = $(".modal-box", modal);
  if (origin?.isConnected && origin.getBoundingClientRect().width > 4) {
    // Klasör kapanışı: kutu açıldığı öğeye geri küçülür
    modal.classList.add("closing-folder");
    modal.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 440, easing: "ease-in", fill: "forwards" });
    box.animate([{ transform: "none", opacity: 1 }, { transform: folderTransform(origin.getBoundingClientRect(), box.getBoundingClientRect()), borderRadius: "28px", opacity: .3 }],
      { duration: 460, easing: FOLDER_EASE, fill: "forwards" }).finished
      .then(() => { modal.getAnimations().forEach((a) => a.cancel()); box.getAnimations().forEach((a) => a.cancel()); modal.classList.remove("closing-folder"); done(); }, done);
    return;
  }
  modal.classList.add("closing");
  setTimeout(() => { if (modal.classList.contains("closing")) done(); }, 170);
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
  rememberPaper(p);
  S.paperRequest?.abort();
  const controller = new AbortController(); S.paperRequest = controller;
  openModal(`<div class="m-kicker">${sourceBadges(p)}
      <span>${esc(p.year || "")}</span>${p.citations != null ? `<span>· ${fmtNum(p.citations)} atıf</span>` : ""}</div>
    <h2 class="m-title">${esc(p.title)}</h2>
    <div id="mMeta" class="muted">${esc(p.venue || "")}</div><div id="mAuthors"></div>
    <div class="m-publication-status">${publicationStatusHtml(p)}</div>
    <div class="m-h">Türkçe özet</div><div id="mSum" class="m-sum typing"></div>
    <div class="m-h">Özet (abstract)</div><div id="mAbs" class="m-abs muted"><div class="loading-line"><span class="spinner"></span>Kaynak okunuyor…</div></div>
    <div id="mLinks" class="chips" style="margin-top:16px"></div>
    <div id="mStages" class="stages"></div>`);
  const sumEl = $("#mSum"), absEl = $("#mAbs"), stages = $("#mStages"), meta = $("#mMeta"), links = $("#mLinks");
  loadPaperAuthors(p);
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
          (safeUrl(d.pdf) || p.doi || d.doi) && `<button class="btn sm primary" type="button" data-pdf="${esc(safeUrl(d.pdf) || "")}" data-doi="${esc(p.doi || d.doi || "")}" data-title="${esc(p.title)}">${icon("book")}PDF oku</button>`].filter(Boolean).join("");
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
  const known = new Set(S.chats.map(c => c.id));
  const visits = readRecentVisits().filter(v => v.kind !== "person" || known.has(v.id));
  const seen = new Set(visits.map(v => `${v.kind}:${v.id}`));
  const recent = [...visits, ...S.chats.filter(c => !seen.has(`person:${c.id}`)).map(c => ({ kind: "person", id: c.id, name: c.name, at: Date.parse(c.updated || c.created || "") || 0 }))].sort((a, b) => b.at - a.at).slice(0, 10);
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
      <div class="lc-head"><h3>Son incelenenler</h3><span class="faint">Akademisyen · Firma · Konu</span></div>
      <div class="stagger profile-card-list">${recent.map((entry, i) => recentVisitHtml(entry, i + 6)).join("")}</div></div>` : ""}`);
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
  return `<div class="person-row pr-v2" data-org-brand role="link" tabindex="0" aria-label="${esc(c.name)} profilini aç" style="--i:${Math.min(i, 24)}" data-chat="${esc(c.id)}" data-q="${esc(fold(`${c.name} ${c.institution || ""}`))}" data-ints="${esc(ints.map(fold).join("|"))}">
    ${avatar(c.name, profilePhoto(c), "av pr-av")}
    <div class="pr-main"><b>${esc(c.name || "?")}</b><span class="pr-title">${esc(c.title || "")}${c.title ? " · " : ""}<em class="pr-count">${fmtNum(c.papers)} yayın</em></span></div>
    ${c.institution ? `<div class="pr-uni">${organizationLogo("universities", orgId(c.institution), c.institution, "pr-logo")}<span>${esc(c.institution)}</span></div>` : ""}
    <button class="h-del" data-delchat="${esc(c.id)}" type="button" aria-label="Sil" title="Profili sil">${icon("x")}</button></div>`;
}
document.addEventListener("keydown", (event) => {
  if (event.target.matches?.('.person-row[role="link"][data-chat]') && ["Enter", " "].includes(event.key)) {
    event.preventDefault(); event.target.click();
  }
});

// --------------------------------------------------------- klasör görünümü (üniversiteye göre gruplu)
const peopleView = () => { try { return localStorage.getItem("peopleView") || "folders"; } catch { return "folders"; } };
function chatGroups(chats) {
  const map = new Map();
  for (const c of chats) {
    const key = orgId(c.institution || "") || "_";
    if (!map.has(key)) map.set(key, { key, name: c.institution || "Kurumu bilinmeyen", items: [] });
    map.get(key).items.push(c);
  }
  return [...map.values()].sort((a, b) => b.items.length - a.items.length || a.name.localeCompare(b.name, "tr"));
}
function folderGrid(chats) {
  S.folders = chatGroups(chats);
  return `<div class="folder-grid stagger">${S.folders.map((g, i) => {
    const ints = [...new Set(g.items.flatMap((c) => chatInterests(c).map(fold)))];
    const preview = g.items.slice(0, g.items.length > 9 ? 8 : 9), more = g.items.length - preview.length;
    return `<button type="button" class="folder" data-folder="${i}" style="--i:${Math.min(i, 16)}" data-q="${esc(fold(`${g.name} ${g.items.map((c) => c.name).join(" ")}`))}" data-ints="${esc(ints.join("|"))}" aria-label="${esc(g.name)}: ${g.items.length} profil">
      <span class="folder-box"><span class="folder-icons">${preview.map((c) => `<span class="fi-cell">${avatar(c.name, profilePhoto(c))}</span>`).join("")}${more > 0 ? `<span class="fi-cell fi-more">+${more}</span>` : ""}</span></span>
      <span class="folder-label"><b>${esc(g.name)}</b></span></button>`;
  }).join("")}</div>`;
}
// Yatay sayfalama: sürükleme iptalinde temel görünüm her zaman geri yüklenir.
function mountPager(host, { per, render, pageClass = "", empty = "" }) {
  let items = [], page = 0, gesture = null, suppressUntil = 0;
  host.classList.add("pager"); host.tabIndex = 0;
  host.innerHTML = `<button class="pager-arrow prev" type="button" aria-label="Önceki sayfa">${icon("chevron")}</button><div class="pager-stage"></div><button class="pager-arrow next" type="button" aria-label="Sonraki sayfa">${icon("chevron")}</button><div class="pager-dots"></div>`;
  hydrateIcons(host);
  const stage = $(".pager-stage", host), dots = $(".pager-dots", host);
  const pages = () => Math.max(1, Math.ceil(items.length / per));
  const sheet = n => {
    const el = document.createElement("div"); el.className = `pager-page ${pageClass}`;
    el.innerHTML = items.length ? items.slice(n * per, n * per + per).map(render).join("") : empty;
    hydrateIcons(el); return el;
  };
  const reset = () => {
    const previous = gesture; gesture = null;
    previous?.events.abort(); host.classList.remove("dragging");
    if (previous && stage.hasPointerCapture(previous.id)) stage.releasePointerCapture(previous.id);
    for (const child of stage.children) {
      child.getAnimations().forEach(animation => animation.cancel());
      child.style.removeProperty("transform"); child.style.removeProperty("transform-origin");
      child.style.removeProperty("opacity"); child.style.removeProperty("filter");
    }
    stage.querySelectorAll("[data-pager-leaving]").forEach(child => child.remove());
  };
  const ui = () => {
    const n = pages();
    $(".prev", host).disabled = page === 0; $(".next", host).disabled = page >= n - 1;
    host.classList.toggle("single", n < 2);
    dots.innerHTML = n < 2 ? "" : n > 12 ? `<span>${page + 1} / ${n}</span>`
      : Array.from({ length: n }, (_, i) => `<button type="button" class="${i === page ? "on" : ""}" data-page="${i}" aria-label="Sayfa ${i + 1}"></button>`).join("");
  };
  const go = n => {
    n = Math.max(0, Math.min(pages() - 1, n));
    reset();
    if (n === page) return;
    const direction = n > page ? 1 : -1, previous = stage.firstElementChild;
    page = n;
    const next = sheet(page); stage.replaceChildren(next); ui();
    if (!calmMotion()) {
      // Küp: iki yüz ortak merkez etrafında birlikte döner, yön gidilen sayfaya göre
      TX.cube(next, direction, "in");
      if (previous) {
        previous.dataset.pagerLeaving = "";
        previous.inert = true;
        previous.setAttribute("aria-hidden", "true");
        stage.append(previous);
        const animation = TX.cube(previous, direction, "out");
        animation.onfinish = animation.oncancel = () => previous.remove();
      }
    }
  };
  const end = (event, commit = false) => {
    if (!gesture || (event.pointerId != null && event.pointerId !== gesture.id)) return;
    const dx = Number.isFinite(event.clientX) ? event.clientX - gesture.x : gesture.dx;
    const moved = gesture.moved;
    reset();
    if (!moved) return;
    suppressUntil = performance.now() + 300;
    if (commit && Math.abs(dx) > Math.min(100, stage.clientWidth * .18)) go(page + (dx < 0 ? 1 : -1));
  };
  stage.addEventListener("pointerdown", event => {
    if (event.button !== 0 || event.isPrimary === false || event.target.closest("input, textarea, select")) return;
    reset(); suppressUntil = 0;
    const events = new AbortController(), options = { signal: events.signal };
    gesture = { id: event.pointerId, x: event.clientX, y: event.clientY, dx: 0, moved: false, events };
    window.addEventListener("pointermove", move => {
      if (!gesture || move.pointerId !== gesture.id) return;
      if (move.pointerType === "mouse" && move.buttons === 0) { end(move); return; }
      const dx = move.clientX - gesture.x, dy = move.clientY - gesture.y;
      gesture.dx = dx;
      if (!gesture.moved) {
        if (Math.abs(dy) > 10 && Math.abs(dy) > Math.abs(dx)) { end(move); return; }
        if (Math.abs(dx) < 8) return;
        gesture.moved = true; host.classList.add("dragging");
        stage.setPointerCapture(move.pointerId);
      }
      if (move.cancelable) move.preventDefault();
      const atEdge = (page === 0 && dx > 0) || (page === pages() - 1 && dx < 0);
      const offset = Math.max(-stage.clientWidth * .35, Math.min(stage.clientWidth * .35, dx * (atEdge ? .15 : .7)));
      if (stage.firstElementChild && !calmMotion()) {
        const face = stage.firstElementChild;
        face.style.transformOrigin = "50% 50%";
        face.style.transform = TX.cubeFrame(offset / Math.max(1, stage.clientWidth) * 90, Math.max(160, face.offsetWidth) / 2);
      }
    }, { ...options, passive: false });
    window.addEventListener("pointerup", event => end(event, true), options);
    window.addEventListener("pointercancel", event => end(event), options);
    window.addEventListener("blur", event => end(event), options);
    document.addEventListener("visibilitychange", event => { if (document.hidden) end(event); }, options);
  });
  stage.addEventListener("lostpointercapture", event => end(event));
  host.addEventListener("dragstart", event => event.preventDefault());
  host.addEventListener("click", event => {
    if (performance.now() < suppressUntil) { event.preventDefault(); event.stopPropagation(); }
  }, true);
  $(".prev", host).onclick = () => go(page - 1);
  $(".next", host).onclick = () => go(page + 1);
  dots.onclick = event => { const button = event.target.closest("[data-page]"); if (button) go(Number(button.dataset.page)); };
  host.addEventListener("keydown", event => {
    if (event.target.closest("input, textarea, select")) return;
    if (event.key === "ArrowRight" || event.key === "ArrowLeft") { event.preventDefault(); go(page + (event.key === "ArrowRight" ? 1 : -1)); }
    if (event.key === "Escape") reset();
  });
  return { set(list) { reset(); items = list; page = 0; stage.replaceChildren(sheet(0)); ui(); }, go };
}
// Daktilo: metin harf harf yazılır
function typeText(el, text, speed = 38) {
  if (!el) return;
  clearInterval(el._typer);
  if (calmMotion()) { el.textContent = text; return; }
  let i = 0; el.textContent = ""; el.classList.add("typing-title");
  el._typer = setInterval(() => {
    el.textContent = text.slice(0, ++i);
    if (i >= text.length) { clearInterval(el._typer); setTimeout(() => el.classList.remove("typing-title"), 900); }
  }, speed);
}
// ⋮ seçenek menüsü
document.addEventListener("click", (e) => {
  const btn = e.target.closest(".kebab-btn");
  $$(".kebab-menu:not([hidden])").forEach((m) => { if (!btn || m !== btn.nextElementSibling) m.hidden = true; });
  if (btn) { const m = btn.nextElementSibling; m.hidden = !m.hidden; }
});
// Apple Watch ızgarası: petek dizilim; merkeze yakın balon büyük ve öne, kenardakiler küçülüp geriye eğilir
function mountWatch(body) {
  const grid = $(".watch-grid", body), baseSize = body.classList.contains("firm-watch") ? 108 : 96;
  let zoom = 1, raf = 0, inertia = 0, items = [], positions = [], columns = 1, visible = new Set();
  body.tabIndex = 0; body.setAttribute("aria-label", "Firma peteği; ok tuşlarıyla gezin, artı ve eksiyle yakınlaştırın");
  const shell = document.createElement("div"); shell.className = "watch-shell"; body.before(shell); shell.appendChild(body);
  const scrollbar = document.createElement("input"); scrollbar.type = "range"; scrollbar.className = "watch-scrollbar";
  scrollbar.min = "0"; scrollbar.max = "1"; scrollbar.step = "1"; scrollbar.value = "0"; scrollbar.setAttribute("aria-label", "Firmalarda aşağı yukarı gezin");
  shell.appendChild(scrollbar);
  const syncScroll = () => { scrollbar.max = String(Math.max(0, body.scrollHeight - body.clientHeight)); scrollbar.value = String(body.scrollTop); scrollbar.disabled = Number(scrollbar.max) === 0; };
  scrollbar.oninput = () => { body.scrollTop = Number(scrollbar.value); };
  let drag = null, suppressUntil = 0;
  const endDrag = event => {
    if (!drag || (event?.pointerId != null && drag.id !== event.pointerId)) return;
    const previous = drag; drag = null;
    previous.events.abort(); body.classList.remove("panning");
    if (previous.moved) suppressUntil = performance.now() + 300;
    if (body.hasPointerCapture(previous.id)) body.releasePointerCapture(previous.id);
    syncScroll();
    if (event?.type === "pointerup" && previous.moved && !calmMotion()) {
      let vx = previous.vx, vy = previous.vy, last = performance.now();
      if (last - previous.time > 90) return;
      const coast = now => {
        if (!body.isConnected) return;
        const dt = Math.min(32, now - last); last = now;
        const left = body.scrollLeft, top = body.scrollTop;
        body.scrollLeft -= vx * dt; body.scrollTop -= vy * dt;
        vx *= Math.exp(-dt / 180); vy *= Math.exp(-dt / 180);
        if (Math.hypot(vx, vy) > .02 && (body.scrollLeft !== left || body.scrollTop !== top)) inertia = requestAnimationFrame(coast);
      };
      inertia = requestAnimationFrame(coast);
    }
  };
  body.addEventListener("dragstart", event => event.preventDefault());
  body.addEventListener("pointerdown", event => {
    if (event.button !== 0 || event.isPrimary === false || event.target.closest("input, button, textarea, select")
        || event.clientX - body.getBoundingClientRect().left >= body.clientWidth) return;
    cancelAnimationFrame(inertia); endDrag(); suppressUntil = 0;
    const events = new AbortController(), options = { signal: events.signal, capture: true };
    drag = { id: event.pointerId, x: event.clientX, y: event.clientY, top: body.scrollTop, left: body.scrollLeft, moved: false, events, vx: 0, vy: 0, lastX: event.clientX, lastY: event.clientY, time: performance.now() };
    window.addEventListener("pointermove", move => {
      if (!drag || drag.id !== move.pointerId) return;
      if (!body.isConnected || (move.pointerType === "mouse" && move.buttons === 0)) { endDrag(move); return; }
      const dx = move.clientX - drag.x, dy = move.clientY - drag.y;
      if (!drag.moved && Math.hypot(dx, dy) < 6) return;
      if (!drag.moved) {
        drag.moved = true; body.classList.add("panning");
        body.setPointerCapture(move.pointerId);
      }
      if (move.cancelable) move.preventDefault();
      const now = performance.now(), dt = Math.max(1, now - drag.time);
      drag.vx = .6 * drag.vx + .4 * (move.clientX - drag.lastX) / dt;
      drag.vy = .6 * drag.vy + .4 * (move.clientY - drag.lastY) / dt;
      drag.lastX = move.clientX; drag.lastY = move.clientY; drag.time = now;
      body.scrollTop = drag.top - dy; body.scrollLeft = drag.left - dx;
    }, { ...options, passive: false });
    window.addEventListener("pointerup", endDrag, options);
    window.addEventListener("pointercancel", endDrag, options);
    window.addEventListener("blur", endDrag, options);
    window.addEventListener("pagehide", endDrag, options);
    window.addEventListener("hashchange", endDrag, options);
    document.addEventListener("visibilitychange", event => { if (document.hidden) endDrag(event); }, options);
  });
  body.addEventListener("lostpointercapture", endDrag);
  body.addEventListener("pointerleave", event => { if (drag && !drag.moved) endDrag(event); });
  body.addEventListener("click", event => {
    if (performance.now() < suppressUntil) { event.preventDefault(); event.stopPropagation(); }
  }, true);
  const paint = () => {
    if (raf) return;
    raf = requestAnimationFrame(() => {
      raf = 0;
      if (!body.isConnected) return;
      const width = body.clientWidth, height = body.clientHeight;
      const cx = body.scrollLeft + width / 2, cy = body.scrollTop + height / 2;
      const stepY = (baseSize + 30) * .866 * zoom;
      const firstRow = Math.max(0, Math.floor((body.scrollTop - 180) / stepY));
      const lastRow = Math.ceil((body.scrollTop + height + 180) / stepY);
      const nextVisible = new Set();
      for (let i = firstRow * columns; i < Math.min(items.length, (lastRow + 1) * columns); i++) {
        const b = items[i], [x, y] = positions[i];
        const px = x * zoom, py = y * zoom;
        if (px < body.scrollLeft - 180 || px > body.scrollLeft + width + 180) continue;
        nextVisible.add(i);
        if (!visible.has(i)) b.style.visibility = "visible";
        const dx = px + baseSize / 2 - cx, dy = py + baseSize / 2 - cy;
        const d = Math.min(1.4, Math.hypot(dx / Math.max(1, width / 2), dy / Math.max(1, height / 2)));
        const depth = Math.max(.48, 1 - .28 * d * d);
        const bend = calmMotion() ? "" : ` perspective(900px) rotateX(${-dy / height * 12}deg) rotateY(${dx / width * 12}deg)`;
        b.style.transform = `translate3d(${px}px, ${py}px, 0)${bend} scale(${zoom * depth})`;
        b.style.setProperty("--shade", String(Math.min(.65, d * .38)));
      }
      for (const i of visible) if (!nextVisible.has(i) && items[i]) items[i].style.visibility = "hidden";
      visible = nextVisible;
    });
  };
  const sizeCanvas = () => {
    grid.style.width = `${Math.max(body.clientWidth, (columns + .5) * (baseSize + 30) * zoom + 40)}px`;
    grid.style.height = `${Math.max(body.clientHeight, (Math.ceil(items.length / columns) * (baseSize + 30) * .866 + 80) * zoom)}px`;
  };
  const layout = () => {
    items = $$(".bubble:not([hidden])", grid);
    columns = Math.max(3, Math.floor((body.clientWidth - 40) / (baseSize + 30)));
    visible = new Set();
    positions = items.map((b, i) => {
      const row = Math.floor(i / columns), col = i % columns;
      b.style.left = "0"; b.style.top = "0"; b.style.visibility = "hidden";
      b.querySelectorAll("img").forEach(img => { img.loading = "lazy"; img.decoding = "async"; });
      return [20 + (col + (row % 2) * .5) * (baseSize + 30), 30 + row * (baseSize + 30) * .866];
    });
    sizeCanvas(); syncScroll(); paint();
  };
  const zoomTo = (value, anchorX = body.clientWidth / 2, anchorY = body.clientHeight / 2) => {
    cancelAnimationFrame(inertia); endDrag();
    const oldZoom = zoom;
    zoom = Math.max(.55, Math.min(2.2, value));
    const x = (body.scrollLeft + anchorX) / oldZoom, y = (body.scrollTop + anchorY) / oldZoom;
    sizeCanvas(); body.scrollLeft = x * zoom - anchorX; body.scrollTop = y * zoom - anchorY;
    syncScroll(); paint();
  };
  const controls = document.createElement("div"); controls.className = "watch-zoom";
  controls.innerHTML = '<button type="button" aria-label="Uzaklaştır">−</button><button type="button" aria-label="Yakınlaştır">+</button><button type="button">Sıfırla</button><small>Tekerlek: yakınlaştır · basılı tutup sürükle: gezin</small>';
  shell.before(controls);
  const buttons = $$("button", controls); buttons[0].onclick = () => zoomTo(zoom - .15); buttons[1].onclick = () => zoomTo(zoom + .15); buttons[2].onclick = () => { zoomTo(1); body.scrollTo(0, 0); };
  body.addEventListener("wheel", e => { e.preventDefault(); const rect = body.getBoundingClientRect(); zoomTo(zoom * Math.exp(-e.deltaY * (e.deltaMode === 1 ? .03 : .002)), e.clientX - rect.left, e.clientY - rect.top); }, { passive: false });
  body.addEventListener("scroll", () => { syncScroll(); paint(); }, { passive: true });
  body.addEventListener("keydown", event => {
    if (event.key === "+" || event.key === "=") { event.preventDefault(); zoomTo(zoom * 1.15); }
    if (event.key === "-") { event.preventDefault(); zoomTo(zoom / 1.15); }
  });
  body.addEventListener("focusin", event => {
    const index = items.indexOf(event.target.closest(".bubble"));
    if (index < 0) return;
    const [x, y] = positions[index];
    body.scrollTo({ left: x * zoom - body.clientWidth / 2 + baseSize / 2, top: y * zoom - body.clientHeight / 2 + baseSize / 2 });
  });
  const observer = new ResizeObserver(() => { endDrag(); if (!body.isConnected) observer.disconnect(); else layout(); }); observer.observe(body);
  requestAnimationFrame(layout);
  return { layout };
}
// Klasör açılışı: kutu yerinden büyüyerek ortaya gelir (iOS klasörü gibi), içeride profil listesi
function openFolder(btn) {
  const g = S.folders?.[+btn.dataset.folder]; if (!g) return;
  const from = $(".folder-box", btn).getBoundingClientRect();
  const layer = document.createElement("div");
  layer.className = "folder-layer";
  layer.innerHTML = `<div class="folder-scrim"></div><section class="folder-open" role="dialog" aria-modal="true" aria-label="${esc(g.name)}">
    <header><div class="fo-brand">${g.key !== "_" ? organizationLogo("universities", g.key, g.name, "folder-logo xl") : ""}<div class="fo-title"><h2>${esc(g.name)}</h2><span>${g.items.length} incelenen profil</span></div></div>
      <div class="input slim">${icon("search")}<input placeholder="Bu klasörde ara" aria-label="Klasörde ara"></div><button class="icon-btn" type="button" data-folder-close aria-label="Kapat">${icon("x")}</button></header>
    <div class="folder-body"><div class="folder-pager"></div></div></section>`;
  document.body.appendChild(layer); hydrateIcons(layer);
  const panel = $(".folder-open", layer), to = panel.getBoundingClientRect();
  const sx = from.width / to.width, sy = from.height / to.height;
  const dx = from.left + from.width / 2 - (to.left + to.width / 2), dy = from.top + from.height / 2 - (to.top + to.height / 2);
  const ease = "cubic-bezier(.22,.9,.24,1)";
  btn.classList.add("opening");
  panel.animate([{ transform: `translate(${dx}px, ${dy}px) scale(${sx}, ${sy})`, borderRadius: "28px", opacity: .6 }, { transform: "none", borderRadius: "26px", opacity: 1 }], { duration: 620, easing: ease });
  $(".folder-body", layer).animate([{ opacity: 0, transform: "scale(.96)" }, { opacity: 1, transform: "none" }], { duration: 420, delay: 260, easing: ease, fill: "backwards" });
  $(".folder-scrim", layer).animate([{ opacity: 0 }, { opacity: 1 }], { duration: 480, easing: "ease-out" });
  const search = $("header input", layer);
  const pager = mountPager($(".folder-pager", layer), { per: 6, pageClass: "pcard-grid", empty: `<p class="faint">Eşleşen akademisyen yok.</p>`,
    render: (c) => `<button type="button" class="pcard" data-chat="${esc(c.id)}" aria-label="${esc(c.name)}">${avatar(c.name, profilePhoto(c), "av pcard-av")}<span class="pcard-name">${esc(c.name)}</span><span class="pcard-sub">${esc(c.title || "")}</span></button>` });
  pager.set(g.items);
  search.oninput = () => { const q = fold(search.value); pager.set(g.items.filter((c) => !q || fold(c.name).includes(q))); };
  setTimeout(() => search.focus({ preventScroll: true }), 650);
  let closing = false;
  const finish = () => { layer.parentNode?.removeChild(layer); btn.classList.remove("opening"); document.removeEventListener("keydown", onKey); };
  const close = () => {
    if (closing) return; closing = true;
    const now = panel.getBoundingClientRect(), target = $(".folder-box", btn).getBoundingClientRect();
    const ex = target.left + target.width / 2 - (now.left + now.width / 2), ey = target.top + target.height / 2 - (now.top + now.height / 2);
    $(".folder-scrim", layer).animate([{ opacity: 1 }, { opacity: 0 }], { duration: 420, fill: "forwards" });
    panel.animate([{ transform: "none", opacity: 1 }, { transform: `translate(${ex}px, ${ey}px) scale(${target.width / now.width}, ${target.height / now.height})`, opacity: .3 }], { duration: 480, easing: ease, fill: "forwards" })
      .finished.then(finish, finish);
  };
  const onKey = (e) => { if (e.key !== "Escape") return; if (layer.peek) layer.peek.close(); else close(); };
  document.addEventListener("keydown", onKey);
  layer.addEventListener("click", (e) => {
    if (e.target.closest(".peek")) { e.stopPropagation(); return; }
    if (e.target.closest("[data-folder-close]") || e.target.classList.contains("folder-scrim")) { if (layer.peek) layer.peek.close(); else close(); return; }
    const row = e.target.closest(".pcard[data-chat], .person-row[data-chat]");
    if (row && !e.target.closest("[data-delchat]")) {
      e.stopPropagation();
      const c = g.items.find((x) => x.id === row.dataset.chat);
      if (c) openPeek(row, chatPerson(c), { layer, panel, finish });
    }
  });
}
document.addEventListener("click", (e) => { const f = e.target.closest(".folder[data-folder]"); if (f) openFolder(f); });

// ------------------------------------------------------------- önizleme kartı (kişi / üniversite)
const chatByName = (name) => S.chats.find((c) => fold(c.name) === fold(name || ""));
const chatPerson = (c) => ({ chat: c.id, name: c.name, title: c.title, institution: c.institution, photo: profilePhoto(c), papers: c.papers, interests: chatInterests(c) });
const peekPubs = (title, list) => list.length ? `<div class="peek-sec"><div class="peek-h">${esc(title)} · ${list.length}</div><div class="peek-pubs">${list.slice(0, 6).map((x) =>
  `<div class="peek-pub"><span class="peek-year">${esc(x.year || "")}</span><div>${safeUrl(x.url) ? `<a href="${esc(safeUrl(x.url))}" target="_blank" rel="noopener"><b>${esc(x.title || "")}</b></a>` : `<b>${esc(x.title || "")}</b>`}<span>${esc(x.venue || x.source || "")}</span></div></div>`).join("")}</div></div>` : "";
function personPeekHtml(P) {
  return `<div class="peek-side"><div class="av peek-side-av"><span class="portrait-initials">${esc(initials(P.name))}</span>${safeImg(P.photo) ? `<img src="${esc(safeImg(P.photo))}" alt="${esc(P.name)}" onerror="this.remove()">` : ""}</div></div>
    <div class="peek-body">
      <div class="peek-top"><div class="peek-mid"><span class="peek-title">${esc(P.title || "")}</span><h3>${esc(P.name)}</h3><span class="peek-dept" data-peek-dept>${esc(P.department || "")}</span></div>
        ${P.institution ? `<div class="peek-uni">${organizationLogo("universities", orgId(P.institution), P.institution, "peek-logo")}<span>${esc(P.institution)}</span></div>` : ""}</div>
      ${P.chat ? `<div class="peek-stats"><div><b>${fmtNum(P.papers)}</b><span>yayın</span></div><div><b data-peek-cites>…</b><span>atıf</span></div><div><b data-peek-src>…</b><span>kaynak</span></div><div><b data-peek-last>…</b><span>son yayın</span></div></div>` : ""}
      <div class="peek-links" data-peek-links>${(P.links || []).join("")}</div>
      ${P.extra || ""}
      <div class="peek-actions">${P.chat ? `<button class="btn primary peek-go" type="button" data-peek-go="#/profil/${esc(P.chat)}">Profile git ${icon("arrow")}</button>`
        : `<button class="btn primary peek-go" type="button" data-peek-new="${esc(P.name)}">${icon("sparkle")}Profil çıkar</button>`}</div>
    </div>`;
}
async function loadPersonPeek(peek, P) {
  if (!P.chat) return;
  try {
    const d = await api(`/api/chats/${encodeURIComponent(P.chat)}`);
    if (!peek.isConnected) return;
    const r = d.result || {}, p = r.profile || {}, y = p.yok || {}, pubs = r.publications || [];
    const years = pubs.map((x) => Number(x.year) || 0).filter(Boolean);
    $("[data-peek-dept]", peek).textContent = p.department || "";
    $("[data-peek-cites]", peek).textContent = fmtNum(pubs.reduce((a, x) => a + (Number(x.citations) || 0), 0));
    $("[data-peek-src]", peek).textContent = Object.keys(r.by_source || {}).length;
    $("[data-peek-last]", peek).textContent = years.length ? Math.max(...years) : "—";
    const email = y.email || p.email, links = p.links || {};
    $("[data-peek-links]", peek).innerHTML = [...(P.links || []), email ? `<a class="chip" href="mailto:${esc(email)}">${icon("mail")}${esc(email)}</a>` : "",
      !P.links?.length && safeUrl(links.yok) ? `<a class="chip" target="_blank" rel="noopener" href="${esc(safeUrl(links.yok))}">${icon("cap")}YÖK Akademik</a>` : "",
      safeUrl(p.source_url) ? `<a class="chip" target="_blank" rel="noopener" href="${esc(safeUrl(p.source_url))}">${icon("building")}Kurum sayfası</a>` : ""].join("");
    hydrateIcons(peek);
  } catch { /* önizleme temel bilgilerle kalır */ }
}
// Kart yerinden büyüyerek açılır; klasör içindeyse klasör sola çekilir.
function openPeek(src, P, ctx = {}) {
  const ease = "cubic-bezier(.22,.9,.24,1)";
  let layer = ctx.layer, own = false;
  const panel = ctx.panel || null;
  if (!layer) {
    own = true; layer = document.createElement("div"); layer.className = "folder-layer peek-layer";
    layer.innerHTML = `<div class="folder-scrim"></div>`; document.body.appendChild(layer);
    $(".folder-scrim", layer).animate([{ opacity: 0 }, { opacity: 1 }], { duration: 380, easing: "ease-out" });
  }
  if (layer.peek) layer.peek.close(true);
  $$(".peeked").forEach((r) => r.classList.remove("peeked"));
  src?.classList.add("peeked");
  const peek = document.createElement("section");
  peek.className = `peek peek-${P.kind || "person"}`; peek.setAttribute("role", "dialog"); peek.setAttribute("aria-label", P.name || "Önizleme");
  peek.innerHTML = `<button class="icon-btn peek-x" type="button" data-peek-close aria-label="Kapat">${icon("x")}</button>${P.html || personPeekHtml(P)}`;
  layer.appendChild(peek); hydrateIcons(peek);

  const gap = 20, pw = Math.min(P.kind === "university" ? 600 : 760, innerWidth - 24);
  peek.style.width = `${pw}px`;
  let folderTo = "none", to;
  if (panel) {
    const fr = panel.getBoundingClientRect(), wide = innerWidth >= fr.width * .9 + pw + gap + 48;
    const scale = wide ? Math.min(1, (innerWidth - pw - gap - 48) / fr.width) : .94, fw = fr.width * scale, total = fw + gap + pw;
    folderTo = wide ? `translateX(${(innerWidth - total) / 2 - (fr.left + (fr.width - fw) / 2)}px) scale(${scale})` : "scale(.94)";
    to = wide ? { left: (innerWidth - total) / 2 + fw + gap } : { left: (innerWidth - pw) / 2 };
    panel.animate([{ transform: "none" }, { transform: folderTo, filter: wide ? "none" : "brightness(.8)" }], { duration: 640, easing: ease, fill: "forwards" });
  } else to = { left: (innerWidth - pw) / 2 };
  const h = Math.min(peek.scrollHeight, innerHeight - 32);
  Object.assign(peek.style, { left: `${to.left}px`, top: `${Math.max(16, (innerHeight - h) / 2)}px`, maxHeight: `${innerHeight - 32}px` });
  if (!calmMotion()) {
    if (P.enter) P.enter(peek);
    else peek.animate([{ opacity: 0, transform: "translateY(10px)" }, { opacity: 1, transform: "none" }], { duration: 180, easing: ease });
  }
  const onKey = (e) => { if (e.key === "Escape" && own) api_.close(); };
  document.addEventListener("keydown", onKey);
  const api_ = {
    close(instant) {
      if (layer.peek !== api_) return; layer.peek = null; src?.classList.remove("peeked"); document.removeEventListener("keydown", onKey);
      if (panel) panel.animate([{ transform: folderTo }, { transform: "none", filter: "none" }], { duration: instant ? 1 : 520, easing: ease, fill: "forwards" });
      const done = () => { peek.remove(); if (own) layer.remove(); };
      if (instant || calmMotion()) { done(); return; }
      if (own) $(".folder-scrim", layer).animate([{ opacity: 1 }, { opacity: 0 }], { duration: 420, fill: "forwards" });
      (P.leave ? P.leave(peek) : peek.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 160, fill: "forwards" })).finished.then(done, done);
    },
    go(hash) {
      // Kapanış sade: kart ve katman solar, sayfa küp geçişiyle gelir
      const leave = [peek, ...(own ? [layer] : [layer])];
      Promise.all(leave.map((n) => n.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 200, easing: "ease-out", fill: "forwards" }).finished.catch(() => {})))
        .then(() => { document.removeEventListener("keydown", onKey); if (ctx.finish) ctx.finish(); layer.remove(); location.hash = hash; });
    },
  };
  layer.peek = api_;
  peek.addEventListener("click", (e) => {
    if (e.target.closest("[data-peek-close]")) { e.stopPropagation(); api_.close(); return; }
    const go = e.target.closest("[data-peek-go]");
    if (go) { e.stopPropagation(); api_.go(go.dataset.peekGo); return; }
    const nw = e.target.closest("[data-peek-new]");
    if (nw) { e.stopPropagation(); api_.go(`#/akademisyenler?q=${encodeURIComponent(nw.dataset.peekNew)}`); return; }
  });
  if (own) layer.addEventListener("click", (e) => { if (e.target.classList.contains("folder-scrim")) api_.close(); });
  (P.load || loadPersonPeek)(peek, P);
}
// Üniversite önizlemesi: künye kartı (sayaçlar) + Genel bakış / Kadro ve öğrenci / Araştırma sekmeleri
function uniTrend(trend) {
  if (!trend?.length) return "";
  const max = Math.max(...trend.map((t) => t.works), 1);
  return `<div class="uf-trend" role="img" aria-label="Son ${trend.length} yılın yayın sayıları">${trend.map((t, i) => `<div class="uf-bar grow" style="--h:${Math.max(4, Math.round(t.works / max * 100))}%;--i:${i}" title="${t.year}: ${fmtNum(t.works)} yayın"><span>${fmtNum(t.works)}</span><i></i><em>${String(t.year).slice(2)}</em></div>`).join("")}</div>`;
}
function uniStack(parts, total, note) {
  const sum = total || parts.reduce((a, p) => a + p.value, 0) || 1;
  return `<div class="uf-stack">${parts.map((p, i) => `<i class="grow" style="--w:${(p.value / sum * 100).toFixed(2)}%;--c:var(--uf-${i});--i:${i}" title="${esc(p.label)}: ${fmtNum(p.value)}"></i>`).join("")}</div>
    <ul class="uf-legend">${parts.map((p, i) => `<li><i style="--c:var(--uf-${i})"></i><span>${esc(p.label)}</span><b>${count(p.value)}</b>${p.year ? `<small>${esc(p.year)}</small>` : ""}</li>`).join("")}</ul>
    ${note ? `<p class="uf-src">${esc(note)}</p>` : ""}`;
}
function uniStaffBlock(ac) {
  if (!ac?.total) return `<div class="peek-h">Akademik kadro</div><div class="loading-line"><span class="spinner"></span>Unvan dağılımı YÖK Akademik'ten okunuyor…</div>`;
  return `<div class="peek-h">Akademik kadro · ${count(ac.total)} kişi</div>${uniStack((ac.titles || []).map((t) => ({ label: t.title, value: t.count })), ac.total, "Kaynak: YÖK Akademik")}`;
}
function uniFactsHtml(d, people) {
  const id = d.identity || {}, sc = d.scale || {}, ac = d.academics || {}, rs = d.research || {}, un = d.units || {};
  const line = [id.founded && `Kuruluş ${id.founded}`, id.type, id.city].filter(Boolean);
  const stat = (v, label, extra = "") => `<div><b>${v == null || v === "" ? "—" : typeof v === "number" ? count(v) : esc(v)}</b><span>${esc(label)}${extra}</span></div>`;
  const studentYear = sc.students?.year ? ` · ${esc(sc.students.year)}` : "";
  const deps = un.scanned ? `${fmtNum(un.departments)}${un.scanned < un.faculties ? "+" : ""}` : "";
  const row = (ic, label, value) => value ? `<div class="uf-row"><span class="uf-ic">${icon(ic)}</span><div><small>${esc(label)}</small><p>${value}</p></div></div>` : "";
  const link = (url, text) => safeUrl(url) ? `<a href="${esc(safeUrl(url))}" target="_blank" rel="noopener">${esc(text)} ${icon("external")}</a>` : "";
  const studentParts = [["associate", "Önlisans"], ["undergrad", "Lisans"], ["graduate", "Yüksek lisans"], ["doctoral", "Doktora"]]
    .filter(([k]) => sc[k]).map(([k, label]) => ({ label, value: sc[k].value, year: sc[k].year }));
  const titleParts = (ac.titles || []).map((t) => ({ label: t.title, value: t.count }));
  const site = (id.website || "").replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "");
  const overview = `${row("user", "Rektör", esc(id.rector || ""))}
    ${row("map", "Şehir", esc(id.city || ""))}
    ${row("building", "Adres", esc(id.address || ""))}
    ${row("layers", "Yerleşke", esc(id.campus || ""))}
    ${row("globe", "Eğitim dili", esc(id.language || ""))}
    ${row("bookmark", "Bağlı olduğu vakıf", esc(id.affiliation || ""))}
    ${row("external", "Bağlantılar", [link(id.website, site), link(id.wikipedia, "Vikipedi")].filter(Boolean).join(" · "))}
    ${d.firms?.length ? `<div class="uf-block"><div class="peek-h">Ortak yayın yapan firmalar</div><div class="uf-chips">${d.firms.map((f) => `<a class="chip" href="#/firma/${esc(f.id)}">${esc(f.name)} <b>${f.people}</b></a>`).join("")}</div></div>` : ""}
    ${people.length ? `<div class="uf-block"><div class="peek-h">İncelediğiniz akademisyenler</div><div class="peek-faces">${people.slice(0, 12).map((c) => `<a href="#/profil/${esc(c.id)}" title="${esc(c.name)}">${avatar(c.name, profilePhoto(c))}</a>`).join("")}${people.length > 12 ? `<span class="fi-more">+${people.length - 12}</span>` : ""}</div></div>` : ""}
    ${!id.rector && !id.city && !id.address ? `<p class="uf-empty">Bu kurumun künye bilgisi Vikipedi/Wikidata'da bulunamadı.</p>` : ""}
    ${d.sources?.identity ? `<p class="uf-src">Kaynak: ${esc(d.sources.identity)}</p>` : ""}`;
  const scale = `<div class="uf-block" data-uf-staff>${uniStaffBlock(ac)}</div>
    <div class="uf-block"><div class="peek-h">Öğrenci dağılımı${sc.students ? ` · ${count(sc.students.value)} öğrenci` : ""}</div>${studentParts.length ? uniStack(studentParts, 0, "Kaynak: Vikipedi bilgi kutusu (yıl yanında)") : `<p class="uf-empty">Önlisans / lisans / lisansüstü kırılımı kamuya açık kaynaklarda bulunamadı.</p>`}</div>
    ${sc.graduates ? `<div class="uf-block"><div class="peek-h">Mezun</div><p class="uf-big">${count(sc.graduates.value)} <small>${esc(sc.graduates.year || "")}</small></p></div>` : ""}`;
  const research = rs.works ? `<div class="uf-mini">${stat(rs.works, "yayın")}${stat(rs.citations, "atıf")}${stat(rs.h_index, "h-index")}${stat(rs.i10_index, "i10-index")}</div>
    <div class="uf-block"><div class="peek-h">Son ${rs.trend?.length || 0} yılda yayın</div>${uniTrend(rs.trend)}</div>
    ${rs.topics?.length ? `<div class="uf-block"><div class="peek-h">En çok çalışılan konular</div><div class="uf-chips">${rs.topics.map((t) => `<span class="chip">${esc(t)}</span>`).join("")}</div></div>` : ""}
    ${rs.partners?.length ? `<div class="uf-block"><div class="peek-h">En çok birlikte yayın yapılan kurumlar</div><ol class="uf-partners">${rs.partners.map((x) => `<li><span>${esc(x.name)}</span><b>${count(x.count)}</b></li>`).join("")}</ol></div>` : ""}
    <p class="uf-src">Kaynak: OpenAlex · ${esc(rs.name || "")}</p>` : `<p class="uf-empty">OpenAlex'te kurum kaydı bulunamadı.</p>`;
  return `${line.length || id.motto ? `<div class="uf-id">${line.length ? `<p class="uf-line">${line.map(esc).join(" · ")}</p>` : ""}${id.motto ? `<p class="uf-motto">“${esc(id.motto)}”</p>` : ""}</div>` : ""}
    <div class="uf-stats">${stat(sc.students?.value, "öğrenci", studentYear)}${d.academics ? stat(ac.total, "akademisyen") : `<div data-uf-staff-stat><b class="sk-num"></b><span>akademisyen</span></div>`}${stat(un.faculties, "fakülte")}${stat(deps, "bölüm")}${stat(rs.works, "yayın")}${stat(rs.h_index, "h-index")}</div>
    <div class="uf-tabs" role="tablist"><button class="on" type="button" data-uf-tab="0" role="tab">Genel bakış</button><button type="button" data-uf-tab="1" role="tab">Kadro ve öğrenci</button><button type="button" data-uf-tab="2" role="tab">Araştırma</button><i class="uf-ink"></i></div>
    <div class="uf-panes"><div class="uf-pane on">${overview}</div><div class="uf-pane">${scale}</div><div class="uf-pane">${research}</div></div>`;
}
function openUniPeek(card, id, name, people) {
  const html = `<div class="peek-cover uni">${organizationLogo("universities", id, name, "peek-logo xl")}</div>
    <div class="peek-head center"><div class="peek-id"><h3>${esc(name)}</h3></div></div>
    <div class="uf-host"><div class="uf-stats">${["öğrenci", "akademisyen", "fakülte", "bölüm", "yayın", "h-index"].map((l) => `<div><b class="sk-num"></b><span>${l}</span></div>`).join("")}</div>
      <div class="loading-line"><span class="spinner"></span>Künye Vikipedi, YÖK Akademik ve OpenAlex'ten derleniyor…</div></div>
    <div class="peek-actions"><button class="btn primary peek-go" type="button" data-peek-go="#/universite/${esc(id)}">Üniversite sayfası ${icon("arrow")}</button></div>`;
  openPeek(card, { kind: "university", name, html, load: async (peek) => {
    const host = $(".uf-host", peek);
    try {
      const d = await api(`/api/universities/${encodeURIComponent(id)}/facts`, { quiet: true });
      if (!peek.isConnected) return;
      host.innerHTML = uniFactsHtml(d, people); hydrateIcons(host);
      if (!calmMotion()) host.animate([{ opacity: .3 }, { opacity: 1 }], { duration: 320, easing: "ease-out" });
      animateCounts($(".uf-stats", host)); animateCounts($(".uf-pane.on", host));
      const tabs = $$("[data-uf-tab]", host), panes = $$(".uf-pane", host), ink = $(".uf-ink", host);
      const place = (b) => { ink.style.width = `${b.offsetWidth}px`; ink.style.transform = `translateX(${b.offsetLeft}px)`; };
      requestAnimationFrame(() => place(tabs[0]));
      tabs.forEach((b) => b.onclick = () => {
        const i = +b.dataset.ufTab, prev = panes.findIndex((p) => p.classList.contains("on"));
        if (i === prev) return;
        tabs.forEach((t) => t.classList.toggle("on", t === b)); place(b);
        panes[prev].classList.remove("on"); panes[i].classList.add("on");
        if (!calmMotion()) panes[i].animate([{ opacity: 0, transform: `translateX(${i > prev ? 24 : -24}px)` }, { opacity: 1, transform: "none" }], { duration: 320, easing: EASE });
        animateCounts(panes[i]);
        panes[i].querySelectorAll(".grow").forEach((el) => { el.classList.remove("grow"); void el.offsetWidth; el.classList.add("grow"); });
      });
      if (!d.academics) {
        try {
          const ac = await api(`/api/universities/${encodeURIComponent(id)}/staff-counts`, { quiet: true });
          if (!peek.isConnected) return;
          const st = $("[data-uf-staff-stat]", host);
          if (st) { st.outerHTML = `<div><b>${count(ac.total)}</b><span>akademisyen</span></div>`; animateCounts($(".uf-stats", host)); }
          const block = $("[data-uf-staff]", host); block.innerHTML = uniStaffBlock(ac);
          if (block.closest(".uf-pane.on")) animateCounts(block);
        } catch (e) {
          const block = $("[data-uf-staff]", host), st = $("[data-uf-staff-stat] b", host);
          if (block) block.innerHTML = `<div class="peek-h">Akademik kadro</div><p class="uf-empty">${esc(e.message)}</p>`;
          if (st) { st.classList.remove("sk-num"); st.textContent = "—"; }
        }
      }
    } catch (e) { if (peek.isConnected) host.innerHTML = `<p class="uf-empty">Künye alınamadı: ${esc(e.message)}</p>`; }
  } });
}
document.addEventListener("click", (e) => {
  if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey) return;
  const uni = e.target.closest(".uni-card[data-uni-peek]");
  if (uni) { e.preventDefault(); openUniPeek(uni, uni.dataset.uniPeek, $(".uc-main b", uni)?.textContent || "", S.chats.filter((c) => orgId(c.institution || "") === uni.dataset.uniPeek)); return; }
  const fp = e.target.closest("[data-peek-person]");
  if (fp && !e.target.closest("a, summary, details") && (!e.target.closest("button") || e.target.closest("button") === fp)) {
    const p = S.firmPeople?.[+fp.dataset.peekPerson]; if (!p) return;
    const c = p.chat_id ? S.chats.find((x) => x.id === p.chat_id) : null;
    openFirmPerson(p, c);
    return;
  }
  const co = e.target.closest("[data-collab]");
  if (co && !e.target.closest("a, button")) {
    const x = S.collabs?.[+co.dataset.collab]; if (!x) return;
    const c = chatByName(x.name), last = fold(x.name).split(" ").pop();
    const shared = (S.collabPubs || []).filter((pub) => (pub.authors || []).some((a) => fold(a).includes(last) && fold(a)[0] === fold(x.name)[0]));
    openPeek(co, { ...(c ? chatPerson(c) : {}), name: x.name, title: x.title, institution: x.institution, department: x.unit, photo: x.photo || (c ? profilePhoto(c) : ""),
      links: safeUrl(x.url) ? [`<a class="chip" href="${esc(safeUrl(x.url))}" target="_blank" rel="noopener">${icon("cap")}YÖK</a>`] : [],
      extra: peekPubs("Ortak yayınlar", shared) });
  }
});

// =================================================================== AKADEMİSYENLER
const existingChat = (p) => S.chats.find((c) => fold(c.name) === fold(p.name)
  && (!c.institution || fold(c.institution).includes(fold(p.university)) || fold(p.university).includes(fold(c.institution))));
const startFromYok = (p) => startJob(p.university, p.name, () => post("/api/jobs", { name: p.name, yok_url: p.url, university: p.university, department: p.department || p.faculty || "", email: p.email || "" }));

async function viewPeople(q = "") {
  setCrumbs([{ label: "Ana sayfa", href: "#/" }, { label: "Akademisyenler" }]);
  const seq = S.routeSeq;
  if (!S.chats.length) { await loadChats(); if (seq !== S.routeSeq) return; }
  else if (!viewPeople.bg) { viewPeople.bg = true; loadChats().then(() => { viewPeople.bg = false; }); }
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
        <div class="input slim">${icon("search")}<input data-filter="pList" placeholder="Listede ara"></div>
        <div class="seg" role="tablist" aria-label="Görünüm"><button type="button" data-pview="folders" class="${peopleView() === "folders" ? "on" : ""}">Klasör</button><button type="button" data-pview="list" class="${peopleView() === "list" ? "on" : ""}">Liste</button></div>
        <button class="link" type="button" data-clearall>Tümünü sil</button>` : ""}</div>
    <div class="${peopleView() === "folders" ? "folder-host" : "card list-card"}" id="pList">${S.chats.length ? (peopleView() === "folders" ? folderGrid(S.chats) : `<div class="stagger profile-card-list">${S.chats.map(profileRow).join("")}</div>`)
      : emptyState("users", "Henüz profil yok", "Yukarıdan bir akademisyen arayın.")}</div>`);
  $$("[data-pview]").forEach((b) => b.onclick = () => { try { localStorage.setItem("peopleView", b.dataset.pview); } catch { /* yok */ } viewPeople($("#pQ")?.value.trim() || ""); });
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
    $$("#pList .person-row, #pList .folder").forEach((row) => {
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

async function startJob(sub, name, create, verb = "hazırlanıyor", selection = null, expectWos = selection === null) {
  let job;
  try { job = await (create ? create() : post("/api/jobs", { url: sub, name })); } catch (e) { toast(esc(e.message)); return; }
  if (expectWos) document.dispatchEvent(new Event("wos-work-requested"));
  const phases = selection ? PHASES.filter(([key]) => ["collect", "merge"].includes(key) || key === "scrape" && selection.includes("institution")) : PHASES;
  const node = document.createElement("div");
  node.className = "card job enter";
  node.innerHTML = `<div class="m-kicker"><span class="spinner"></span>Profil ${verb}</div>
    <h2 style="margin-top:10px">${esc(name)}</h2><div class="job-sub">${esc(sub)}</div>
    <div class="progress"><div></div></div>
    <div class="steps">${phases.map(([k, l]) => `<div class="step" data-phase="${k}" ${k === "bot" ? "hidden" : ""}><span class="dot"></span>${esc(l)}</div>`).join("")}</div>
    <div class="now"></div>
    <section class="live-profile" hidden><div class="live-head"></div>
      <div class="live-list-head"><b>Yayınlar</b><span class="live-count"></span></div>
      <div class="live-list"></div><div class="live-loading loading-line"><span class="spinner"></span><span></span></div></section>
    <details class="tech"><summary>Teknik ayrıntılar</summary><div class="log"></div></details>`;
  S.jobs[job.id] = { node, name, done: false };
  // Canlı liste: kaynaklar bittikçe yayınlar eklenir; aynı yayın (DOI ya da başlık) tek satır, kaynakları birleşir
  const live = new Map();
  const liveKey = (r) => r.doi ? `doi:${normDoi(r.doi)}` : `t:${fold(r.title).replace(/[^a-z0-9]/g, "").slice(0, 120)}`;
  function renderLive(ev) {
    const box = $(".live-profile", node); box.hidden = false;
    if (ev.profile) {
      const p = ev.profile;
      $(".live-head", box).innerHTML = `${avatar(p.name || name, p.photo)}<div><b>${esc(p.name || name)}</b><span>${esc([p.title, p.institution, p.department].filter(Boolean).join(" · "))}</span></div>`;
    }
    for (const r of ev.records || []) {
      const k = liveKey(r), old = live.get(k);
      if (old) { if (r.source && !old.sources.includes(r.source)) old.sources.push(r.source); old.year ||= r.year; old.venue ||= r.venue; }
      else live.set(k, { ...r, sources: r.source ? [r.source] : [] });
    }
    const rows = [...live.values()].sort((a, b) => (Number(b.year) || 0) - (Number(a.year) || 0));
    $(".live-count", box).textContent = rows.length ? `${fmtNum(rows.length)} yayın şimdiye kadar` : "";
    $(".live-list", box).innerHTML = rows.slice(0, 150).map((r, i) => `<div class="live-row" style="--i:${Math.min(i, 12)}"><span class="live-year">${esc(r.year || "—")}</span><div><b>${esc(r.title)}</b>${r.venue ? `<span>${esc(r.venue)}</span>` : ""}</div><span class="live-src">${esc(r.sources.map((x) => SRC_TR[x] || x).join(" + "))}</span></div>`).join("")
      + (rows.length > 150 ? `<div class="faint">+${fmtNum(rows.length - 150)} yayın daha; profil açılınca tamamı görünür.</div>` : "");
    const pending = ev.pending || [];
    $(".live-loading span:last-child", box).textContent = pending.length
      ? `Yükleniyor · bekleniyor: ${pending.join(", ")}`
      : "Kaynaklar tamam · yayınlar birleştiriliyor ve doğrulanıyor…";
    hydrateIcons(box);
  }
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
        $(".now", node).textContent = selection ? ev.message : PHASE_NOW[phase] || "";
        $(".progress div", node).style.width = `${Math.max(8, ((order.indexOf(phase) + 1) / order.length) * 92)}%`;
      }
      const line = document.createElement("div");
      line.className = ev.status === "warning" ? "warning" : "";
      line.innerHTML = `<span class="t">${ev.t.toFixed(1).padStart(5)}s</span> <span class="s">${esc(ev.step)}</span> ${esc(ev.message)}`;
      const log = $(".log", node); log.appendChild(line); log.scrollTop = log.scrollHeight;
    } else if (ev.type === "partial") {
      renderLive(ev);
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
    if (expectWos) document.dispatchEvent(new Event("wos-work-requested"));
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
    <div class="toolbar"><div class="input">${icon("search")}<input id="uQ" placeholder="Üniversite ara" autocomplete="off"></div></div>
    <div id="uGrid" class="uni-grid">${skeleton(6)}</div>`);
  let u;
  try { u = await api("/api/universities"); } catch (e) { $("#uGrid").innerHTML = `<div class="card">${emptyState("building", "Liste alınamadı", esc(e.message))}</div>`; hydrateIcons($("#uGrid")); return; }
  const grid = $("#uGrid");
  if (!grid) return;
  $("#uSub").textContent = `YÖK Akademik'teki ${u.items.length} üniversite. Birini seçin: fakülte, bölüm, kadro.`;
  grid.className = "";
  const cols = Math.max(2, Math.floor((grid.clientWidth + 14) / 204));
  const pager = mountPager(grid, { per: cols * 3, pageClass: "uni-grid", empty: `<p class="faint">Üniversite bulunamadı.</p>`,
    render: (x) => `<a class="card uni-card" data-uni-peek="${esc(x.id)}" href="#/universite/${esc(x.id)}">
    ${organizationLogo("universities", x.id, x.name, "uni-mark")}<span class="uc-main"><b>${esc(x.name)}</b>${x.people.length ? `<span>${x.people.length} profil incelendi</span>` : ""}</span></a>` });
  pager.set(u.items);
  $("#uQ").oninput = (e) => { const q = fold(e.target.value); pager.set(u.items.filter((x) => !q || fold(x.name).includes(q))); };
}

async function viewUni(uid) {
  setCrumbs([{ label: "Ana sayfa", href: "#/" }, { label: "Üniversiteler", href: "#/universiteler" }, { label: "…" }]);
  if (S.uni?.id !== uid) S.uni = { id: uid, data: null, fac: null, facData: null, dep: null };
  const d = S.uni, col = (id, ic, title, ph, body) => `<section class="card col" id="${id}">
      <div class="col-head"><span class="ch-icon">${icon(ic)}</span><h3>${title}</h3><span class="count" id="${id}N"></span></div>
      <div class="col-filter"><div class="input">${icon("search")}<input data-filter="${id}" placeholder="${ph}"></div></div>
      <div class="col-body">${body}</div></section>`;
  setView(`<section class="card identity-hero identity-org" data-org-brand>
      <div class="identity-cover" aria-hidden="true"></div>
      <div class="identity-main">
        <div class="identity-avatar" id="uLogo">${organizationLogo("universities", uid, d.data?.name || "Üniversite", "hero-logo")}</div>
        <div class="identity-info"><h1 id="uName">${esc(d.data?.name || "Üniversite")}</h1><div class="meta" id="uMeta"></div></div>
        <div class="kebab"><button class="icon-btn kebab-btn" type="button" aria-label="Seçenekler">${icon("dots")}</button><div class="kebab-menu" id="uAct" hidden></div></div>
      </div></section>
    <div class="audience-tabs" role="tablist" aria-label="Üniversite görünümü"><button data-audience="overview" type="button" role="tab" aria-controls="universityOverview">Genel bakış</button><button class="active" data-audience="academic" type="button" role="tab" aria-selected="true" aria-controls="academicUniversity">${icon("users")}Akademisyen bakışı</button><button data-audience="student" type="button" role="tab" aria-selected="false" aria-controls="studentView">${icon("cap")}Öğrenci bakışı</button></div>
    <div id="academicUniversity" role="tabpanel"><div class="miller">${col("colFac", "layers", "Fakülteler", "Fakültelerde ara", skeleton(7))}
      ${col("colDep", "grid", "Bölümler", "Bölümlerde ara", `<div class="col-empty">Soldan bir fakülte seçin.</div>`)}
      ${col("colStaff", "users", "Akademisyenler", "Akademisyenlerde ara", `<div class="col-empty">Bir bölüm seçin.</div>`)}</div></div><div id="studentView" role="tabpanel" hidden></div><div id="universityOverview" role="tabpanel" hidden></div>`);
  if (d.data?.name) { $("#uName").dataset.typed = d.data.name; typeText($("#uName"), d.data.name); }
  const facultyColumn = $("#colFac");
  if (!d.data) {
    try { d.data = await api(`/api/universities/${encodeURIComponent(uid)}`); }
    catch (e) { if (facultyColumn.isConnected) $(".col-body", facultyColumn).innerHTML = `<div class="col-empty">${esc(e.message)}</div>`; return; }
    if (S.uni !== d || !facultyColumn.isConnected) return;
  }
  renderUni();
  $$("[data-audience]").forEach((button) => { button.onclick = () => setUniversityAudience(button.dataset.audience); });
  setUniversityAudience(d.audience || "overview");
  if (d.facData) { renderYokDeps(); if (d.dep != null) renderYokStaff(); if (d.fac != null) loadYokRoles(d, d.data.items[d.fac].raw); }
}

const STUDENT_SECTIONS = [
  ["graduate", "Yüksek lisans ve doktora", "Tezli / tezsiz programlar ve başvuru koşulları", "cap"],
  ["fees", "Ücretler ve burslar", "Yayımlanan tutarlar, burslar ve dönem bilgisi", "bookmark"],
  ["erasmus", "Erasmus ve değişim", "Anlaşmalı kurumlar, ülkeler ve başvurular", "globe"],
  ["work_travel", "Work and Travel", "Üniversitenin yayımladığı duyurular", "briefcase"],
  ["campus", "Kampüs ve ulaşım", "Yerleşkeler, konum ve iletişim", "building"],
];
function studentAccordion(section, title, subtitle, ic, faculty = "", department = "") {
  return `<details class="student-accordion" data-student-section="${section}" data-faculty="${esc(faculty)}" data-department="${esc(department)}"><summary><span class="student-summary-icon">${icon(ic)}</span><span><b>${esc(title)}</b><small>${esc(subtitle)}</small></span>${icon("chevron")}</summary><div class="student-content"></div></details>`;
}
function studentState(d) {
  d.studentResults ||= new Map(); d.studentPending ||= new Map();
  d.studentFaculties ||= new Map(); d.studentFacultyPending ||= new Map();
  return d;
}
const studentChats = new Map();
function studentChatState(d) {
  if (!studentChats.has(d.id)) studentChats.set(d.id, { messages: [], request: null, error: "" });
  return studentChats.get(d.id);
}
function studentAssistantHtml(d) {
  return `<aside class="student-assistant" aria-labelledby="studentAssistantTitle" data-student-chat="${esc(d.id)}">
    <header class="student-assistant-head"><span class="student-assistant-symbol">${icon("sparkle")}</span><div><h3 id="studentAssistantTitle">Öğrenci asistanı</h3><p>${esc(d.data.name)}</p></div><button class="icon-btn" type="button" data-student-chat-clear aria-label="Sohbeti temizle" title="Sohbeti temizle">${icon("trash")}</button></header>
    <p class="student-assistant-intro">Programlar, dersler ve öğrenci yaşamı hakkında sor. Yanıtın kaynaklarını birlikte incele.</p>
    <div class="student-chat-suggestions">${["Yüksek lisans programları neler?", "Erasmus hakkında bilgi verir misin?", "Ücret ve burs bilgileri neler?"].map((q) => `<button type="button" data-student-question="${esc(q)}">${esc(q)}</button>`).join("")}</div>
    <div class="student-chat-scope" data-student-chat-scope hidden></div>
    <div class="student-chat-thread" role="log" aria-live="polite" aria-relevant="additions" aria-label="Öğrenci asistanı sohbeti"></div>
    <div class="student-assistant-status" role="status" aria-live="polite"></div>
    <form class="student-chat-form"><label class="sr-only" for="studentQuestion">Öğrenci asistanına sor</label><textarea id="studentQuestion" rows="3" maxlength="1000" placeholder="Örneğin: İlk yıl hangi dersler var?" required></textarea><div class="student-chat-toolbar"><span>Enter gönderir · Shift+Enter yeni satır</span><button class="btn primary" type="submit" data-student-chat-submit>${icon("send")}Gönder</button></div></form>
  </aside>`;
}
function drawStudentChat(d) {
  const host = $("[data-student-chat]");
  if (S.uni !== d || !host || host.dataset.studentChat !== d.id) return;
  const chat = studentChatState(d), pending = Boolean(chat.request), thread = $(".student-chat-thread", host);
  const previous = thread._messages || [];
  const keepMessages = previous.length <= chat.messages.length && previous.every((message, i) => message === chat.messages[i]);
  const firstNew = keepMessages ? previous.length : 0;
  const changed = !keepMessages || firstNew < chat.messages.length;
  const nearEnd = thread.scrollHeight - thread.scrollTop - thread.clientHeight < 48;
  if (!keepMessages) thread.replaceChildren();
  if (firstNew < chat.messages.length) thread.insertAdjacentHTML("beforeend", chat.messages.slice(firstNew).map((message) => {
    const sources = (message.sources || []).filter((source) => /^S\d+$/.test(source.id) && safeUrl(source.url));
    let content = esc(message.content).replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>").replace(/\n/g, "<br>");
    if (message.role === "assistant") content = content.replace(/\[(S\d+)\]/g, (label, id) => {
      const source = sources.find((item) => item.id === id);
      return source ? `<a href="${esc(safeUrl(source.url))}" target="_blank" rel="noopener" title="${esc(source.title)}">${label}</a>` : label;
    });
    return `<article class="student-chat-message ${message.role === "user" ? "user" : "assistant"}"><div class="student-chat-bubble"><p>${content}</p>${sources.length ? `<div class="student-chat-sources">${sources.map((source) => `<a href="${esc(safeUrl(source.url))}" target="_blank" rel="noopener">${icon("external")}<span>[${source.id}] ${esc(source.title || "Resmî kaynak")}</span></a>`).join("")}</div>` : ""}</div></article>`;
  }).join(""));
  thread._messages = chat.messages.slice();
  thread.hidden = !chat.messages.length;
  host.setAttribute("aria-busy", String(pending));
  thread.setAttribute("aria-busy", String(pending));
  $(".student-chat-suggestions", host).hidden = chat.messages.length > 0;
  $$("[data-student-question]", host).forEach((button) => { button.disabled = pending; });
  $("[data-student-chat-submit]", host).disabled = pending;
  $(".student-chat-form", host).setAttribute("aria-busy", String(pending));
  $(".student-assistant-status", host).innerHTML = pending ? '<span class="spinner" aria-hidden="true"></span>Kaynaklar inceleniyor, yanıt hazırlanıyor…' : chat.error ? `<span class="student-chat-notice">${esc(chat.error)}</span>` : "";
  const scope = $("[data-student-chat-scope]", host), department = d.studentChatScope?.department;
  scope.hidden = !department;
  scope.innerHTML = department ? `<span>${esc(department)}</span><button class="icon-btn" type="button" data-student-chat-general aria-label="Üniversite geneline dön" title="Üniversite geneline dön">${icon("x")}</button>` : "";
  if (department) $("[data-student-chat-general]", scope).onclick = () => { d.studentChatScope = null; drawStudentChat(d); };
  if (changed && (nearEnd || chat.messages.at(-1)?.role === "user")) thread.scrollTop = thread.scrollHeight;
}
function bindStudentChat(d) {
  const host = $("[data-student-chat]"), form = $(".student-chat-form", host), input = $("textarea", form);
  const askStudent = async (question) => {
    const chat = studentChatState(d);
    question = String(question || "").trim().slice(0, 1000);
    if (!question || chat.request || S.uni !== d) return;
    const history = chat.messages.slice(-10).map((message) => ({ role: message.role, content: message.content.slice(0, 2000) }));
    const controller = new AbortController(), scope = d.studentChatScope || {};
    chat.request = controller; chat.error = "";
    chat.messages.push({ role: "user", content: question });
    input.value = ""; drawStudentChat(d);
    const timeout = setTimeout(() => controller.abort(), 150000);
    try {
      const data = await api(`/api/universities/${encodeURIComponent(d.id)}/student/chat`, {
        method: "POST", quiet: true, signal: controller.signal,
        body: JSON.stringify({ question, messages: history, faculty: scope.faculty || "", department: scope.department || "" }),
      });
      if (chat.request !== controller) return;
      if (typeof data.answer !== "string" || !data.answer.trim()) throw new Error("Asistandan yanıt alınamadı.");
      chat.messages.push({ role: "assistant", content: data.answer, sources: Array.isArray(data.sources) ? data.sources : [] });
      chat.messages = chat.messages.slice(-40);
    } catch (error) {
      if (chat.request !== controller) return;
      chat.error = error.name === "AbortError" ? "Yanıt bekleme süresi doldu. Sorunu yeniden gönderebilirsin." : error.status === 404 ? "Öğrenci asistanına bağlanılamadı. Uygulamanın güncel sürümünü açıp yeniden dene." : error.message;
      if (input.isConnected && !input.value.trim()) input.value = question;
    } finally {
      clearTimeout(timeout);
      if (chat.request === controller) {
        chat.request = null;
        if (S.uni?.id === d.id) drawStudentChat(S.uni);
      }
    }
  };
  form.onsubmit = (event) => { event.preventDefault(); void askStudent(input.value); };
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); form.requestSubmit(); }
  });
  $$("[data-student-question]", host).forEach((button) => { button.onclick = () => { void askStudent(button.dataset.studentQuestion); }; });
  $("[data-student-chat-clear]", host).onclick = () => {
    const chat = studentChatState(d);
    chat.request?.abort(); chat.request = null; chat.messages = []; chat.error = "";
    drawStudentChat(d); input.focus();
  };
  drawStudentChat(d);
}
// Öğrenci bakışı: üstte kurum künyesi, kategori karoları, seçilen kategorinin içerik paneli, sağda asistan
const STUDENT_TILES = [["undergrad", "Lisans programları", "Fakülteler, bölümler, dersler ve kadro", "layers"], ...STUDENT_SECTIONS];
function renderStudentView() {
  const box = $("#studentView"), d = S.uni;
  if (!box || !d || box.dataset.ready) return;
  studentState(d); box.dataset.ready = "1";
  box.innerHTML = `<div class="sv-hero"><div><span class="eyebrow">ÖĞRENCİ REHBERİ</span><h2>Ne öğrenmek istersin?</h2><p>Bir başlık seç; bilgiler üniversitenin resmî sayfalarından, kaynağıyla gelir.</p></div>
      <div class="sv-facts" data-sv-facts>${Array.from({ length: 4 }, () => `<div class="sv-fact"><b class="sk-num"></b><span class="sk-line"></span></div>`).join("")}</div></div>
    <div class="student-layout"><div class="student-guide">
      <div class="sv-tiles" role="tablist">${STUDENT_TILES.map(([key, title, sub, ic], i) => `<button type="button" class="sv-tile" role="tab" data-sv-tile="${key}" style="--i:${i}"><span class="sv-tile-ic">${icon(ic)}</span><b>${esc(title)}</b><small>${esc(sub)}</small><em data-sv-badge="${key}"></em></button>`).join("")}</div>
      <section class="sv-panel" hidden aria-live="polite"></section>
      <p class="student-footnote">Program, ücret ve anlaşma bilgileri resmî kaynaklarıyla gösterilir. Başvurmadan önce ilgili dönemin kurum duyurusunu inceleyin.</p></div></div>`;
  hydrateIcons(box);
  $$("[data-sv-tile]", box).forEach((tile) => tile.onclick = () => openStudentTile(d, tile.dataset.svTile));
  loadStudentFacts(d);
  api(`/api/universities/${encodeURIComponent(d.id)}/student`, { quiet: true }).then((m) => {
    if (S.uni !== d) return;
    Object.entries(m.groups || {}).forEach(([key, g]) => {
      const badge = $(`[data-sv-badge="${key}"]`); if (!badge) return;
      badge.textContent = g.cached ? (g.item_count ? `${fmtNum(g.item_count)} bilgi` : "Sayfalar") : "";
      badge.classList.toggle("on", Boolean(g.item_count));
    });
  }).catch(() => {});
  if (d.studentTile) openStudentTile(d, d.studentTile, true);
}
async function loadStudentFacts(d) {
  const host = $("[data-sv-facts]");
  try {
    const f = await api(`/api/universities/${encodeURIComponent(d.id)}/facts`, { quiet: true });
    if (S.uni !== d || !host?.isConnected) return;
    const id = f.identity || {}, sc = f.scale || {};
    const cells = [
      sc.students && [count(sc.students.value), `öğrenci${sc.students.year ? ` · ${sc.students.year}` : ""}`],
      id.founded && [esc(id.founded), "kuruluş"],
      id.type && [esc(id.type.replace(" üniversitesi", "")), "üniversite türü"],
      id.city && [esc(id.city), "şehir"],
      id.language && [esc(id.language), "eğitim dili"],
    ].filter(Boolean).slice(0, 4);
    host.innerHTML = cells.map(([v, l]) => `<div class="sv-fact"><b>${v}</b><span>${esc(l)}</span></div>`).join("");
    host.hidden = !cells.length;
    animateCounts(host);
  } catch { if (host) host.hidden = true; }
}
function openStudentTile(d, key, instant = false) {
  const panel = $(".sv-panel"); if (!panel) return;
  const tile = STUDENT_TILES.find(([k]) => k === key); if (!tile) return;
  const [, title, sub, ic] = tile;
  d.studentTile = key;
  $$("[data-sv-tile]").forEach((t) => { const on = t.dataset.svTile === key; t.classList.toggle("on", on); t.setAttribute("aria-selected", String(on)); });
  panel.hidden = false;
  panel.innerHTML = `<header class="sv-panel-head"><span class="sv-tile-ic">${icon(ic)}</span><div><h3>${esc(title)}</h3><small>${esc(sub)}</small></div></header><div class="student-content"></div>`;
  hydrateIcons(panel);
  delete panel.dataset.ready;
  if (key === "undergrad") { delete panel.dataset.studentSection; renderStudentFaculties(panel, d); }
  else { panel.dataset.studentSection = key; panel.dataset.faculty = ""; panel.dataset.department = ""; loadStudentSection(panel, d); }
  if (!instant && !calmMotion()) {
    panel.animate([{ opacity: 0, transform: "translateY(14px) scale(.985)" }, { opacity: 1, transform: "none" }], { duration: 380, easing: EASE });
    panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}
const studentDisclosureStates = new WeakMap();
function moveStudentDisclosure(details, expanded, fromHeight) {
  const summary = $(":scope > summary", details), content = summary?.nextElementSibling;
  if (!summary || !content) return;
  const previous = studentDisclosureStates.get(details);
  const start = fromHeight ?? details.getBoundingClientRect().height;
  if (previous) {
    cancelAnimationFrame(previous.frame); previous.observer?.disconnect();
    if (previous.animation) { previous.animation.onfinish = null; previous.animation.cancel(); }
  }
  const state = { expanded, animation: null, frame: null, observer: null, target: null };
  studentDisclosureStates.set(details, state);
  summary.setAttribute("aria-expanded", String(expanded));
  const finish = () => {
    if (studentDisclosureStates.get(details) !== state) return;
    state.observer?.disconnect(); state.animation = null;
    details.open = expanded; delete details.dataset.animating;
    content.inert = !expanded;
  };
  if (matchMedia("(prefers-reduced-motion: reduce)").matches || typeof details.animate !== "function") { finish(); return; }
  details.open = true; content.inert = !expanded; details.dataset.animating = "true";
  const px = (value) => parseFloat(value) || 0;
  const targetHeight = () => {
    const outer = getComputedStyle(details), inner = getComputedStyle(content);
    return summary.getBoundingClientRect().height + px(outer.paddingTop) + px(outer.paddingBottom)
      + px(outer.borderTopWidth) + px(outer.borderBottomWidth)
      + (expanded ? content.getBoundingClientRect().height + px(inner.marginTop) + px(inner.marginBottom) : 0);
  };
  const animate = (from) => {
    if (!details.isConnected || studentDisclosureStates.get(details) !== state) { finish(); return; }
    state.target = targetHeight();
    state.animation = details.animate([{ height: `${from}px` }, { height: `${state.target}px` }],
      { duration: 280, easing: "cubic-bezier(.22,.75,.25,1)" });
    state.animation.onfinish = finish;
  };
  // Native toggle handlers can populate the selected branch before measuring it.
  state.frame = requestAnimationFrame(() => {
    animate(start);
    if (expanded && typeof ResizeObserver === "function" && state.animation) {
      state.observer = new ResizeObserver(() => {
        if (!state.animation || Math.abs(targetHeight() - state.target) < 1) return;
        const current = details.getBoundingClientRect().height;
        state.animation.onfinish = null; state.animation.cancel(); animate(current);
      });
      state.observer.observe(content);
    }
  });
}
function bindStudentMotion(root) {
  $$("details.student-accordion, details.student-term, details.student-course, details.student-links", root).forEach((details) => {
    if (details.dataset.motionBound) return;
    details.dataset.motionBound = "1";
    const summary = $(":scope > summary", details);
    summary.setAttribute("aria-expanded", String(details.open));
    summary.addEventListener("click", (event) => {
      if (event.target.closest("a, button, input, select, textarea")) return;
      event.preventDefault();
      moveStudentDisclosure(details, !(studentDisclosureStates.get(details)?.expanded ?? details.open));
    });
  });
}
function updateStudentContent(details, render) {
  const previous = details.getBoundingClientRect().height;
  render();
  bindStudentMotion(details);
  if (details.open && studentDisclosureStates.get(details)?.expanded !== false) moveStudentDisclosure(details, true, previous);
}
function bindStudentAccordions(root, d) {
  $$("details[data-student-section]", root).forEach((details) => {
    if (details.dataset.bound) return;
    details.dataset.bound = "1";
    details.addEventListener("toggle", () => { if (details.open) loadStudentSection(details, d); });
  });
  bindStudentMotion(root);
}
// Sayfa başlığı: "Home | Erasmus", "Ostim Teknik Üniversitesi : Yüksek Lisans" → anlamlı parça
function cleanPageTitle(t, fallback = "Resmî sayfa") {
  const parts = String(t || "").split(/\s[|–—:-]\s/).map((x) => x.trim()).filter(Boolean);
  const good = parts.filter((x) => !/^(home|anasayfa|ana sayfa|homepage|index)$/i.test(x) && !/üniversitesi$|university$/i.test(x));
  return good.sort((a, b) => b.length - a.length)[0] || parts[0] || fallback;
}
const hostPath = (u) => { try { const x = new URL(u); return (x.hostname.replace(/^www\./, "") + x.pathname).replace(/\/$/, "").slice(0, 70); } catch { return ""; } };
function studentFactCard(item, section) {
  const src = safeUrl(item.source_url);
  return `<article class="sv-card"><h4>${esc(item.title)}</h4>${item.period ? `<span class="chip">${esc(item.period)}</span>` : section === "fees" ? '<span class="chip warn">Dönem belirtilmemiş</span>' : ""}
    ${item.detail ? `<p>${esc(item.detail)}</p>` : ""}${src ? `<a class="sv-src" href="${esc(src)}" target="_blank" rel="noopener">${icon("external")}${esc(hostPath(src))}</a>` : ""}</article>`;
}
function studentItems(group, section) {
  const items = group.items;
  if (section === "courses" && group.format === "course_catalog") {
    const periods = new Map();
    items.forEach((item) => {
      const key = (item.period || "Dönemi belirtilmeyen dersler").replace(/^(\d+)\s*\.\s*(?:dönem|yarıyıl)/i, "$1. dönem");
      if (!periods.has(key)) periods.set(key, []);
      periods.get(key).push(item);
    });
    const source = (item) => `<a class="source-link" href="${esc(safeUrl(item.source_url))}" target="_blank" rel="noopener">${icon("external")}Kaynağı aç</a>`;
    const progUrl = items.map((x) => x.source_url || "").find((u) => /\/oibs\/bologna\/.*curSunit=\d+/i.test(u));
    return `<div class="student-catalog">${progUrl && safeUrl(progUrl) ? `<div class="program-profile" data-program-url="${esc(safeUrl(progUrl))}"></div>` : ""}<p class="student-hint">${items.length} ders kaydı · İçeriği görmek için bir dönem ve ders seçin.</p>${[...periods].map(([period, courses]) => `<details class="student-term"><summary><b>${esc(period)}</b><span>${courses.length} kayıt</span>${icon("chevron")}</summary><div class="student-term-courses">${courses.map((item) => `<details class="student-course" ${safeUrl(item.detail_url) ? `data-course-url="${esc(safeUrl(item.detail_url))}"` : ""}><summary><span>${esc(item.title)}</span>${icon("chevron")}</summary><div>${item.detail ? `<p>${esc(item.detail)}</p>` : ""}${item.detail_url ? `<div class="course-description"></div>` : ""}${source(item)}</div></details>`).join("")}</div></details>`).join("")}</div>`;
  }
  // Tablo satırları (ör. anlaşmalı kurum listeleri) ayrı, aranabilir bir listede; metin bilgileri kart olarak
  const rows = items.filter((x) => x.evidence_kind === "table"), facts = items.filter((x) => x.evidence_kind !== "table");
  const summaries = facts.filter((x) => x.evidence_kind === "summary" || !x.evidence_kind), raw = facts.filter((x) => x.evidence_kind && x.evidence_kind !== "summary");
  const seen = new Set(), unique = [...summaries, ...raw].filter((x) => { const k = fold(`${x.title} ${x.detail}`).slice(0, 160); if (seen.has(k)) return false; seen.add(k); return true; });
  const pages = new Map();
  unique.forEach((item) => { const k = item.source_url || ""; if (!pages.has(k)) pages.set(k, []); pages.get(k).push(item); });
  const groupHtml = ([url, entries]) => {
    const title = cleanPageTitle(entries.find((x) => x.source_title)?.source_title || (group.links || []).find((l) => l.url === url)?.title);
    return `<div class="sv-group"><div class="sv-group-head"><b>${esc(title)}</b><span>${entries.length} bilgi</span></div><div class="sv-cards">${entries.slice(0, 4).map((x) => studentFactCard(x, section)).join("")}</div>
      ${entries.length > 4 ? `<details class="student-links sv-more"><summary>${entries.length - 4} bilgi daha</summary><div class="sv-cards">${entries.slice(4).map((x) => studentFactCard(x, section)).join("")}</div></details>` : ""}</div>`;
  };
  // En çok bilgi içeren sayfalar önde; beşten fazlası tek başlık altında
  const ordered = [...pages].sort((a, b) => b[1].length - a[1].length);
  const groups = ordered.slice(0, 5).map(groupHtml).join("") + (ordered.length > 5
    ? `<details class="student-links sv-more"><summary>${ordered.length - 5} kaynak sayfası daha</summary>${ordered.slice(5).map(groupHtml).join("")}</details>` : "");
  const table = rows.length ? `<div class="sv-group"><div class="sv-group-head"><b>${section === "erasmus" ? "Anlaşmalı kurumlar" : "Tablo kayıtları"}</b><span>${fmtNum(rows.length)} satır</span></div>
    <div class="input slim sv-rows-q">${icon("search")}<input placeholder="${section === "erasmus" ? "Ülke veya üniversite ara" : "Tabloda ara"}" data-sv-rows-q></div>
    <ul class="sv-rows">${rows.map((x) => { let t = x.quote || x.title; if (x.context_quote && t.startsWith(x.context_quote)) t = t.slice(x.context_quote.length).trim(); return `<li data-q="${esc(fold(t))}"><span>${esc(t)}</span>${x.period ? `<small>${esc(x.period)}</small>` : ""}</li>`; }).join("")}</ul></div>` : "";
  return `${groups}${table}`;
}
function studentSectionResult(data, section) {
  const group = data.groups?.[section] || { items: [], links: [] };
  const date = (value) => value ? new Date(value * 1000).toLocaleDateString("tr-TR") : "—";
  const previous = (group.items?.length || group.links?.length) && group.previously_checked_at;
  const links = (section === "courses" ? [] : group.links || []).filter((l) => safeUrl(l.url) && !/^(türkçe|turkce|english|ingilizce|tr|en)$/i.test((l.title || "").trim()) && (section !== "work_travel" || /work.?(and|&)?.?travel|\bwat\b/i.test(`${l.title} ${l.url}`)));
  const hasItems = Boolean(group.items?.length);
  const empty = !hasItems && !links.length
    ? `<div class="sv-empty">${icon("info")}<div><b>${data.errors?.length ? "Bu bilgi şu an alınamadı" : section === "work_travel" ? "Üniversitenin sitesinde Work and Travel sayfası yok" : "Resmî sayfalarda bu başlıkta bilgi bulunamadı"}</b><p>${data.errors?.length ? "Kurum sitesi geç yanıt vermiş olabilir; yeniden tarayabilirsin." : section === "work_travel" ? "Work and Travel genellikle özel ajanslarla yürütülür; üniversite yalnız duyuru yayımlıyorsa burada görünür. Uluslararası ofis sayfaları Erasmus başlığında." : "Kurum bu konuyu sitesinde yayımlamıyor olabilir. Asistana sorarak diğer sayfalara da baktırabilirsin."}</p></div></div>` : "";
  return `<div class="student-section-meta"><span>${previous ? "Önceki kayıt" : "Son kontrol"}: ${date(previous || data.checked_at)} · ${fmtNum(data.pages_read || 0)} sayfa okundu</span><button class="btn sm" type="button" data-student-refresh>${icon("refresh")}Yeniden tara</button></div>
    ${data.errors?.length ? `<div class="notice warn"><div>${data.errors.map(esc).join(" ")}</div></div>` : ""}
    ${hasItems ? studentItems(group, section) : ""}${empty}
    ${links.length && group.format !== "course_catalog" ? `<div class="sv-group"><div class="sv-group-head"><b>${hasItems ? "İlgili resmî sayfalar" : "Resmî sayfalarda bulunanlar"}</b><span>${links.length} sayfa</span></div>
      <div class="sv-previews">${links.slice(0, hasItems ? 4 : 8).map(linkPreviewCard).join("")}</div>
      ${links.length > (hasItems ? 4 : 8) ? `<details class="student-links sv-more"><summary>${links.length - (hasItems ? 4 : 8)} sayfa daha</summary><div class="sv-previews">${links.slice(hasItems ? 4 : 8).map(linkPreviewCard).join("")}</div></details>` : ""}</div>` : ""}`;
}
function linkPreviewCard(link) {
  const url = safeUrl(link.url);
  return `<article class="lp" data-lp-url="${esc(url)}"><header><span class="lp-ic">${icon(/\.pdf(\?|$)/i.test(url) ? "file" : "globe")}</span><div><b>${esc(cleanPageTitle(link.title, "Resmî sayfa"))}</b><small>${esc(hostPath(url))}</small></div>
    <a class="icon-btn" href="${esc(url)}" target="_blank" rel="noopener" title="Sayfayı aç" aria-label="Sayfayı aç">${icon("external")}</a></header>
    <div class="lp-body"><span class="sk-line"></span><span class="sk-line short"></span></div></article>`;
}
function linkPreviewBody(p) {
  const secs = (p.sections || []).filter((s) => s.items?.length).slice(0, 3);
  const item = (x) => safeUrl(x.url) ? `<li><a href="${esc(safeUrl(x.url))}" target="_blank" rel="noopener">${esc(x.text)}</a></li>` : `<li>${esc(x.text)}</li>`;
  const body = `${p.description ? `<p class="lp-desc">${esc(p.description)}</p>` : ""}${(p.paragraphs || []).slice(0, p.description ? 1 : 2).map((x) => `<p>${esc(x)}</p>`).join("")}
    ${secs.map((s) => `<div class="lp-sec">${s.heading ? `<h5>${esc(s.heading)}</h5>` : ""}<ul>${s.items.slice(0, 6).map(item).join("")}</ul>${s.items.length > 6 ? `<small>+${s.items.length - 6} madde</small>` : ""}</div>`).join("")}`;
  return body.trim() || `<p class="faint">Bu sayfada okunabilir metin bulunamadı; sayfayı açarak inceleyebilirsin.</p>`;
}
document.addEventListener("click", (e) => { const c = e.target.closest(".sv-card"); if (c && !e.target.closest("a")) c.classList.toggle("open"); });
// Önizlemeler görünür oldukça, en fazla üç paralel istekle yüklenir (sonuçlar sunucuda 14 gün saklanır)
function mountLinkPreviews(root, d) {
  const cards = $$(".lp[data-lp-url]:not([data-lp-state])", root);
  if (!cards.length) return;
  let active = 0; const queue = [];
  const pump = () => {
    while (active < 3 && queue.length) {
      const card = queue.shift(); active++;
      api(`/api/universities/${encodeURIComponent(d.id)}/student/preview?url=${encodeURIComponent(card.dataset.lpUrl)}`, { quiet: true })
        .then((p) => {
          const b = $(".lp-body", card); if (!b) return;
          if (p.title && !/^(home|anasayfa)$/i.test(p.title)) $("header b", card).textContent = cleanPageTitle(p.title);
          b.innerHTML = linkPreviewBody(p); card.dataset.lpState = "done";
          if (!calmMotion()) b.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 260 });
        })
        .catch((e) => { const b = $(".lp-body", card); if (b) b.innerHTML = `<p class="faint">${esc(e.message || "Önizleme alınamadı.")}</p>`; card.dataset.lpState = "error"; })
        .finally(() => { active--; pump(); });
    }
  };
  const io = new IntersectionObserver((entries) => entries.forEach((en) => {
    if (!en.isIntersecting) return;
    io.unobserve(en.target); en.target.dataset.lpState = "queued"; queue.push(en.target); pump();
  }), { rootMargin: "200px" });
  cards.forEach((c) => io.observe(c));
}
async function loadStudentSection(details, d, refresh = false) {
  if (S.uni !== d || !details.isConnected) return;
  studentState(d);
  const section = details.dataset.studentSection, faculty = details.dataset.faculty || "", department = details.dataset.department || "";
  d.studentChatScope = { faculty, department }; drawStudentChat(d);
  const key = JSON.stringify([section, faculty, department]), box = $(":scope > .student-content", details);
  if (section === "courses" && d.studentResults.has(key) && d.studentResults.get(key).collection_version !== 6) d.studentResults.delete(key);
  const draw = (data) => {
    if (S.uni !== d || !details.isConnected) return;
    updateStudentContent(details, () => { box.innerHTML = studentSectionResult(data, section); });
    $("[data-student-refresh]", box).onclick = () => loadStudentSection(details, d, true);
    mountLinkPreviews(box, d);
    bindCourseDetails(box, d);
    loadProgramProfile(box, d);
    $$("[data-sv-rows-q]", box).forEach((input) => input.oninput = () => {
      const q = fold(input.value);
      $$(".sv-rows li", input.closest(".sv-group")).forEach((li) => { li.hidden = Boolean(q) && !li.dataset.q.includes(q); });
    });
  };
  if (d.studentResults.has(key) && !refresh && !d.studentPending.has(key)) { draw(d.studentResults.get(key)); return; }
  if (d.studentResults.has(key)) draw(d.studentResults.get(key));
  else box.innerHTML = "";
  $("[data-student-refresh]", box)?.setAttribute("disabled", "");
  if (!$(".student-loading", box)) box.insertAdjacentHTML("afterbegin", `<div class="loading-line student-loading" role="status"><span class="spinner"></span>${esc(department || STUDENT_SECTIONS.find(([id]) => id === section)?.[1] || "Seçilen bilgiler")} alınıyor…</div>`);
  let pending = d.studentPending.get(key);
  if (!pending) {
    const query = new URLSearchParams({ section });
    if (faculty) query.set("faculty", faculty);
    if (department) query.set("department", department);
    if (refresh) query.set("refresh", "1");
    pending = api(`/api/universities/${encodeURIComponent(d.id)}/student?${query}`, { quiet: true });
    d.studentPending.set(key, pending);
  }
  try { const data = await pending; d.studentResults.set(key, data); draw(data); }
  catch (error) {
    if (S.uni !== d || !details.isConnected) return;
    if (d.studentResults.has(key)) draw(d.studentResults.get(key)); else box.innerHTML = "";
    box.insertAdjacentHTML("afterbegin", `<div class="notice warn"><div>${esc(error.message)} <button class="link" data-student-retry type="button">Tekrar dene</button></div></div>`);
    $("[data-student-retry]", box).onclick = () => loadStudentSection(details, d, true);
  } finally { if (d.studentPending.get(key) === pending) d.studentPending.delete(key); }
}
function renderStudentFaculties(details, d) {
  const box = $(":scope > .student-content", details);
  const faculties = d.data.items.map((fac, i) => ({ fac, i })).filter(({ fac }) => /fakulte|yuksekokul|faculty|school/.test(fold(fac.name)) && !/meslek|enstitu|lisansustu|graduate/.test(fold(fac.name)));
  box.innerHTML = faculties.length ? `<p class="student-hint">Bir fakülte seçerek bölümlerini aç.</p><div class="student-tree">${faculties.map(({ fac, i }) => `<details class="student-accordion student-branch" data-student-faculty="${i}"><summary><span class="student-summary-icon">${icon("building")}</span><span><b>${esc(fac.name)}</b></span>${icon("chevron")}</summary><div class="student-content"></div></details>`).join("")}</div>` : '<p class="student-missing">YÖK dizininde lisans fakültesi veya yüksekokulu bulunamadı.</p>';
  $$("[data-student-faculty]", box).forEach((entry) => entry.addEventListener("toggle", () => { if (entry.open) loadStudentFaculty(entry, d); }));
  bindStudentAccordions(box, d);
}
async function loadStudentFaculty(details, d) {
  if (S.uni !== d || !details.isConnected || details.dataset.ready) return;
  const faculty = d.data.items[Number(details.dataset.studentFaculty)], box = $(":scope > .student-content", details);
  if (!faculty) return;
  studentState(d);
  if (d.facData && d.data.items[d.fac]?.raw === faculty.raw) d.studentFaculties.set(faculty.raw, d.facData);
  let data = d.studentFaculties.get(faculty.raw);
  if (!data) {
    box.innerHTML = '<div class="loading-line" role="status"><span class="spinner"></span>Seçilen fakültenin bölümleri alınıyor…</div>';
    let pending = d.studentFacultyPending.get(faculty.raw);
    if (!pending) {
      pending = api(`/api/universities/${encodeURIComponent(d.id)}/faculty?name=${encodeURIComponent(faculty.raw)}&metrics=false`, { quiet: true });
      d.studentFacultyPending.set(faculty.raw, pending);
    }
    try { data = await pending; d.studentFaculties.set(faculty.raw, data); }
    catch (error) {
      if (S.uni === d && details.isConnected) {
        updateStudentContent(details, () => {
          box.innerHTML = `<div class="notice warn"><div>${esc(error.message)} <button class="link" type="button" data-faculty-retry>Tekrar dene</button></div></div>`;
        });
        $("[data-faculty-retry]", box).onclick = () => loadStudentFaculty(details, d);
      }
      return;
    } finally { if (d.studentFacultyPending.get(faculty.raw) === pending) d.studentFacultyPending.delete(faculty.raw); }
  }
  if (S.uni !== d || !details.isConnected) return;
  details.dataset.ready = "1";
  updateStudentContent(details, () => {
    box.innerHTML = `<div class="student-tree">${data.departments.map((dep, i) => `<details class="student-accordion student-branch" data-student-department="${i}"><summary><span class="student-summary-icon">${icon("grid")}</span><span><b>${esc(dep.name)}</b><small>${fmtNum(dep.count)} akademisyen · YÖK Akademik</small></span>${icon("chevron")}</summary><div class="student-content"></div></details>`).join("") || '<p class="student-missing">Bu fakülte için bölüm bilgisi bulunamadı.</p>'}</div>`;
  });
  $$("[data-student-department]", box).forEach((entry) => entry.addEventListener("toggle", () => {
    if (!entry.open || entry.dataset.ready) return;
    entry.dataset.ready = "1";
    const dep = data.departments[Number(entry.dataset.studentDepartment)], target = $(":scope > .student-content", entry);
    target.innerHTML = `<section class="department-courses" data-student-section="courses" data-faculty="${esc(faculty.raw)}" data-department="${esc(dep.name)}"><div class="student-content"></div></section>`
      + `<details class="student-accordion student-branch" data-student-staff><summary><span class="student-summary-icon">${icon("users")}</span><span><b>Akademik kadro</b><small>${fmtNum(dep.count)} akademisyen</small></span>${icon("chevron")}</summary><div class="student-content"></div></details>`;
    loadStudentSection($(".department-courses", target), d);
    const staff = $("[data-student-staff]", target);
    staff.addEventListener("toggle", () => { if (staff.open && !staff.dataset.ready) { staff.dataset.ready = "1"; renderStudentStaff($(":scope > .student-content", staff), data.people.filter((p) => p.department === dep.key), d); } });
    bindStudentAccordions(target, d);
  }));
  bindStudentAccordions(box, d);
}
function renderStudentStaff(box, people, d) {
  box.innerHTML = `<div class="student-staff">${people.map((person) => {
    const saved = existingChat({ name: person.name, university: d.data.name });
    const source = safeUrl(person.site_url || person.url);
    return `<article class="student-person">${avatar(person.name, person.photo)}<div><b>${esc(person.name)}</b><span>${esc(person.title || "")}</span></div><div class="student-person-links">${saved ? `<a class="source-link" href="#/profil/${esc(saved.id)}">Kayıtlı profil ${icon("chevron")}</a>` : ""}${source ? `<a class="source-link" href="${esc(source)}" target="_blank" rel="noopener">Kaynak ${icon("external")}</a>` : ""}</div></article>`;
  }).join("") || '<p class="student-missing">Bu bölümde kadro kaydı bulunamadı.</p>'}</div>`;
}
function setUniversityAudience(audience) {
  if (!S.uni) return;
  S.uni.audience = audience;
  $$("[data-audience]").forEach((button) => { const on = button.dataset.audience === audience; button.classList.toggle("active", on); button.setAttribute("aria-selected", String(on)); });
  $("#academicUniversity").hidden = audience !== "academic";
  $("#studentView").hidden = audience !== "student";
  $("#universityOverview").hidden = audience !== "overview";
  if (audience === "overview") renderUniversityOverview();
  if (audience === "student") renderStudentView();
}

function renderUni() {
  const d = S.uni, items = d.data.items;
  setCrumbs([{ label: "Ana sayfa", href: "#/" }, { label: "Üniversiteler", href: "#/universiteler" }, { label: d.data.name }]);
  if ($("#uName").dataset.typed !== d.data.name) { $("#uName").dataset.typed = d.data.name; typeText($("#uName"), d.data.name); }
  $("#uMeta").innerHTML = `<span>Kaynak: YÖK Akademik</span>${d.data.home ? `<span>${esc(new URL(d.data.home).hostname.replace(/^www\./, ""))}</span>` : ""}`;
  $("#uLogo").innerHTML = organizationLogo("universities", d.id, d.data.name, "hero-logo");
  $("#uAct").innerHTML = organizationSaveButton("universities", d.id) + (d.data.home ? `<a class="btn sm" href="${esc(safeUrl(d.data.home))}" target="_blank" rel="noopener">${icon("globe")}Kurum sitesi</a>
    <button class="btn sm" id="uNewPerson" type="button">${icon("plus")}Akademisyen ara</button>` : "");
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
    d.facData = data; renderYokDeps(); loadYokRoles(d, fac.raw);
  } catch (e) { if (active()) body.innerHTML = `<div class="col-empty">${esc(e.message)}</div>`; }
}
// Dekan / bölüm başkanı: YÖK "İdari Görevler" (yalnız süren görevler); ilk açılış birkaç saniye, sonra önbellek
async function loadYokRoles(d, facRaw) {
  if (d.roles?.fac === facRaw && d.roles.data) return;
  d.roles = { fac: facRaw, data: null, loading: true };
  if ($("#colDep .fac-lead")) renderYokDeps();
  try {
    const data = await api(`/api/universities/${encodeURIComponent(d.id)}/roles?name=${encodeURIComponent(facRaw)}`, { quiet: true });
    if (d.roles?.fac !== facRaw) return;
    d.roles = { fac: facRaw, data, loading: false };
  } catch { if (d.roles?.fac === facRaw) d.roles = { fac: facRaw, data: null, loading: false, failed: true }; }
  if (S.uni !== d || d.data.items[d.fac]?.raw !== facRaw || !$("#colDep")) return;
  renderYokDeps();
  if (d.dep != null) d.staffController?.draw();
}
const ROLE_ORDER = ["Dekan", "Bölüm Başkanı", "Dekan Yardımcısı", "Bölüm Başkan Yardımcısı", "Rektör Yardımcısı", "Rektör", "Müdür"];
function staffRoles(p) {
  const roles = S.uni?.roles?.data?.roles?.[p.yok_id] || [];
  const names = [...new Set(roles.map((r) => r.role))];
  return names.sort((a, b) => (ROLE_ORDER.findIndex((x) => a.startsWith(x)) + 99) % 99 - (ROLE_ORDER.findIndex((x) => b.startsWith(x)) + 99) % 99).slice(0, 2);
}

function renderYokDeps() {
  const d = S.uni, f = d.facData;
  $("#colDepN").textContent = f.departments.length;
  const roles = d.roles?.fac === d.data.items[d.fac]?.raw ? d.roles : null, info = roles?.data;
  const head = (name) => { const h = info?.heads?.[name]; return h ? `<span class="u-head">${icon("user")}Bölüm Başkanı: <b>${esc(`${h.title} ${h.name}`)}</b></span>` : ""; };
  const lead = roles?.loading ? `<div class="fac-lead loading"><span class="spinner"></span>Dekan ve bölüm başkanları YÖK'ten okunuyor…</div>`
    : info?.dean ? `<div class="fac-lead"><span class="fl-badge">Dekan</span><div><b>${esc(`${info.dean.title} ${info.dean.name}`)}</b><small>${esc(info.dean.since)}'den beri · YÖK İdari Görevler</small></div></div>`
    : info ? `<div class="fac-lead muted">Dekan bilgisi bu fakültenin YÖK profillerinde bulunamadı.</div>` : "";
  const row = (name, n, i, q) => `<div class="unit ${d.dep === i ? "active" : ""}" data-unit="ydep" data-i="${i}" style="--i:${Math.min(i + 1, 24)}" data-q="${esc(q)}">
    <div class="u-main"><b>${esc(name)}</b><span>${n} akademisyen</span>${i >= 0 ? head(name) : ""}</div>
    <div class="u-act"><button class="btn sm" data-yokpapers="${i}" type="button" title="Bu birimin yayınları">${icon("file")}Yayınlar</button></div>${icon("chevron")}</div>`;
  $("#colDep .col-body").innerHTML = `${lead}<div class="stagger">${row("Tüm fakülte", f.people.length, -1, "tum fakulte")}${f.departments.map((x, i) => row(x.name, x.count, i, fold(x.name))).join("")}</div>`;
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
  let paperRevision, staffRevision, loadEpoch = 0, busy = false, lastJob = null, polling = false;
  const staff = mountStaffList($("#unitStaff"), "unit", [], { institution: sub, mode: "directory", onRefresh: (p) => refreshPerson(p) });
  const setBusy = (value) => {
    busy = value; rescan.disabled = value; rescan.setAttribute("aria-busy", String(value));
    rescan.innerHTML = `${value ? '<span class="spinner" aria-hidden="true"></span>' : icon("refresh")}Tekrar tara`;
    if (!value) hydrateIcons(rescan);
  };
  const apply = (r) => {
    const papers = r.papers || [], people = r.staff || [], total = r.total_people ?? r.people ?? people.length;
    if (r.job_id) lastJob = r.job_id;
    const idle = people.filter((p) => p.status === "idle").length;
    const complete = r.completed ?? r.matched ?? 0;
    const state = r.status === "running" ? "Kaynaklar taranıyor" : r.cached
      ? `Kayıtlı sonuçlar${r.status === "error" ? " · toplama tamamlanamadı" : r.status === "partial" ? " · kısmi sonuç" : r.status === "cancelled" ? " · tarama durduruldu" : ""}`
      : r.status === "error" ? "Toplama tamamlanamadı" : r.status === "partial" ? "Kısmi sonuç" : r.status === "cancelled" ? "Tarama durduruldu" : "Toplama tamamlandı";
    $("#unitProgress").innerHTML = `${r.status === "running" ? '<span class="spinner"></span>' : ""}${state} · ${fmtNum(complete)} / ${fmtNum(total)} akademisyen tamamlandı${idle ? ` · ${fmtNum(idle)} kişi taranmadı (kadrodaki satırdan Yenile)` : ""}`;
    if (idle && r.status !== "running") $(".unit-staff").open = true;
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
  // Satırdaki Yenile: yalnız o kişi taranır; çekmece açıkken sonuç gelene kadar izlenir
  async function refreshPerson(p) {
    if (!lastJob || !active()) return;
    try {
      const first = await post(`/api/units/papers/${encodeURIComponent(lastJob)}/people/${encodeURIComponent(p.person_key)}`, {});
      if (polling) { apply(first); return; }
      polling = true;
      const epoch = loadEpoch, current = () => active() && epoch === loadEpoch;
      await pollSnapshots(async () => first, current, apply, (r) => r.status === "running" && !!r.job_id,
        (r) => api(`/api/units/papers/${encodeURIComponent(r.job_id)}`));
    } catch (e) { toast(esc(e.message)); }
    finally { polling = false; }
  }
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
      const seq = S.routeSeq;
      const data = await api(`/api/chats/${encodeURIComponent(cid)}`);
      if (seq !== S.routeSeq) return;
      if (!data.result) { setView(emptyState("user", "Profil sonucu bulunamadı", "Bu sohbetin profil sonucu silinmiş olabilir.")); return; }
      S.result = data.result; chat = data.chat;
    } catch { setView(emptyState("user", "Profil bulunamadı", "Bu kayıt silinmiş olabilir.")); return; }
  }
  S.chatId = cid; S.jobId = S.result.job_id;
  rememberVisit("person", cid, S.result.profile.name);
  renderProfile(S.result, chat);
}

// Kapakta kendiliğinden kayan bilgi şeridi (fare üstündeyken durur)
function mountSlider(box) {
  if (!box) return;
  const slides = $$(".ph-slide", box), dots = $(".ph-dots", box);
  if (!slides.length) return;
  let i = 0, timer = 0;
  dots.innerHTML = slides.length > 1 ? slides.map((_, k) => `<button type="button" aria-label="${k + 1}"></button>`).join("") : "";
  const show = (n) => { i = (n + slides.length) % slides.length; slides.forEach((sl, k) => sl.classList.toggle("on", k === i)); $$("button", dots).forEach((d, k) => d.classList.toggle("on", k === i)); };
  const start = () => { clearInterval(timer); if (slides.length > 1) timer = setInterval(() => { if (!box.isConnected) clearInterval(timer); else show(i + 1); }, 4200); };
  dots.onclick = (e) => { const b = e.target.closest("button"); if (b) { show($$("button", dots).indexOf(b)); start(); } };
  const prev = $(".ph-prev", box), next = $(".ph-next", box);
  if (prev) prev.onclick = () => { show(i - 1); start(); };
  if (next) next.onclick = () => { show(i + 1); start(); };
  if (slides.length < 2) $(".ph-ctrl", box)?.setAttribute("hidden", "");
  box.onmouseenter = () => clearInterval(timer); box.onmouseleave = start;
  show(0); start();
}
// Profil fotoğrafı büyür; yanında iletişim düğmeleri çıkar
function photoPop(src, linksHtml) {
  const layer = document.createElement("div");
  layer.className = "photo-pop";
  const img = $("img", src);
  layer.innerHTML = `<div class="folder-scrim"></div><div class="pp-card"><div class="pp-photo">${img ? `<img src="${esc(img.src)}" alt="">` : src.innerHTML}</div>
    <div class="pp-links">${linksHtml || `<span class="faint">İletişim bilgisi yok.</span>`}</div></div>`;
  document.body.appendChild(layer); hydrateIcons(layer);
  const portrait = $(".pp-photo img", layer);
  if (portrait) {
    const fit = () => { const w = Math.min(240, portrait.naturalWidth || 128), h = Math.min(300, portrait.naturalHeight || 160); Object.assign(portrait.parentElement.style, { width: `${w}px`, height: `${h}px`, aspectRatio: "auto" }); };
    portrait.addEventListener("load", fit); if (portrait.complete) fit();
  }
  const card = $(".pp-card", layer), photo = $(".pp-photo", layer), from = src.getBoundingClientRect(), to = photo.getBoundingClientRect();
  const ease = "cubic-bezier(.22,.9,.24,1)";
  if (!calmMotion()) {
    photo.animate([{ transform: `translate(${from.left - to.left}px, ${from.top - to.top}px) scale(${from.width / to.width})` }, { transform: "none" }], { duration: 560, easing: ease });
    $$(".pp-links > *", layer).forEach((el, k) => el.animate([{ opacity: 0, transform: "translateX(-14px) scale(.9)" }, { opacity: 1, transform: "none" }], { duration: 360, delay: 260 + k * 60, easing: ease, fill: "backwards" }));
    $(".folder-scrim", layer).animate([{ opacity: 0 }, { opacity: 1 }], { duration: 360 });
  }
  const close = () => {
    document.removeEventListener("keydown", onKey);
    const back = src.getBoundingClientRect(), now = photo.getBoundingClientRect();
    $(".folder-scrim", layer).animate([{ opacity: 1 }, { opacity: 0 }], { duration: 320, fill: "forwards" });
    $(".pp-links", layer).animate([{ opacity: 1 }, { opacity: 0 }], { duration: 180, fill: "forwards" });
    photo.animate([{ transform: "none" }, { transform: `translate(${back.left - now.left}px, ${back.top - now.top}px) scale(${back.width / now.width})` }], { duration: 420, easing: ease, fill: "forwards" })
      .finished.then(() => layer.remove(), () => layer.remove());
  };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  document.addEventListener("keydown", onKey);
  layer.addEventListener("click", (e) => { if (!e.target.closest(".pp-links a")) close(); });
  void card;
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
    ["pubs", "Yayınlar", r.unique_count], ["career", "Akademik geçmiş", (y.career || []).length + (y.education || []).length],
    ["courses", "Dersler", (sec.courses || []).length], ["theses", "Tezler", nTheses],
    ["more", "Projeler ve diğer", ["projects", "awards", "patents", "memberships", "art"].reduce((s, k) => s + (sec[k] || []).length, 0)],
    ["collab", "İş birlikleri", (y.collaborators || []).length + (r.industry || []).length],
    ...(trProjects.length ? [["tubitak", "TÜBİTAK", trProjects.length]] : []), ["patents", "Patentler", patentCount(r.patents)],
    ["score", "Doçentlik ve teşvik puanı", ""], ["interests", "Ekstra bilgi", ""], ["chat", "Asistan", ""],
  ];
  const otherSections = [["projects", "Projeler", "briefcase"], ["awards", "Ödüller", "award"], ["patents", "Patentler", "file"],
    ["memberships", "Üyelikler", "users"], ["art", "Sanatsal faaliyetler", "sparkle"]];
  const pubSrc = (x) => ({ jid: r.job_id, pid: x.id, person: p.name });
  S.lists.pubs = r.publications;
  S.listMeta.pubs = { file: p.name, person: p.name, title: p.title, institution: p.institution, cats: true };

  S.collabs = y.collaborators || []; S.collabPubs = r.publications || [];
  const heroInts = (p.verification?.interests?.length ? p.verification.interests.map((x) => cleanInterest(x.value)) : (p.interests || []).map(cleanInterest)).filter(Boolean);
  const root = setView(`
    <section class="card profile-hero identity-hero" data-org-brand>
      <div class="ph-branding"><div class="ph-band identity-cover"><div class="ph-institution">${organizationLogo("universities", orgId(p.institution), p.institution, "band-logo")}<span>${esc(p.institution || "Akademik profil")}</span></div>
      </div>
      <div class="ph-body identity-main">
        <button type="button" class="ph-photo identity-avatar" id="phPhoto" aria-label="Fotoğraf ve iletişim">${r.job_id ? `<img src="/api/jobs/${encodeURIComponent(r.job_id)}/photo?v=2" alt="${esc(p.name)}" onerror="this.hidden=true">` : avatar(p.name, safeImg(p.photo || y.photo))}</button>
        <div class="ph-info identity-info">
          <div class="ph-title">${esc(p.title || "Unvan bilinmiyor")}</div>
          <h1>${esc(p.name)}</h1>
          <div class="ph-lines"><span>${esc(p.department || "Bölüm bilinmiyor")}</span></div>
        </div>
        <div class="kebab ph-gear"><button class="icon-btn kebab-btn" type="button" aria-label="Profil ayarları" title="Profil ayarları">${icon("settings")}</button><div class="kebab-menu" hidden>
          <button class="btn ${isFav ? "" : "primary"}" id="favPersonBtn" type="button">${icon("star")}${isFav ? "Favorilerde" : "Favorilere ekle"}</button>
          <button class="btn" id="refreshProfileBtn" type="button" title="Yenilenecek bilgileri ve kaynakları seç">${icon("refresh")}Yenile</button>
        </div></div>
      </div>
      </div><div class="kpis">
        <div class="kpi"><b id="profilePubCount">${count(r.unique_count)}</b><span>benzersiz yayın</span></div>
        <div class="kpi"><b id="profileCitesCount">${count(totalCites)}</b><span>toplam atıf</span></div>
        <div class="kpi"><b>${count((sec.courses || []).length)}</b><span>ders</span></div>
        ${hIndex.length ? `<div class="kpi kpi-h" title="Kaynaklar farklı yayınları saydığı için değerler farklı olabilir. Web of Science ve Scopus değerleri dahil değildir.">${hIndex.map(([v, l]) => `<b>${count(v)}<small>${esc(l)}</small></b>`).join("")}<span>h-index</span></div>` : ""}
        <div class="kpi"><b>${count(nTheses)}</b><span>yönetilen tez</span></div>
        <div class="kpi"><b>${count((y.collaborators || []).length)}</b><span>iş birliği</span></div>
      </div>
    </section>

    <div class="tabs" role="tablist">${tabs.map(([k, l, n], i) => `<button class="tab ${i === 0 ? "active" : ""}" data-tab="${k}" type="button" ${k === "patents" && !n ? "hidden" : ""}>${esc(l)}${n !== "" && n != null ? `<span class="n">${fmtNum(n)}</span>` : ""}</button>`).join("")}</div>

    <div class="panel" data-panel="overview" hidden><div class="stack"><div class="stack" id="analysisBox">${analysisHtml(a)}</div>

      ${false ? `<div class="card card-pad"><div class="card-title">İlgi alanları</div><div class="chips">
        ${(p.verification?.interests?.length ? p.verification.interests.filter((x) => cleanInterest(x.value)).slice(0, 16).map((x) => `<span class="chip" title="${esc(x.sources.join(", "))}">${esc(cleanInterest(x.value))}${x.sources.length > 1 ? `<sup>✓${x.sources.length}</sup>` : ""}</span>`)
          : p.interests.filter(cleanInterest).map((x) => `<span class="chip">${esc(cleanInterest(x))}</span>`)).join("")}</div></div>` : ""}
      ${(r.industry || []).length ? `<div class="card card-pad"><div class="card-title">${icon("building")}Sanayi iş birlikleri<span class="spacer"></span>
        <button class="btn sm" data-tabgo="collab" type="button">Kanıtları gör</button></div><div class="chips">${r.industry.map((x) =>
          `<span class="chip ${x.official ? "teal" : ""}">${x.official ? "✓ " : ""}${esc(x.name)}</span>`).join("")}</div></div>` : ""}
      ${techTrace(r)}
      <p class="faint"><span id="profileSummary">${esc(r.summary || "")}</span> · ${r.elapsed ?? "?"} sn · ${esc(r.llm || "")}${y.updated ? ` · YÖK son güncelleme ${esc(y.updated)}` : ""}</p>
    </div></div>

    <div class="panel active" data-panel="pubs">
      <div class="publication-actions"><div class="pub-scan-state" id="profileWosState" role="status"></div>${sourcePicker("profileSourcesPicker", PROFILE_SOURCES, r.refresh_preferences?.sources, true)}</div><div id="profilePublications"></div></div>

    <div class="panel" data-panel="interests"><div class="extra-info-grid"><section class="card card-pad"><h3>Dergi çeyreği</h3><p class="extra-info-value" id="profileQuartiles">${quartileDistribution(r, qCounts)}</p><p class="faint">SJR sınıflaması, yayın yılına göre derginin en iyi alanı.</p></section><section class="card card-pad"><h3>Kaynak dağılımı</h3><p class="extra-info-value" id="profileSources">${esc(sourceDistribution(r))}</p></section></div><div class="card card-pad"><h3>İlgi alanları</h3><div class="chips interest-list">${heroInts.map(x => `<span class="chip">${esc(x)}</span>`).join("") || "İlgi alanı kaydı bulunamadı."}</div></div></div>
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
      ${otherSections.filter(([k]) => (sec[k] || []).length).map(([k, l, ic]) => `<div class="card card-pad"><div class="card-title">${icon(ic)}${l}<span class="spacer"></span><span class="count">${(sec[k] || []).length}</span></div>${sectionView(sec[k])}</div>`).join("")}</div>
      ${(() => { const none = otherSections.filter(([k]) => !(sec[k] || []).length).map(([, l]) => l); return none.length ? `<div class="empty-sections">${icon("info")}<span>YÖK'te kaydı bulunmayan: <b>${esc(none.join(", "))}</b>. Eski profillerde projeler okunamamış olabilir; <b>Yenile → Projeler</b> ile tekrar alınır.</span></div>` : ""; })()}</div>

    <div class="panel" data-panel="collab"><div class="stack"><div id="industryBox">${industryHtml(r.industry)}</div>${(y.collaborators || []).length ? `<div class="collabs stagger">${y.collaborators.map((c, i) => `
      <div class="collab cl-card" data-collab="${i}" style="--i:${i}">
        <div class="cl-uni">${c.institution ? organizationLogo("universities", orgId(c.institution), c.institution, "cl-logo") : ""}<span>${esc(c.institution || "")}</span></div>
        <div class="cl-person">${avatar(c.name, c.photo, "av cl-av")}<div><b>${esc(c.name)}</b><span>${esc(c.title || "")}</span></div></div></div>`).join("")}</div>`
      : `<div class="card">${emptyState("users", "İş birliği bilgisi yok", "YÖK'te birlikte çalıştığı kişi kaydı bulunamadı ya da profil eski sürümle hazırlandı.")}</div>`}</div></div>

    <div class="panel" data-panel="tubitak"><div class="card card-pad" id="tubitakBox">${tubitakHtml(trProjects, r.industry)}</div></div>
    <div class="panel" data-panel="patents"><div class="card card-pad" id="patentsBox">${r.patents ? personPatentsHtml(r.patents) : ""}</div></div>

    <div class="panel" data-panel="score"><div id="scoreBox" class="t-score" data-job-id="${esc(r.job_id || "")}"></div></div>
    <div class="panel" data-panel="chat"><div class="card chat-wrap">
      <div class="chat-head"><span class="chat-orb">${icon("sparkle")}</span><div><b>Profil asistanı</b><span>${esc(p.name)} · yalnız toplanan kaynaklardan, kimlikli yanıt</span></div></div>
      <div class="thread" id="thread"><div class="msg bot"><span class="chat-orb sm">${icon("sparkle")}</span><div class="bubble">Merhaba! <b>${esc(p.name)}</b> hakkında yayınlar, dersler, tezler, iş birlikleri ya da araştırma alanları üzerine soru sorabilirsiniz.
        Cevaplar yalnızca toplanan kaynaklara dayanır ve yayın kimlikleriyle gösterilir.</div></div></div>
      <div class="suggest">${["En çok atıf alan yayınları hangileri?", "Hangi dersleri veriyor?", "Danışmanlık yaptığı tezler hangi konularda?", "TÜBİTAK projeleri neler?", "Hangi firmalarla çalışmış?", "Son yıllarda hangi konulara yöneldi?", "En sık kimlerle çalışıyor?"].map((q) => `<button class="chip" data-ask="${esc(q)}" type="button">${esc(q)}</button>`).join("")}</div>
      <form class="composer" id="askForm"><div class="input">${icon("message")}<input id="question" placeholder="${esc(p.name)} hakkında bir şey sorun…" autocomplete="off"></div>
        <button class="btn primary" id="send" type="submit">${icon("send")}Gönder</button></form>
    </div></div>`);

  mountSlider($("#phSlider"));
  $("#phPhoto").onclick = () => photoPop($("#phPhoto"), links);
  const publicationTable = mountPublicationTable($("#profilePublications"), "pub", "pubs", r.publications, "year", { rowId: "pubs", sourceFor: pubSrc });
  const drawPubs = () => publicationTable.update(r.publications);

  $("#refreshProfileBtn").onclick = () => refreshProfileModal(r);
  bindSourcePicker($("#profileSourcesPicker"), (sources) => runProfileRefresh(r, ["publications"], sources));
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
  loadWos(r, drawPubs);
  if (r.refresh_report?.warnings?.length) {
    const reportKey = `${r.job_id}:${r.refresh_report.at}`;
    if (!refreshNotices.has(reportKey)) { refreshNotices.add(reportKey); toast(esc(r.refresh_report.warnings.join(" ")), 9000); }
  }
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
  openModal(`<div class="pat-modal"><header class="pat-header"><h2>${esc(x.title)}</h2>${x.title_en ? `<div class="faint">${esc(x.title_en)}</div>` : ""}
    <div class="chips"><span class="chip">${esc(x.year || "?")}</span>${x.numbers.map(n => `<span class="chip">${esc(n)}</span>`).join("")}
    ${safeUrl(x.url) ? `<a class="chip" href="${esc(safeUrl(x.url))}" target="_blank" rel="noopener">Espacenet ${icon("external")}</a>` : ""}</div>
    <details class="pat-metadata"><summary>Özet ve başvuru bilgileri</summary><p>${esc(x.applicants.join(" · "))}</p><p>Buluş sahipleri: ${esc(x.inventors.join(", ") || "—")}</p>${x.abstract ? `<div class="abs">${esc(x.abstract)}</div>` : ""}</details></header>
    <div id="patPages"><div class="loading-line"><span class="spinner"></span>Belge EPO'dan alınıyor…</div></div></div>`);
  const box = $("#patPages");
  let d;
  try { d = await api(`/api/patents/document?${x.numbers.map(n => `n=${encodeURIComponent(n)}`).join("&")}`); }
  catch (error) { d = { pages: 0, error: error.message }; }
  if (!box.isConnected || $("#modal").hidden) return;
  if (!d.pages) { box.innerHTML = `<p class="faint">${esc(d.error || "Bu patentin taranmış belgesi EPO'da yok.")}</p>`; return; }
  box.innerHTML = `<div class="pat-toolbar"><button class="btn sm" data-pat-prev aria-label="Önceki sayfa">←</button><label>Sayfa <select class="select" data-pat-page aria-label="Belge sayfası">${Array.from({ length: d.pages }, (_, i) => `<option value="${i + 1}">${i + 1}</option>`).join("")}</select> / ${d.pages}</label><button class="btn sm" data-pat-next aria-label="Sonraki sayfa">→</button><span class="spacer"></span><button class="btn sm" data-pat-minus aria-label="Uzaklaştır">−</button><output>100%</output><button class="btn sm" data-pat-plus aria-label="Yakınlaştır">+</button><button class="btn sm" data-pat-reset>Sayfayı sığdır</button></div><div class="pat-viewport" tabindex="0" aria-label="Patent belgesi; büyüttükten sonra sürükleyerek gezinin"><div class="pat-canvas"><img class="pat-document-image" draggable="false" alt=""><p class="pat-image-error" hidden>Sayfa yüklenemedi. Başka sayfa seçip tekrar deneyebilirsiniz.</p></div></div>`;
  const viewport = $(".pat-viewport", box), picture = $(".pat-document-image", box), selector = $("[data-pat-page]", box);
  let current = 1, zoom = 1, drag = null;
  const fit = () => {
    if (!box.isConnected || !picture.naturalWidth) return;
    const ratio = picture.naturalWidth / picture.naturalHeight;
    const width = Math.max(1, Math.min(viewport.clientWidth - 28, (viewport.clientHeight - 28) * ratio));
    picture.style.width = `${Math.round(width * zoom)}px`;
    $("output", box).textContent = `${Math.round(zoom * 100)}%`;
  };
  const zoomTo = value => {
    const old = zoom; zoom = Math.max(.5, Math.min(4, value));
    const x = viewport.scrollLeft + viewport.clientWidth / 2, y = viewport.scrollTop + viewport.clientHeight / 2;
    fit(); viewport.scrollLeft = x * zoom / old - viewport.clientWidth / 2; viewport.scrollTop = y * zoom / old - viewport.clientHeight / 2;
  };
  const go = value => {
    current = Math.max(1, Math.min(d.pages, Number(value))); selector.value = String(current);
    $("[data-pat-prev]", box).disabled = current === 1; $("[data-pat-next]", box).disabled = current === d.pages;
    picture.hidden = false; $(".pat-image-error", box).hidden = true;
    picture.alt = `Patent belgesi, sayfa ${current}`;
    picture.src = `/api/patents/page/${encodeURIComponent(d.source)}/${current}.png`;
    viewport.scrollTop = 0; viewport.scrollLeft = 0;
  };
  picture.onload = fit;
  picture.onerror = () => { picture.hidden = true; $(".pat-image-error", box).hidden = false; };
  selector.onchange = () => go(selector.value);
  $("[data-pat-prev]", box).onclick = () => go(current - 1);
  $("[data-pat-next]", box).onclick = () => go(current + 1);
  $("[data-pat-minus]", box).onclick = () => zoomTo(zoom - .25);
  $("[data-pat-plus]", box).onclick = () => zoomTo(zoom + .25);
  $("[data-pat-reset]", box).onclick = () => { zoom = 1; fit(); viewport.scrollTop = 0; viewport.scrollLeft = 0; };
  viewport.addEventListener("wheel", event => { if (event.ctrlKey || event.metaKey) { event.preventDefault(); zoomTo(zoom * Math.exp(-event.deltaY * .003)); } }, { passive: false });
  const endDrag = () => {
    if (!drag) return;
    const old = drag; drag = null; old.events.abort(); viewport.classList.remove("panning");
    if (viewport.hasPointerCapture(old.id)) viewport.releasePointerCapture(old.id);
  };
  viewport.addEventListener("pointerdown", event => {
    if (event.button !== 0 || event.isPrimary === false) return;
    endDrag();
    const events = new AbortController(), options = { signal: events.signal };
    drag = { id: event.pointerId, x: event.clientX, y: event.clientY, left: viewport.scrollLeft, top: viewport.scrollTop, events };
    viewport.setPointerCapture(event.pointerId); viewport.classList.add("panning");
    window.addEventListener("pointermove", move => {
      if (!drag || move.pointerId !== drag.id) return;
      if (!viewport.isConnected || (move.pointerType === "mouse" && move.buttons === 0)) { endDrag(); return; }
      move.preventDefault(); viewport.scrollLeft = drag.left - (move.clientX - drag.x); viewport.scrollTop = drag.top - (move.clientY - drag.y);
    }, { ...options, passive: false });
    window.addEventListener("pointerup", endDrag, options); window.addEventListener("pointercancel", endDrag, options); window.addEventListener("blur", endDrag, options);
    document.addEventListener("visibilitychange", () => { if (document.hidden) endDrag(); }, options);
  });
  viewport.addEventListener("lostpointercapture", endDrag);
  const resize = new ResizeObserver(() => { if (!box.isConnected) { resize.disconnect(); endDrag(); } else fit(); }); resize.observe(viewport);
  go(1); hydrateIcons(box);
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
      ${safeUrl(x.pdf) ? `<button class="chip teal" type="button" data-pdf="${esc(safeUrl(x.pdf))}" data-title="${esc(x.title)}">${icon("book")}PDF oku</button>` : ""}</div>
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
  el.innerHTML = `${role === "bot" ? `<span class="chat-orb sm">${icon("sparkle")}</span>` : ""}<div class="bubble">${html}</div>`;
  hydrateIcons(el);
  thread.appendChild(el); thread.scrollTop = thread.scrollHeight;
  return $(".bubble", el);
}
async function ask(question) {
  if (!question || !S.result || S.chatRequest) return;
  const controller = new AbortController(); S.chatRequest = controller;
  $("#send").disabled = true;
  addMsg("user", esc(question));
  const bubble = addMsg("bot", `<div class="answer typing"><span class="typing-dots"><i></i><i></i><i></i></span></div><div class="faint stage">Yanıt hazırlanıyor…</div>`);
  const out = $(".answer", bubble), stage = $(".stage", bubble);
  let text = "", meta = null, failure = "", shown = 0, typer = 0, streamDone = false;
  // Daktilo: gelen metin karakter karakter yazılır, birikirse hızlanır
  const type = () => {
    if (shown < text.length) {
      shown = Math.min(text.length, shown + Math.max(1, Math.ceil((text.length - shown) / 24)));
      out.innerHTML = formatAnswer(text.slice(0, shown)) + '<span class="caret"></span>';
      const th = $("#thread"); if (th) th.scrollTop = 1e9;
    } else if (streamDone) { out.innerHTML = formatAnswer(text); typer = 0; return; }
    typer = requestAnimationFrame(type);
  };
  const timer = setTimeout(() => controller.abort(), 150000);
  try {
    const res = await fetch(`/api/jobs/${S.result.job_id}/chat`, { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, chat_id: S.chatId, mode: "auto" }), signal: controller.signal });
    if (!res.ok) { const e = await res.json().catch(() => ({})); throw new Error(e.detail || `HTTP ${res.status}`); }
    await readSse(res, (m) => {
      if (m.chat_id) S.chatId = m.chat_id;
      if (m.stage) stage.textContent = m.stage;
      if (m.delta) { text += m.delta; stage.textContent = ""; if (!typer) typer = requestAnimationFrame(type); }
      if (m.error) failure = m.error;
      if (m.done) { meta = m.meta; return false; }
    }, controller.signal);
    streamDone = true;
    if (failure) throw new Error(failure);
    if (typer) await new Promise((res) => { const w = () => (typer ? requestAnimationFrame(w) : res()); w(); });
    if (meta) out.insertAdjacentHTML("afterend", metaLine(meta));
  } catch (e) {
    streamDone = true; cancelAnimationFrame(typer); typer = 0;
    out.innerHTML = text ? formatAnswer(text) : "Cevap alınamadı.";
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
  if (wos?.status === "skipped") return "";
  if (!wos) return "";
  const count = wos.total == null ? `${fmtNum(wos.checked || 0)} kayıt incelendi` : `${fmtNum(wos.total)} kayıttan ${fmtNum(wos.checked || 0)} kayıt incelendi`;
  const state = { pending: "WoS sırası bekleniyor", running: "WoS taranıyor", done: "WoS taraması tamamlandı", partial: "WoS kısmi sonuç", blocked: "WoS erişimi sağlanamadı", error: "WoS taraması tamamlanamadı" }[wos.status] || "WoS";
  const reason = { record_limit: `Tarama ilk ${wos.limit || 20} kayıtla sınırlı.`, time_budget: "Tarama süresi doldu.", queue_timeout: "Tarama sırası için bekleme süresi doldu.", results_not_fully_loaded: "WoS sonuçlarının bir bölümü yüklenemedi.", access_unavailable: "Diğer kaynaklardan alınan yayınlar gösteriliyor." }[wos.reason] || "";
  return `${["pending", "running"].includes(wos.status) ? '<span class="spinner"></span>' : ""}${esc(state)} · ${esc(count)}${reason ? ` · ${esc(reason)}` : ""}`;
}
// =================================================================== KONULAR: raflar, okuma köşesi, PDF okuyucu
const RECENT_PAPERS_KEY = "academic-recent-papers";
function readRecentPapers() {
  try { const v = JSON.parse(localStorage.getItem(RECENT_PAPERS_KEY) || "[]"); return Array.isArray(v) ? v.filter((x) => x && typeof x.title === "string" && x.title) : []; } catch { return []; }
}
function rememberPaper(p) {
  if (!p?.title) return;
  const keep = { title: p.title, year: p.year || "", venue: p.venue || "", doi: p.doi || "", url: p.url || "", authors: (p.authors || []).slice(0, 6),
    source: p.source || "", sources: p.sources || [], citations: p.citations ?? null, id: p.id || "", at: Date.now() };
  const list = [keep, ...readRecentPapers().filter((x) => fold(x.title) !== fold(p.title))].slice(0, 24);
  try { localStorage.setItem(RECENT_PAPERS_KEY, JSON.stringify(list)); } catch { /* tarayıcı depolaması kapalı olabilir */ }
}
// Kitaplık: dört raflı, ayaklı bir dolap. Kitaplar sırtı dışarıda duran gerçek 3B kutulardır (sırt, kapak, arka
// kapak, sayfa yüzü). Üzerine gelince raftan çekilir; tıklanınca dolaptan çıkıp kapağını göstererek ortaya gelir ve
// modal kitabın kapağından büyüyerek açılır. Kapanınca modal raftaki boş yerine geri küçülür, kitap yerine döner.
const TOME_COLORS = ["#1f3a5f", "#6b2232", "#2f4f3e", "#3b3f47", "#7a5a2b", "#2b5d6b", "#4f3a66", "#8a3b2a", "#24414d", "#5c4a3a"];
const tomeSeed = (text) => { let h = 0; for (const ch of String(text)) h = (h * 31 + ch.charCodeAt(0)) >>> 0; return h; };
const SHELF = { papers: [], topics: [], trending: [], reading: [] };
const SHELF_META = {
  papers: ["clock", "Son okuduklarım", "Açtığın makaleler; tıkla, kaldığın yerden oku."],
  topics: ["search", "Son konularım", "Araştırdığın konular; tıkla, konunun öne çıkan yayınları açılsın."],
  trending: ["flame", "Türkiye gündemi", "Türkiye adresli yayınlarda son 12 ayda en hızlı büyüyen konular (OpenAlex)."],
  reading: ["book", "Okuma köşesi", "Alan seç: Türkiye'den, açık erişimli, son iki yılın en çok atıf alan yayınları."],
};

function tomeHtml({ title, kicker = "", sub = "", badge = "", ic = "", data = "", kind = "", thick = 0 }) {
  const seed = tomeSeed(title);
  const t = thick || Math.round(Math.min(54, Math.max(kind === "trend" ? 42 : 30, 24 + title.length * .42)));
  const tip = [kicker, sub].filter(Boolean).join(" · ");
  return `<button type="button" class="tome ${kind}" style="--t:${t}px;--hh:${80 + (seed % 17)};--c:${TOME_COLORS[seed % TOME_COLORS.length]}" data-band="${seed % 3}" ${data} data-tip="${esc(title)}" data-tip-sub="${esc(tip)}" aria-label="${esc(title + (tip ? ` — ${tip}` : ""))}">
    <span class="tome-3d">
      <span class="tome-spine">${ic ? `<span class="tome-ic">${icon(ic)}</span>` : ""}<span class="tome-title">${esc(title)}</span>${badge ? `<i class="tome-badge">${esc(badge)}</i>` : ""}</span>
      <span class="tome-cover">${ic ? `<span class="tome-cover-ic">${icon(ic)}</span>` : ""}${kicker ? `<small>${esc(kicker)}</small>` : ""}<b>${esc(title)}</b>${sub ? `<em>${esc(sub)}</em>` : ""}</span>
      <span class="tome-back" aria-hidden="true"></span><span class="tome-top" aria-hidden="true"></span>
    </span></button>`;
}
function ghostTomes(text) {
  const w = [34, 46, 30, 40, 52, 36];
  return w.map((t, i) => `<span class="tome ghost" style="--t:${t}px;--hh:${82 + (i * 5) % 14}" aria-hidden="true"></span>`).join("") + `<p class="bc-empty">${esc(text)}</p>`;
}
function caseShelfHtml(id) {
  const [ic, title, hint] = SHELF_META[id];
  return `<section class="bc-shelf" data-shelf="${id}" aria-label="${esc(title)}">
    <div class="bc-row"><div class="bc-loading"><span class="spinner"></span></div></div>
    <div class="bc-board"><button type="button" class="bc-plate" data-shelf-all="${id}" title="${esc(hint)}">${icon(ic)}<span>${esc(title)}</span><b class="bc-count"></b></button></div></section>`;
}
function bookcaseHtml() {
  return `<div class="bookcase" id="bookcase">
    <div class="bc-crown" aria-hidden="true"></div>
    <div class="bc-body">${Object.keys(SHELF_META).map(caseShelfHtml).join("")}</div>
    <div class="bc-plinth" aria-hidden="true"><i></i><i></i></div>
    <div class="bc-tip" role="tooltip" hidden><b></b><span></span></div></div>`;
}
// Rafa sığmayan kitaplar gizlenir (yatay kaydırma yok); levhada toplam ve sığmayan sayısı yazar, levha tüm rafı açar.
function fitShelf(row) {
  const tomes = $$(".tome:not(.ghost)", row), count = $(".bc-count", row.closest(".bc-shelf"));
  let over = false, hidden = 0;
  tomes.forEach((t) => { t.hidden = false; });
  const limit = row.clientWidth - 12;
  tomes.forEach((t) => { if (over || t.offsetLeft + t.offsetWidth > limit) { t.hidden = true; over = true; hidden++; } });
  if (count) count.textContent = tomes.length ? (hidden ? `${tomes.length} · tümü` : `${tomes.length}`) : "";
}
function fillShelf(host, id, items, emptyText) {
  const row = $(`[data-shelf="${id}"] .bc-row`, host);
  if (!row) return;
  row.innerHTML = items.length ? items.join("") : ghostTomes(emptyText);
  hydrateIcons(row);
  fitShelf(row);
  if (!calmMotion()) $$(".tome:not([hidden])", row).forEach((b, j) => b.animate([{ opacity: 0, transform: "translate3d(48px, 0, 0) rotate(5deg)" }, { opacity: 1, transform: "none" }],
    { duration: 520, delay: 60 + j * 32, easing: "cubic-bezier(.2,.8,.2,1)", fill: "backwards" }));
}
function bindBookcase(bc) {
  const tip = $(".bc-tip", bc);
  const hide = () => { tip.hidden = true; };
  const show = (t) => {
    if (!t || t.classList.contains("ghost") || t.classList.contains("opening")) { hide(); return; }
    $("b", tip).textContent = t.dataset.tip;
    $("span", tip).textContent = t.dataset.tipSub || ""; $("span", tip).hidden = !t.dataset.tipSub;
    tip.hidden = false;
    const c = bc.getBoundingClientRect(), r = t.getBoundingClientRect(), half = Math.min(140, c.width / 2);
    tip.style.left = `${Math.min(Math.max(r.left + r.width / 2 - c.left, half), c.width - half)}px`;
    tip.style.top = `${r.top - c.top - 12}px`;
  };
  bc.addEventListener("pointerover", (e) => show(e.target.closest(".tome")));
  bc.addEventListener("pointerleave", hide);
  bc.addEventListener("focusin", (e) => show(e.target.closest(".tome")));
  bc.addEventListener("focusout", hide);
  let frame = 0;
  const ro = new ResizeObserver(() => {
    if (!bc.isConnected) { ro.disconnect(); return; }
    cancelAnimationFrame(frame); frame = requestAnimationFrame(() => $$(".bc-row", bc).forEach(fitShelf));
  });
  ro.observe(bc);
}
async function renderShelves(host) {
  host.innerHTML = bookcaseHtml(); hydrateIcons(host);
  const bc = $("#bookcase", host);
  bindBookcase(bc);
  if (!calmMotion()) {
    // Dolap yandan dönerek gelir, raflar yukarıdan aşağı sırayla dolar
    bc.animate([{ opacity: 0, transform: "perspective(1800px) rotateY(-26deg) translateX(-5%)" }, { opacity: 1, transform: "perspective(1800px) rotateY(0deg) translateX(0)" }],
      { duration: 900, easing: "cubic-bezier(.16,.84,.24,1)" });
    $$(".bc-shelf", bc).forEach((s, i) => s.animate([{ opacity: 0, transform: "translateY(12px)" }, { opacity: 1, transform: "none" }], { duration: 440, delay: 240 + i * 120, easing: EASE, fill: "backwards" }));
  }
  SHELF.papers = readRecentPapers();
  SHELF.topics = readRecentVisits().filter((v) => v.kind === "topic").slice(0, 24);
  fillShelf(bc, "papers", SHELF.papers.map((p, i) => tomeHtml({ title: p.title, kicker: [p.year, p.venue].filter(Boolean).join(" · "), sub: (p.authors || []).slice(0, 2).join(", "), data: `data-book-paper="${i}"`, kind: "paper" })),
    "Henüz makale açmadın. Bir konu kitabını aç; okuduğun makaleler bu rafa dizilir.");
  fillShelf(bc, "topics", SHELF.topics.map((t, i) => tomeHtml({ title: t.name, kicker: "Aradığın konu", data: `data-book-topic="${i}"`, kind: "topic" })),
    "Konu bulucuda aradığın konular bu rafa dizilir.");
  api("/api/topics/trending", { quiet: true }).then((d) => {
    SHELF.trending = d.items || [];
    fillShelf(bc, "trending", SHELF.trending.map((t, i) => tomeHtml({ title: t.name_tr || t.name, kicker: `${fmtNum(t.count)} yayın · geçen yıl ${fmtNum(t.prev)}`, badge: `+%${t.growth}`, data: `data-book-trend="${i}"`, kind: "trend" })),
      "Gündem şu an hesaplanamadı.");
  }).catch((e) => fillShelf(bc, "trending", [], e.message));
  api("/api/reading", { quiet: true }).then((d) => {
    SHELF.reading = d.items || [];
    fillShelf(bc, "reading", SHELF.reading.map((c) => tomeHtml({ title: c.label, ic: c.icon, kicker: "Okuma köşesi", sub: "Açık erişimli, çok atıf alan yayınlar", data: `data-book-cat="${esc(c.id)}"`, kind: "cat", thick: 58 })), "Okuma köşesi yüklenemedi.");
  }).catch((e) => fillShelf(bc, "reading", [], e.message));
}
// Kitap dolaptan çıkar: önce raftan çekilir, sonra dönerek kapağını gösterir ve ekranın ortasına gelir
async function pullTome(tome) {
  if (calmMotion() || !tome.isConnected) return null;
  const r = tome.getBoundingClientRect(), row = tome.closest(".bc-row");
  const fly = document.createElement("div");
  fly.className = "tome-fly";
  fly.dataset.band = tome.dataset.band;
  fly.innerHTML = tome.innerHTML;
  fly.style.cssText = `${tome.style.cssText};--sh:${row?.clientHeight || r.height}px;left:${r.left}px;top:${r.top}px;width:${r.width}px;height:${r.height}px`;
  document.body.appendChild(fly);
  tome.classList.add("opening");
  $(".bc-tip")?.setAttribute("hidden", "");
  const scale = Math.min(2.8, Math.max(1.4, innerHeight * .44 / r.height));
  const dx = innerWidth / 2 - (r.left + r.width / 2), dy = innerHeight / 2 - (r.top + r.height / 2);
  const ease = "cubic-bezier(.3,.7,.2,1)", duration = 680;
  const move = fly.animate([{ transform: "none" }, { transform: "translate3d(0, -12px, 0) scale(1.05)", offset: .28 }, { transform: `translate3d(${dx}px, ${dy}px, 0) scale(${scale})` }], { duration, easing: ease, fill: "forwards" });
  $(".tome-3d", fly).animate([{ transform: "translateZ(calc(var(--d) / -2))" }, { transform: "translateZ(calc(var(--d) / -2 + 70px)) rotateY(-22deg)", offset: .28 },
    { transform: "translateZ(calc(var(--t) / -2)) rotateY(-90deg)" }], { duration, easing: ease, fill: "forwards" });
  await move.finished.catch(() => {});
  return fly;
}
async function fromShelf(tome, open) {
  const fly = await pullTome(tome);
  const cover = fly && $(".tome-cover", fly);
  if (cover) { modalTap = cover; modalTapAt = performance.now(); }
  try { open(); } catch (err) { console.error(err); }
  if (!fly) return;
  if (modalOrigin === cover) { cover.classList.remove("opening"); modalOrigin = tome; }  // kapanınca raftaki yerine küçülür
  if ($("#modal").hidden) tome.classList.remove("opening");
  fly.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 280, delay: 140, fill: "forwards" }).finished.then(() => fly.remove(), () => fly.remove());
}
function swapModal() {
  if (!calmMotion()) $("#modalBody").animate([{ opacity: 0, transform: "translateX(18px)" }, { opacity: 1, transform: "none" }], { duration: 320, easing: EASE });
}
function readingItemHtml(x) {
  const id = reg({ title: x.title, year: x.year, venue: x.venue, doi: x.doi, url: x.url, authors: x.authors, citations: x.citations, source: "openalex", sources: ["openalex"] }, {});
  return `<article class="read-item"><div><b class="read-title" data-open="${id}">${esc(x.title)}</b>
      <p>${esc(x.authors.join(", "))}${x.institutions.length ? ` · <span class="faint">${esc(x.institutions.join(", "))}</span>` : ""}</p>
      <div class="chips"><span class="chip">${esc(x.year || "")}</span>${x.venue ? `<span class="chip">${esc(x.venue)}</span>` : ""}<span class="chip teal">${fmtNum(x.citations)} atıf</span>${x.topic ? `<span class="chip blue">${esc(x.topic)}</span>` : ""}</div></div>
    <div class="read-actions">${x.pdf || x.doi ? `<button class="btn sm primary" type="button" data-pdf="${esc(safeUrl(x.pdf) || "")}" data-doi="${esc(x.doi)}" data-title="${esc(x.title)}">${icon("book")}Oku</button>` : ""}
      ${safeUrl(x.url) ? `<a class="btn sm" href="${esc(safeUrl(x.url))}" target="_blank" rel="noopener">${icon("external")}Kaynak</a>` : ""}</div></article>`;
}
function readingModalHtml(ic, title, sub, foot = "") {
  return `<div class="reading-modal"><header class="reading-head"><span class="reading-ic">${icon(ic)}</span><div><h2>${esc(title)}</h2><p class="muted">${sub}</p></div></header>
    <div class="reading-list"><div class="loading-line"><span class="spinner"></span>Kitap açılıyor…</div></div>${foot}</div>`;
}
async function fillReadingList(url, emptyTitle, note = (d) => "") {
  const list = $(".reading-list");
  try {
    const d = await api(url, { quiet: true });
    if (!list?.isConnected) return null;
    list.innerHTML = (note(d) ? `<p class="notice">${icon("info")}<span>${esc(note(d))}</span></p>` : "")
      + (d.items.map(readingItemHtml).join("") || emptyState("book", emptyTitle, "Konu bulucuda bütün kaynaklarda aramayı dene."));
    hydrateIcons(list);
    if (!calmMotion()) $$(".read-item", list).slice(0, 10).forEach((el, i) => el.animate([{ opacity: 0, transform: "translateY(10px)" }, { opacity: 1, transform: "none" }], { duration: 340, delay: 160 + i * 45, easing: EASE, fill: "backwards" }));
    return d;
  } catch (e) { if (list?.isConnected) list.innerHTML = `<p class="notice warn">${esc(e.message)}</p>`; return null; }
}
async function openReadingShelf(cat, label) {
  openModal(readingModalHtml("book", label || "Okuma köşesi", "Türkiye adresli, açık erişimli, son iki yılın en çok atıf alan yayınları · OpenAlex"));
  const d = await fillReadingList(`/api/reading/${encodeURIComponent(cat)}`, "Bu rafta yayın yok");
  if (d?.icon && $(".reading-ic")) $(".reading-ic").innerHTML = icon(d.icon);
}
// Konu kitabı: konu bulucuya gitmeden konunun öne çıkan yayınları modalda listelenir
async function openTopicShelf(t) {
  const sub = t.trend ? `Son 12 ayda ${fmtNum(t.trend.count)} yayın (geçen yıl ${fmtNum(t.trend.prev)}, +%${t.trend.growth})${t.name && t.name !== t.label ? ` · ${esc(t.name)}` : ""} · OpenAlex`
    : "Konunun en çok atıf alan güncel yayınları · OpenAlex";
  openModal(readingModalHtml(t.trend ? "flame" : "search", t.label, sub,
    `<footer class="reading-foot"><span class="muted">Daha geniş tarama için Crossref, TR Dizin, OpenAIRE ve diğer kaynaklar da aranabilir.</span><button class="btn" type="button" data-finder="${esc(t.q || t.label)}">${icon("search")}Bütün kaynaklarda ara</button></footer>`));
  await fillReadingList(t.id ? `/api/topic-works?id=${encodeURIComponent(t.id)}` : `/api/topic-works?q=${encodeURIComponent(t.q)}`, "Bu konuda yayın bulunamadı",
    (d) => d.scope === "world" ? "Türkiye adresli yayın az olduğu için dünya genelinden en çok atıf alanlar gösteriliyor." : "");
}
// Raf levhası: o raftaki bütün kitaplar
function openShelfAll(id) {
  const [ic, title] = SHELF_META[id], items = SHELF[id] || [];
  const row = (i, main, sub, extra = "") => `<button class="sa-item" type="button" data-sa="${id}" data-i="${i}"><span class="sa-spine" style="--c:${TOME_COLORS[tomeSeed(main) % TOME_COLORS.length]}"></span><span class="sa-text"><b>${esc(main)}</b>${sub ? `<span>${esc(sub)}</span>` : ""}</span>${extra}</button>`;
  const max = Math.max(1, ...items.map((t) => t.count || 0));
  const body = {
    papers: () => items.map((p, i) => row(i, p.title, [p.year, p.venue, (p.authors || []).slice(0, 2).join(", ")].filter(Boolean).join(" · "))),
    topics: () => items.map((t, i) => row(i, t.name, new Date(t.at).toLocaleDateString("tr-TR"))),
    trending: () => items.map((t, i) => row(i, t.name_tr || t.name, `${fmtNum(t.count)} yayın · geçen yıl ${fmtNum(t.prev)}`, `<span class="sa-bar"><i style="width:${Math.round((t.count || 0) / max * 100)}%"></i></span><em class="sa-growth">+%${t.growth}</em>`)),
    reading: () => items.map((c, i) => row(i, c.label, "Açık erişimli, çok atıf alan yayınlar", `<span class="sa-ic">${icon(c.icon)}</span>`)),
  }[id]().join("");
  openModal(`<div class="reading-modal"><header class="reading-head"><span class="reading-ic">${icon(ic)}</span><div><h2>${esc(title)}</h2><p class="muted">${items.length} kitap · ${esc(SHELF_META[id][2])}</p></div></header>
    <div class="sa-list">${body || emptyState("book", "Bu raf boş", "")}</div></div>`);
  if (!calmMotion()) $$(".sa-item").slice(0, 14).forEach((el, i) => el.animate([{ opacity: 0, transform: "translateX(-12px)" }, { opacity: 1, transform: "none" }], { duration: 300, delay: 180 + i * 35, easing: EASE, fill: "backwards" }));
}
function openShelfItem(kind, x) {
  if (kind === "papers") openPaper(reg(x, {}));
  else if (kind === "topics") openTopicShelf({ q: x.name, label: x.name });
  else if (kind === "trending") openTopicShelf({ id: x.id, name: x.name, label: x.name_tr || x.name, trend: x });
  else if (kind === "reading") openReadingShelf(x.id, x.label);
}
document.addEventListener("click", (e) => {
  const tome = e.target.closest(".tome:not(.ghost)");
  if (tome) {
    e.preventDefault();
    const d = tome.dataset;
    const [kind, i] = d.bookPaper != null ? ["papers", d.bookPaper] : d.bookTopic != null ? ["topics", d.bookTopic] : d.bookTrend != null ? ["trending", d.bookTrend] : ["reading", null];
    const x = kind === "reading" ? SHELF.reading.find((c) => c.id === d.bookCat) : SHELF[kind][+i];
    if (x) fromShelf(tome, () => openShelfItem(kind, x));
    return;
  }
  const plate = e.target.closest("[data-shelf-all]");
  if (plate) { e.preventDefault(); openShelfAll(plate.dataset.shelfAll); return; }
  const sa = e.target.closest("[data-sa]");
  if (sa) { const x = SHELF[sa.dataset.sa]?.[+sa.dataset.i]; if (x) { openShelfItem(sa.dataset.sa, x); swapModal(); } return; }
  const finder = e.target.closest("[data-finder]");
  if (finder) { const q = finder.dataset.finder; closeModal(); location.hash = `#/ara?q=${encodeURIComponent(q)}`; return; }
  const pdfBtn = e.target.closest("[data-pdf]");
  if (pdfBtn) { e.preventDefault(); openPdfReader(pdfBtn.dataset.pdf || "", pdfBtn.dataset.doi || "", pdfBtn.dataset.title || "PDF"); }
});
// Uygulama içi PDF okuyucu: kitap gibi soldan açılır; kapalı PDF'te açık erişim kopyası aranır
async function openPdfReader(url, doi, title) {
  const layer = document.createElement("div");
  layer.className = "pdf-layer";
  layer.innerHTML = `<div class="pdf-scrim"></div><section class="pdf-reader" role="dialog" aria-modal="true" aria-label="PDF okuyucu">
    <header><span class="pdf-ic">${icon("book")}</span><b>${esc(title)}</b><span class="spacer"></span><a class="btn sm" target="_blank" rel="noopener" data-pdf-ext hidden>${icon("external")}Yeni sekmede aç</a>
      <button class="icon-btn" type="button" data-pdf-close aria-label="Kapat">${icon("x")}</button></header>
    <div class="pdf-body"><div class="loading-line"><span class="spinner"></span>PDF açılıyor; yayıncı kapattıysa açık erişim kopyası aranıyor…</div></div></section>`;
  document.body.appendChild(layer); hydrateIcons(layer);
  const reader = $(".pdf-reader", layer), body = $(".pdf-body", layer);
  let objectUrl = "";
  if (!calmMotion()) {
    $(".pdf-scrim", layer).animate([{ opacity: 0 }, { opacity: 1 }], { duration: 360, easing: "ease-out" });
    reader.animate([{ transformOrigin: "0% 50%", transform: "perspective(1800px) rotateY(-80deg)", opacity: 0 }, { transformOrigin: "0% 50%", transform: "perspective(1800px) rotateY(6deg)", opacity: 1, offset: .75 }, { transformOrigin: "0% 50%", transform: "none", opacity: 1 }], { duration: 760, easing: "cubic-bezier(.2,.8,.2,1)" });
  }
  const close = () => {
    document.removeEventListener("keydown", onKey, true);
    const done = () => { if (objectUrl) URL.revokeObjectURL(objectUrl); layer.remove(); };
    if (calmMotion()) { done(); return; }
    $(".pdf-scrim", layer).animate([{ opacity: 1 }, { opacity: 0 }], { duration: 320, fill: "forwards" });
    reader.animate([{ transformOrigin: "0% 50%", transform: "none", opacity: 1 }, { transformOrigin: "0% 50%", transform: "perspective(1800px) rotateY(-80deg)", opacity: 0 }], { duration: 420, easing: "cubic-bezier(.5,0,.8,.4)", fill: "forwards" }).finished.then(done, done);
  };
  // Esc yalnız okuyucuyu kapatır; arkadaki modal açık kalır
  const onKey = (e) => { if (e.key === "Escape") { e.stopImmediatePropagation(); e.preventDefault(); close(); } };
  document.addEventListener("keydown", onKey, true);
  layer.addEventListener("click", (e) => { if (e.target.closest("[data-pdf-close]") || e.target.classList.contains("pdf-scrim")) close(); });
  try {
    const res = await fetch(`/api/pdf?url=${encodeURIComponent(url)}&doi=${encodeURIComponent(doi)}`);
    if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.detail || `HTTP ${res.status}`); }
    const source = res.headers.get("X-Source-Url") || url;
    objectUrl = URL.createObjectURL(await res.blob());
    if (!layer.isConnected) { URL.revokeObjectURL(objectUrl); return; }
    body.innerHTML = `<iframe class="pdf-frame" src="${objectUrl}" title="${esc(title)}"></iframe>`;
    const ext = $("[data-pdf-ext]", layer); if (safeUrl(source)) { ext.href = safeUrl(source); ext.hidden = false; }
  } catch (e) {
    if (!layer.isConnected) return;
    const landing = safeUrl(url) || (doi ? `https://doi.org/${doi}` : "");
    body.innerHTML = `<div class="pdf-fail">${icon("info")}<h3>PDF açılamadı</h3><p>${esc(e.message)}</p>${landing ? `<a class="btn primary" href="${esc(landing)}" target="_blank" rel="noopener">${icon("external")}Yayıncı sayfasına git</a>` : ""}</div>`;
    hydrateIcons(body);
  }
}
// Makale modalı: yazarlar ve kurumları tıklanabilir (profil / üniversite sayfası)
async function loadPaperAuthors(p) {
  const host = $("#mAuthors");
  if (!host || !p.doi) return;
  try {
    const d = await api(`/api/paper/authors?doi=${encodeURIComponent(p.doi)}`, { quiet: true });
    if (!host.isConnected || !d.items.length) return;
    const tr = (a) => a.institutions.some((i) => i.country === "TR") ? 0 : 1;
    const items = d.items.map((a, i) => ({ ...a, i })).sort((x, y) => tr(x) - tr(y) || x.i - y.i), more = Math.max(0, items.length - 8);
    host.innerHTML = `<div class="m-h">Yazarlar ve kurumları <small class="faint">${items.length} yazar${items.some((x) => !tr(x)) ? " · Türkiye adresliler önde" : ""}</small></div><div class="m-authors">${items.map((a, n) => {
      const c = chatByName(a.name);
      const href = c ? `#/profil/${encodeURIComponent(c.id)}` : `#/akademisyenler?q=${encodeURIComponent(a.name)}`;
      const insts = a.institutions.map((i) => i.uni_id ? `<a class="m-inst tr" href="#/universite/${esc(i.uni_id)}" data-close-modal>${organizationLogo("universities", i.uni_id, i.name, "m-inst-logo")}${esc(i.name)}</a>`
        : `<span class="m-inst">${esc(i.name)}${i.country ? ` <small>${esc(i.country)}</small>` : ""}</span>`).join("");
      return `<div class="m-author"${n >= 8 ? " hidden" : ""}><a class="m-author-name" href="${esc(href)}" data-close-modal title="${c ? "Profili aç" : "YÖK'te ara"}">${avatar(a.name, c ? profilePhoto(c) : "", "av m-av")}<span>${esc(a.name)}</span>${c ? `<i class="chip teal">profil</i>` : ""}</a>${insts ? `<div class="m-insts">${insts}</div>` : ""}</div>`; }).join("")}${more ? `<button class="link m-more" type="button">+${more} yazarın tümünü göster</button>` : ""}</div>`;
    hydrateIcons(host);
    $(".m-more", host)?.addEventListener("click", (e) => { $$(".m-author[hidden]", host).forEach((x) => { x.hidden = false; }); e.currentTarget.remove(); });
    $$("[data-close-modal]", host).forEach((a) => a.addEventListener("click", () => closeModal()));
  } catch { /* yazar bilgisi isteğe bağlı */ }
}

async function viewSearch(q, requestedSources = "") {
  let selected = requestedSources ? requestedSources.split(",").filter((key) => TOPIC_SOURCES.includes(key)) : null;
  if (!selected?.length) { try { selected = JSON.parse(localStorage.getItem("topic-sources")); } catch { /* tercih */ } }
  if (!Array.isArray(selected) || !selected.filter((key) => TOPIC_SOURCES.includes(key)).length) selected = [...TOPIC_SOURCES];
  selected = selected.filter((key) => TOPIC_SOURCES.includes(key));
  setCrumbs([{ label: "Ana sayfa", href: "#/" }, { label: "Konu bul" }]);
  setView(`<div class="section-head"><div><h1>Konu bul</h1><p>${q ? "OpenAlex, Crossref, Semantic Scholar, TR Dizin, OpenAIRE ve WoS kayıtları kaynaklarıyla birleştirilir." : "Bir konu yaz; Türkçe yazdığın konu İngilizceye de çevrilerek bütün kaynaklarda aranır, yayınlar tek listede gelir."}</p></div>${q ? `<a class="btn sm" href="#/ara">${icon("arrow")}Yeni arama</a>` : ""}</div>
    <form class="card quick-search" id="searchForm" style="margin-top:0">
      <div class="input">${icon("search")}<input id="sInput" value="${esc(q)}" placeholder="ör. göğüs hastalıkları, makine öğrenmesi, deprem mühendisliği"></div>
      ${sourcePicker("topicSourcePicker", TOPIC_SOURCES, selected)}<button class="btn primary" type="submit">Ara</button></form>
    <div id="sResults" style="margin-top:18px"></div>
    ${q ? "" : `<div id="shelves"></div>`}`);
  const search = () => {
    const value = $("#sInput").value.trim();
    if (value.length < 3) return;
    const hash = `#/ara?q=${encodeURIComponent(value)}&sources=${selected.join(",")}`;
    if (location.hash === hash) viewSearch(value, selected.join(",")); else location.hash = hash;
  };
  bindSourcePicker($("#topicSourcePicker"), (sources) => {
    selected = sources;
    try { localStorage.setItem("topic-sources", JSON.stringify(sources)); } catch { /* tercih */ }
    search();
  });
  $("#searchForm").addEventListener("submit", (e) => { e.preventDefault(); search(); });
  const box = $("#sResults"), routeHash = location.hash;
  if (!q) { renderAgenda($("#shelves")); return; }
  box.innerHTML = `<div id="topicSources" class="src-status"></div><div id="topicProgress" class="loading-line" role="status" aria-live="polite"><span class="spinner"></span>Akademik kaynaklar taranıyor…</div><div id="topicError"></div><div id="topicTable"></div>`;
  const active = () => box.isConnected && location.hash === routeHash;
  S.listMeta.search = { file: `arama ${q}` };
  const table = mountPublicationTable($("#topicTable"), "s", "search", [], "rel");
  let revision;
  const apply = (r) => {
    rememberVisit("topic", q, q, { sources: selected.join(",") });
    $("#topicSources").innerHTML = Object.entries(r.sources || {}).map(([source, value]) => `<span class="chip ${typeof value === "number" ? "teal" : "gold"}">${esc(SRC_TR[sourceKey(source)] || source)}: ${typeof value === "number" ? fmtNum(value) + " sonuç" : esc(value)}</span>`).join("")
      + (r.english ? `<span class="chip blue">EN: ${esc(r.english)}</span>` : "") + (r.elapsed != null ? `<span class="chip">${esc(r.elapsed)} sn</span>` : "");
    $("#topicProgress").innerHTML = topicProgress(r.wos);
    if (["pending", "running"].includes(r.wos?.status)) document.dispatchEvent(new Event("wos-work-requested"));
    const next = r.revision ?? JSON.stringify(r.papers || []);
    if (next !== revision) { revision = next; table.update(r.papers || []); }
  };
  try {
    await pollSnapshots(() => api(`/api/search?q=${encodeURIComponent(q)}&sources=${selected.join(",")}`), active, apply,
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
  const seq = S.routeSeq;
  setCrumbs([{ label: "Ana sayfa", href: "#/" }, { label: "Kütüphanem" }]);
  await loadFav();
  const papers = [...S.fav.papers].reverse(), people = [...S.fav.people].reverse();
  const tabs = [["papers", "Makaleler", "book"], ["people", "Akademisyenler", "users"], ["universities", "Üniversiteler", "building"], ["firms", "Firmalar", "briefcase"]];
  if (!tabs.some(([id]) => id === tab)) tab = "papers";
  S.lists.fav = papers;
  S.listMeta.fav = { file: "favori makaleler" };
  const institutions = (kind) => {
    const items = [...(S.fav[kind] || [])].reverse(), university = kind === "universities";
    return items.length ? `<div class="library-org-grid">${items.map((item) => `<article class="card library-org-card">${organizationLogo(kind, item.id, item.name)}<div><h3><a href="#/${university ? "universite" : "firma"}/${esc(item.id)}">${esc(item.name)}</a></h3><p>${esc(university ? "Fakülteler, akademisyenler ve öğrenci rehberi" : (item.sectors || []).join(" · "))}</p>${!university && item.cities?.length ? `<span class="faint">${esc(item.cities.join(", "))}</span>` : ""}</div>${organizationSaveButton(kind, item.id)}</article>`).join("")}</div>`
      : `<div class="card">${emptyState(university ? "building" : "briefcase", university ? "Üniversitelerini burada biriktir" : "İlgilendiğin firmaları kaydet", "Kurum sayfasındaki “Kaydet” düğmesiyle kütüphanene ekleyebilirsin.", `<a class="btn sm" href="#/${university ? "universiteler" : "firmalar"}">Keşfet ${icon("arrow")}</a>`)}</div>`;
  };
  setView(`<div class="section-head"><div><span class="eyebrow">KİŞİSEL ARAŞTIRMA ALANIN</span><h1>Kütüphanem</h1><p>Yayınların, akademisyenlerin, üniversitelerin ve firmaların bir arada.</p></div><div class="actions">${papers.length ? exportButtons("fav") : ""}</div></div>
    <div class="tabs library-tabs" role="tablist">${tabs.map(([id, label, ic]) => `<button class="tab ${tab === id ? "active" : ""}" data-tab="${id}" type="button">${icon(ic)}${label}<span class="n">${(S.fav[id] || []).length}</span></button>`).join("")}</div>
    <div class="panel ${tab === "papers" ? "active" : ""}" data-panel="papers"><div class="card">${papers.length ? `<div class="stagger">${papers.map((p, i) => paperCard(p, p.job_id && p.pid ? { jid: p.job_id, pid: p.pid, person: p.person } : {}, i)).join("")}</div>` : emptyState("bookmark", "İlk yayınını kaydet", "Yayınların yanındaki yıldızla araştırma kütüphaneni oluştur.", '<a class="btn sm" href="#/ara">Yayın keşfet →</a>')}</div></div>
    <div class="panel ${tab === "people" ? "active" : ""}" data-panel="people">${people.length ? `<div class="collabs stagger">${people.map((p, i) => `<div class="collab" style="--i:${i}">${avatar(p.name, p.photo)}<div class="c-main"><div class="c-title">${esc(p.title || "")}</div><b><a href="#/profil/${esc(p.chat_id || "")}">${esc(p.name)}</a></b><span>${esc(p.institution || "")}</span><span class="faint">${esc(p.department || "")}</span><div class="chips" style="margin-top:8px"><span class="chip">${fmtNum(p.papers)} yayın</span><button class="chip" data-unfav="${esc(p.key)}" type="button">${icon("x")}Çıkar</button></div></div></div>`).join("")}</div>` : `<div class="card">${emptyState("users", "Takip ettiğin akademisyenler", "Profil sayfasındaki “Favorilere ekle” düğmesiyle buraya kaydet.")}</div>`}</div>
    <div class="panel ${tab === "universities" ? "active" : ""}" data-panel="universities">${institutions("universities")}</div>
    <div class="panel ${tab === "firms" ? "active" : ""}" data-panel="firms">${institutions("firms")}</div>`);
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
// ------------------------------------------------------------ firma künyesi (önizleme modalı + Genel bakış sekmesi)
function firmMoney(r) {
  if (!r) return "";
  if (r.text) return r.text;
  const v = r.value, unit = r.currency || "";
  const s = v >= 1e9 ? `${(v / 1e9).toLocaleString("tr-TR", { maximumFractionDigits: 1 })} milyar` : v >= 1e6 ? `${(v / 1e6).toLocaleString("tr-TR", { maximumFractionDigits: 1 })} milyon` : fmtNum(v);
  return `${s} ${unit}${r.year ? ` (${r.year})` : ""}`.trim();
}
function firmFactsHtml(f, { compact = false } = {}) {
  const id = f.identity || {}, l = f.local || {};
  const stat = (v, label, extra = "") => `<div><b>${v == null || v === "" ? "—" : typeof v === "number" ? count(v) : esc(v)}</b><span>${esc(label)}${extra}</span></div>`;
  const row = (ic, label, value) => value ? `<div class="uf-row"><span class="uf-ic">${icon(ic)}</span><div><small>${esc(label)}</small><p>${value}</p></div></div>` : "";
  const link = (url, text) => safeUrl(url) ? `<a href="${esc(safeUrl(url))}" target="_blank" rel="noopener">${esc(text)} ${icon("external")}</a>` : "";
  const site = (id.website || "").replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "");
  const line = [id.founded && `Kuruluş ${id.founded}`, id.hq || l.cities?.join(", "), l.sectors?.[0]].filter(Boolean);
  return `${line.length ? `<p class="uf-line ff-line">${line.map(esc).join(" · ")}</p>` : ""}
    <div class="uf-stats">${stat(id.employees?.value, "çalışan", id.employees?.year ? ` · ${esc(id.employees.year)}` : "")}${stat(id.founded || null, "kuruluş")}
      ${stat(l.academics, "akademisyen")}${stat(l.papers, "ortak yayın")}${stat(l.universities, "üniversite")}${stat(l.centers, "Ar-Ge / tasarım merkezi")}</div>
    ${id.revenue ? `<div class="ff-revenue"><small>Ciro / gelir</small><b>${esc(firmMoney(id.revenue))}</b></div>` : ""}
    <div class="ff-rows">
      ${row("briefcase", "Sektör", esc([id.industry, ...(l.sectors || [])].filter(Boolean).filter((v, i, a) => a.findIndex((x) => fold(x) === fold(v)) === i).join(" · ")))}
      ${l.areas?.length ? row("layers", "Çalışma alanları", l.areas.map((a) => `<span class="chip">${esc(a)}</span>`).join(" ")) : ""}
      ${row("map", "Merkez", esc(id.hq || ""))}
      ${row("globe", "Şehirler", esc((l.cities || []).join(", ")))}
      ${compact ? "" : row("user", "Kilit kişiler", esc(id.people || ""))}
      ${compact ? "" : row("user", "Kurucu", esc(id.founder || ""))}
      ${compact ? "" : row("bookmark", "Sahibi / ortaklık", esc(id.owner || ""))}
      ${compact ? "" : row("grid", "Ürünler", esc(id.products || ""))}
      ${row("external", "Bağlantılar", [link(id.website, site), link(id.wikipedia, "Vikipedi")].filter(Boolean).join(" · "))}
    </div>
    ${!Object.keys(id).length ? `<p class="uf-empty">Bu firmanın Vikipedi/Wikidata kaydı bulunamadı; bilgiler resmî Ar-Ge merkezi listesinden ve ortak yayınlardan.</p>` : ""}
    <p class="uf-src">Kaynak: ${esc([...(f.sources || []), "Sanayi ve Teknoloji Bakanlığı Ar-Ge listesi", "OpenAlex / TR Dizin"].join(" · "))}</p>`;
}
function openFirmPeek(card, id, name) {
  const html = `<div class="peek-cover uni">${organizationLogo("firms", id, name, "peek-logo xl")}</div>
    <div class="peek-head center"><div class="peek-id"><h3>${esc(name)}</h3></div></div>
    <div class="uf-host ff-host"><div class="uf-stats">${["çalışan", "kuruluş", "akademisyen", "ortak yayın", "üniversite", "merkez"].map((l) => `<div><b class="sk-num"></b><span>${l}</span></div>`).join("")}</div>
      <div class="loading-line"><span class="spinner"></span>Firma künyesi derleniyor…</div></div>
    <div class="peek-actions"><button class="btn primary peek-go" type="button" data-peek-go="#/firma/${esc(id)}">Firma detayı ${icon("arrow")}</button></div>`;
  openPeek(card, { kind: "university", name, html, enter: TX.windmill, leave: TX.windmillOut, load: async (peek) => {
    const host = $(".ff-host", peek);
    try {
      const f = await api(`/api/firms/${encodeURIComponent(id)}/facts`, { quiet: true });
      if (!peek.isConnected) return;
      host.innerHTML = firmFactsHtml(f, { compact: true }); hydrateIcons(host);
      if (!calmMotion()) host.animate([{ opacity: .3 }, { opacity: 1 }], { duration: 300, easing: "ease-out" });
      animateCounts(host);
    } catch (e) { if (peek.isConnected) host.innerHTML = `<p class="uf-empty">Künye alınamadı: ${esc(e.message)}</p>`; }
  } });
}
document.addEventListener("click", (e) => {
  if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey || e.button) return;
  const b = e.target.closest(".firm-bubble[href^='#/firma/']");
  if (!b) return;
  e.preventDefault();
  openFirmPeek(b, b.getAttribute("href").slice(8), $(".bubble-name", b)?.textContent || b.title.split(" · ")[0]);
});
// Firma asistanı: künye, ortak yayınlar ve TÜBİTAK verisiyle yanıt verir
function firmAssistantHtml(f) {
  return `<aside class="student-assistant firm-assistant"><header class="student-assistant-head"><span class="student-assistant-symbol">${icon("sparkle")}</span><div><h3>Firma asistanı</h3><p>${esc(f.name)}</p></div></header>
    <p class="student-assistant-intro">Firmanın akademik iş birlikleri, çalıştığı üniversiteler ve projeleri hakkında sor.</p>
    <div class="student-chat-suggestions">${["En çok hangi üniversitelerle çalışıyor?", "Hangi alanlarda ortak yayın var?", "TÜBİTAK projeleri neler?"].map((q) => `<button type="button" data-fa-q="${esc(q)}">${esc(q)}</button>`).join("")}</div>
    <div class="student-chat-thread" role="log" aria-live="polite"></div>
    <form class="student-chat-form"><textarea rows="3" maxlength="1000" placeholder="Örneğin: Aselsan ile en çok kim yayın yapmış?" required></textarea><div class="student-chat-toolbar"><span>Enter gönderir</span><button class="btn primary" type="submit">${icon("send")}Gönder</button></div></form></aside>`;
}
function bindFirmAssistant(host, fid) {
  const thread = $(".student-chat-thread", host), form = $("form", host), input = $("textarea", form), messages = [];
  const add = (role, text) => {
    const el = document.createElement("article"); el.className = `student-chat-message ${role}`;
    el.innerHTML = `<div class="student-chat-bubble"><p></p></div>`; thread.appendChild(el);
    const p = $("p", el);
    if (role === "user" || calmMotion()) p.textContent = text;
    else { let i = 0; const t = setInterval(() => { p.textContent = text.slice(0, i += 3); thread.scrollTop = thread.scrollHeight; if (i >= text.length) clearInterval(t); }, 16); }
    thread.scrollTop = thread.scrollHeight; return el;
  };
  const ask = async (q) => {
    q = q.trim(); if (!q || form.dataset.busy) return;
    form.dataset.busy = "1"; $(".student-chat-suggestions", host).hidden = true; input.value = "";
    add("user", q);
    const wait = document.createElement("article"); wait.className = "student-chat-message assistant";
    wait.innerHTML = `<div class="student-chat-bubble"><span class="typing-dots"><i></i><i></i><i></i></span></div>`; thread.appendChild(wait);
    try {
      const r = await post(`/api/firms/${encodeURIComponent(fid)}/chat`, { question: q, messages });
      wait.remove(); add("assistant", r.answer || "Yanıt alınamadı.");
      messages.push({ role: "user", content: q }, { role: "assistant", content: r.answer || "" });
    } catch (e) { wait.remove(); add("assistant", e.message); }
    finally { delete form.dataset.busy; }
  };
  form.onsubmit = (e) => { e.preventDefault(); ask(input.value); };
  input.onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(input.value); } };
  $$("[data-fa-q]", host).forEach((b) => b.onclick = () => ask(b.dataset.faQ));
}
async function renderFirmOverview(fid, name, refresh = false) {
  const host = $("#firmOverview"); if (!host) return;
  if (!$(".overview-facts", host)) {
    host.innerHTML = `<div class="university-overview-layout"><section class="card card-pad"><div class="section-head"><h2>Firma künyesi</h2><button class="btn sm" data-firm-refresh-facts type="button">${icon("refresh")}Eksik bilgileri yenile</button></div><div class="overview-facts"></div></section>${firmAssistantHtml({ name })}</div>`;
    hydrateIcons(host); bindFirmAssistant(host, fid);
    $("[data-firm-refresh-facts]", host).onclick = () => renderFirmOverview(fid, name, true);
  }
  const box = $(".overview-facts", host), button = $("[data-firm-refresh-facts]", host);
  button.disabled = true; box.innerHTML = '<div class="loading-line"><span class="spinner"></span>Firma künyesi alınıyor…</div>';
  try {
    const f = await api(`/api/firms/${encodeURIComponent(fid)}/facts${refresh ? "?refresh=1" : ""}`, { quiet: true });
    if (!box.isConnected) return;
    box.innerHTML = firmFactsHtml(f); hydrateIcons(box); animateCounts(box);
  } catch (e) { box.innerHTML = `<p class="notice warn">${esc(e.message)}</p>`; }
  finally { button.disabled = false; }
}

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
      ${d.items.length ? `<div class="watch-body firm-watch"><div class="watch-grid">${d.items.map((x) => `<a class="bubble firm-bubble" href="#/firma/${esc(x.id)}" draggable="false" title="${esc(`${x.name} · ${x.sectors.join(", ")} · ${x.centers.length} merkez${x.academics ? ` · ${x.academics} akademisyen` : ""}`)}">
        ${organizationLogo("firms", x.id, x.name, "bubble-logo")}<span class="bubble-name">${esc(x.name)}</span></a>`).join("")}</div></div>`
        : `<div class="card">${emptyState("search", "Firma bulunamadı", "Aramayı ya da filtreleri değiştirin.")}</div>`}`;
    hydrateIcons($("#fBody"));
    if ($(".firm-watch")) mountWatch($(".firm-watch"));
  };
  $("#firmQ").oninput = () => { clearTimeout(timer); timer = setTimeout(load, 250); };
  $("#firmSector").onchange = load; $("#firmCity").onchange = load; $("#firmArea").onchange = () => { area = ""; load(); };
  load();
}

async function viewFirm(fid, refresh = false, supplied = null) {
  setCrumbs([{ label: "Ana sayfa", href: "#/" }, { label: "Firmalar", href: "#/firmalar" }, { label: "…" }]);
  if (!supplied) setView(`<div id="firmHead">${skeleton(1)}</div><div class="card card-pad"><div class="loading-line"><span class="spinner"></span>
    OpenAlex ve TR Dizin'de firmayla ortak yayınlar taranıyor, profiller kontrol ediliyor…</div>${skeleton(3)}</div>`);
  let d;
  const seq = S.routeSeq;
  try { d = supplied || await api(`/api/firms/${encodeURIComponent(fid)}?quick=1${refresh ? "&refresh=1" : ""}`); if (seq !== S.routeSeq) return; }
  catch (e) { setView(`<div class="card">${emptyState("briefcase", "Firma açılamadı", esc(e.message))}</div>`); return; }
  const f = d.firm;
  rememberVisit("firm", fid, f.name);
  setCrumbs([{ label: "Ana sayfa", href: "#/" }, { label: "Firmalar", href: "#/firmalar" }, { label: f.name }]);
  const people = d.academics;
  const paperRow = (x) => `<div class="variants">${safeUrl(x.url) ? `<a href="${esc(safeUrl(x.url))}" target="_blank" rel="noopener">${esc(x.title)}</a>` : esc(x.title)}
    · ${esc(x.year || "?")} · ${esc(x.source)}${x.role ? ` · ${esc(x.role)}` : ""}${x.firm_people?.length ? ` · <span class="faint">firmadan: ${esc(x.firm_people.join(", "))}</span>` : ""}
    ${x.quote ? `<div class="faint" style="font-style:italic;margin-top:2px">“${esc(x.quote)}”</div>` : ""}</div>`;
  setView(`<section class="card identity-hero identity-org" data-org-brand>
      <div class="identity-cover" aria-hidden="true"></div>
      <div class="identity-main">
        <div class="identity-avatar">${organizationLogo("firms", f.id, f.name, "hero-logo")}</div>
        <div class="identity-info"><h1>${esc(f.name)}</h1><div class="meta"><span>${esc(f.sectors.join(", "))}</span><span>${esc(f.cities.join(", "))}</span></div>
          <div class="chips" style="margin-top:10px">${f.kinds.map((k) => `<span class="chip teal">✓ ${esc(k)}</span>`).join("")}</div></div>
        <div class="kebab"><button class="icon-btn kebab-btn" type="button" aria-label="Seçenekler">${icon("dots")}</button><div class="kebab-menu" hidden>${organizationSaveButton("firms", fid)}<button class="btn" id="firmRefresh" type="button">${icon("refresh")}Yeniden tara</button></div></div>
      </div><div class="identity-details">
      ${f.areas?.tags?.length ? `<div class="m-h" style="margin:14px 0 6px">Çalışma alanları</div><div class="chips">${f.areas.tags.map((t) => `<a class="chip blue" href="#/firmalar?area=${encodeURIComponent(t.name)}">${esc(t.name)}<sup>${t.count}</sup></a>`).join("")}</div>
        ${f.areas.topics?.length ? `<div class="chips" style="margin-top:6px">${f.areas.topics.map((t) => `<span class="chip">${esc(t.name)}<sup>${t.count}</sup></span>`).join("")}</div>` : ""}
        <p class="faint" style="margin:6px 0 0;font-size:12.5px">Firmanın ${fmtNum(f.areas.papers)} yayınının OpenAlex konularından; yayın dışı çalışmaları kapsamaz.</p>` : ""}
      <details style="margin-top:10px"><summary class="faint" style="cursor:pointer">${f.centers.length} kayıtlı merkez</summary>
        <ul style="margin:8px 0 0;padding-left:18px">${f.centers.map((c) => `<li class="faint">${esc(c)}</li>`).join("")}</ul></details></div></section>
    ${d.pending ? `<div class="loading-line" data-firm-background><span class="spinner"></span>Kayıtlı bilgiler gösteriliyor; ortak yayınlar arka planda güncelleniyor…</div>` : ""}
    ${d.errors.map((e) => `<div class="notice warn" style="margin-bottom:14px">${icon("info")}<div>${esc(e)}. Sonuç eksik olabilir; yeniden tara düğmesiyle tekrar deneyebilirsiniz.</div></div>`).join("")}
    <div class="stat-row"><div class="stat"><b>${fmtNum(people.length)}</b><span>akademisyen</span></div>
      <div class="stat"><b>${fmtNum(d.papers)}</b><span>ortak yayın ve proje</span></div>
      <div class="stat src"><b>${Object.entries(d.by_source).map(([k, v]) => `${esc(k)} ${v}`).join(" · ") || "—"}</b><span>kaynak · ${esc(d.updated)}</span></div></div>
    <div class="tabs" role="tablist"><button class="tab active" data-tab="overview" type="button">Genel bakış</button><button class="tab" data-tab="people" type="button">Akademisyenler<span class="n">${fmtNum(people.length)}</span></button>
      <button class="tab" data-tab="tubitak" type="button">TÜBİTAK<span class="n" id="tubitakN">${fmtNum(d.ardeb.length)}</span></button>
      <button class="tab" data-tab="patents" type="button" hidden>Patentler<span class="n" id="patentsN">0</span></button></div>
    <div class="panel active" data-panel="overview" id="firmOverview"></div>
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
    <div class="panel" data-panel="people">
    ${people.length ? `<div class="toolbar"><div class="input">${icon("search")}<input id="firmPeopleQ" placeholder="Akademisyen ya da üniversite ara"></div></div>
      <div class="firm-person-grid" id="firmPeople">${people.map((p, i) => { const c = p.chat_id && S.chats.find((x) => x.id === p.chat_id);
        return `<button type="button" class="firm-person-card" data-peek-person="${i}" data-fold="${esc(fold(p.name + " " + p.institution))}"><span class="firm-person-uni">${p.institution ? organizationLogo("universities", orgId(p.institution), p.institution, "firm-person-logo") : ""}<span>${esc(p.institution || "Kurum belirtilmemiş")}</span></span>${avatar(p.name, c ? profilePhoto(c) : p.photo || "", "av fb-av")}<span class="fb-name">${esc(p.name)}</span><span class="fb-sub">${esc(p.title || "")}${p.title ? " · " : ""}${c ? `${fmtNum(c.papers)} yayın` : `${p.papers.length} ortak yayın`}</span></button>`; }).join("")}</div>`
      : `<div class="card">${emptyState("users", d.pending ? "Akademisyenler alınıyor…" : "Akademisyen bulunamadı",
        d.pending ? "Firma bilgilerini inceleyebilirsiniz; yayın kaynakları hazır olduğunda kartlar burada görünecek." : "Açık kaynaklarda bu firmayla ortak yayını olan akademisyen yok ya da firma yayınlarda farklı adla geçiyor. Gizli sözleşmeler ve yayına dönüşmeyen işler görünmez.")}</div>`}</div>`);
  S.firmPeople = people;
  renderFirmOverview(fid, f.name);
  typeText($(".identity-org h1"), f.name);
  $("#firmRefresh").onclick = () => viewFirm(fid, true);
  if (!d.pending) {
    const projectsTab = $('.tab[data-tab="tubitak"]'), patentsTab = $('.tab[data-tab="patents"]');
    projectsTab?.addEventListener("click", () => loadTeydeb(fid, refresh, d.ardeb.length), { once: true });
    if (patentsTab) { patentsTab.hidden = false; patentsTab.addEventListener("click", () => loadFirmPatents(fid, refresh), { once: true }); }
  }
  else {
    api(`/api/firms/${encodeURIComponent(fid)}${refresh ? "?refresh=1" : ""}`, { quiet: true }).then(full => {
      if (S.routeSeq !== seq || !location.hash.startsWith(`#/firma/${fid}`)) return;
      const scroll = view().scrollTop, activeTab = $(".tab.active")?.dataset.tab;
      viewFirm(fid, false, full).then(() => { if (S.routeSeq !== seq) return; const tab = $(`.tab[data-tab="${activeTab}"]`); if (tab && !tab.hidden) switchTab(tab); view().scrollTop = scroll; });
    }).catch(error => { const status = $("[data-firm-background]"); if (status && S.routeSeq === seq) status.textContent = `Güncelleme tamamlanamadı: ${error.message}. Yeniden tara ile tekrar deneyebilirsiniz.`; });
  }
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
  S.routeSeq = (S.routeSeq || 0) + 1;
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
    firmalar: "firmalar", firma: "firmalar", ara: "ara", kutuphane: "kutuphane", sistem: "sistem", danisman: "danisman" }[parts[0]] || (parts.length ? "" : "home"));
  switch (parts[0]) {
    case "ara": return viewSearch(params.get("q") || "", params.get("sources") || "");
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
    case "puan": location.replace(parts[1] ? `#/profil/${parts[1]}` : "#/akademisyenler"); return undefined;
    case "danisman": return viewAdvisor(params);
    default: return viewHome();
  }
}

document.addEventListener("click", async (e) => {
  const t = e.target;
  $$(".source-picker[open]").forEach((el) => { if (!el.contains(t)) el.open = false; });
  const saveOrg = t.closest("[data-save-org]");
  if (saveOrg) { e.preventDefault(); toggleOrganization(saveOrg); return; }
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
  const staffRefresh = t.closest("[data-staff-refresh]");
  if (staffRefresh) { const entry = S.staffRegistry.get(staffRefresh.dataset.staffRefresh); if (entry?.onRefresh) { staffRefresh.disabled = true; entry.onRefresh(entry.person); } return; }
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
  if (e.key === "Tab" && !$("#modal").hidden && !wosVerification?.isOpen()) {
    const focusable = $$("button:not([disabled]), input:not([disabled]), select:not([disabled]), a[href], summary, textarea:not([disabled])", $(".modal-box")).filter((el) => el.getClientRects().length);
    const first = focusable[0], last = focusable.at(-1);
    if (first && e.shiftKey && (document.activeElement === first || !$(".modal-box").contains(document.activeElement))) { e.preventDefault(); last.focus(); }
    else if (first && !e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }
  if (e.key !== "Escape") return;
  if (wosVerification?.isOpen()) { e.preventDefault(); wosVerification.hide(); return; }
  const filter = $(".dt-filter-popover:popover-open");
  if (filter) {
    e.preventDefault(); filter.hidePopover();
    $(`[popovertarget="${filter.id}"].dt-filter-toggle`)?.focus({ preventScroll: true });
    return;
  }
  const picker = $(".source-picker[open]");
  if (picker) { picker.open = false; $("summary", picker).focus(); return; }
  closeModal(); closeDrawer();
  if ($("#app").classList.contains("menu-open")) { $("#app").classList.remove("menu-open"); syncSidebar(); $("#menuBtn").focus(); }
});
$("#menuBtn").addEventListener("click", toggleSidebar);
$("#scrim").addEventListener("click", () => { $("#app").classList.remove("menu-open"); syncSidebar(); });
$("#themeBtn").addEventListener("click", toggleTheme);
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", (e) => { if (!storedTheme()) applyTheme(e.matches ? "dark" : "light"); });
let lastRouteHash = location.hash;
const NAV_ORDER = ["", "akademisyenler", "universiteler", "firmalar", "ara", "kutuphane", "sistem"];
const routeInfo = (hash) => {
  const parts = (hash || "#/").slice(1).split("?")[0].split("/").filter(Boolean);
  return { key: parts[0] || "", path: parts.join("/"), detail: ["profil", "is", "universite", "kurum", "firma"].includes(parts[0]) };
};
window.addEventListener("hashchange", () => {
  const a = routeInfo(lastRouteHash), b = routeInfo(location.hash), root = document.documentElement;
  lastRouteHash = location.hash;
  if (!document.startViewTransition || calmMotion() || root.classList.contains("page-vt") || a.path === b.path) { route(); return; }
  const kind = !a.detail && !b.detail ? "tx-box" : "tx-perspective";
  const back = kind === "tx-box" ? NAV_ORDER.indexOf(b.key) < NAV_ORDER.indexOf(a.key) : a.detail && !b.detail;
  const cls = ["page-vt", kind, ...(back ? ["tx-back"] : [])];
  root.classList.add(...cls);
  const vt = document.startViewTransition(() => { route(); });
  vt.finished.finally(() => root.classList.remove(...cls));
});

(async () => {
  hydrateIcons();
  wosVerification = createWosVerification();
  setupSidebar();
  showWelcome();
  const legacy = new URLSearchParams(location.search).get("chat");
  if (legacy) { history.replaceState(null, "", `/#/profil/${legacy}`); }
  loadEnv();
  applyTheme(document.documentElement.dataset.theme);
  await Promise.all([loadFav(), loadChats()]);
  route();
  document.fonts?.ready.then(() => { const a = $("#nav a.active"); if (a) setNav(a.dataset.nav); $("#navPill").classList.add("ready"); });
})();

async function renderUniversityOverview(refresh = false) {
  const host = $("#universityOverview"), d = S.uni;
  if (!host || !d || (host.dataset.ready && !refresh)) return;
  host.dataset.ready = "1";
  if (!$(".overview-facts", host)) {
    host.innerHTML = `<div class="university-overview-layout"><section class="card card-pad"><div class="section-head"><h2>Üniversite künyesi</h2><button class="btn sm" data-refresh-facts>${icon("refresh")}Eksik bilgileri yenile</button></div><div class="overview-facts"></div></section>${studentAssistantHtml(d)}</div>`;
    bindStudentChat(d);
    $("[data-refresh-facts]", host).onclick = () => renderUniversityOverview(true);
  }
  const box = $(".overview-facts", host), button = $("[data-refresh-facts]", host);
  button.disabled = true;
  box.innerHTML = '<div class="loading-line"><span class="spinner"></span>Üniversite bilgileri alınıyor…</div>';
  try {
    const f = await api(`/api/universities/${encodeURIComponent(d.id)}/facts${refresh ? "?refresh=1" : ""}`, { quiet: true });
    if (!host.isConnected || S.uni !== d) return;
    box.innerHTML = uniFactsHtml(f, S.chats.filter(c => orgId(c.institution || "") === d.id));
    const tabs = $$("[data-uf-tab]", box), panes = $$(".uf-pane", box);
    tabs.forEach((tab, i) => tab.onclick = () => { tabs.forEach(t => t.classList.toggle("on", t === tab)); panes.forEach((p, j) => p.classList.toggle("on", i === j)); });
    $(".uf-ink", box)?.remove(); hydrateIcons(host);
    if (!f.academics) {
      try {
        const ac = await api(`/api/universities/${encodeURIComponent(d.id)}/staff-counts`, { quiet: true });
        if (!box.isConnected) return;
        const stat = $("[data-uf-staff-stat]", box), block = $("[data-uf-staff]", box);
        if (stat) stat.innerHTML = `<b>${count(ac.total)}</b><span>akademisyen</span>`;
        if (block) block.innerHTML = uniStaffBlock(ac);
      } catch { const stat = $("[data-uf-staff-stat]", box); if (stat) stat.innerHTML = '<b>—</b><span>akademisyen</span>'; }
    }
  } catch (e) { box.innerHTML = `<p class="notice warn">${esc(e.message)}</p>`; }
  finally { button.disabled = false; }
}
async function openFirmPerson(person, chat) {
  let papers = person.papers || [];
  if (chat) {
    openModal(`<div data-firm-loading="${esc(chat.id)}"><h2>${esc(person.name)}</h2><p>Yayınlar alınıyor…</p></div>`);
    const loading = $("[data-firm-loading]");
    try {
      const data = await api(`/api/chats/${encodeURIComponent(chat.id)}`, { quiet: true });
      if (!loading?.isConnected || $("#modal").hidden) return;
      if (data.result?.publications?.length) papers = data.result.publications;
    } catch { if (!loading?.isConnected || $("#modal").hidden) return; }
  }
  const wasOpen = !$("#modal").hidden;
  openModal(`<div class="firm-publications"><div><h2>${esc(person.name)}</h2><p class="muted">${esc(person.institution || "")} · ${papers.length} ${chat ? "yayın" : "ortak yayın"}</p><div class="firm-publication-list">${papers.map((p, i) => `<button class="firm-publication" type="button" data-firm-paper="${i}"><span>${esc(p.year || "")}</span><b>${esc(p.title)}</b>${icon("chevron")}</button>`).join("") || "Ortak yayın kaydı bulunamadı."}</div>${chat ? `<a class="btn sm" href="#/profil/${esc(chat.id)}" data-firm-profile>Tüm profil yayınları</a>` : ""}</div><aside class="firm-paper-detail" hidden></aside></div>`);
  const root = $(".firm-publications"), detail = $(".firm-paper-detail", root), box = root.closest(".modal-box");
  void wasOpen; // açılış: openModal'ın klasör büyümesi
  $("[data-firm-profile]", root)?.addEventListener("click", closeModal);
  $$("[data-firm-paper]", root).forEach(button => button.onclick = async () => {
    const p = papers[+button.dataset.firmPaper];
    const first = !root.classList.contains("expanded"), from = box.getBoundingClientRect().width, listFrom = root.firstElementChild?.getBoundingClientRect().width;
    root.classList.add("expanded"); detail.hidden = false;
    if (!calmMotion()) {
      if (first) {
        // Squeeze: modal genişler, liste sıkışarak yer açar, özet sağ kenardan genişleyerek gelir
        const to = box.getBoundingClientRect().width, list = root.firstElementChild;
        box.animate([{ width: `${from}px` }, { width: `${to}px` }], { duration: 460, easing: EASE });
        if (list && listFrom) TX.squeezeFrom(list, listFrom / Math.max(1, list.getBoundingClientRect().width));
        TX.squeeze(detail, { delay: 90 });
      } else TX.squeeze(detail, { from: .86 });
    }
    $$("[data-firm-paper]", root).forEach(b => b.classList.toggle("selected", b === button));
    detail.innerHTML = `<h3>${esc(p.title)}</h3><p class="muted">${esc(p.year || "")} · ${esc(p.source || "")}</p><h4>Özet</h4><div class="abs">${esc(p.abstract || p.summary || p.quote || "Kaynak kaydında özet bulunmuyor.")}</div>${safeUrl(p.url) ? `<a class="btn sm" target="_blank" rel="noopener" href="${esc(safeUrl(p.url))}">Kaynağı aç ${icon("external")}</a>` : ""}`;
    hydrateIcons(detail);
    S.paperRequest?.abort();
    if (p.abstract || p.summary) return;
    const controller = new AbortController(); S.paperRequest = controller;
    const abs = $(".abs", detail); abs.textContent = "Yayın özeti kaynaktan alınıyor…";
    const timer = setTimeout(() => controller.abort(), 90000);
    let found = false;
    try {
      const response = await fetch("/api/paper", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ paper: p }), signal: controller.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      await readSse(response, message => {
        if (!detail.isConnected || S.paperRequest !== controller) return false;
        if (message.meta?.abstract) { found = true; abs.textContent = message.meta.abstract; }
      });
      if (!found && S.paperRequest === controller) abs.textContent = "Kaynaklarda bu yayının özeti bulunamadı.";
    } catch (e) { if (detail.isConnected && S.paperRequest === controller) abs.textContent = "Özet şu anda alınamadı. Kaynak bağlantısından inceleyebilirsiniz."; }
    finally { clearTimeout(timer); if (S.paperRequest === controller) S.paperRequest = null; }
  });
}

// Ders izlencesi: değerlendirme yüzdeleri, haftalık konular, iş yükü, öğrenme çıktıları
const SYL_COLORS = ["#2563eb", "#14b8a6", "#f59e0b", "#a855f7", "#ef4444", "#64748b", "#0ea5e9", "#84cc16"];
function syllabusHtml(sy) {
  const info = sy.info?.length ? `<div class="syl-info">${sy.info.map((x) => `<span><small>${esc(x.label.replace(/^Dersin\s+/i, ""))}</small><b>${esc(x.value)}</b></span>`).join("")}</div>` : "";
  const total = (sy.assessment || []).reduce((a, x) => a + x.percent, 0) || 100;
  const assess = sy.assessment?.length ? `<section class="syl-block"><h4>Değerlendirme</h4>
    <div class="syl-bar" role="img" aria-label="${esc(sy.assessment.map((x) => `${x.name} yüzde ${x.percent}`).join(", "))}">${sy.assessment.map((x, i) => `<i style="--w:${x.percent / total * 100}%;--c:${SYL_COLORS[i % SYL_COLORS.length]}" title="${esc(x.name)} %${x.percent}"></i>`).join("")}</div>
    <ul class="syl-legend">${sy.assessment.map((x, i) => `<li><span style="--c:${SYL_COLORS[i % SYL_COLORS.length]}"></span>${esc(x.name)}${x.count && x.count !== "1" ? ` <small>×${esc(x.count)}</small>` : ""}<b>%${x.percent}</b></li>`).join("")}</ul></section>` : "";
  const wl = sy.workload || {};
  const work = wl.hours || wl.items?.length ? `<section class="syl-block"><h4>İş yükü</h4><p class="syl-work"><b>${esc(wl.hours || "—")}</b> saat${wl.ects ? ` · <b>${esc(wl.ects)}</b> AKTS` : ""}</p>
    ${wl.items?.length ? `<ul class="syl-work-items">${wl.items.map((x) => `<li><span>${esc(x.name)}</span><b>${esc(x.hours)} sa</b></li>`).join("")}</ul>` : ""}</section>` : "";
  const weeks = sy.weeks?.length ? `<section class="syl-block syl-wide"><h4>Haftalık konular <small>${sy.weeks.length} hafta</small></h4>
    <ol class="syl-weeks">${sy.weeks.map((w) => `<li class="${/vize|final|sınav|midterm|exam/.test(w.topic.toLocaleLowerCase("tr")) ? "exam" : ""}"><span>${esc(w.week)}</span><p>${esc(w.topic)}${w.prep ? `<small>Hazırlık: ${esc(w.prep)}</small>` : ""}</p></li>`).join("")}</ol></section>` : "";
  const outs = sy.outcomes?.length ? `<section class="syl-block syl-wide"><h4>Öğrenme çıktıları</h4><ul class="syl-outcomes">${sy.outcomes.map((o) => `<li>${esc(o)}</li>`).join("")}</ul></section>` : "";
  return `<div class="syllabus">${info}<div class="syl-grid">${assess}${work}${weeks}${outs}</div></div>`;
}
// Program profili (OIBS): mezun iş alanları, profil, üst kademe, derece, amaçlar
function programChips(text) {
  const parts = text.replace(/\s+vb\.?\s*(gibi)?.*$/i, "").split(/\s*[,;•\n]\s*/).map((x) => x.trim()).filter((x) => x.length > 2 && x.length < 60);
  return parts.length >= 3 && parts.length <= 40 ? parts : null;
}
async function loadProgramProfile(box, d) {
  const host = $("[data-program-url]", box);
  if (!host) return;
  host.innerHTML = '<div class="loading-line"><span class="spinner"></span>Program profili ve mezun iş alanları alınıyor…</div>';
  try {
    const p = await api(`/api/universities/${encodeURIComponent(d.id)}/student/program?url=${encodeURIComponent(host.dataset.programUrl)}`, { quiet: true });
    if (!host.isConnected) return;
    if (!p.sections?.length) { host.hidden = true; return; }
    const order = ["employment", "profile", "further", "degree", "goals"], secs = [...p.sections].sort((a, b) => order.indexOf(a.key) - order.indexOf(b.key));
    host.innerHTML = `<div class="prog-head">${icon("cap")}<div><h4>Program profili</h4><p>Bölüm seçerken: mezunlar nerede çalışıyor, program ne kazandırıyor?</p></div></div>
      <div class="prog-secs">${secs.map((s, i) => { const chips = s.key === "employment" && programChips(s.text);
        return `<section class="prog-sec ${s.key}${i === 0 ? " lead" : ""}"><h5>${esc(s.heading)}</h5>${chips ? `<div class="chips">${chips.map((c) => `<span class="chip teal">${esc(c)}</span>`).join("")}</div>` : `<p class="${s.text.length > 420 ? "clamp" : ""}">${esc(s.text)}</p>${s.text.length > 420 ? '<button class="link" type="button" data-prog-more>Devamını göster</button>' : ""}`}
          <a class="source-link" href="${esc(safeUrl(s.url))}" target="_blank" rel="noopener">${icon("external")}Kaynak</a></section>`; }).join("")}</div>`;
    hydrateIcons(host);
    $$("[data-prog-more]", host).forEach((b) => b.onclick = () => { const t = b.previousElementSibling; const shut = t.classList.toggle("clamp"); b.textContent = shut ? "Devamını göster" : "Daralt"; });
    if (!calmMotion()) $$(".prog-sec", host).forEach((el, i) => el.animate([{ opacity: 0, transform: "translateY(8px)" }, { opacity: 1, transform: "none" }], { duration: 300, delay: i * 50, easing: EASE, fill: "backwards" }));
  } catch { host.hidden = true; }
}

function bindCourseDetails(root, d) {
  $$("[data-course-url]", root).forEach(course => {
    course.addEventListener("toggle", async () => {
      if (!course.open || course.dataset.loaded) return;
      course.dataset.loaded = "pending";
      const target = $(".course-description", course);
      target.innerHTML = '<div class="loading-line"><span class="spinner"></span>Ders içeriği alınıyor…</div>';
      try {
        const content = await api(`/api/universities/${encodeURIComponent(d.id)}/student/preview?url=${encodeURIComponent(course.dataset.courseUrl)}`, { quiet: true });
        if (!course.isConnected) return;
        const sy = content.syllabus && Object.keys(content.syllabus).length ? content.syllabus : null;
        const parts = (content.course_content || []).filter(part => !sy || !/haftal|weekly|öğrenme çıktı|ogrenme cikti|learning outcome/i.test(part.heading));
        target.innerHTML = (sy ? syllabusHtml(sy) : "") + (parts.length ? parts.map(part => `<section><h4>${esc(part.heading)}</h4><p>${esc(part.text)}</p></section>`).join("") : sy ? "" : linkPreviewBody(content));
        if (sy && !calmMotion()) $$(".syl-bar i", target).forEach((el, i) => el.animate([{ transform: "scaleX(0)" }, { transform: "none" }], { duration: 520, delay: i * 90, easing: EASE, fill: "backwards" }));
        target.insertAdjacentHTML("beforeend", `<a class="source-link" target="_blank" rel="noopener" href="${esc(safeUrl(course.dataset.courseUrl))}">Dersin kaynak sayfası ${icon("external")}</a>`);
        course.dataset.loaded = "done"; hydrateIcons(target);
      } catch (e) { delete course.dataset.loaded; target.innerHTML = `<p class="notice warn">${esc(e.message)} · Dersi kapatıp yeniden açarak tekrar deneyebilirsin.</p>`; }
    });
  });
}

function readRecentVisits() {
  try { const value = JSON.parse(localStorage.getItem("academic-recent-views") || "[]"); return Array.isArray(value) ? value.filter(v => v && ["person", "firm", "topic"].includes(v.kind) && typeof v.id === "string" && typeof v.name === "string" && Number.isFinite(v.at)) : []; } catch { return []; }
}
function rememberVisit(kind, id, name, extra = {}) {
  const list = [{ kind, id, name, at: Date.now(), ...extra }, ...readRecentVisits().filter(v => v.kind !== kind || v.id !== id)].slice(0, 30);
  try { localStorage.setItem("academic-recent-views", JSON.stringify(list)); } catch { /* Storage may be unavailable. */ }
}
function recentVisitHtml(entry, i) {
  if (entry.kind === "person") { const chat = S.chats.find(c => c.id === entry.id); return chat ? profileRow(chat, i) : ""; }
  const firm = entry.kind === "firm", href = firm ? `#/firma/${encodeURIComponent(entry.id)}` : `#/ara?q=${encodeURIComponent(entry.id)}${entry.sources ? `&sources=${encodeURIComponent(entry.sources)}` : ""}`;
  return `<a class="recent-entry" href="${esc(href)}">${firm ? organizationLogo("firms", entry.id, entry.name, "recent-logo") : `<span class="recent-topic-icon">${icon("book")}</span>`}<span><b>${esc(entry.name)}</b><small>${firm ? "Firma" : "Konu araştırması"}</small></span>${icon("chevron")}</a>`;
}
document.addEventListener("load", event => {
  const img = event.target;
  if (!(img instanceof HTMLImageElement) || !img.closest(".peek-side-av")) return;
  if (img.naturalWidth && img.naturalHeight) { img.style.maxWidth = `${Math.min(128, img.naturalWidth)}px`; img.style.maxHeight = `${Math.min(156, img.naturalHeight)}px`; }
}, true);
