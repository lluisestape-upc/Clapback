"""Clap recording → decay curves → reverberation parameters.

Day-one risk of the project: if RT from a hand clap on a phone mic isn't
within ~20 % of a reference by 10-10, switch to a swept-sine measurement.

Pipeline, per octave band:
    1. find the clap onset (energy rise), trim a little before it
    2. octave-band filter (Butterworth band-pass, zero-phase)
    3. estimate the noise floor from the tail and find where the decay meets
       it (a simplified Lundeby et al. 1995 iteration), truncate there and
       add the energy the truncated exponential tail would have had
    4. Schroeder backward integration of the squared signal, in dB
    5. linear fit on the decay curve: EDT (0 to -10 dB), T20 (-5 to -25 dB),
       T30 (-5 to -35 dB), each only if the dynamic range allows it
    6. ISO 3382-1 energy ratios from the same curve: C50, C80 (clarity) and
       D50 (definition), with t = 0 at the direct sound

analyze_full() also returns what the results screen plots: the decay curve
per band, the broadband energy-time curve and a spectrogram of the decay.
The same pipeline runs on a clap and on an impulse response from a sweep.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from scipy import signal

from ..room import OCTAVE_BANDS_HZ

FRAME_S = 0.01  # envelope frame for onset and noise estimation

# A fit is only trusted if the decay is close to a straight line (r²) and
# the result is physically plausible for a room.
MIN_R2 = 0.95
RT_RANGE_S = (0.05, 5.0)

# Dynamic range (peak above noise, dB) needed for each fit: the fit range
# plus a 10 dB margin above the noise, as ISO 3382-2 recommends.
MIN_RANGE_DB = {"edt": 20.0, "t20": 35.0, "t30": 45.0}


@dataclass
class BandDecay:
    band_hz: int
    edt_s: float | None
    t20_s: float | None
    t30_s: float | None
    dynamic_range_db: float  # usable decay range above the noise floor
    c50_db: float | None = None
    c80_db: float | None = None
    d50: float | None = None

    @property
    def rt_s(self) -> float | None:
        """Best available estimate: T30, then T20, then EDT."""
        return self.t30_s or self.t20_s or self.edt_s

    def to_dict(self) -> dict:
        return {**asdict(self), "rt_s": self.rt_s}


def _frames_db(x: np.ndarray, fs: int, frame_s: float = FRAME_S) -> np.ndarray:
    hop = max(1, int(fs * frame_s))
    n = len(x) // hop
    p = np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1)
    return 10 * np.log10(p + 1e-20)


ONSET_BACK_FRAMES = 3  # a clap rises to its peak within ~30 ms


def find_onset(x: np.ndarray, fs: int) -> int:
    """Sample index where the clap starts.

    The rise into the loudest 10 ms frame, minus one frame of safety. Taking
    the loudest event (not the first loud one) keeps talking or a knock
    before the clap from being analysed as the clap.
    """
    db = _frames_db(x, fs)
    if db.size == 0:
        return 0
    p = int(np.argmax(db))
    i = p
    while i > max(0, p - ONSET_BACK_FRAMES) and db[i - 1] >= db[p] - 20:
        i -= 1
    hop = int(fs * FRAME_S)
    return max(0, (i - 1) * hop)


def octave_filter(x: np.ndarray, fs: int, band_hz: int) -> np.ndarray:
    """Zero-phase octave-band filter centred on band_hz."""
    lo = band_hz / np.sqrt(2)
    hi = min(band_hz * np.sqrt(2), 0.45 * fs)
    sos = signal.butter(3, [lo, hi], btype="bandpass", fs=fs, output="sos")
    return signal.sosfiltfilt(sos, x)


def _noise_crosspoint(h2: np.ndarray, fs: int) -> tuple[int, float, float]:
    """Simplified Lundeby: where the decay meets the noise floor.

    Returns (crosspoint sample, noise power, decay slope in dB/s).
    """
    hop = max(1, int(fs * FRAME_S))
    n = len(h2) // hop
    env = np.mean(h2[: n * hop].reshape(n, hop), axis=1)
    env_db = 10 * np.log10(env + 1e-20)
    t = (np.arange(n) + 0.5) * hop / fs

    noise = np.mean(env[int(n * 0.9):]) if n >= 10 else env.min()
    noise_db = 10 * np.log10(noise + 1e-20)
    start = int(np.argmax(env_db))
    cross = n - 1
    slope = -60.0  # dB/s, placeholder until the first fit

    for _ in range(5):
        # fit from the peak down to 10 dB above the noise
        stop_idx = np.nonzero(env_db[start:cross] < noise_db + 10)[0]
        stop = start + (stop_idx[0] if stop_idx.size else cross - start)
        if stop - start < 3:
            break
        slope, icpt = np.polyfit(t[start:stop], env_db[start:stop], 1)
        if slope >= 0:
            break
        new_cross = int(np.clip((noise_db - icpt) / slope / (hop / fs), start + 1, n - 1))
        # re-estimate the noise from what lies well after the crosspoint
        tail_from = new_cross + int(abs(10 / slope) / (hop / fs))
        if tail_from < n - 2:
            noise = np.mean(env[tail_from:])
            noise_db = 10 * np.log10(noise + 1e-20)
        if new_cross == cross:
            break
        cross = new_cross

    return min(len(h2), cross * hop), float(noise), float(slope)


def schroeder_db(x: np.ndarray, fs: int) -> tuple[np.ndarray, float]:
    """Backward-integrated energy decay curve in dB (0 dB at t = 0), and the
    dynamic range in dB between the peak and the noise floor."""
    h2 = x.astype(np.float64) ** 2
    cross, noise, slope = _noise_crosspoint(h2, fs)
    peak = np.max(h2[: max(cross, 1)])
    hop = max(1, int(fs * FRAME_S))
    peak_env = np.max(np.convolve(h2, np.ones(hop) / hop, mode="valid")) if len(h2) > hop else peak
    range_db = 10 * np.log10(peak_env / (noise + 1e-20))

    h2 = h2[:cross]
    # energy of the exponential tail cut off at the crosspoint
    tail = 0.0
    if slope < 0 and cross > hop:
        p_c = np.mean(h2[-hop:])
        tau = 10 / (abs(slope) * np.log(10))  # power decay time constant, s
        tail = p_c * tau * fs
    edc = np.cumsum(h2[::-1])[::-1] + tail
    edc_db = 10 * np.log10(edc / edc[0] + 1e-30)
    return edc_db, float(range_db)


def fit_rt(edc_db: np.ndarray, fs: int, start_db: float, stop_db: float) -> float | None:
    """Reverberation time extrapolated to -60 dB from a linear fit between
    start_db and stop_db. None if the curve doesn't reach stop_db."""
    below_start = np.nonzero(edc_db <= start_db)[0]
    below_stop = np.nonzero(edc_db <= stop_db)[0]
    if below_start.size == 0 or below_stop.size == 0:
        return None
    i0, i1 = below_start[0], below_stop[0]
    if i1 - i0 < 3:
        return None
    t = np.arange(i0, i1) / fs
    seg = edc_db[i0:i1]
    slope, icpt = np.polyfit(t, seg, 1)
    if slope >= 0:
        return None
    resid = seg - (slope * t + icpt)
    r2 = 1 - np.sum(resid**2) / np.sum((seg - seg.mean()) ** 2)
    rt = float(-60.0 / slope)
    if r2 < MIN_R2 or not RT_RANGE_S[0] <= rt <= RT_RANGE_S[1]:
        return None
    return rt


