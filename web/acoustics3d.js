// Acoustics for the 3D views, without any drawing (so node --test can run it):
// surfaces, heat on surfaces from reflection points, the modal field in the
// whole volume, and sound particles for the clap replay.
//
// Room coordinates are metres, z up. Surfaces follow clapback/acoustics/
// geometry.py: floor, ceiling, then wall A, B, C… along the floor polygon.

const C = 343;
const MID = [2, 3]; // 500 Hz, 1 kHz

export const wallName = (i) => `wall ${String.fromCharCode(65 + (i % 26))}`;

function ccw(floor) {
  let a = 0;
  for (let i = 0; i < floor.length; i++) {
    const p = floor[i], q = floor[(i + 1) % floor.length];
    a += p.x * q.y - q.x * p.y;
  }
  return a > 0;
}

export function inFloor(floor, x, y) {
  let inside = false;
  for (let i = 0; i < floor.length; i++) {
    const a = floor[i], b = floor[(i + 1) % floor.length];
    if ((a.y > y) !== (b.y > y) && x < a.x + ((y - a.y) * (b.x - a.x)) / (b.y - a.y)) inside = !inside;
  }
  return inside;
}

// Surfaces with inward normals. alphaOf(kind, wallIndex) gives each one's
// mid-band absorption (see surfaceAlpha).
export function planes(room, alphaOf = () => 0.05) {
  const out = [
    { name: "floor", kind: "floor", point: [0, 0, 0], normal: [0, 0, 1], alpha: alphaOf("floor") },
    { name: "ceiling", kind: "ceiling", point: [0, 0, room.height], normal: [0, 0, -1], alpha: alphaOf("ceiling") },
  ];
  const s = ccw(room.floor) ? 1 : -1, n = room.floor.length;
  for (let i = 0; i < n; i++) {
    const a = room.floor[i], b = room.floor[(i + 1) % n];
    const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy);
    const ux = dx / len, uy = dy / len;
    out.push({
      name: wallName(i), kind: "wall", index: i, point: [a.x, a.y, 0], normal: [-s * uy, s * ux, 0],
      start: [a.x, a.y, 0], along: [ux, uy, 0], length: len, alpha: alphaOf("wall", i),
    });
  }
  return out;
}

// Mid-band absorption of a surface with its patches, from the materials table.
export function surfaceAlpha(room, mats) {
  const mid = (id) => { const a = mats[id]?.alpha; return a ? (a[MID[0]] + a[MID[1]]) / 2 : 0.05; };
  const floorArea = Math.abs(room.floor.reduce((acc, p, i) => {
    const q = room.floor[(i + 1) % room.floor.length];
    return acc + p.x * q.y - q.x * p.y;
  }, 0)) / 2;
  return (kind, i) => {
    const s = room.surfaces.find((x) => x.kind === kind && (kind !== "wall" || x.wall_index === i));
    if (!s) return mid("plaster_on_masonry");
    let area = floorArea;
    if (kind === "wall") {
      const a = room.floor[i], b = room.floor[(i + 1) % room.floor.length];
      area = Math.hypot(b.x - a.x, b.y - a.y) * room.height;
    }
    const patch = (s.patches ?? []).reduce((acc, p) => acc + p.area_m2, 0);
    const sum = mid(s.material) * Math.max(area - patch, 0) + (s.patches ?? []).reduce((acc, p) => acc + mid(p.material) * p.area_m2, 0);
    return area > 0 ? sum / area : mid(s.material);
  };
}

// In-plane coordinates of a point: (along the wall, height) or (x, y).
export function local(pl, p) {
  if (pl.kind === "wall") return [(p[0] - pl.start[0]) * pl.along[0] + (p[1] - pl.start[1]) * pl.along[1], p[2]];
  return [p[0], p[1]];
}

// Heat on a surface from the reflection points on it: power sum of each
// path's level, spread over about a panel's size (sigma).
export function heatAt(hits, u, v, sigma = 0.3) {
  let e = 0;
  for (const [hu, hv, level] of hits) {
    const d2 = (hu - u) ** 2 + (hv - v) ** 2;
    e += 10 ** (level / 10) * Math.exp(-d2 / (2 * sigma * sigma));
  }
  return 10 * Math.log10(e + 1e-9);
}

export function hitsBySurface(reflections, after = false) {
  const out = {};
  for (const r of reflections) {
    const level = after && r.level_after_db != null ? r.level_after_db : r.level_db;
    r.surfaces.forEach((name, k) => (out[name] ??= []).push([...r.points[k], level]));
  }
  return out;
}

