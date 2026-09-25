// Clap capture as raw PCM → WAV, with a live level for the meter and a quick
// quality check so the user knows right away whether to clap again.
//
// Two things matter for decay measurement:
//  - Browser voice processing (echo cancellation, noise suppression, AGC)
//    must be off, or it eats the reverberant tail. Some phones ignore the
//    request, so the settings actually applied are returned and checked.
//  - No lossy codec (MediaRecorder gives Opus), so samples are taken straight
//    from an AudioWorklet.

const WORKLET = `
class Tap extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0][0];
    if (ch) this.port.postMessage(ch.slice(0));
    return true;
  }
}
registerProcessor("tap", Tap);
`;

export async function openMic() {
  return navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: false,
      noiseSuppression: false,
      autoGainControl: false,
      channelCount: 1,
    },
  });
}

// onLevel(0..1) is called per audio block while recording.
// bits: 32 (float) for claps; 16 halves the upload of a 15 s sweep recording.
export async function recordClap(stream, { seconds = 5, onLevel = () => {}, bits = 32 } = {}) {
  const track = stream.getAudioTracks()[0];
  const ctx = new AudioContext();
  const url = URL.createObjectURL(new Blob([WORKLET], { type: "text/javascript" }));
  await ctx.audioWorklet.addModule(url);

  const src = ctx.createMediaStreamSource(stream);
  const tap = new AudioWorkletNode(ctx, "tap");
  const chunks = [];
  tap.port.onmessage = (e) => {
    const c = e.data;
    chunks.push(c);
    let peak = 0;
    for (let i = 0; i < c.length; i++) peak = Math.max(peak, Math.abs(c[i]));
    // map -60..0 dBFS to 0..1 for the meter
    const db = 20 * Math.log10(peak + 1e-9);
    onLevel(Math.min(1, Math.max(0, (db + 60) / 60)));
  };
  src.connect(tap);

  await new Promise((r) => setTimeout(r, seconds * 1000));

  src.disconnect();
  const settings = { ...track.getSettings(), sampleRate: ctx.sampleRate };
  await ctx.close();

  const n = chunks.reduce((a, c) => a + c.length, 0);
  const pcm = new Float32Array(n);
  let o = 0;
  for (const c of chunks) { pcm.set(c, o); o += c.length; }

  return { pcm, settings, blob: toWav(pcm, settings.sampleRate, bits) };
}

// Rough, fast check for coaching only. The real analysis happens on the server.
// Uses 10 ms RMS frames: loudest frame vs the quietest 20 % (background noise).
export function quickQuality(pcm, fs) {
  const hop = Math.round(fs * 0.01);
  const frames = [];
  let peak = 0;
  for (let i = 0; i + hop <= pcm.length; i += hop) {
    let s = 0;
    for (let j = i; j < i + hop; j++) { s += pcm[j] * pcm[j]; peak = Math.max(peak, Math.abs(pcm[j])); }
    frames.push(10 * Math.log10(s / hop + 1e-12));
  }
  const sorted = [...frames].sort((a, b) => a - b);
  const noise = sorted[Math.floor(sorted.length * 0.2)];
  const loud = sorted[sorted.length - 1];
  const range = loud - noise;
  const clipped = peak >= 0.999;

  let level, message;
  if (clipped) { level = "warn"; message = "Too loud for the mic. Hold the phone a bit further away and clap again."; }
  else if (range < 20) { level = "bad"; message = "I couldn't hear a clear clap. Try a sharper, louder clap."; }
  else if (range < 35) { level = "warn"; message = "Usable, but a bit quiet or noisy. A louder clap in silence will be more accurate."; }
  else { level = "good"; message = "Great clap. That's all I need."; }
  return { level, message, rangeDb: range, peakDb: 20 * Math.log10(peak + 1e-9) };
}

// Mono WAV: 32-bit float, or 16-bit PCM.
function toWav(pcm, fs, bits = 32) {
  const bytes = bits / 8;
  const buf = new ArrayBuffer(44 + pcm.length * bytes);
  const v = new DataView(buf);
  const str = (off, s) => [...s].forEach((c, i) => v.setUint8(off + i, c.charCodeAt(0)));
  str(0, "RIFF"); v.setUint32(4, 36 + pcm.length * bytes, true); str(8, "WAVE");
  str(12, "fmt "); v.setUint32(16, 16, true);
  v.setUint16(20, bits === 32 ? 3 : 1, true);   // 3 = IEEE float, 1 = PCM
  v.setUint16(22, 1, true);                     // mono
  v.setUint32(24, fs, true);
  v.setUint32(28, fs * bytes, true);            // byte rate
  v.setUint16(32, bytes, true);                 // block align
  v.setUint16(34, bits, true);
  str(36, "data"); v.setUint32(40, pcm.length * bytes, true);
  if (bits === 32) new Float32Array(buf, 44).set(pcm);
  else pcm.forEach((s, i) => v.setInt16(44 + i * 2, Math.max(-1, Math.min(1, s)) * 32767, true));
  return new Blob([buf], { type: "audio/wav" });
}
