"""FastAPI app. Serves the API and the phone web app from web/."""

from __future__ import annotations

import io
import json
import logging
import os
import time
from collections import defaultdict, deque
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import materials, products, targets
from .acoustics import decay, maps, modes, reverb, treat
from .agents import intake, optimizer, planner
from .room import Room

WEB = Path(__file__).resolve().parent.parent / "web"
log = logging.getLogger("uvicorn.error")

app = FastAPI(title="Clapback")


@app.middleware("http")
async def no_stale_app(request, call_next):
    """Phones cache the app's JS aggressively; make them revalidate so every
    update shows up on the next load (ETags keep it cheap)."""
    response = await call_next(request)
    if not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


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


# Claps are saved with their context for validating the engine. On Vercel
# only /tmp is writable (and it doesn't persist), so saving is best-effort;
# the API itself is stateless: the app sends the per-band results back.
RECORDINGS = Path(
    os.environ.get("CLAPBACK_RECORDINGS")
    or ("/tmp/recordings" if os.environ.get("VERCEL") else Path(__file__).resolve().parent.parent / "recordings")
)
MAX_CLAP_SECONDS = 15


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
    if len(x) > MAX_CLAP_SECONDS * fs:
        raise HTTPException(413, f"recordings longer than {MAX_CLAP_SECONDS} s aren't claps")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    try:
        RECORDINGS.mkdir(parents=True, exist_ok=True)
        sf.write(RECORDINGS / f"clap-{stamp}.wav", x, fs, subtype="FLOAT")
        (RECORDINGS / f"clap-{stamp}.json").write_text(
            json.dumps(
                {"room": json.loads(room or "{}"), "goal": goal, "notes": notes, "mic": json.loads(mic or "{}")},
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError as e:
        log.warning("could not save clap: %s", e)
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    bands = decay.analyze(x, fs)
    out = {
        "id": f"clap-{stamp}",
        "sample_rate": fs,
        "seconds": round(len(x) / fs, 3),
        "peak_dbfs": round(20 * np.log10(peak + 1e-12), 1),
    }
    try:
        room_model = Room.model_validate_json(room) if room and room != "{}" else None
    except ValueError:
        room_model = None
    out["decay"] = [BandIn(**b.to_dict()).model_dump() for b in bands]
    out.update(combine([bands], room_model, goal))
    return out


def analyze(x: np.ndarray, fs: int, room: Room | None, goal: str) -> dict:
    """Everything the results screen shows, from one clap."""
    return combine([decay.analyze(x, fs)], room, goal)


class BandIn(BaseModel):
    """One band of one clap, as /api/clap returned it (the app sends it back)."""
    band_hz: int = Field(ge=20, le=20000)
    edt_s: float | None = Field(None, gt=0, le=20)
    t20_s: float | None = Field(None, gt=0, le=20)
    t30_s: float | None = Field(None, gt=0, le=20)
    dynamic_range_db: float = 0.0

    def to_decay(self) -> decay.BandDecay:
        return decay.BandDecay(**self.model_dump())


def combine(claps: list[list[decay.BandDecay]], room: Room | None, goal: str) -> dict:
    """Average several claps per band (valid values only) and build the report."""
    bands_hz = [b.band_hz for b in claps[0]] if claps else []
    per_band = {f: [b.rt_s for c in claps for b in c if b.band_hz == f and b.rt_s] for f in bands_hz}
    rt = {f: (sum(v) / len(v) if v else None) for f, v in per_band.items()}
    mids = [rt.get(f) for f in (500, 1000) if rt.get(f)]
    rt_mid = sum(mids) / len(mids) if mids else None

    # spread of the per-clap mid RT, for the planner
    clap_mids = []
    for c in claps:
        m = [b.rt_s for b in c if b.band_hz in (500, 1000) and b.rt_s]
        if m:
            clap_mids.append(sum(m) / len(m))
    spread = (max(clap_mids) - min(clap_mids)) / rt_mid * 100 if rt_mid and len(clap_mids) > 1 else None

    out: dict = {
        "claps": len(claps),
        "bands": [{"band_hz": f, "rt_s": rt[f], "n": len(per_band[f])} for f in bands_hz],
        "rt_mid_s": rt_mid,
        "clap_mids_s": [round(m, 3) for m in clap_mids],
        "mid_spread_pct": round(spread, 1) if spread is not None else None,
    }
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
        out["model"] = reverb.calibrate(room, [rt.get(f) for f in reverb.OCTAVE_BANDS_HZ])
    if rt_mid:
        out["maps"] = maps.all_maps(room, [rt.get(f) for f in reverb.OCTAVE_BANDS_HZ], goal)
    return out


class AnalyzeRequest(BaseModel):
    room: Room
    goal: str = Field("", max_length=32)
    notes: str = Field("", max_length=600)
    claps: list[list[BandIn]] = Field(min_length=1, max_length=6)


class PlanRequest(AnalyzeRequest):
    budget_eur: float = Field(150, ge=0, le=5000)


def _claps(req: AnalyzeRequest) -> list[list[decay.BandDecay]]:
    return [[b.to_decay() for b in clap] for clap in req.claps]


# A public demo URL means anyone can spend the Nebius credits. Each server
# instance allows LLM_CALLS_PER_HOUR model-backed requests per client IP.
LLM_CALLS_PER_HOUR = int(os.environ.get("CLAPBACK_LLM_PER_HOUR", "40"))
_calls: dict[str, deque] = defaultdict(deque)


def _rate_limit(request: Request) -> None:
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0]
    now = time.monotonic()
    q = _calls[ip]
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= LLM_CALLS_PER_HOUR:
        raise HTTPException(429, "Too many analyses from this device for now; try again in an hour.")
    q.append(now)


@lru_cache(maxsize=64)
def _intake_cached(room_json: str, notes: str) -> intake.IntakeResult:
    return intake.run(Room.model_validate_json(room_json), notes)


def _with_intake(room: Room, notes: str) -> tuple[Room, intake.IntakeResult]:
    try:
        res = _intake_cached(room.model_dump_json(), notes.strip())
    except Exception as e:  # noqa: BLE001 - the notes are optional; carry on without them
        log.warning("intake failed: %s", e)
        res = intake.IntakeResult(unknown=[notes.strip()] if notes.strip() else [])
    return intake.apply(room, res), res


@app.post("/api/analyze")
def analyze_session(req: AnalyzeRequest, request: Request) -> dict:
    """All claps so far + notes → combined report, what the notes added,
    and whether another clap is worth it."""
    _rate_limit(request)
    claps = _claps(req)
    room, understood = _with_intake(req.room, req.notes)
    out = combine(claps, room, req.goal)
    out["understood"] = understood.model_dump()
    report = {k: out.get(k) for k in ("claps", "rt_mid_s", "clap_mids_s", "mid_spread_pct")}
    report["low_bands_usable"] = [b["band_hz"] for b in out["bands"] if b["band_hz"] <= 250 and b["rt_s"]]
    out["next"] = planner.run(report).model_dump()
    return out


@app.post("/api/plan")
def make_plan(req: PlanRequest, request: Request) -> dict:
    """Budgeted treatment plan from Nemotron, scored by the engine."""
    _rate_limit(request)
    claps = _claps(req)
    room, _ = _with_intake(req.room, req.notes)
    rep = combine(claps, room, req.goal)
    measured = [b["rt_s"] for b in rep["bands"]]
    if not rep["rt_mid_s"]:
        raise HTTPException(422, "no usable measurement yet")
    target = targets.target_rt(req.goal, room.volume())
    plan = optimizer.run(room, req.goal, measured, target, req.budget_eur, rep.get("bass_notes"))
    names = {c["id"]: c["name"] for c in treat.catalogue().values()}
    out = plan.model_dump()
    shop = products.for_plan([t["id"] for t in out["treatments"]])
    for t in out["treatments"]:
        t["name"] = names.get(t["id"], t["id"])
        t["cost_eur"] = round(treat.catalogue()[t["id"]]["eur_per_m2"] * t["area_m2"])
        t["products"] = shop.get(t["id"], [])
    return out


app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
