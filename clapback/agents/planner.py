"""Measurement planner: is another clap worth it, and where?

After each clap the engine reports how consistent the claps are, which bands
have a usable decay, and how far the material model is from the measurement.
Nemotron 3 Super reads that and either asks for one more clap (with a
concrete, friendly instruction) or says it has enough.

Hard limits stay in code: at most MAX_CLAPS, and the first clap always gets a
second one, since one position isn't a measurement.
"""

from __future__ import annotations

import json
import logging
from typing import Literal

from pydantic import BaseModel

from ..llm import nemotron

log = logging.getLogger("uvicorn.error")

MAX_CLAPS = 4


class NextStep(BaseModel):
    action: Literal["clap", "done"]
    instruction: str  # shown to the user, e.g. "Clap again from the corner by the window"
    reason: str       # one short sentence on why


SYSTEM = """You guide someone measuring their room's echo with hand claps and a phone.
Decide whether one more clap would make the result noticeably more reliable.

Ask for another clap only when: there is a single clap so far, the claps disagree by
more than about 10 % in the mid bands (mid_spread_pct), or the low bands (125-250 Hz)
have no usable result and there are fewer than 3 claps. Otherwise say it's done.
More claps don't change how the room is modelled, only how precise the measurement is.

When asking for a clap, give ONE short, concrete instruction for a different position
than before (e.g. a corner, near the window, by the door), and keep the phone at the
listening spot. Plain words, friendly, no jargon."""


def run(report: dict) -> NextStep:
    n = report.get("claps", 0)
    if n >= MAX_CLAPS:
        return NextStep(action="done", instruction="That's plenty of claps.",
                        reason=f"{n} claps is enough for a solid average.")
    try:
        step = nemotron.chat_json(
            [{"role": "system", "content": SYSTEM},
             {"role": "user", "content": json.dumps(report)}],
            schema=NextStep, model=nemotron.SUPER, max_tokens=512, thinking=False,
        )
    except Exception as e:  # noqa: BLE001 - the planner is optional; fall back to a rule
        log.warning("planner failed: %s", e)
        step = _rule(report)
    if n < 2 and step.action == "done":
        step = _rule(report)
    return step


def _rule(report: dict) -> NextStep:
    if report.get("claps", 0) < 2 or (report.get("mid_spread_pct") or 0) > 10:
        return NextStep(action="clap", instruction="Clap once more, this time standing near a corner.",
                        reason="A second position makes the average much more reliable.")
    return NextStep(action="done", instruction="That's enough claps.", reason="The claps agree well.")
