import * as THREE from "/static/vendor/three.module.min.js";

// Yardımcılar ve yalnızca aynı kaynaktaki veri uçları.
const $ = selector => document.querySelector(selector);
const $$ = selector => [...document.querySelectorAll(selector)];
const enc = encodeURIComponent;
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[c]);
const clamp = THREE.MathUtils.clamp;
const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
const number = value => Number(value || 0).toLocaleString("tr-TR");
const fold = value => String(value || "").toLocaleLowerCase("tr").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9]/g, "");
const doiOf = item => String(item.doi || "").replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, "").trim().toLowerCase();
const titleOf = item => String(item.kind === "person" ? item.name || "Akademisyen" : item.name_tr || item.title || item.name || "Başlıksız yayın");
const authorName = value => typeof value === "string" ? value : value?.name || value?.display_name || "";
const initials = name => String(name || "?").split(/\s+/).slice(0, 2).map(x => x[0]).join("").toLocaleUpperCase("tr");
const safeUrl = value => {
  try { const url = new URL(String(value)); return /^https?:$/.test(url.protocol) ? url.href : ""; }
  catch { return ""; }
};
const sourceUrl = item => safeUrl(item.url) || (doiOf(item) ? `https://doi.org/${enc(doiOf(item))}` : "");
const link = (url, label, cls = "btn") => url ? `<a class="${cls}" href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>` : "";
const searchLink = item => `/#/ara?q=${enc(titleOf(item))}`;
function readStore(key) {
  try { const value = JSON.parse(localStorage.getItem(key) || "[]"); return Array.isArray(value) ? value : []; }
  catch { return []; }
}
function writeStore(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); }
  catch { toast("Tarayıcı depolaması dolu; bu oturumda okumaya devam edebilirsin."); }
}
async function api(path, { timeout = 20000, ...options } = {}) {
  if (!path.startsWith("/api/")) throw new Error("Geçersiz veri adresi");
  const response = await fetch(path, { ...options, signal: options.signal ? AbortSignal.any([options.signal, AbortSignal.timeout(timeout)]) : AbortSignal.timeout(timeout) });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : `HTTP ${response.status}`);
  return data;
}
let toastTimer;
function toast(message) {
  $("#toast").textContent = message; $("#toast").hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { $("#toast").hidden = true; }, 4000);
}
const busy = text => `<p class="loading"><span class="spinner"></span>${esc(text)}</p>`;
const errorHtml = error => `<p class="error">${esc(error?.message || "Veri alınamadı.")}</p>`;
const colors = { tip: "#b91c1c", muhendislik: "#334155", kod: "#1d4ed8", temel: "#6d28d9", yasam: "#047857", sosyal: "#b7791f", sanayi: "#0f766e" };
const palette = ["#1d4ed8", "#0f766e", "#b7791f", "#6d28d9", "#047857"];
function hash(text) {
  let n = 0; for (const ch of String(text)) n = (Math.imul(n, 31) + ch.charCodeAt(0)) | 0;
  return n >>> 0;
}
const itemColor = item => colors[item.category] || palette[hash(titleOf(item)) % palette.length];
const icons = {
  book: '<path d="M4 4h6a3 3 0 0 1 2 1 3 3 0 0 1 2-1h6v16h-6a3 3 0 0 0-2 1 3 3 0 0 0-2-1H4zM12 5v16"/>',
  heart: '<path d="M12 21 3 12C-3 4 7-1 12 6c5-7 15-2 9 6z"/>',
  settings: '<circle cx="12" cy="12" r="4"/><path d="m12 2 1 3 3 1 3-1 2 3-2 3 1 3 2 2-2 3-3-1-3 1-1 3-4-1v-3l-3-2-3 1-1-4 2-2-1-3-2-1 2-4 3 1 2-2z"/>',
  code: '<path d="m8 5-6 7 6 7m8-14 6 7-6 7M14 3l-4 18"/>',
  atom: '<ellipse cx="12" cy="12" rx="11" ry="4"/><ellipse cx="12" cy="12" rx="11" ry="4" transform="rotate(60 12 12)"/><ellipse cx="12" cy="12" rx="11" ry="4" transform="rotate(120 12 12)"/>',
  leaf: '<path d="M20 3C5 0-1 14 7 20s15-5 13-17ZM5 22 16 9"/>',
  scale: '<path d="M12 3v18M5 21h14M3 7h18M5 7l-4 8h8zM19 7l-4 8h8z"/>',
  briefcase: '<rect x="2" y="7" width="20" height="14" rx="2"/><path d="M8 7V3h8v4M2 12h20M10 12v3h4v-3"/>',
  map: '<path d="m2 5 6-3 8 3 6-3v17l-6 3-8-3-6 3zM8 2v17M16 5v17"/>',
  search: '<circle cx="10" cy="10" r="7"/><path d="m15 15 7 7"/>',
  x: '<path d="m5 5 14 14M19 5 5 19"/>',
  exit: '<path d="M10 3H3v18h7m4-15 6 6-6 6M8 12h12"/>',
};
const iconImages = {};
let logoImage;
function loadImage(src) {
  return new Promise((resolve, reject) => {
    const img = new Image(); img.onload = () => resolve(img); img.onerror = reject; img.src = src;
  });
}
async function loadAssets() {
  await Promise.all([400, 500, 600, 700, 800].map(weight => document.fonts.load(`${weight} 24px Inter`)));
  logoImage = await loadImage("/static/brand-mark.svg");
  await Promise.all(Object.entries(icons).map(async ([name, path]) => {
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${path}</svg>`;
    iconImages[name] = await loadImage(`data:image/svg+xml,${enc(svg)}`);
  }));
  $$("[data-i]").forEach(el => { el.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">${icons[el.dataset.i] || icons.book}</svg>`; });
}

// Tek döngüde yürütülen küçük animasyon sistemi.
const tweens = new Set();
function tween(duration, update) {
  return new Promise(resolve => {
    tweens.add({ start: performance.now(), duration: reduced ? 35 : duration, update, resolve });
  });
}
function updateTweens(now) {
  for (const task of tweens) {
    const t = clamp((now - task.start) / task.duration, 0, 1);
    task.update(1 - Math.pow(1 - t, 3));
    if (t === 1) { tweens.delete(task); task.resolve(); }
  }
}

// Canvas yazımı: tüm dokular aynı yazı tipi hazır olduktan sonra üretilir.
function canvas(width, height) {
  const c = document.createElement("canvas"); c.width = width; c.height = height; return c;
}
function round(ctx, x, y, w, h, r, fill) {
  ctx.beginPath(); ctx.roundRect(x, y, w, h, r); ctx.fillStyle = fill; ctx.fill();
}
function text(ctx, value, x, y, size = 24, weight = 500, color = "#0a0a0b") {
  ctx.font = `${weight} ${size}px Inter`; ctx.fillStyle = color; ctx.fillText(String(value ?? ""), x, y);
}
function wrap(ctx, value, x, y, width, size, maxLines, color, weight = 700) {
  ctx.font = `${weight} ${size}px Inter`; ctx.fillStyle = color;
  const words = String(value || "").split(/\s+/), lines = [];
  let line = "";
  for (const word of words) {
    const next = line ? `${line} ${word}` : word;
    if (ctx.measureText(next).width > width && line) { lines.push(line); line = word; }
    else line = next;
  }
  if (line) lines.push(line);
  const clipped = lines.slice(0, maxLines);
  clipped.forEach((value, i) => {
    let result = value;
    if (i === maxLines - 1 && lines.length > maxLines) result += "…";
    while (ctx.measureText(result).width > width && result.length > 1) result = result.slice(0, -2) + "…";
    ctx.fillText(result, x, y + i * size * 1.3);
  });
  return y + clipped.length * size * 1.3;
}
function texture(c) {
  const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 4; return tex;
}
function tabletTexture(item, high = false, back = false) {
  const c = canvas(high ? 672 : 168, high ? 960 : 240), ctx = c.getContext("2d");
  ctx.scale(c.width / 672, c.height / 960);
  const kind = item.kind || "paper", dark = kind === "topic" || kind === "trend" || hash(titleOf(item)) % 5 === 0;
  const fg = dark ? "#ffffff" : "#0a0a0b", muted = dark ? "#b4b4c0" : "#6b6b73";
  ctx.fillStyle = dark ? "#111113" : hash(titleOf(item)) % 3 ? "#ffffff" : "#e9efff";
  ctx.fillRect(0, 0, 672, 960);
  if (back) {
    ctx.drawImage(logoImage, 280, 180, 112, 112);
    wrap(ctx, titleOf(item), 50, 390, 572, 30, 6, fg);
    wrap(ctx, doiOf(item) ? `DOI · ${doiOf(item)}` : "AKADEMİK İZ · DİJİTAL KÜTÜPHANE", 50, 730, 572, 20, 4, muted, 500);
    return texture(c);
  }
  text(ctx, "09:41", 32, 36, 18, 600, fg);
  text(ctx, "Akademik İz", 240, 36, 18, 500, fg);
  round(ctx, 585, 19, 40, 17, 4, muted); round(ctx, 589, 23, 30, 9, 2, fg);
  ctx.fillStyle = itemColor(item); ctx.fillRect(0, 60, 672, 12);
  const source = kind === "person" ? "Akademisyen dosyası" : kind === "trend" ? "Türkiye gündemi" : kind === "topic" ? "Araştırma konusu" : item.source || item.sources?.[0] || "OpenAlex";
  round(ctx, 36, 110, 600, 52, 16, dark ? "#2a2a31" : "#e9efff");
  wrap(ctx, `${source}  ${item.year || ""}`, 54, 144, 560, 22, 1, dark ? "#c7d7ff" : "#1d4ed8", 600);
  let y = 235;
  if (kind === "person") {
    round(ctx, 36, 198, 112, 112, 26, "#e9efff");
    text(ctx, initials(item.name), 58, 270, 42, 800, "#1d4ed8"); y = 375;
  }
  y = wrap(ctx, titleOf(item), 36, y, 600, 44, 7, fg);
  if (kind === "trend") {
    text(ctx, `+%${number(item.growth)}`, 36, Math.min(y + 65, 700), 52, 800, "#34d399");
    text(ctx, `${number(item.count)} yayın`, 36, Math.min(y + 108, 750), 24, 500, muted);
  } else {
    const byline = kind === "person" ? item.institution : (item.authors || []).slice(0, 3).map(authorName).join(", ");
    wrap(ctx, byline || "Akademik İz koleksiyonu", 36, Math.min(y + 40, 725), 600, 23, 3, muted, 500);
  }
  ctx.fillStyle = dark ? "#37373c" : "#e9e9ec"; ctx.fillRect(36, 830, 600, 2);
  ctx.drawImage(logoImage, 36, 861, 45, 45);
  text(ctx, "AKADEMİK İZ", 95, 890, 20, 700, fg);
  const stat = kind === "person" ? `${number(item.papers)} yayın` : `${number(item.citations)} atıf`;
  ctx.textAlign = "right"; text(ctx, stat, 632, 890, 22, 600, muted); ctx.textAlign = "left";
  return texture(c);
}
function labelTexture(title, subtitle = "", icon = "book", color = "#111113") {
  const c = canvas(1024, 224), ctx = c.getContext("2d");
  round(ctx, 0, 0, 1024, 224, 20, color);
  if (iconImages[icon]) ctx.drawImage(iconImages[icon], 38, 52, 78, 78);
  wrap(ctx, title, 145, 100, 835, 45, 1, "#fff");
  text(ctx, subtitle, 145, 163, 27, 500, "#d4d4d8");
  return texture(c);
}

// Sahne, paylaşılan geometri ve malzemeler.
let scene, camera, renderer, floor, board, boardCanvas, boardTexture, monitorScreen, dock;
const raycaster = new THREE.Raycaster(), pointer = new THREE.Vector2(0, 0);
const hitTargets = [], colliders = [], shelves = new Map(), stands = [], tablets = new Set();
const materials = {}, geometries = {}, sharedResources = new Set();
const state = { entered: false, held: null, busy: false, yaw: 0, pitch: 0, hover: null, target: null, reader: null, parent: null, pcReturn: null };
const keys = new Set();
const data = { recent: [], favorites: [], topics: [], people: [], trending: [], categories: [] };
const hold = new THREE.Group();
const v3 = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);
function shared(resource) { sharedResources.add(resource); return resource; }
function standard(color, extra = {}) { return new THREE.MeshStandardMaterial({ color, roughness: .65, ...extra }); }
function box(parent, w, h, d, x, y, z, material) {
  const mesh = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), material);
  mesh.position.set(x, y, z); mesh.receiveShadow = true; mesh.castShadow = true; parent.add(mesh); return mesh;
}
function cylinder(parent, r1, r2, h, x, y, z, material, segments = 20) {
  const mesh = new THREE.Mesh(new THREE.CylinderGeometry(r1, r2, h, segments), material);
  mesh.position.set(x, y, z); mesh.castShadow = true; mesh.receiveShadow = true; parent.add(mesh); return mesh;
}
function roundedGeometry(w, h, d, r) {
  const s = new THREE.Shape(), x = -w / 2, y = -h / 2;
  s.moveTo(x + r, y); s.lineTo(x + w - r, y); s.quadraticCurveTo(x + w, y, x + w, y + r);
  s.lineTo(x + w, y + h - r); s.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  s.lineTo(x + r, y + h); s.quadraticCurveTo(x, y + h, x, y + h - r);
  s.lineTo(x, y + r); s.quadraticCurveTo(x, y, x + r, y);
  const g = new THREE.ExtrudeGeometry(s, { depth: d, bevelEnabled: false, curveSegments: 6 });
  g.translate(0, 0, -d / 2); return g;
}
function plane(parent, width, height, map, x, y, z) {
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(width, height), new THREE.MeshBasicMaterial({ map, toneMapped: false }));
  mesh.position.set(x, y, z); parent.add(mesh); return mesh;
}
function hit(mesh, action, title, extra = {}) {
  mesh.userData.interaction = { action, title, ...extra }; hitTargets.push(mesh); return mesh;
}
function obstacle(x, z, w, d) { colliders.push({ x: x - w / 2 - .28, X: x + w / 2 + .28, z: z - d / 2 - .28, Z: z + d / 2 + .28 }); }
function setup() {
  scene = new THREE.Scene(); scene.background = new THREE.Color("#f4f4f5");
  camera = new THREE.PerspectiveCamera(65, innerWidth / innerHeight, .025, 65);
  camera.position.set(0, 1.6, 5.4); camera.rotation.order = "YXZ";
  scene.add(camera); camera.add(hold);
  renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 1.75)); renderer.setSize(innerWidth, innerHeight);
  renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.outputColorSpace = THREE.SRGBColorSpace; renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.1;
  $("#stage").append(renderer.domElement);
  materials.white = shared(standard("#fafafa")); materials.wall = shared(standard("#ededf0"));
  materials.black = shared(standard("#17171a", { metalness: .35 }));
  materials.wood = shared(standard("#d9b98e")); materials.teal = shared(standard("#90aaa3"));
  materials.glass = shared(standard("#e9f2ff", { transparent: true, opacity: .22, roughness: .15 }));
  materials.silver = shared(standard("#aeb6bf", { metalness: .8, roughness: .3 }));
  materials.front = shared(standard("#08080a", { roughness: .22 }));
  geometries.body = shared(roundedGeometry(.19, .265, .008, .012));
  geometries.glass = shared(roundedGeometry(.183, .256, .001, .01));
  geometries.screen = shared(new THREE.PlaneGeometry(.166, .237));
  geometries.camera = shared(new THREE.CircleGeometry(.0017, 10));
  const ambient = new THREE.HemisphereLight(0xf4f8ff, 0xb6a28b, 2.1); scene.add(ambient);
  const sun = new THREE.DirectionalLight(0xfff6e9, 2.4); sun.position.set(7, 5, 1);
  sun.castShadow = true; sun.shadow.mapSize.set(2048, 2048);
  Object.assign(sun.shadow.camera, { left: -10, right: 10, top: 9, bottom: -9, near: .5, far: 30 });
  sun.shadow.bias = -.0004; sun.shadow.normalBias = .025; scene.add(sun);
  buildRoom(); buildShelves(); buildBoard(); buildDesk();
  restorePosition(); resize(); bindScene();
  renderer.setAnimationLoop(frame);
}
function woodTexture() {
  const c = canvas(1024, 1024), ctx = c.getContext("2d");
  ctx.fillStyle = "#dcc39e"; ctx.fillRect(0, 0, 1024, 1024);
  let seed = 15;
  const rand = () => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed / 4294967296; };
  for (let row = 0; row < 16; row++) {
    for (let col = -1; col < 4; col++) {
      const x = col * 330 + (row % 2) * 165;
      ctx.fillStyle = `hsl(35 39% ${70 + rand() * 12}%)`; ctx.fillRect(x + 1, row * 64 + 1, 328, 62);
      ctx.strokeStyle = "#79563418";
      for (let i = 0; i < 12; i++) {
        ctx.beginPath(); ctx.moveTo(x + rand() * 40, row * 64 + i * 5);
        ctx.bezierCurveTo(x + 90, row * 64 + i * 5 + 3, x + 180, row * 64 + i * 5 - 2, x + 325, row * 64 + i * 5); ctx.stroke();
      }
    }
  }
  const tex = texture(c); tex.wrapS = tex.wrapT = THREE.RepeatWrapping; tex.repeat.set(4, 4); return tex;
}
function buildRoom() {
  floor = new THREE.Mesh(new THREE.PlaneGeometry(16, 13), standard("#fff", { map: woodTexture(), roughness: .8 }));
  floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; scene.add(floor);
  hit(floor, "floor", "Buraya yürü");
  box(scene, 16, 3.4, .15, 0, 1.7, -6.58, materials.wall);
  box(scene, 16, 3.4, .15, 0, 1.7, 6.58, materials.wall);
  box(scene, .15, 3.4, 13, -8.08, 1.7, 0, materials.wall);
  box(scene, .15, 3.4, 13, 8.08, 1.7, 0, materials.wall);
  box(scene, 16, .1, 13, 0, 3.45, 0, materials.white);
  for (const z of [-4, 0, 4]) {
    const win = new THREE.Group(); win.position.set(7.99, 1.95, z); win.rotation.y = -Math.PI / 2; scene.add(win);
    box(win, 2.6, 2.15, .07, 0, 0, 0, materials.black);
    box(win, 2.48, 2.03, .08, 0, 0, .025, shared(standard("#e3f0fc", { emissive: "#c8dff5", emissiveIntensity: .75 })));
    box(win, .045, 2.05, .09, 0, 0, .08, materials.black);
  }
  box(scene, 1.45, 2.65, .06, 0, 1.325, 6.46, materials.wood);
  box(scene, .06, .4, .07, -.5, 1.2, 6.39, materials.black);
  const sign = labelTexture("AKADEMİK İZ KÜTÜPHANESİ", "Araştır · keşfet · oku");
  plane(scene, 5.3, .52, sign, -.9, 2.95, -6.46);
  for (const x of [-4, 0, 4]) for (const z of [-3, 2]) {
    cylinder(scene, .012, .012, .45, x, 3.1, z, materials.black, 8);
    cylinder(scene, .13, .3, .16, x, 2.82, z, materials.black);
    cylinder(scene, .27, .27, .014, x, 2.73, z, shared(standard("#fff6db", { emissive: "#fff2d2", emissiveIntensity: 1.5 })));
  }
  plant(-6.9, -5.5); plant(6.9, -5.5); plant(7, 5.3);
  chair(6.8, 2.4, -Math.PI / 2); chair(6.8, 4, -Math.PI / 2);
  cylinder(scene, .35, .35, .05, 6.1, .55, 3.25, materials.wood);
  cylinder(scene, .045, .045, .52, 6.1, .26, 3.25, materials.black); obstacle(6.1, 3.25, .7, .7);
  const rug = new THREE.Mesh(new THREE.CircleGeometry(1.12, 64), standard("#d8dddb"));
  rug.rotation.x = -Math.PI / 2; rug.position.set(-.8, .006, -1.4); rug.receiveShadow = true; scene.add(rug);
  cylinder(scene, .42, .42, .05, -.8, .5, -1.4, materials.wood);
  cylinder(scene, .15, .2, .47, -.8, .24, -1.4, materials.black); obstacle(-.8, -1.4, .85, .85);
  const totem = new THREE.Group(); totem.position.set(2.2, 0, 4.7); totem.rotation.y = -.25; scene.add(totem);
  box(totem, .85, 1.85, .1, 0, .925, 0, materials.black);
  const c = canvas(420, 840), ctx = c.getContext("2d"); ctx.fillStyle = "#111113"; ctx.fillRect(0, 0, 420, 840);
  ctx.drawImage(logoImage, 42, 44, 65, 65); text(ctx, "BÖLÜMLER", 42, 175, 29, 700, "#fff");
  ["← Kişisel raflar", "↑ Okuma köşesi", "← Gündem panosu", "→ Konu bulucu", "Liste görünümü ↗"].forEach((t, i) => text(ctx, t, 42, 280 + i * 90, 25, 500, "#eee"));
  hit(plane(totem, .77, 1.54, texture(c), 0, 1, .056), "sections", "Bölümler ve liste görünümü");
  obstacle(2.2, 4.7, .85, .15);
}
function plant(x, z) {
  cylinder(scene, .24, .18, .44, x, .22, z, materials.white);
  const green = shared(standard("#567b54"));
  for (let i = 0; i < 9; i++) {
    const angle = i * 2.4, mesh = new THREE.Mesh(new THREE.SphereGeometry(1, 8, 6), green);
    mesh.scale.set(.08, .37, .035); mesh.position.set(x + Math.sin(angle) * .14, .75 + (i % 3) * .11, z + Math.cos(angle) * .14);
    mesh.rotation.set(Math.cos(angle) * .6, angle, Math.sin(angle) * .6); scene.add(mesh);
  }
  obstacle(x, z, .5, .5);
}
function chair(x, z, yaw = 0) {
  const group = new THREE.Group(); group.position.set(x, 0, z); group.rotation.y = yaw; scene.add(group);
  box(group, .72, .18, .7, 0, .43, 0, materials.teal);
  box(group, .72, .65, .15, 0, .77, -.3, materials.teal);
  for (const side of [-1, 1]) {
    box(group, .12, .3, .67, side * .39, .61, 0, materials.teal);
    for (const depth of [-1, 1]) cylinder(group, .025, .025, .35, side * .28, .17, depth * .26, materials.black, 8);
  }
  obstacle(x, z, .9, .9);
}

