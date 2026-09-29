// 3D room view (three.js from jsDelivr via the import map in index.html, no build step).
//
// Layers, all fed by the engine (clapback/acoustics/maps.py, geometry.py) or by
// the node-tested math in acoustics3d.js:
//   - a map on a horizontal plane: speech clarity, a bass slice, where to sit
//   - heat on the walls, floor and ceiling where early reflections land, with
//     the reflection paths drawn from the source to the listener
//   - the treatments of the plan, as pieces where they go
//   - the modal field of one bass note in the whole volume
//   - the clap replay: sound particles bouncing and fading
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { planes, local, heatAt, hitsBySurface, inFloor } from "./acoustics3d.js";

const views = new Map(); // container element → view

function makeView(el) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  el.appendChild(renderer.domElement);
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 200);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.enablePan = false;
  controls.autoRotate = true;
  controls.autoRotateSpeed = 1.2;
  controls.addEventListener("start", () => { controls.autoRotate = false; });

  const resize = () => {
    const w = el.clientWidth, h = el.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  };
  new ResizeObserver(resize).observe(el);
  resize();
  const frame = new Set();   // per-frame callbacks (the clap replay)
  renderer.setAnimationLoop(() => {
    if (!el.offsetParent) return; // hidden screen: skip rendering
    for (const f of frame) f();
    controls.update();
    renderer.render(scene, camera);
  });
  return { renderer, scene, camera, controls, group: null, framed: false, frame };
}

const accent = () =>
  getComputedStyle(document.documentElement).getPropertyValue("--accent").trim() || "#d9480f";

// Room coords are z-up; three.js is y-up. Room (x, y, z) → three (x, z, -y).
export function showRoom(el, room) {
  let v = views.get(el);
  if (!v) { v = makeView(el); views.set(el, v); }
  if (v.group) v.scene.remove(v.group);
  const g = new THREE.Group();

  const shape = new THREE.Shape(room.floor.map((p) => new THREE.Vector2(p.x, p.y)));
  const solid = new THREE.ExtrudeGeometry(shape, { depth: room.height, bevelEnabled: false });
  solid.rotateX(-Math.PI / 2);
  g.add(new THREE.LineSegments(
    new THREE.EdgesGeometry(solid),
    new THREE.LineBasicMaterial({ color: accent() }),
  ));
  g.add(new THREE.Mesh(solid, new THREE.MeshBasicMaterial({
    color: accent(), transparent: true, opacity: 0.06, side: THREE.BackSide, depthWrite: false,
  })));

  const floor = new THREE.ShapeGeometry(shape);
  floor.rotateX(-Math.PI / 2);
  g.add(new THREE.Mesh(floor, new THREE.MeshBasicMaterial({
    color: 0x9a948b, transparent: true, opacity: 0.22, side: THREE.DoubleSide,
  })));

  // Wall letters, as the plan's positions refer to them
  for (const pl of planes(room)) {
    if (pl.kind !== "wall") continue;
    const s = label(pl.name.slice(-1));
    s.position.copy(T(pl.start[0] + pl.along[0] * pl.length / 2, pl.start[1] + pl.along[1] * pl.length / 2, room.height + 0.35));
    g.add(s);
  }

  // A person for scale (1.7 m)
  const person = new THREE.Mesh(
    new THREE.CapsuleGeometry(0.18, 1.34, 4, 12),
    new THREE.MeshBasicMaterial({ color: 0x6b665e, transparent: true, opacity: 0.6 }),
  );
  const box0 = new THREE.Box3().setFromObject(g);
  const c0 = box0.getCenter(new THREE.Vector3());
  person.position.set(c0.x, 0.85, c0.z);
  g.add(person);

  v.scene.add(g);
  v.group = g;

  const box = new THREE.Box3().setFromObject(g);
  const c = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3()).length();
  v.camera.position.set(c.x + size * 0.7, c.y + size * 0.55, c.z + size * 0.7);
  v.controls.target.copy(c);
}

// ---------- map layers ----------

