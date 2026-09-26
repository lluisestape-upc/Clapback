// Result charts, drawn by hand (SVG, one canvas) so they follow the app's
// theme and cost nothing to load. Every function takes the server's JSON as is.

const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

export const BAND_COLORS = {
  125: "#7048e8", 250: "#1c7ed6", 500: "#0ca678", 1000: "#f59f00", 2000: "#e8590c", 4000: "#c2255c",
};
const MODE_COLORS = { axial: "#e8590c", tangential: "#1c7ed6", oblique: "#868e96" };

export const hz = (f) => (f >= 1000 ? `${+(f / 1000).toFixed(1)}k` : `${Math.round(f)}`);

function frame(W, H, pad) {
  return { W, H, pad, x0: pad.l, x1: W - pad.r, y0: pad.t, y1: H - pad.b };
}
const svg = (f, body, label) =>
  `<svg viewBox="0 0 ${f.W} ${f.H}" role="img" aria-label="${label}">${body}</svg>`;
const text = (x, y, s, anchor = "middle", extra = "") =>
  `<text x="${x.toFixed(1)}" y="${y.toFixed(1)}" text-anchor="${anchor}" ${extra}>${s}</text>`;
const line = (x1, y1, x2, y2, cls = "grid") =>
  `<line class="${cls}" x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}"/>`;
const path = (pts) => pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join("");

function niceStep(range, target = 5) {
  const raw = range / target, p = 10 ** Math.floor(Math.log10(raw));
  return [1, 2, 2.5, 5, 10].map((m) => m * p).find((s) => s >= raw);
}

// ---------- RT60 per band (optionally with the plan's prediction) ----------

// certain: every band is trustworthy (a sweep, or the plan view); otherwise
// low bands from a single clap are drawn faded.
export function rtChart(bands, range, after = null, certain = false) {
  const f = frame(340, 190, { l: 40, r: 8, t: 12, b: 40 });
  const vals = bands.flatMap((b, i) => [b.rt_s ?? 0, after?.[i] ?? 0]);
  const max = Math.max(range[1] * 1.3, ...vals) * 1.08;
  const y = (s) => f.y1 - (f.y1 - f.y0) * (s / max);
  const bw = (f.x1 - f.x0) / bands.length;
  const step = niceStep(max, 4);

  let body = "";
  for (let s = 0; s <= max + 1e-9; s += step) {
    body += line(f.x0, y(s), f.x1, y(s)) + text(f.x0 - 6, y(s) + 4, +s.toFixed(2), "end");
  }
  body += `<rect class="zone" x="${f.x0}" y="${y(range[1])}" width="${f.x1 - f.x0}" height="${y(range[0]) - y(range[1])}" rx="3"/>`;
  bands.forEach((b, i) => {
    const cx = f.x0 + (i + 0.5) * bw;
    const w = after ? bw * 0.32 : bw * 0.56;
    const unsure = !certain && b.band_hz < 250 && (b.n ?? 1) < 2;
    if (b.rt_s) {
      const x = after ? cx - w - 1 : cx - w / 2;
      body += `<rect class="bar" x="${x.toFixed(1)}" y="${y(b.rt_s).toFixed(1)}" width="${w.toFixed(1)}" height="${(y(0) - y(b.rt_s)).toFixed(1)}" rx="3" opacity="${unsure ? 0.45 : 1}"><title>${b.band_hz} Hz: ${b.rt_s.toFixed(2)} s</title></rect>`;
    }
    if (after?.[i]) {
      body += `<rect class="bar-after" x="${(cx + 1).toFixed(1)}" y="${y(after[i]).toFixed(1)}" width="${w.toFixed(1)}" height="${(y(0) - y(after[i])).toFixed(1)}" rx="3"><title>After: ${after[i].toFixed(2)} s</title></rect>`;
    }
    body += text(cx, f.y1 + 15, hz(b.band_hz));
  });
  body += text((f.x0 + f.x1) / 2, f.H - 4, "Octave band (Hz)", "middle", 'class="axis-title"');
  body += text(10, (f.y0 + f.y1) / 2, "RT60 (s)", "middle", `class="axis-title" transform="rotate(-90 10 ${(f.y0 + f.y1) / 2})"`);
  return svg(f, body, "Reverberation time per octave band");
}

// ---------- decay curves (Schroeder) over the energy-time curve ----------

