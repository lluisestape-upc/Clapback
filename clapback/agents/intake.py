"""Intake agent: the user's own words → extra absorbers from the database.

"a big bookshelf on one wall, a sofa and a double bed" becomes
[{bookshelf_filled, 4 m²}, {upholstered_furniture, 3 m²}, {bed_with_duvet, 3 m²}].

The model may only use material ids from data/materials.json, and every
area is checked against the room before it is used. Anything it can't map
goes to `unknown`, so the app can show it instead of guessing.

Model: Nemotron 3 Super with reasoning off (about a second, one call per room).
Nano was tried first and mapped a closed wardrobe to carpet; Super doesn't.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .. import materials
from ..llm import nemotron
from ..room import Patch, Room


class Extra(BaseModel):
    material: str
    area_m2: float = Field(gt=0)
    what: str = Field(description="the user's words for this item, short")


class IntakeResult(BaseModel):
    extras: list[Extra] = []
    unknown: list[str] = []


SYSTEM = """You turn a room description into sound-absorbing items for an acoustics model.
Use ONLY these material ids (id: description):
{catalogue}

For each item the user mentions that absorbs sound (furniture, textiles, shelves, rugs),
output one entry with a material id from the list and an estimated exposed area in m²
(e.g. a 3-seat sofa ~3 m², a double bed ~3 m², a big bookshelf ~4 m², a rug of 2x3 m = 6 m²).
Ignore hard things (tables, TV, desk, closed wardrobes, cabinets) unless they are soft;
an open wardrobe or hanging clothes counts as clothes_in_wardrobe_open.
Put anything you can't map to the list in "unknown", in the user's words.
The room floor is {floor:.1f} m²; no single item can exceed that."""


def run(room: Room, notes: str) -> IntakeResult:
    if not notes.strip():
        return IntakeResult()
    cat = "\n".join(f"- {m.id}: {m.name}" for m in materials.load().values())
    result = nemotron.chat_json(
        [
            {"role": "system", "content": SYSTEM.format(catalogue=cat, floor=room.floor_area())},
            {"role": "user", "content": notes},
        ],
        schema=IntakeResult,
        model=nemotron.SUPER,
        max_tokens=1024,
        thinking=False,
    )
    return clean(room, result)


def clean(room: Room, result: IntakeResult) -> IntakeResult:
    """Drop anything the model invented; clamp areas to the room."""
    known = materials.load()
    ok, unknown = [], list(result.unknown)
    for e in result.extras:
        if e.material not in known:
            unknown.append(e.what)
            continue
        ok.append(Extra(material=e.material, area_m2=round(min(e.area_m2, room.floor_area()), 1), what=e.what))
    return IntakeResult(extras=ok, unknown=unknown)


def apply(room: Room, result: IntakeResult) -> Room:
    r = room.model_copy(deep=True)
    r.extras = [*r.extras, *(Patch(material=e.material, area_m2=e.area_m2) for e in result.extras)]
    return r
