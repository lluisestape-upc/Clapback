"""FastAPI app. Serves the API and the phone web app from web/."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
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


# TODO POST /api/clap      upload a recording → per-band decay (acoustics.decay)
# TODO POST /api/analyze   room + claps → RT, modes, maps, calibration
# TODO POST /api/intake    surface descriptions → materials (agents.intake)
# TODO POST /api/next      → next measurement (agents.planner)
# TODO POST /api/plan      goal + budget → treatment plan (agents.optimizer)

app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