// Pressure level (dB, 0 = median) of one frequency over a 3D grid, from the
// same modal sum as maps.py / modalGrid in room3d.js. Rectangular rooms.
export function modalCloud(room, freq, src, rt = 0.5, step = 0.3) {
  const xsR = room.floor.map((p) => p.x), ysR = room.floor.map((p) => p.y);
  const x0 = Math.min(...xsR), y0 = Math.min(...ysR);
  const lx = Math.max(...xsR) - x0, ly = Math.max(...ysR) - y0, lz = room.height;
  const fMax = Math.max(2 * freq, 60), w = 2 * Math.PI * freq, delta = 6.91 / rt;
  const axis = (L, o) => { const a = []; for (let t = step / 2; t < L; t += step) a.push(o + t); return a; };
  const xs = axis(lx, x0), ys = axis(ly, y0), zs = axis(lz, 0);
  const n = xs.length * ys.length * zs.length;
  const re = new Float64Array(n), im = new Float64Array(n);
  const N = (L) => Math.floor((2 * fMax * L) / C) + 1;
  const modes = [[0, 0, 0, 0]];
  for (let a = 0; a <= N(lx); a++) for (let b = 0; b <= N(ly); b++) for (let d = 0; d <= N(lz); d++) {
    if (!a && !b && !d) continue;
    const f = (C / 2) * Math.hypot(a / lx, b / ly, d / lz);
    if (f <= fMax) modes.push([a, b, d, f]);
  }
  for (const [a, b, d, f] of modes) {
    const wn = 2 * Math.PI * f, lam = (a ? 0.5 : 1) * (b ? 0.5 : 1) * (d ? 0.5 : 1);
    const ps = Math.cos((a * Math.PI * (src.x - x0)) / lx) * Math.cos((b * Math.PI * (src.y - y0)) / ly) * Math.cos((d * Math.PI * src.z) / lz);
    const dr = lam * (wn * wn - w * w), di = lam * 2 * delta * w, den = dr * dr + di * di;
    const cr = (ps * dr) / den, ci = (-ps * di) / den;
    const cx = xs.map((x) => Math.cos((a * Math.PI * (x - x0)) / lx));
    const cy = ys.map((y) => Math.cos((b * Math.PI * (y - y0)) / ly));
    const cz = zs.map((z) => Math.cos((d * Math.PI * z) / lz));
    let k = 0;
    for (let iz = 0; iz < zs.length; iz++) for (let iy = 0; iy < ys.length; iy++) {
      const yz = cy[iy] * cz[iz];
      for (let ix = 0; ix < xs.length; ix++, k++) { const m = cx[ix] * yz; re[k] += m * cr; im[k] += m * ci; }
    }
  }
  const points = new Float32Array(n * 3), db = new Float32Array(n);
  let k = 0;
  for (const z of zs) for (const y of ys) for (const x of xs) {
    points.set([x, y, z], k * 3);
    db[k] = 20 * Math.log10(Math.hypot(re[k], im[k]) + 1e-12);
    k++;
  }
  const sorted = Array.from(db).sort((p, q) => p - q), med = sorted[Math.floor(n / 2)];
  for (let i = 0; i < n; i++) db[i] -= med;
  return { points, db, step };
}

// ---------- sound particles ----------

// Scale the surfaces' absorption so an Eyring decay with them gives the
// measured RT: furniture and anything else the model misses is spread over
// the surfaces.
export function calibratedScale(pls, room, areaOf, rtMeasured) {
  const V = volume(room);
  const S = pls.reduce((a, p) => a + areaOf(p), 0);
  const mean = pls.reduce((a, p) => a + areaOf(p) * p.alpha, 0) / S;
  const want = 1 - Math.exp((-0.161 * V) / (S * rtMeasured));
  return mean > 0 ? want / mean : 1;
}

export function volume(room) {
  const a = Math.abs(room.floor.reduce((acc, p, i) => {
    const q = room.floor[(i + 1) % room.floor.length];
    return acc + p.x * q.y - q.x * p.y;
  }, 0)) / 2;
  return a * room.height;
}

export function areaOf(room) {
  const fa = volume(room) / room.height;
  return (p) => (p.kind === "wall" ? p.length * room.height : fa);
}

// A deterministic generator, so replays (and tests) repeat.
function rng(seed) {
  let s = seed >>> 0;
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
}

