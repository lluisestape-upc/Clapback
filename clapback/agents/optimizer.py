"""Treatment optimizer: budgeted fixes, every one scored by the engine.

Nemotron 3 Super gets the measured room, the goal, the budget and a priced
catalogue, and two tools:

    try_plan(treatments)            → valid? cost, predicted RT per band
    finish(treatments, summary)     → final answer (validated again)

It can't state an acoustic number on its own: every prediction comes from
acoustics/treat.py. If the model fails (bad tool calls, no finish within the
step limit, API error), a deterministic greedy plan is returned instead, so
the app always has an answer. The trace of tried plans is returned for the UI.
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel

from ..acoustics import treat
from ..acoustics.treat import Treatment
from ..llm import nemotron
from ..room import OCTAVE_BANDS_HZ, Room
from ..targets import TOLERANCE

log = logging.getLogger("uvicorn.error")

MAX_STEPS = 7


class Plan(BaseModel):
    treatments: list[Treatment]
    cost_eur: float
    before_mid_s: float
    after_mid_s: float
    target_s: float
    predicted_rt_s: list[float]
    summary: str
    trace: list[dict]
    source: str  # "nemotron", "fallback", or "engine" (no model needed)


TREATMENTS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "where": {"type": "string", "enum": ["wall", "floor", "ceiling", "window"]},
            "area_m2": {"type": "number"},
        },
        "required": ["id", "where", "area_m2"],
    },
}

TOOLS = [
    {"type": "function", "function": {
        "name": "try_plan",
        "description": "Score a set of treatments. Returns validity, cost and predicted reverberation per band.",
        "parameters": {"type": "object", "properties": {"treatments": TREATMENTS_SCHEMA}, "required": ["treatments"]},
    }},
    {"type": "function", "function": {
        "name": "finish",
        "description": "Submit the final plan with a short plain-language summary for the room's owner.",
        "parameters": {"type": "object", "properties": {
            "treatments": TREATMENTS_SCHEMA,
            "summary": {"type": "string", "description": "2 to 4 sentences, plain words, no jargon"},
        }, "required": ["treatments", "summary"]},
    }},
]

SYSTEM = """You are a friendly room-acoustics consultant planning cheap fixes for someone's room.

Room: {volume:.0f} m³, floor {floor:.1f} m², use: {goal}.
Measured reverberation now (s) per band {bands}: {measured}.
Target mid-band reverberation: {target:.2f} s (±20 %). Budget: €{budget:.0f}.
Boomy bass notes from the room shape: {bass}.

Treatment catalogue (id: name, allowed places, €/m²):
{catalogue}

Rules:
- Use try_plan to test ideas; predictions come ONLY from the tool. Never invent numbers.
- Find the cheapest plan that brings the mid reverberation into the target range, within budget.
- If the room is already at or below target, propose no treatments and say so.
- Prefer spreading absorption over different surfaces rather than one huge patch.
- Porous panels barely touch the lowest bass; if there are boomy notes, say thicker panels or
  corner placement help, without promising a fix.
- Try at most 4 plans, then call finish. If the target can't be reached within budget,
  finish with the plan that gets closest and say so honestly.
