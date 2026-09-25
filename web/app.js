// Step-by-step flow: welcome → goal → size → surfaces → clap → results.
// One task per screen; every step builds the same Room JSON (clapback/room.py).
import { openMic, recordClap, quickQuality } from "./capture.js";
import { arSupported, startScan } from "./scan.js";
import { motionSupported, startMeasure } from "./measure.js";
import { showRoom, showGrid, showSource, modalGrid, RAMPS } from "./room3d.js";
import { SWEEP, playSweep } from "./sweep.js";
import {
  rtChart, decayChart, bandLegend, drawSpectrogram, modesChart, modeLegend, responseChart, isoTable,
} from "./charts.js";

const $ = (id) => document.getElementById(id);
const SCREENS = ["welcome", "goal", "room", "surfaces", "clap", "results"];

const state = {
  step: 0,
  goal: null,
  dims: { length: 5.0, width: 4.0, height: 2.6 },
  scanned: null,           // Room from the AR scan, if used
  answers: { floor: null, walls: null, ceiling: null, furnishing: null, windows: null },
  notes: "",
  clap: null,              // last clap: { quality, settings, upload }
  claps: [],               // every good measurement this session (clap or sweep)
  mode: "clap",            // "clap" or "sweep"
  src: "bt",               // sweep played by a speaker on this phone, or by "other" device
  budget: 150,
};

// ---------- navigation ----------

function renderSteps() {
  $("steps").innerHTML = SCREENS.slice(1).map((_, i) => {
    const k = i + 1;
    const cls = k < state.step ? "done" : k === state.step ? "current" : "";
    return `<li class="${cls}"></li>`;
  }).join("");
}

function go(step) {
  state.step = Math.max(0, Math.min(SCREENS.length - 1, step));
  document.querySelectorAll(".screen").forEach((s) => {
    s.hidden = s.dataset.screen !== SCREENS[state.step];
  });
  $("btn-back").hidden = state.step === 0;
  renderSteps();
  window.scrollTo({ top: 0 });
  onEnter[SCREENS[state.step]]?.();
}

document.querySelectorAll("[data-next]").forEach((b) => b.addEventListener("click", () => go(state.step + 1)));
$("btn-back").addEventListener("click", () => go(state.step - 1));

// ---------- goal ----------

const ICONS = {
  mic: '<path d="M12 3a3 3 0 0 1 3 3v6a3 3 0 0 1-6 0V6a3 3 0 0 1 3-3zM5 11a7 7 0 0 0 14 0M12 18v3"/>',
  note: '<path d="M9 18V5l11-2v13M9 18a3 3 0 1 1-3-3 3 3 0 0 1 3 3zm11-2a3 3 0 1 1-3-3 3 3 0 0 1 3 3z"/>',
  sliders: '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
  book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5v14zM4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5"/>',
  film: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4"/>',
  sparkle: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/>',
};
const GOALS = [
  { id: "voice", icon: "mic", title: "Podcast or calls", hint: "Clear, dry voice" },
  { id: "music", icon: "note", title: "Playing music", hint: "Some life, no mush" },
  { id: "studio", icon: "sliders", title: "Mixing / studio", hint: "Honest, even bass" },
  { id: "study", icon: "book", title: "Studying or teaching", hint: "Easy to understand speech" },
  { id: "cinema", icon: "film", title: "Movies and TV", hint: "Clear dialogue, tight bass" },
  { id: "curious", icon: "sparkle", title: "Just curious", hint: "Tell me how it sounds" },
];

$("goal-choices").innerHTML = GOALS.map((g) => `
  <button class="choice" role="radio" aria-checked="false" data-goal="${g.id}">
    <svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${ICONS[g.icon]}</svg>
    <strong>${g.title}</strong><span>${g.hint}</span>
  </button>`).join("");
$("goal-choices").addEventListener("click", (e) => {
  const b = e.target.closest("[data-goal]");
  if (!b) return;
  state.goal = b.dataset.goal;
  document.querySelectorAll("[data-goal]").forEach((x) => x.setAttribute("aria-checked", x === b));
  $("goal-next").disabled = false;
});

// ---------- room size ----------

const PRESETS = [
  { label: "Small bedroom", d: [3.0, 3.0, 2.5] },
  { label: "Bedroom", d: [4.0, 3.5, 2.6] },
  { label: "Living room", d: [5.5, 4.5, 2.6] },
  { label: "Home office", d: [3.5, 2.8, 2.5] },
  { label: "Classroom", d: [8.0, 7.0, 3.0] },
];
$("presets").innerHTML = PRESETS.map((p, i) =>
  `<button class="chip" aria-pressed="false" data-preset="${i}">${p.label}</button>`).join("");
