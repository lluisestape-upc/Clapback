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

from . import materials
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
) -> dict:
    """Save a clap recording with its context, return basic facts about it.

    Every clap from the phone lands in recordings/ with a JSON sidecar, which
    is also how the reference claps for validating decay.py get collected.
    TODO: run acoustics.decay.analyze once it exists.
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
        json.dumps({"room": json.loads(room or "{}"), "goal": goal, "notes": notes}, indent=2),
        encoding="utf-8",
    )
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    return {
        "id": wav.stem,
        "sample_rate": fs,
        "seconds": round(len(x) / fs, 3),
        "peak_dbfs": round(20 * np.log10(peak + 1e-12), 1),
    }


# TODO POST /api/analyze   room + claps → RT, modes, maps, calibration
# TODO POST /api/intake    surface descriptions → materials (agents.intake)
# TODO POST /api/next      → next measurement (agents.planner)
# TODO POST /api/plan      goal + budget → treatment plan (agents.optimizer)

app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
