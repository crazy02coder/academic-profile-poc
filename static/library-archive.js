// Arşiv katı: eski usul, tavana kadar kitaplıklı uzun salon. Kategoriler iki yandaki bölmelerde;
// her bölmede bağışlar ve açık erişim kitaplar (DOAB/OAPEN, Gutenberg) birlikte durur.
// Raflar veri gelmeden de dolu görünür (dekor kitaplar); gerçek kitaplar göz hizasındaki raflara yerleşir.
import { THREE, v3, cyl, plane, archShape, basic, standard, woodTexture, stoneTexture, makeCanvas, brassTexture, tween, ease, Walker, EYE, reduced, pickOf } from "./library-engine.js?v=lib5";
import { canvasTexture, drawSpine } from "./library-covers.js?v=lib5";
import { api } from "./library-ui.js?v=lib5";

const CATS = [["muhendislik", "Mühendislik", "#334155"], ["tip", "Tıp ve Sağlık", "#7f354b"], ["sosyal", "Sosyal Bilimler", "#695a88"], ["temel", "Fen Bilimleri", "#4338ca"], ["sanat", "Sanat ve Edebiyat", "#7b426b"],
  ["tarih", "Tarih", "#78563d"], ["egitim", "Eğitim", "#3d6474"], ["hukuk", "Hukuk ve Ekonomi", "#455d46"], ["klasikler", "Klasikler", "#62534d"], ["genel", "Genel", "#52525b"]];
const FACE = 5.55, DEPTH = .45, WALL_H = 6.0, PERP_H = 3.3, BAY = 5.2;
const bayCenter = (i) => 9.8 - i * BAY; // 0: girişe en yakın bölme
const WALL_ROWS = Array.from({ length: 14 }, (_, k) => .12 + k * .42);
const PERP_ROWS = Array.from({ length: 7 }, (_, k) => .12 + k * .42);
const REAL_ROWS = [3, 4, 2, 5, 1]; // göz hizası önce
const UP = v3(0, 1, 0);
const MAX_REAL = 64, CELL_W = 64, CELL_H = 248;

function rng(seed) { let s = seed >>> 0; return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; }; }