$("presets").addEventListener("click", (e) => {
  const b = e.target.closest("[data-preset]");
  if (!b) return;
  const [length, width, height] = PRESETS[+b.dataset.preset].d;
  state.dims = { length, width, height };
  state.scanned = null;
  document.querySelectorAll("[data-preset]").forEach((x) => x.setAttribute("aria-pressed", x === b));
  renderDims();
});

document.querySelectorAll(".stepper").forEach((s) => {
  s.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-d]");
    if (!b) return;
    const k = s.dataset.dim;
    const step = k === "height" ? 0.1 : 0.25;
    const min = k === "height" ? 1.8 : 1.5;
    state.dims[k] = Math.max(min, Math.round((state.dims[k] + step * +b.dataset.d) * 100) / 100);
    state.scanned = null;
    document.querySelectorAll("[data-preset]").forEach((x) => x.setAttribute("aria-pressed", false));
    renderDims();
  });
});

function renderDims() {
  document.querySelectorAll(".stepper").forEach((s) => {
    s.querySelector("output").textContent = state.dims[s.dataset.dim].toFixed(1);
  });
  showRoom($("view3d-room"), currentRoom());
}

arSupported().then((ok) => { $("btn-scan").hidden = !ok; });
$("btn-measure").hidden = !motionSupported();

const stored = (k, fallback) => { try { return localStorage.getItem(k) ?? fallback; } catch { return fallback; } };
const store = (k, v) => { try { localStorage.setItem(k, v); } catch { /* private mode */ } };

$("btn-measure").addEventListener("click", async () => {
  try {
    const r = await startMeasure({ stature: +stored("clapback.stature", 1.7) });
    store("clapback.stature", r.stature);
    state.scanned = null;
    state.dims = { length: r.length, width: r.width, height: r.height };
    document.querySelectorAll("[data-preset]").forEach((x) => x.setAttribute("aria-pressed", false));
    $("btn-measure").querySelector("strong").textContent = "Measured ✓  Measure again";
    renderDims();
  } catch (err) {
    if (err?.message === "cancelled") return;
    alert(err?.message === "no motion sensor"
      ? "This phone doesn't report its tilt, so the camera can't measure. Type the sizes below instead."
      : "The camera didn't start. Allow it in the browser's site settings, or type the sizes below.");
  }
});
$("btn-scan").addEventListener("click", async () => {
  try {
    const room = await startScan({ defaultHeight: state.dims.height });
    state.scanned = room;
    const xs = room.floor.map((p) => p.x), ys = room.floor.map((p) => p.y);
    state.dims = {
      length: Math.max(...xs) - Math.min(...xs),
      width: Math.max(...ys) - Math.min(...ys),
      height: room.height,
    };
    document.querySelectorAll(".stepper").forEach((s) => {
      s.querySelector("output").textContent = state.dims[s.dataset.dim].toFixed(1);
    });
    $("btn-scan").querySelector("strong").textContent = "Scanned ✓  Scan again";
    showRoom($("view3d-room"), currentRoom());
  } catch (err) {
    if (err?.message !== "cancelled") alert("The scan didn't start. You can type the sizes below instead.");
  }
});

// ---------- surfaces ----------
// Common answers map straight to database materials; free text goes to the
// intake agent (Nemotron) later.

const QUESTIONS = [
  { key: "floor", title: "The floor", options: [
    { label: "Wood / laminate", mat: "wood_floor_on_joists" },
    { label: "Wood with a rug", mat: "wood_floor_on_joists", patch: "carpet_on_concrete" },
    { label: "Tile or stone", mat: "vinyl_on_concrete" },
    { label: "Carpet", mat: "carpet_on_pad" },
  ]},
  { key: "walls", title: "The walls", options: [
    { label: "Plaster / paint", mat: "plaster_on_masonry" },
    { label: "Plasterboard", mat: "gypsum_board_on_studs" },
    { label: "Bare brick", mat: "brick_unglazed" },
    { label: "Wood panels", mat: "wood_panel_on_battens" },
  ]},
  { key: "ceiling", title: "The ceiling", options: [
    { label: "Plaster / paint", mat: "plaster_on_masonry" },
    { label: "Plasterboard", mat: "gypsum_board_on_studs" },
    { label: "Acoustic tiles", mat: "acoustic_ceiling_tile" },
  ]},
  { key: "furnishing", title: "How furnished is it?", options: [
    { label: "Almost empty", furn: "empty" },
    { label: "Some furniture", furn: "some" },
    { label: "Full: bed or sofa, shelves, curtains", furn: "full" },
  ]},
  { key: "windows", title: "Windows", options: [
    { label: "None", area: 0 },
    { label: "One small", area: 1.5 },
    { label: "One big", area: 3.5 },
    { label: "A whole glass wall", area: -1 },
  ]},
];

