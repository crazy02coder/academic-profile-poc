// Kütüphane kapakları: başlık temizliği, e-kitap kapağı ve arşiv kitap sırtı çizimleri.
// Kapaklar koyu, dolgun renkli modern kitap kapağı gibi; beyaz "belge" görünümü yok.
import * as THREE from "/static/vendor/three.module.min.js";

const GREEK = Object.fromEntries("alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma tau upsilon phi chi psi omega"
  .split(" ").map((k, i) => [k, [..."αβγδεζηθικλμνξοπρστυφχψω"][i]]));
const SYMBOLS = { ...GREEK, rightarrow: "→", leftarrow: "←", to: "→", pm: "±", times: "×", cdot: "·", infty: "∞", leq: "≤", geq: "≥", approx: "≈", sim: "~", degree: "°", circ: "°" };
const SUPER = Object.fromEntries([..."0123456789+-=()ni"].map((x, i) => [x, [..."⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱ"][i]]));
const SUB = Object.fromEntries([..."0123456789+-=()aehijklmnoprstuvx"].map((x, i) => [x, [..."₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ"][i]]));
const convert = (s, map) => [...String(s)].map((x) => map[x] || x).join("");

/** OpenAlex başlıklarındaki HTML/MathML/LaTeX artıklarını okunur metne çevirir. */
export function cleanTitle(value) {
  let s = String(value ?? "");
  if (/[<&]/.test(s)) {
    const doc = new DOMParser().parseFromString(s, "text/html");
    doc.querySelectorAll("script,style").forEach((x) => x.remove());
    doc.querySelectorAll("sup").forEach((x) => { x.textContent = convert(x.textContent, SUPER); });
    doc.querySelectorAll("sub").forEach((x) => { x.textContent = convert(x.textContent, SUB); });
    s = doc.body.textContent || "";
  }
  for (let i = 0; i < 4; i++) {
    s = s.replace(/\\(?:hbox|mbox|mathrm|text|textrm|textit|mathbf|mathit|mathcal|boldsymbol|operatorname)\s*\{([^{}]*)\}/g, "$1")
      .replace(/\\sqrt\s*\{([^{}]*)\}/g, "√$1")
      .replace(/\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}/g, "$1/$2")
      .replace(/\^\s*\{([^{}]*)\}/g, (_, v) => convert(v, SUPER))
      .replace(/_\s*\{([^{}]*)\}/g, (_, v) => convert(v, SUB));
  }
  s = s.replace(/\\([a-zA-Z]+)/g, (_, v) => SYMBOLS[v] ?? "")
    .replace(/\^([\w+-])/g, (_, v) => convert(v, SUPER))
    .replace(/_([\w+-])/g, (_, v) => convert(v, SUB))
    .replace(/[${}\\]/g, "")
    .replace(/\s+/g, " ").trim().replace(/[.\s]+$/, "");
  return s;
}

export const PALETTE = ["#1f2a44", "#2e2a6b", "#173f4f", "#3b2f5c", "#1f4d3a", "#5b2338", "#4a3426", "#26323d"];
const CATEGORY_TONE = { tip: 5, muhendislik: 0, kod: 1, temel: 3, yasam: 4, sosyal: 6, sanayi: 7, "for-you": 2 };
export const hash = (s) => [...String(s || "")].reduce((n, c) => (Math.imul(n, 31) + c.charCodeAt(0)) >>> 0, 7);
export const toneOf = (item) => PALETTE[CATEGORY_TONE[item.category] ?? hash(item.doi || item.title || item.name) % PALETTE.length];

const authorName = (a) => (typeof a === "string" ? a : a?.name || a?.display_name || "");
export const authorsLine = (item, n = 2) => {
  const list = (item.authors || []).map(authorName).filter(Boolean);
  return list.slice(0, n).join(", ") + (list.length > n ? " vd." : "");
};

