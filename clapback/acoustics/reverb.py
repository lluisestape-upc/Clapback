"""Statistical reverberation model and its calibration against measurement.

    Sabine:  T = 0.161 V / A,           A = Σ S_i α_i  (+ 4 m V air absorption)
    Eyring:  T = 0.161 V / (-S ln(1 - ᾱ))

Use Eyring when ᾱ is high (roughly > 0.2); Sabine overestimates T there.

Calibration: the materials chosen by the intake agent give a predicted T per
band. The claps give a measured T. Scale the uncertain surfaces' absorption
(not the whole room uniformly) until prediction matches measurement, and
report how much each one had to move; a large correction means the material
guess is probably wrong. The planner agent uses that to ask for more claps.
"""

from __future__ import annotations

from ..room import Room


def absorption_area(room: Room) -> list[float]:
    """Equivalent absorption area A (m² Sabine) per octave band."""
    raise NotImplementedError


def sabine(room: Room) -> list[float]:
    """Predicted RT per octave band (s)."""
    raise NotImplementedError


def eyring(room: Room) -> list[float]:
    raise NotImplementedError


def calibrate(room: Room, measured_rt: list[float | None]) -> dict:
    """Fit per-surface absorption corrections to measured RT.

    Returns the corrected coefficients per surface and the size of each
    correction, so the report can flag unreliable material guesses.
    """
    raise NotImplementedError
