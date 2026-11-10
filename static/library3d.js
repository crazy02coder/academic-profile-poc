// Akademik İz 3B kütüphanesi: açılış, girdi, kat geçişi ve veri yükleme.
// Sahne kurulumu library-upper.js / library-archive.js, HTML katmanları library-ui.js içinde.
import { THREE, updateTweens, tween, EYE, reduced, pickOf } from "./library-engine.js?v=lib5";
import * as ui from "./library-ui.js?v=lib5";
import { createUpper } from "./library-upper.js?v=lib5";

const { $, api, esc, enc, toast, store } = ui;
const keys = new Set();
const data = { recent: [], forYou: [], rising: [], trending: [], categories: [] };
let renderer = null, upper = null, archive = null, floor = null, entered = false, switching = false;
let pointer = { x: innerWidth / 2, y: innerHeight / 2 }, drag = null, lastHover = 0, lastSave = 0, last = performance.now(), seated = null;

const readStore = (key) => { try { const v = JSON.parse(localStorage.getItem(key) || "[]"); return Array.isArray(v) ? v : []; } catch { return []; } };
const readJson = (key) => { try { return JSON.parse(localStorage.getItem(key) || "null"); } catch { return null; } };
const blocked = () => !entered || switching || ui.layersOpen() || !!seated;

// ------------------------------------------------------------------ veri
function recentPapers() {
  return readStore("academic-recent-papers").filter((p) => p && p.title).map((p) => ({ ...p, kind: "paper" }));
}
async function loadPersonal() {
  data.recent = recentPapers();
  upper?.setShelf("recent", data.recent);
  const [fav, chats] = await Promise.allSettled([api("/api/favorites", { timeout: 8000 }), api("/api/chats", { timeout: 8000 })]);
  if (fav.status === "fulfilled") store.favorites = (fav.value.papers || []).map((p) => ({ ...p, kind: "paper" }));
  if (chats.status === "fulfilled") store.chats = Array.isArray(chats.value) ? chats.value : chats.value.items || [];
  upper?.setShelf("favorites", [...store.favorites].reverse());
  upper?.drawKiosk(store.chats);
  return [fav, chats].some((r) => r.status === "rejected");
}
async function loadStands() {
  try {
    const r = await api("/api/reading");
    data.categories = (r.items || []).slice(0, 6);
    await Promise.allSettled(data.categories.map(async (category, i) => {
      const stand = upper?.buildStand(i, category);
      stand && upper.standNote(stand, "Yükleniyor…");
      try {
        const shelf = await api(`/api/reading/${enc(category.id)}`, { timeout: 120000 });
        const items = (shelf.items || []).map((x) => ({ ...x, kind: "paper", category: category.id, category_label: category.label }));
        category.items = items;
        stand && upper.fillStand(stand, items);
      } catch { stand && upper.standNote(stand, "Yüklenemedi"); }
    }));
  } catch (e) { toast(`Okuma köşesi alınamadı: ${esc(e.message)}`); }
}
// Pencere dışı: Open-Meteo (sunucu üzerinden, sabit şehir). Önizleme: ?hava=kar|yagmur|bulut|kapali|gunes|sis|firtina&saat=21.5
async function loadWeather() {
  const qs = new URLSearchParams(location.search), alias = { kar: "snow", yagmur: "rain", bulut: "cloudy", kapali: "overcast", gunes: "clear", acik: "clear", sis: "fog", firtina: "storm" };
  let w = {};
  try { w = await (await fetch("/api/library/weather")).json(); } catch { w = {}; }
  const kind = alias[qs.get("hava")] || w.kind || "clear", hour = qs.has("saat") ? Number(qs.get("saat")) : null;
  upper?.setWeather({ kind, sunrise: w.sunrise || null, sunset: w.sunset || null, temp: w.temp ?? null, city: w.city || "", hour: Number.isFinite(hour) ? hour : null });
}
async function loadTrending() {
  try {
    const r = await api("/api/topics/trending", { timeout: 180000 });
    data.trending = Array.isArray(r) ? r : r.items || [];
    upper?.setBoard({ trending: data.trending, message: data.trending.length ? "" : "Henüz gündem verisi yok." });
  } catch (e) { upper?.setBoard({ message: `Gündem alınamadı: ${e.message}` }); }
}
async function loadForYou() {
  upper?.setShelf("forYou", [], "Sana göre hazırlanıyor…");
  try {
    const recent = [...readStore("academic-recent-views").filter((x) => x.kind === "topic").map((x) => x.name || x.id),
      ...readStore("academic-recent-papers").map((x) => (typeof x.topic === "string" ? x.topic : ""))].filter(Boolean).slice(0, 20).join(",");
    const r = await api(`/api/library/for-you?recent=${enc(recent)}`, { timeout: 150000 });
    data.forYou = (r.items || []).map((x) => ({ ...x, kind: "paper", category: "for-you" }));
    data.rising = (r.rising || []).map((x) => ({ ...x, reason: r.interests?.length ? `İlgi alanların: ${r.interests.slice(0, 2).join(", ")}` : "" }));
    upper?.setShelf("forYou", data.forYou, data.forYou.length ? "" : (r.message || ""));
    upper?.setBoard({ rising: data.rising });
  } catch { upper?.setShelf("forYou", [], "Şu an hazırlanamadı"); }
}
store.onChange = (what) => {
  if (what === "favorites") upper?.setShelf("favorites", [...store.favorites].reverse());
  if (what === "recent") { data.recent = recentPapers(); upper?.setShelf("recent", data.recent); }
};

