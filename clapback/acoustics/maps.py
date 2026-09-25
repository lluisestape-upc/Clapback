"""Spatial maps over the floor plane at listener height (1.2 m).

RT is nearly constant across a diffuse room, so it is shown as a per-band
curve, not a map. What does change with position, and what these maps show:

- C50 from Barron's revised theory (Barron & Lee 1988): direct, early and
  late energy as a function of source distance r, volume V and RT T:
      d = 100 / r²
      e = (31200 T / V) · e^(-0.04 r / T) · (1 - e^(-0.691 / T))   (0-50 ms)
      l = (31200 T / V) · e^(-0.04 r / T) · e^(-0.691 / T)
      C50 = 10 lg((d + e) / l)
- STI estimate: modulation transfer of an exponential decay (Schroeder 1981)
  mixed with the direct sound by the direct-to-reverberant ratio, then the
  IEC 60268-16 male weighting. No background noise, so it is an upper
  bound. Labelled as an estimate in the UI.
- Modal pressure at one low frequency (below the Schroeder frequency):
  modal sum for a rectangular room with a point source. The web app runs
  the same formula in JS (web/room3d.js) so a frequency sweep can animate;
  this version is the tested reference.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np

from ..room import OCTAVE_BANDS_HZ, Point3, Room
from .modes import SPEED_OF_SOUND, room_modes

LISTENER_Z = 1.2
TALKER_Q = 2.0  # directivity factor of a talker, roughly

# IEC 60268-16 (male speech) octave weights 125 Hz .. 8 kHz, and redundancy.
STI_ALPHA = (0.085, 0.127, 0.230, 0.233, 0.309, 0.224, 0.173)
STI_BETA = (0.085, 0.078, 0.065, 0.011, 0.047, 0.095)
MOD_FREQS = (0.63, 0.8, 1.0, 1.25, 1.6, 2.0, 2.5, 3.15, 4.0, 5.0, 6.3, 8.0, 10.0, 12.5)


@dataclass
class Grid:
    xs: list[float]
    ys: list[float]
    values: list[list[float]]  # values[j][i] at (xs[i], ys[j])
    unit: str

    def to_dict(self) -> dict:
        return asdict(self)


def default_source(room: Room, goal: str = "") -> Point3:
    """Talker or speakers near the middle of the first wall."""
    xs = [p.x for p in room.floor]
    ys = [p.y for p in room.floor]
    return Point3(x=min(xs) + 0.6, y=(min(ys) + max(ys)) / 2, z=1.4 if goal in ("study", "voice") else 1.1)


def _grid(room: Room, step_m: float) -> tuple[np.ndarray, np.ndarray]:
    xs = [p.x for p in room.floor]
    ys = [p.y for p in room.floor]
    gx = np.arange(min(xs) + step_m / 2, max(xs), step_m)
    gy = np.arange(min(ys) + step_m / 2, max(ys), step_m)
    return gx, gy


def _distance(gx, gy, src: Point3) -> np.ndarray:
    X, Y = np.meshgrid(gx, gy)
    return np.maximum(0.3, np.sqrt((X - src.x) ** 2 + (Y - src.y) ** 2 + (LISTENER_Z - src.z) ** 2))


def c50_barron(r: np.ndarray, V: float, T: float) -> np.ndarray:
    d = 100.0 / r**2
    k = 31200.0 * T / V * np.exp(-0.04 * r / T)
    e = k * (1 - math.exp(-0.691 / T))
    late = k * math.exp(-0.691 / T)
    return 10 * np.log10((d + e) / late)


def clarity_map(room: Room, rt_s: float, source: Point3, step_m: float = 0.25) -> Grid:
    """C50 in dB over the floor, for RT at 1 kHz (or mid)."""
    gx, gy = _grid(room, step_m)
    c50 = c50_barron(_distance(gx, gy, source), room.volume(), rt_s)
    return Grid(gx.round(3).tolist(), gy.round(3).tolist(), c50.round(2).tolist(), "dB")


def _mti(T: float, dr: np.ndarray) -> np.ndarray:
    """Mean transmission index for one band: reverberant MTF mixed with the
    direct sound by the direct-to-reverberant energy ratio `dr`."""
    ti = []
    for F in MOD_FREQS:
        m_rev = 1 / math.sqrt(1 + (2 * math.pi * F * T / 13.8) ** 2)
        m = (dr + m_rev) / (dr + 1)
        snr = np.clip(10 * np.log10(np.clip(m, 1e-6, 1 - 1e-6) / (1 - np.clip(m, 1e-6, 1 - 1e-6))), -15, 15)
        ti.append((snr + 15) / 30)
    return np.mean(ti, axis=0)


def sti_map(room: Room, rt_bands: list[float | None], source: Point3, step_m: float = 0.25) -> Grid:
    """Rough STI estimate over the floor (no background noise)."""
    gx, gy = _grid(room, step_m)
    r = _distance(gx, gy, source)
    V = room.volume()
    known = [t for t in rt_bands if t]
    fill = float(np.median(known)) if known else 0.5
    bands = [t or fill for t in rt_bands] + [rt_bands[-1] or fill]  # 8 kHz ≈ 4 kHz
    mtis = []
    for T in bands:
        A = 0.161 * V / T
        dr = (TALKER_Q / (4 * math.pi * r**2)) / (4 / A)
        mtis.append(_mti(T, dr))
    sti = sum(a * m for a, m in zip(STI_ALPHA, mtis))
    sti -= sum(b * np.sqrt(mtis[k] * mtis[k + 1]) for k, b in enumerate(STI_BETA))
    sti = np.clip(sti, 0, 1)
    return Grid(gx.round(3).tolist(), gy.round(3).tolist(), sti.round(3).tolist(), "STI")


def modal_pressure_map(room: Room, freq_hz: float, source: Point3, rt_s: float = 0.5,
                       step_m: float = 0.25) -> Grid:
    """Relative SPL (dB, 0 = median over the floor) at freq_hz.

    p(r) ∝ Σ_n ψ_n(r) ψ_n(s) / (Λ_n (ω_n² - ω² + 2jδω)),  δ = 6.91 / T,
    ψ_n = cos(nx π x/Lx) cos(ny π y/Ly) cos(nz π z/Lz), Λ_n = Π (1 if n=0 else 1/2).
    """
    xs = [p.x for p in room.floor]
    ys = [p.y for p in room.floor]
    x0, y0 = min(xs), min(ys)
    lx, ly, lz = max(xs) - x0, max(ys) - y0, room.height
    gx, gy = _grid(room, step_m)
    X, Y = np.meshgrid(gx - x0, gy - y0)
    w = 2 * math.pi * freq_hz
    delta = 6.91 / rt_s
    p = np.zeros_like(X, dtype=complex)
    for m in room_modes(lx, ly, lz, f_max=max(2 * freq_hz, 60.0)) + [None]:
        n = m.n if m else (0, 0, 0)
        wn = 2 * math.pi * (m.freq_hz if m else 0.0)
        lam = math.prod(1.0 if k == 0 else 0.5 for k in n)
        psi_s = (math.cos(n[0] * math.pi * (source.x - x0) / lx) * math.cos(n[1] * math.pi * (source.y - y0) / ly)
                 * math.cos(n[2] * math.pi * source.z / lz))
        psi_r = (np.cos(n[0] * math.pi * X / lx) * np.cos(n[1] * math.pi * Y / ly)
                 * math.cos(n[2] * math.pi * LISTENER_Z / lz))
        p += psi_r * psi_s / (lam * (wn**2 - w**2 + 2j * delta * w))
    db = 20 * np.log10(np.abs(p) + 1e-12)
    db -= np.median(db)
    return Grid(gx.round(3).tolist(), gy.round(3).tolist(), db.round(2).tolist(), "dB")


def summarize(grid: Grid) -> dict:
    v = np.array(grid.values)
    return {"min": round(float(v.min()), 2), "max": round(float(v.max()), 2), "mean": round(float(v.mean()), 2)}


def all_maps(room: Room, rt_bands: list[float | None], goal: str = "", source: Point3 | None = None) -> dict:
    src = source or room.source or default_source(room, goal)
    known = [t for t in rt_bands if t]
    rt_1k = rt_bands[OCTAVE_BANDS_HZ.index(1000)] or (float(np.median(known)) if known else 0.5)
    rt_low = rt_bands[0] or rt_bands[1] or rt_1k
    out = {
        "source": src.model_dump(),
        "listener_z": LISTENER_Z,
        "sti": sti_map(room, rt_bands, src).to_dict(),
        "c50": clarity_map(room, rt_1k, src).to_dict(),
        "rt_low_s": rt_low,
    }
    out["sti_summary"] = summarize(Grid(**out["sti"]))
    return out


# Speed of sound is re-exported for the JS mirror's constants check in tests.
__all__ = ["Grid", "all_maps", "clarity_map", "sti_map", "modal_pressure_map", "SPEED_OF_SOUND"]
