"""Sweep measurement: synthetic rooms with known answers."""

import numpy as np
import pytest
from scipy import signal

from clapback.acoustics import decay, sweep

FS = 48000


def record(room_ir, fs=FS, lead_s=0.7, tail_s=3.0, noise_db=-70.0, player=None, seed=0):
    """What the phone would record: silence, the sweep through the room, silence."""
    rng = np.random.default_rng(seed)
    x = player if player is not None else sweep.ess(fs)
    y = signal.fftconvolve(x, room_ir)
    rec = np.concatenate([np.zeros(int(lead_s * fs)), y, np.zeros(int(tail_s * fs))])
    return rec + rng.standard_normal(rec.size) * 10 ** (noise_db / 20)


def room(rt, fs=FS, seconds=2.5, seed=1):
    """Direct sound plus exponentially decaying noise with a known RT."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * fs)) / fs
    h = 0.3 * rng.standard_normal(t.size) * 10 ** (-3 * t / rt)
    h[0] += 1.0
    return h


def test_a_bare_delta_comes_back_where_the_sweep_started():
    ir, info = sweep.deconvolve(record(np.array([1.0])), FS)
    assert info["start_s"] == pytest.approx(0.7, abs=0.002)
    assert int(np.argmax(np.abs(ir))) == pytest.approx(0.005 * FS, abs=2)


@pytest.mark.parametrize("rt", [0.4, 0.9])
def test_rt_from_a_sweep_matches_the_room(rt):
    ir, _ = sweep.deconvolve(record(room(rt)), FS)
    bands = {b.band_hz: b for b in decay.analyze(ir, FS)}
    for f in (500, 1000, 2000):
        assert bands[f].t30_s == pytest.approx(rt, rel=0.10), bands[f]


def test_response_of_a_delta_is_flat():
    ir, _ = sweep.deconvolve(record(np.array([1.0])), FS)
    r = sweep.response(ir, FS)
    db = np.array(r["db"])
    f = np.array(r["f_hz"])
    assert np.all(np.abs(db[(f > 100) & (f < 10000)]) < 1.0)


def test_player_at_another_sample_rate_still_works():
    at_44k = sweep.ess(44100)
    heard_at_48k = signal.resample_poly(at_44k, 160, 147)
    ir, _ = sweep.deconvolve(record(room(0.6), player=heard_at_48k), FS)
    b = {b.band_hz: b for b in decay.analyze(ir, FS)}[1000]
    assert b.rt_s == pytest.approx(0.6, rel=0.10)


def test_noise_is_not_a_sweep():
    rng = np.random.default_rng(3)
    with pytest.raises(sweep.NoSweep):
        sweep.deconvolve(rng.standard_normal(FS * 10) * 0.01, FS)


def test_a_cut_off_sweep_is_rejected():
    rec = record(room(0.6))[: int((0.7 + sweep.SECONDS + 0.3) * FS)]  # stopped 0.3 s after
    with pytest.raises(sweep.NoSweep):
        sweep.deconvolve(rec, FS)
    late_start = record(room(0.6))[int(1.5 * FS):]      # recording began mid-sweep
    with pytest.raises(sweep.NoSweep):
        sweep.deconvolve(late_start, FS)


def test_wav_export_is_readable():
    import base64
    import io

    import soundfile as sf

    ir, _ = sweep.deconvolve(record(room(0.5)), FS)
    x, fs = sf.read(io.BytesIO(base64.b64decode(sweep.wav_base64(ir, FS))))
    assert fs == FS and 0.8 < np.max(np.abs(x)) <= 0.91
