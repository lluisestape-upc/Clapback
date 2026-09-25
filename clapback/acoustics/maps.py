"""Spatial maps over the floor plane (listener height ~1.2 m).

RT is nearly constant across a diffuse room, so it is shown as a per-band
curve, not a map. What does change with position, and what these maps show:

- C50 and a speech STI estimate from Barron's revised theory
  (direct + early + late energy as a function of source distance, V and T).
- Modal pressure at a chosen low frequency (below the Schroeder frequency):
  sum of cos(nx π x/Lx) cos(ny π y/Ly) cos(nz π z/Lz) terms weighted by
  each mode's response at that frequency. Rectangular rooms only.

Output format: a grid the web app can colour directly.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..room import Room


@dataclass
class Grid:
    xs: list[float]
    ys: list[float]
    values: list[list[float]]  # values[j][i] at (xs[i], ys[j])
    unit: str


def clarity_map(room: Room, band_hz: int = 1000, step_m: float = 0.25) -> Grid:
    """C50 in dB over the floor, for room.source."""
    raise NotImplementedError


def sti_map(room: Room, step_m: float = 0.25) -> Grid:
    """Rough STI estimate over the floor. Label it as an estimate in the UI."""
    raise NotImplementedError


def modal_pressure_map(room: Room, freq_hz: float, step_m: float = 0.25) -> Grid:
    """Relative SPL (dB) at freq_hz over the floor, for room.source."""
    raise NotImplementedError
