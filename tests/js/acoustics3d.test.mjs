// node --test tests/js  (run from pytest by tests/test_js.py)
import assert from "node:assert/strict";
import test from "node:test";

import {
  areaOf, calibratedScale, heatAt, makeParticles, modalCloud, planes, volume,
} from "../../web/acoustics3d.js";

const box = (l, w, h) => ({
  floor: [{ x: 0, y: 0 }, { x: l, y: 0 }, { x: l, y: w }, { x: 0, y: w }], height: h, surfaces: [],
});

test("walls are named in floor order and every normal points into the room", () => {
  const room = box(6, 4, 3);
  const pls = planes(room);
  assert.deepEqual(pls.map((p) => p.name), ["floor", "ceiling", "wall A", "wall B", "wall C", "wall D"]);
  const centre = [3, 2, 1.5];
  for (const p of pls) {
    const d = (centre[0] - p.point[0]) * p.normal[0] + (centre[1] - p.point[1]) * p.normal[1] + (centre[2] - p.point[2]) * p.normal[2];
    assert.ok(d > 0, p.name);
  }
});

test("particle energy decays at the Eyring rate", () => {
  const room = box(6, 4, 3), alpha = 0.2;
  const pls = planes(room, () => alpha);
  const sim = makeParticles(room, pls, { x: 2, y: 1.5, z: 1.2 }, () => alpha, 2000);
  const S = pls.reduce((a, p) => a + areaOf(room)(p), 0);
  const eyring = (0.161 * volume(room)) / (-S * Math.log(1 - alpha));
  const levels = [];
  for (let t = 0; t < eyring * 0.6; t += 0.002) { sim.step(0.002); levels.push([t + 0.002, sim.levelDb()]); }
  // slope of the level over time, fitted from -5 to -25 dB
  const seg = levels.filter(([, l]) => l <= -5 && l >= -25);
  const n = seg.length, mt = seg.reduce((a, [t]) => a + t, 0) / n, ml = seg.reduce((a, [, l]) => a + l, 0) / n;
  const slope = seg.reduce((a, [t, l]) => a + (t - mt) * (l - ml), 0) / seg.reduce((a, [t]) => a + (t - mt) ** 2, 0);
  const rt = -60 / slope;
  assert.ok(Math.abs(rt / eyring - 1) < 0.2, `particles ${rt.toFixed(3)} s vs Eyring ${eyring.toFixed(3)} s`);
});

test("calibration makes the surfaces' Eyring decay equal to the measured RT", () => {
  const room = box(5, 4, 2.6);
  const pls = planes(room, () => 0.1);
  const k = calibratedScale(pls, room, areaOf(room), 0.5);
  const S = pls.reduce((a, p) => a + areaOf(room)(p), 0);
  const rt = (0.161 * volume(room)) / (-S * Math.log(1 - 0.1 * k));
  assert.ok(Math.abs(rt - 0.5) < 1e-6);
});

test("the modal field in the volume is centred on its median", () => {
  const room = box(5, 4, 2.6);
  const { points, db } = modalCloud(room, 34.3, { x: 0.5, y: 0.5, z: 0.5 }, 0.6, 0.5);
  assert.equal(points.length, db.length * 3);
  const sorted = Array.from(db).sort((a, b) => a - b);
  assert.ok(Math.abs(sorted[Math.floor(sorted.length / 2)]) < 1e-6);
  // 34.3 Hz is the first axial mode along the 5 m length: loud at both ends, silent across the middle
  const at = (x) => { let best = -Infinity; for (let i = 0; i < db.length; i++) if (Math.abs(points[i * 3] - x) < 0.01) best = Math.max(best, db[i]); return best; };
  assert.ok(at(0.25) > at(2.25) + 10);
});

test("heat peaks at the reflection point", () => {
  const hits = [[1, 1.2, -3]];
  assert.ok(heatAt(hits, 1, 1.2) > heatAt(hits, 1.6, 1.2) + 5);
});

test("particles calibrated by simulation decay with the measured RT", async () => {
  const { calibrate, simulatedRt } = await import("../../web/acoustics3d.js");
  const room = box(5.5, 4.5, 2.6);
  const pls = planes(room, (kind) => (kind === "floor" ? 0.1 : 0.03));
  const src = { x: 0.6, y: 2.25, z: 1.2 };
  const k = calibrate(room, pls, src, 0.6);
  const sim = makeParticles(room, pls, src, (pl) => Math.min(0.95, pl.alpha * k), 2000, 3);
  const rt = simulatedRt(sim, 1.2);
  assert.ok(Math.abs(rt / 0.6 - 1) < 0.08, `calibrated particles ${rt.toFixed(3)} s vs 0.6 s`);
});
