// Clap capture as raw PCM → WAV.
//
// Two things matter for decay measurement:
//  - Browser voice processing (echo cancellation, noise suppression, AGC)
//    must be off, or it eats the reverberant tail. Some phones ignore the
//    request, so the settings actually applied are returned and should be
//    checked.
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

export async function recordClap({ seconds = 3 } = {}) {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: false,
      noiseSuppression: false,
      autoGainControl: false,
      channelCount: 1,
    },
  });
  const track = stream.getAudioTracks()[0];
  const ctx = new AudioContext();
  const url = URL.createObjectURL(new Blob([WORKLET], { type: "text/javascript" }));
  await ctx.audioWorklet.addModule(url);

  const src = ctx.createMediaStreamSource(stream);
  const tap = new AudioWorkletNode(ctx, "tap");
  const chunks = [];
  tap.port.onmessage = (e) => chunks.push(e.data);
  src.connect(tap);

  await new Promise((r) => setTimeout(r, seconds * 1000));

  src.disconnect();
  track.stop();
  const settings = { ...track.getSettings(), sampleRate: ctx.sampleRate };
  await ctx.close();

  const n = chunks.reduce((a, c) => a + c.length, 0);
  const pcm = new Float32Array(n);
  let o = 0;
  for (const c of chunks) { pcm.set(c, o); o += c.length; }

  return { blob: toWav(pcm, settings.sampleRate), settings };
}

// 32-bit float WAV, mono.
function toWav(pcm, fs) {
  const buf = new ArrayBuffer(44 + pcm.length * 4);
  const v = new DataView(buf);
  const str = (off, s) => [...s].forEach((c, i) => v.setUint8(off + i, c.charCodeAt(0)));
  str(0, "RIFF"); v.setUint32(4, 36 + pcm.length * 4, true); str(8, "WAVE");
  str(12, "fmt "); v.setUint32(16, 16, true);
  v.setUint16(20, 3, true);           // format 3 = IEEE float
  v.setUint16(22, 1, true);           // mono
  v.setUint32(24, fs, true);
  v.setUint32(28, fs * 4, true);      // byte rate
  v.setUint16(32, 4, true);           // block align
  v.setUint16(34, 32, true);          // bits per sample
  str(36, "data"); v.setUint32(40, pcm.length * 4, true);
  new Float32Array(buf, 44).set(pcm);
  return new Blob([buf], { type: "audio/wav" });
}
