// Measure a rectangular room with the camera and the phone's tilt sensor.
// Works on any phone with a camera and an accelerometer; no ARCore needed,
// so it is the fallback when the WebXR scan (scan.js) isn't available.
//
// Geometry: with the phone held at height h and the centre of the screen on
// the line where a wall meets the floor, the camera points θ below the
// horizon and that wall is d = h / tan θ away. On the line where the same
// wall meets the ceiling (θ' above) the ceiling is at h + d · tan θ'.
// Facing each wall in turn: length = d_front + d_back, width = d_left + d_right.
//
// Accuracy is a few percent: ±3 cm of phone height is ±2 % of every distance,
// and not facing a wall squarely adds 1/cos of the angle (10° → +1.5 %).

const G_SMOOTH = 0.12;          // low-pass on gravity (per sensor event, ~60 Hz)
const STEADY_DEG = 0.6;         // spread of the last half second to call it steady
const MIN_DEG = 3;              // closer to the horizon than this is unmeasurable

export function motionSupported() {
  return window.isSecureContext && "DeviceMotionEvent" in window && !!navigator.mediaDevices?.getUserMedia;
}

const STEPS = [
  { key: "front", aim: "floor", text: "Face a wall straight on. Put the cross on the line where it meets the floor." },
  { key: "ceiling", aim: "ceiling", text: "Same wall: now the line where it meets the ceiling." },
  { key: "back", aim: "floor", text: "Turn around to the opposite wall. Its floor line." },
  { key: "left", aim: "floor", text: "Turn a quarter to a side wall. Its floor line." },
  { key: "right", aim: "floor", text: "Turn around to the last wall. Its floor line." },
];

// Elevation of the back camera's axis in degrees (+ up, − down), from the
// gravity vector in device coordinates (x right, y up the screen, z out of
// the screen; the back camera looks along −z).
export function elevationDeg({ x, y, z }) {
  const g = Math.hypot(x, y, z) || 1;
  return (Math.asin(Math.max(-1, Math.min(1, -z / g))) * 180) / Math.PI;
}

export function distanceTo(aim, elevDeg, phoneH, ceilingH) {
  const t = Math.tan((Math.abs(elevDeg) * Math.PI) / 180);
  if (Math.abs(elevDeg) < MIN_DEG) return null;
  if (aim === "floor") return elevDeg < 0 ? phoneH / t : null;
  return elevDeg > 0 && ceilingH ? (ceilingH - phoneH) / t : null;
}