// Raflar ve tablet ömrü: yalnızca ekrana özel dokular yenilenir.
function makeTablet(item, parent, position, rotation = 0, owner = null) {
  const group = new THREE.Group(); group.position.copy(position); group.rotation.x = -.2; group.rotation.y = rotation;
  parent.add(group);
  const body = new THREE.Mesh(geometries.body, hash(titleOf(item)) % 2 ? materials.silver : materials.black); group.add(body);
  const glass = new THREE.Mesh(geometries.glass, materials.front); glass.position.z = .005; group.add(glass);
  const low = tabletTexture(item), screenMaterial = new THREE.MeshBasicMaterial({ map: low, color: "#dcdcdc", toneMapped: false });
  const screen = new THREE.Mesh(geometries.screen, screenMaterial); screen.position.z = .006; group.add(screen);
  const cam = new THREE.Mesh(geometries.camera, materials.black); cam.position.set(0, .125, .006); group.add(cam);
  const mark = new THREE.Mesh(new THREE.PlaneGeometry(.04, .04), new THREE.MeshBasicMaterial({ map: logoTexture, toneMapped: false }));
  mark.rotation.y = Math.PI; mark.position.z = -.0045; group.add(mark);
  const entry = { group, screen, low, item, owner, parent, home: position.clone(), homeQ: group.quaternion.clone(), high: null, back: null, mark, hover: 0, temporary: !owner };
  hit(body, "tablet", titleOf(item), { tablet: entry }); tablets.add(entry); return entry;
}
let logoTexture;
function removeTablet(entry) {
  if (state.held === entry) return;
  entry.group.removeFromParent(); tablets.delete(entry);
  for (let i = hitTargets.length - 1; i >= 0; i--) if (hitTargets[i].userData.interaction?.tablet === entry) hitTargets.splice(i, 1);
  entry.low.dispose(); entry.high?.dispose(); entry.screen.material.dispose();
  entry.mark.geometry.dispose(); entry.mark.material.dispose();
  if (entry.back) { entry.back.material.map.dispose(); entry.back.material.dispose(); entry.back.geometry.dispose(); }
}
function upgradeTablet(entry) {
  entry.high?.dispose(); entry.high = tabletTexture(entry.item, true);
  entry.screen.material.map = entry.high; entry.screen.material.color.set("#fff");
  if (!entry.back) {
    entry.back = plane(entry.group, .13, .19, tabletTexture(entry.item, true, true), 0, 0, -.005);
    entry.back.rotation.y = Math.PI; entry.mark.visible = false;
  }
}
function downgradeTablet(entry) {
  entry.screen.material.map = entry.low; entry.screen.material.color.set("#dcdcdc");
  entry.high?.dispose(); entry.high = null;
  if (entry.back) {
    entry.back.removeFromParent(); entry.back.material.map.dispose(); entry.back.material.dispose(); entry.back.geometry.dispose(); entry.back = null;
  }
  entry.mark.visible = true;
}
function makeShelf(id, title, x, z, yaw, empty) {
  const root = new THREE.Group(); root.position.set(x, 0, z); root.rotation.y = yaw; scene.add(root);
  for (const side of [-1, 1]) {
    box(root, .035, 2.1, .4, side * 1.35, 1.05, 0, materials.black);
    box(root, .035, 2.1, .035, side * 1.35, 1.05, .22, materials.black);
  }
  const levels = [.36, .83, 1.3, 1.77];
  levels.forEach(y => {
    box(root, 2.74, .045, .43, 0, y, 0, materials.wood);
    box(root, 2.68, .055, .008, 0, y + .045, .215, materials.glass);
  });
  const sign = plane(root, 2.7, .39, labelTexture(title, "0 e-kitap"), 0, 2.18, .03);
  hit(sign, "shelf", title, { shelfId: id });
  const shelf = { id, title, root, sign, levels, entries: [], items: [], empty, emptyCard: null, dirty: false, point: root.localToWorld(v3(0, 1.6, 1.6)) };
  shelves.set(id, shelf);
  if (yaw) obstacle(x, z, .5, 2.8); else obstacle(x, z, 2.8, .5);
  return shelf;
}
function buildShelves() {
  logoTexture = shared(new THREE.Texture(logoImage)); logoTexture.colorSpace = THREE.SRGBColorSpace; logoTexture.needsUpdate = true;
  makeShelf("recent", "Son okuduklarım", -4.7, -6.23, 0, "Henüz okunan yayın yok");
  makeShelf("favorites", "Kaydettiklerim", -1.5, -6.23, 0, "Henüz kaydedilen yayın yok");
  makeShelf("topics", "Son konularım", 1.7, -6.23, 0, "Henüz araştırılan konu yok");
  makeShelf("people", "Akademisyen dosyaları", -7.73, 3, Math.PI / 2, "Henüz akademisyen dosyası yok");
}
function refillShelf(id, items) {
  const shelf = shelves.get(id); if (!shelf) return;
  shelf.items = items;
  if (state.held?.owner === shelf) { shelf.dirty = true; return; }
  shelf.dirty = false; shelf.entries.forEach(removeTablet); shelf.entries = [];
  if (shelf.emptyCard) {
    shelf.emptyCard.removeFromParent(); shelf.emptyCard.material.map.dispose(); shelf.emptyCard.material.dispose(); shelf.emptyCard.geometry.dispose(); shelf.emptyCard = null;
  }
  shelf.sign.material.map.dispose(); shelf.sign.material.map = labelTexture(shelf.title, `${items.length} e-kitap · liste için tıkla`);
  if (!items.length) {
    shelf.emptyCard = plane(shelf.root, 1.7, .37, labelTexture(shelf.empty, "İçerikler burada görünecek", "book", "#6b6b73"), 0, 1.47, .05); return;
  }
  const order = [2, 1, 3, 0];
  items.slice(0, 40).forEach((item, i) => {
    const tier = order[Math.floor(i / 10)], x = -1.17 + (i % 10) * .26;
    shelf.entries.push(makeTablet(item, shelf.root, v3(x, shelf.levels[tier] + .158, .08), 0, shelf));
  });
}
function updatePersonalShelves() {
  data.recent = readStore("academic-recent-papers").slice(0, 24).map(x => ({ ...x, kind: "paper" }));
  data.topics = readStore("academic-recent-views").filter(x => x.kind === "topic").map(x => ({ ...x, kind: "topic" }));
  refillShelf("recent", data.recent); refillShelf("topics", data.topics);
}