export function createArchive() {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color("#1a120d");
  scene.fog = new THREE.FogExp2("#22170f", .028);
  const camera = new THREE.PerspectiveCamera(64, innerWidth / innerHeight, .05, 70);
  camera.position.set(0, EYE, 13.4); scene.add(camera);
  const walker = new Walker(camera, { bounds: { x: -5.15, X: 5.15, z: -14.3, Z: 14.4 } });
  const raycaster = new THREE.Raycaster(), ndc = new THREE.Vector2();
  const pickables = [], sections = [], bays = [], ladders = [], flames = [], lights = [];
  let hovered = null, climbed = null, loading = null;

  const M = {
    walnut: standard("#4a3022", { roughness: .78, map: woodTexture({ base: "#4d3223", dark: "#24160e", planks: 4, repeat: [1, 1] }) }),
    dark: standard("#2a1a12", { roughness: .85 }),
    stone: standard("#776a5b", { roughness: 1, map: stoneTexture({ repeat: [4, 2] }) }),
    brass: standard("#b8924a", { metalness: .85, roughness: .32 }),
    iron: standard("#1d1a18", { metalness: .6, roughness: .5 }),
    leather: standard("#5a261d", { roughness: .7 }),
    shade: new THREE.MeshStandardMaterial({ color: "#1d5134", emissive: "#2f7a4b", emissiveIntensity: .55, roughness: .35 }),
    bulb: new THREE.MeshBasicMaterial({ color: "#ffe2a8", toneMapped: false }),
    flame: new THREE.MeshBasicMaterial({ color: "#ffcc6e", toneMapped: false }),
    candle: standard("#efe4cc", { roughness: .6 }),
    runner: standard("#5b1f19", { roughness: 1 }),
  };

  // ---------------------------------------------------------------- ışık
  scene.add(new THREE.HemisphereLight("#ffd9a8", "#24170f", .6));
  const moon = new THREE.DirectionalLight("#cfdcff", .35); moon.position.set(0, 8, -16); scene.add(moon, moon.target);

  // ---------------------------------------------------------------- yapı: tek çizimde birleşen kutular
  const structure = { walnut: [], dark: [] };
  const sbox = (kind, x, y, z, sx, sy, sz) => structure[kind].push([x, y, z, sx, sy, sz]);
  const at = (o, a, n, s, y, d) => v3(o.x + a.x * s - n.x * d, y, o.z + a.z * s - n.z * d);
  const sizeOf = (a, n, sa, sy, sn) => [Math.abs(a.x) * sa + Math.abs(n.x) * sn, sy, Math.abs(a.z) * sa + Math.abs(n.z) * sn];
  function caseBox(kind, o, a, n, s, y, d, sa, sy, sn) { const p = at(o, a, n, s, y, d), [sx, , sz] = sizeOf(a, n, sa, sy, sn); sbox(kind, p.x, p.y, p.z, sx, sy, sz); }

  // Raf yuvaları: her kitap için konum/boyut; dekor kitaplar tek InstancedMesh'te.
  const slots = [];
  const tones = ["#5b2a22", "#2f3b2a", "#2b2f45", "#4a3426", "#6b4b2a", "#1f2d33", "#3d2433", "#6a5a3a", "#2a2320"];
  const basis = new THREE.Matrix4(), tmpM = new THREE.Matrix4(), tmpS = v3(), tmpQ = new THREE.Quaternion();
  function fillRow(o, a, n, y, from, to, random, color, list) {
    let s = from + .01;
    while (true) {
      const t = .032 + random() * .045, h = .24 + random() * .11, d = .17 + random() * .07;
      if (s + t > to - .01) break;
      const c = at(o, a, n, s + t / 2, y + .015 + h / 2, d / 2 + .012);
      basis.makeBasis(a, UP, n); tmpQ.setFromRotationMatrix(basis);
      const m = new THREE.Matrix4().compose(c, tmpQ, tmpS.set(t, h, d));
      const tone = random() < .38 ? color : tones[Math.floor(random() * tones.length)];
      const slot = { m, color: tone, n: n.clone(), index: slots.length };
      slots.push(slot); list?.push(slot);
      s += t + (random() < .04 ? .05 + random() * .08 : .002);
    }
  }
  function compartments(length, size = 1.18) {
    const count = Math.max(1, Math.round(length / size)), w = length / count, out = [];
    for (let i = 0; i < count; i++) out.push([i * w + (i ? .02 : 0), (i + 1) * w - (i < count - 1 ? .02 : 0)]);
    return out;
  }
  /** Duvar kitaplığı bölümü (tek yüzlü, tavana yakın). */
  function wallSection(side, zA, zB, color, seed, real = false) {
    const n = v3(-side, 0, 0), a = new THREE.Vector3().crossVectors(UP, n), L = zB - zA;
    const o = v3(side * FACE, 0, a.z < 0 ? zB : zA);
    caseBox("walnut", o, a, n, L / 2, WALL_H / 2, DEPTH - .01, L, WALL_H, .02);
    caseBox("dark", o, a, n, L / 2, .06, DEPTH / 2, L, .12, DEPTH);
    caseBox("dark", o, a, n, L / 2, WALL_H + .09, DEPTH / 2 - .04, L + .04, .18, DEPTH + .08);
    const parts = compartments(L);
    for (const [, end] of parts.slice(0, -1)) caseBox("walnut", o, a, n, end + .02, WALL_H / 2, DEPTH / 2, .04, WALL_H, DEPTH - .02);
    for (const s of [0, L]) caseBox("walnut", o, a, n, s, WALL_H / 2, DEPTH / 2, .05, WALL_H, DEPTH);
    const random = rng(seed), rows = new Map();
    WALL_ROWS.forEach((y, k) => {
      caseBox("walnut", o, a, n, L / 2, y, DEPTH / 2, L, .03, DEPTH);
      const list = real && REAL_ROWS.includes(k) ? [] : null;
      for (const [from, to] of parts) fillRow(o, a, n, y, from, to, random, color, list);
      if (list) rows.set(k, list);
    });
    // Galeri yürüyüş yolu: 8. raf hizasında öne taşan döşeme
    caseBox("dark", o, a, n, L / 2, WALL_ROWS[8] - .02, -.27, L, .07, .55);
    const section = { side, zA, zB, color, real, realSlots: REAL_ROWS.flatMap((k) => rows.get(k) || []), items: [], mesh: null, hidden: [], offsets: null, targets: null, base: null };
    sections.push(section); return section;
  }
  /** Koridora dik, çift yüzlü alçak kitaplık (bölmeleri ayırır). */
  function perpCase(side, z, seed) {
    const x0 = side * 3.2, x1 = side * FACE, len = Math.abs(x1 - x0);
    sbox("walnut", (x0 + x1) / 2, PERP_H / 2, z, len, PERP_H, .02);
    sbox("dark", (x0 + x1) / 2, .06, z, len, .12, .5);
    sbox("dark", (x0 + x1) / 2, PERP_H + .07, z, len + .06, .14, .58);
    sbox("walnut", x0, PERP_H / 2, z, .08, PERP_H + .02, .54);
    sbox("dark", x0 - side * .04, 1.7, z, .03, 2.6, .3);
    walker.addCollider((x0 + x1) / 2, z, len, .5, .3);
    const random = rng(seed);
    for (const nz of [1, -1]) {
      const n = v3(0, 0, nz), a = new THREE.Vector3().crossVectors(UP, n);
      const o = v3(a.x > 0 ? Math.min(x0, x1) : Math.max(x0, x1), 0, z + nz * .25);
      PERP_ROWS.forEach((y) => { caseBox("walnut", o, a, n, len / 2, y, .125, len, .03, .25); fillRow(o, a, n, y, .05, len - .06, random, CATS[Math.floor(random() * CATS.length)][2], null); });
    }
  }

  // ---------------------------------------------------------------- salon kabuğu
  const floorTex = woodTexture({ base: "#5b3e2b", dark: "#2c1d13", planks: 12, repeat: [2, 6], herringbone: true });
  const floor = plane(scene, 12, 30, standard("#6b4a33", { map: floorTex, roughness: .8 }), 0, 0, 0);
  floor.rotation.x = -Math.PI / 2; floor.receiveShadow = true; floor.userData.floor = true; pickables.push(floor);
  const runner = plane(scene, 2.4, 25, M.runner, 0, .005, -.5); runner.rotation.x = -Math.PI / 2; runner.userData.floor = true; pickables.push(runner);
  for (const x of [-1.15, 1.15]) { const edge = plane(scene, .06, 25, M.brass, x, .006, -.5); edge.rotation.x = -Math.PI / 2; edge.userData.noPick = true; }
  sbox("dark", 0, 7.05, 0, 12.4, .1, 30.4);
  for (let z = -14; z <= 14; z += 2.5) sbox("dark", 0, 6.85, z, 12, .3, .32);
  for (const side of [-1, 1]) { const wall = new THREE.Mesh(new THREE.BoxGeometry(.2, 7, 30.2), M.stone); wall.position.set(side * 6.1, 3.5, 0); scene.add(wall); }
  const endWall = new THREE.Mesh(new THREE.BoxGeometry(12.2, 7, .2), M.stone); endWall.position.set(0, 3.5, -15.1); scene.add(endWall);
  const frontWall = endWall.clone(); frontWall.position.z = 15.1; scene.add(frontWall);

  // ---------------------------------------------------------------- kitaplıklar
  const wallSpans = [[-14.6, -13.85], [-13.35, -8.65], [-8.15, -3.45], [-2.95, 1.75], [2.25, 6.95], [7.45, 12.15], [12.65, 14.6]];
  const bayOfSpan = (zA, zB) => { const zc = (zA + zB) / 2; for (let i = 0; i < 5; i++) if (Math.abs(bayCenter(i) - zc) < .5) return i; return -1; };
  let seed = 11;
  for (const side of [-1, 1]) {
    for (const [zA, zB] of wallSpans) {
      const i = bayOfSpan(zA, zB), cat = i >= 0 ? CATS[(side < 0 ? 0 : 5) + i] : null;
      const entranceNew = side < 0 && zA > 12;
      const section = wallSection(side, zA, zB, cat ? cat[2] : entranceNew ? "#7a5a2a" : "#4a3426", seed += 7, !!cat || entranceNew);
      if (cat) { section.key = cat[0]; bays.push({ key: cat[0], name: cat[1], color: cat[2], side, index: i, section, all: [] }); }
      if (entranceNew) { section.key = "new"; bays.push({ key: "new", name: "Bağışlar — Yeni gelenler", color: "#7a5a2a", side, index: -1, section, all: [] }); }
    }
    for (let i = 0; i <= 5; i++) perpCase(side, bayCenter(i) + BAY / 2, seed += 5); // 12.4, 7.2, 2.0, -3.2, -8.4, -13.6
    // pirinç ray ve galeri korkuluğu
    const rail = cyl(scene, .018, .018, 29, side * 5.47, 3.38, 0, M.brass, 8); rail.rotation.x = Math.PI / 2; rail.userData.noPick = true;
    const top = cyl(scene, .025, .025, 29.2, side * 5.02, 4.35, 0, M.brass, 8); top.rotation.x = Math.PI / 2; top.userData.noPick = true;
    for (let z = -14.4; z <= 14.4; z += .9) sbox("dark", side * 5.02, 3.92, z, .04, .86, .04);
  }

  for (const [kind, list] of Object.entries(structure)) {
    const inst = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), M[kind], list.length), d = new THREE.Object3D();
    list.forEach(([x, y, z, sx, sy, sz], i) => { d.position.set(x, y, z); d.scale.set(sx, sy, sz); d.updateMatrix(); inst.setMatrixAt(i, d.matrix); });
    inst.receiveShadow = true; scene.add(inst); pickables.push(inst);
  }
  const fillerGeo = new THREE.BoxGeometry(1, 1, 1);
  const filler = new THREE.InstancedMesh(fillerGeo, standard("#ffffff", { roughness: .75 }), slots.length);
  const color = new THREE.Color();
  slots.forEach((s) => { filler.setMatrixAt(s.index, s.m); filler.setColorAt(s.index, color.set(s.color)); });
  filler.instanceMatrix.needsUpdate = true; if (filler.instanceColor) filler.instanceColor.needsUpdate = true;
  filler.frustumCulled = false; scene.add(filler);
  const ZERO = new THREE.Matrix4().makeScale(0, 0, 0);

  // ---------------------------------------------------------------- bölme tabelaları
  for (const bay of bays) {
    const zc = bay.index >= 0 ? bayCenter(bay.index) : 13.6;
    const g = new THREE.Group(); g.position.set(bay.side * (bay.index >= 0 ? 3.05 : 5.5), bay.index >= 0 ? 3.75 : 2.95, zc); g.rotation.y = bay.side < 0 ? Math.PI / 2 : -Math.PI / 2; scene.add(g);
    const signMat = basic(brassTexture(bay.name, "Raflar dolduruluyor…", { wood: true }));
    const sign = plane(g, 2.1, .46, signMat, 0, 0, 0); sign.material.side = THREE.DoubleSide;
    if (bay.index >= 0) for (const x of [-.85, .85]) { const chain = cyl(g, .008, .008, 3.0, x, 1.73, 0, M.iron, 6); chain.userData.noPick = true; }
    sign.userData.pick = { type: "bay", bay }; bay.sign = sign; pickables.push(sign);
  }
  function setBaySign(bay, text) { const old = bay.sign.material.map; bay.sign.material.map = brassTexture(bay.name, text, { wood: true }); bay.sign.material.needsUpdate = true; old?.dispose(); }

  // ---------------------------------------------------------------- gerçek kitaplar (atlas dokulu tek geometri)
  const unit = new THREE.BoxGeometry(1, 1, 1).toNonIndexed();
  const UP_ = unit.attributes.position.array, UN = unit.attributes.normal.array, UV = unit.attributes.uv.array;
  function buildReal(section, items) {
    if (section.mesh) { section.mesh.removeFromParent(); section.mesh.geometry.dispose(); section.mesh.material.map.dispose(); section.mesh.material.dispose(); pickables.splice(pickables.indexOf(section.mesh), 1); section.mesh = null; }
    section.hidden.forEach((s) => filler.setMatrixAt(s.index, s.m)); section.hidden = [];
    const list = items.slice(0, Math.min(MAX_REAL, section.realSlots.length));
    section.items = list;
    if (!list.length) { filler.instanceMatrix.needsUpdate = true; return; }
    const [atlas, ctx] = makeCanvas(1024, 1024);
    ctx.fillStyle = "#e6d8b8"; ctx.fillRect(0, 992, 1024, 32);
    const pos = new Float32Array(list.length * 108), nor = new Float32Array(list.length * 108), uv = new Float32Array(list.length * 72);
    const p = v3(), nn = v3(), nm = new THREE.Matrix3();
    const pageU = 16 / 1024, pageV = 1 - 1008 / 1024;
    list.forEach((item, b) => {
      const slot = section.realSlots[b]; section.hidden.push(slot); filler.setMatrixAt(slot.index, ZERO);
      const col = b % 16, row = Math.floor(b / 16), cx = col * CELL_W, cy = row * CELL_H;
      drawSpine(ctx, item, cx, cy, CELL_W, CELL_H, section.color);
      const u0 = cx / 1024, u1 = (cx + CELL_W) / 1024, vTop = 1 - cy / 1024, vBot = 1 - (cy + CELL_H) / 1024;
      const coverU = (cx + 3) / 1024, coverV = 1 - (cy + 128) / 1024;
      nm.getNormalMatrix(slot.m);
      for (let v = 0; v < 36; v++) {
        p.set(UP_[v * 3], UP_[v * 3 + 1], UP_[v * 3 + 2]).applyMatrix4(slot.m); pos.set([p.x, p.y, p.z], (b * 36 + v) * 3);
        nn.set(UN[v * 3], UN[v * 3 + 1], UN[v * 3 + 2]).applyMatrix3(nm).normalize(); nor.set([nn.x, nn.y, nn.z], (b * 36 + v) * 3);
        const face = Math.floor(v / 6);
        if (face === 4) uv.set([u0 + UV[v * 2] * (u1 - u0), vBot + UV[v * 2 + 1] * (vTop - vBot)], (b * 36 + v) * 2);
        else if (face === 2 || face === 3) uv.set([pageU, pageV], (b * 36 + v) * 2);
        else uv.set([coverU, coverV], (b * 36 + v) * 2);
      }
    });
    filler.instanceMatrix.needsUpdate = true;
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3)); geo.setAttribute("normal", new THREE.BufferAttribute(nor, 3)); geo.setAttribute("uv", new THREE.BufferAttribute(uv, 2));
    geo.computeBoundingSphere();
    const mesh = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ map: canvasTexture(atlas, 8), roughness: .62 }));
    mesh.userData.pick = { type: "book", section };
    scene.add(mesh); pickables.push(mesh);
    section.mesh = mesh; section.base = pos.slice(); section.offsets = new Float32Array(list.length); section.targets = new Float32Array(list.length);
  }
  function setOffset(section, b, value) {
    const pos = section.mesh.geometry.attributes.position, n = section.realSlots[b].n;
    for (let v = 0; v < 36; v++) { const i = (b * 36 + v) * 3; pos.array[i] = section.base[i] + n.x * value; pos.array[i + 2] = section.base[i + 2] + n.z * value; }
    pos.needsUpdate = true;
  }

  // ---------------------------------------------------------------- okuma masaları ve lambalar
  function table(zc) {
    const g = new THREE.Group(); g.position.set(0, 0, zc); scene.add(g);
    const top = new THREE.Mesh(new THREE.BoxGeometry(1.3, .07, 5.6), M.walnut); top.position.y = .79; top.castShadow = top.receiveShadow = true; g.add(top);
    for (const x of [-.55, .55]) for (const z of [-2.5, 0, 2.5]) { const leg = cyl(g, .05, .06, .76, x, .38, z, M.dark, 10); leg.castShadow = false; }
    for (const x of [-1.02, 1.02]) { const seat = new THREE.Mesh(new THREE.BoxGeometry(.42, .08, 5.3), M.leather); seat.position.set(x, .46, 0); g.add(seat); for (const z of [-2.4, 2.4]) { const l = new THREE.Mesh(new THREE.BoxGeometry(.36, .42, .06), M.dark); l.position.set(x, .21, z); g.add(l); } }
    for (let z = -2.1; z <= 2.11; z += 1.4) {
      cyl(g, .07, .08, .025, 0, .835, z, M.brass, 16); cyl(g, .011, .011, .3, 0, .99, z, M.brass, 8);
      const shade = new THREE.Mesh(new THREE.CylinderGeometry(.13, .13, .26, 16, 1, false, 0, Math.PI), M.shade); shade.rotation.z = Math.PI / 2; shade.rotation.y = Math.PI / 2; shade.position.set(0, 1.15, z); g.add(shade);
      const bulb = new THREE.Mesh(new THREE.SphereGeometry(.035, 8, 6), M.bulb); bulb.position.set(0, 1.11, z); g.add(bulb);
    }
    const light = new THREE.PointLight("#ffd79a", 7, 7, 2); light.position.set(0, 1.35, zc); scene.add(light); lights.push({ light, base: 7 });
    walker.addCollider(0, zc, 2.5, 5.7, .25);
    g.userData.pick = { type: "table" };
  }
  table(-6.0); table(4.4);

  // ---------------------------------------------------------------- avizeler
  function chandelier(z) {
    const g = new THREE.Group(); g.position.set(0, 5.5, z); scene.add(g);
    const ring = new THREE.Mesh(new THREE.TorusGeometry(.85, .03, 8, 40), M.iron); ring.rotation.x = Math.PI / 2; g.add(ring);
    const inner = new THREE.Mesh(new THREE.TorusGeometry(.45, .025, 8, 30), M.iron); inner.rotation.x = Math.PI / 2; inner.position.y = -.25; g.add(inner);
    cyl(g, .012, .012, 1.45, 0, .72, 0, M.iron, 6);
    for (let i = 0; i < 12; i++) {
      const a = i / 12 * Math.PI * 2, r = i % 2 ? .85 : .45, y = i % 2 ? 0 : -.25;
      cyl(g, .018, .02, .12, Math.cos(a) * r, y + .07, Math.sin(a) * r, M.candle, 8);
      const f = new THREE.Mesh(new THREE.SphereGeometry(.017, 8, 6), M.flame); f.scale.set(1, 1.8, 1); f.position.set(Math.cos(a) * r, y + .16, Math.sin(a) * r); g.add(f); flames.push(f);
    }
    const light = new THREE.PointLight("#ffc77d", 26, 15, 2); light.position.set(0, 5.4, z); scene.add(light); lights.push({ light, base: 26 });
  }
  chandelier(-10.5); chandelier(-.6); chandelier(9.4);

  // ---------------------------------------------------------------- pencereler ve ışık huzmeleri
  for (const x of [-3.2, 0, 3.2]) {
    const glass = new THREE.Mesh(new THREE.ShapeGeometry(archShape(1.5, 3.8), 24), new THREE.MeshBasicMaterial({ color: "#e9d3a6", toneMapped: false }));
    glass.position.set(x, 2.4, -14.98); scene.add(glass);
    for (const dx of [-.25, .25]) { const bar = new THREE.Mesh(new THREE.BoxGeometry(.04, 3.8, .04), M.iron); bar.position.set(x + dx, 4.3, -14.96); scene.add(bar); }
    for (const y of [3.3, 4.3, 5.3]) { const bar = new THREE.Mesh(new THREE.BoxGeometry(1.5, .04, .04), M.iron); bar.position.set(x, y, -14.96); scene.add(bar); }
    const beam = new THREE.Mesh(new THREE.CylinderGeometry(.7, 1.7, 8, 20, 1, true), new THREE.MeshBasicMaterial({ color: "#ffe2b0", transparent: true, opacity: .045, depthWrite: false, side: THREE.DoubleSide, blending: THREE.AdditiveBlending, toneMapped: false }));
    beam.position.set(x, 2.6, -11.8); beam.rotation.x = -1.05; beam.userData.noPick = true; scene.add(beam);
  }

  // ---------------------------------------------------------------- giriş kapısı ve karşılama kürsüsü
  const exitDoor = new THREE.Group(); exitDoor.position.set(0, 0, 14.98); exitDoor.rotation.y = Math.PI; scene.add(exitDoor);
  const band = archShape(2.0, 2.9); band.lineTo(.75, 0); band.lineTo(.75, 1.87); band.absarc(0, 1.87, .75, 0, Math.PI, false); band.lineTo(-.75, 0); band.lineTo(-1, 0);
  exitDoor.add(new THREE.Mesh(new THREE.ExtrudeGeometry(band, { depth: .14, bevelEnabled: false, curveSegments: 24 }), M.walnut));
  const leaf = new THREE.Mesh(new THREE.ShapeGeometry(archShape(1.5, 2.62), 24), M.dark); leaf.position.z = .03; exitDoor.add(leaf);
  const seam = new THREE.Mesh(new THREE.BoxGeometry(.03, 2.6, .02), M.iron); seam.position.set(0, 1.3, .05); exitDoor.add(seam);
  for (const x of [-.12, .12]) { const h = cyl(exitDoor, .05, .05, .02, x, 1.1, .06, M.brass, 16); h.rotation.x = Math.PI / 2; }
  plane(exitDoor, 1.7, .36, basic(brassTexture("↑ ÜST KAT", "Okuma salonuna dön")), 0, 3.12, .1);
  exitDoor.userData.pick = { type: "exit" }; pickables.push(exitDoor);
  const lectern = new THREE.Group(); lectern.position.set(2.4, 0, 12.3); lectern.rotation.y = -.5; scene.add(lectern);
  cyl(lectern, .22, .3, .08, 0, .04, 0, M.dark, 16); cyl(lectern, .07, .09, 1.0, 0, .55, 0, M.walnut, 12);
  const desk = new THREE.Mesh(new THREE.BoxGeometry(.7, .05, .5), M.walnut); desk.position.set(0, 1.08, 0); desk.rotation.x = .35; lectern.add(desk);
  const card = plane(lectern, .62, .42, basic(brassTexture("Arşiv Katı", "Kategoriler iki yanda · kitaba dokun, raftan al")), 0, 1.108, .012); card.rotation.x = -Math.PI / 2 + .35;
  walker.addCollider(2.4, 12.3, .6, .6, .2);

  // ---------------------------------------------------------------- raylı merdivenler
  for (const side of [-1, 1]) {
    const g = new THREE.Group(); g.position.set(side * 4.36, 0, side < 0 ? 4.6 : -5.8); g.rotation.z = -side * .19; scene.add(g);
    for (const x of [-.22, .22]) { const r = new THREE.Mesh(new THREE.BoxGeometry(.05, 3.45, .05), M.walnut); r.position.set(0, 1.72, x); r.castShadow = true; g.add(r); }
    for (let y = .3; y < 3.3; y += .32) { const step = new THREE.Mesh(new THREE.BoxGeometry(.06, .035, .48), M.walnut); step.position.set(0, y, 0); g.add(step); }
    for (const x of [-.22, .22]) { const w = cyl(g, .045, .045, .03, 0, .05, x, M.brass, 12); w.rotation.z = Math.PI / 2; }
    const zc = g.position.z, ladder = { group: g, side, min: zc - 2.0, max: zc + 2.0 };
    g.userData.pick = { type: "ladder", ladder }; pickables.push(g); ladders.push(ladder);
  }

  // ---------------------------------------------------------------- toz
  const dustCount = 700, dustPos = new Float32Array(dustCount * 3);
  for (let i = 0; i < dustCount; i++) { dustPos[i * 3] = (Math.random() - .5) * 10; dustPos[i * 3 + 1] = .3 + Math.random() * 6.2; dustPos[i * 3 + 2] = (Math.random() - .5) * 28; }
  const dustGeo = new THREE.BufferGeometry(); dustGeo.setAttribute("position", new THREE.BufferAttribute(dustPos, 3));
  const dust = new THREE.Points(dustGeo, new THREE.PointsMaterial({ color: "#f2dcab", size: .022, transparent: true, opacity: .5, depthWrite: false }));
  dust.userData.noPick = true; scene.add(dust);

  // ---------------------------------------------------------------- veri
  async function load(force = false) {
    if (loading && !force) return loading;
    for (const bay of bays) setBaySign(bay, "Raflar dolduruluyor…");
    loading = api("/api/library/archive", { timeout: 240000 }).then((data) => {
      const byKey = new Map((data.categories || []).map((c) => [c.key, c]));
      for (const bay of bays) {
        const c = byKey.get(bay.key);
        const all = c ? [...(c.donations || []), ...(c.oa || [])].map((x) => ({ ...x, archive: true, category_name: bay.name })) : [];
        bay.all = all; buildReal(bay.section, all);
        const donated = c?.donations?.length || 0;
        setBaySign(bay, all.length ? `${all.length} kitap${donated ? ` · ${donated} bağış` : ""} · listeyi aç` : "Henüz kitap yok");
      }
      return data;
    }).catch((e) => { for (const bay of bays) setBaySign(bay, "Kitaplar alınamadı · tekrar girişte denenecek"); loading = null; throw e; });
    return loading;
  }
  const refresh = () => { loading = null; return load(true); };

  // ---------------------------------------------------------------- etkileşim
  function raycast(clientX, clientY) {
    ndc.set(clientX / innerWidth * 2 - 1, 1 - clientY / innerHeight * 2);
    raycaster.setFromCamera(ndc, camera);
    return raycaster.intersectObjects(pickables, true).find((h) => h.object.visible && !h.object.userData.noPick && h.distance < 30) || null;
  }
  const bookOf = (hit) => { const pick = hit ? pickOf(hit.object) : null; if (pick?.type !== "book" || hit.faceIndex == null) return null; const b = Math.floor(hit.faceIndex / 12); return pick.section.items[b] ? { section: pick.section, b, item: pick.section.items[b] } : null; };
  function hover(hit) {
    const ref = bookOf(hit);
    if (hovered && (!ref || ref.section !== hovered.section || ref.b !== hovered.b) && hovered.section.targets && hovered.section.targets[hovered.b] < .1) hovered.section.targets[hovered.b] = 0;
    hovered = ref;
    if (ref) { if (ref.section.targets[ref.b] < .04) ref.section.targets[ref.b] = .04; return { item: ref.item, clickable: true }; }
    const pick = hit ? pickOf(hit.object) : null;
    if (pick?.type === "bay") return { item: { title: pick.bay.name, kind: "bay", venue: `${pick.bay.all.length} kitap · listeyi aç` }, clickable: true };
    if (pick && pick.type !== "table") return { clickable: true };
    return { clickable: !!hit?.object.userData.floor };
  }
  function click(hit) {
    if (!hit) return null;
    const ref = bookOf(hit);
    if (ref) return { type: "book", item: ref.item, ref };
    const pick = pickOf(hit.object);
    if (pick?.type === "bay") return { type: "bay", title: pick.bay.name, items: pick.bay.all };
    if (pick?.type === "exit") return { type: "exit" };
    if (pick?.type === "ladder") return { type: "ladder", ladder: pick.ladder };
    if (hit.object.userData.floor) return { type: "walk", point: hit.point };
    return null;
  }
  function pullBook(ref) {
    if (!ref?.section.targets) return Promise.resolve();
    ref.section.targets[ref.b] = .17;
    return new Promise((r) => setTimeout(r, reduced ? 0 : 380));
  }
  function pushBook(ref) { if (ref?.section.targets) ref.section.targets[ref.b] = 0; }
  async function climb(ladder) {
    if (climbed) return descend();
    const p = ladder.group.position, s = ladder.side;
    climbed = { ladder, from: camera.position.clone(), yaw: walker.yaw, pitch: walker.pitch };
    walker.locked = true; walker.goal = null;
    const start = camera.position.clone(), end = v3(s * 4.45, 2.95, p.z), y0 = walker.yaw, p0 = walker.pitch, y1 = s < 0 ? Math.PI / 2 : -Math.PI / 2;
    let dy = y1 - y0; dy = Math.atan2(Math.sin(dy), Math.cos(dy));
    await tween(900, (k) => { camera.position.lerpVectors(start, end, k); walker.yaw = y0 + dy * k; walker.pitch = p0 + (.12 - p0) * k; });
  }
  async function descend() {
    if (!climbed) return;
    const s = climbed.ladder.side, p = climbed.ladder.group.position, start = camera.position.clone(), end = v3(s * 3.9, EYE, p.z);
    climbed = null;
    await tween(700, (k) => { camera.position.lerpVectors(start, end, k); walker.pitch *= 1 - k * .5; });
    walker.locked = false;
  }
  function dragLadder(ladder, dz) { ladder.group.position.z = THREE.MathUtils.clamp(ladder.group.position.z + dz, ladder.min, ladder.max); }

  // ---------------------------------------------------------------- kare
  function update(dt, now) {
    for (const s of sections) {
      if (!s.mesh) continue;
      for (let b = 0; b < s.offsets.length; b++) {
        const want = s.targets[b], cur = s.offsets[b];
        if (cur === want) continue;
        let next = cur + (want - cur) * Math.min(1, dt * 10);
        if (Math.abs(next - want) < .002) next = want;
        s.offsets[b] = next; setOffset(s, b, next);
      }
    }
    if (!reduced) {
      dust.position.y = Math.sin(now * .00015) * .12; dust.rotation.y = Math.sin(now * .00005) * .02;
      const flick = (Math.sin(now * .011) + Math.sin(now * .017 + 1.3) + Math.sin(now * .029 + 2.1)) / 3;
      for (const { light, base } of lights) light.intensity = base * (1 + flick * .06);
      flames.forEach((f, i) => { f.scale.y = 1.8 + Math.sin(now * .02 + i) * .25; });
    }
  }
  function resize() { camera.aspect = innerWidth / innerHeight; camera.updateProjectionMatrix(); }

  return {
    id: "archive", scene, camera, walker, raycast, hover, click, update, resize, load, refresh, pullBook, pushBook, climb, descend, dragLadder,
    isClimbed: () => !!climbed, bays, spawn: { x: 0, z: 13.2, yaw: 0 },
  };
}