// Colour ramps. Each stop is [value, [r, g, b]] in 0..1 space.
export const RAMPS = {
  // IEC 60268-16 bands: <0.45 poor, 0.45-0.6 fair, 0.6-0.75 good, >0.75 excellent
  sti: [[0.30, [0.79, 0.16, 0.16]], [0.45, [0.91, 0.35, 0.05]], [0.60, [0.98, 0.76, 0.2]], [0.75, [0.18, 0.62, 0.27]]],
  // bass level relative to the room median, dB: blue = quiet spot, red = boom
  modal: [[-12, [0.11, 0.49, 0.84]], [0, [0.85, 0.83, 0.8]], [12, [0.91, 0.35, 0.05]]],
};

function ramp(stops, v) {
  if (v <= stops[0][0]) return stops[0][1];
  for (let i = 1; i < stops.length; i++) {
    const [v1, c1] = stops[i];
    if (v <= v1) {
      const [v0, c0] = stops[i - 1];
      const t = (v - v0) / (v1 - v0);
      return c0.map((c, k) => c + (c1[k] - c) * t);
    }
  }
  return stops[stops.length - 1][1];
}

// grid: {xs, ys, values[j][i]} in room coords; drawn at height z.
export function showGrid(el, grid, rampName, z = 1.2) {
  const v = views.get(el);
  if (!v) return;
  if (v.layer) { v.scene.remove(v.layer); v.layer.geometry.dispose(); v.layer = null; }
  if (!grid) return;
  const nx = grid.xs.length, ny = grid.ys.length;
  const w = grid.xs[nx - 1] - grid.xs[0], h = grid.ys[ny - 1] - grid.ys[0];
  const geo = new THREE.PlaneGeometry(w, h, nx - 1, ny - 1);
  const colors = new Float32Array(nx * ny * 3);
  // PlaneGeometry vertices run row by row from top-left (+y) to bottom-right.
  for (let r = 0; r < ny; r++) {
    for (let c = 0; c < nx; c++) {
      const j = ny - 1 - r;
      const col = ramp(RAMPS[rampName], grid.values[j][c]);
      colors.set(col, (r * nx + c) * 3);
    }
  }
  geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  geo.rotateX(-Math.PI / 2);
  const mesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
    vertexColors: true, side: THREE.DoubleSide, transparent: true, opacity: 0.92,
  }));
  mesh.position.set(grid.xs[0] + w / 2, z, -(grid.ys[0] + h / 2));
  v.scene.add(mesh);
  v.layer = mesh;
}

export function showSource(el, src) {
  const v = views.get(el);
  if (!v) return;
  if (v.source) v.scene.remove(v.source);
  const m = new THREE.Mesh(new THREE.SphereGeometry(0.14, 20, 14), new THREE.MeshBasicMaterial({ color: accent() }));
  m.position.set(src.x, src.z, -src.y);
  v.scene.add(m);
  v.source = m;
}

// Same modal sum as clapback/acoustics/maps.py modal_pressure_map (the tested
// reference); duplicated here so a frequency sweep can animate at 60 fps.
export function modalGrid(room, freq, src, rt = 0.5, step = 0.25, z = 1.2) {
  const xsR = room.floor.map((p) => p.x), ysR = room.floor.map((p) => p.y);
  const x0 = Math.min(...xsR), y0 = Math.min(...ysR);
  const lx = Math.max(...xsR) - x0, ly = Math.max(...ysR) - y0, lz = room.height;
  const c = 343, fMax = Math.max(2 * freq, 60), w = 2 * Math.PI * freq, delta = 6.91 / rt;
  const xs = [], ys = [];
  for (let x = x0 + step / 2; x < x0 + lx; x += step) xs.push(x);
  for (let y = y0 + step / 2; y < y0 + ly; y += step) ys.push(y);

  const modes = [[0, 0, 0, 0]];
  const N = (L) => Math.floor((2 * fMax * L) / c) + 1;
  for (let a = 0; a <= N(lx); a++) for (let b = 0; b <= N(ly); b++) for (let d = 0; d <= N(lz); d++) {
    if (!a && !b && !d) continue;
    const f = (c / 2) * Math.hypot(a / lx, b / ly, d / lz);
    if (f <= fMax) modes.push([a, b, d, f]);
  }
  const re = ys.map(() => new Float64Array(xs.length)), im = ys.map(() => new Float64Array(xs.length));
  for (const [a, b, d, f] of modes) {
    const wn = 2 * Math.PI * f;
    const lam = (a ? 0.5 : 1) * (b ? 0.5 : 1) * (d ? 0.5 : 1);
    const ps = Math.cos(a * Math.PI * (src.x - x0) / lx) * Math.cos(b * Math.PI * (src.y - y0) / ly) * Math.cos(d * Math.PI * src.z / lz);
    const pz = Math.cos(d * Math.PI * z / lz);
    // 1 / (lam (wn² - w² + 2jδw))
    const dr = lam * (wn * wn - w * w), di = lam * 2 * delta * w, den = dr * dr + di * di;
    const cr = dr / den, ci = -di / den;
    const cx = xs.map((x) => Math.cos(a * Math.PI * (x - x0) / lx));
    ys.forEach((y, j) => {
      const k = ps * pz * Math.cos(b * Math.PI * (y - y0) / ly);
      for (let i = 0; i < xs.length; i++) { re[j][i] += k * cx[i] * cr; im[j][i] += k * cx[i] * ci; }
    });
  }
  const db = re.map((row, j) => Array.from(row, (r, i) => 20 * Math.log10(Math.hypot(r, im[j][i]) + 1e-12)));
  const flat = db.flat().sort((p, q) => p - q), med = flat[Math.floor(flat.length / 2)];
  return { xs, ys, values: db.map((row) => row.map((v) => v - med)), unit: "dB" };
}