export async function startMeasure({ stature = 1.7 } = {}) {
  // iOS (and some Chrome builds) gate the sensor behind a prompt. Ask, but let
  // the sensor itself decide: no readings within 2.5 s means no measurement.
  try { await DeviceMotionEvent.requestPermission?.(); } catch { /* not a user gesture, or no prompt */ }
  const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false });
  const ui = buildOverlay();
  document.body.appendChild(ui.root);
  ui.video.srcObject = stream;
  ui.video.play().catch(() => {});

  const phoneH = () => Math.max(1.0, (parseFloat(ui.stature.value) || stature * 100) / 100 - 0.15);
  ui.stature.value = Math.round(stature * 100);

  let g = null;
  const recent = [];
  let lastEvent = 0;
  const onMotion = (e) => {
    const a = e.accelerationIncludingGravity;
    if (!a || a.x == null) return;
    g = g ? { x: g.x + G_SMOOTH * (a.x - g.x), y: g.y + G_SMOOTH * (a.y - g.y), z: g.z + G_SMOOTH * (a.z - g.z) } : { x: a.x, y: a.y, z: a.z };
    const now = performance.now();
    recent.push([now, elevationDeg(g)]);
    while (recent.length && now - recent[0][0] > 500) recent.shift();
    lastEvent = now;
  };
  addEventListener("devicemotion", onMotion);

  const got = {};           // key → metres (ceiling: height of the ceiling)
  let i = 0;
  let aimOverride = null;   // "ceiling" when the floor line of a wall is hidden

  let resolve, reject;
  const done = new Promise((res, rej) => { resolve = res; reject = rej; });
  const cleanup = () => {
    removeEventListener("devicemotion", onMotion);
    stream.getTracks().forEach((t) => t.stop());
    clearInterval(timer);
    ui.root.remove();
  };

  const aim = () => aimOverride ?? STEPS[i].aim;
  const reading = () => {
    if (!g) return null;
    const elev = elevationDeg(g);
    if (STEPS[i]?.key === "ceiling") {
      const d = got.front;
      return elev > MIN_DEG ? { elev, value: phoneH() + d * Math.tan((elev * Math.PI) / 180), label: "ceiling at" } : { elev, value: null };
    }
    return { elev, value: distanceTo(aim(), elev, phoneH(), got.ceiling), label: "wall at" };
  };
  const steady = () => recent.length > 10 &&
    Math.max(...recent.map((r) => r[1])) - Math.min(...recent.map((r) => r[1])) < STEADY_DEG;

  const render = () => {
    const s = STEPS[i];
    ui.hint.textContent = aimOverride ? s.text.replace("floor line", "ceiling line").replace("meets the floor", "meets the ceiling") : s.text;
    ui.count.textContent = `${i + 1} of ${STEPS.length}`;
    ui.swap.hidden = !(s.aim === "floor" && s.key !== "front" && got.ceiling);
    ui.swap.textContent = aimOverride ? "Use the floor line" : "Floor line hidden? Use the ceiling line";
    ui.undo.disabled = i === 0;
  };

  let timer = 0;
  const tick = () => {
    const r = reading();
    const ok = r?.value != null && steady();
    ui.cross.classList.toggle("steady", ok);
    ui.mark.disabled = !ok;
    ui.value.textContent = r?.value != null ? `${r.label} ${r.value.toFixed(2)} m` : r ? `${r.elev > 0 ? "↑" : "↓"} ${Math.abs(r.elev).toFixed(0)}°` : "Waiting for the tilt sensor…";
    if (!r && performance.now() - started > 2500) {
      cleanup();
      reject(new Error("no motion sensor"));
      return;
    }
  };
  const started = performance.now();

  ui.mark.addEventListener("click", () => {
    const r = reading();
    if (r?.value == null) return;
    got[STEPS[i].key] = r.value;
    navigator.vibrate?.(20);
    aimOverride = null;
    i++;
    if (i < STEPS.length) { render(); return; }
    const room = {
      length: +(got.front + got.back).toFixed(2),
      width: +(got.left + got.right).toFixed(2),
      height: +got.ceiling.toFixed(2),
    };
    ui.panel.hidden = true;
    ui.summary.hidden = false;
    ui.hint.textContent = "Done. Expect these to be within a few percent.";
    ui.count.textContent = "";
    ui.result.textContent = `${room.length.toFixed(1)} × ${room.width.toFixed(1)} m, ${room.height.toFixed(1)} m high`;
    ui.use.onclick = () => { cleanup(); resolve({ ...room, stature: +(phoneH() + 0.15).toFixed(2) }); };
  });
  ui.undo.addEventListener("click", () => { if (i > 0) { i--; delete got[STEPS[i].key]; aimOverride = null; render(); } });
  ui.swap.addEventListener("click", () => { aimOverride = aimOverride ? null : "ceiling"; render(); });
  ui.again.addEventListener("click", () => {
    i = 0; aimOverride = null;
    for (const k of Object.keys(got)) delete got[k];
    ui.panel.hidden = false; ui.summary.hidden = true;
    render();
  });
  ui.cancel.addEventListener("click", () => { cleanup(); reject(new Error("cancelled")); });

  render();
  timer = setInterval(tick, 50);   // 20 Hz is plenty for a reading
  return done;
}

function buildOverlay() {
  const root = document.createElement("div");
  root.className = "measure";
  root.innerHTML = `
    <video playsinline muted></video>
    <div class="measure-cross" aria-hidden="true"></div>
    <div class="ar-top"><p class="ar-hint" aria-live="polite"></p><span class="ar-count"></span></div>
    <div class="ar-bottom">
      <div class="measure-panel">
        <p class="measure-value" aria-live="polite"></p>
        <button class="measure-swap link" hidden></button>
        <div class="ar-corners">
          <button class="secondary measure-undo">Back</button>
          <button class="primary measure-mark" disabled>Mark</button>
        </div>
        <label class="measure-stature">Your height (cm) <input type="number" min="120" max="220" step="1" inputmode="numeric"></label>
      </div>
      <div class="measure-summary" hidden>
        <p class="measure-result"></p>
        <div class="ar-corners">
          <button class="secondary measure-again">Measure again</button>
          <button class="primary measure-use">Use these</button>
        </div>
      </div>
      <button class="ar-cancel">Cancel</button>
    </div>`;
  const $ = (s) => root.querySelector(s);
  return {
    root, video: $("video"), cross: $(".measure-cross"), hint: $(".ar-hint"), count: $(".ar-count"),
    panel: $(".measure-panel"), value: $(".measure-value"), swap: $(".measure-swap"),
    undo: $(".measure-undo"), mark: $(".measure-mark"), stature: $(".measure-stature input"),
    summary: $(".measure-summary"), result: $(".measure-result"), again: $(".measure-again"), use: $(".measure-use"),
    cancel: $(".ar-cancel"),
  };
}
