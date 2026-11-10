// Üst kat: modern okuma salonu. Duvar rafları, dönen standlar, gündem panosu, masa bilgisayarı,
// akademisyen rehberi (AVM kiosku), bağış istasyonu ve arşiv katına inen kapı.
import { THREE, v3, box, cyl, plane, roundedBox, archShape, basic, standard, woodTexture, makeCanvas, signTexture, brassTexture, drawIcon, tween, ease, Walker, EYE, reduced, pickOf } from "./library-engine.js?v=lib5";
import { coverCanvas, canvasTexture, cleanTitle, PALETTE, toneOf } from "./library-covers.js?v=lib5";
import { groupsOf } from "./library-ui.js?v=lib5";

const STAND_POS = [[-4.6, -2.7], [-1.2, -2.7], [2.2, -2.7], [-4.6, 1.1], [-1.2, 1.1], [2.2, 1.1]];
const ROWS = [1.46, 1.94, .98]; // önce göz hizası
const SEAT = { pos: v3(7.62, 1.22, .6), yaw: -Math.PI / 2, pitch: -.13 };

export function createUpper() {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color("#ebe9e5");
  const camera = new THREE.PerspectiveCamera(62, innerWidth / innerHeight, .05, 60);
  camera.position.set(0, EYE, 5.3); scene.add(camera);
  const walker = new Walker(camera, { bounds: { x: -8.45, X: 8.45, z: -6.05, Z: 6.45 } });
  const raycaster = new THREE.Raycaster(), ndc = new THREE.Vector2(), tmp = v3();
  const tablets = [], stands = [], shelves = new Map();
  let hovered = null, scanning = false;

  const M = {
    wall: standard("#f3f2ef", { roughness: .95 }),
    ceiling: standard("#fafaf9", { roughness: 1 }),
    white: standard("#f6f6f7", { roughness: .4 }),
    graphite: standard("#202126", { roughness: .45, metalness: .25 }),
    niche: standard("#2a2b31", { roughness: .85 }),
    oak: standard("#caa87f", { roughness: .55, map: woodTexture({ planks: 5, repeat: [1, 1] }) }),
    chrome: standard("#d4d7dc", { metalness: .9, roughness: .22 }),
    alu: standard("#bcc1c8", { metalness: .75, roughness: .35 }),
    led: new THREE.MeshStandardMaterial({ color: "#ffffff", emissive: "#fff6e6", emissiveIntensity: 2.4 }),
    glass: new THREE.MeshStandardMaterial({ color: "#d6e6f5", transparent: true, opacity: .13, roughness: .05, metalness: .1, depthWrite: false }),
    acrylic: new THREE.MeshStandardMaterial({ color: "#ffffff", transparent: true, opacity: .22, roughness: .05, depthWrite: false }),
    body: standard("#17171a", { metalness: .55, roughness: .32 }),
    panel: standard("#ececef", { roughness: .65 }),
    fabric: standard("#2b2d33", { roughness: .95 }),
    walnut: standard("#3c2a20", { roughness: .7, map: woodTexture({ base: "#4a3326", dark: "#24170f", planks: 3, repeat: [1, 1] }) }),
    brass: standard("#c19a52", { metalness: .85, roughness: .3 }),
    leaf: standard("#3f6a4b", { roughness: .8 }),
  };

  // ---------------------------------------------------------------- oda
  const hemi = new THREE.HemisphereLight("#ffffff", "#cdb99d", 1.1); scene.add(hemi);
  const sun = new THREE.DirectionalLight("#fff3df", 1.8);
  sun.position.set(3, 9, 8); sun.castShadow = true; sun.shadow.mapSize.set(2048, 2048);
  Object.assign(sun.shadow.camera, { left: -11, right: 11, top: 9, bottom: -9, near: 1, far: 30 });
  sun.shadow.bias = -.0004; sun.shadow.normalBias = .02; scene.add(sun, sun.target);
  const fill = new THREE.PointLight("#fff0da", 7, 16, 2); fill.position.set(0, 3.1, -1); scene.add(fill);

  const floorMesh = plane(scene, 18, 14, standard("#d9c19c", { roughness: .7, map: woodTexture({ base: "#dcc49f", dark: "#a98b63", planks: 10, repeat: [3, 2.4] }) }), 0, 0, 0);
  floorMesh.rotation.x = -Math.PI / 2; floorMesh.receiveShadow = true; floorMesh.userData.floor = true;
  const rug = plane(scene, 10.4, 6.6, standard("#dedbd5", { roughness: 1 }), -1.2, .004, -.8);
  rug.rotation.x = -Math.PI / 2; rug.receiveShadow = true; rug.userData.floor = true;

  box(scene, 18.2, 3.6, .2, 0, 1.8, -7.1, M.wall);
  box(scene, .2, 3.6, 14.2, -9.1, 1.8, 0, M.wall);
  box(scene, .2, 3.6, 14.2, 9.1, 1.8, 0, M.wall);
  box(scene, 18.2, .9, .2, 0, .45, 7.1, M.wall); box(scene, 18.2, .7, .2, 0, 3.25, 7.1, M.wall);
  box(scene, 18, 2, .04, 0, 1.9, 7.1, M.glass, { shadow: false }).userData.noPick = true;
  for (let x = -9; x <= 9.01; x += 1.5) box(scene, .06, 2, .1, x, 1.9, 7.04, M.graphite);
  box(scene, 18, .06, .1, 0, 2.9, 7.04, M.graphite); box(scene, 18, .06, .1, 0, .9, 7.04, M.graphite);
  for (const [w, d, x, z] of [[18, .02, 0, -6.99], [.02, 14, -8.99, 0], [.02, 14, 8.99, 0]]) box(scene, w, .09, d, x, .045, z, M.graphite, { shadow: false });
  box(scene, 18.2, .1, 14.2, 0, 3.65, 0, M.ceiling, { shadow: false });
  const slatCount = 46, slats = new THREE.InstancedMesh(new THREE.BoxGeometry(.1, .07, 13.8), M.oak, slatCount);
  const dummy = new THREE.Object3D();
  for (let i = 0; i < slatCount; i++) { dummy.position.set(-8.55 + i * .38, 3.56, 0); dummy.updateMatrix(); slats.setMatrixAt(i, dummy.matrix); }
  scene.add(slats);
  for (const x of [-6.27, -2.47, 1.33, 5.13]) box(scene, .06, .02, 13.2, x, 3.5, 0, M.led, { shadow: false });
  // Giriş duvarındaki marka bandı
  const brand = plane(scene, 3.6, .46, basic(signTexture("Akademik İz Kütüphanesi", "Araştır · keşfet · oku · bağışla", { icon: "book", theme: "light" })), 0, 3.25, 6.99);
  brand.rotation.y = Math.PI;

  // ---------------------------------------------------------------- tabletler
  const tabletGeo = roundedBox(.2, .27, .009, .014), screenGeo = new THREE.PlaneGeometry(.184, .252);
  function makeTablet(item, parent, x, y, z, tilt, extra = {}) {
    const g = new THREE.Group(); g.position.set(x, y, z); g.rotation.x = tilt;
    const body = new THREE.Mesh(tabletGeo, M.body); body.castShadow = true; g.add(body);
    const screen = new THREE.Mesh(screenGeo, basic(null)); screen.position.z = .0052; g.add(screen);
    const entry = { group: g, screen, item, level: -1, z, lift: 0 };
    g.userData.pick = { type: "item", item, entry, ...extra };
    parent.add(g); tablets.push(entry); setLevel(entry, 0);
    return entry;
  }
  function setLevel(entry, level) {
    if (entry.level === level) return;
    entry.level = level;
    const old = entry.screen.material.map;
    entry.screen.material.map = canvasTexture(coverCanvas(entry.item, { lod: level === 0 }));
    entry.screen.material.needsUpdate = true; old?.dispose();
  }
  function removeTablet(entry) {
    entry.group.removeFromParent(); entry.screen.material.map?.dispose(); entry.screen.material.dispose();
    const i = tablets.indexOf(entry); if (i >= 0) tablets.splice(i, 1);
    if (hovered === entry) hovered = null;
  }
  function ghostTexture(title, text) {
    const [c, ctx] = makeCanvas(720, 240);
    ctx.strokeStyle = "rgba(255,255,255,.28)"; ctx.setLineDash([10, 8]); ctx.lineWidth = 3; ctx.beginPath(); ctx.roundRect(6, 6, 708, 228, 22); ctx.stroke();
    ctx.fillStyle = "#fff"; ctx.font = "700 34px Inter, system-ui, sans-serif"; ctx.textAlign = "center"; ctx.fillText(title, 360, 104, 660);
    ctx.fillStyle = "rgba(255,255,255,.62)"; ctx.font = "500 22px Inter, system-ui, sans-serif"; ctx.fillText(text, 360, 150, 660);
    return canvasTexture(c);
  }

  // ---------------------------------------------------------------- duvar rafları
  function buildUnit(id, title, icon, x, empty) {
    const g = new THREE.Group(); g.position.set(x, 0, -6.78); scene.add(g);
    const W = 3.3, D = .42, H = 2.6;
    box(g, .05, H, D, -W / 2, H / 2, 0, M.white); box(g, .05, H, D, W / 2, H / 2, 0, M.white); box(g, W + .05, .05, D, 0, H, 0, M.white);
    box(g, W, .5, D, 0, .3, 0, M.white); box(g, W - .04, .05, D - .06, 0, .025, -.02, M.graphite);
    box(g, W - .04, .006, .004, 0, .3, D / 2 + .002, M.graphite, { shadow: false });
    for (const dx of [-W / 4, 0, W / 4]) box(g, .004, .46, .004, dx, .3, D / 2 + .002, M.graphite, { shadow: false });
    box(g, W - .08, 2.05, .02, 0, 1.55, -D / 2 + .02, M.niche, { shadow: false });
    for (const y of ROWS) {
      box(g, W - .08, .03, D - .06, 0, y, 0, M.oak);
      box(g, W - .14, .012, .02, 0, y - .022, D / 2 - .08, M.led, { shadow: false });
      const lip = box(g, W - .08, .05, .006, 0, y + .036, D / 2 - .05, M.acrylic, { shadow: false }); lip.userData.noPick = true;
    }
    box(g, W + .06, .4, .03, 0, H + .26, 0, M.graphite);
    const sign = plane(g, W, .36, basic(signTexture(title, "Yükleniyor…", { icon })), 0, H + .26, .017);
    const shelf = { id, title, icon, empty, group: g, sign, items: [], entries: [], ghost: null };
    sign.userData.pick = { type: "shelf", shelf };
    walker.addCollider(x, -6.78, W, D, .3);
    shelves.set(id, shelf); return shelf;
  }
  buildUnit("recent", "Son okuduklarım", "clock", -5.6, "Uygulamada ya da burada açtığın yayınlar bu rafa gelir.");
  buildUnit("favorites", "Kaydettiklerim", "star", -1.9, "Bir yayını açıp Kaydet'e bastığında burada durur.");
  buildUnit("forYou", "Senin için", "sparkle", 1.8, "Akademisyen incele, yayın kaydet; raf ilgi alanına göre dolar.");

  function setShelf(id, items, status = "") {
    const shelf = shelves.get(id); if (!shelf) return;
    shelf.entries.forEach(removeTablet); shelf.entries = []; shelf.items = items;
    items.slice(0, 18).forEach((item, i) => {
      const row = ROWS[Math.floor(i / 6)], col = i % 6;
      shelf.entries.push(makeTablet(item, shelf.group, -1.25 + col * .5, row + .155, .09, -.16, { shelf }));
    });
    const old = shelf.sign.material.map;
    shelf.sign.material.map = signTexture(shelf.title, status || (items.length ? `${items.length} yayın · listeyi açmak için tıkla` : "Henüz boş"), { icon: shelf.icon });
    shelf.sign.material.needsUpdate = true; old?.dispose();
    if (shelf.ghost) { shelf.ghost.material.map.dispose(); shelf.ghost.material.dispose(); shelf.ghost.removeFromParent(); shelf.ghost = null; }
    if (!items.length) {
      shelf.ghost = plane(shelf.group, 1.29, .43, basic(ghostTexture(status ? status : "Raf henüz boş", shelf.empty), { transparent: true }), 0, 1.7, -.17);
      shelf.ghost.userData.pick = { type: "shelf", shelf };
    }
  }

  // ---------------------------------------------------------------- dönen standlar
  function standLabel(text, color) {
    const [c, ctx] = makeCanvas(640, 224);
    ctx.fillStyle = color; ctx.fillRect(0, 0, 640, 224);
    ctx.fillStyle = "rgba(255,255,255,.14)"; ctx.fillRect(0, 186, 640, 38);
    ctx.textAlign = "center"; ctx.fillStyle = "#fff"; ctx.font = "750 56px Inter, system-ui, sans-serif"; ctx.fillText(text, 320, 116, 590);
    ctx.font = "700 20px Inter, system-ui, sans-serif"; ctx.fillStyle = "rgba(255,255,255,.75)"; ctx.fillText("OKUMA KÖŞESİ · SÜRÜKLE VE ÇEVİR", 320, 212, 590);
    return canvasTexture(c);
  }
  function buildStand(index, category) {
    const [x, z] = STAND_POS[index];
    const color = PALETTE[(index * 3 + 1) % PALETTE.length];
    const g = new THREE.Group(); g.position.set(x, 0, z); scene.add(g);
    cyl(g, .46, .5, .045, 0, .022, 0, M.graphite, 48); cyl(g, .5, .5, .008, 0, .048, 0, M.chrome, 48);
    cyl(g, .032, .032, 2.08, 0, 1.06, 0, M.chrome, 14);
    const rotor = new THREE.Group(); g.add(rotor);
    const stand = { index, category, color, group: g, rotor, faces: [], angle: index * .7, vel: 0, drag: false, touched: -1e9, items: [], entries: [], notes: [], x, z };
    for (let f = 0; f < 4; f++) {
      const face = new THREE.Group(); face.rotation.y = f * Math.PI / 2; rotor.add(face);
      box(face, .62, 1.52, .02, 0, 1.12, .3, M.panel);
      box(face, .022, 1.54, .022, .31, 1.12, .31, M.chrome);
      for (const y of [.62, 1.04, 1.46]) {
        box(face, .6, .012, .075, 0, y - .006, .345, M.chrome);
        box(face, .6, .03, .006, 0, y + .01, .383, M.chrome, { shadow: false });
      }
      face.userData.pick = { type: "stand", stand };
      stand.faces.push(face);
    }
    const head = new THREE.Group(); head.position.y = 2.02; rotor.add(head);
    box(head, .64, .25, .64, 0, 0, 0, M.graphite);
    const labelMat = basic(standLabel(category.label, color));
    for (let f = 0; f < 4; f++) { const side = new THREE.Group(); side.rotation.y = f * Math.PI / 2; head.add(side); plane(side, .62, .217, labelMat, 0, 0, .3215); }
    head.userData.pick = { type: "standHead", stand };
    walker.addCollider(x, z, .8, .8, .3);
    stands.push(stand); return stand;
  }
  function standNote(stand, text) {
    stand.notes.forEach((n) => { n.material.map.dispose(); n.material.dispose(); n.removeFromParent(); }); stand.notes = [];
    if (!text) return;
    const tex = ghostTexture(text, stand.category.label);
    for (const f of [0, 2]) { const n = plane(stand.faces[f], .5, .17, basic(tex, { transparent: true }), 0, 1.16, .312); n.material.color.set("#4b4b55"); n.userData.pick = { type: "standHead", stand }; stand.notes.push(n); }
  }
  function fillStand(stand, items) {
    stand.entries.forEach(removeTablet); stand.entries = []; stand.items = items;
    items.slice(0, 24).forEach((item, i) => {
      const f = i % 4, k = Math.floor(i / 4), row = [1.46, 1.04, .62][Math.floor(k / 2)], col = k % 2 ? .148 : -.148;
      stand.entries.push(makeTablet(item, stand.faces[f], col, row + .14, .352, -.2, { stand }));
    });
    standNote(stand, items.length ? "" : "Bu kategoride yayın yok");
  }
  function dragStand(stand, dx, dt) {
    const d = dx * .0085; stand.drag = true; stand.touched = performance.now();
    stand.angle += d; stand.vel = THREE.MathUtils.clamp(d / Math.max(dt, .008), -9, 9);
  }
  function releaseStand(stand) { stand.drag = false; stand.touched = performance.now(); }
  function turnStand(stand, dir) {
    if (stand.turning) return;
    const step = Math.PI / 2, from = stand.angle, to = Math.round(from / step) * step - dir * step;
    stand.turning = true; stand.drag = true; stand.vel = 0; stand.touched = performance.now();
    tween(460, (k) => { stand.angle = from + (to - from) * k; }, ease.out).then(() => { stand.drag = false; stand.turning = false; stand.touched = performance.now(); });
  }
  function nearestStand() {
    let best = null, bestD = 2.7;
    const p = camera.position, fwd = v3(-Math.sin(walker.yaw), 0, -Math.cos(walker.yaw));
    for (const s of stands) {
      const dx = s.x - p.x, dz = s.z - p.z, d = Math.hypot(dx, dz);
      if (d < bestD && (dx * fwd.x + dz * fwd.z) / d > .35) { best = s; bestD = d; }
    }
    return best;
  }

  // ---------------------------------------------------------------- gündem panosu
  const BW = 4.6, BH = 2.5, [boardCanvas, bctx] = makeCanvas(2048, 1114), boardTex = canvasTexture(boardCanvas, 8);
  const board = new THREE.Group(); board.position.set(-8.93, 1.8, -.8); board.rotation.y = Math.PI / 2; scene.add(board);
  box(board, BW + .1, BH + .1, .05, 0, 0, -.03, M.graphite);
  const boardScreen = plane(board, BW, BH, basic(boardTex), 0, 0, .0);
  boardScreen.userData.pick = { type: "board" };
  box(board, .5, .03, .03, 0, -BH / 2 - .09, -.01, M.graphite);
  const boardState = { mode: "tr", trending: [], rising: [], message: "Türkiye gündemi yükleniyor…", hover: -1, rects: [], tabs: [] };
  function drawBoard() {
    const W = 2048, H = 1114, s = boardState, list = s.mode === "tr" ? s.trending : s.rising;
    bctx.fillStyle = "#0f1115"; bctx.fillRect(0, 0, W, H);
    bctx.fillStyle = "#818cf8"; bctx.font = "700 26px Inter, system-ui, sans-serif"; bctx.fillText("GÜNDEM PANOSU · OPENALEX", 80, 92);
    bctx.fillStyle = "#fff"; bctx.font = "800 64px Inter, system-ui, sans-serif"; bctx.fillText(s.mode === "tr" ? "Türkiye'de yükselen konular" : "Senin alanında yükselenler", 80, 168);
    bctx.fillStyle = "rgba(255,255,255,.55)"; bctx.font = "500 26px Inter, system-ui, sans-serif";
    bctx.fillText(s.mode === "tr" ? "Son 12 ayda bir önceki yıla göre en hızlı büyüyen konular · karta dokun" : "İncelediğin akademisyenler ve kaydettiğin yayınlarla kesişen yükselişler", 80, 214);
    s.tabs = [];
    let tx = W - 80;
    for (const [mode, label] of [["mine", "Senin alanında"], ["tr", "Türkiye gündemi"]]) {
      bctx.font = "700 28px Inter, system-ui, sans-serif"; const w = bctx.measureText(label).width + 56; tx -= w;
      bctx.beginPath(); bctx.roundRect(tx, 70, w, 62, 31); bctx.fillStyle = s.mode === mode ? "#fff" : "rgba(255,255,255,.08)"; bctx.fill();
      bctx.fillStyle = s.mode === mode ? "#0f1115" : "rgba(255,255,255,.8)"; bctx.fillText(label, tx + 28, 111);
      s.tabs.push({ mode, x: tx, y: 70, w, h: 62 }); tx -= 16;
    }
    s.rects = [];
    if (!list.length) {
      bctx.fillStyle = "rgba(255,255,255,.6)"; bctx.font = "600 38px Inter, system-ui, sans-serif"; bctx.textAlign = "center";
      bctx.fillText(s.mode === "mine" && !s.message ? "Akademisyen incele veya yayın kaydet; panonun bu yüzü sana göre dolsun." : s.message || "Henüz veri yok.", W / 2, H / 2 + 40, W - 200);
      bctx.textAlign = "left"; boardTex.needsUpdate = true; return;
    }
    const cols = 4, gap = 28, x0 = 80, y0 = 262, cw = (W - 160 - gap * 3) / cols, ch = (H - y0 - 70 - gap * 2) / 3;
    const max = Math.max(...list.map((t) => Number(t.growth) || 0), 1);
    list.slice(0, 12).forEach((t, i) => {
      const x = x0 + (i % cols) * (cw + gap), y = y0 + Math.floor(i / cols) * (ch + gap), hot = s.hover === i;
      bctx.beginPath(); bctx.roundRect(x, y, cw, ch, 22); bctx.fillStyle = hot ? "#262a35" : "#1a1d24"; bctx.fill();
      if (hot) { bctx.strokeStyle = "#818cf8"; bctx.lineWidth = 3; bctx.stroke(); }
      bctx.fillStyle = "rgba(255,255,255,.45)"; bctx.font = "700 24px Inter, system-ui, sans-serif"; bctx.fillText(`#${i + 1}`, x + 28, y + 46);
      const name = cleanTitle(t.name_tr || t.name || "");
      bctx.fillStyle = "#fff"; bctx.font = "700 34px Inter, system-ui, sans-serif";
      const words = name.split(/\s+/); let line = "", lineY = y + 96, lines = 0;
      for (const word of words) {
        const trial = line ? `${line} ${word}` : word;
        if (bctx.measureText(trial).width > cw - 56 && line) { if (lines === 2) { line += "…"; break; } bctx.fillText(line, x + 28, lineY); lineY += 42; lines++; line = word; } else line = trial;
      }
      if (line && lines <= 2) bctx.fillText(line, x + 28, lineY, cw - 56);
      const pill = `+%${Number(t.growth || 0).toLocaleString("tr-TR")}`;
      bctx.font = "800 26px Inter, system-ui, sans-serif"; const pw = bctx.measureText(pill).width + 32;
      bctx.beginPath(); bctx.roundRect(x + 28, y + ch - 66, pw, 42, 21); bctx.fillStyle = "rgba(52,211,153,.16)"; bctx.fill();
      bctx.fillStyle = "#6ee7b7"; bctx.fillText(pill, x + 44, y + ch - 36);
      bctx.fillStyle = "rgba(255,255,255,.5)"; bctx.font = "500 24px Inter, system-ui, sans-serif"; bctx.fillText(`${Number(t.count || 0).toLocaleString("tr-TR")} yayın`, x + 44 + pw, y + ch - 37);
      bctx.fillStyle = "rgba(255,255,255,.08)"; bctx.fillRect(x + 28, y + ch - 12, cw - 56, 4);
      bctx.fillStyle = "#818cf8"; bctx.fillRect(x + 28, y + ch - 12, (cw - 56) * Math.min(1, (Number(t.growth) || 0) / max), 4);
      s.rects.push({ x, y, w: cw, h: ch, topic: t });
    });
    boardTex.needsUpdate = true;
  }
  const boardHit = (uv) => {
    const x = uv.x * 2048, y = (1 - uv.y) * 1114;
    const tab = boardState.tabs.find((r) => x > r.x && x < r.x + r.w && y > r.y && y < r.y + r.h);
    if (tab) return { tab };
    const i = boardState.rects.findIndex((r) => x > r.x && x < r.x + r.w && y > r.y && y < r.y + r.h);
    return i >= 0 ? { index: i, topic: boardState.rects[i].topic } : {};
  };
  drawBoard();
  function setBoard(values) { Object.assign(boardState, values); drawBoard(); }
  // Panonun önünde okuma bankı
  const bench = new THREE.Group(); bench.position.set(-6.3, 0, -.8); scene.add(bench);
  box(bench, .46, .06, 2.2, 0, .44, 0, M.oak); for (const z of [-.95, .95]) box(bench, .4, .42, .05, 0, .21, z, M.graphite);
  walker.addCollider(-6.3, -.8, .46, 2.2, .25);

  // ---------------------------------------------------------------- masa ve bilgisayar
  function monitorTexture() {
    const [c, ctx] = makeCanvas(1024, 612);
    ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, 1024, 612);
    ctx.fillStyle = "#f4f4f5"; ctx.fillRect(0, 0, 1024, 56);
    ["#ef4444", "#f59e0b", "#22c55e"].forEach((col, i) => { ctx.fillStyle = col; ctx.beginPath(); ctx.arc(30 + i * 24, 28, 7, 0, 7); ctx.fill(); });
    ctx.fillStyle = "#3a3a40"; ctx.font = "600 20px Inter, system-ui, sans-serif"; ctx.fillText("Akademik İz · Konu bulucu", 110, 35);
    ctx.fillStyle = "#1d4ed8"; ctx.font = "700 16px Inter, system-ui, sans-serif"; ctx.fillText("KONU BULUCU", 72, 140);
    ctx.fillStyle = "#0a0a0b"; ctx.font = "800 52px Inter, system-ui, sans-serif"; ctx.fillText("Ne okumak istiyorsun?", 72, 206);
    ctx.fillStyle = "#6b6b73"; ctx.font = "500 21px Inter, system-ui, sans-serif"; ctx.fillText("Türkçe yaz; OpenAlex'te aranır, en çok atıf alanlar önde gelir.", 72, 246);
    ctx.strokeStyle = "#dcdce0"; ctx.lineWidth = 2; ctx.beginPath(); ctx.roundRect(72, 286, 740, 72, 16); ctx.stroke();
    drawIcon(ctx, "sparkle", 94, 306, 30, "#85858e"); ctx.fillStyle = "#85858e"; ctx.font = "500 24px Inter, system-ui, sans-serif"; ctx.fillText("ör. deprem mühendisliği, makine öğrenmesi…", 140, 331);
    ctx.fillStyle = "#111113"; ctx.beginPath(); ctx.roundRect(828, 286, 124, 72, 16); ctx.fill(); ctx.fillStyle = "#fff"; ctx.font = "700 24px Inter, system-ui, sans-serif"; ctx.fillText("Ara", 866, 331);
    ["yapay zekâ", "deprem", "kanser tedavisi", "enerji"].forEach((t, i) => { const x = 72 + i * 190; ctx.fillStyle = "#f0f0f1"; ctx.beginPath(); ctx.roundRect(x, 392, 172, 44, 22); ctx.fill(); ctx.fillStyle = "#3a3a40"; ctx.font = "500 19px Inter, system-ui, sans-serif"; ctx.fillText(t, x + 20, 421); });
    ctx.fillStyle = "#85858e"; ctx.font = "500 19px Inter, system-ui, sans-serif"; ctx.fillText("Oturmak ve aramak için tıkla", 72, 520);
    return canvasTexture(c);
  }
  const desk = new THREE.Group(); desk.position.set(8.3, 0, .6); desk.rotation.y = -Math.PI / 2; scene.add(desk);
  box(desk, 1.7, .04, .78, 0, .74, 0, M.oak);
  for (const [x, z] of [[-.8, -.34], [.8, -.34], [-.8, .34], [.8, .34]]) box(desk, .04, .72, .04, x, .36, z, M.graphite);
  box(desk, 1.6, .2, .02, 0, .6, -.34, M.graphite);
  box(desk, .25, .015, .18, 0, .765, -.2, M.graphite); box(desk, .05, .3, .04, 0, .9, -.22, M.graphite);
  box(desk, .68, .43, .028, 0, 1.1, -.2, M.body);
  const monitor = plane(desk, .64, .385, basic(monitorTexture()), 0, 1.1, -.185);
  box(desk, .44, .014, .14, 0, .765, .12, M.graphite); box(desk, .06, .02, .1, .34, .765, .14, M.graphite);
  cyl(desk, .07, .08, .02, -.66, .77, -.2, M.graphite); cyl(desk, .01, .01, .38, -.66, .97, -.2, M.graphite);
  const lampHead = cyl(desk, .05, .09, .09, -.66, 1.17, -.2, M.graphite); lampHead.rotation.x = .3;
  cyl(desk, .06, .05, .14, .66, .82, -.18, M.white); [0, 1, 2].forEach((i) => { const s = new THREE.Mesh(new THREE.SphereGeometry(.07 - i * .012, 10, 8), M.leaf); s.position.set(.66 + (i - 1) * .03, .93 + i * .04, -.18); desk.add(s); });
  desk.userData.pick = { type: "pc" };
  walker.addCollider(8.3, .6, .78, 1.7, .3);
  // Ofis sandalyesi
  const chair = new THREE.Group(); chair.position.set(7.58, 0, .6); chair.rotation.y = Math.PI / 2; scene.add(chair);
  for (let i = 0; i < 5; i++) {
    const a = i * Math.PI * 2 / 5, leg = box(chair, .3, .03, .04, Math.cos(a) * .15, .08, Math.sin(a) * .15, M.graphite); leg.rotation.y = -a;
    const caster = new THREE.Mesh(new THREE.SphereGeometry(.028, 8, 6), M.graphite); caster.position.set(Math.cos(a) * .3, .03, Math.sin(a) * .3); chair.add(caster);
  }
  cyl(chair, .028, .028, .36, 0, .27, 0, M.chrome, 10);
  box(chair, .52, .08, .5, 0, .48, 0, M.fabric);
  box(chair, .48, .56, .05, 0, .84, -.25, M.fabric).rotation.x = -.08;
  box(chair, .04, .3, .04, 0, .62, -.23, M.graphite);
  for (const x of [-.27, .27]) { box(chair, .04, .2, .04, x, .6, 0, M.graphite); box(chair, .06, .025, .3, x, .71, 0, M.graphite); }
  chair.userData.pick = { type: "pc" };
  walker.addCollider(7.58, .6, .55, .55, .15);
  const seatPose = () => ({ pos: SEAT.pos.clone(), yaw: SEAT.yaw, pitch: SEAT.pitch });

  // ---------------------------------------------------------------- akademisyen rehberi (AVM kiosku)
  // Pencere köşesindeki duvarda, AVM'lerdeki gibi büyük yatay dokunmatik ekran.
  const KW = 1600, KH = 900, [kioskCanvas, kctx] = makeCanvas(KW, KH), kioskTex = canvasTexture(kioskCanvas, 8);
  const kiosk = new THREE.Group(); kiosk.position.set(-8.72, 0, 4.0); kiosk.rotation.y = Math.PI / 2; scene.add(kiosk);
  box(kiosk, 2.5, .06, .56, 0, .03, .12, M.graphite);
  for (const x of [-.85, .85]) box(kiosk, .14, .86, .12, x, .49, 0, M.alu);
  box(kiosk, 2.96, 1.84, .14, 0, 1.77, 0, M.alu);
  box(kiosk, 2.86, 1.62, .01, 0, 1.71, .071, M.body);
  plane(kiosk, 2.76, 1.5525, basic(kioskTex), 0, 1.71, .077);
  plane(kiosk, 2.5, .13, basic(signTexture("AKADEMİSYEN REHBERİ", "dokun · ara · yayınlarını gör", { icon: "book", width: 1600, height: 84 })), 0, 2.6, .071);
  kiosk.userData.pick = { type: "kiosk" };
  walker.addCollider(-8.72, 4.0, .6, 3.0, .25);
  let kioskPeople = [], kioskMinute = -1, weatherLabel = "";
  function drawKiosk(people = kioskPeople) {
    kioskPeople = people;
    const W = KW, H = KH, groups = groupsOf(people), k = kctx, F = (w, px) => `${w} ${px}px Inter, system-ui, sans-serif`;
    const bg = k.createLinearGradient(0, 0, W, H); bg.addColorStop(0, "#0b1220"); bg.addColorStop(1, "#14223f");
    k.fillStyle = bg; k.fillRect(0, 0, W, H);
    k.fillStyle = "#1d4ed8"; k.beginPath(); k.roundRect(48, 40, 78, 78, 22); k.fill(); drawIcon(k, "book", 65, 57, 44, "#fff", 2.4);
    k.fillStyle = "#fff"; k.font = F(800, 46); k.fillText("AKADEMİSYEN REHBERİ", 150, 88);
    k.fillStyle = "rgba(255,255,255,.55)"; k.font = F(500, 24); k.fillText(`${people.length} akademisyen · ${groups.length} kurum`, 150, 122);
    const now = new Date();
    k.textAlign = "right"; k.fillStyle = "#e6ebf5"; k.font = F(700, 56); k.fillText(now.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" }), W - 48, 94);
    k.fillStyle = "rgba(255,255,255,.55)"; k.font = F(500, 22);
    k.fillText([now.toLocaleDateString("tr-TR", { weekday: "long", day: "numeric", month: "long" }), weatherLabel].filter(Boolean).join(" · "), W - 48, 124); k.textAlign = "left";
    const X0 = 48, Y0 = 160, GW = 1030, GH = 610;
    k.fillStyle = "rgba(255,255,255,.03)"; k.beginPath(); k.roundRect(X0, Y0, GW, GH, 26); k.fill();
    k.strokeStyle = "rgba(255,255,255,.05)"; k.lineWidth = 1;
    for (let x = X0 + 40; x < X0 + GW; x += 40) { k.beginPath(); k.moveTo(x, Y0 + 8); k.lineTo(x, Y0 + GH - 8); k.stroke(); }
    for (let y = Y0 + 40; y < Y0 + GH; y += 40) { k.beginPath(); k.moveTo(X0 + 8, y); k.lineTo(X0 + GW - 8, y); k.stroke(); }
    const top = groups.slice(0, 10), weight = (g) => Math.sqrt(g.items.length) + .7;
    const block = (g, x, y, w, h) => {
      x += 7; y += 7; w -= 14; h -= 14; if (w < 30 || h < 30) return;
      const grad = k.createLinearGradient(x, y, x + w, y + h); grad.addColorStop(0, g.color); grad.addColorStop(1, g.color + "99");
      k.fillStyle = grad; k.beginPath(); k.roundRect(x, y, w, h, 18); k.fill();
      k.fillStyle = "#fff"; k.beginPath(); k.arc(x + 32, y + 32, 19, 0, 7); k.fill();
      k.fillStyle = "#0b1220"; k.font = F(800, 19); k.textAlign = "center"; k.fillText(String(g.no), x + 32, y + 39); k.textAlign = "left";
      const size = Math.max(17, Math.min(34, Math.sqrt(w * h) / 9)); k.fillStyle = "#fff"; k.font = F(750, size);
      const words = g.name.replace(/Üniversitesi/g, "Ünv.").split(/\s+/); let line = "", lines = [];
      for (const word of words) { const t = line ? `${line} ${word}` : word; if (k.measureText(t).width > w - 36 && line) { lines.push(line); line = word; } else line = t; }
      lines.push(line); lines = lines.slice(0, Math.max(1, Math.floor((h - 70) / (size * 1.2))));
      lines.forEach((l, i) => k.fillText(l, x + 18, y + h - 22 - (lines.length - i) * size * 1.18 + (h > 110 ? 0 : 8), w - 36));
      if (h > 110) { k.fillStyle = "rgba(255,255,255,.82)"; k.font = F(600, 18); k.fillText(`${g.items.length} akademisyen`, x + 18, y + h - 20); }
    };
    const tm = (list, x, y, w, h) => {
      if (!list.length) return; if (list.length === 1) { block(list[0], x, y, w, h); return; }
      const total = list.reduce((a, g) => a + weight(g), 0); let acc = 0, i = 0;
      while (i < list.length - 1 && acc + weight(list[i]) <= total / 2) acc += weight(list[i++]);
      if (!i) { acc = weight(list[0]); i = 1; }
      const f = acc / total;
      if (w >= h) { tm(list.slice(0, i), x, y, w * f, h); tm(list.slice(i), x + w * f, y, w * (1 - f), h); }
      else { tm(list.slice(0, i), x, y, w, h * f); tm(list.slice(i), x, y + h * f, w, h * (1 - f)); }
    };
    if (top.length) tm(top, X0 + 10, Y0 + 10, GW - 20, GH - 20);
    else { k.fillStyle = "rgba(255,255,255,.55)"; k.font = F(600, 30); k.textAlign = "center"; k.fillText("Henüz incelenen akademisyen yok", X0 + GW / 2, Y0 + GH / 2); k.textAlign = "left"; }
    const LX = 1110; k.fillStyle = "rgba(255,255,255,.45)"; k.font = F(700, 18); k.fillText("D İ Z İ N", LX, Y0 + 24);
    groups.slice(0, 12).forEach((g, i) => {
      const y = Y0 + 48 + i * 47;
      k.fillStyle = g.color; k.beginPath(); k.roundRect(LX, y, 38, 34, 9); k.fill();
      k.fillStyle = "#fff"; k.font = F(800, 17); k.textAlign = "center"; k.fillText(String(g.no), LX + 19, y + 24); k.textAlign = "left";
      k.font = F(500, 21); k.fillText(g.name, LX + 52, y + 25, 330);
      k.fillStyle = "rgba(255,255,255,.5)"; k.textAlign = "right"; k.fillText(String(g.items.length), W - 48, y + 25); k.textAlign = "left";
    });
    k.fillStyle = "#1d4ed8"; k.beginPath(); k.roundRect(48, 800, W - 96, 60, 30); k.fill();
    k.fillStyle = "#fff"; k.font = F(700, 24); k.textAlign = "center"; k.fillText("EKRANA DOKUNUN  ·  KURUM SEÇ  ·  AKADEMİSYEN ARA  ·  YAYINLARINI GÖR", W / 2, 838); k.textAlign = "left";
    kioskTex.needsUpdate = true;
  }
  drawKiosk([]);

  // ---------------------------------------------------------------- bağış istasyonu
  function stationTexture() {
    const [c, ctx] = makeCanvas(640, 420);
    ctx.fillStyle = "#ffffff"; ctx.fillRect(0, 0, 640, 420);
    ctx.fillStyle = "#eef2ff"; ctx.beginPath(); ctx.arc(320, 116, 62, 0, 7); ctx.fill();
    drawIcon(ctx, "upload", 286, 82, 68, "#4338ca", 2.2);
    ctx.textAlign = "center"; ctx.fillStyle = "#0a0a0b"; ctx.font = "800 40px Inter, system-ui, sans-serif"; ctx.fillText("Bağış istasyonu", 320, 236);
    ctx.fillStyle = "#6b6b73"; ctx.font = "500 21px Inter, system-ui, sans-serif"; ctx.fillText("PDF'ini bırak · yerelde taransın", 320, 276); ctx.fillText("arşiv katında herkes okuyabilsin", 320, 304);
    ctx.fillStyle = "#111113"; ctx.beginPath(); ctx.roundRect(200, 336, 240, 52, 26); ctx.fill(); ctx.fillStyle = "#fff"; ctx.font = "700 21px Inter, system-ui, sans-serif"; ctx.fillText("Dokun ve başla", 320, 369);
    return canvasTexture(c);
  }
  const station = new THREE.Group(); station.position.set(8.45, 0, 4.4); station.rotation.y = -Math.PI / 2; scene.add(station);
  box(station, 1.2, .96, .6, 0, .5, 0, M.white); box(station, 1.16, .05, .56, 0, .025, -.01, M.graphite);
  box(station, 1.24, .04, .64, 0, 1.0, 0, M.graphite);
  box(station, .52, .06, .03, -.12, .8, .3, M.graphite); box(station, .56, .012, .04, -.12, .836, .3, M.brass);
  plane(station, .5, .1, basic(signTexture("KİTAP BAĞIŞI", "", { icon: null, theme: "light", width: 512, height: 100 })), -.12, .68, .302);
  box(station, .07, .26, .07, -.28, 1.15, -.05, M.graphite);
  const screenGroup = new THREE.Group(); screenGroup.position.set(-.28, 1.34, .02); screenGroup.rotation.x = -.55; station.add(screenGroup);
  box(screenGroup, .62, .42, .03, 0, 0, 0, M.body); plane(screenGroup, .58, .38, basic(stationTexture()), 0, 0, .016);
  box(station, .44, .07, .34, .3, 1.055, .02, M.graphite); box(station, .38, .006, .28, .3, 1.092, .02, M.glass, { shadow: false });
  const lid = new THREE.Group(); lid.position.set(.3, 1.09, -.15); lid.rotation.x = -.42; station.add(lid); box(lid, .44, .02, .34, 0, .01, .17, M.graphite);
  const scanBar = box(station, .38, .012, .03, .3, 1.1, .02, new THREE.MeshBasicMaterial({ color: "#5eead4", toneMapped: false }), { shadow: false });
  scanBar.visible = false; scanBar.userData.noPick = true;
  plane(station, 1.7, .32, basic(signTexture("Bağış istasyonu", "PDF bağışla · yerel OCR ile taranır", { icon: "upload" })), 0, 2.4, -.53);
  station.userData.pick = { type: "donate" };
  walker.addCollider(8.45, 4.4, .6, 1.2, .3);

  // ---------------------------------------------------------------- arşiv katı kapısı
  const door = new THREE.Group(); door.position.set(8.98, 0, -4.3); door.rotation.y = -Math.PI / 2; scene.add(door);
  const frameShape = archShape(2.0, 2.9);
  frameShape.lineTo(.75, 0); frameShape.lineTo(.75, 1.87); frameShape.absarc(0, 1.87, .75, 0, Math.PI, false); frameShape.lineTo(-.75, 0); frameShape.lineTo(-1, 0);
  const frame = new THREE.Mesh(new THREE.ExtrudeGeometry(frameShape, { depth: .14, bevelEnabled: false, curveSegments: 24 }), M.walnut);
  frame.position.z = -.02; frame.castShadow = true; door.add(frame);
  const glow = new THREE.Mesh(new THREE.ShapeGeometry(archShape(1.5, 2.62), 24), new THREE.MeshBasicMaterial({ color: "#ffb35c", transparent: true, opacity: 0, toneMapped: false }));
  glow.position.z = .01; glow.userData.noPick = true; door.add(glow);
  const dark = new THREE.Mesh(new THREE.ShapeGeometry(archShape(1.5, 2.62), 24), standard("#120c08")); dark.position.z = .005; door.add(dark);
  const leaves = [];
  for (const side of [-1, 1]) {
    const pivot = new THREE.Group(); pivot.position.set(side * .75, 0, .06); door.add(pivot);
    const leafShape = new THREE.Shape(), w = .75, ix = -side * w;
    leafShape.moveTo(0, 0); leafShape.lineTo(ix, 0); leafShape.lineTo(ix, 1.87 + w);
    leafShape.absarc(ix, 1.87, w, Math.PI / 2, side > 0 ? 0 : Math.PI, side > 0); leafShape.lineTo(0, 0);
    const leaf = new THREE.Mesh(new THREE.ExtrudeGeometry(leafShape, { depth: .06, bevelEnabled: false, curveSegments: 16 }), M.walnut); leaf.castShadow = true; pivot.add(leaf);
    for (const y of [.45, 1.25]) box(pivot, .5, .6, .012, -side * .375, y, .066, M.walnut);
    cyl(pivot, .022, .022, .06, -side * .68, 1.1, .09, M.brass, 12).rotation.x = Math.PI / 2;
    leaves.push({ pivot, side });
  }
  for (const x of [-1.25, 1.25]) { box(door, .12, .26, .12, x, 2.2, .1, M.brass); box(door, .07, .14, .07, x, 2.24, .13, new THREE.MeshBasicMaterial({ color: "#ffd38a", toneMapped: false })); }
  const doorSign = new THREE.Group(); doorSign.position.set(0, 3.12, .1); door.add(doorSign);
  plane(doorSign, 1.7, .36, basic(brassTexture("ARŞİV KATI", "Açık erişim ve bağış kitapları  ↓"), {}), 0, 0, 0);
  door.userData.pick = { type: "door" };
  async function playDoor() {
    const t1 = tween(420, (k) => { doorSign.position.y = 3.12 + .32 * k; doorSign.rotation.x = -.7 * k; }, ease.out);
    await new Promise((r) => setTimeout(r, reduced ? 0 : 180));
    const t2 = tween(720, (k) => { leaves.forEach(({ pivot, side }) => { pivot.rotation.y = side * -1.35 * k; }); glow.material.opacity = .9 * k; });
    await Promise.all([t1, t2]);
  }
  function resetDoor() { doorSign.position.y = 3.12; doorSign.rotation.x = 0; leaves.forEach(({ pivot }) => { pivot.rotation.y = 0; }); glow.material.opacity = 0; }

  // ---------------------------------------------------------------- pencere dışı: saat ve hava
  // Üst kattayız: yer 5 m aşağıda, ağaç tepeleri ve şehir silueti görünür. Gökyüzü saate, bulut/yağış havaya göre.
  const outside = new THREE.Group(); scene.add(outside);
  const [skyCanvas, sctx] = makeCanvas(1024, 512), skyTex = canvasTexture(skyCanvas);
  const skyMat = new THREE.MeshBasicMaterial({ map: skyTex, toneMapped: false, depthWrite: false });
  const sky = plane(outside, 90, 40, skyMat, 0, 4, 30); sky.rotation.y = Math.PI; sky.userData.noPick = true;
  const [cityCanvas, cctx] = makeCanvas(2048, 256), cityTex = canvasTexture(cityCanvas);
  const city = plane(outside, 70, 8.75, new THREE.MeshBasicMaterial({ map: cityTex, transparent: true, toneMapped: false, depthWrite: false }), 0, -.6, 22);
  city.rotation.y = Math.PI; city.userData.noPick = true;
  const groundMat = standard("#6f8a5a", { roughness: 1 });
  const ground = plane(outside, 80, 30, groundMat, 0, -5, 22); ground.rotation.x = -Math.PI / 2; ground.userData.noPick = true;
  const canopyMat = standard("#4f7a4c", { roughness: .9 }), trunkMat = standard("#5a4636", { roughness: 1 });
  let seed = 7; const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  for (let i = 0; i < 16; i++) {
    const x = -10 + i * 1.35 + rnd() * .6, z = 9.2 + rnd() * 4, r = .9 + rnd() * .8, top = -1.2 + rnd() * 1.4;
    cyl(outside, .12, .16, top + 5, x, (top - 5) / 2, z, trunkMat, 6).userData.noPick = true;
    const c = new THREE.Mesh(new THREE.SphereGeometry(r, 12, 9), canopyMat); c.position.set(x, top + r * .6, z); c.scale.y = .85; c.userData.noPick = true; outside.add(c);
  }
  const hazeMat = new THREE.MeshBasicMaterial({ color: "#d9dee3", transparent: true, opacity: 0, toneMapped: false, depthWrite: false });
  const haze = plane(outside, 40, 20, hazeMat, 0, 2, 8.4); haze.rotation.y = Math.PI; haze.userData.noPick = true;
  // bulutlar
  const [cloudCanvas, clctx] = makeCanvas(512, 200);
  for (let i = 0; i < 26; i++) {
    const x = 60 + rnd() * 390, y = 70 + rnd() * 70, r = 28 + rnd() * 44, g = clctx.createRadialGradient(x, y, 0, x, y, r);
    g.addColorStop(0, "rgba(255,255,255,.95)"); g.addColorStop(1, "rgba(255,255,255,0)"); clctx.fillStyle = g; clctx.beginPath(); clctx.arc(x, y, r, 0, 7); clctx.fill();
  }
  const cloudTex = canvasTexture(cloudCanvas), clouds = [];
  for (let i = 0; i < 9; i++) {
    const m = new THREE.MeshBasicMaterial({ map: cloudTex, transparent: true, opacity: 0, toneMapped: false, depthWrite: false });
    const c = plane(outside, 10 + rnd() * 8, 4 + rnd() * 2, m, -40 + i * 9 + rnd() * 4, 5.5 + rnd() * 6, 26 + rnd() * 2);
    c.rotation.y = Math.PI; c.userData.noPick = true; clouds.push({ mesh: c, speed: .25 + rnd() * .35 });
  }
  // yağmur ve kar
  const RAIN = 1400, rainPos = new Float32Array(RAIN * 6), rainSpeed = new Float32Array(RAIN);
  for (let i = 0; i < RAIN; i++) {
    const x = -10 + rnd() * 20, y = -5 + rnd() * 13, z = 7.5 + rnd() * 8;
    rainPos.set([x, y, z, x - .04, y - .38, z], i * 6); rainSpeed[i] = 11 + rnd() * 5;
  }
  const rainGeo = new THREE.BufferGeometry(); rainGeo.setAttribute("position", new THREE.BufferAttribute(rainPos, 3));
  const rain = new THREE.LineSegments(rainGeo, new THREE.LineBasicMaterial({ color: "#c3cfdc", transparent: true, opacity: .55, toneMapped: false }));
  rain.frustumCulled = false; rain.visible = false; rain.userData.noPick = true; outside.add(rain);
  const SNOW = 1500, snowPos = new Float32Array(SNOW * 3), snowPhase = new Float32Array(SNOW);
  for (let i = 0; i < SNOW; i++) { snowPos.set([-10 + rnd() * 20, -5 + rnd() * 13, 7.5 + rnd() * 8], i * 3); snowPhase[i] = rnd() * 6.28; }
  const snowGeo = new THREE.BufferGeometry(); snowGeo.setAttribute("position", new THREE.BufferAttribute(snowPos, 3));
  const [flake, fctx] = makeCanvas(32, 32); { const g = fctx.createRadialGradient(16, 16, 0, 16, 16, 16); g.addColorStop(0, "rgba(255,255,255,1)"); g.addColorStop(1, "rgba(255,255,255,0)"); fctx.fillStyle = g; fctx.fillRect(0, 0, 32, 32); }
  const snow = new THREE.Points(snowGeo, new THREE.PointsMaterial({ size: .09, map: canvasTexture(flake), transparent: true, depthWrite: false, toneMapped: false }));
  snow.frustumCulled = false; snow.visible = false; snow.userData.noPick = true; outside.add(snow);

  const C = (h) => new THREE.Color(h);
  const DAY = { clear: ["#4f93d6", "#cfe6f7"], cloudy: ["#6f9cc7", "#d7e5ef"], overcast: ["#98a3ae", "#d3d8dd"], rain: ["#6b7784", "#aab3bc"],
    snow: ["#aeb8c2", "#e3e7eb"], fog: ["#c3c9ce", "#dde0e3"], storm: ["#3c4652", "#7a838d"] };
  const weather = { kind: "clear", sunrise: null, sunset: null, hour: null, temp: null, city: "" };
  let skyKey = "", flash = 0;
  function sunState() {
    const now = new Date(), h = weather.hour ?? now.getHours() + now.getMinutes() / 60;
    const hm = (d, fb) => { const t = d ? new Date(d) : null; return t && !isNaN(t) ? t.getHours() + t.getMinutes() / 60 : fb; };
    const rise = hm(weather.sunrise, 6.8), set = hm(weather.sunset, 17.4), f = (h - rise) / (set - rise);
    const alt = f >= 0 && f <= 1 ? Math.sin(Math.PI * f) : -Math.min(1, (f < 0 ? rise - h : h - set) / 1.6);
    return { alt, f, h };
  }
  function paintSky() {
    const { alt, f } = sunState(), kind = weather.kind, key = `${kind}|${Math.round(alt * 40)}`;
    if (key === skyKey) return; skyKey = key;
    const day = DAY[kind] || DAY.clear, wet = ["rain", "storm", "overcast", "fog", "snow"].includes(kind);
    const night = wet ? ["#0b0f17", "#20262f"] : ["#060a18", "#18213b"], dusk = wet ? ["#3a3f52", "#8d7f7c"] : ["#2b3b6b", "#f2a46b"];
    const pick = (i) => {
      if (alt >= .22) return C(day[i]);
      if (alt <= -.22) return C(night[i]);
      const t = (alt + .22) / .44;
      return t < .5 ? C(night[i]).lerp(C(dusk[i]), t * 2) : C(dusk[i]).lerp(C(day[i]), (t - .5) * 2);
    };
    const top = pick(0), hor = pick(1), W = 1024, H = 512, horizonY = 330;
    const g = sctx.createLinearGradient(0, 0, 0, horizonY); g.addColorStop(0, `#${top.getHexString()}`); g.addColorStop(1, `#${hor.getHexString()}`);
    sctx.fillStyle = g; sctx.fillRect(0, 0, W, H); sctx.fillStyle = `#${hor.getHexString()}`; sctx.fillRect(0, horizonY, W, H - horizonY);
    if (alt < -.1 && (kind === "clear" || kind === "cloudy")) {
      let st = 11; const r2 = () => ((st = (st * 48271) % 2147483647) / 2147483647);
      for (let i = 0; i < 260; i++) { sctx.fillStyle = `rgba(255,255,255,${(.25 + r2() * .7) * Math.min(1, (-alt - .1) * 4)})`; sctx.fillRect(r2() * W, r2() * horizonY * .95, 1.6, 1.6); }
    }
    const disc = (x, y, r, inner, glow) => { const gr = sctx.createRadialGradient(x, y, 0, x, y, r * 4); gr.addColorStop(0, glow); gr.addColorStop(1, "rgba(255,255,255,0)"); sctx.fillStyle = gr; sctx.fillRect(x - r * 4, y - r * 4, r * 8, r * 8); sctx.fillStyle = inner; sctx.beginPath(); sctx.arc(x, y, r, 0, 7); sctx.fill(); };
    const visible = !["overcast", "rain", "storm", "fog", "snow"].includes(kind);
    if (visible && alt > -.08) disc(W * (.82 - .64 * Math.min(1, Math.max(0, f))), horizonY - 20 - alt * 230, 15, alt < .2 ? "#ffd9a0" : "#fffaf0", alt < .2 ? "rgba(255,170,90,.55)" : "rgba(255,245,220,.5)");
    if (visible && alt < -.15) { disc(W * .3, 120, 11, "#f3f1ea", "rgba(200,210,255,.25)"); sctx.fillStyle = `#${top.getHexString()}`; sctx.beginPath(); sctx.arc(W * .3 + 6, 116, 10, 0, 7); sctx.fill(); }
    skyTex.needsUpdate = true;
    // şehir silueti: gündüz pus mavisi, gece koyu ve ışıklı pencereler
    const cityCol = pick(1).clone().lerp(C(alt > 0 ? "#6b7a8c" : "#0d1220"), alt > 0 ? .55 : .8);
    cctx.clearRect(0, 0, 2048, 256); let cs = 3; const r3 = () => ((cs = (cs * 16807) % 2147483647) / 2147483647);
    for (let x = 0; x < 2048;) {
      const w = 40 + r3() * 90, h = 60 + r3() * 170, y = 256 - h;
      cctx.fillStyle = `#${cityCol.clone().offsetHSL(0, 0, (r3() - .5) * .06).getHexString()}`; cctx.fillRect(x, y, w, h);
      if (r3() < .2) cctx.fillRect(x + w / 2 - 2, y - 24, 4, 24);
      if (alt < .05) for (let wy = y + 10; wy < 250; wy += 14) for (let wx = x + 6; wx < x + w - 8; wx += 12) if (r3() < .32) { cctx.fillStyle = r3() < .8 ? "rgba(255,214,140,.85)" : "rgba(190,215,255,.7)"; cctx.fillRect(wx, wy, 5, 7); }
      x += w + 2 + r3() * 10;
    }
    cityTex.needsUpdate = true;
    const snowy = kind === "snow", dim = alt > 0 ? .55 + .45 * Math.min(1, alt * 3) : .18 + .37 * Math.max(0, 1 + alt / .22);
    groundMat.color.set(snowy ? "#e9edf1" : "#6f8a5a"); canopyMat.color.set(snowy ? "#9fb3a3" : "#4f7a4c");
    // iç ışık: gece tavan ışıkları ağırlıkta, gündüz güneş
    const dayK = Math.max(0, Math.min(1, (alt + .1) / .4)), wetK = { overcast: .6, rain: .5, snow: .75, fog: .55, storm: .38 }[kind] ?? 1;
    sun.intensity = .12 + 1.7 * dayK * wetK; sun.color.set(alt < .2 && alt > -.1 ? "#ffc497" : dayK > .5 ? "#fff3df" : "#a9b8ff");
    hemi.intensity = .5 + .6 * dayK; fill.intensity = 7 + (1 - dayK) * 7;
    hazeMat.color.copy(hor); hazeMat.opacity = kind === "fog" ? .62 : kind === "rain" || kind === "storm" ? .22 : kind === "snow" ? .18 : 0;
    clouds.forEach(({ mesh }) => {
      mesh.material.opacity = { clear: .0, cloudy: .75, overcast: .95, rain: .9, snow: .85, fog: .5, storm: .95 }[kind] ?? 0;
      mesh.material.color.set(kind === "clear" || kind === "cloudy" ? "#ffffff" : kind === "storm" ? "#5d6670" : "#9aa3ad").multiplyScalar(dim);
    });
    rain.visible = kind === "rain" || kind === "storm"; snow.visible = snowy;
  }
  function setWeather(w = {}) {
    Object.assign(weather, w); skyKey = "";
    const names = { clear: "Açık", cloudy: "Parçalı bulutlu", overcast: "Kapalı", rain: "Yağmurlu", snow: "Karlı", fog: "Sisli", storm: "Fırtına" };
    weatherLabel = [weather.city, weather.temp != null ? `${Math.round(weather.temp)}°` : "", names[weather.kind] || ""].filter(Boolean).join(" ");
    paintSky(); drawKiosk();
  }
  function updateOutside(dt, now) {
    for (const c of clouds) { c.mesh.position.x += c.speed * dt; if (c.mesh.position.x > 46) c.mesh.position.x = -46; }
    if (rain.visible) {
      for (let i = 0; i < RAIN; i++) {
        const o = i * 6, d = rainSpeed[i] * dt; rainPos[o + 1] -= d; rainPos[o + 4] -= d; rainPos[o] -= d * .1; rainPos[o + 3] -= d * .1;
        if (rainPos[o + 4] < -5) { const y = 8 + Math.random() * 2, x = -10 + Math.random() * 20; rainPos[o] = x; rainPos[o + 1] = y; rainPos[o + 3] = x - .04; rainPos[o + 4] = y - .38; }
      }
      rainGeo.attributes.position.needsUpdate = true;
    }
    if (snow.visible) {
      const t = now * .001;
      for (let i = 0; i < SNOW; i++) {
        const o = i * 3; snowPos[o + 1] -= (.55 + (i % 7) * .06) * dt; snowPos[o] += Math.sin(t * .8 + snowPhase[i]) * .35 * dt;
        if (snowPos[o + 1] < -5) { snowPos[o + 1] = 8; snowPos[o] = -10 + Math.random() * 20; }
      }
      snowGeo.attributes.position.needsUpdate = true;
    }
    if (weather.kind === "storm") {
      if (flash <= 0 && Math.random() < dt * .06) flash = .22;
      if (flash > 0) { flash -= dt; skyMat.color.setScalar(flash > .14 || (flash < .08 && flash > .03) ? 2.6 : 1); if (flash <= 0) skyMat.color.setScalar(1); }
    }
  }
  paintSky();

  // ---------------------------------------------------------------- bitkiler
  function plant(x, z, s = 1) {
    const g = new THREE.Group(); g.position.set(x, 0, z); g.scale.setScalar(s); scene.add(g);
    cyl(g, .2, .16, .42, 0, .21, 0, M.white, 20);
    for (let i = 0; i < 7; i++) { const a = i * 2.4, leaf = new THREE.Mesh(new THREE.SphereGeometry(.2, 10, 8), M.leaf); leaf.scale.set(.5, 1.4, .25); leaf.position.set(Math.cos(a) * .12, .7 + (i % 3) * .12, Math.sin(a) * .12); leaf.rotation.set(Math.sin(a) * .5, a, Math.cos(a) * .5); leaf.castShadow = true; g.add(leaf); }
    walker.addCollider(x, z, .4 * s, .4 * s, .2);
  }
  plant(-8.3, 6.3); plant(8.3, 6.3); plant(8.3, -6.0, .9); plant(-8.3, -6.0, .9);

  // ---------------------------------------------------------------- etkileşim
  function raycast(clientX, clientY) {
    ndc.set(clientX / innerWidth * 2 - 1, 1 - clientY / innerHeight * 2);
    raycaster.setFromCamera(ndc, camera);
    const hits = raycaster.intersectObjects(scene.children, true);
    return hits.find((h) => h.object.visible && !h.object.userData.noPick && h.distance < 26) || null;
  }
  function hover(hit) {
    const pick = hit ? pickOf(hit.object) : null;
    hovered = pick?.type === "item" ? pick.entry : null;
    let index = -1, result = null;
    if (pick?.type === "board" && hit.uv) {
      const b = boardHit(hit.uv);
      if (b.tab) result = { clickable: true };
      else if (b.topic) { index = b.index; result = { item: { ...b.topic, kind: "trend" }, clickable: true }; }
      else result = { clickable: false };
    }
    if (boardState.hover !== index) { boardState.hover = index; drawBoard(); }
    if (result) return result;
    if (hovered) return { item: hovered.item, clickable: true };
    if (pick) return { clickable: pick.type !== "stand" };
    return { clickable: !!hit?.object.userData.floor };
  }
  function click(hit) {
    if (!hit) return null;
    const pick = pickOf(hit.object);
    if (!pick) return hit.object.userData.floor ? { type: "walk", point: hit.point } : null;
    if (pick.type === "item") return { type: "item", item: pick.item };
    if (pick.type === "shelf") return { type: "list", title: pick.shelf.title, items: pick.shelf.items, empty: pick.shelf.empty, emblem: { clock: "clock", star: "star", sparkle: "sparkle" }[pick.shelf.icon] || "book" };
    if (pick.type === "standHead" || pick.type === "stand") return { type: "list", title: pick.stand.category.label, items: pick.stand.items, empty: "Bu kategoride henüz yayın yok.", emblem: "book" };
    if (pick.type === "board") {
      const b = hit.uv ? boardHit(hit.uv) : {};
      if (b.tab) { boardState.mode = b.tab.mode; boardState.hover = -1; drawBoard(); return { type: "none" }; }
      return b.topic ? { type: "topic", topic: b.topic } : { type: "none" };
    }
    return { type: pick.type };
  }
  function standOf(hit) { const p = hit ? pickOf(hit.object) : null; return p?.stand || null; }

  // ---------------------------------------------------------------- kare güncellemesi
  let lodClock = 0;
  function update(dt, now) {
    for (const s of stands) {
      const near = Math.hypot(camera.position.x - s.x, camera.position.z - s.z) < 3.6;
      if (!s.drag) {
        if (!near && !reduced && now - s.touched > 5000) { s.angle += dt * .14; s.vel = 0; }
        else {
          s.angle += s.vel * dt; s.vel *= Math.pow(.1, dt);
          if (Math.abs(s.vel) < 1.4) { const step = Math.PI / 2, target = Math.round(s.angle / step) * step; s.vel += (target - s.angle) * 34 * dt; s.vel *= Math.pow(.015, dt); }
        }
      }
      s.rotor.rotation.y = s.angle;
    }
    for (const e of tablets) {
      const want = e === hovered ? 1 : 0;
      if (e.lift !== want) { e.lift += (want - e.lift) * Math.min(1, dt * 12); if (Math.abs(e.lift - want) < .01) e.lift = want; e.group.position.z = e.z + e.lift * .035; e.group.scale.setScalar(1 + e.lift * .05); }
    }
    lodClock -= dt;
    if (lodClock <= 0) {
      lodClock = .35;
      const p = camera.position, ranked = tablets.map((e) => ({ e, d: e.group.getWorldPosition(tmp).distanceTo(p) })).sort((a, b) => a.d - b.d);
      ranked.forEach(({ e, d }, i) => setLevel(e, i < 30 && d < 3.4 ? 1 : 0));
    }
    const minute = Math.floor(Date.now() / 60000);
    if (minute !== kioskMinute) { kioskMinute = minute; drawKiosk(); paintSky(); }
    updateOutside(dt, now);
    if (scanning) scanBar.position.z = .02 + Math.sin(now * .004) * .12;
  }
  function setScanning(on) { scanning = on; scanBar.visible = on; }
  function resize() { camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix(); }

  return {
    id: "upper", scene, camera, walker, raycast, hover, click, update, resize, standOf, dragStand, releaseStand, turnStand, nearestStand,
    setShelf, buildStand, fillStand, standNote, setBoard, drawKiosk, setWeather, setScanning, playDoor, resetDoor, seatPose, stands,
    spawn: { x: 0, z: 5.3, yaw: 0 }, doorSpawn: { x: 7.4, z: -4.3, yaw: Math.PI / 2 },
  };
}
