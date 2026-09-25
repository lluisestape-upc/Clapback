"""Measurement planner: where should the next clap be?

After each clap the engine calibrates the room and reports which surfaces'
absorption is poorly determined, whether a flutter echo showed up, and the
usable dynamic range per band. The planner reads that report and either
asks for another measurement ("clap near the window, phone at the desk")
or says it has enough.

This is the agentic core of the project: "more serious tests for a better
answer" is the planner's job, not a settings menu.

Model: Super. Output is constrained to a Next-step schema with a position
the web app can show on the 3D room.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from ..room import Point3, Room


class NextStep(BaseModel):
    action: Literal["clap", "done"]
    source: Point3 | None = None  # where to clap
    receiver: Point3 | None = None  # where to put the phone
    reason: str  # shown to the user


def run(room: Room, calibration_report: dict, history: list[dict]) -> NextStep:
    raise NotImplementedError