- The summary is for a non-expert: what to buy, where, and what will change."""


def run(room: Room, goal: str, measured_rt: list[float | None], target_s: float,
        budget_eur: float, bass_notes: list[dict] | None = None) -> Plan:
    before = treat.mid(treat.predict(room, measured_rt, []))
    if before < target_s * (1 - TOLERANCE):
        # Already drier than the target: every item in the catalogue absorbs,
        # so the only honest plan is none. No model call.
        rt = treat.predict(room, measured_rt, [])
        return Plan(
            treatments=[], cost_eur=0, before_mid_s=round(before, 2), after_mid_s=round(before, 2),
            target_s=round(target_s, 2), predicted_rt_s=[round(t, 2) for t in rt], trace=[], source="engine",
            summary=(f"The room is already drier than the {target_s:.2f} s target ({before:.2f} s now). "
                     "Everything on this list absorbs sound and would make it drier, so there is nothing to buy."),
        )
    trace: list[dict] = []
    try:
        plan, summary = _agent(room, goal, measured_rt, target_s, budget_eur, bass_notes or [], trace)
        source = "nemotron"
    except Exception as e:  # noqa: BLE001 - any failure falls back to the greedy plan
        log.warning("optimizer failed: %s", e)
        trace.append({"error": str(e)[:200]})
        plan, summary, source = None, "", "fallback"

    if plan is None:
        plan = treat.greedy_plan(room, measured_rt, target_s, budget_eur)
        summary = summary or _fallback_summary(plan, before, room, measured_rt, target_s)
        source = "fallback"

    after_rt = treat.predict(room, measured_rt, plan)
    return Plan(
        treatments=plan,
        cost_eur=round(treat.cost(plan)),
        before_mid_s=round(before, 2),
        after_mid_s=round(treat.mid(after_rt), 2),
        target_s=round(target_s, 2),
        predicted_rt_s=[round(t, 2) for t in after_rt],
        summary=summary,
        trace=trace,
        source=source,
    )


def _agent(room, goal, measured_rt, target_s, budget_eur, bass_notes, trace):
    cat = "\n".join(
        f"- {c['id']}: {c['name']}, {'/'.join(c['where'])}, €{c['eur_per_m2']}/m²"
        for c in treat.catalogue().values()
    )
    system = SYSTEM.format(
        volume=room.volume(), floor=room.floor_area(), goal=goal or "general listening",
        bands=list(OCTAVE_BANDS_HZ),
        measured=[round(t, 2) if t else None for t in measured_rt],
        target=target_s, budget=budget_eur,
        bass=", ".join(f"{b['freq_hz']:.0f} Hz" for b in bass_notes) or "none found",
        catalogue=cat,
    )
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": "Plan the fixes for my room."}]

    for step in range(MAX_STEPS):
        last = step == MAX_STEPS - 1
        choice = {"type": "function", "function": {"name": "finish"}} if last else "auto"
        resp = nemotron.chat(messages, model=nemotron.SUPER, tools=TOOLS, tool_choice=choice,
                             max_tokens=4096, thinking=False)
        msg = resp.choices[0].message
        if not msg.tool_calls:
            messages.append({"role": "assistant", "content": msg.content or ""})
            messages.append({"role": "user", "content": "Use the tools: try_plan, then finish."})
            continue
        messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": [
            {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}}
            for c in msg.tool_calls
        ]})
        for call in msg.tool_calls:
            args = json.loads(call.function.arguments or "{}")
            try:
                plan = [Treatment(**t) for t in args.get("treatments", [])]
            except Exception as e:  # noqa: BLE001 - report schema errors back to the model
                result = {"valid": False, "errors": [f"bad treatment format: {e}"]}
                plan = None
            else:
                result = treat.evaluate(room, measured_rt, plan, target_s, budget_eur)
            trace.append({"tool": call.function.name, "treatments": args.get("treatments", []), "result": result})
            if call.function.name == "finish" and plan is not None and result.get("valid"):
                return plan, args.get("summary", "").strip()
            messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result)})
    return None, ""


def _fallback_summary(plan, before, room, measured_rt, target_s) -> str:
    if not plan:
        return (f"Your room is already close to the {target_s:.2f} s target "
                f"({before:.2f} s now), so nothing needs buying.")
    names = {c["id"]: c["name"] for c in treat.catalogue().values()}
    parts = [f"{t.area_m2:g} m² of {names[t.id].lower()} on the {t.where}" for t in plan]
    after = treat.mid(treat.predict(room, measured_rt, plan))
    return (f"Add {', '.join(parts)}. That should bring the echo from {before:.2f} s "
            f"to about {after:.2f} s (target {target_s:.2f} s).")