$("surface-questions").innerHTML = QUESTIONS.map((q) => `
  <div class="q" role="group" aria-label="${q.title}">
    <span class="q-title">${q.title}</span>
    <div class="row">${q.options.map((o, i) =>
      `<button class="chip" aria-pressed="false" data-q="${q.key}" data-i="${i}">${o.label}</button>`).join("")}
    </div>
  </div>`).join("");
$("surface-questions").addEventListener("click", (e) => {
  const b = e.target.closest("[data-q]");
  if (!b) return;
  state.answers[b.dataset.q] = +b.dataset.i;
  document.querySelectorAll(`[data-q="${b.dataset.q}"]`).forEach((x) => x.setAttribute("aria-pressed", x === b));
});
$("surface-notes").addEventListener("input", (e) => { state.notes = e.target.value; });

// ---------- room model ----------

function currentRoom() {
  const base = state.scanned ?? {
    name: "typed",
    height: state.dims.height,
    floor: [
      { x: 0, y: 0 }, { x: state.dims.length, y: 0 },
      { x: state.dims.length, y: state.dims.width }, { x: 0, y: state.dims.width },
    ],
  };
  return { ...base, surfaces: buildSurfaces(base), furnishing: pick("furnishing", { furn: "some" }).furn };
}

function pick(key, fallback) {
  const q = QUESTIONS.find((q) => q.key === key);
  const i = state.answers[key];
  return i == null ? fallback : q.options[i];
}

function buildSurfaces(room) {
  const n = room.floor.length;
  const floorArea = Math.abs(room.floor.reduce((a, p, i) => {
    const q = room.floor[(i + 1) % room.floor.length];
    return a + p.x * q.y - q.x * p.y;
  }, 0)) / 2;
  const floor = pick("floor", QUESTIONS[0].options[0]);
  const walls = pick("walls", QUESTIONS[1].options[0]);
  const ceiling = pick("ceiling", QUESTIONS[2].options[0]);
  const windows = pick("windows", { area: 0 });

  const out = [
    { kind: "floor", material: floor.mat,
      patches: floor.patch ? [{ material: floor.patch, area_m2: +(floorArea * 0.3).toFixed(2) }] : [] },
    { kind: "ceiling", material: ceiling.mat, patches: [] },
  ];
  for (let i = 0; i < n; i++) out.push({ kind: "wall", wall_index: i, material: walls.mat, patches: [] });

  // Windows go on the first wall; a glass wall replaces it entirely.
  if (windows.area === -1) out[2].material = "glass_window";
  else if (windows.area > 0) out[2].patches.push({ material: "glass_window", area_m2: windows.area });
  return out;
}

// ---------- measure: clap or test sweep ----------

let mic = null;
let busy = false;

const SRC_HELP = {
  bt: [
    "Connect a Bluetooth speaker to this phone and put it at least 2 m away, at ear height.",
    "Set the phone's volume to about three quarters.",
    "Stand in the listening spot, tap, and stay quiet until it finishes (about 11 s).",
  ],
  other: [
    `On a laptop or a second phone, open <b>${location.host}/speaker.html</b>.`,
    "Put it at least 2 m from you, volume at about three quarters.",
    "Tap here first, then press Play on the other device within 4 seconds. Stay quiet until this phone finishes.",
  ],
};

function idleLabel() { return state.mode === "clap" ? "Tap, then clap" : "Tap to measure"; }