export function decayChart(edc, etc) {
  const f = frame(340, 210, { l: 40, r: 8, t: 10, b: 36 });
  const curves = Object.entries(edc.db);
  const longest = Math.max(...curves.map(([, c]) => c.length)) * edc.dt_s;
  const tmax = Math.min(2.5, Math.max(0.3, longest));
  const x = (t) => f.x0 + (f.x1 - f.x0) * Math.min(1, Math.max(0, t / tmax));
  const y = (db) => f.y0 + (f.y1 - f.y0) * Math.min(1, -db / 70);

  let body = "";
  for (let db = 0; db >= -70; db -= 10) body += line(f.x0, y(db), f.x1, y(db)) + text(f.x0 - 6, y(db) + 4, db, "end");
  const ts = niceStep(tmax, 5);
  for (let t = 0; t <= tmax + 1e-9; t += ts) body += text(x(t), f.y1 + 15, +t.toFixed(2));

  if (etc?.db?.length) {
    const pts = etc.db.map((v, i) => [etc.t0_s + i * etc.dt_s, v]).filter(([t]) => t >= 0 && t <= tmax);
    body += `<path class="etc" d="${path(pts.map(([t, v]) => [x(t), y(Math.max(-70, v))]))}"/>`;
  }
  for (const [band, c] of curves) {
    const pts = c.map((v, i) => [x(i * edc.dt_s), y(Math.max(-70, v))]).filter((_, i) => i * edc.dt_s <= tmax);
    body += `<path class="curve" stroke="${BAND_COLORS[band] ?? css("--accent")}" d="${path(pts)}"/>`;
  }
  body += text((f.x0 + f.x1) / 2, f.H - 4, "Time after the direct sound (s)", "middle", 'class="axis-title"');
  body += text(10, (f.y0 + f.y1) / 2, "Level (dB)", "middle", `class="axis-title" transform="rotate(-90 10 ${(f.y0 + f.y1) / 2})"`);
  return svg(f, body, "Energy decay curves per octave band");
}

export function bandLegend(bands) {
  return bands.map((b) => `<span><i style="background:${BAND_COLORS[b]}"></i>${b >= 1000 ? `${b / 1000} kHz` : `${b} Hz`}</span>`).join("") +
    `<span><i class="etc-key"></i>Raw energy</span>`;
}

// ---------- spectrogram (canvas) ----------

const MAGMA = [
  [0, [0, 0, 4]], [0.25, [59, 15, 112]], [0.5, [140, 41, 129]],
  [0.7, [222, 73, 104]], [0.85, [254, 159, 109]], [1, [252, 253, 191]],
];
function magma(v) {
  for (let i = 1; i < MAGMA.length; i++) {
    const [p1, c1] = MAGMA[i], [p0, c0] = MAGMA[i - 1];
    if (v <= p1) {
      const k = (v - p0) / (p1 - p0);
      return c0.map((c, j) => c + (c1[j] - c) * k);
    }
  }
  return MAGMA.at(-1)[1];
}

export function drawSpectrogram(canvas, spec) {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  canvas.width = Math.round(w * dpr);
  canvas.height = Math.round(h * dpr);
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, w, h);
  const pad = { l: 40, r: 8, t: 6, b: 34 };
  const pw = w - pad.l - pad.r, ph = h - pad.t - pad.b;
  const nt = spec.level.length, nf = spec.f_hz.length;
  if (!nt || !nf) return;

  const img = new ImageData(nt, nf);
  for (let t = 0; t < nt; t++) {
    for (let k = 0; k < nf; k++) {
      const [r, g, b] = magma(spec.level[t][k] / 255);
      const o = ((nf - 1 - k) * nt + t) * 4;
      img.data[o] = r; img.data[o + 1] = g; img.data[o + 2] = b; img.data[o + 3] = 255;
    }
  }
  const off = document.createElement("canvas");
  off.width = nt; off.height = nf;
  off.getContext("2d").putImageData(img, 0, 0);
  ctx.imageSmoothingEnabled = true;
  ctx.drawImage(off, pad.l, pad.t, pw, ph);

  ctx.fillStyle = css("--muted");
  ctx.font = "11px system-ui, sans-serif";
  const f0 = spec.f_hz[0], fN = spec.f_hz[nf - 1];
  ctx.textAlign = "right";
  for (const f of [63, 125, 250, 500, 1000, 2000, 4000, 8000]) {
    if (f < f0 || f > fN) continue;
    const yy = pad.t + ph * (1 - Math.log2(f / f0) / Math.log2(fN / f0));
    ctx.fillText(hz(f), pad.l - 6, yy + 4);
  }
  const t0 = spec.t0_s, t1 = spec.t0_s + nt * spec.dt_s;
  const ts = niceStep(t1, 5);
  ctx.textAlign = "center";
  for (let t = 0; t <= t1 + 1e-9; t += ts) {
    ctx.fillText(+t.toFixed(2), pad.l + (pw * (t - t0)) / (t1 - t0), pad.t + ph + 15);
  }
  ctx.fillText("Time after the direct sound (s)", pad.l + pw / 2, h - 4);
  ctx.save();
  ctx.translate(10, pad.t + ph / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillText("Frequency (Hz)", 0, 0);
  ctx.restore();
}

// ---------- room modes, with the measured response when there is one ----------