// ---------- more layers ----------

const T = (x, y, z) => new THREE.Vector3(x, z, -y);   // room (z up) → three (y up)

function setObj(el, key, obj) {
  const v = views.get(el);
  if (!v) return null;
  if (v[key]) {
    v.scene.remove(v[key]);
    v[key].traverse((o) => { o.geometry?.dispose(); o.material?.map?.dispose(); o.material?.dispose(); });
  }
  v[key] = obj;
  if (obj) v.scene.add(obj);
  return v;
}

export function clear(el, ...keys) { for (const k of keys) setObj(el, k, null); }

function label(text) {
  const c = document.createElement("canvas");
  c.width = c.height = 64;
  const g = c.getContext("2d");
  g.fillStyle = accent();
  g.beginPath(); g.arc(32, 32, 28, 0, Math.PI * 2); g.fill();
  g.fillStyle = "#fff"; g.font = "bold 36px system-ui, sans-serif"; g.textAlign = "center"; g.textBaseline = "middle";
  g.fillText(text, 32, 34);
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c), depthTest: false }));
  s.scale.set(0.42, 0.42, 1);
  return s;
}

RAMPS.refl = [[-20, [0.85, 0.83, 0.8]], [-12, [0.98, 0.76, 0.2]], [-6, [0.91, 0.35, 0.05]], [0, [0.72, 0.1, 0.1]]];
RAMPS.even = [[2, [0.18, 0.62, 0.27]], [5, [0.98, 0.76, 0.2]], [9, [0.79, 0.16, 0.16]]];

// A surface as a grid of coloured vertices. at(u, v) → room point, col(u, v) → rgb or null (outside).
function surfaceMesh(nu, nv, U, V, at, col, offset, alphaOf = () => 0.9) {
  const pos = new Float32Array((nu + 1) * (nv + 1) * 3), rgba = new Float32Array((nu + 1) * (nv + 1) * 4);
  const idx = [];
  for (let j = 0; j <= nv; j++) for (let i = 0; i <= nu; i++) {
    const u = (U * i) / nu, w = (V * j) / nv, k = j * (nu + 1) + i;
    const p = at(u, w);
    const t = T(p[0] + offset[0], p[1] + offset[1], p[2] + offset[2]);
    pos.set([t.x, t.y, t.z], k * 3);
    const c = col(u, w);
    rgba.set(c ? [...c, alphaOf(u, w)] : [0, 0, 0, 0], k * 4);
    if (i < nu && j < nv) idx.push(k, k + 1, k + nu + 1, k + 1, k + nu + 2, k + nu + 1);
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geo.setAttribute("color", new THREE.BufferAttribute(rgba, 4));
  geo.setIndex(idx);
  return new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
    vertexColors: true, transparent: true, side: THREE.DoubleSide, depthWrite: false,
  }));
}

