// Kütüphanenin iki katının ortak 3B yardımcıları: geometri, malzeme, tabela dokuları, animasyon ve yürüyüş.
import * as THREE from "/static/vendor/three.module.min.js";
import { canvasTexture } from "./library-covers.js?v=lib5";

export { THREE };
export const v3 = (x = 0, y = 0, z = 0) => new THREE.Vector3(x, y, z);
export const clamp = THREE.MathUtils.clamp;
export const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
export const EYE = 1.62;

// ------------------------------------------------------------------ geometri
const unitBox = new THREE.BoxGeometry(1, 1, 1);
export function box(parent, w, h, d, x, y, z, material, { shadow = true } = {}) {
  const m = new THREE.Mesh(unitBox, material);
  m.scale.set(w, h, d); m.position.set(x, y, z);
  m.castShadow = shadow; m.receiveShadow = true;
  parent.add(m); return m;
}
export function cyl(parent, rTop, rBottom, h, x, y, z, material, segments = 24) {
  const m = new THREE.Mesh(new THREE.CylinderGeometry(rTop, rBottom, h, segments), material);
  m.position.set(x, y, z); m.castShadow = true; m.receiveShadow = true; parent.add(m); return m;
}
export function plane(parent, w, h, material, x, y, z) {
  const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), material);
  m.position.set(x, y, z); parent.add(m); return m;
}
export function roundedBox(w, h, d, r) {
  const s = new THREE.Shape(), x = -w / 2, y = -h / 2;
  s.moveTo(x + r, y); s.lineTo(x + w - r, y); s.quadraticCurveTo(x + w, y, x + w, y + r); s.lineTo(x + w, y + h - r);
  s.quadraticCurveTo(x + w, y + h, x + w - r, y + h); s.lineTo(x + r, y + h); s.quadraticCurveTo(x, y + h, x, y + h - r);
  s.lineTo(x, y + r); s.quadraticCurveTo(x, y, x + r, y);
  const g = new THREE.ExtrudeGeometry(s, { depth: d, bevelEnabled: false, curveSegments: 5 });
  g.translate(0, 0, -d / 2); return g;
}
export function archShape(w, h) {
  const s = new THREE.Shape(), r = w / 2;
  s.moveTo(-r, 0); s.lineTo(-r, h - r); s.absarc(0, h - r, r, Math.PI, 0, true); s.lineTo(r, 0); s.lineTo(-r, 0);
  return s;
}
export const basic = (map, extra = {}) => new THREE.MeshBasicMaterial({ map, toneMapped: false, ...extra });
export const standard = (color, extra = {}) => new THREE.MeshStandardMaterial({ color, roughness: .7, metalness: 0, ...extra });

// ------------------------------------------------------------------ prosedürel dokular
export function makeCanvas(w, h) { const c = document.createElement("canvas"); c.width = w; c.height = h; return [c, c.getContext("2d")]; }
export function woodTexture({ base = "#c9a77d", dark = "#9c7a52", planks = 8, size = 1024, repeat = [4, 4], herringbone = false } = {}) {
  const [c, ctx] = makeCanvas(size, size);
  ctx.fillStyle = base; ctx.fillRect(0, 0, size, size);
  const ph = size / planks;
  for (let i = 0; i < planks; i++) {
    const tone = (Math.sin(i * 12.9898) * 43758.5453) % 1;
    ctx.fillStyle = `rgba(${tone > 0 ? 255 : 0},${tone > 0 ? 240 : 0},${tone > 0 ? 220 : 0},${Math.abs(tone) * .12})`;
    ctx.fillRect(0, i * ph, size, ph);
    ctx.strokeStyle = dark; ctx.globalAlpha = .18; ctx.lineWidth = 1.2;
    for (let k = 0; k < 14; k++) {
      const y = i * ph + 4 + k * (ph - 8) / 14; ctx.beginPath(); ctx.moveTo(0, y);
      for (let x = 0; x <= size; x += 64) ctx.lineTo(x, y + Math.sin((x + i * 97 + k * 31) * .012) * 2.2);
      ctx.stroke();
    }
    ctx.globalAlpha = .5; ctx.fillStyle = dark; ctx.fillRect(0, i * ph, size, 2);
    const off = (i * 379) % size; ctx.fillRect(off, i * ph, 2, ph); if (!herringbone) ctx.fillRect((off + size / 2) % size, i * ph, 2, ph);
    ctx.globalAlpha = 1;
  }
  const t = canvasTexture(c, 8); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(...repeat); return t;
}
export function stoneTexture({ base = "#6f655a", line = "#4a423a", repeat = [3, 2] } = {}) {
  const [c, ctx] = makeCanvas(512, 512);
  ctx.fillStyle = base; ctx.fillRect(0, 0, 512, 512);
  for (let i = 0; i < 2600; i++) { ctx.fillStyle = `rgba(0,0,0,${Math.random() * .06})`; ctx.fillRect(Math.random() * 512, Math.random() * 512, 2, 2); }
  ctx.strokeStyle = line; ctx.lineWidth = 3;
  for (let r = 0; r < 8; r++) { const y = r * 64; ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(512, y); ctx.stroke(); for (let k = 0; k < 4; k++) { const x = (k * 128 + (r % 2) * 64) % 512; ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x, y + 64); ctx.stroke(); } }
  const t = canvasTexture(c, 4); t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(...repeat); return t;
}

