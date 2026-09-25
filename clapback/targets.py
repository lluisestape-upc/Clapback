"""Target reverberation time per use, and a plain-language verdict.

Targets are for the mid-frequency RT (mean of 500 Hz and 1 kHz):

- study / teaching: DIN 18041:2016 group A3, T = 0.32·lg(V) − 0.17 s
- music practice:   DIN 18041:2016 group A1, T = 0.45·lg(V) + 0.07 s
- studio / mixing:  EBU Tech 3276 control room, T = 0.25·(V/100)^(1/3) s
- podcast / voice:  0.3 s, a common practical target for small voice rooms
- movies / TV:      0.35 s, a common home-cinema recommendation
- curious:          0.5 s, typical of a comfortable furnished living room

Tolerance ±20 % around the target.
"""

from __future__ import annotations

import math

TOLERANCE = 0.2


def target_rt(goal: str, volume_m3: float) -> float:
    lv = math.log10(max(volume_m3, 1.0))
    match goal:
        case "study":
            return max(0.3, 0.32 * lv - 0.17)
        case "music":
            return 0.45 * lv + 0.07
        case "studio":
            return 0.25 * (volume_m3 / 100) ** (1 / 3)
        case "voice":
            return 0.3
        case "cinema":
            return 0.35
        case _:
            return 0.5


SOURCES = {
    "study": "DIN 18041, group A3",
    "music": "DIN 18041, group A1",
    "studio": "EBU Tech 3276",
    "voice": "common practice for voice rooms",
    "cinema": "common practice for home cinema",
}


def verdict(goal: str, volume_m3: float, rt_mid: float | None) -> dict:
    target = target_rt(goal, volume_m3)
    lo, hi = target * (1 - TOLERANCE), target * (1 + TOLERANCE)
    out = {"target_s": round(target, 2), "range_s": [round(lo, 2), round(hi, 2)],
           "source": SOURCES.get(goal, "a comfortable furnished room")}
    if rt_mid is None:
        return {**out, "level": "unknown", "headline": "No reliable measurement",
                "detail": "The clap didn't rise far enough above the background noise. Repeat it in silence."}
    ratio = rt_mid / target
    off = abs(ratio - 1) * 100
    if ratio > 1 + TOLERANCE:
        level, headline = "too_live", "Too reverberant"
        detail = f"{off:.0f} % above the target. Adding absorption will bring it down."
    elif ratio < 1 - TOLERANCE:
        level, headline = "too_dead", "Too dry"
        detail = f"{off:.0f} % below the target. More absorption would make it worse."
    else:
        level, headline = "good", "Within target"
        detail = "Reverberation suits this use; no extra absorption needed."
    return {**out, "level": level, "ratio": round(ratio, 2), "headline": headline, "detail": detail}
