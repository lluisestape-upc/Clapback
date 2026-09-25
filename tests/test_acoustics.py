import numpy as np
import pytest

from clapback import targets
from clapback.acoustics import decay, modes, reverb
from clapback.room import Room


def synthetic_clap(rt: float, fs: int = 48000, seconds: float = 4.0, noise_db: float = -70.0, seed: int = 0):
    """Exponentially decaying noise with a known RT, plus a noise floor and
    half a second of background before the clap."""
    rng = np.random.default_rng(seed)
    t = np.arange(int(fs * seconds)) / fs
    x = rng.standard_normal(t.size) * 10 ** (-3 * t / rt)
    x += rng.standard_normal(t.size) * 10 ** (noise_db / 20)
    pre = rng.standard_normal(int(0.5 * fs)) * 10 ** (noise_db / 20)
    return np.concatenate([pre, x]), fs


@pytest.mark.parametrize("rt", [0.3, 0.6, 1.2])
def test_t20_recovers_known_rt_in_mid_and_high_bands(rt):
    x, fs = synthetic_clap(rt)
    for b in decay.analyze(x, fs):
        if b.band_hz >= 1000:
            assert b.t20_s == pytest.approx(rt, rel=0.10), b


def test_noisy_clap_drops_t30_but_keeps_t20():
    x, fs = synthetic_clap(0.6, noise_db=-40)
    b = {d.band_hz: d for d in decay.analyze(x, fs)}[1000]
    assert b.t30_s is None
    assert b.t20_s == pytest.approx(0.6, rel=0.10)


def test_no_clap_gives_no_rt():
    rng = np.random.default_rng(1)
    x = rng.standard_normal(48000 * 3) * 1e-3
    assert all(b.rt_s is None for b in decay.analyze(x, 48000))


def test_onset_is_found():
    x, fs = synthetic_clap(0.5)
    assert decay.find_onset(x, fs) == pytest.approx(0.5 * fs, abs=0.02 * fs)


def test_axial_modes_of_a_box():
    ms = modes.room_modes(5.0, 4.0, 2.5, f_max=100)
    first_x = next(m for m in ms if m.n == (1, 0, 0))
    assert first_x.freq_hz == pytest.approx(343 / (2 * 5.0), rel=1e-3)
    assert first_x.kind == "axial"
    assert [m.freq_hz for m in ms] == sorted(m.freq_hz for m in ms)


def test_schroeder_frequency():
    assert modes.schroeder_frequency(0.5, 50) == pytest.approx(2000 * (0.5 / 50) ** 0.5)


def _room(floor="wood_floor_on_joists"):
    surfaces = [
        {"kind": "floor", "material": floor},
        {"kind": "ceiling", "material": "plaster_on_masonry"},
        *({"kind": "wall", "wall_index": i, "material": "plaster_on_masonry"} for i in range(4)),
    ]
    return Room.box(5, 4, 2.5, surfaces=surfaces)


def test_sabine_by_hand():
    room = _room()
    # 1 kHz: floor 20·0.07 + ceiling 20·0.03 + walls 45·0.03, plus air
    A = 20 * 0.07 + 20 * 0.03 + 45 * 0.03
    expected = 0.161 * 50 / (A + 4 * 0.00115 * 50)
    assert reverb.sabine(room)[3] == pytest.approx(expected)


def test_carpet_shortens_rt():
    assert reverb.sabine(_room("carpet_on_pad"))[3] < reverb.sabine(_room())[3]


def test_calibration_factor_is_one_when_model_matches():
    room = _room()
    cal = reverb.calibrate(room, reverb.sabine(room))
    assert all(f == pytest.approx(1.0, abs=0.01) for f in cal["absorption_factor"])


def test_targets_and_verdicts():
    assert targets.target_rt("study", 100) == pytest.approx(0.32 * 2 - 0.17)
    assert targets.verdict("voice", 50, 0.9)["level"] == "too_live"
    assert targets.verdict("voice", 50, 0.3)["level"] == "good"
    assert targets.verdict("voice", 50, 0.1)["level"] == "too_dead"
    assert targets.verdict("voice", 50, None)["level"] == "unknown"


def test_furniture_shortens_rt():
    empty, full = _room(), _room()
    full.furnishing = "full"
    assert reverb.sabine(full)[3] < 0.5 * reverb.sabine(empty)[3]


def test_implausible_fit_is_rejected():
    fs = 48000
    flat = np.full(fs, -3.0)  # a "decay" that never decays
    flat[0] = 0.0
    flat[-1] = -40.0
    assert decay.fit_rt(flat, fs, -5.0, -25.0) is None
