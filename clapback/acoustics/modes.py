"""Room modes and the frequency limit of statistical acoustics.

Rectangular rooms only (Room.is_rectangular()). For other shapes, say so in
the report rather than pretending.

    f(nx, ny, nz) = c/2 * sqrt((nx/Lx)^2 + (ny/Ly)^2 + (nz/Lz)^2)

axial: one index non-zero; tangential: two; oblique: three.
Schroeder frequency: f_s ≈ 2000 * sqrt(T / V), with T in s and V in m³.
Below f_s, maps should use modal pressure, not diffuse-field theory.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

SPEED_OF_SOUND = 343.0  # m/s at ~20 °C

KINDS = {1: "axial", 2: "tangential", 3: "oblique"}


@dataclass
class Mode:
    n: tuple[int, int, int]
    freq_hz: float
    kind: Literal["axial", "tangential", "oblique"]


def room_modes(lx: float, ly: float, lz: float, f_max: float = 300.0) -> list[Mode]:
    """All modes up to f_max, sorted by frequency."""
    c = SPEED_OF_SOUND
    nmax = [int(2 * f_max * L / c) + 1 for L in (lx, ly, lz)]
    out = []
    for nx in range(nmax[0] + 1):
        for ny in range(nmax[1] + 1):
            for nz in range(nmax[2] + 1):
                if nx == ny == nz == 0:
                    continue
                f = c / 2 * math.sqrt((nx / lx) ** 2 + (ny / ly) ** 2 + (nz / lz) ** 2)
                if f <= f_max:
                    k = sum(1 for n in (nx, ny, nz) if n)
                    out.append(Mode((nx, ny, nz), f, KINDS[k]))
    return sorted(out, key=lambda m: m.freq_hz)


def schroeder_frequency(rt_s: float, volume_m3: float) -> float:
    return 2000.0 * math.sqrt(rt_s / volume_m3)


def problem_frequencies(modes: list[Mode], below_hz: float, cluster_hz: float = 5.0) -> list[dict]:
    """Axial modes below `below_hz`, grouped when they fall within cluster_hz
    of each other. Stacked or isolated axial modes are what people hear as
    boomy notes. Returns [{"freq_hz", "count", "axes"}] sorted by frequency."""
    axial = [m for m in modes if m.kind == "axial" and m.freq_hz < below_hz]
    groups: list[list[Mode]] = []
    for m in axial:
        if groups and m.freq_hz - groups[-1][-1].freq_hz <= cluster_hz:
            groups[-1].append(m)
        else:
            groups.append([m])
    out = []
    for g in groups:
        axes = sorted({"xyz"[[i for i, n in enumerate(m.n) if n][0]] for m in g})
        out.append({
            "freq_hz": round(sum(m.freq_hz for m in g) / len(g), 1),
            "count": len(g),
            "axes": axes,
        })
    return out
