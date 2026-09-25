"""FastAPI app. Serves the API and the phone web app from web/."""

from __future__ import annotations

import io
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles

from . import materials, targets
from .acoustics import decay, modes, reverb
from .room import Room

WEB = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(title="Clapback")


@app.get("/api/health")
def health() -> dict:
    return {"ok": True}


@app.get("/api/materials")
def list_materials() -> list[dict]:
    return [m.model_dump() for m in materials.load().values()]


@app.post("/api/room")
def check_room(room: Room) -> dict:
    """Validate a room (typed or scanned) and return its basic geometry."""
    for s in room.surfaces:
        for mat in [s.material, *(p.material for p in s.patches)]:
            if mat not in materials.load():
                raise HTTPException(422, f"unknown material '{mat}'")
    return {
        "volume_m3": room.volume(),
        "floor_area_m2": room.floor_area(),
        "total_area_m2": room.total_area(),
        "rectangular": room.is_rectangular(),
    }


RECORDINGS = Path(__file__).resolve().parent.parent / "recordings"


@app.post("/api/clap")
async def upload_clap(
    audio: UploadFile,
    room: str = Form("{}"),
    goal: str = Form(""),
    notes: str = Form(""),
    mic: str = Form("{}"),
) -> dict:
    """Save a clap recording with its context and analyse it.

    Every clap from the phone lands in recordings/ with a JSON sidecar, which
    is also how the reference claps for validating decay.py get collected.
    """
    data = await audio.read()
    try:
        x, fs = sf.read(io.BytesIO(data), dtype="float32")
    except Exception as e:  # noqa: BLE001 - any decode failure is a bad upload
        raise HTTPException(422, f"could not read audio: {e}") from e
    if x.ndim > 1:
        x = x.mean(axis=1)

    RECORDINGS.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    wav = RECORDINGS / f"clap-{stamp}.wav"
    sf.write(wav, x, fs, subtype="FLOAT")
    (RECORDINGS / f"clap-{stamp}.json").write_text(
        json.dumps(
            {"room": json.loads(room or "{}"), "goal": goal, "notes": notes, "mic": json.loads(mic or "{}")},
            indent=2,
        ),
        encoding="utf-8",
    )
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    out = {
        "id": wav.stem,
        "sample_rate": fs,
        "seconds": round(len(x) / fs, 3),
        "peak_dbfs": round(20 * np.log10(peak + 1e-12), 1),
    }
    try:
        room_model = Room.model_validate_json(room) if room and room != "{}" else None
    except ValueError:
        room_model = None
    out.update(analyze(x, fs, room_model, goal))
    return out


def analyze(x: np.ndarray, fs: int, room: Room | None, goal: str) -> dict:
    """Everything the results screen shows, from one clap."""
    bands = decay.analyze(x, fs)
    by_band = {b.band_hz: b.rt_s for b in bands}
    mids = [by_band.get(f) for f in (500, 1000) if by_band.get(f)]
    rt_mid = sum(mids) / len(mids) if mids else None

    out: dict = {"bands": [b.to_dict() for b in bands], "rt_mid_s": rt_mid}
    if room is None:
        return out

    V = room.volume()
    out["volume_m3"] = round(V, 1)
    out["verdict"] = targets.verdict(goal, V, rt_mid)
    if rt_mid:
        out["schroeder_hz"] = round(modes.schroeder_frequency(rt_mid, V))
    if room.is_rectangular():
        xs = [p.x for p in room.floor]
        ys = [p.y for p in room.floor]
        lx, ly = max(xs) - min(xs), max(ys) - min(ys)
        ms = modes.room_modes(lx, ly, room.height, f_max=200)
        out["bass_notes"] = modes.problem_frequencies(ms, below_hz=out.get("schroeder_hz", 200))
    if room.surfaces:
        measured = [by_band.get(f) for f in reverb.OCTAVE_BANDS_HZ]
        out["model"] = reverb.calibrate(room, measured)
    return out


# TODO POST /api/analyze   room + claps → RT, modes, maps, calibration
# TODO POST /api/intake    surface descriptions → materials (agents.intake)
# TODO POST /api/next      → next measurement (agents.planner)
# TODO POST /api/plan      goal + budget → treatment plan (agents.optimizer)

app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