function setMode(mode) {
  state.mode = mode;
  document.querySelectorAll("[data-mode]").forEach((b) => b.setAttribute("aria-checked", b.dataset.mode === mode));
  $("howto-clap").hidden = mode !== "clap";
  $("howto-sweep").hidden = mode !== "sweep";
  $("src-help").innerHTML = SRC_HELP[state.src].map((t) => `<li>${t}</li>`).join("");
  if (!busy) {
    $("btn-record").className = "clap-btn";
    $("clap-label").textContent = idleLabel();
  }
}
document.querySelectorAll("[data-mode]").forEach((b) => b.addEventListener("click", () => setMode(b.dataset.mode)));
$("sweep-src").addEventListener("click", (e) => {
  const b = e.target.closest("[data-src]");
  if (!b) return;
  state.src = b.dataset.src;
  document.querySelectorAll("[data-src]").forEach((x) => x.setAttribute("aria-pressed", x === b));
  setMode("sweep");
});

async function ensureMic(coach) {
  try {
    mic ??= await openMic();
    $("mic-explainer").hidden = true;
    return true;
  } catch {
    coach.className = "coach bad";
    coach.textContent = "Microphone blocked. Allow it in the browser's site settings, then try again.";
    return false;
  }
}

function measure() { return state.mode === "clap" ? doClap() : doSweep(); }

async function doClap() {
  if (busy) return;
  busy = true;
  const btn = $("btn-record"), label = $("clap-label"), coach = $("clap-coach");
  coach.className = "coach"; coach.textContent = "";
  $("btn-retry").hidden = true;

  if (!(await ensureMic(coach))) { busy = false; return; }

  // Recording starts during the countdown, so the first second captures the
  // room's background noise before the clap.
  const recording = recordClap(mic, {
    seconds: 5,
    onLevel: (v) => { $("meter-fill").style.width = `${Math.round(v * 100)}%`; },
  });
  btn.className = "clap-btn countdown";
  for (const n of ["3", "2", "1"]) { label.textContent = n; await sleep(500); }
  btn.className = "clap-btn listening";
  label.textContent = "Clap now!";
  coach.textContent = "Then stay still and quiet…";

  const { pcm, blob, settings } = await recording;
  $("meter-fill").style.width = "0%";

  const q = quickQuality(pcm, settings.sampleRate);
  const processed = settings.echoCancellation || settings.noiseSuppression || settings.autoGainControl;
  btn.className = "clap-btn done";
  label.textContent = q.level === "bad" ? "Try again" : "Got it";
  coach.className = `coach ${q.level}`;
  coach.textContent = q.message + (processed
    ? " (This phone is filtering the mic, so results may be less accurate.)" : "");
  $("btn-retry").hidden = false;
  $("clap-next").disabled = q.level === "bad";

  state.clap = { kind: "clap", quality: q, settings, upload: upload("/api/clap", blob, settings).then((r) => r.json) };
  if (q.level !== "bad") state.claps.push(state.clap);
  busy = false;
}

// The recording starts first; the sweep plays 0.5 s later (from this phone)
// or whenever the user presses Play on the other device. The server finds
// it by deconvolution, so the timing doesn't need to be exact.
async function doSweep() {
  if (busy) return;
  busy = true;
  const btn = $("btn-record"), label = $("clap-label"), coach = $("clap-coach");
  coach.className = "coach"; coach.textContent = "";
  $("btn-retry").hidden = true;
  if (!(await ensureMic(coach))) { busy = false; return; }

  const seconds = SWEEP.seconds + (state.src === "bt" ? 4.5 : 9);
  const recording = recordClap(mic, {
    seconds, bits: 16,
    onLevel: (v) => { $("meter-fill").style.width = `${Math.round(v * 100)}%`; },
  });
  btn.className = "clap-btn listening";
  coach.textContent = state.src === "bt"
    ? "Playing the sweep. Stay quiet until it finishes."
    : "Press Play on the other device now. Stay quiet until this finishes.";
  const t0 = performance.now();
  const tick = setInterval(() => {
    label.textContent = `Listening… ${Math.max(0, Math.ceil(seconds - (performance.now() - t0) / 1000))} s`;
  }, 200);
  if (state.src === "bt") { await sleep(500); playSweep().catch(() => {}); }

  const { blob, settings } = await recording;
  clearInterval(tick);
  $("meter-fill").style.width = "0%";
  btn.className = "clap-btn countdown";
  label.textContent = "Analysing…";

  const up = await upload("/api/sweep", blob, settings, SWEEP);
  btn.className = "clap-btn done";
  $("btn-retry").hidden = false;
  if (!up.json) {
    label.textContent = "Try again";
    coach.className = "coach bad";
    coach.textContent = up.error ?? "Couldn't reach the server. Check the connection.";
    busy = false;
    return;
  }
  const mid = up.json.decay.filter((b) => b.band_hz === 500 || b.band_hz === 1000);
  const range = Math.min(...mid.map((b) => b.dynamic_range_db));
  const lowRate = settings.sampleRate < 32000;
  const level = up.json.detail.warning || lowRate || range < 35 ? "warn" : "good";
  label.textContent = "Got it";
  coach.className = `coach ${level}`;
  coach.textContent = up.json.detail.warning
    ?? (lowRate ? "The phone switched the speaker to call mode, so the recording is low quality. Try another device as the speaker."
      : range < 35 ? `Usable, with ${Math.round(range)} dB of range. A louder speaker or a quieter room will be more accurate.`
        : `Clean measurement: ${Math.round(range)} dB of decay range in the mid bands.`);
  state.clap = { kind: "sweep", quality: { level }, settings, upload: Promise.resolve(up.json) };
  state.claps.push(state.clap);
  $("clap-next").disabled = false;
  busy = false;
}

