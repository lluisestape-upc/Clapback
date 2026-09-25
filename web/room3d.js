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

// TODO showGrid(el, grid, { layer: "sti" | "c50" | "modal" })