// ------------------------------------------------------------------ eylemler
function act(action) {
  if (!action) return;
  switch (action.type) {
    case "item": ui.openPaper(action.item); break;
    case "list": ui.openList({ title: action.title, items: action.items, empty: action.empty, emblem: action.emblem }); break;
    case "topic": ui.openTopic(action.topic); break;
    case "pc": sitAtDesk(); break;
    case "kiosk": ui.openKiosk(store.chats); break;
    case "donate": ui.openDonation({ onScan: (on) => upper?.setScanning(on), onDone: () => archive?.refresh().catch(() => {}) }); break;
    case "door": goArchive(); break;
    case "exit": goUpper(); break;
    case "book": readArchiveBook(action.item, action.ref); break;
    case "bay": ui.openList({ title: action.title, items: action.items, emblem: "book", empty: "Bu rafa henüz kitap gelmedi.", subtitle: `${action.items.length} kitap · bağışlar ve açık erişim · okumak için seç`, onPick: (item) => { ui.closeModal(); readArchiveBook(item, null); } }); break;
    case "ladder": archive?.climb(action.ladder); break;
    case "walk": if (archive?.isClimbed?.() && floor === archive) archive.descend(); else floor.walker.walkTo(action.point.x, action.point.z); break;
    default: break;
  }
}
async function readArchiveBook(item, ref) {
  hover(null);
  if (ref) await archive.pullBook(ref);
  ui.openArchiveReader(item, { onClose: () => ref && archive.pushBook(ref) });
}
function shortestAngle(from, to) { let d = to - from; return Math.atan2(Math.sin(d), Math.cos(d)); }
async function sitAtDesk() {
  if (seated || floor !== upper) return;
  hover(null);
  const w = upper.walker, cam = upper.camera, pose = upper.seatPose();
  seated = { pos: cam.position.clone(), yaw: w.yaw, pitch: w.pitch };
  w.locked = true; w.goal = null;
  const start = cam.position.clone(), y0 = w.yaw, p0 = w.pitch, dy = shortestAngle(y0, pose.yaw);
  await tween(850, (k) => { cam.position.lerpVectors(start, pose.pos, k); w.yaw = y0 + dy * k; w.pitch = p0 + (pose.pitch - p0) * k; });
  ui.openPc({ onClose: standUp });
}
async function standUp() {
  if (!seated) return;
  const w = upper.walker, cam = upper.camera, back = new THREE.Vector3(6.75, EYE, .6);
  const start = cam.position.clone(), y0 = w.yaw, p0 = w.pitch;
  await tween(650, (k) => { cam.position.lerpVectors(start, back, k); w.pitch = p0 * (1 - k); });
  w.locked = false; seated = null;
}

