"""Score treatment plans against the measured room.

The optimizer agent proposes plans; everything here decides whether a plan is
allowed and what it would do. The baseline is the *measured* absorption (from
the claps), not the material guesses, so furniture and other things the
model doesn't know about are already included.

    A_now(band)   = 0.161 V / T_measured - 4 m V
    ΔA(band)      = Σ S_i (α_treatment - α_covered)
    T_new(band)   = 0.161 V / (A_now + ΔA + 4 m V)
"""

from __future__ import annotations

import json
from collections import Counter
from functools import lru_cache
from pathlib import Path
from statistics import median

from pydantic import BaseModel, Field

from .. import materials
from ..room import OCTAVE_BANDS_HZ, Room
from .reverb import AIR_M, absorption_area

DATA = Path(__file__).resolve().parents[2] / "data" / "treatments.json"
MID = (2, 3)  # indices of 500 Hz and 1 kHz


class Treatment(BaseModel):
    id: str = Field(description="id from the treatment catalogue")
    where: str = Field(description="wall | floor | ceiling | window")
    area_m2: float = Field(gt=0)


@lru_cache
def catalogue() -> dict[str, dict]:
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    return {t["id"]: t for t in raw["treatments"]}


def _surface_totals(room: Room) -> dict[str, float]:
    walls = sum(room.surface_area("wall", i) for i in range(len(room.floor)))
    window = 0.0
    for s in room.surfaces:
        if s.kind == "wall" and s.material.startswith("glass"):
            window += room.surface_area("wall", s.wall_index)
        window += sum(p.area_m2 for p in s.patches if p.material.startswith("glass"))
    return {"wall": walls - window, "floor": room.floor_area(), "ceiling": room.floor_area(), "window": window}


def _covered_alpha(room: Room, where: str) -> list[float]:
    """Absorption of what a treatment would cover (most common material)."""
    if where == "window":
        return materials.get("glass_window").alpha
    kind = "wall" if where == "wall" else where
    mats = Counter(s.material for s in room.surfaces if s.kind == kind)
    if not mats:
        return [0.0] * len(OCTAVE_BANDS_HZ)
    return materials.get(mats.most_common(1)[0][0]).alpha


def baseline_absorption(room: Room, measured_rt: list[float | None]) -> list[float]:
    """Measured absorption area per band. Bands without a measurement use the
    model scaled by the median calibration factor of the measured ones."""
    V = room.volume()
    model = absorption_area(room)
    measured = [
        (0.161 * V / T - 4 * m * V) if T else None for T, m in zip(measured_rt, AIR_M)
    ]
    ratios = [a / b for a, b in zip(measured, model) if a and b > 0]
    k = median(ratios) if ratios else 1.0
    return [a if a is not None else b * k for a, b in zip(measured, model)]


def validate(room: Room, plan: list[Treatment], budget_eur: float | None = None) -> list[str]:
    cat = catalogue()
    totals = _surface_totals(room)
    errors = []
    used: Counter = Counter()
    for t in plan:
        c = cat.get(t.id)
        if c is None:
            errors.append(f"unknown treatment '{t.id}'")
            continue
        if t.where not in c["where"]:
            errors.append(f"'{t.id}' can't go on {t.where}; allowed: {', '.join(c['where'])}")
            continue
        used[t.where] += t.area_m2
        limit = c["max_m2_fraction"] * totals.get(t.where, 0.0)
        if t.where == "window":
            limit = totals["window"]
        if t.area_m2 > limit + 1e-6:
            errors.append(f"{t.area_m2} m² of '{t.id}' on {t.where} is more than the {limit:.1f} m² available")
    for where, area in used.items():
        if area > totals.get(where, 0.0) + 1e-6:
            errors.append(f"treatments on {where} add up to {area:.1f} m², more than its {totals[where]:.1f} m²")
    if budget_eur is not None and cost(plan) > budget_eur + 1e-6:
        errors.append(f"plan costs €{cost(plan):.0f}, over the €{budget_eur:.0f} budget")
    return errors


def cost(plan: list[Treatment]) -> float:
    cat = catalogue()
    return sum(cat[t.id]["eur_per_m2"] * t.area_m2 for t in plan if t.id in cat)


def predict(room: Room, measured_rt: list[float | None], plan: list[Treatment]) -> list[float]:
    V = room.volume()
    A = baseline_absorption(room, measured_rt)
    cat = catalogue()
    for t in plan:
        new = materials.get(cat[t.id]["material"]).alpha
        old = _covered_alpha(room, t.where)
        A = [a + t.area_m2 * (n - o) for a, n, o in zip(A, new, old)]
    return [0.161 * V / (max(a, 0.01) + 4 * m * V) for a, m in zip(A, AIR_M)]


def mid(rt: list[float]) -> float:
    return sum(rt[i] for i in MID) / len(MID)


def evaluate(room: Room, measured_rt: list[float | None], plan: list[Treatment],
             target_s: float, budget_eur: float) -> dict:
    """What the optimizer's tool returns for one proposed plan."""
    errors = validate(room, plan, budget_eur)
    if errors:
        return {"valid": False, "errors": errors}
    rt = predict(room, measured_rt, plan)
    m = mid(rt)
    return {
        "valid": True,
        "cost_eur": round(cost(plan)),
        "predicted_rt_s": {f"{b}Hz": round(t, 2) for b, t in zip(OCTAVE_BANDS_HZ, rt)},
        "predicted_mid_s": round(m, 2),
        "target_s": round(target_s, 2),
        "meets_target": abs(m / target_s - 1) <= 0.2,
    }


def greedy_plan(room: Room, measured_rt: list[float | None], target_s: float, budget_eur: float,
                step_m2: float = 1.0) -> list[Treatment]:
    """Deterministic fallback: add 1 m² at a time of whichever allowed
    treatment lowers mid RT most per euro, until the target or the budget."""
    plan: list[Treatment] = []
    for _ in range(200):
        now = mid(predict(room, measured_rt, plan))
        if now <= target_s * 1.2:
            break
        best, best_gain = None, 0.0
        for c in catalogue().values():
            for where in c["where"]:
                trial = _merge(plan, Treatment(id=c["id"], where=where, area_m2=step_m2))
                if validate(room, trial, budget_eur):
                    continue
                gain = (now - mid(predict(room, measured_rt, trial))) / (c["eur_per_m2"] * step_m2)
                if gain > best_gain:
                    best, best_gain = trial, gain
        if best is None:
            break
        plan = best
    return plan


def _merge(plan: list[Treatment], t: Treatment) -> list[Treatment]:
    out = [p.model_copy() for p in plan]
    for p in out:
        if p.id == t.id and p.where == t.where:
            p.area_m2 = round(p.area_m2 + t.area_m2, 2)
            return out
    return [*out, t]
