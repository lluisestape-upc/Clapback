// 3D room view (three.js from jsDelivr via the import map in index.html, no build step).
//
// Layers to add, all fed by the engine's Grid output (clapback/acoustics/maps.py):
//   - STI / C50 heat map on the floor plane
//   - modal pressure slice at a chosen frequency; sweep the frequency to
//     animate the bass nodes (the demo's wow shot)
//   - (extra) first-order image-source rays from the source
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

let renderer, scene, camera, controls, roomGroup;

function init(el) {
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(devicePixelRatio);
  el.appendChild(renderer.domElement);
  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(50, 4 / 3, 0.1, 100);
  controls = new OrbitControls(camera, renderer.domElement);
  scene.add(new THREE.AmbientLight(0xffffff, 1));

  const resize = () => {
    const w = el.clientWidth, h = el.clientHeight;
    renderer.setSize(w, h);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  };
  new ResizeObserver(resize).observe(el);
  resize();
  renderer.setAnimationLoop(() => { controls.update(); renderer.render(scene, camera); });
}

// Room coords are z-up; three.js is y-up. Room (x, y, z) → three (x, z, -y).
export function showRoom(el, room) {
  if (!renderer) init(el);
  if (roomGroup) scene.remove(roomGroup);
  roomGroup = new THREE.Group();

  const shape = new THREE.Shape(room.floor.map((p) => new THREE.Vector2(p.x, p.y)));
  const walls = new THREE.ExtrudeGeometry(shape, { depth: room.height, bevelEnabled: false });
  walls.rotateX(-Math.PI / 2);
  roomGroup.add(new THREE.LineSegments(
    new THREE.EdgesGeometry(walls),
    new THREE.LineBasicMaterial({ color: 0xd9480f }),
  ));
  const floor = new THREE.ShapeGeometry(shape);
  floor.rotateX(-Math.PI / 2);
  roomGroup.add(new THREE.Mesh(floor, new THREE.MeshBasicMaterial({
    color: 0x888888, transparent: true, opacity: 0.25, side: THREE.DoubleSide,
  })));
  scene.add(roomGroup);

  const box = new THREE.Box3().setFromObject(roomGroup);
  const c = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3()).length();
  camera.position.set(c.x + size * 0.8, c.y + size * 0.7, c.z + size * 0.8);
  controls.target.copy(c);
}

// TODO showGrid(grid, { layer: "sti" | "c50" | "modal" })