// ------------------------------------------------------------------ kat geçişi
async function fade(on) {
  const el = $("#floorFade"); el.hidden = false;
  const anim = el.animate([{ opacity: on ? 0 : 1 }, { opacity: on ? 1 : 0 }], { duration: reduced ? 30 : on ? 420 : 520, fill: "forwards", easing: "ease-in-out" });
  await anim.finished.catch(() => {});
  if (!on) { el.hidden = true; anim.cancel(); }
}
function place(target, spot) {
  target.camera.position.set(spot.x, EYE, spot.z); target.walker.yaw = spot.yaw ?? 0; target.walker.pitch = spot.pitch ?? 0; target.walker.goal = null;
}
function setFloorUi() {
  const onArchive = floor === archive;
  document.body.classList.toggle("on-archive", onArchive);
  $("#floorName").textContent = onArchive ? "Arşiv katı" : "Üst kat · Okuma salonu";
  $("#floorBtn").innerHTML = onArchive ? `${ui.icon("arrow")}Üst kata çık` : `${ui.icon("book")}Arşiv katına in`;
}
async function goArchive(saved = null) {
  if (switching || floor === archive) return;
  switching = true; hover(null);
  try {
    if (!saved) await upper.playDoor();
    await fade(true);
    if (!archive) {
      $("#floorStatus").hidden = false;
      const mod = await import("./library-archive.js?v=lib5");
      archive = mod.createArchive();
      archive.resize();
      archive.load().catch(() => toast("Arşiv kitapları şu an alınamadı; raflar dekor kitaplarla duruyor."));
      $("#floorStatus").hidden = true;
    }
    floor = archive;
    place(archive, saved || archive.spawn);
    upper.resetDoor(); setFloorUi(); savePosition(true);
    await fade(false);
  } catch (e) { toast(`Arşiv katı açılamadı: ${esc(e.message)}`); floor = upper; upper.resetDoor(); await fade(false); }
  finally { switching = false; }
}
async function goUpper() {
  if (switching || floor === upper) return;
  switching = true; hover(null);
  if (archive?.isClimbed()) await archive.descend();
  await fade(true);
  floor = upper; place(upper, upper.doorSpawn); setFloorUi(); savePosition(true);
  await fade(false);
  switching = false;
}
function savePosition(force = false) {
  const now = performance.now(); if (!force && now - lastSave < 3000) return; lastSave = now;
  if (!floor || seated) return;
  const p = floor.camera.position;
  try { localStorage.setItem("akademik-kutuphane-yer", JSON.stringify({ floor: floor.id, x: +p.x.toFixed(2), z: +p.z.toFixed(2), yaw: +floor.walker.yaw.toFixed(3) })); } catch { /* isteğe bağlı */ }
}