// Heat where early reflections land, relative to the strongest one now.
export function showReflections(el, room, reflections, { after = false, paths = 6, source, listener } = {}) {
  const g = new THREE.Group();
  if (!reflections?.length) { setObj(el, "refl", null); return; }
  const top = reflections[0].level_db;
  const hits = hitsBySurface(reflections, after);
  const res = 0.1;
  for (const pl of planes(room)) {
    const list = (hits[pl.name] ?? []).map(([x, y, z, l]) => [...local(pl, [x, y, z]), l - top]);
    if (!list.length) continue;
    const heat = (u, w) => heatAt(list, u, w);
    const col = (u, w) => ramp(RAMPS.refl, heat(u, w));
    const alphaOf = (u, w) => 0.92 * Math.max(0, Math.min(1, (heat(u, w) + 22) / 12));
    const off = pl.normal.map((n) => n * 0.01);
    if (pl.kind === "wall") {
      g.add(surfaceMesh(Math.ceil(pl.length / res), Math.ceil(room.height / res), pl.length, room.height,
        (u, w) => [pl.start[0] + pl.along[0] * u, pl.start[1] + pl.along[1] * u, w], col, off, alphaOf));
    } else {
      const xs = room.floor.map((p) => p.x), ys = room.floor.map((p) => p.y);
      const x0 = Math.min(...xs), y0 = Math.min(...ys), X = Math.max(...xs) - x0, Y = Math.max(...ys) - y0;
      const z = pl.kind === "floor" ? 0 : room.height;
      g.add(surfaceMesh(Math.ceil(X / res), Math.ceil(Y / res), X, Y, (u, w) => [x0 + u, y0 + w, z],
        (u, w) => (inFloor(room.floor, x0 + u, y0 + w) ? col(x0 + u, y0 + w) : null), off,
        (u, w) => alphaOf(x0 + u, y0 + w)));
    }
  }
  // the strongest paths: source → reflection point(s) → listener
  if (source && listener) {
    for (const r of reflections.slice(0, paths)) {
      const level = after && r.level_after_db != null ? r.level_after_db : r.level_db;
      const pts = [[source.x, source.y, source.z], ...r.points, [listener.x, listener.y, listener.z]].map((p) => T(...p));
      const c = ramp(RAMPS.refl, level - top);
      g.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({
        color: new THREE.Color(...c), transparent: true, opacity: after && r.covered ? 0.25 : 0.9,
      })));
    }
  }
  setObj(el, "refl", g);
}

// Source (orange), listener (blue), best seat (green ring on the floor).
export function showMarkers(el, { source, listener, seat } = {}) {
  const g = new THREE.Group();
  const ball = (p, color, r) => {
    const m = new THREE.Mesh(new THREE.SphereGeometry(r, 20, 14), new THREE.MeshBasicMaterial({ color }));
    m.position.copy(T(p.x, p.y, p.z));
    g.add(m);
  };
  if (source) ball(source, accent(), 0.16);
  if (listener) ball(listener, "#1c7ed6", 0.13);
  if (seat) {
    const ring = new THREE.Mesh(new THREE.RingGeometry(0.22, 0.3, 32), new THREE.MeshBasicMaterial({ color: "#2f9e44", side: THREE.DoubleSide }));
    ring.rotateX(-Math.PI / 2);
    ring.position.copy(T(seat.x, seat.y, 0.02));
    g.add(ring);
    const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, seat.z, 8), new THREE.MeshBasicMaterial({ color: "#2f9e44" }));
    pole.position.copy(T(seat.x, seat.y, seat.z / 2));
    g.add(pole);
  }
  setObj(el, "markers", g);
}

const PIECE = {
  panel_50: { color: "#2f6f8f", depth: 0.05 }, panel_100: { color: "#1f4f66", depth: 0.1 },
  curtain: { color: "#8a3b3b", depth: 0.06 }, rug: { color: "#a47148", depth: 0.015 },
  bookshelf: { color: "#7a5230", depth: 0.3 },
};