// Dört yüzlü, tekerlekli dönen okuma standları.
function buildStand(category, index) {
  const angle = -Math.PI / 2 + Math.PI / 7 + index * Math.PI * 2 / 7;
  const base = new THREE.Group(); base.position.set(-.8 + Math.cos(angle) * 2.5, 0, -1.4 + Math.sin(angle) * 2.5); scene.add(base);
  for (let i = 0; i < 2; i++) {
    const beam = box(base, .84, .04, .07, 0, .11, 0, materials.black); beam.rotation.y = i * Math.PI / 2;
  }
  for (const [x, z] of [[-.37, 0], [.37, 0], [0, -.37], [0, .37]]) {
    const wheel = cylinder(base, .055, .055, .04, x, .06, z, materials.black, 12); wheel.rotation.z = Math.PI / 2;
  }
  cylinder(base, .035, .035, 1.5, 0, .85, 0, materials.silver);
  const tower = new THREE.Group(); tower.position.y = 1.12; base.add(tower);
  const core = box(tower, .51, .95, .51, 0, 0, 0, materials.black);
  const stand = { category, base, tower, faces: [], entries: [], items: [], pauseUntil: 0, point: v3(base.position.x, 1.6, base.position.z + 1.2), title: category.label, id: `stand-${category.id}` };
  hit(core, "stand", `${category.label} · sürükle, döndür`, { stand });
  for (let face = 0; face < 4; face++) {
    const f = new THREE.Group(); f.rotation.y = face * Math.PI / 2; tower.add(f); stand.faces.push(f);
    const header = plane(f, .62, .23, labelTexture(category.label, "Okuma köşesi", category.icon, colors[category.id] || "#111113"), 0, .68, .29);
    hit(header, "stand-list", category.label, { stand });
    for (const y of [-.35, .07]) {
      box(f, .61, .025, .12, 0, y - .14, .3, materials.wood);
      box(f, .6, .045, .006, 0, y - .1, .36, materials.glass);
    }
  }
  obstacle(base.position.x, base.position.z, .9, .9); stands.push(stand);
  return stand;
}
async function loadStands() {
  try {
    const result = await api("/api/reading"); data.categories = result.items || [];
    await Promise.allSettled(data.categories.slice(0, 7).map(async (category, index) => {
      const stand = buildStand(category, index);
      try {
        const response = await api(`/api/reading/${enc(category.id)}`, { timeout: 120000 });
        stand.items = (response.items || []).map(item => ({ ...item, kind: "paper", category: category.id }));
        stand.items.slice(0, 16).forEach((item, i) => {
          const face = stand.faces[Math.floor(i / 4)];
          stand.entries.push(makeTablet(item, face, v3((i % 2 ? 1 : -1) * .145, Math.floor((i % 4) / 2) ? -.35 : .07, .31), 0, stand));
        });
        stand.status = stand.items.length ? "" : "Bu kategoride yayın bulunamadı.";
      } catch (error) { stand.status = error.message; }
    }));
  } catch (error) { toast(`Okuma köşesi: ${error.message}`); }
}