// ------------------------------------------------------------------ girdi
function hover(info) {
  ui.hoverCard(info?.item || null, pointer.x, pointer.y);
  if (renderer) renderer.domElement.style.cursor = info?.grab ? "grab" : info?.clickable ? "pointer" : "default";
}
function bindInput() {
  const el = renderer.domElement;
  el.addEventListener("pointerdown", (e) => {
    if (blocked() || e.button !== 0) return;
    const hit = floor.raycast(e.clientX, e.clientY), pick = hit ? pickOf(hit.object) : null;
    drag = { id: e.pointerId, x: e.clientX, y: e.clientY, lx: e.clientX, ly: e.clientY, t: performance.now(), moved: false, hit,
      stand: floor === upper ? upper.standOf(hit) : null, ladder: pick?.type === "ladder" ? pick.ladder : null };
    floor.walker.goal = null;
    el.setPointerCapture(e.pointerId);
    if (drag.stand) el.style.cursor = "grabbing";
  });
  el.addEventListener("pointermove", (e) => {
    pointer = { x: e.clientX, y: e.clientY };
    if (!drag || drag.id !== e.pointerId) return;
    const now = performance.now(), dx = e.clientX - drag.lx, dy = e.clientY - drag.ly, dt = (now - drag.t) / 1000;
    drag.lx = e.clientX; drag.ly = e.clientY; drag.t = now;
    if (Math.hypot(e.clientX - drag.x, e.clientY - drag.y) > 5) drag.moved = true;
    if (!drag.moved) return;
    hover(null);
    if (drag.stand) upper.dragStand(drag.stand, dx, dt);
    else if (drag.ladder) archive.dragLadder(drag.ladder, (drag.ladder.side < 0 ? -dx : dx) * .01);
    else if (!floor.walker.locked) { floor.walker.yaw -= dx * .0034; floor.walker.pitch -= dy * .0028; }
  });
  const end = (e) => {
    if (!drag || drag.id !== e.pointerId) return;
    const d = drag; drag = null;
    if (el.hasPointerCapture(e.pointerId)) el.releasePointerCapture(e.pointerId);
    if (d.stand) upper.releaseStand(d.stand);
    if (!d.moved && e.type === "pointerup" && !blocked()) act(floor.click(d.hit));
  };
  el.addEventListener("pointerup", end); el.addEventListener("pointercancel", end);
  el.addEventListener("wheel", (e) => {
    if (blocked() || floor.walker.locked) return; e.preventDefault();
    const d = THREE.MathUtils.clamp(-e.deltaY * .0025, -.45, .45), w = floor.walker;
    w.move(-Math.sin(w.yaw) * d, -Math.cos(w.yaw) * d);
  }, { passive: false });
  addEventListener("keydown", (e) => {
    if (e.target.matches?.("input, textarea, select") || ui.layersOpen()) return;
    const k = e.key.toLowerCase();
    if (!entered) { if (k === "enter" && !$("#enterBtn").disabled) enter(); return; }
    if (["w", "a", "s", "d", "arrowup", "arrowdown", "arrowleft", "arrowright", "shift"].includes(k)) {
      e.preventDefault(); keys.add(k);
      if (floor === archive && archive.isClimbed() && k !== "shift") archive.descend();
    }
    if ((k === "q" || k === "e") && floor === upper) { const s = upper.nearestStand(); if (s) upper.turnStand(s, k === "q" ? -1 : 1); }
  });
  addEventListener("keyup", (e) => keys.delete(e.key.toLowerCase()));
  addEventListener("blur", () => { keys.clear(); drag = null; });
  addEventListener("resize", () => { renderer.setSize(innerWidth, innerHeight); upper.resize(); archive?.resize(); });
  $("#standLeft").onclick = () => { const s = upper.nearestStand(); if (s) upper.turnStand(s, -1); };
  $("#standRight").onclick = () => { const s = upper.nearestStand(); if (s) upper.turnStand(s, 1); };
}

// ------------------------------------------------------------------ kare döngüsü
const noKeys = new Set();
function frame(now) {
  const dt = Math.min(.05, (now - last) / 1000); last = now;
  updateTweens(now);
  if (!floor) return;
  floor.walker.update(dt, blocked() ? noKeys : keys);
  floor.update(dt, now);
  if (entered && !blocked() && !drag && now - lastHover > 70) {
    lastHover = now;
    const hit = floor.raycast(pointer.x, pointer.y), info = floor.hover(hit);
    if (floor === upper && upper.standOf(hit) && !info.item) info.grab = true;
    hover(info);
  } else if (blocked() && !drag) ui.hoverCard(null);
  const near = entered && !blocked() && floor === upper && upper.nearestStand();
  $("#standPad").hidden = !near;
  if (near) $("#standName").textContent = near.category.label;
  $("#climbHint").hidden = !(floor === archive && archive?.isClimbed());
  renderer.render(floor.scene, floor.camera);
  if (entered) savePosition();
}

