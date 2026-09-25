"""Deterministic parts of the agents. No network: model calls are faked."""

import pytest

from clapback.acoustics import treat
from clapback.acoustics.treat import Treatment
from clapback.agents import intake, optimizer, planner
from clapback.llm import nemotron
from clapback.room import Room

MEASURED = [0.9, 0.8, 0.8, 0.75, 0.7, 0.6]


def room():
    surfaces = [
        {"kind": "floor", "material": "wood_floor_on_joists"},
        {"kind": "ceiling", "material": "plaster_on_masonry"},
        {"kind": "wall", "wall_index": 0, "material": "plaster_on_masonry",
         "patches": [{"material": "glass_window", "area_m2": 3}]},
        *({"kind": "wall", "wall_index": i, "material": "plaster_on_masonry"} for i in range(1, 4)),
    ]
    return Room.box(5, 4, 2.6, surfaces=surfaces)


def test_no_treatment_reproduces_measurement():
    rt = treat.predict(room(), MEASURED, [])
    assert rt == pytest.approx(MEASURED, rel=1e-6)


def test_panels_lower_rt_and_cost_money():
    plan = [Treatment(id="panel_50", where="wall", area_m2=6)]
    assert treat.mid(treat.predict(room(), MEASURED, plan)) < treat.mid(MEASURED)
    assert treat.cost(plan) == 6 * 30


def test_validation_catches_bad_plans():
    r = room()
    assert treat.validate(r, [Treatment(id="nope", where="wall", area_m2=1)])
    assert treat.validate(r, [Treatment(id="rug", where="wall", area_m2=1)])
    assert treat.validate(r, [Treatment(id="curtain", where="window", area_m2=10)])  # only 3 m² of glass
    assert treat.validate(r, [Treatment(id="panel_50", where="wall", area_m2=5)], budget_eur=100)
    assert not treat.validate(r, [Treatment(id="panel_50", where="wall", area_m2=3)], budget_eur=100)


def test_greedy_reaches_target_when_budget_allows():
    plan = treat.greedy_plan(room(), MEASURED, target_s=0.5, budget_eur=1000)
    assert treat.mid(treat.predict(room(), MEASURED, plan)) <= 0.5 * 1.2
    assert treat.cost(plan) <= 1000


def test_greedy_does_nothing_for_a_dry_room():
    assert treat.greedy_plan(room(), [0.3] * 6, target_s=0.4, budget_eur=500) == []


def test_optimizer_falls_back_when_the_model_fails(monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("no network in tests")

    monkeypatch.setattr(nemotron, "chat", boom)
    plan = optimizer.run(room(), "voice", MEASURED, target_s=0.4, budget_eur=500)
    assert plan.source == "fallback"
    assert plan.after_mid_s < plan.before_mid_s
    assert plan.cost_eur <= 500
    assert plan.summary


def test_intake_drops_invented_materials():
    res = intake.IntakeResult(extras=[
        intake.Extra(material="bookshelf_filled", area_m2=4, what="bookshelf"),
        intake.Extra(material="magic_foam", area_m2=2, what="magic foam"),
        intake.Extra(material="upholstered_furniture", area_m2=500, what="huge sofa"),
    ])
    out = intake.clean(room(), res)
    assert [e.material for e in out.extras] == ["bookshelf_filled", "upholstered_furniture"]
    assert out.extras[1].area_m2 == 20  # clamped to the floor area
    assert out.unknown == ["magic foam"]


def test_planner_limits(monkeypatch):
    monkeypatch.setattr(nemotron, "chat_json", lambda *a, **kw: planner.NextStep(
        action="done", instruction="", reason=""))
    # one clap is never enough, whatever the model says
    assert planner.run({"claps": 1}).action == "clap"
    assert planner.run({"claps": planner.MAX_CLAPS}).action == "done"