function shade(hex, amount) {
  const n = parseInt(hex.slice(1), 16);
  const f = (c) => Math.max(0, Math.min(255, Math.round(c + (amount > 0 ? (255 - c) * amount : c * amount))));
  return `rgb(${f(n >> 16)},${f((n >> 8) & 255)},${f(n & 255)})`;
}
function lines(ctx, text, width) {
  const out = []; let line = "";
  for (const word of String(text).split(/\s+/).filter(Boolean)) {
    const trial = line ? `${line} ${word}` : word;
    if (ctx.measureText(trial).width > width && line) { out.push(line); line = word; } else line = trial;
  }
  if (line) out.push(line);
  return out;
}
/** Metni genişliğe sığdırır: önce yazıyı küçültür, sonra satırı "…" ile keser. Son satırın altını döndürür. */
function fitText(ctx, text, x, y, width, { maxLines = 4, max = 40, min = 18, weight = 700, color = "#fff", leading = 1.16, family = "Inter, system-ui, sans-serif" } = {}) {
  if (!text) return y;
  let size = max, rows;
  for (; size >= min; size -= 1) {
    ctx.font = `${weight} ${size}px ${family}`;
    rows = lines(ctx, text, width);
    if (rows.length <= maxLines) break;
  }
  size = Math.max(size, min);
  ctx.font = `${weight} ${size}px ${family}`;
  rows = lines(ctx, text, width);
  ctx.fillStyle = color; ctx.textBaseline = "alphabetic";
  rows.slice(0, maxLines).forEach((row, i) => {
    let r = row;
    if (i === maxLines - 1 && rows.length > maxLines) r += "…";
    while (ctx.measureText(r).width > width && r.length > 2) r = r.slice(0, -2) + "…";
    ctx.fillText(r, x, y + size + i * size * leading);
  });
  return y + size + (Math.min(rows.length, maxLines) - 1) * size * leading;
}
function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}

/** Desen: her yayın kendi deterministik motifini taşır, raftaki tabletler birbirinden ayrışır. */
function motif(ctx, n, W, H) {
  ctx.save();
  ctx.strokeStyle = "rgba(255,255,255,.10)"; ctx.fillStyle = "rgba(255,255,255,.07)"; ctx.lineWidth = 2;
  const kind = n % 4;
  if (kind === 0) { for (let r = 60; r < W * 1.1; r += 34) { ctx.beginPath(); ctx.arc(W * .95, H * .78, r, 0, Math.PI * 2); ctx.stroke(); } }
  else if (kind === 1) { ctx.translate(W, 0); ctx.rotate(Math.PI / 4); for (let x = -H; x < H; x += 26) ctx.fillRect(x, 0, 9, W * 1.6); }
  else if (kind === 2) { for (let y = H * .52; y < H; y += 22) for (let x = 18; x < W; x += 22) { ctx.beginPath(); ctx.arc(x, y, 2.2, 0, 7); ctx.fill(); } }
  else { ctx.beginPath(); ctx.arc(W * .82, H * .70, W * .42, 0, Math.PI * 2); ctx.fill(); ctx.beginPath(); ctx.arc(W * .82, H * .70, W * .26, 0, Math.PI * 2); ctx.fillStyle = "rgba(255,255,255,.06)"; ctx.fill(); }
  ctx.restore();
}