// Tek dokulu gündem panosu; UV koordinatları kartlara dönüştürülür.
let boardHover = -1;
const boardRects = [];
function buildBoard() {
  const root = new THREE.Group(); root.position.set(-7.88, 1.7, -2); root.rotation.y = Math.PI / 2; scene.add(root);
  box(root, 3.3, 1.9, .08, 0, 0, 0, materials.black);
  boardCanvas = canvas(1920, 1080); boardTexture = texture(boardCanvas);
  board = plane(root, 3.2, 1.8, boardTexture, 0, 0, .046);
  hit(board, "board", "Türkiye gündemi"); drawBoard();
}
function drawBoard(message = "Türkiye gündemi yükleniyor…") {
  const ctx = boardCanvas.getContext("2d"); ctx.fillStyle = "#f4f4f5"; ctx.fillRect(0, 0, 1920, 1080);
  text(ctx, "Türkiye gündemi", 55, 78, 45, 800);
  text(ctx, "Son 12 ayda en hızlı büyüyen konular · OpenAlex", 55, 125, 25, 500, "#6b6b73");
  round(ctx, 1680, 50, 160, 50, 25, "#e3f6ee"); text(ctx, "● Canlı", 1700, 84, 25, 600, "#047857");
  boardRects.length = 0;
  if (!data.trending.length) text(ctx, message, 60, 260, 32, 500, "#6b6b73");
  data.trending.slice(0, 15).forEach((item, i) => {
    const x = 50 + i % 5 * 368, y = 175 + Math.floor(i / 5) * 292, w = 350, h = 270;
    const offset = boardHover === i ? -8 : 0;
    boardRects.push({ x, y, w, h });
    ctx.save(); if (boardHover === i) { ctx.shadowColor = "#0003"; ctx.shadowBlur = 22; ctx.shadowOffsetY = 9; }
    round(ctx, x, y + offset, w, h, 18, "#fff"); ctx.restore();
    round(ctx, x + 14, y + offset + 12, w - 28, 5, 2, palette[i % palette.length]);
    text(ctx, `#${i + 1}`, x + 22, y + 57 + offset, 23, 700, "#6b6b73");
    ctx.save(); ctx.translate(x + w - 35, y + 43 + offset); ctx.rotate(.35);
    ctx.fillStyle = palette[i % palette.length]; ctx.beginPath(); ctx.arc(0, 0, 8, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = "#6b6b73"; ctx.beginPath(); ctx.moveTo(0, 6); ctx.lineTo(0, 23); ctx.stroke(); ctx.restore();
    wrap(ctx, titleOf(item), x + 22, y + 105 + offset, w - 44, 27, 3, "#111113");
    round(ctx, x + 20, y + 209 + offset, 150, 38, 18, "#e3f6ee");
    text(ctx, `+%${number(item.growth)}`, x + 32, y + 236 + offset, 22, 700, "#047857");
    text(ctx, `${number(item.count)} yayın`, x + 180, y + 235 + offset, 20, 500, "#6b6b73");
  });
  boardTexture.needsUpdate = true;
}
function boardIndex(uv) {
  if (!uv) return -1;
  const x = uv.x * 1920, y = (1 - uv.y) * 1080;
  return boardRects.findIndex(r => x >= r.x && x <= r.x + r.w && y >= r.y && y <= r.y + r.h);
}
async function loadTrending() {
  try { const result = await api("/api/topics/trending", { timeout: 180000 }); data.trending = (result.items || []).map(x => ({ ...x, kind: "trend" })); drawBoard("Henüz gündem verisi yok."); }
  catch (error) { drawBoard(`Gündem alınamadı: ${error.message}`); }
}

// Masa ve bilgisayar ekranı.
function buildDesk() {
  const root = new THREE.Group(); root.position.set(6.6, 0, -1); root.rotation.y = -Math.PI / 2; scene.add(root);
  box(root, 1.65, .07, .8, 0, .76, 0, materials.wood);
  for (const x of [-.7, .7]) for (const z of [-.3, .3]) box(root, .05, .73, .05, x, .36, z, materials.black);
  box(root, .38, .025, .26, 0, .81, -.14, materials.black);
  box(root, .055, .22, .055, 0, .94, -.2, materials.black);
  box(root, .92, .58, .035, 0, 1.22, -.2, materials.black);
  const c = canvas(1000, 600), ctx = c.getContext("2d"); ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, 1000, 600);
  ctx.drawImage(logoImage, 42, 35, 40, 40); text(ctx, "Akademik İz", 100, 64, 28, 700);
  text(ctx, "Ne okumak istiyorsun?", 70, 220, 46, 800);
  round(ctx, 70, 275, 860, 75, 16, "#f4f4f5"); text(ctx, "Konu, yayın veya araştırma alanı…", 95, 322, 26, 400, "#6b6b73");
  round(ctx, 70, 400, 250, 65, 14, "#111113"); text(ctx, "Konu bulucuyu aç", 93, 441, 23, 600, "#fff");
  monitorScreen = plane(root, .87, .52, texture(c), 0, 1.22, -.178); hit(monitorScreen, "pc", "Konu bulucu · otur");
  box(root, .55, .018, .18, 0, .81, .17, materials.wall);
  box(root, .23, .035, .15, .6, .815, .05, materials.black);
  dock = new THREE.Group(); dock.position.set(.6, .97, .05); root.add(dock);
  chair(5.45, -1, -Math.PI / 2); obstacle(6.6, -1, .8, 1.65);
}