async function upload(url, blob, settings, extra = {}) {
  const form = new FormData();
  form.append("mic", JSON.stringify(settings));
  form.append("audio", blob, "recording.wav");
  form.append("room", JSON.stringify(currentRoom()));
  form.append("goal", state.goal ?? "");
  form.append("notes", state.notes);
  for (const [k, v] of Object.entries(extra)) form.append(k, v);
  try {
    const res = await fetch(url, { method: "POST", body: form });
    if (res.ok) return { json: await res.json() };
    const body = await res.json().catch(() => ({}));
    return { json: null, error: typeof body.detail === "string" ? body.detail : null };
  } catch {
    return { json: null, error: null };
  }
}

$("btn-record").addEventListener("click", measure);
$("btn-retry").addEventListener("click", measure);

// ---------- results ----------

const NOTE_NAMES = ["C", "C♯", "D", "D♯", "E", "F", "F♯", "G", "G♯", "A", "A♯", "B"];

function noteName(f) {
  const n = Math.round(12 * Math.log2(f / 440) + 69);
  return `${NOTE_NAMES[n % 12]}${Math.floor(n / 12) - 1}`;
}

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
const avg = (v) => (v.length ? v.reduce((a, b) => a + b, 0) / v.length : null);

async function renderResults() {
  const room = currentRoom();
  showRoom($("view3d"), room);
  const goal = GOALS.find((g) => g.id === state.goal);
  const v = $("verdict");
  const cards = ["rt-card", "decay-card", "spec-card", "response-card", "modes-card", "next-card",
    "understood-card", "iso-card", "fix-card"];
  for (const id of cards) $(id).hidden = true;
  $("stats").innerHTML = "";
  $("plan").innerHTML = "";

  if (!state.claps.length) {
    v.className = "verdict";
    v.innerHTML = `<span class="badge warn">No measurement yet</span><p>Go back one step and measure.</p>`;
    return;
  }

  v.className = "verdict";
  v.innerHTML = `<div class="spinner" aria-hidden="true"></div><p>Analysing the measurements…</p>`;

  const uploads = (await Promise.all(state.claps.map((c) => c.upload))).filter(Boolean);
  const res = uploads.length ? await api("/api/analyze", {
    room, goal: state.goal ?? "", notes: state.notes, claps: uploads.map((u) => u.decay),
    kinds: uploads.map((u) => u.kind),
  }) : null;
  if (!res) {
    v.innerHTML = `<span class="badge bad">Couldn't reach the server</span>
      <p>Check the connection and measure again.</p>`;
    return;
  }
  state.analysis = res;

  // Charts of the decay come from one measurement: the latest sweep if
  // there is one (cleaner), otherwise the latest clap.
  const shown = [...uploads].reverse().find((u) => u.kind === "sweep") ?? uploads.at(-1);
  const nClaps = uploads.filter((u) => u.kind !== "sweep").length;
  const nSweeps = uploads.length - nClaps;
  const counts = [nSweeps && plural(nSweeps, "sweep"), nClaps && plural(nClaps, "clap")].filter(Boolean).join(" + ");

  const vd = res.verdict;
  const q = state.clap?.quality ?? { level: "good" };
  v.className = `verdict ${vd.level}`;
  v.innerHTML = `
    <span class="badge ${q.level}">${goal ? goal.title : "Your room"} · ${counts}</span>
    <h3>${vd.headline}</h3>
    ${res.rt_mid_s ? `
    <div class="figure">
      <div><b>${res.rt_mid_s.toFixed(2)} s</b><span>RT60, 500 Hz–1 kHz</span></div>
      <div class="target"><b>${vd.range_s[0].toFixed(2)}–${vd.range_s[1].toFixed(2)} s</b><span>Target · ${vd.source}</span></div>
    </div>
    ${gauge(res.rt_mid_s, vd.range_s)}` : ""}
    <p>${vd.detail}</p>
    <p class="definition">RT60 (reverberation time): how long a sound takes to fade by 60 dB once it stops.</p>`;

  if (res.next?.action === "clap") {
    $("next-text").textContent = res.next.instruction;
    $("next-card").hidden = false;
  }

  const mid = (k) => avg(res.bands.filter((b) => b.band_hz === 500 || b.band_hz === 1000).map((b) => b[k]).filter((x) => x != null));
  const c50 = mid("c50_db"), d50 = mid("d50");
  const stats = [
    ["C50 · speech clarity", c50 != null ? `${c50 > 0 ? "+" : ""}${c50.toFixed(1)} dB` : "–"],
    ["D50 · definition", d50 != null ? `${Math.round(d50 * 100)} %` : "–"],
    ["Volume", `${res.volume_m3?.toFixed(0) ?? "–"} m³`],
    ["Schroeder frequency", res.schroeder_hz ? `${res.schroeder_hz} Hz` : "–"],
  ];
  if (res.mid_spread_pct != null) stats.push(["Measurements agree", `±${(res.mid_spread_pct / 2).toFixed(0)} %`]);
  $("stats").innerHTML = stats.map(([k, val]) => `<div><dt>${k}</dt><dd>${val}</dd></div>`).join("");

  if (res.bands?.some((b) => b.rt_s)) {
    $("rt-chart").innerHTML = rtChart(res.bands, vd.range_s, null, nSweeps > 0);
    const faded = !nSweeps && res.bands.some((b) => b.rt_s && b.band_hz < 250 && b.n < 2);
    $("rt-help").textContent = "RT60 in each octave band. The green band is the target range for your use." +
      (faded ? " Faded bars: one measurement is less certain this low; measure again or use the sweep." : "");
    $("rt-card").hidden = false;
  }

  const d = shown?.detail;
  const from = shown?.kind === "sweep" ? "the sweep" : "your last clap";
  if (d?.edc) {
    $("decay-chart").innerHTML = decayChart(d.edc, d.etc);
    $("decay-legend").innerHTML = bandLegend(Object.keys(d.edc.db).map(Number));
    $("decay-card").hidden = false;
  }
  if (d?.spectrogram?.level?.length) {
    $("spec-card").hidden = false;
    state.spectrogram = d.spectrogram;
    drawSpectrogram($("spec"), d.spectrogram);   // the card is visible now, so it has a width
  }
  if (d?.response) {
    $("response-chart").innerHTML = responseChart(d.response, res.schroeder_hz);
    $("response-card").hidden = false;
  }
  if (res.modes?.length) {
    $("modes-chart").innerHTML = modesChart(res.modes, res.schroeder_hz, d?.response);
    $("modes-legend").innerHTML = modeLegend(!!d?.response);
    $("bass-notes").innerHTML = (res.bass_notes ?? []).slice(0, 6).map((b) => `
      <span class="note-chip"><b>${Math.round(b.freq_hz)} Hz</b>
      <small>≈ ${noteName(b.freq_hz)}${b.count > 1 ? ", stacked" : ""}</small></span>`).join("");
    $("modes-card").hidden = false;
  }
  for (const id of ["decay-card", "spec-card"]) {
    $(id).querySelector("h3").dataset.from = `From ${from}`;
  }

  $("iso-table").innerHTML = isoTable(res.bands);
  const dl = $("ir-download");
  dl.hidden = !d?.ir_wav;
  if (d?.ir_wav) dl.href = `data:audio/wav;base64,${d.ir_wav}`;
  $("iso-card").hidden = false;

  const u = res.understood;
  if (u && (u.extras.length || u.unknown.length)) {
    $("understood").innerHTML =
      u.extras.map((e) => `<span class="chip static">${esc(e.what)} · ${e.area_m2} m²</span>`).join("") +
      u.unknown.map((w) => `<span class="chip static unknown" title="Not counted">${esc(w)}?</span>`).join("");
    $("understood-card").hidden = false;
  }

  if (res.rt_mid_s) $("fix-card").hidden = false;

  if (res.maps) {
    showSource($("view3d"), res.maps.source);
    if (res.bass_notes?.length) setFreq(Math.round(res.bass_notes[0].freq_hz));
    setLayer(state.layer ?? "sti");
  }
}