const coverCache = new Map();
/** E-kitap kapağı (3:4). lod=true uzak raflar için küçük sürüm. */
export function coverCanvas(item, { lod = false } = {}) {
  const title = cleanTitle(item.name_tr || item.title || item.name || "Başlıksız yayın");
  const key = `${lod}|${title}|${item.doi || ""}|${item.category || ""}|${item.reason ? 1 : 0}`;
  if (coverCache.has(key)) { const c = coverCache.get(key); coverCache.delete(key); coverCache.set(key, c); return c; }
  const W = 480, H = 640, scale = lod ? .3 : 1;
  const c = document.createElement("canvas"); c.width = W * scale; c.height = H * scale;
  const ctx = c.getContext("2d"); ctx.scale(scale, scale);
  const n = hash(item.doi || title), tone = toneOf(item);
  const g = ctx.createLinearGradient(0, 0, W * .4, H);
  g.addColorStop(0, shade(tone, .14)); g.addColorStop(1, shade(tone, -.38));
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  motif(ctx, n, W, H);
  const topic = cleanTitle(item.topic?.display_name || item.topic || item.category_label || "Akademik yayın").toLocaleUpperCase("tr");
  ctx.font = "700 17px Inter, system-ui, sans-serif"; ctx.fillStyle = "rgba(255,255,255,.72)";
  let t = topic; while (ctx.measureText(t).width > W - 72 && t.length > 3) t = t.slice(0, -2) + "…";
  ctx.fillText(t, 36, 58);
  ctx.fillStyle = "rgba(255,255,255,.55)"; ctx.fillRect(36, 74, 44, 3);
  if (lod) { fitText(ctx, title, 36, 100, W - 72, { maxLines: 4, max: 58, min: 40 }); return remember(key, c); }
  const bottom = fitText(ctx, title, 36, 96, W - 72, { maxLines: 6, max: 50, min: 26, weight: 750 });
  const venue = cleanTitle(item.venue || item.source || "");
  let y = Math.max(bottom + 28, 380);
  if (venue) y = fitText(ctx, venue, 36, y, W - 72, { maxLines: 2, max: 21, min: 16, weight: 600, color: "rgba(255,255,255,.82)" }) + 10;
  const authors = authorsLine(item);
  if (authors) fitText(ctx, authors, 36, y, W - 72, { maxLines: 2, max: 19, min: 15, weight: 500, color: "rgba(255,255,255,.62)" });
  // Alt şerit: yıl, atıf, açık erişim
  ctx.fillStyle = "rgba(0,0,0,.22)"; ctx.fillRect(0, H - 82, W, 82);
  ctx.font = "800 15px Inter, system-ui, sans-serif"; ctx.fillStyle = "rgba(255,255,255,.9)"; ctx.fillText("AKADEMİK İZ", 36, H - 34);
  const tags = [item.year ? String(item.year) : "", item.citations != null || item.cited_by != null ? `${Number(item.citations ?? item.cited_by ?? 0).toLocaleString("tr-TR")} atıf` : ""].filter(Boolean).join("  ·  ");
  ctx.font = "600 15px Inter, system-ui, sans-serif"; ctx.textAlign = "right"; ctx.fillStyle = "rgba(255,255,255,.78)"; ctx.fillText(tags, W - 36, H - 34); ctx.textAlign = "left";
  if (item.is_oa || item.pdf || item.pdf_url) {
    ctx.font = "700 13px Inter, system-ui, sans-serif"; const label = "AÇIK ERİŞİM", w = ctx.measureText(label).width + 24;
    roundRect(ctx, W - 36 - w, 30, w, 30, 15); ctx.fillStyle = "rgba(255,255,255,.16)"; ctx.fill();
    ctx.fillStyle = "#d1fae5"; ctx.fillText(label, W - 36 - w + 12, 50);
  }
  if (item.reason) { ctx.fillStyle = "#a5b4fc"; ctx.fillRect(0, 0, 8, H); }
  return remember(key, c);
}
function remember(key, c) { coverCache.set(key, c); while (coverCache.size > 240) coverCache.delete(coverCache.keys().next().value); return c; }

export function canvasTexture(canvas, anisotropy = 4) {
  const t = new THREE.CanvasTexture(canvas); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = anisotropy; return t;
}

/** Arşiv kitap sırtı: cilt rengi, yaldız şeritler, dikey başlık, yazar ve küçük mühür. */
export function drawSpine(ctx, item, x, y, w, h, color) {
  const n = hash(item.id || item.title);
  const base = shade(color, (n % 5) * .06 - .18);
  const g = ctx.createLinearGradient(x, 0, x + w, 0);
  g.addColorStop(0, shade(base, -.35)); g.addColorStop(.25, base); g.addColorStop(.7, shade(base, .08)); g.addColorStop(1, shade(base, -.4));
  ctx.fillStyle = g; ctx.fillRect(x, y, w, h);
  ctx.fillStyle = "#c9a45c";
  for (const yy of [y + 12, y + 18, y + h - 22, y + h - 16]) ctx.fillRect(x + 4, yy, w - 8, 2);
  ctx.save(); ctx.beginPath(); ctx.rect(x, y + 26, w, h - 56); ctx.clip();
  ctx.translate(x + w / 2 + 6, y + h - 32); ctx.rotate(-Math.PI / 2);
  ctx.fillStyle = "#f1dfb4"; ctx.font = `600 ${w > 50 ? 17 : 15}px Georgia, "Iowan Old Style", serif`;
  let title = cleanTitle(item.title || "Adsız");
  while (ctx.measureText(title).width > h - 66 && title.length > 4) title = title.slice(0, -2) + "…";
  ctx.fillText(title, 0, 0);
  const author = authorsLine(item, 1);
  if (author) { ctx.font = `italic 11px Georgia, serif`; ctx.fillStyle = "rgba(241,223,180,.75)"; let a = author; while (ctx.measureText(a).width > h - 66 && a.length > 4) a = a.slice(0, -2) + "…"; ctx.fillText(a, 0, -17); }
  ctx.restore();
  ctx.beginPath(); ctx.arc(x + w / 2, y + h - 40, 6, 0, Math.PI * 2);
  ctx.fillStyle = item.source === "Bağış" ? "#e9c46a" : "rgba(233,196,106,.35)"; ctx.fill();
}