// Çarpışma, yürüyüş ve kameraya bağlı tablet hareketi.
function inside(p, c) { return p.x > c.x && p.x < c.X && p.z > c.z && p.z < c.Z; }
function canMove(from, to) {
  if (Math.abs(to.x) > 7.65 || Math.abs(to.z) > 6.15) return false;
  return !colliders.some(c => !inside(from, c) && inside(to, c));
}
function move(dx, dz) {
  const from = camera.position, candidate = from.clone();
  candidate.x += dx; if (canMove(from, candidate)) from.x = candidate.x;
  candidate.copy(from); candidate.z += dz; if (canMove(from, candidate)) from.z = candidate.z;
}
function cancelWalk() {
  state.target?.resolve(false); state.target = null;
}
function pathTo(goal) {
  const step = .35, origin = camera.position.clone();
  const gridKey = (x, z) => `${x},${z}`;
  const index = p => [Math.round(p.x / step), Math.round(p.z / step)];
  const start = index(origin), end = index(goal), queue = [start], seen = new Map([[gridKey(...start), null]]);
  let cursor = 0, found = null;
  while (cursor < queue.length && cursor < 6000) {
    const node = queue[cursor++], point = v3(node[0] * step, 1.6, node[1] * step);
    if (Math.hypot(node[0] - end[0], node[1] - end[1]) <= 1) { found = node; break; }
    for (const [dx, dz] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
      const next = [node[0] + dx, node[1] + dz], key = gridKey(...next);
      if (seen.has(key)) continue;
      const p = v3(next[0] * step, 1.6, next[1] * step);
      if (!canMove(point, p)) continue;
      seen.set(key, node); queue.push(next);
    }
  }
  if (!found) return [];
  const result = [];
  while (found && gridKey(...found) !== gridKey(...start)) {
    result.unshift(v3(found[0] * step, 1.6, found[1] * step)); found = seen.get(gridKey(...found));
  }
  if (canMove(result.at(-1) || origin, goal)) result.push(goal.clone());
  return result;
}
function walkTo(goal, lookAt = null) {
  cancelWalk();
  goal.y = 1.6; goal.x = clamp(goal.x, -7.6, 7.6); goal.z = clamp(goal.z, -6.1, 6.1);
  const route = pathTo(goal);
  if (!route.length) { toast("Bu noktaya doğrudan ulaşılamıyor; biraz yana ilerle."); return Promise.resolve(false); }
  return new Promise(resolve => { state.target = { route, resolve, lookAt }; });
}
function facePoint(point, amount = 1) {
  const dx = point.x - camera.position.x, dz = point.z - camera.position.z;
  const target = Math.atan2(-dx, -dz), difference = Math.atan2(Math.sin(target - state.yaw), Math.cos(target - state.yaw));
  state.yaw += difference * amount; state.pitch *= 1 - amount;
}
function approachPoint(object) {
  const world = object.getWorldPosition(v3());
  const normal = v3(0, 0, 1).applyQuaternion(object.getWorldQuaternion(new THREE.Quaternion())); normal.y = 0; normal.normalize();
  return world.clone().addScaledVector(normal, 1.1).setY(1.6);
}
async function takeTablet(entry) {
  if (state.busy || state.held) return;
  cancelWalk(); state.busy = true; clearHover();
  state.held = entry;
  upgradeTablet(entry); scene.updateMatrixWorld(true); hold.attach(entry.group);
  const start = entry.group.position.clone(), rotation = entry.group.quaternion.clone();
  const destination = v3(.03, -.045, -.5), q = new THREE.Quaternion();
  await tween(650, t => { entry.group.position.lerpVectors(start, destination, t); entry.group.quaternion.slerpQuaternions(rotation, q, t); });
  state.busy = false; $("#rotateHint").hidden = false; $("#help").hidden = true; renderActions();
}
async function putBack() {
  if (!state.held || state.busy) return;
  state.busy = true; const entry = state.held;
  $("#actions").hidden = true; $("#rotateHint").hidden = true;
  scene.updateMatrixWorld(true); scene.attach(entry.group);
  const start = entry.group.position.clone(), rotation = entry.group.quaternion.clone();
  await tween(600, t => {
    entry.parent.updateWorldMatrix(true, false);
    const end = entry.parent.localToWorld(entry.home.clone());
    const q = entry.parent.getWorldQuaternion(new THREE.Quaternion()).multiply(entry.homeQ);
    entry.group.position.lerpVectors(start, end, t); entry.group.quaternion.slerpQuaternions(rotation, q, t);
  });
  entry.parent.add(entry.group); entry.group.position.copy(entry.home); entry.group.quaternion.copy(entry.homeQ);
  downgradeTablet(entry); state.held = null; state.busy = false; $("#help").hidden = false;
  if (entry.temporary) removeTablet(entry);
  if (entry.owner?.dirty) refillShelf(entry.owner.id, entry.owner.items);
}
function savedMatch(item) {
  const doi = doiOf(item), title = fold(titleOf(item));
  return data.favorites.find(p => (doi && doiOf(p) === doi) || fold(titleOf(p)) === title);
}
function renderActions() {
  const entry = state.held; if (!entry) return;
  const item = entry.item, person = item.kind === "person", paper = !["person", "topic", "trend"].includes(item.kind);
  $("#actions").innerHTML = `<button class="btn primary" data-act="open">Aç</button>${paper ? `<button class="btn" data-act="pdf">PDF</button><button class="btn ${savedMatch(item) ? "saved" : ""}" data-act="save">${savedMatch(item) ? "Kaydedildi" : "Kaydet"}</button>` : ""}${person ? link(`/#/profil/${enc(item.id)}`, "Profili aç") : ""}<button class="btn" data-act="return">${item.kind === "trend" ? "Panoya bırak" : "Yerine koy"}</button>`;
  $("#actions").hidden = false;
}
function blocked() { return !state.entered || state.busy || !$("#reader").hidden || !$("#panel").hidden || !$("#pc").hidden; }
let pointerPosition = { x: innerWidth / 2, y: innerHeight / 2 }, drag = null;
function rayAt(x, y) {
  pointer.set(x / innerWidth * 2 - 1, -(y / innerHeight) * 2 + 1);
  scene.updateMatrixWorld(true); raycaster.setFromCamera(pointer, camera);
  return raycaster.intersectObjects(hitTargets.filter(mesh => mesh.parent && mesh.visible), false)[0] || null;
}
function clearHover() {
  state.hover = null; $("#hint").hidden = true; $("#stage").classList.remove("point");
  if (boardHover !== -1) { boardHover = -1; drawBoard(); }
}
function updateHover() {
  if (blocked() || state.held || drag?.moved) { clearHover(); return; }
  const intersection = rayAt(pointerPosition.x, pointerPosition.y);
  state.hover = intersection;
  if (!intersection || intersection.object === floor) { $("#hint").hidden = true; return; }
  const action = intersection.object.userData.interaction;
  const i = action.action === "board" ? boardIndex(intersection.uv) : -1;
  if (i !== boardHover) { boardHover = i; drawBoard(); }
  const title = i >= 0 ? titleOf(data.trending[i]) : action.title;
  const hint = intersection.distance > 2.6 ? "Yaklaş" : action.action === "tablet" || i >= 0 ? "Tıkla, al" : "Tıkla, aç";
  $("#hint").textContent = `${hint} · ${title}`; $("#hint").hidden = false;
  $("#hint").style.left = `${clamp(pointerPosition.x, 155, innerWidth - 155)}px`;
  $("#hint").style.top = `${Math.max(85, pointerPosition.y)}px`; $("#stage").classList.add("point");
}
async function activate(intersection) {
  if (!intersection || blocked() || state.held) return;
  const action = intersection.object.userData.interaction;
  if (action.action === "floor") { walkTo(intersection.point.clone()); return; }
  if (intersection.distance > 2.6) {
    const ok = await walkTo(approachPoint(intersection.object), intersection.point);
    if (!ok || blocked()) return;
  }
  if (action.action === "tablet") await takeTablet(action.tablet);
  if (action.action === "sections") openSections();
  if (action.action === "shelf") openList(shelves.get(action.shelfId));
  if (action.action === "stand" || action.action === "stand-list") openList(action.stand);
  if (action.action === "pc") await sitAtDesk();
  if (action.action === "board") {
    const index = boardIndex(intersection.uv);
    if (index < 0) { openList({ title: "Türkiye gündemi", items: data.trending }); return; }
    const local = board.worldToLocal(intersection.point.clone()); local.z += .015;
    const entry = makeTablet(data.trending[index], board, local); await takeTablet(entry);
  }
}
function bindScene() {
  const el = renderer.domElement;
  el.addEventListener("pointerdown", event => {
    if (event.button !== 0 || !event.isPrimary || blocked()) return;
    cancelWalk();
    const pick = !state.held ? rayAt(event.clientX, event.clientY) : null;
    const action = pick?.object.userData.interaction;
    const stand = action?.stand || (action?.tablet?.owner?.tower ? action.tablet.owner : null);
    drag = { id: event.pointerId, x: event.clientX, y: event.clientY, lastX: event.clientX, lastY: event.clientY, moved: false, stand: pick?.distance < 2.6 ? stand : null };
    el.setPointerCapture(event.pointerId);
  });
  el.addEventListener("pointermove", event => {
    pointerPosition = { x: event.clientX, y: event.clientY };
    if (!drag || drag.id !== event.pointerId) return;
    if (event.pointerType === "mouse" && !event.buttons) { endPointer(event, false); return; }
    const dx = event.clientX - drag.lastX, dy = event.clientY - drag.lastY;
    drag.lastX = event.clientX; drag.lastY = event.clientY;
    if (Math.hypot(event.clientX - drag.x, event.clientY - drag.y) > 5) drag.moved = true;
    if (!drag.moved) return;
    if (state.held) { state.held.group.rotation.y += dx * .012; state.held.group.rotation.x += dy * .012; }
    else if (drag.stand) { drag.stand.tower.rotation.y += dx * .012; drag.stand.pauseUntil = performance.now() + 2500; }
    else { state.yaw -= dx * .004; state.pitch = clamp(state.pitch - dy * .003, -.95, .95); }
  });
  function endPointer(event, click) {
    if (!drag || (event.pointerId != null && event.pointerId !== drag.id)) return;
    const old = drag; drag = null;
    if (el.hasPointerCapture(old.id)) el.releasePointerCapture(old.id);
    if (old.stand) old.stand.pauseUntil = performance.now() + 2500;
    if (click && !old.moved) activate(rayAt(event.clientX, event.clientY));
  }
  el.addEventListener("pointerup", event => endPointer(event, true));
  el.addEventListener("pointercancel", event => endPointer(event, false));
  el.addEventListener("lostpointercapture", event => endPointer(event, false));
  window.addEventListener("blur", event => { keys.clear(); endPointer(event, false); cancelWalk(); });
  el.addEventListener("wheel", event => {
    if (blocked()) return; event.preventDefault(); cancelWalk();
    if (state.held) state.held.group.position.z = clamp(state.held.group.position.z - event.deltaY * .0005, -.8, -.32);
    else {
      const delta = clamp(event.deltaY * (event.deltaMode === 1 ? .04 : .003), -.6, .6);
      move(Math.sin(state.yaw) * delta, Math.cos(state.yaw) * delta);
    }
  }, { passive: false });
  window.addEventListener("resize", resize);
  window.addEventListener("keydown", event => {
    if (event.key === "Escape") { event.preventDefault(); escapeLayer(); return; }
    if (event.target.matches("input, textarea, select") || event.ctrlKey || event.metaKey || event.altKey) return;
    if (event.key.toLowerCase() === "m") { event.preventDefault(); if (!state.busy) openSections(); return; }
    if (blocked() || state.held) return;
    if (["w", "a", "s", "d", "arrowup", "arrowdown", "arrowleft", "arrowright", "shift"].includes(event.key.toLowerCase())) {
      event.preventDefault(); cancelWalk(); keys.add(event.key.toLowerCase());
    }
  });
  window.addEventListener("keyup", event => keys.delete(event.key.toLowerCase()));
  document.addEventListener("visibilitychange", () => { keys.clear(); if (document.hidden) { cancelWalk(); savePosition(); } });
  window.addEventListener("pagehide", savePosition);
  el.addEventListener("webglcontextlost", event => { event.preventDefault(); toast("3B görüntü durdu. Liste görünümünden okumaya devam edebilirsin."); });
}
function resize() {
  if (!renderer) return;
  camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight); renderer.setPixelRatio(Math.min(devicePixelRatio, 1.75));
}
let lastFrame = 0, lastHover = 0, walkPhase = 0, lastSave = 0;
function frame(now) {
  const dt = Math.min(.04, (now - lastFrame) / 1000 || .016); lastFrame = now;
  updateTweens(now);
  if (document.hidden) return;
  if (!blocked() && !state.held) {
    let moving = false;
    if (state.target) {
      const point = state.target.route[0], dx = point.x - camera.position.x, dz = point.z - camera.position.z, length = Math.hypot(dx, dz);
      if (length < .08) {
        state.target.route.shift();
        if (!state.target.route.length) {
          const target = state.target; state.target = null;
          if (target.lookAt) facePoint(target.lookAt); target.resolve(true);
        }
      } else { move(dx / length * Math.min(length, dt * 2.7), dz / length * Math.min(length, dt * 2.7)); moving = true; }
    } else {
      if (keys.has("arrowleft")) state.yaw += dt * 1.4;
      if (keys.has("arrowright")) state.yaw -= dt * 1.4;
      const forward = Number(keys.has("w") || keys.has("arrowup")) - Number(keys.has("s") || keys.has("arrowdown"));
      const side = Number(keys.has("d")) - Number(keys.has("a"));
      const speed = (keys.has("shift") ? 3.6 : 2) * dt / Math.max(1, Math.hypot(forward, side));
      move((-Math.sin(state.yaw) * forward + Math.cos(state.yaw) * side) * speed, (-Math.cos(state.yaw) * forward - Math.sin(state.yaw) * side) * speed);
      moving = !!(forward || side);
    }
    if (moving) walkPhase += dt * 8;
    camera.position.y = 1.6 + (moving && !reduced ? Math.sin(walkPhase) * .012 : 0);
  }
  camera.rotation.set(state.pitch, state.yaw, 0, "YXZ");
  for (const stand of stands) {
    const hovered = state.hover?.object.userData.interaction;
    if (!reduced && now > stand.pauseUntil && hovered?.stand !== stand && hovered?.tablet?.owner !== stand && drag?.stand !== stand) stand.tower.rotation.y += dt * .075;
  }
  for (const entry of tablets) {
    if (entry === state.held) continue;
    const hover = state.hover?.object.userData.interaction?.tablet === entry && state.hover.distance <= 2.6;
    entry.hover = THREE.MathUtils.damp(entry.hover, hover ? .04 : 0, 14, dt);
    entry.group.position.copy(entry.home); entry.group.position.z += entry.hover;
  }
  if (now - lastHover > 70) { updateHover(); lastHover = now; }
  if (now - lastSave > 5000) { savePosition(); lastSave = now; }
  renderer.render(scene, camera);
}
function savePosition() {
  if (!state.entered || !camera || state.busy || !$("#pc").hidden) return;
  try { localStorage.setItem("akademik-kutuphane-yer", JSON.stringify({ x: camera.position.x, z: camera.position.z, yaw: state.yaw, pitch: state.pitch })); } catch { /* Depolama kapalı olabilir. */ }
}
function restorePosition() {
  try {
    const p = JSON.parse(localStorage.getItem("akademik-kutuphane-yer"));
    if (!p || ![p.x, p.z, p.yaw, p.pitch].every(Number.isFinite)) return;
    camera.position.set(clamp(p.x, -7.6, 7.6), 1.6, clamp(p.z, -6.1, 6.1));
    state.yaw = p.yaw; state.pitch = clamp(p.pitch, -.95, .95);
  } catch { /* Varsayılan giriş konumu korunur. */ }
}

