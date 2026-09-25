// Test sweep: the exponential sine sweep of clapback/acoustics/sweep.py.
// Keep ess() in step with the Python one: the server rebuilds this exact
// signal (continuous-time definition, so the player's sample rate is free).

export const SWEEP = { f1: 40, f2: 16000, seconds: 6 };
const FADE_IN_S = 0.05, FADE_OUT_S = 0.01, AMPLITUDE = 0.5;

export function ess(fs, { f1, f2, seconds } = SWEEP) {
  const n = Math.round(seconds * fs);
  const L = seconds / Math.log(f2 / f1);
  const x = new Float32Array(n);
  const ni = Math.floor(FADE_IN_S * fs), no = Math.floor(FADE_OUT_S * fs);
  for (let i = 0; i < n; i++) {
    const t = i / fs;
    let g = AMPLITUDE;
    if (i < ni) g *= 0.5 - 0.5 * Math.cos((Math.PI * i) / ni);
    if (i >= n - no) g *= 0.5 + 0.5 * Math.cos((Math.PI * (i - (n - no))) / no);
    x[i] = g * Math.sin(2 * Math.PI * f1 * L * (Math.exp(t / L) - 1));
  }
  return x;
}

// Play the sweep through this device's audio output (its speaker, or a
// Bluetooth speaker connected to it). Resolves when playback ends.
export async function playSweep(ctx = new AudioContext(), delayS = 0.3) {
  if (ctx.state === "suspended") await ctx.resume();
  const x = ess(ctx.sampleRate);
  const buf = ctx.createBuffer(1, x.length, ctx.sampleRate);
  buf.copyToChannel(x, 0);
  const src = ctx.createBufferSource();
  src.buffer = buf;
  src.connect(ctx.destination);
  src.start(ctx.currentTime + delayS);
  await new Promise((r) => { src.onended = r; });
  return ctx;
}
