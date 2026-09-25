// Guided AR scan (WebXR hit-test, Chrome on ARCore Android, HTTPS only).
//
// What the user sees:
//   "Point at a floor corner and tap"  → marker → "Next corner" → …
//   tap near the first corner (or "Done") to close the outline,
//   then set the ceiling height (hit-test can't find ceilings reliably).
//
// Output: the same Room JSON as the typed form (see clapback/room.py), with the
// first wall along +x and the floor starting at (0, 0). A 4-corner outline that
// is close to rectangular is snapped to an exact rectangle, so modes and maps
// (which need a box) work.
//
// Timebox: if this isn't working by 10-21, ship with typed dimensions;
// nothing else depends on this file.
import * as THREE from "three";

export async function arSupported() {
  if (!("xr" in navigator) || !window.isSecureContext) return false;
  try {
    return await navigator.xr.isSessionSupported("immersive-ar");
  } catch {
    return false;
  }
}

const CLOSE_M = 0.3;       // tap this close to the first corner to close the outline
const SNAP_DEG = 10;       // snap to a rectangle if every corner is within this of 90°

export async function startScan({ defaultHeight = 2.6 } = {}) {
  const overlay = buildOverlay();
  document.body.appendChild(overlay.root);

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(devicePixelRatio);
  renderer.setSize(innerWidth, innerHeight);
  renderer.xr.enabled = true;
  renderer.xr.setReferenceSpaceType("local");
  renderer.domElement.className = "ar-canvas";
  document.body.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera();
  const accent = new THREE.Color("#d9480f");

  const reticle = new THREE.Mesh(
    new THREE.RingGeometry(0.07, 0.1, 32).rotateX(-Math.PI / 2),
    new THREE.MeshBasicMaterial({ color: 0xffffff }),
  );
  reticle.matrixAutoUpdate = false;
  reticle.visible = false;
  scene.add(reticle);

  const corners = [];          // THREE.Vector3 in XR local space
  const markers = [];
  const lineGeo = new THREE.BufferGeometry();
  const line = new THREE.Line(lineGeo, new THREE.LineBasicMaterial({ color: accent }));
  scene.add(line);

  let session;
  try {
    session = await navigator.xr.requestSession("immersive-ar", {
      requiredFeatures: ["hit-test"],
      optionalFeatures: ["dom-overlay"],
      domOverlay: { root: overlay.root },
    });
  } catch (err) {
    cleanup();
    throw err;
  }
  await renderer.xr.setSession(session);
  const viewer = await session.requestReferenceSpace("viewer");
  const hitSource = await session.requestHitTestSource({ space: viewer });

  // Taps on overlay buttons must not also drop a corner.
  overlay.root.querySelectorAll("button, input").forEach((el) =>
    el.addEventListener("beforexrselect", (e) => e.preventDefault()));

  const hint = (t) => { overlay.hint.textContent = t; };
  const updateUi = () => {
    const n = corners.length;
    overlay.count.textContent = n ? `${n} corner${n > 1 ? "s" : ""}` : "";
    overlay.undo.disabled = n === 0;
    overlay.done.disabled = n < 3;
    hint(n === 0 ? "Point at a corner of the floor and tap."
      : n < 3 ? "Now the next corner, going around the room."
      : "Next corner, or tap the first one again to finish.");
  };

  const redraw = () => {
    const pts = corners.length > 2 ? [...corners, corners[0]] : corners;
    lineGeo.setFromPoints(pts);
  };

  const addCorner = (p) => {
    if (corners.length >= 3 && p.distanceTo(corners[0]) < CLOSE_M) return finishOutline();
    corners.push(p.clone());
    const m = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.25, 12), new THREE.MeshBasicMaterial({ color: accent }));
    m.position.copy(p).add(new THREE.Vector3(0, 0.125, 0));
    scene.add(m);
    markers.push(m);
    navigator.vibrate?.(20);
    redraw();
    updateUi();
  };

  session.addEventListener("select", () => {
    if (!reticle.visible || overlay.stage !== "corners") return;
    addCorner(new THREE.Vector3().setFromMatrixPosition(reticle.matrix));
  });

  overlay.undo.addEventListener("click", () => {
    corners.pop();
    const m = markers.pop();
    if (m) scene.remove(m);
    redraw();
    updateUi();
  });

  let resolveScan, rejectScan;
  const result = new Promise((res, rej) => { resolveScan = res; rejectScan = rej; });

  function finishOutline() {
    overlay.stage = "height";
    reticle.visible = false;
    redraw();
    overlay.corners.hidden = true;
    overlay.height.hidden = false;
    overlay.heightInput.value = defaultHeight.toFixed(1);
    hint("Last step: how high is the ceiling?");
  }
  overlay.done.addEventListener("click", finishOutline);

  overlay.confirm.addEventListener("click", () => {
    const height = Math.max(1.8, parseFloat(overlay.heightInput.value) || defaultHeight);
    const floor = normalise(corners.map((p) => ({ x: p.x, y: -p.z })));
    session.end();
    resolveScan({ name: "scanned", floor, height });
  });

  overlay.cancel.addEventListener("click", () => { session.end(); rejectScan(new Error("cancelled")); });
  session.addEventListener("end", cleanup);

  renderer.setAnimationLoop((t, frame) => {
    if (frame && overlay.stage === "corners") {
      const hits = frame.getHitTestResults(hitSource);
      const pose = hits.length && hits[0].getPose(renderer.xr.getReferenceSpace());
      reticle.visible = !!pose;
      if (pose) reticle.matrix.fromArray(pose.transform.matrix);
    }
    renderer.render(scene, camera);
  });

  updateUi();
  return result;

  function cleanup() {
    renderer.setAnimationLoop(null);
    hitSource?.cancel?.();
    renderer.dispose();
    renderer.domElement.remove();
    overlay.root.remove();
  }
}

