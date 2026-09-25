"""Clap recording → decay curves → reverberation parameters.

Day-one risk of the project: if RT from a hand clap on a phone mic isn't
within ~20 % of a reference by 10-10, switch to a swept-sine measurement.

Pipeline, per octave band:
    1. find the clap onset (energy rise), trim a little before it
    2. octave-band filter (IEC 61260-style Butterworth, zero-phase)
    3. estimate the noise floor from the tail; truncate where the decay meets it
       (Lundeby et al. 1995 is the standard method)
    4. Schroeder backward integration of the squared signal, in dB
    5. linear fit on the decay curve: EDT (0 to -10 dB), T20 (-5 to -25 dB),
       T30 (-5 to -35 dB) when the dynamic range allows
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..room import OCTAVE_BANDS_HZ


@dataclass
class BandDecay:
    band_hz: int
    edt_s: float | None
    t20_s: float | None
    t30_s: float | None
    dynamic_range_db: float  # usable decay range above the noise floor


def find_onset(x: np.ndarray, fs: int) -> int:
    """Sample index where the clap starts."""
    raise NotImplementedError


def octave_filter(x: np.ndarray, fs: int, band_hz: int) -> np.ndarray:
    """Zero-phase octave-band filter centred on band_hz."""
    raise NotImplementedError


def schroeder_db(x: np.ndarray, fs: int) -> np.ndarray:
    """Backward-integrated energy decay curve in dB, 0 dB at t = 0."""
    raise NotImplementedError


def fit_rt(edc_db: np.ndarray, fs: int, start_db: float, stop_db: float) -> float | None:
    """Reverberation time extrapolated to -60 dB from a linear fit between
    start_db and stop_db. None if the curve doesn't reach stop_db."""
    raise NotImplementedError


def analyze(x: np.ndarray, fs: int, bands: tuple[int, ...] = OCTAVE_BANDS_HZ) -> list[BandDecay]:
    """Full pipeline for one clap recording."""
    raise NotImplementedError