// HTML tablet okuyucu ve istek iptalleri.
let readerVersion = 0, readerAbort = null, pdfAbort = null, pdfBlob = null, readerReturn = null;
function showLayer(id) {
  keys.clear(); cancelWalk(); clearHover();
  const layer = $(id); layer.hidden = false;
  layer.dataset.previousFocus = ""; layer._previousFocus = document.activeElement;
  requestAnimationFrame(() => layer.querySelector("button, input, [tabindex]")?.focus());
}
function hideLayer(id) {
  const layer = $(id); layer.hidden = true; layer._previousFocus?.focus?.();
}
function releasePdf() {
  pdfAbort?.abort(); pdfAbort = null;
  $("#readerPdf").replaceChildren();
  if (pdfBlob) { URL.revokeObjectURL(pdfBlob); pdfBlob = null; }
}
async function openReader(item, { child = false, pdf = false } = {}) {
  if (state.busy) return;
  if (!child) state.parent = null;
  const first = $("#reader").hidden;
  if (first && state.held) {
    state.busy = true; const group = state.held.group;
    readerReturn = { p: group.position.clone(), q: group.quaternion.clone() };
    const targetQ = new THREE.Quaternion().setFromEuler(new THREE.Euler(0, 0, Math.PI / 2));
    await tween(400, t => {
      group.position.lerpVectors(readerReturn.p, v3(0, 0, -.3), t);
      group.quaternion.slerpQuaternions(readerReturn.q, targetQ, t);
    });
    group.visible = false; state.busy = false;
  }
  readerAbort?.abort(); readerAbort = new AbortController(); releasePdf();
  const version = ++readerVersion; state.reader = item;
  $("#readerTitle").textContent = titleOf(item);
  $("#readerBack").hidden = !state.parent;
  $("#actions").hidden = true; $("#rotateHint").hidden = true;
  const special = ["topic", "trend", "person"].includes(item.kind);
  $("#pdfTab").disabled = special;
  selectReaderTab(false); showLayer("#reader");
  if (item.kind === "topic" || item.kind === "trend") await topicReader(item, version);
  else if (item.kind === "person") personReader(item);
  else {
    paperReader(item); rememberPaper(item);
    if (doiOf(item)) fillBrief(item, version, readerAbort.signal);
    if (pdf) showPdf(item);
  }
}
async function closeReader() {
  if (state.busy) return;
  ++readerVersion; readerAbort?.abort(); releasePdf(); hideLayer("#reader"); state.reader = null; state.parent = null;
  if (state.held) {
    state.busy = true; const group = state.held.group; group.visible = true;
    const start = group.position.clone(), q = group.quaternion.clone();
    const destination = readerReturn || { p: v3(.03, -.045, -.5), q: new THREE.Quaternion() };
    await tween(350, t => { group.position.lerpVectors(start, destination.p, t); group.quaternion.slerpQuaternions(q, destination.q, t); });
    state.busy = false; renderActions(); $("#rotateHint").hidden = false;
  }
}
function selectReaderTab(pdf) {
  $("#summaryTab").setAttribute("aria-selected", String(!pdf)); $("#pdfTab").setAttribute("aria-selected", String(pdf));
  $("#readerSummary").hidden = pdf; $("#readerPdf").hidden = !pdf;
}
function badges(item) {
  const sources = [...new Set([item.source, ...(Array.isArray(item.sources) ? item.sources : [])].filter(Boolean))];
  return `<div class="chips">${sources.map(source => `<span class="chip ${String(source).includes("TR") ? "teal" : "blue"}">${esc(source)}</span>`).join("")}${item.year ? `<span class="chip">${esc(item.year)}</span>` : ""}</div>`;
}
function paperReader(item) {
  $("#pageLeft").innerHTML = `${badges(item)}<h1>${esc(titleOf(item))}</h1><p>${esc(item.venue || "Yayın yeri belirtilmemiş")}${item.year ? ` · ${esc(item.year)}` : ""}</p>
    <h3>Yazarlar</h3><div id="readerAuthors" class="authors"></div><h3>Künye</h3><dl class="meta"><dt>Yıl</dt><dd>${esc(item.year || "Belirtilmemiş")}</dd><dt>Yayın yeri</dt><dd>${esc(item.venue || "Belirtilmemiş")}</dd><dt>Atıf</dt><dd>${number(item.citations)}</dd><dt>DOI</dt><dd>${doiOf(item) ? link(`https://doi.org/${enc(doiOf(item))}`, doiOf(item), "") : "Belirtilmemiş"}</dd></dl>`;
  $("#pageRight").innerHTML = `<h3>Özet</h3><div id="readerAbstract" class="abstract">${esc(item.abstract || "Bu kayıt için özet henüz yok.")}</div><div class="page-actions"><button class="btn primary" data-reader="pdf">PDF oku</button><button class="btn" data-reader="save">${savedMatch(item) ? "Kaydedildi" : "Kaydet"}</button>${link(searchLink(item), "Akademik İz'de ara")}${link(sourceUrl(item), "Kaynağa git")}</div>`;
  renderAuthors(item.authors || []);
}
function renderAuthors(authors) {
  if (!$("#readerAuthors")) return;
  const sorted = [...authors].sort((a, b) => {
    const tr = value => (value?.institutions || []).some(x => ["TR", "TUR", "Turkey", "Türkiye"].includes(x.country));
    return Number(tr(b)) - Number(tr(a));
  });
  $("#readerAuthors").innerHTML = sorted.slice(0, 8).map(author => {
    const name = authorName(author), institutions = typeof author === "object" ? author.institutions || [] : [];
    return `<div class="author">${link(`/#/akademisyenler?q=${enc(name)}`, name, "")}${institutions.map(inst => inst.uni_id ? link(`/#/universite/${enc(inst.uni_id)}`, inst.name, "inst tr") : `<span class="inst">${esc(inst.name)}</span>`).join("")}</div>`;
  }).join("") + (sorted.length > 8 ? `<span class="chip">+${sorted.length - 8} yazar</span>` : sorted.length ? "" : '<p class="muted">Yazar bilgisi yok.</p>');
}
async function fillBrief(item, version, signal) {
  try {
    const result = await api(`/api/paper/brief?doi=${enc(doiOf(item))}`, { signal });
    if (version !== readerVersion || state.reader !== item) return;
    if (!item.abstract && result.abstract) { item.abstract = result.abstract; $("#readerAbstract").textContent = result.abstract; rememberPaper(item); }
    if (result.items?.length) renderAuthors(result.items);
  } catch (error) {
    if (error.name !== "AbortError" && version === readerVersion && !item.abstract) $("#readerAbstract").textContent = `Özet alınamadı. ${error.message}`;
  }
}
async function topicReader(item, version) {
  $("#pageLeft").innerHTML = `<span class="chip ${item.kind === "trend" ? "ok" : "blue"}">${item.kind === "trend" ? "Türkiye gündemi" : "Araştırma konusu"}</span><h1>${esc(titleOf(item))}</h1>${item.kind === "trend" ? `<dl class="meta"><dt>Son 12 ay</dt><dd>${number(item.count)} yayın</dd><dt>Geçen yıl</dt><dd>${number(item.prev)} yayın</dd><dt>Büyüme</dt><dd>+%${number(item.growth)}</dd></dl>` : '<p>Bu konudaki yayınlar ve araştırmalar.</p>'}<div class="page-actions">${link(searchLink(item), "Bütün kaynaklarda ara")}</div>`;
  $("#pageRight").innerHTML = `<h3>İçindekiler</h3>${busy("Yayınlar yükleniyor…")}`;
  try {
    const query = item.kind === "trend" ? `id=${enc(String(item.id).split("/").at(-1))}` : `q=${enc(item.name || item.id || titleOf(item))}`;
    const result = await api(`/api/topic-works?${query}`, { timeout: 90000, signal: readerAbort.signal });
    if (version !== readerVersion) return;
    const items = result.items || [];
    $("#pageRight").innerHTML = `<h3>İçindekiler</h3>${result.scope === "world" ? '<p class="muted">Türkiye adresli az, dünya geneli</p>' : ""}<ol class="toc">${items.map((paper, i) => `<li><button data-paper-index="${i}"><span><b>${esc(titleOf(paper))}</b><small>${esc(paper.venue || "")} · ${esc(paper.year || "")}</small></span><em>${number(paper.citations)} atıf</em></button></li>`).join("")}</ol>${items.length ? "" : '<p class="muted">Bu konu için yayın bulunamadı.</p>'}`;
    $$("[data-paper-index]").forEach(button => { button.onclick = () => { state.parent = item; openReader({ ...items[Number(button.dataset.paperIndex)], kind: "paper" }, { child: true }); }; });
  } catch (error) { if (version === readerVersion && error.name !== "AbortError") $("#pageRight").innerHTML = errorHtml(error); }
}
function personReader(item) {
  $("#pageLeft").innerHTML = `<div class="profile-av">${esc(initials(item.name))}</div><h1>${esc(item.name)}</h1><p>${esc(item.title || "")}</p><p>${esc(item.institution || "")}</p><span class="chip blue">${number(item.papers)} yayın</span>`;
  $("#pageRight").innerHTML = `<h3>İlgi alanları</h3><div class="chips">${(item.interests || []).map(x => `<span class="chip">${esc(x)}</span>`).join("") || '<p class="muted">İlgi alanı bilgisi bulunmuyor.</p>'}</div><div class="page-actions">${link(`/#/profil/${enc(item.id)}`, "Profili aç", "btn primary")}</div>`;
}
function rememberPaper(item) {
  const record = {};
  for (const key of ["title", "year", "venue", "doi", "url", "source", "sources", "citations", "id", "pdf"]) if (item[key] !== undefined) record[key] = item[key];
  record.title = titleOf(item); record.authors = (item.authors || []).slice(0, 6); record.abstract = String(item.abstract || "").slice(0, 1500); record.at = Date.now();
  const recent = readStore("academic-recent-papers").filter(p => fold(titleOf(p)) !== fold(record.title));
  writeStore("academic-recent-papers", [record, ...recent].slice(0, 24)); updatePersonalShelves();
}
async function showPdf(item) {
  if (!item || ["topic", "trend", "person"].includes(item.kind)) return;
  selectReaderTab(true);
  if (pdfBlob) return;
  releasePdf(); pdfAbort = new AbortController(); const signal = pdfAbort.signal, version = readerVersion;
  $("#readerPdf").innerHTML = busy("Açık erişim PDF hazırlanıyor…");
  try {
    const response = await fetch(`/api/pdf?url=${enc(safeUrl(item.pdf))}&doi=${enc(doiOf(item))}`, { signal });
    if (!response.ok || response.headers.get("content-type")?.includes("application/json")) {
      const result = await response.json().catch(() => ({}));
      throw new Error(typeof result.detail === "string" ? result.detail : `HTTP ${response.status}`);
    }
    const blob = await response.blob();
    if (version !== readerVersion || signal.aborted) return;
    if (!blob.type.includes("pdf")) throw new Error("Sunucu okunabilir bir PDF döndürmedi.");
    pdfBlob = URL.createObjectURL(blob);
    const iframe = document.createElement("iframe"); iframe.title = `${titleOf(item)} · PDF`; iframe.src = pdfBlob;
    $("#readerPdf").replaceChildren(iframe);
  } catch (error) {
    if (signal.aborted || version !== readerVersion) return;
    $("#readerPdf").innerHTML = `<div class="pdf-fail"><h3>PDF açılamadı</h3><p>${esc(error.message)}</p>${link(sourceUrl(item), "Yayıncı sayfasına git")}</div>`;
  }
}
let saving = false;
async function toggleSave(item) {
  if (saving) return; saving = true;
  try {
    const saved = savedMatch(item);
    if (saved) {
      await api(`/api/favorites/papers/${enc(saved.key)}`, { method: "DELETE" });
      data.favorites = data.favorites.filter(p => p.key !== saved.key); toast("Kaydedilenlerden çıkarıldı.");
    } else {
      const result = await api("/api/favorites/papers", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ item }) });
      const record = result.item || result;
      if (record.key) data.favorites.unshift({ ...item, ...record, kind: "paper" });
      else { const response = await api("/api/favorites"); data.favorites = (response.papers || []).map(p => ({ ...p, kind: "paper" })); }
      toast("Yayın kaydedildi.");
    }
    refillShelf("favorites", data.favorites);
    if (state.held) renderActions();
    if (!$("#reader").hidden) { $("#actions").hidden = true; const button = $('[data-reader="save"]'); if (button) button.textContent = savedMatch(state.reader) ? "Kaydedildi" : "Kaydet"; }
  } catch (error) { toast(error.message); }
  finally { saving = false; }
}

