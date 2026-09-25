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


def verdict(goal: str, volume_m3: float, rt_mid: float | None) -> dict:
    target = target_rt(goal, volume_m3)
    if rt_mid is None:
        return {"level": "unknown", "target_s": round(target, 2), "headline": "Couldn't measure the echo",
                "detail": "The clap wasn't clear enough above the background noise. Try again in silence."}
    ratio = rt_mid / target
    if ratio > 1 + TOLERANCE:
        level, headline = "too_live", "Too echoey"
        detail = (f"Sound hangs around for {rt_mid:.2f} s; for this use about {target:.2f} s is ideal. "
                  "Soft, absorbent things will help most.")
    elif ratio < 1 - TOLERANCE:
        level, headline = "too_dead", "Very dry"
        detail = (f"Sound dies in {rt_mid:.2f} s, quicker than the {target:.2f} s that suits this use. "
                  "It may feel flat; don't add more absorption.")
    else:
        level, headline = "good", "About right"
        detail = f"{rt_mid:.2f} s against a target of {target:.2f} s. Nice."
    return {"level": level, "target_s": round(target, 2), "ratio": round(ratio, 2),
            "headline": headline, "detail": detail}
