// Wires the three steps together. Each step lives in its own module.
import { recordClap } from "./capture.js";
import { arSupported, startScan } from "./scan.js";
import { showRoom } from "./room3d.js";

const $ = (id) => document.getElementById(id);
let room = null;

// 1. Room: typed dimensions (MVP) or AR scan (same Room JSON either way)
function boxRoom(length, width, height) {
  return {
    name: "typed",
    height,
    floor: [
      { x: 0, y: 0 }, { x: length, y: 0 },
      { x: length, y: width }, { x: 0, y: width },
    ],
    surfaces: [],
  };
}

async function useRoom(r) {
  const res = await fetch("/api/room", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(r),
  });
  const out = await res.json();
  $("room-out").textContent = JSON.stringify(out, null, 2);
  if (res.ok) {
    room = r;
    showRoom($("view3d"), room);
  }
}

$("form-dims").addEventListener("submit", (e) => {
  e.preventDefault();
  const f = new FormData(e.target);
  useRoom(boxRoom(+f.get("length"), +f.get("width"), +f.get("height")));
});

arSupported().then((ok) => {
  $("btn-scan").disabled = !ok;
  $("scan-support").textContent = ok
    ? "AR available on this device."
    : "AR not available here (needs Chrome on an ARCore Android phone, over HTTPS).";
});
$("btn-scan").addEventListener("click", async () => useRoom(await startScan()));

// 2. Clap
$("btn-record").addEventListener("click", async () => {
  const status = $("rec-status");
  status.textContent = "Recording… clap once, then stay quiet.";
  const { blob, settings } = await recordClap({ seconds: 3 });
  status.textContent = `Recorded ${(blob.size / 1024).toFixed(0)} KB at ${settings.sampleRate} Hz.`;
  // TODO POST blob to /api/clap and show the decay curves
});

// Installable as an app (PWA). Play Store packaging later via a Trusted Web Activity.
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js");
