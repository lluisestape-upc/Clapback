"""Room modes and the frequency limit of statistical acoustics.

Rectangular rooms only (Room.is_rectangular()). For other shapes, say so in
the report rather than pretending.

    f(nx, ny, nz) = c/2 * sqrt((nx/Lx)^2 + (ny/Ly)^2 + (nz/Lz)^2)

axial: one index non-zero; tangential: two; oblique: three.
Schroeder frequency: f_s ≈ 2000 * sqrt(T / V), with T in s and V in m³.
Below f_s, maps should use modal pressure, not diffuse-field theory.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SPEED_OF_SOUND = 343.0  # m/s at ~20 °C


@dataclass
class Mode:
    n: tuple[int, int, int]
    freq_hz: float
    kind: Literal["axial", "tangential", "oblique"]


def room_modes(lx: float, ly: float, lz: float, f_max: float = 300.0) -> list[Mode]:
    """All modes up to f_max, sorted by frequency."""
    raise NotImplementedError


def schroeder_frequency(rt_s: float, volume_m3: float) -> float:
    raise NotImplementedError