// Canvas pixels don't scale with CSS; redraw after a rotation or resize.
let redraw = 0;
addEventListener("resize", () => {
  clearTimeout(redraw);
  redraw = setTimeout(() => { if (state.spectrogram && !$("spec-card").hidden) drawSpectrogram($("spec"), state.spectrogram); }, 150);
});

// ---------- map layers ----------

function legend(name) {
  const stops = RAMPS[name];
  const css = stops.map(([v, c]) => {
    const pct = ((v - stops[0][0]) / (stops.at(-1)[0] - stops[0][0])) * 100;
    return `rgb(${c.map((x) => Math.round(x * 255)).join(",")}) ${pct}%`;
  }).join(",");
  const labels = name === "sti"
    ? ["Hard to follow", "Fair", "Clear"]
    : ["Bass hole", "Even", "Boom"];
  return `<div class="bar" style="background:linear-gradient(90deg,${css})"></div>
    <div class="labels">${labels.map((l) => `<span>${l}</span>`).join("")}</div>`;
}

function setLayer(name) {
  state.layer = name;
  const res = state.analysis;
  if (!res?.maps) return;
  document.querySelectorAll("[data-layer]").forEach((b) => b.setAttribute("aria-pressed", b.dataset.layer === name));
  $("legend").innerHTML = legend(name);
  $("bass-ctrl").hidden = name !== "modal";
  if (name === "sti") {
    showGrid($("view3d"), res.maps.sti, "sti", res.maps.listener_z);
    const s = res.maps.sti_summary;
    $("map-help").textContent = `How easy speech is to follow at ear height, for someone talking from the orange dot. ` +
      `From ${s.min.toFixed(2)} to ${s.max.toFixed(2)} on the 0–1 speech-transmission scale (an estimate for a quiet room).`;
  } else {
    drawModal();
  }
}

