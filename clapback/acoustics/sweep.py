"""Exponential sine sweep (Farina, AES 2000): the signal, its deconvolution
into an impulse response, and the frequency response at the mic.

A sweep measures what a clap can't: it puts known energy into every
frequency, the deconvolution gains tens of dB of signal-to-noise, and
harmonic distortion from the speaker lands before the linear impulse
response, where it is cut away.

The sweep is defined in continuous time, so the server rebuilds exactly the
same signal at the recorder's sample rate, even when the player (a laptop
running speaker.html) ran at another rate. Where the sweep starts in the
recording doesn't matter; the deconvolution finds it. web/sweep.js
generates the same signal and must stay in step with ess() below.
"""

from __future__ import annotations

import base64
import io

import numpy as np
import soundfile as sf
from scipy import signal

F1_HZ, F2_HZ, SECONDS = 40.0, 16000.0, 6.0
FADE_IN_S, FADE_OUT_S = 0.05, 0.01
AMPLITUDE = 0.5            # -6 dBFS, headroom for small speakers

MIN_PEAK_DB = 30.0         # linear IR peak above the median of the deconvolved signal
MIN_TAIL_S = 0.8           # recording must go on this long after the sweep ends
IR_SECONDS = 3.0


class NoSweep(ValueError):
    """The recording doesn't contain one whole sweep."""


def ess(fs: int, f1: float = F1_HZ, f2: float = F2_HZ, seconds: float = SECONDS) -> np.ndarray:
    """x(t) = sin(2π f1 L (e^(t/L) − 1)), L = T / ln(f2/f1), with short fades."""
    n = int(round(seconds * fs))
    t = np.arange(n) / fs
    L = seconds / np.log(f2 / f1)
    x = AMPLITUDE * np.sin(2 * np.pi * f1 * L * (np.exp(t / L) - 1))
    ni, no = int(FADE_IN_S * fs), int(FADE_OUT_S * fs)
    x[:ni] *= 0.5 - 0.5 * np.cos(np.pi * np.arange(ni) / ni)
    x[n - no:] *= 0.5 + 0.5 * np.cos(np.pi * np.arange(no) / no)
    return x


def inverse_filter(fs: int, f1: float = F1_HZ, f2: float = F2_HZ, seconds: float = SECONDS) -> np.ndarray:
    """Time-reversed sweep with a 6 dB/octave tilt that undoes the sweep's
    pink spectrum, scaled so sweep ∗ inverse peaks at 1."""
    x = ess(fs, f1, f2, seconds)
    L = seconds / np.log(f2 / f1)
    inv = x[::-1] * np.exp(-np.arange(len(x)) / fs / L)
    return inv / np.max(np.abs(signal.fftconvolve(x, inv)))


def deconvolve(rec: np.ndarray, fs: int, f1: float = F1_HZ, f2: float = F2_HZ,
               seconds: float = SECONDS) -> tuple[np.ndarray, dict]:
    """Recording → impulse response starting 5 ms before the direct sound."""
    inv = inverse_filter(fs, f1, f2, seconds)
    h = signal.fftconvolve(np.asarray(rec, dtype=np.float64), inv)
    k = int(np.argmax(np.abs(h)))
    peak_db = 20 * np.log10(np.abs(h[k]) / (np.median(np.abs(h)) + 1e-30))
    if peak_db < MIN_PEAK_DB:
        raise NoSweep("No test sweep found in the recording. Turn the speaker up and try again.")

    start = k - (len(inv) - 1)          # where the sweep begins in the recording
    tail = (len(rec) - (start + len(inv))) / fs
    if start < 0:
        raise NoSweep("The sweep started before the recording. Start listening first, then play it.")
    if tail < MIN_TAIL_S:
        raise NoSweep("The recording stopped before the room went quiet. Play the sweep sooner.")

    ir = h[max(0, k - int(0.005 * fs)): k + int(min(IR_SECONDS, tail) * fs)]
    return ir, {"start_s": round(start / fs, 3), "peak_db": round(float(peak_db), 1),
                "tail_s": round(tail, 2)}


def response(ir: np.ndarray, fs: int, f_lo: float = F1_HZ, f_hi: float = F2_HZ,
             window_s: float = 0.5, points: int = 240, smoothing_oct: float = 1 / 6) -> dict:
    """Level at the mic per frequency, 1/6-octave smoothed, 0 dB = mean of
    500 Hz–2 kHz. Includes the speaker and the mic, so the shape below the
    Schroeder frequency (room modes) is what to read, not the absolute level."""
    n = min(len(ir), int(window_s * fs))
    seg = ir[:n].copy()
    fade = n // 5
    seg[n - fade:] *= 0.5 + 0.5 * np.cos(np.pi * np.arange(fade) / fade)
    nfft = 1 << int(np.ceil(np.log2(max(n, fs))))
    power = np.abs(np.fft.rfft(seg, nfft)) ** 2
    freqs = np.fft.rfftfreq(nfft, 1 / fs)

    hi = min(f_hi, 20000.0, 0.45 * fs)
    centres = np.geomspace(max(20.0, f_lo), hi, points)
    half = 2 ** (smoothing_oct / 2)
    csum = np.concatenate([[0.0], np.cumsum(power)])
    lo_i = np.searchsorted(freqs, centres / half)
    hi_i = np.maximum(np.searchsorted(freqs, centres * half), lo_i + 1)
    db = 10 * np.log10((csum[hi_i] - csum[lo_i]) / (hi_i - lo_i) + 1e-30)
    ref = (centres >= 500) & (centres <= 2000)
    db -= db[ref].mean() if ref.any() else db.max()
    return {"f_hz": [round(float(f), 1) for f in centres], "db": [round(float(v), 1) for v in db]}


def wav_base64(ir: np.ndarray, fs: int, seconds: float = 2.0) -> str:
    """The impulse response as a 16-bit WAV (for REW, convolution reverbs...)."""
    x = ir[: int(seconds * fs)]
    x = 0.9 * x / (np.max(np.abs(x)) + 1e-30)
    buf = io.BytesIO()
    sf.write(buf, x.astype(np.float32), fs, format="WAV", subtype="PCM_16")
    return base64.b64encode(buf.getvalue()).decode("ascii")
