# Clapback

Clap once in a room. Clapback tells you why it sounds bad and what to change.

Scan the room with your phone (guided, corner by corner), clap where it asks
you to, and get reverberation time per band, room modes, speech-clarity and
bass maps over the floor, and a budgeted treatment plan.

Built for the [Nebius x NVIDIA Global AI Hackathon](https://nebiusglobalaihackathon.devpost.com/)
(deadline 2026-10-30).

> Status: skeleton. Nothing below is implemented yet unless marked done.

## How it works

```
phone (web app, HTTPS)
  1. Scan     WebXR hit-test: floor corners → polygon, one tap for the ceiling,
              then "what is this surface?" for each wall/floor/ceiling
  2. Measure  Web Audio: record claps (no AGC / noise suppression)
  3. Show     three.js room with map layers
        │
        ▼
server (Python, FastAPI)
  room model (JSON)  ←  typed dimensions OR the scan: same schema
  acoustics engine   deterministic: T20/EDT per band, modes, Sabine/Eyring
                     calibration, C50/STI and modal pressure maps
  agents (Nemotron on Nebius Token Factory)
    intake     free-text surface description → materials from data/materials.json
    planner    decides where the next clap should be to reduce uncertainty
    optimizer  proposes treatments, calls the engine to score them, stays in budget
```

The rule: **the models never produce an acoustic number.** They choose from
the materials database and call the engine; the engine computes; the claps
check it.

## How Nebius and NVIDIA are used

| Role | Model | Where |
|---|---|---|
| Intake (description → materials) | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | `clapback/agents/intake.py` |
| Measurement planner | `nvidia/nemotron-3-super-120b-a12b` | `clapback/agents/planner.py` |
| Treatment optimizer (tool calls) | `nvidia/nemotron-3-super-120b-a12b` | `clapback/agents/optimizer.py` |

All calls go through Nebius Token Factory's OpenAI-compatible API
(`clapback/llm/nemotron.py`). *To be completed with measured token usage and
cost per analysis.*

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env   # then fill in NEBIUS_API_KEY
python scripts/check_nebius.py
uvicorn clapback.server:app --reload
pytest
```

WebXR only starts over HTTPS. To test the scan on a phone, expose the dev
server through an HTTPS tunnel; plain `http://` on the LAN won't open an AR
session. Needs Chrome on an ARCore-supported Android phone.

## Layout

```
clapback/
  room.py            room model schema (pydantic)
  materials.py       absorption database loader
  acoustics/         deterministic engine
    decay.py         clap → band-filtered Schroeder decay → T20, EDT
    modes.py         rectangular-room modes, Schroeder frequency
    reverb.py        Sabine / Eyring, calibration against measured RT
    maps.py          C50 / STI / modal pressure over the floor plane
  agents/            Nemotron agents (intake, planner, optimizer)
  llm/nemotron.py    Token Factory client
  server.py          FastAPI app, also serves web/
web/                 phone app (no build step)
data/materials.json  absorption coefficients per octave band
tests/               pytest
docs/                architecture and plan
recordings/          your clap recordings (git-ignored)
```

## License

MIT, see [LICENSE](LICENSE).