function drawModal() {
  const res = state.analysis, f = +$("freq").value;
  const g = modalGrid(currentRoom(), f, res.maps.source, res.maps.rt_low_s || 0.5);
  showGrid($("view3d"), g, "modal", res.maps.listener_z);
  $("freq-out").textContent = `${f} Hz ≈ ${noteName(f)}`;
  $("map-help").textContent = "How loud one bass note is around the room. Red spots boom, blue spots lose the note. Slide or press play to sweep.";
}

function setFreq(f) { $("freq").value = f; }

document.querySelectorAll("[data-layer]").forEach((b) => b.addEventListener("click", () => setLayer(b.dataset.layer)));
$("freq").addEventListener("input", drawModal);

let sweeping = null;
$("btn-sweep").addEventListener("click", () => {
  if (sweeping) { cancelAnimationFrame(sweeping); sweeping = null; return; }
  let f = 25, last = 0;
  const step = (t) => {
    if (t - last > 70) {           // ~14 frames per second is plenty
      last = t;
      setFreq(f); drawModal();
      f += 1;
      if (f > 160) { sweeping = null; return; }
    }
    sweeping = requestAnimationFrame(step);
  };
  sweeping = requestAnimationFrame(step);
});

// ---------- plan ----------

const BUDGETS = [50, 150, 300, 500];
$("budgets").innerHTML = BUDGETS.map((b) =>
  `<button class="chip" role="radio" aria-checked="${b === state.budget}" aria-pressed="${b === state.budget}" data-budget="${b}">€${b}</button>`).join("");
$("budgets").addEventListener("click", (e) => {
  const b = e.target.closest("[data-budget]");
  if (!b) return;
  state.budget = +b.dataset.budget;
  document.querySelectorAll("[data-budget]").forEach((x) => {
    x.setAttribute("aria-pressed", x === b); x.setAttribute("aria-checked", x === b);
  });
});

$("btn-plan").addEventListener("click", async () => {
  const out = $("plan"), btn = $("btn-plan");
  btn.disabled = true;
  out.innerHTML = `<div class="spinner" aria-hidden="true"></div><p class="sub small">Nemotron is trying options; the engine checks each one…</p>`;
  const uploads = (await Promise.all(state.claps.map((c) => c.upload))).filter(Boolean);
  const p = await api("/api/plan", {
    room: currentRoom(), goal: state.goal ?? "", notes: state.notes,
    claps: uploads.map((u) => u.decay), budget_eur: state.budget,
  });
  btn.disabled = false;
  if (!p) { out.innerHTML = `<p class="coach bad">Couldn't make a plan. Try again.</p>`; return; }
  out.innerHTML = renderPlan(p);
});