// ------------------------------------------------------------------ tabelalar
const ICON_PATHS = {
  book: "M4 19.5A2.5 2.5 0 0 1 6.5 17H20M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z",
  star: "M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01z",
  clock: "M12 2a10 10 0 1 0 0 20a10 10 0 1 0 0-20M12 6v6l4 2",
  sparkle: "M12 3l1.9 5.8L20 11l-6.1 2.2L12 19l-1.9-5.8L4 11l6.1-2.2z",
  upload: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12",
  arrowDown: "M12 5v14M19 12l-7 7-7-7",
  arrowUp: "M12 19V5M5 12l7-7 7 7",
};
export function drawIcon(ctx, name, x, y, size, color, width = 2) {
  const p = ICON_PATHS[name]; if (!p) return;
  ctx.save(); ctx.translate(x, y); ctx.scale(size / 24, size / 24);
  ctx.strokeStyle = color; ctx.lineWidth = width; ctx.lineCap = "round"; ctx.lineJoin = "round";
  ctx.stroke(new Path2D(p)); ctx.restore();
}
/** Kurumsal tabela: koyu zemin, beyaz başlık, gri alt yazı. Raf başlıkları ve istasyonlar için. */
export function signTexture(title, subtitle = "", { icon = "book", width = 1024, height = 160, theme = "dark", accent = "#6366f1" } = {}) {
  const [c, ctx] = makeCanvas(width, height);
  const dark = theme === "dark";
  ctx.fillStyle = dark ? "#16171b" : "#ffffff"; ctx.fillRect(0, 0, width, height);
  ctx.fillStyle = accent; ctx.fillRect(0, height - 6, width, 6);
  const pad = height * .28;
  if (icon) {
    ctx.fillStyle = dark ? "rgba(255,255,255,.08)" : "#f1f1f4";
    ctx.beginPath(); ctx.roundRect(pad * .8, height / 2 - height * .3, height * .6, height * .6, 14); ctx.fill();
    drawIcon(ctx, icon, pad * .8 + height * .12, height / 2 - height * .18, height * .36, dark ? "#fff" : "#111113", 2.2);
  }
  const x = icon ? pad * .8 + height * .78 : pad;
  ctx.fillStyle = dark ? "#ffffff" : "#0a0a0b"; ctx.font = `700 ${Math.round(height * .3)}px Inter, system-ui, sans-serif`;
  ctx.fillText(title, x, subtitle ? height * .48 : height * .6, width - x - pad);
  if (subtitle) { ctx.fillStyle = dark ? "rgba(255,255,255,.62)" : "#6b6b73"; ctx.font = `500 ${Math.round(height * .17)}px Inter, system-ui, sans-serif`; ctx.fillText(subtitle, x, height * .76, width - x - pad); }
  return canvasTexture(c, 8);
}
/** Pirinç levha (arşiv katı kapısı ve kategori tabelaları). */
export function brassTexture(title, subtitle = "", { width = 1024, height = 220, wood = false } = {}) {
  const [c, ctx] = makeCanvas(width, height);
  const g = ctx.createLinearGradient(0, 0, width, height);
  if (wood) { g.addColorStop(0, "#4a2f20"); g.addColorStop(1, "#2e1d14"); } else { g.addColorStop(0, "#c8a45a"); g.addColorStop(.5, "#e3c27a"); g.addColorStop(1, "#a9843f"); }
  ctx.fillStyle = g; ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = wood ? "#c9a45c" : "#7a5a24"; ctx.lineWidth = 6; ctx.strokeRect(14, 14, width - 28, height - 28);
  ctx.lineWidth = 2; ctx.strokeRect(26, 26, width - 52, height - 52);
  ctx.textAlign = "center"; ctx.fillStyle = wood ? "#ecd29a" : "#3b2a12";
  ctx.font = `700 ${Math.round(height * (subtitle ? .27 : .34))}px Georgia, "Iowan Old Style", serif`;
  ctx.fillText(title, width / 2, subtitle ? height * .5 : height * .62, width - 90);
  if (subtitle) { ctx.font = `italic ${Math.round(height * .14)}px Georgia, serif`; ctx.fillStyle = wood ? "rgba(236,210,154,.8)" : "rgba(59,42,18,.8)"; ctx.fillText(subtitle, width / 2, height * .75, width - 90); }
  return canvasTexture(c, 8);
}

