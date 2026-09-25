"""Absorption database: data/materials.json.

The agents may only pick materials by id from this file. That keeps every
acoustic number traceable to a table, not to a model's guess.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

from .room import OCTAVE_BANDS_HZ

DATA = Path(__file__).resolve().parent.parent / "data" / "materials.json"


class Material(BaseModel):
    id: str
    name: str
    # One coefficient per band in OCTAVE_BANDS_HZ.
    alpha: list[float] = Field(min_length=len(OCTAVE_BANDS_HZ), max_length=len(OCTAVE_BANDS_HZ))
    notes: str = ""


@lru_cache
def load() -> dict[str, Material]:
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    mats = [Material(**m) for m in raw["materials"]]
    return {m.id: m for m in mats}


def get(material_id: str) -> Material:
    try:
        return load()[material_id]
    except KeyError:
        raise KeyError(f"unknown material '{material_id}'") from None