// Rotate so the first wall runs along +x, move the floor to start at (0, 0),
// make the winding counter-clockwise, and snap near-rectangles to rectangles.
export function normalise(pts) {
  const a = Math.atan2(pts[1].y - pts[0].y, pts[1].x - pts[0].x);
  const c = Math.cos(-a), s = Math.sin(-a);
  let out = pts.map((p) => ({ x: (p.x - pts[0].x) * c - (p.y - pts[0].y) * s, y: (p.x - pts[0].x) * s + (p.y - pts[0].y) * c }));
  const area = out.reduce((acc, p, i) => { const q = out[(i + 1) % out.length]; return acc + p.x * q.y - q.x * p.y; }, 0);
  if (area < 0) out = out.map((p) => ({ x: p.x, y: -p.y }));

  if (out.length === 4 && out.every((_, i) => Math.abs(cornerAngle(out, i) - 90) < SNAP_DEG)) {
    const len = (i) => Math.hypot(out[(i + 1) % 4].x - out[i].x, out[(i + 1) % 4].y - out[i].y);
    const L = (len(0) + len(2)) / 2, W = (len(1) + len(3)) / 2;
    out = [{ x: 0, y: 0 }, { x: L, y: 0 }, { x: L, y: W }, { x: 0, y: W }];
  }
  const mx = Math.min(...out.map((p) => p.x)), my = Math.min(...out.map((p) => p.y));
  return out.map((p) => ({ x: +(p.x - mx).toFixed(3), y: +(p.y - my).toFixed(3) }));
}

function cornerAngle(pts, i) {
  const n = pts.length, a = pts[(i + n - 1) % n], b = pts[i], c = pts[(i + 1) % n];
  const v1 = [a.x - b.x, a.y - b.y], v2 = [c.x - b.x, c.y - b.y];
  const cos = (v1[0] * v2[0] + v1[1] * v2[1]) / (Math.hypot(...v1) * Math.hypot(...v2));
  return (Math.acos(Math.max(-1, Math.min(1, cos))) * 180) / Math.PI;
}

function buildOverlay() {
  const root = document.createElement("div");
  root.className = "ar-overlay";
  root.innerHTML = `
    <div class="ar-top"><p class="ar-hint" aria-live="polite"></p><span class="ar-count"></span></div>
    <div class="ar-bottom">
      <div class="ar-corners">
        <button class="secondary ar-undo">Undo</button>
        <button class="primary ar-done" disabled>Done</button>
      </div>
      <div class="ar-height" hidden>
        <label>Ceiling height (m) <input type="number" step="0.1" min="1.8" max="8" inputmode="decimal"></label>
        <button class="primary ar-confirm">Use this room</button>
      </div>
      <button class="ar-cancel">Cancel scan</button>
    </div>`;
  const $ = (s) => root.querySelector(s);
  return {
    root, stage: "corners",
    hint: $(".ar-hint"), count: $(".ar-count"),
    corners: $(".ar-corners"), undo: $(".ar-undo"), done: $(".ar-done"),
    height: $(".ar-height"), heightInput: $(".ar-height input"), confirm: $(".ar-confirm"),
    cancel: $(".ar-cancel"),
  };
}