// ------------------------------------------------------------------ animasyon
const tweens = new Set();
export const ease = { inOut: (t) => (t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2), out: (t) => 1 - Math.pow(1 - t, 3), back: (t) => 1 + 2.2 * Math.pow(t - 1, 3) + 1.2 * Math.pow(t - 1, 2) };
export function tween(duration, update, curve = ease.inOut) {
  if (reduced) duration = Math.min(duration, 60);
  return new Promise((resolve) => tweens.add({ start: performance.now(), duration, update, curve, resolve }));
}
export function updateTweens(now) {
  for (const t of tweens) {
    const k = clamp((now - t.start) / t.duration, 0, 1);
    t.update(t.curve(k));
    if (k >= 1) { tweens.delete(t); t.resolve(); }
  }
}

// ------------------------------------------------------------------ yürüyüş ve çarpışma
export class Walker {
  constructor(camera, { bounds, colliders = [] }) {
    this.camera = camera; this.bounds = bounds; this.colliders = colliders;
    this.yaw = 0; this.pitch = 0; this.goal = null; this.bob = 0; this.locked = false;
  }
  addCollider(x, z, w, d, pad = .32) { this.colliders.push({ x: x - w / 2 - pad, X: x + w / 2 + pad, z: z - d / 2 - pad, Z: z + d / 2 + pad }); }
  can(x, z) {
    const b = this.bounds;
    if (x < b.x || x > b.X || z < b.z || z > b.Z) return false;
    return !this.colliders.some((c) => x > c.x && x < c.X && z > c.z && z < c.Z);
  }
  move(dx, dz) {
    const p = this.camera.position; let moved = false;
    if (dx && this.can(p.x + dx, p.z)) { p.x += dx; moved = true; }
    if (dz && this.can(p.x, p.z + dz)) { p.z += dz; moved = true; }
    return moved;
  }
  walkTo(x, z) {
    // Hedef engelin içindeyse en yakın serbest noktaya çekilir.
    if (!this.can(x, z)) {
      const p = this.camera.position; let best = null;
      for (let r = .2; r < 2.4 && !best; r += .2) for (let a = 0; a < Math.PI * 2; a += Math.PI / 8) { const tx = x + Math.cos(a) * r, tz = z + Math.sin(a) * r; if (this.can(tx, tz) && (!best || Math.hypot(tx - p.x, tz - p.z) < Math.hypot(best.x - p.x, best.z - p.z))) best = { x: tx, z: tz }; }
      if (!best) return false; x = best.x; z = best.z;
    }
    this.goal = { x, z }; return true;
  }
  update(dt, keys) {
    if (this.locked) { this.apply(); return; }
    const run = keys.has("shift") ? 3.6 : 2.1, step = run * dt;
    const f = (keys.has("w") || keys.has("arrowup") ? 1 : 0) - (keys.has("s") || keys.has("arrowdown") ? 1 : 0);
    const s = (keys.has("d") ? 1 : 0) - (keys.has("a") ? 1 : 0);
    if (keys.has("arrowleft")) this.yaw += 1.6 * dt;
    if (keys.has("arrowright")) this.yaw -= 1.6 * dt;
    let moving = false;
    if (f || s) {
      this.goal = null;
      const len = Math.hypot(f, s);
      moving = this.move(((-Math.sin(this.yaw) * f + Math.cos(this.yaw) * s) / len) * step, ((-Math.cos(this.yaw) * f - Math.sin(this.yaw) * s) / len) * step);
    } else if (this.goal) {
      const p = this.camera.position, dx = this.goal.x - p.x, dz = this.goal.z - p.z, n = Math.hypot(dx, dz);
      if (n < .06) this.goal = null;
      else {
        const k = Math.min(step * 1.1, n);
        moving = this.move((dx / n) * k, (dz / n) * k);
        if (!moving) this.goal = null;
        const want = Math.atan2(-dx, -dz); let diff = want - this.yaw; diff = Math.atan2(Math.sin(diff), Math.cos(diff));
        if (n > .5) this.yaw += diff * Math.min(1, dt * 2.2);
      }
    }
    this.bob = moving && !reduced ? this.bob + dt * 9 : this.bob * .9;
    this.apply();
  }
  apply() {
    this.pitch = clamp(this.pitch, -1.15, 1.15);
    this.camera.rotation.set(this.pitch, this.yaw, 0, "YXZ");
    if (!this.locked) this.camera.position.y = (this.baseY ?? EYE) + Math.sin(this.bob) * .018;
  }
  face(x, z, y = EYE) {
    const p = this.camera.position;
    this.yaw = Math.atan2(-(x - p.x), -(z - p.z));
    this.pitch = Math.atan2(y - p.y, Math.hypot(x - p.x, z - p.z));
  }
}

/** Pick: kesişen nesneden yukarı doğru ilk userData.pick kaydını bulur. */
export function pickOf(object) {
  for (let o = object; o; o = o.parent) if (o.userData.pick) return o.userData.pick;
  return null;
}
export function disposeTree(root) {
  root.traverse((o) => {
    if (o.geometry && o.geometry !== unitBox) o.geometry.dispose();
    const mats = Array.isArray(o.material) ? o.material : o.material ? [o.material] : [];
    for (const m of mats) { m.map?.dispose(); m.dispose(); }
  });
}
