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
from .acoustics import decay, maps, modes, reverb, sweep, treat
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
MAX_SWEEP_SECONDS = 25


def _read_audio(data: bytes, max_seconds: float) -> tuple[np.ndarray, int]:
    try:
        x, fs = sf.read(io.BytesIO(data), dtype="float32")
    except Exception as e:  # noqa: BLE001 - any decode failure is a bad upload
        raise HTTPException(422, f"could not read audio: {e}") from e
    if x.ndim > 1:
        x = x.mean(axis=1)
    if len(x) > max_seconds * fs:
        raise HTTPException(413, f"recordings longer than {max_seconds} s aren't measurements")
    return x, fs


def _save(kind: str, x: np.ndarray, fs: int, meta: dict) -> str:
    """Best-effort copy of the recording and its context, for validating the engine."""
    name = f"{kind}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    try:
        RECORDINGS.mkdir(parents=True, exist_ok=True)
        sf.write(RECORDINGS / f"{name}.wav", x, fs, subtype="FLOAT")
        (RECORDINGS / f"{name}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    except OSError as e:
        log.warning("could not save %s: %s", kind, e)
    return name


def _meta(room: str, goal: str, notes: str, mic: str, **extra) -> dict:
    try:
        return {"room": json.loads(room or "{}"), "goal": goal, "notes": notes,
                "mic": json.loads(mic or "{}"), **extra}
    except ValueError:
        raise HTTPException(422, "room and mic must be JSON") from None


def _room_or_none(room: str) -> Room | None:
    try:
        return Room.model_validate_json(room) if room and room != "{}" else None
    except ValueError:
        return None


def _measurement(name: str, kind: str, x: np.ndarray, fs: int, bands, detail: dict,
                 room: str, goal: str) -> dict:
    peak = float(np.max(np.abs(x))) if x.size else 0.0
    out = {
        "id": name,
        "kind": kind,
        "sample_rate": fs,
        "seconds": round(len(x) / fs, 3),
        "peak_dbfs": round(20 * np.log10(peak + 1e-12), 1),
        "decay": [BandIn(**b.to_dict()).model_dump() for b in bands],
        "detail": detail,
    }
    out.update(combine([bands], _room_or_none(room), goal))
    return out


@app.post("/api/clap")
async def upload_clap(
    audio: UploadFile,
    room: str = Form("{}"),
    goal: str = Form(""),
    notes: str = Form(""),
    mic: str = Form("{}"),
) -> dict:
    """Analyse one clap recording. The app keeps the per-band results and
    sends them back to /api/analyze, so the server stays stateless."""
    x, fs = _read_audio(await audio.read(), MAX_CLAP_SECONDS)
    name = _save("clap", x, fs, _meta(room, goal, notes, mic))
    bands, detail = decay.analyze_full(x, fs)
    return _measurement(name, "clap", x, fs, bands, detail, room, goal)


@app.post("/api/sweep")
async def upload_sweep(
    audio: UploadFile,
    room: str = Form("{}"),
    goal: str = Form(""),
    notes: str = Form(""),
    mic: str = Form("{}"),
    f1: float = Form(sweep.F1_HZ),
    f2: float = Form(sweep.F2_HZ),
    seconds: float = Form(sweep.SECONDS),
) -> dict:
    """Recording of the test sweep → impulse response → the same analysis
    as a clap, plus the frequency response and the IR as a WAV."""
    x, fs = _read_audio(await audio.read(), MAX_SWEEP_SECONDS)
    if not (20 <= f1 < f2 <= fs / 2 and 1 <= seconds <= 15):
        raise HTTPException(422, "bad sweep parameters")
    name = _save("sweep", x, fs, _meta(room, goal, notes, mic, f1=f1, f2=f2, seconds=seconds))
    try:
        ir, info = sweep.deconvolve(x, fs, f1, f2, seconds)
    except sweep.NoSweep as e:
        raise HTTPException(422, str(e)) from None
    bands, detail = decay.analyze_full(ir, fs)
    detail["response"] = sweep.response(ir, fs, f1, f2)
    detail["ir_wav"] = sweep.wav_base64(ir, fs)
    detail["sweep"] = info
    if np.max(np.abs(x)) >= 0.999:
        detail["warning"] = "The mic was overloaded. Turn the speaker down a little and measure again."
    return _measurement(name, "sweep", x, fs, bands, detail, room, goal)


class BandIn(BaseModel):
    """One band of one clap, as /api/clap returned it (the app sends it back)."""
    band_hz: int = Field(ge=20, le=20000)
    edt_s: float | None = Field(None, gt=0, le=20)
    t20_s: float | None = Field(None, gt=0, le=20)
    t30_s: float | None = Field(None, gt=0, le=20)
    dynamic_range_db: float = 0.0
    c50_db: float | None = Field(None, ge=-40, le=40)
    c80_db: float | None = Field(None, ge=-40, le=40)
    d50: float | None = Field(None, ge=0, le=1)

    def to_decay(self) -> decay.BandDecay:
        return decay.BandDecay(**self.model_dump())


ISO_FIELDS = ("edt_s", "t20_s", "t30_s", "c50_db", "c80_db", "d50")


def _mean(v: list[float]) -> float | None:
    return sum(v) / len(v) if v else None


def combine(claps: list[list[decay.BandDecay]], room: Room | None, goal: str) -> dict:
    """Average several measurements per band (valid values only) and build the report."""
    bands_hz = [b.band_hz for b in claps[0]] if claps else []
    rows, rt = [], {}
    for f in bands_hz:
        items = [b for c in claps for b in c if b.band_hz == f]
        rts = [b.rt_s for b in items if b.rt_s]
        rt[f] = _mean(rts)
        row = {"band_hz": f, "rt_s": rt[f], "n": len(rts)}
        for k in ISO_FIELDS:
            v = _mean([getattr(b, k) for b in items if getattr(b, k) is not None])
            row[k] = round(v, 3) if v is not None else None
        rows.append(row)
    mids = [rt.get(f) for f in (500, 1000) if rt.get(f)]
    rt_mid = sum(mids) / len(mids) if mids else None

    # spread of the per-measurement mid RT, for the planner
    clap_mids = []
    for c in claps:
        m = [b.rt_s for b in c if b.band_hz in (500, 1000) and b.rt_s]
        if m:
            clap_mids.append(sum(m) / len(m))
    spread = (max(clap_mids) - min(clap_mids)) / rt_mid * 100 if rt_mid and len(clap_mids) > 1 else None

    out: dict = {
        "claps": len(claps),
        "bands": rows,
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
        ms = modes.room_modes(lx, ly, room.height, f_max=300)
        out["bass_notes"] = modes.problem_frequencies(
            [m for m in ms if m.freq_hz <= 200], below_hz=out.get("schroeder_hz", 200))
        out["modes"] = [{"freq_hz": round(m.freq_hz, 1), "kind": m.kind, "n": list(m.n)} for m in ms]
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
    kinds: list[str] = Field(default_factory=list, max_length=6)  # "clap" / "sweep", same order


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
    report["sweeps"] = req.kinds.count("sweep")
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