export function modesChart(modes, schroederHz, response = null) {
  const f = frame(340, 200, { l: 40, r: 8, t: 14, b: 36 });
  const fmin = 20, fmax = 300;
  const x = (hzv) => f.x0 + (f.x1 - f.x0) * (Math.log(hzv / fmin) / Math.log(fmax / fmin));
  const H = { axial: 1, tangential: 0.62, oblique: 0.36 };

  let body = "";
  for (const t of [20, 30, 50, 100, 200, 300]) body += line(x(t), f.y0, x(t), f.y1) + text(x(t), f.y1 + 15, t);
  if (response) {
    const y = (db) => f.y0 + (f.y1 - f.y0) * Math.min(1, Math.max(0, (10 - db) / 40));
    for (const db of [10, 0, -10, -20, -30]) body += text(f.x0 - 6, y(db) + 4, db, "end");
    const pts = response.f_hz.map((fr, i) => [fr, response.db[i]]).filter(([fr]) => fr >= fmin && fr <= fmax);
    body += `<path class="curve response" d="${path(pts.map(([fr, v]) => [x(fr), y(v)]))}"/>`;
    body += text(10, (f.y0 + f.y1) / 2, "Measured level (dB)", "middle", `class="axis-title" transform="rotate(-90 10 ${(f.y0 + f.y1) / 2})"`);
  }
  for (const m of [...modes].reverse()) {
    if (m.freq_hz < fmin || m.freq_hz > fmax) continue;
    const top = f.y1 - (f.y1 - f.y0) * H[m.kind] * (response ? 0.35 : 1);
    body += `<line class="stem" stroke="${MODE_COLORS[m.kind]}" x1="${x(m.freq_hz).toFixed(1)}" y1="${f.y1}" x2="${x(m.freq_hz).toFixed(1)}" y2="${top.toFixed(1)}"><title>${m.freq_hz} Hz ${m.kind} (${m.n.join(",")})</title></line>`;
  }
  if (schroederHz && schroederHz > fmin && schroederHz < fmax) {
    const right = x(schroederHz) > f.x0 + (f.x1 - f.x0) * 0.6;
    body += line(x(schroederHz), f.y0, x(schroederHz), f.y1, "schroeder") +
      text(x(schroederHz) + (right ? -4 : 4), f.y0 + 8, `Schroeder ${Math.round(schroederHz)} Hz`, right ? "end" : "start", 'class="tag"');
  }
  body += text((f.x0 + f.x1) / 2, f.H - 4, "Frequency (Hz)", "middle", 'class="axis-title"');
  return svg(f, body, "Room modes");
}

export const modeLegend = (withResponse) =>
  Object.entries(MODE_COLORS).map(([k, c]) => `<span><i style="background:${c}"></i>${k}</span>`).join("") +
  (withResponse ? `<span><i style="background:var(--fg)"></i>measured</span>` : "");

// ---------- full frequency response (sweep only) ----------

export function responseChart(response, schroederHz) {
  const f = frame(340, 190, { l: 40, r: 8, t: 10, b: 36 });
  const fmin = 20, fmax = 20000;
  const x = (v) => f.x0 + (f.x1 - f.x0) * (Math.log(v / fmin) / Math.log(fmax / fmin));
  const y = (db) => f.y0 + (f.y1 - f.y0) * Math.min(1, Math.max(0, (15 - db) / 45));
  let body = "";
  if (schroederHz) {
    body += `<rect class="modal-zone" x="${f.x0}" y="${f.y0}" width="${(x(schroederHz) - f.x0).toFixed(1)}" height="${f.y1 - f.y0}"/>` +
      text(f.x0 + 4, f.y0 + 11, "modal region", "start", 'class="tag"');
  }
  for (const db of [15, 0, -15, -30]) body += line(f.x0, y(db), f.x1, y(db)) + text(f.x0 - 6, y(db) + 4, db, "end");
  for (const t of [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000]) body += text(x(t), f.y1 + 15, hz(t));
  const pts = response.f_hz.map((fr, i) => [x(fr), y(response.db[i])]);
  body += `<path class="curve response" d="${path(pts)}"/>`;
  body += text((f.x0 + f.x1) / 2, f.H - 4, "Frequency (Hz)", "middle", 'class="axis-title"');
  body += text(10, (f.y0 + f.y1) / 2, "Level (dB)", "middle", `class="axis-title" transform="rotate(-90 10 ${(f.y0 + f.y1) / 2})"`);
  return svg(f, body, "Frequency response at the listening position");
}

// ---------- ISO 3382-1 table ----------

export function isoTable(bands) {
  const cell = (v, d, unit = "") => (v == null ? "–" : `${v.toFixed(d)}${unit}`);
  const rows = [
    ["EDT (s)", (b) => cell(b.edt_s, 2)],
    ["T20 (s)", (b) => cell(b.t20_s, 2)],
    ["T30 (s)", (b) => cell(b.t30_s, 2)],
    ["C50 (dB)", (b) => cell(b.c50_db, 1)],
    ["C80 (dB)", (b) => cell(b.c80_db, 1)],
    ["D50 (%)", (b) => (b.d50 == null ? "–" : `${Math.round(b.d50 * 100)}`)],
  ];
  return `<div class="table-wrap"><table class="iso">
    <thead><tr><th>Band (Hz)</th>${bands.map((b) => `<th>${hz(b.band_hz)}</th>`).join("")}</tr></thead>
    <tbody>${rows.map(([k, fn]) => `<tr><th>${k}</th>${bands.map((b) => `<td>${fn(b)}</td>`).join("")}</tr>`).join("")}</tbody>
  </table></div>`;
}