// ------------------------------------------------------------------ liste görünümü (WebGL yoksa da çalışır)
function openSections() {
  const sections = [
    ["recent", "Son okuduklarım", "clock", data.recent], ["favorites", "Kaydettiklerim", "star", [...store.favorites].reverse()], ["forYou", "Senin için", "sparkle", data.forYou],
    ...data.categories.map((c) => [c.id, c.label, "book", c.items || []]),
  ];
  ui.openModal(`<div class="modal-heading"><span class="modal-emblem">${ui.icon("grid")}</span><div><h2>Kütüphane bölümleri</h2><p class="muted">Rafları liste olarak aç; 3B salonu kullanmadan da okuyabilirsin.</p></div></div>
    <div class="lib-sections">${sections.map(([id, title, icon, items], i) => `<button class="card lib-section" type="button" data-sec="${i}">${ui.icon(icon)}<b>${esc(title)}</b><small>${items.length} yayın</small></button>`).join("")}
      <button class="card lib-section" type="button" data-sec="trend">${ui.icon("flame")}<b>Türkiye gündemi</b><small>${data.trending.length} konu</small></button>
      <button class="card lib-section" type="button" data-sec="kiosk">${ui.icon("users")}<b>Akademisyen rehberi</b><small>${store.chats.length} profil</small></button>
      <button class="card lib-section" type="button" data-sec="donate">${ui.icon("upload")}<b>Bağış istasyonu</b><small>PDF bağışla</small></button></div>`, { wide: true });
  document.querySelectorAll("[data-sec]").forEach((b) => b.onclick = () => {
    const v = b.dataset.sec;
    if (v === "kiosk") { ui.closeModal(); setTimeout(() => ui.openKiosk(store.chats), 200); return; }
    if (v === "donate") { act({ type: "donate" }); return; }
    if (v === "trend") {
      ui.openModal(`<div class="modal-heading"><span class="modal-emblem">${ui.icon("flame")}</span><div><h2>Türkiye gündemi</h2><p class="muted">Son 12 ayda en hızlı büyüyen konular</p></div></div><div class="card lib-list">${data.trending.map((t, i) => `<div class="paper lib-row" data-t="${i}" role="button" tabindex="0"><div class="p-body"><div class="p-title">${esc(t.name_tr || t.name)}</div><div class="p-meta">${Number(t.count || 0).toLocaleString("tr-TR")} yayın</div></div><div class="p-side"><span class="chip teal">+%${esc(t.growth)}</span></div></div>`).join("") || '<p class="muted" style="padding:16px">Gündem henüz yüklenmedi.</p>'}</div>`, { wide: true });
      document.querySelectorAll("[data-t]").forEach((r) => r.onclick = () => ui.openTopic(data.trending[+r.dataset.t]));
      return;
    }
    const [, title, icon, items] = sections[+v];
    ui.openList({ title, items, emblem: icon });
  });
}

// ------------------------------------------------------------------ açılış
function enter() {
  if (!renderer) { openSections(); return; }
  entered = true;
  $("#splash").classList.add("gone"); setTimeout(() => { $("#splash").hidden = true; }, reduced ? 0 : 500);
  $("#hud").hidden = false; $("#help").hidden = false;
  const saved = readJson("akademik-kutuphane-yer");
  if (saved?.floor === "archive") goArchive({ x: saved.x, z: saved.z, yaw: saved.yaw });
  else if (saved && Number.isFinite(saved.x) && upper.walker.can(saved.x, saved.z)) place(upper, saved);
  renderer.domElement.focus?.();
}
async function boot() {
  ui.bindModalShell();
  $("#listBtn").onclick = openSections; $("#listEntry").onclick = openSections;
  $("#floorBtn").onclick = () => (floor === archive ? goUpper() : goArchive());
  $("#enterBtn").onclick = enter;
  const resume = readJson("akademik-okuma-devam");
  if (resume?.title) {
    const btn = $("#continueBtn"); btn.hidden = false; btn.innerHTML = `${ui.icon("book")}Okumaya devam et · ${esc(String(resume.title).slice(0, 48))}`;
    btn.onclick = () => { if (renderer) enter(); resume.archive ? ui.openArchiveReader(resume) : ui.openPdf(resume); };
  }
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 1.75)); renderer.setSize(innerWidth, innerHeight);
    renderer.outputColorSpace = THREE.SRGBColorSpace; renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.05;
    renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    $("#stage").append(renderer.domElement);
    upper = createUpper(); floor = upper; setFloorUi();
    bindInput();
    renderer.setAnimationLoop(frame);
  } catch (e) {
    console.error(e);
    renderer?.dispose(); renderer = null;
    $("#splashStatus").innerHTML = `3B görüntü bu tarayıcıda açılamadı. <b>Liste görünümü</b> ile aynı raflara ulaşabilirsin.`;
    $("#enterBtn").textContent = "Liste görünümünü aç"; $("#enterBtn").disabled = false;
  }
  if (upper) { $("#enterBtn").disabled = false; $("#splashStatus").textContent = "Salon hazır. Raflar arka planda doluyor."; }
  loadTrending(); loadStands(); loadForYou();
  loadWeather(); setInterval(loadWeather, 15 * 60000);
  setTimeout(() => fetch("/api/library/archive").catch(() => {}), 5000); // arşiv katının kitap hasadını önceden ısıt
  const failed = await loadPersonal();
  if (failed) $("#splashStatus").textContent = "Bazı kişisel raflar alınamadı; diğer bölümlerle devam edebilirsin.";
}
addEventListener("pagehide", () => { renderer?.setAnimationLoop(null); });
boot();