// The plan's pieces where geometry.place() put them.
export function showTreatments(el, rects) {
  if (!rects?.length) { setObj(el, "treat", null); return; }
  const g = new THREE.Group();
  const up = [0, 0, 1];
  for (const r of rects) {
    const s = PIECE[r.id] ?? { color: "#666", depth: 0.05 };
    const horizontal = Math.abs(r.normal[2]) > 0.5;
    const xAxis = T(...r.along), yAxis = horizontal ? T(0, 1, 0) : T(...up), zAxis = T(...r.normal);
    const m = new THREE.Mesh(new THREE.BoxGeometry(r.w * 0.96, r.h * 0.96, s.depth),
      new THREE.MeshBasicMaterial({ color: s.color, transparent: true, opacity: 0.92 }));
    m.matrixAutoUpdate = false;
    const c = T(r.center[0] + r.normal[0] * s.depth / 2, r.center[1] + r.normal[1] * s.depth / 2, r.center[2] + r.normal[2] * s.depth / 2);
    m.matrix.makeBasis(xAxis, yAxis, zAxis).setPosition(c);
    const edges = new THREE.LineSegments(new THREE.EdgesGeometry(m.geometry), new THREE.LineBasicMaterial({ color: "#1d1b18", transparent: true, opacity: 0.35 }));
    edges.matrixAutoUpdate = false;
    edges.matrix.copy(m.matrix);
    g.add(m, edges);
  }
  setObj(el, "treat", g);
}

// One bass note in the whole volume: points within 3 dB of the loudest
// (red, it booms) and more than 15 dB below it (blue, it vanishes); the
// in-between is left out so the lobes and the nodal planes show.
export const CLOUD_BOOM_DB = 3, CLOUD_HOLE_DB = 15;
export function showCloud(el, cloud) {
  if (!cloud) { setObj(el, "cloud", null); return; }
  let max = -Infinity;
  for (const d of cloud.db) max = Math.max(max, d);
  const keep = [], shade = [];
  for (let i = 0; i < cloud.db.length; i++) {
    const below = max - cloud.db[i];
    if (below <= CLOUD_BOOM_DB) { keep.push(i); shade.push(12); } else if (below >= CLOUD_HOLE_DB) { keep.push(i); shade.push(-12); }
  }
  const pos = new Float32Array(keep.length * 3), col = new Float32Array(keep.length * 3);
  keep.forEach((i, k) => {
    const t = T(cloud.points[i * 3], cloud.points[i * 3 + 1], cloud.points[i * 3 + 2]);
    pos.set([t.x, t.y, t.z], k * 3);
    col.set(ramp(RAMPS.modal, shade[k]), k * 3);
  });
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
  const pts = new THREE.Points(geo, new THREE.PointsMaterial({
    size: cloud.step * 0.55, vertexColors: true, transparent: true, opacity: 0.85, depthWrite: false,
  }));
  setObj(el, "cloud", pts);
}

// The clap replay. sim comes from acoustics3d.makeParticles; time runs
// `slow` times slower than real. onTick(t, levelDb) each frame; resolves when
// the sound has died away (60 dB) or after maxT seconds of room time.
export function playParticles(el, sim, { slow = 10, maxT = 2, onTick = () => {}, onDone = () => {} } = {}) {
  const v = views.get(el);
  if (!v) return () => {};
  const geo = new THREE.BufferGeometry();
  const pos = new Float32Array(sim.n * 3), rgba = new Float32Array(sim.n * 4);
  const base = new THREE.Color(accent());
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geo.setAttribute("color", new THREE.BufferAttribute(rgba, 4));
  const pts = new THREE.Points(geo, new THREE.PointsMaterial({ size: 0.1, vertexColors: true, transparent: true, depthWrite: false }));
  setObj(el, "particles", pts);
  let t = 0, last = performance.now(), done = false;
  const tick = () => {
    const now = performance.now();
    const dt = Math.min(0.05, (now - last) / 1000) / slow;
    last = now;
    for (let left = dt; left > 1e-6; left -= 0.002) sim.step(Math.min(0.002, left));
    t += dt;
    for (let i = 0; i < sim.n; i++) {
      pos[i * 3] = sim.pos[i * 3]; pos[i * 3 + 1] = sim.pos[i * 3 + 2]; pos[i * 3 + 2] = -sim.pos[i * 3 + 1];
      const b = Math.max(0, Math.min(1, (10 * Math.log10(sim.energy[i] + 1e-12) + 50) / 50));
      rgba.set([base.r, base.g, base.b, b], i * 4);
    }
    geo.attributes.position.needsUpdate = true;
    geo.attributes.color.needsUpdate = true;
    const level = sim.levelDb();
    onTick(t, level);
    if (level < -60 || t > maxT) stop();
  };
  const stop = () => {
    if (done) return;
    done = true;
    v.frame.delete(tick);
    onDone();
    setTimeout(() => setObj(el, "particles", null), 1200);
  };
  v.frame.add(tick);
  return stop;
}
