"""Targets for the engine. Each test is expected to fail with
NotImplementedError until its function exists; strict=True makes pytest
complain once it passes, so the marker gets removed."""

import numpy as np
import pytest

from clapback.acoustics import decay, modes

todo = pytest.mark.xfail(raises=NotImplementedError, strict=True, reason="not implemented yet")


def synthetic_clap(rt: float, fs: int = 48000, seconds: float = 3.0, noise_db: float = -70.0):
    """Exponentially decaying noise with a known RT, plus a noise floor."""
    rng = np.random.default_rng(0)
    t = np.arange(int(fs * seconds)) / fs
    env = 10 ** (-3 * t / rt)  # -60 dB at t = rt
    x = rng.standard_normal(t.size) * env
    x += rng.standard_normal(t.size) * 10 ** (noise_db / 20)
    pre = np.zeros(int(0.2 * fs))
    return np.concatenate([pre, x]), fs


@todo
def test_t20_recovers_known_rt():
    x, fs = synthetic_clap(rt=0.8)
    bands = {b.band_hz: b for b in decay.analyze(x, fs)}
    assert bands[1000].t20_s == pytest.approx(0.8, rel=0.05)


@todo
def test_axial_modes_of_a_box():
    ms = modes.room_modes(5.0, 4.0, 2.5, f_max=100)
    axial_x = [m.freq_hz for m in ms if m.n == (1, 0, 0)]
    assert axial_x[0] == pytest.approx(343 / (2 * 5.0), rel=1e-3)


@todo
def test_schroeder_frequency():
    assert modes.schroeder_frequency(0.5, 50) == pytest.approx(2000 * (0.5 / 50) ** 0.5)
