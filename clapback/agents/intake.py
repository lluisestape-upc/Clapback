"""Intake agent: the user's words → materials from the database.

Input: the Room (geometry only) plus free text per surface, e.g.
"wall 2: big window, maybe half the wall" or "floor: parquet with a rug".
Output: Surface entries whose material ids exist in data/materials.json,
with patches for partial coverage. Anything the model can't map goes to
`unknown` so the UI can ask again instead of guessing.

Model: Nano (cheap, fast, one call per room).
"""

from __future__ import annotations

from pydantic import BaseModel

from ..room import Room, Surface


class IntakeResult(BaseModel):
    surfaces: list[Surface]
    unknown: list[str] = []  # descriptions it could not map


def run(room: Room, descriptions: dict[str, str]) -> IntakeResult:
    """descriptions keys: "floor", "ceiling", "wall:0", "wall:1", ..."""
    raise NotImplementedError
