"""Treatment optimizer: budgeted fixes, scored by the engine.

Goal presets set the targets, e.g. "podcast", "home studio", "classroom"
(DIN 18041 style RT target from volume), "living room".

Tools the model can call (all deterministic, all in this package):
    apply_treatment(surface, material, area_m2, cost)  → new predicted RT/C50/STI
    undo_last()
    current_scores()
    search_products(query)                              → Tavily, optional

The model proposes; the engine scores; the loop stops when targets are met or
the budget runs out. The final answer explains each choice in plain words.

Model: Super with tool calling.
"""

from __future__ import annotations

from pydantic import BaseModel

from ..room import Room


class Treatment(BaseModel):
    surface: str  # "floor", "ceiling", "wall:2"
    material: str
    area_m2: float
    cost_eur: float
    why: str


class Plan(BaseModel):
    treatments: list[Treatment]
    predicted_rt: list[float]
    total_cost_eur: float
    summary: str


def run(room: Room, goal: str, budget_eur: float) -> Plan:
    raise NotImplementedError
