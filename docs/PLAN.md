# Plan

## Status (2026-09-26)

Live at https://clapback-alpha.vercel.app (Vercel Hobby, free).

Built: room size typed, measured with the camera and tilt (any phone), or
scanned in AR (tested on the phone); clap and test-sweep measurement;
acoustics engine (decay, ISO 3382-1 values, sweep deconvolution, modes,
Sabine/Eyring, calibration, targets); charts (RT60 per band, decay curves,
spectrogram, frequency response, modes, ISO table, plan before/after);
STI and bass maps in 3D; the three Nemotron agents with fallbacks; Tavily
shop links. 54 tests. The README explains all of it.

Still open:
- **Validate against a reference instrument** (measurement mic + REW, or a
  room with a certified RT60). Real phone claps agree with each other
  (0.67 / 0.69 s), and the sweep matches synthetic rooms within 10 %, but
  the absolute value on a real phone is unverified.
- Real room before/after for the video; the video; Devpost text.

Deadline: 2026-10-30 10:00 PDT (19:00 Barcelona). Target submission: 10-29.

| When | What |
|---|---|
| Before 10-05 (1 h) | Confirm WebXR hit-test works on the phone. Record 3 claps in a room with a known RT60 (`recordings/`). Rotate the Nebius key, put the new one in `.env` |
| 10-06 → 10-10 | `acoustics/decay.py`: clap → T20 per band, validated against the reference. **Kill point 10-10**: off by > 20 % and a swept sine doesn't fix it → switch project |
| 10-11 → 10-16 | `room.py` + `modes.py` + `reverb.py` (Sabine/Eyring, calibration) + `maps.py`; intake + optimizer agents; typed-dimensions flow end to end. **MVP** |
| 10-17 | FirstSong Demo Day, no work |
| 10-18 → 10-21 | `web/scan.js` guided AR scan + surface questions + clap upload. **Timebox: not working by 10-21 → ship with typed dimensions** |
| 10-22 → 10-23 | `web/room3d.js` map layers; planner loop for extra claps. **Feature freeze 10-23** |
| 10-24 → 10-27 | Real room, before/after; record the video |
| 10-28 → 10-29 | README (Nebius + NVIDIA section with measured token cost), Devpost text, submit |

## Distribution

Installable web app (PWA): judges can open the demo URL on any device, and on
Android it installs to the home screen and runs full screen. A Play Store
release isn't possible before the deadline: new personal developer accounts
need a 14-day closed test with 12 testers first. After the hackathon the same
app can be packaged for the Play Store as a Trusted Web Activity (Bubblewrap),
or rewritten natively if the AR or microphone access needs it.

## Video (3 min)

1. Room + problem, a real clap on camera
2. Guided scan: corner, corner, corner, ceiling
3. Decay curve and RT per band against the target
4. 3D room: STI map, modal slice sweeping in frequency
5. Optimizer with budget; after the fix, clap again: measured vs predicted
