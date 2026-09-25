# Architecture

## Principle

Models choose and call; the engine computes; the claps check. No acoustic
number in the output comes from a language model.

## Data flow

1. **Room**: `clapback/room.py`. Floor polygon + height + surfaces with
   material ids. Produced by the typed form or by the AR scan; the engine
   can't tell which.
2. **Intake** (`agents/intake.py`, Nemotron Nano): the user's words per
   surface → material ids from `data/materials.json`, with patches for
   partial coverage. Unmappable text goes back to the user.
3. **Clap** (`web/capture.js` → `acoustics/decay.py`): raw PCM with browser
   voice processing off → onset, octave bands, noise-floor truncation,
   Schroeder integration → EDT, T20, T30 per band.
4. **Model** (`acoustics/reverb.py`, `modes.py`): Sabine/Eyring prediction,
   calibrated to the measured RT per surface; modes and Schroeder frequency
   for rectangular rooms.
5. **Planner** (`agents/planner.py`, Nemotron Super): reads the calibration
   report and asks for the next clap where the uncertainty is high, or stops.
6. **Maps** (`acoustics/maps.py`): C50 / STI estimate (Barron's revised
   theory) and modal pressure on the floor plane → `web/room3d.js`.
7. **Optimizer** (`agents/optimizer.py`, Nemotron Super with tools): tries
   treatments against a goal and a budget, each scored by the engine;
   optional Tavily product search.

## Limits to state in the report, not hide

- Statistical acoustics assumes a diffuse field: unreliable below the
  Schroeder frequency and in very absorbent or very non-cuboid rooms.
- Modal maps only for rectangular rooms.
- STI from Barron's theory is an estimate, not an ISO 3382 / IEC 60268-16
  measurement.
- Material coefficients in `data/materials.json` are typical table values.
