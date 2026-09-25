# Clapback

Clap once in a room. Clapback tells you why it sounds the way it does and
what to change.

You tell it what the room is for, give its size (typed, or scanned with the
phone camera), tap what it's made of, and clap where it asks you to. You get
the echo time per frequency against a target for your use, the bass notes
the room's shape will boom on, 3D maps of speech clarity and bass over the
floor, and a shopping list that fits your budget.

Built for the [Nebius x NVIDIA Global AI Hackathon](https://nebiusglobalaihackathon.devpost.com/).

## How it works

```
phone (installable web app)
  goal → size (presets, steppers or AR scan) → materials + notes → clap
        │  raw PCM, browser voice processing off
        ▼
server (Python, FastAPI)
  acoustics engine: deterministic, tested
    decay.py   onset → octave bands → noise crosspoint (Lundeby-style)
               → Schroeder decay → EDT / T20 / T30, gated by dynamic range
    modes.py   rectangular-room modes → boomy-note clusters, Schroeder frequency
    reverb.py  Sabine / Eyring + air + furnishing, calibration against the claps
    maps.py    C50 (Barron's revised theory), STI estimate, modal pressure
    treat.py   validates and scores treatment plans from the MEASURED absorption
    targets.py RT target per use (DIN 18041, EBU Tech 3276) and a verdict
  agents: NVIDIA Nemotron on Nebius Token Factory
    intake     "double bed and a big bookshelf" → absorbers from the materials table
    planner    after each clap: is another one worth it, and where?
    optimizer  tries plans with tool calls; the engine scores every one
  products     Tavily search for real products per treatment (optional)
```

The rule: **the models never produce an acoustic number.** They pick from
the materials table and call the engine; the engine computes; the claps
check it. Every agent has a deterministic fallback, so the app still works
if the model call fails.

## How Nebius and NVIDIA are used

All model calls go through **Nebius Token Factory**'s OpenAI-compatible API
(`clapback/llm/nemotron.py`), using **NVIDIA Nemotron 3 Super**
(`nvidia/nemotron-3-super-120b-a12b`).

| Agent | What Nemotron does | How it's kept honest | Code |
|---|---|---|---|
| Intake | Maps the user's own words to material ids and areas | Only ids from `data/materials.json`; unknown ids dropped; areas clamped to the room | `agents/intake.py` |
| Planner | Decides whether another clap is worth it and gives a concrete position | Hard limits in code: at least 2 claps, at most 4 | `agents/planner.py` |
| Optimizer | Tool-calling loop: `try_plan` / `finish` against a priced catalogue and a budget | Each plan validated (placement, area, budget) and scored by `acoustics/treat.py`; forced `finish` on the last turn; greedy fallback | `agents/optimizer.py` |

Findings that shaped the design:

- Reasoning is switched off for these calls
  (`chat_template_kwargs: {enable_thinking: false}`), which brings each call
  under ~2 s. With reasoning on, a small `max_tokens` can be used up before
  any answer.
- Nemotron 3 Nano was tried first for intake. It mapped "a closed wardrobe"
  to 6 m² of carpet; Super flags it as unknown instead. All agents use Super.

Measured cost of a full session (3 claps with notes, then a plan): **9 Super
calls, ~10.4k input + ~1k output tokens, ~15 s total**. At Token Factory's
per-token pricing that's well under one cent per room.

## Run it

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env   # NEBIUS_API_KEY, optional TAVILY_API_KEY
python scripts/check_nebius.py
uvicorn clapback.server:app --port 8766 --reload
pytest
```

The microphone and the AR scan need a secure context: `localhost`, or HTTPS.
To use a phone, either forward the port over USB (Chrome →
`chrome://inspect` → Port forwarding) and open `http://localhost:8766` on
the phone, or expose the server through an HTTPS tunnel. The AR scan needs
Chrome on an ARCore-supported Android phone.

## Limits, stated rather than hidden

- One clap is a rough measurement, especially below 250 Hz; the app asks for
  more claps and shows low bands as less certain.
- Statistical acoustics assumes a diffuse field; maps of bass use the modal
  model instead, and only for rectangular rooms.
- The STI map is an estimate from theory for a quiet room, not an
  IEC 60268-16 measurement. C50 comes from Barron's revised theory.
- Absorption coefficients and treatment prices are typical values for
  planning, listed in `data/`.
- Phone microphones differ. Clapback asks the browser to turn off echo
  cancellation, noise suppression and gain control, and records what the
  phone actually applied with every clap.

## Layout

```
clapback/
  room.py, materials.py, targets.py, products.py, server.py
  acoustics/   decay, modes, reverb, maps, treat
  agents/      intake, planner, optimizer
  llm/         Nemotron client
web/           the app (no build step): app.js, capture.js, scan.js, room3d.js
data/          materials.json, treatments.json
tests/         pytest (engine, agents with the model faked, API)
docs/          PLAN.md, ARCHITECTURE.md
recordings/    claps saved with their room, goal and mic settings (git-ignored)
```

## License

MIT, see [LICENSE](LICENSE).