def direct_index(x: np.ndarray) -> int:
    """Start of the impulse (ISO 3382-1): first sample within 20 dB of the peak."""
    a = np.abs(x)
    return int(np.argmax(a >= 0.1 * a.max())) if a.size and a.max() > 0 else 0


def clarity(edc_db: np.ndarray, fs: int, i0: int, ms: float) -> tuple[float, float] | None:
    """(C in dB, early fraction) for an early window of `ms` after the direct
    sound at i0. The curve is normalised to the total energy, so its value at
    t0 + ms is the late fraction."""
    i = i0 + int(fs * ms / 1000)
    if i >= len(edc_db):
        return None
    late = 10 ** (edc_db[i] / 10)
    if not 0 < late < 1:
        return None
    c = float(10 * np.log10((1 - late) / late))
    # beyond ±30 dB there's no reverberant tail (or no direct sound) to compare
    return (c, float(1 - late)) if abs(c) <= 30 else None


def _prepare(x: np.ndarray, fs: int) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    if x.ndim > 1:
        x = x.mean(axis=1)
    x = x - np.mean(x)
    return x[find_onset(x, fs):]


def _band(y: np.ndarray, fs: int, band: int, i0: int) -> tuple[BandDecay, np.ndarray]:
    edc, rng = schroeder_db(y, fs)
    c50 = clarity(edc, fs, i0, 50) if rng >= MIN_RANGE_DB["edt"] else None
    c80 = clarity(edc, fs, i0, 80) if rng >= MIN_RANGE_DB["edt"] else None
    return BandDecay(
        band_hz=band,
        edt_s=fit_rt(edc, fs, 0.0, -10.0) if rng >= MIN_RANGE_DB["edt"] else None,
        t20_s=fit_rt(edc, fs, -5.0, -25.0) if rng >= MIN_RANGE_DB["t20"] else None,
        t30_s=fit_rt(edc, fs, -5.0, -35.0) if rng >= MIN_RANGE_DB["t30"] else None,
        dynamic_range_db=round(rng, 1),
        c50_db=round(c50[0], 1) if c50 else None,
        c80_db=round(c80[0], 1) if c80 else None,
        d50=round(c50[1], 2) if c50 else None,
    ), edc