// Particles leave the source in random directions at the speed of sound,
// reflect specularly and keep (1 - α) of their energy at every hit.
// absorb(plane, point) returns the α at that point (a treatment or the surface).
export function makeParticles(room, pls, src, absorb, n = 1500, seed = 7) {
  const r = rng(seed);
  const pos = new Float32Array(n * 3), vel = new Float32Array(n * 3), energy = new Float32Array(n).fill(1);
  for (let i = 0; i < n; i++) {
    const u = 2 * r() - 1, phi = 2 * Math.PI * r(), s = Math.sqrt(1 - u * u);
    vel.set([C * s * Math.cos(phi), C * s * Math.sin(phi), C * u], i * 3);
    pos.set([src.x, src.y, src.z], i * 3);
  }
  const onSurface = (pl, p) => {
    if (pl.kind === "wall") {
      const t = (p[0] - pl.start[0]) * pl.along[0] + (p[1] - pl.start[1]) * pl.along[1];
      return t >= -1e-6 && t <= pl.length + 1e-6 && p[2] >= -1e-6 && p[2] <= room.height + 1e-6;
    }
    return inFloor(room.floor, p[0], p[1]);
  };
  // advance every particle by dt seconds
  function step(dt) {
    for (let i = 0; i < n; i++) {
      let left = dt, guard = 0;
      while (left > 0 && guard++ < 8) {
        const p = [pos[i * 3], pos[i * 3 + 1], pos[i * 3 + 2]], v = [vel[i * 3], vel[i * 3 + 1], vel[i * 3 + 2]];
        let best = null, tBest = left;
        for (const pl of pls) {
          const vn = v[0] * pl.normal[0] + v[1] * pl.normal[1] + v[2] * pl.normal[2];
          if (vn >= 0) continue; // moving away from this surface
          const dist = (p[0] - pl.point[0]) * pl.normal[0] + (p[1] - pl.point[1]) * pl.normal[1] + (p[2] - pl.point[2]) * pl.normal[2];
          const t = -dist / vn;
          if (t < -1e-9 || t > tBest) continue;
          const hit = [p[0] + v[0] * t, p[1] + v[1] * t, p[2] + v[2] * t];
          if (onSurface(pl, hit)) { best = { pl, hit }; tBest = Math.max(t, 0); }
        }
        if (!best) {
          for (let k = 0; k < 3; k++) pos[i * 3 + k] += v[k] * left;
          left = 0;
        } else {
          const { pl, hit } = best, nrm = pl.normal;
          const vn = v[0] * nrm[0] + v[1] * nrm[1] + v[2] * nrm[2];
          for (let k = 0; k < 3; k++) { pos[i * 3 + k] = hit[k] + nrm[k] * 1e-4; vel[i * 3 + k] = v[k] - 2 * vn * nrm[k]; }
          energy[i] *= 1 - absorb(pl, hit);
          left -= tBest;
        }
      }
    }
  }
  const levelDb = () => { let e = 0; for (let i = 0; i < n; i++) e += energy[i]; return 10 * Math.log10(e / n + 1e-12); };
  return { pos, energy, n, step, levelDb };
}

// RT of a particle run: slope of its level from -5 to -25 dB.
export function simulatedRt(sim, tMax, dt = 0.002) {
  const levels = [];
  for (let t = dt; t <= tMax; t += dt) { sim.step(dt); levels.push([t, sim.levelDb()]); if (levels.at(-1)[1] < -30) break; }
  const seg = levels.filter(([, l]) => l <= -5 && l >= -25);
  if (seg.length < 3) return null;
  const n = seg.length, mt = seg.reduce((a, [t]) => a + t, 0) / n, ml = seg.reduce((a, [, l]) => a + l, 0) / n;
  const slope = seg.reduce((a, [t, l]) => a + (t - mt) * (l - ml), 0) / seg.reduce((a, [t]) => a + (t - mt) ** 2, 0);
  return slope < 0 ? -60 / slope : null;
}

// Absorption scale that makes the particles decay with the measured RT.
// Starts from Eyring, then corrects with a quick run: a box with specular
// reflections decays a little slower than Eyring assumes.
export function calibrate(room, pls, src, rtMeasured, alphaOf = (pl) => pl.alpha) {
  let k = calibratedScale(pls, room, areaOf(room), rtMeasured);
  for (let it = 0; it < 2; it++) {
    const sim = makeParticles(room, pls, src, (pl) => Math.min(0.95, alphaOf(pl) * k), 500, 11);
    const rt = simulatedRt(sim, rtMeasured * 1.5);
    if (!rt) break;
    k *= rt / rtMeasured;
  }
  return k;
}