// Bilgisayarda konu arama ve dock üzerinden tablete gönderme.
let pcVersion = 0, pcAbort = null;
async function sitAtDesk() {
  if (state.busy || state.held) return;
  state.pcReturn = { p: camera.position.clone(), yaw: state.yaw, pitch: state.pitch };
  state.busy = true; cancelWalk();
  const start = camera.position.clone(), yaw = state.yaw, pitch = state.pitch;
  const angle = Math.atan2(Math.sin(-Math.PI / 2 - yaw), Math.cos(-Math.PI / 2 - yaw));
  await tween(650, t => { camera.position.lerpVectors(start, v3(5.45, 1.2, -1), t); state.yaw = yaw + angle * t; state.pitch = pitch * (1 - t); });
  state.busy = false; showLayer("#pc"); renderPcRecent(); $("#pcInput").focus();
}
async function leaveDesk() {
  if (state.busy) return;
  pcAbort?.abort(); ++pcVersion; hideLayer("#pc");
  if (!state.pcReturn) return;
  state.busy = true; const start = camera.position.clone(), yaw = state.yaw, pitch = state.pitch, end = state.pcReturn;
  await tween(450, t => { camera.position.lerpVectors(start, end.p, t); state.yaw = yaw + (end.yaw - yaw) * t; state.pitch = pitch + (end.pitch - pitch) * t; });
  state.pcReturn = null; state.busy = false;
}
function renderPcRecent() {
  $("#pcRecent").innerHTML = data.topics.slice(0, 6).map((item, i) => `<button class="chip" data-recent-topic="${i}">${esc(titleOf(item))}</button>`).join("");
  $$("[data-recent-topic]").forEach(button => { button.onclick = () => { $("#pcInput").value = titleOf(data.topics[Number(button.dataset.recentTopic)]); searchPc(); }; });
}
async function searchPc() {
  const query = $("#pcInput").value.trim(); if (!query) return;
  const previous = readStore("academic-recent-views").filter(item => !(item.kind === "topic" && fold(item.name || item.id) === fold(query)));
  writeStore("academic-recent-views", [{ kind: "topic", id: query, name: query, at: Date.now() }, ...previous].slice(0, 30));
  updatePersonalShelves(); renderPcRecent();
  pcAbort?.abort(); pcAbort = new AbortController(); const version = ++pcVersion;
  $("#pcResults").innerHTML = busy("Konuya ilişkin yayınlar aranıyor…");
  try {
    const result = await api(`/api/topic-works?q=${enc(query)}`, { timeout: 90000, signal: pcAbort.signal });
    if (version !== pcVersion) return;
    const papers = result.items || [];
    $("#pcResults").innerHTML = `${result.scope === "world" ? '<p class="muted">Türkiye adresli az, dünya geneli</p>' : ""}${papers.map((item, i) => `<div class="result"><div><button class="back-link" data-pc-paper="${i}">${esc(titleOf(item))}</button><p>${esc(item.venue || "")} · ${esc(item.year || "")} · ${number(item.citations)} atıf</p></div><button class="btn sm" data-send="${i}">Tablete gönder</button></div>`).join("")}${papers.length ? "" : '<p class="muted">Yayın bulunamadı.</p>'}<div class="foot-note">${link(`/#/ara?q=${enc(query)}`, "Akademik İz'de bütün kaynaklarda ara")}</div>`;
    $$("[data-pc-paper]").forEach(button => { button.onclick = () => openReader({ ...papers[Number(button.dataset.pcPaper)], kind: "paper" }); });
    $$("[data-send]").forEach(button => { button.onclick = async () => {
      const item = { ...papers[Number(button.dataset.send)], kind: "paper" };
      await leaveDesk();
      const entry = makeTablet(item, dock, v3()); entry.screen.material.color.set("#050505");
      await tween(450, t => entry.screen.material.color.setScalar(.02 + t * .84));
      await takeTablet(entry);
    }; });
  } catch (error) { if (version === pcVersion && error.name !== "AbortError") $("#pcResults").innerHTML = errorHtml(error); }
}