def analyze(x: np.ndarray, fs: int, bands: tuple[int, ...] = OCTAVE_BANDS_HZ) -> list[BandDecay]:
    """Full pipeline for one clap recording (or impulse response)."""
    return analyze_full(x, fs, bands)[0]


PLOT_STEP_S = 0.005
PLOT_FLOOR_DB = -70.0


def analyze_full(x: np.ndarray, fs: int, bands: tuple[int, ...] = OCTAVE_BANDS_HZ) -> tuple[list[BandDecay], dict]:
    """Band results plus the curves the results screen draws."""
    x = _prepare(x, fs)
    i0 = direct_index(x)
    step = max(1, int(fs * PLOT_STEP_S))

    out, curves = [], {}
    for band in bands:
        if band * np.sqrt(2) >= fs / 2:
            continue
        b, edc = _band(octave_filter(x, fs, band), fs, band, i0)
        out.append(b)
        seg = edc[i0::step]
        cut = np.nonzero(seg < PLOT_FLOOR_DB)[0]
        seg = seg[: cut[0] if cut.size else len(seg)]
        curves[str(band)] = [round(float(v), 1) for v in seg]

    mids = [b.rt_s for b in out if b.band_hz in (500, 1000) and b.rt_s]
    rt_mid = sum(mids) / len(mids) if mids else None
    detail = {
        "edc": {"dt_s": step / fs, "db": curves},
        "etc": energy_time(x, fs, i0),
        "spectrogram": spectrogram(x, fs, i0, seconds=float(np.clip(1.5 * (rt_mid or 1.0), 0.6, 3.0))),
    }
    return out, detail


def energy_time(x: np.ndarray, fs: int, i0: int, frame_s: float = 0.002, seconds: float = 1.5) -> dict:
    """Broadband energy-time curve in dB re its peak, from 10 ms before the
    direct sound. Early reflections show up as spikes after t = 0."""
    hop = max(1, int(fs * frame_s))
    start = max(0, i0 - int(0.01 * fs))
    seg = x[start: i0 + int(seconds * fs)]
    n = len(seg) // hop
    if n == 0:
        return {"dt_s": frame_s, "t0_s": 0.0, "db": []}
    p = np.max(seg[: n * hop].reshape(n, hop) ** 2, axis=1)
    db = np.maximum(10 * np.log10(p / (p.max() + 1e-30) + 1e-30), PLOT_FLOOR_DB - 20)
    return {"dt_s": hop / fs, "t0_s": round((start - i0) / fs, 4), "db": [round(float(v), 1) for v in db]}


SPEC_F_LO, SPEC_F_HI, SPEC_PER_OCT = 50.0, 10000.0, 6
SPEC_RANGE_DB = 80.0


def spectrogram(x: np.ndarray, fs: int, i0: int, seconds: float = 1.5) -> dict:
    """Decay spectrogram on a 1/6-octave frequency axis, 10 ms frames.

    Levels are dB re the loudest cell, mapped to 0..255 over the bottom
    80 dB so the JSON stays small.
    """
    start = max(0, i0 - int(0.05 * fs))
    seg = x[start: i0 + int(seconds * fs)]
    nper = 2048 if fs > 32000 else 1024
    hop = max(1, int(fs * 0.01))
    if len(seg) < nper:
        return {"f_hz": [], "t0_s": 0.0, "dt_s": 0.01, "level": []}
    f, _, z = signal.stft(seg, fs, window="hann", nperseg=nper, noverlap=nper - hop,
                          boundary=None, padded=False)
    power = np.abs(z) ** 2
    hi = min(SPEC_F_HI, 0.45 * fs)
    n_bands = int(np.floor(SPEC_PER_OCT * np.log2(hi / SPEC_F_LO))) + 1
    centres = SPEC_F_LO * 2 ** (np.arange(n_bands) / SPEC_PER_OCT)
    half = 2 ** (1 / (2 * SPEC_PER_OCT))
    rows = []
    for fc in centres:
        sel = (f >= fc / half) & (f < fc * half)
        rows.append(power[sel].mean(axis=0) if sel.any() else power[np.argmin(np.abs(f - fc))])
    db = 10 * np.log10(np.array(rows) + 1e-30)
    db -= db.max()
    level = np.clip((db + SPEC_RANGE_DB) / SPEC_RANGE_DB * 255, 0, 255).astype(int)
    return {
        "f_hz": [round(float(c), 1) for c in centres],
        "t0_s": round((start - i0) / fs + nper / 2 / fs, 4),
        "dt_s": hop / fs,
        "range_db": SPEC_RANGE_DB,
        "level": level.T.tolist(),   # one row per time frame
    }