const WHERE = { wall: "on the walls", floor: "on the floor", ceiling: "on the ceiling", window: "over the window" };

function renderPlan(p) {
  const items = p.treatments.length
    ? `<ul class="plan-items">${p.treatments.map((t) => `
        <li><div>${esc(t.name)}<span>${t.area_m2} m² ${WHERE[t.where] ?? t.where}</span>${
          t.products?.length ? `<span class="shop">${t.products.slice(0, 2).map((x) =>
            `<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.site)}</a>`).join(" · ")}</span>` : ""
        }</div><b>€${t.cost_eur}</b></li>`).join("")}
      </ul><div class="plan-total"><span>Total</span><span>€${p.cost_eur}</span></div>`
    : "";
  const tries = p.trace.filter((s) => s.tool);
  const trace = tries.length ? `
    <details class="trace"><summary>How it decided (${tries.length} tries)</summary><ol>
      ${tries.map((s) => `<li>${s.tool === "finish" ? "Final: " : "Tried "}${
        s.treatments.map((t) => `${t.area_m2} m² ${t.id.replace("_", " ")} (${t.where})`).join(" + ") || "nothing"} → ${
        s.result.valid ? `${s.result.predicted_mid_s} s, €${s.result.cost_eur}` : `rejected: ${esc(s.result.errors[0])}`}</li>`).join("")}
    </ol></details>` : "";
  return `
    <div class="before-after"><span>${p.before_mid_s.toFixed(2)} s</span><span class="arrow">→</span>
      <span class="after">${p.after_mid_s.toFixed(2)} s</span></div>
    <div class="chart">${rtChart(state.analysis.bands, state.analysis.verdict.range_s, p.predicted_rt_s, true)}</div>
    <div class="chart-legend"><span><i style="background:var(--accent)"></i>Measured</span><span><i class="after-key"></i>Predicted after the plan</span></div>
    ${items}
    <p class="plan-summary">${esc(p.summary)}</p>
    ${trace}
    ${p.source === "fallback" ? `<p class="sub small">Nemotron wasn't available, so this plan comes from a simple rule.</p>` : ""}`;
}

async function api(url, body) {
  try {
    const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (res.status === 429) { alert((await res.json()).detail); return null; }
    return res.ok ? res.json() : null;
  } catch { return null; }
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

$("btn-next-clap").addEventListener("click", () => {
  $("btn-record").className = "clap-btn";
  $("clap-label").textContent = idleLabel();
  $("clap-coach").className = "coach";
  $("clap-coach").textContent = $("next-text").textContent;
  $("btn-retry").hidden = true;
  $("clap-next").disabled = true;
  go(SCREENS.indexOf("clap"));
});

// Horizontal scale from 0; the green zone is the target range.
function gauge(rt, [lo, hi]) {
  const max = Math.max(1.5, hi * 2, rt * 1.1);
  const pct = (x) => `${Math.min(100, (x / max) * 100).toFixed(1)}%`;
  return `
    <div class="gauge" role="img" aria-label="RT60 ${rt.toFixed(2)} seconds, target ${lo.toFixed(2)} to ${hi.toFixed(2)}">
      <div class="zone" style="left:${pct(lo)};width:calc(${pct(hi)} - ${pct(lo)})"></div>
      <div class="dot" style="left:${pct(rt)}"></div>
    </div>
    <div class="gauge-labels"><span>Dry</span><span>Reverberant</span></div>`;
}

$("btn-restart").addEventListener("click", () => {
  Object.assign(state, { goal: null, scanned: null, clap: null, claps: [], notes: "",
    answers: { floor: null, walls: null, ceiling: null, furnishing: null, windows: null } });
  document.querySelectorAll('[aria-pressed="true"]').forEach((x) => x.setAttribute("aria-pressed", false));
  document.querySelectorAll('[aria-checked="true"]').forEach((x) => x.setAttribute("aria-checked", false));
  $("goal-next").disabled = true;
  $("clap-next").disabled = true;
  go(0);
});

// ---------- boot ----------

const onEnter = {
  room: renderDims,
  results: renderResults,
};

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
go(0);

// Installable as an app (PWA). Play Store packaging later via a Trusted Web Activity.
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js");