// Bölüm paneli ve sahneden bağımsız erişilebilir listeler.
function collectionList() {
  return [
    { id: "recent", title: "Son okuduklarım", items: data.recent, point: v3(-4.7, 1.6, -4.7) },
    { id: "favorites", title: "Kaydettiklerim", items: data.favorites, point: v3(-1.5, 1.6, -4.7) },
    { id: "topics", title: "Son konularım", items: data.topics, point: v3(1.7, 1.6, -4.7) },
    { id: "people", title: "Akademisyen dosyaları", items: data.people, point: v3(-6.2, 1.6, 3) },
    { id: "reading", title: "Okuma köşesi", items: stands.flatMap(stand => stand.items), point: v3(-.8, 1.6, 2.5) },
    { id: "trending", title: "Gündem panosu", items: data.trending, point: v3(-5.6, 1.6, -2) },
    { id: "pc", title: "Konu bulucu", items: [], point: v3(4.7, 1.6, -1) },
  ];
}
function openSections() {
  if (state.busy) return;
  const collections = collectionList();
  $("#panelBody").innerHTML = `<h2 id="panelTitle">Bölümler</h2><p>Kütüphanede bir bölüme git veya içerikleri liste olarak aç.</p><div class="zones">${collections.map((section, i) => `<div class="zone"><div><b>${esc(section.title)}</b><span>${section.id === "pc" ? "Konu arama bilgisayarı" : `${section.items.length} içerik`}</span><div class="shelf-tools">${renderer ? `<button class="btn sm" data-go="${i}">Bölüme git</button>` : ""}<button class="btn sm" data-list="${i}">${section.id === "pc" ? "Ara" : "Liste görünümü"}</button></div></div></div>`).join("")}</div>`;
  showLayer("#panel");
  $$("[data-go]").forEach(button => { button.onclick = async () => {
    const section = collections[Number(button.dataset.go)]; hideLayer("#panel");
    if (state.held) await putBack();
    const target = section.id === "trending" ? v3(-7.8, 1.7, -2) : section.id === "people" ? v3(-7.7, 1.6, 3) : section.id === "pc" ? v3(6.6, 1.2, -1) : section.id === "reading" ? v3(-.8, 1.6, -1.4) : v3(section.point.x, 1.6, -6.2);
    const ok = await walkTo(section.point.clone(), target);
    if (ok && section.id === "pc") await sitAtDesk();
  }; });
  $$("[data-list]").forEach(button => { button.onclick = () => {
    const section = collections[Number(button.dataset.list)];
    if (section.id === "pc") { hideLayer("#panel"); showLayer("#pc"); renderPcRecent(); }
    else openList(section);
  }; });
}
function openList(collection) {
  if (!collection) return;
  $("#panelBody").innerHTML = `<h2 id="panelTitle">${esc(collection.title)}</h2><p>${collection.items.length} içerik · okumak için seç</p><div class="shelf-tools"><button class="btn sm" id="allSections">← Bölümler</button></div>${collection.status ? `<p class="muted">${esc(collection.status)}</p>` : ""}<div class="list">${collection.items.map((item, i) => `<button data-list-item="${i}"><span class="sw" style="background:${itemColor(item)}"></span><span><b>${esc(titleOf(item))}</b><small>${esc(item.venue || item.institution || item.source || "Akademik İz")}${item.year ? ` · ${esc(item.year)}` : ""}</small></span></button>`).join("") || '<p class="muted">Bu raf henüz boş. Uygulamada açtığın ve kaydettiğin içerikler burada görünecek.</p>'}</div>`;
  showLayer("#panel"); $("#allSections").onclick = openSections;
  $$("[data-list-item]").forEach(button => { button.onclick = () => { hideLayer("#panel"); openReader(collection.items[Number(button.dataset.listItem)]); }; });
}
function escapeLayer() {
  if (state.busy) return;
  if (!$("#reader").hidden) closeReader();
  else if (!$("#panel").hidden) hideLayer("#panel");
  else if (!$("#pc").hidden) leaveDesk();
  else if (state.held) putBack();
  else cancelWalk();
}
function bindInterface() {
  $("#mapBtn").onclick = openSections;
  bindLifecycle();
  $("#listEntry").onclick = openSections;
  $("#enterBtn").onclick = enter;
  $("#pcForm").onsubmit = event => { event.preventDefault(); searchPc(); };
  $("[data-pc-close]").onclick = leaveDesk;
  $$("[data-close]").forEach(button => { button.onclick = () => button.closest("#reader") ? closeReader() : hideLayer("#panel"); });
  $("#readerBack").onclick = () => { const parent = state.parent; state.parent = null; if (parent) openReader(parent); };
  $("#summaryTab").onclick = () => selectReaderTab(false);
  $("#pdfTab").onclick = () => showPdf(state.reader);
  $("#actions").onclick = event => {
    const action = event.target.closest("[data-act]")?.dataset.act, item = state.held?.item;
    if (!item || state.busy) return;
    if (action === "open") openReader(item);
    if (action === "pdf") openReader(item, { pdf: true });
    if (action === "save") toggleSave(item);
    if (action === "return") putBack();
  };
  $("#reader").addEventListener("click", event => {
    const action = event.target.closest("[data-reader]")?.dataset.reader;
    if (action === "pdf") showPdf(state.reader);
    if (action === "save") toggleSave(state.reader);
  });
  // Odak, en üstteki açık iletişim kutusunda kalır.
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && !renderer) { escapeLayer(); return; }
    if (event.key !== "Tab") return;
    const layer = [$("#reader"), $("#panel"), $("#pc")].find(el => !el.hidden);
    if (!layer) return;
    const focusable = [...layer.querySelectorAll('a[href], button:not(:disabled), input, [tabindex="0"]')].filter(el => el.getClientRects().length);
    const first = focusable[0], last = focusable.at(-1);
    if (!first) return;
    if (event.shiftKey && (document.activeElement === first || !layer.contains(document.activeElement))) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && (document.activeElement === last || !layer.contains(document.activeElement))) { event.preventDefault(); first.focus(); }
  });
  window.addEventListener("storage", event => {
    if (["academic-recent-papers", "academic-recent-views"].includes(event.key)) updatePersonalShelves();
  });
}
function enter() {
  if (!renderer) { openSections(); return; }
  state.entered = true; $("#splash").hidden = true; $("#hudTop").hidden = false; $("#help").hidden = false;
}
async function loadPersonal() {
  updatePersonalShelves();
  const results = await Promise.allSettled([
    api("/api/favorites", { timeout: 6000 }),
    api("/api/chats", { timeout: 6000 }),
  ]);
  if (results[0].status === "fulfilled") data.favorites = (results[0].value.papers || []).map(item => ({ ...item, kind: "paper" }));
  if (results[1].status === "fulfilled") data.people = (Array.isArray(results[1].value) ? results[1].value : []).map(item => ({ ...item, kind: "person" }));
  refillShelf("favorites", data.favorites); refillShelf("people", data.people);
  const failures = results.filter(result => result.status === "rejected").length;
  $("#splashStatus").textContent = failures ? "Bazı raf verileri alınamadı. Mevcut içeriklerle giriş yapabilirsin." : "Kütüphane hazır. Gündem ve okuma köşesi arka planda güncelleniyor.";
  if (data.recent[0]) {
    $("#continueBtn").hidden = false; $("#continueBtn").textContent = `Okumaya devam et · ${titleOf(data.recent[0])}`;
    $("#continueBtn").onclick = () => { enter(); openReader(data.recent[0]); };
  }
}
async function boot() {
  bindInterface();
  try {
    await loadAssets(); setup();
  } catch (error) {
    renderer?.setAnimationLoop(null); renderer?.dispose(); renderer = null;
    $("#splashStatus").innerHTML = `3B kütüphane başlatılamadı. Tarayıcıda WebGL desteğini kontrol et. Liste görünümünü kullanabilir veya <a href="/#/ara">konu aramasına dönebilirsin</a>.`;
    await loadPersonal();
    $("#splashStatus").innerHTML = `3B görüntü kullanılamıyor. Liste görünümünden okuyabilir veya <a href="/#/ara">konu aramasına dönebilirsin</a>.`;
    return;
  }
  loadTrending(); loadStands();
  await loadPersonal();
  $("#enterBtn").disabled = false;
}
// GPU kaynaklarını ve geçici PDF adreslerini sayfa ömrüyle sınırla.
let disposed = false;
function disposeScene() {
  if (disposed) return;
  disposed = true;
  renderer?.setAnimationLoop(null);
  readerAbort?.abort(); pcAbort?.abort(); pdfAbort?.abort();
  if (pdfBlob) URL.revokeObjectURL(pdfBlob);
  pdfBlob = null;
  const geometrySet = new Set(), materialSet = new Set(), textureSet = new Set();
  scene?.traverse(object => {
    if (object.geometry) geometrySet.add(object.geometry);
    const list = Array.isArray(object.material) ? object.material : object.material ? [object.material] : [];
    for (const material of list) {
      materialSet.add(material);
      for (const value of Object.values(material)) if (value?.isTexture) textureSet.add(value);
    }
  });
  for (const entry of tablets) {
    textureSet.add(entry.low);
    if (entry.high) textureSet.add(entry.high);
  }
  for (const resource of sharedResources) {
    if (resource.isTexture) textureSet.add(resource);
    else if (resource.isMaterial) materialSet.add(resource);
    else if (resource.isBufferGeometry) geometrySet.add(resource);
  }
  textureSet.forEach(resource => resource.dispose());
  materialSet.forEach(resource => resource.dispose());
  geometrySet.forEach(resource => resource.dispose());
  renderer?.dispose();
  clearTimeout(toastTimer);
}
function bindLifecycle() {
  window.addEventListener("pagehide", event => {
    savePosition();
    // Geri/ileri önbelleğinde sahneyi koru, tamamen çıkarken bırak.
    if (!event.persisted) disposeScene();
    else renderer?.setAnimationLoop(null);
  });
  window.addEventListener("pageshow", event => {
    if (event.persisted && renderer && !disposed) {
      lastFrame = performance.now();
      renderer.setAnimationLoop(frame);
    }
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      drag = null;
      keys.clear();
      clearHover();
    } else lastFrame = performance.now();
  });
  window.addEventListener("focus", async () => {
    if (!state.entered || disposed) return;
    updatePersonalShelves();
    // Ana uygulamada kaydedilen yayınlar kütüphaneye dönünce görünür.
    try {
      const result = await api("/api/favorites", { timeout: 6000 });
      if (disposed) return;
      data.favorites = (result.papers || []).map(item => ({ ...item, kind: "paper" }));
      refillShelf("favorites", data.favorites);
      if (state.held && $("#reader").hidden) renderActions();
    } catch { /* Mevcut raf, geçici ağ hatasında korunur. */ }
  });
}
boot();
