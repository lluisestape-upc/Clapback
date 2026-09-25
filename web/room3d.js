// 3D room view (three.js from jsDelivr via the import map in index.html, no build step).
//
// Layers to add, all fed by the engine's Grid output (clapback/acoustics/maps.py):
//   - STI / C50 heat map on the floor plane
//   - modal pressure slice at a chosen frequency; sweep the frequency to
//     animate the bass nodes (the demo's wow shot)
//   - (extra) first-order image-source rays from the source
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

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
  renderer.setAnimationLoop(() => {
    if (!el.offsetParent) return; // hidden screen: skip rendering
    controls.update();
    renderer.render(scene, camera);
  });
  return { renderer, scene, camera, controls, group: null, framed: false };
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
  v.camera.position.set(c.x + size * 0.95, c.y + size * 0.7, c.z + size * 0.95);
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
  if (v.layer) { v.scene.remove(v.layer); v.layer.geometry.dispose(); }
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
