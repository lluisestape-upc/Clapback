"""Statistical reverberation model and its calibration against measurement.

    Sabine:  T = 0.161 V / (A + 4 m V),      A = Σ S_i α_i
    Eyring:  T = 0.161 V / (-S ln(1 - ᾱ) + 4 m V)

Use Eyring when ᾱ is high (roughly > 0.2); Sabine overestimates T there.

Calibration: the materials picked from the user's answers give a predicted
T per band; the claps give a measured T. `calibrate` returns, per band, the
factor the absorption must be scaled by for prediction to match. A factor
far from 1 means the material guess is probably wrong (or there's
furniture the model doesn't know about), which is what the planner agent
will use to ask for more claps. Per-surface calibration is the next step.
"""

from __future__ import annotations

import math

from .. import materials
from ..room import OCTAVE_BANDS_HZ, Room

# Air attenuation coefficient m (1/m, energy) at ~20 °C, 50 % RH, per band.
# Converted from ISO 9613-1 attenuation in dB/km (m = α / 4343).
AIR_M = (0.0001, 0.00023, 0.00044, 0.00115, 0.0021, 0.0053)


# Furniture, bed, clothes, shelves: extra absorption area per m² of floor,
# per band. Rough estimates, not table values: they give the model a
# sensible starting point and calibration corrects them.
FURNISHING = {
    "empty": (0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    "some": (0.05, 0.10, 0.15, 0.20, 0.20, 0.20),
    "full": (0.10, 0.25, 0.40, 0.50, 0.50, 0.50),
}


def _surface_items(room: Room) -> list[tuple[float, list[float]]]:
    """(area, alpha per band) for every surface and patch in the room."""
    items = []
    for s in room.surfaces:
        area = room.surface_area(s.kind, s.wall_index)
        patch_area = sum(p.area_m2 for p in s.patches)
        base = max(0.0, area - patch_area)
        items.append((base, materials.get(s.material).alpha))
        for p in s.patches:
            items.append((min(p.area_m2, area), materials.get(p.material).alpha))
    for e in room.extras:
        items.append((e.area_m2, materials.get(e.material).alpha))
    return items


def absorption_area(room: Room) -> list[float]:
    """Equivalent absorption area A (m² Sabine) per octave band, surfaces only."""
    items = _surface_items(room)
    furn = FURNISHING.get(room.furnishing or "empty")
    floor = room.floor_area()
    return [sum(S * a[b] for S, a in items) + furn[b] * floor for b in range(len(OCTAVE_BANDS_HZ))]


def mean_alpha(room: Room) -> list[float]:
    total = room.total_area()
    return [A / total for A in absorption_area(room)]


def sabine(room: Room) -> list[float]:
    """Predicted RT per octave band (s)."""
    V = room.volume()
    return [0.161 * V / (A + 4 * m * V) for A, m in zip(absorption_area(room), AIR_M)]


def eyring(room: Room) -> list[float]:
    V, S = room.volume(), room.total_area()
    out = []
    for a, m in zip(mean_alpha(room), AIR_M):
        a = min(a, 0.99)
        out.append(0.161 * V / (-S * math.log(1 - a) + 4 * m * V))
    return out


def predicted(room: Room) -> list[float]:
    """Eyring when the room is fairly absorbent, Sabine otherwise."""
    return eyring(room) if max(mean_alpha(room)) > 0.2 else sabine(room)


def calibrate(room: Room, measured_rt: list[float | None]) -> dict:
    """Per band: how much the modelled absorption must be scaled to match
    the measured RT (Sabine form, air absorption kept fixed)."""
    V = room.volume()
    A_model = absorption_area(room)
    factors: list[float | None] = []
    for A, m, T in zip(A_model, AIR_M, measured_rt):
        if not T or A <= 0:
            factors.append(None)
            continue
        A_needed = max(0.0, 0.161 * V / T - 4 * m * V)
        factors.append(round(A_needed / A, 2))
    return {
        "bands_hz": list(OCTAVE_BANDS_HZ),
        "absorption_factor": factors,
        "predicted_rt": [round(t, 2) for t in predicted(room)],
    }
