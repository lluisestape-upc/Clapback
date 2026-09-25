from fastapi.testclient import TestClient

from clapback.server import app

client = TestClient(app)


def test_health():
    assert client.get("/api/health").json() == {"ok": True}


def test_room_endpoint():
    room = {
        "floor": [{"x": 0, "y": 0}, {"x": 5, "y": 0}, {"x": 5, "y": 4}, {"x": 0, "y": 4}],
        "height": 2.5,
        "surfaces": [{"kind": "floor", "material": "wood_floor_on_joists"}],
    }
    out = client.post("/api/room", json=room).json()
    assert out["volume_m3"] == 50
    assert out["rectangular"] is True


def test_unknown_material_rejected():
    room = {
        "floor": [{"x": 0, "y": 0}, {"x": 5, "y": 0}, {"x": 5, "y": 4}],
        "height": 2.5,
        "surfaces": [{"kind": "floor", "material": "unobtainium"}],
    }
    assert client.post("/api/room", json=room).status_code == 422


def test_clap_upload_is_saved(tmp_path, monkeypatch):
    import io

    import numpy as np
    import soundfile as sf

    from clapback import server

    monkeypatch.setattr(server, "RECORDINGS", tmp_path)
    fs = 48000
    x = np.zeros(fs, dtype="float32")
    x[100] = 0.5
    buf = io.BytesIO()
    sf.write(buf, x, fs, format="WAV", subtype="FLOAT")

    res = client.post(
        "/api/clap",
        files={"audio": ("clap.wav", buf.getvalue(), "audio/wav")},
        data={"room": "{}", "goal": "voice"},
    )
    out = res.json()
    assert res.status_code == 200
    assert out["sample_rate"] == fs
    assert out["peak_dbfs"] == -6.0
    assert len(list(tmp_path.glob("*.wav"))) == 1
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_clap_is_analysed_with_room(tmp_path, monkeypatch):
    import io
    import json

    import soundfile as sf

    from clapback import server
    from tests.test_acoustics import synthetic_clap

    monkeypatch.setattr(server, "RECORDINGS", tmp_path)
    x, fs = synthetic_clap(0.9)
    buf = io.BytesIO()
    sf.write(buf, x.astype("float32"), fs, format="WAV", subtype="FLOAT")
    room = {
        "floor": [{"x": 0, "y": 0}, {"x": 5, "y": 0}, {"x": 5, "y": 4}, {"x": 0, "y": 4}],
        "height": 2.5,
        "surfaces": [{"kind": "floor", "material": "wood_floor_on_joists"}],
    }
    out = client.post(
        "/api/clap",
        files={"audio": ("clap.wav", buf.getvalue(), "audio/wav")},
        data={"room": json.dumps(room), "goal": "voice"},
    ).json()
    assert abs(out["rt_mid_s"] - 0.9) < 0.15
    assert out["verdict"]["level"] == "too_live"
    assert out["bass_notes"][0]["freq_hz"] < out["schroeder_hz"]
    assert len(out["model"]["absorption_factor"]) == 6


def _fake_models(monkeypatch):
    from clapback.agents import intake, planner
    from clapback.llm import nemotron

    monkeypatch.setattr(nemotron, "chat_json", lambda *a, schema=None, **kw: (
        intake.IntakeResult() if schema is intake.IntakeResult
        else planner.NextStep(action="done", instruction="", reason="")))

    def no_chat(*a, **kw):
        raise RuntimeError("no network in tests")

    monkeypatch.setattr(nemotron, "chat", no_chat)


def _clap_decay(tmp_path, monkeypatch, rt=0.9):
    import io

    import soundfile as sf

    from clapback import server
    from tests.test_acoustics import synthetic_clap

    monkeypatch.setattr(server, "RECORDINGS", tmp_path)
    x, fs = synthetic_clap(rt)
    buf = io.BytesIO()
    sf.write(buf, x.astype("float32"), fs, format="WAV", subtype="FLOAT")
    out = client.post("/api/clap", files={"audio": ("c.wav", buf.getvalue(), "audio/wav")}).json()
    return out["decay"]


ROOM = {
    "floor": [{"x": 0, "y": 0}, {"x": 5, "y": 0}, {"x": 5, "y": 4}, {"x": 0, "y": 4}],
    "height": 2.5,
    "surfaces": [{"kind": "floor", "material": "wood_floor_on_joists"},
                 {"kind": "ceiling", "material": "plaster_on_masonry"},
                 *({"kind": "wall", "wall_index": i, "material": "plaster_on_masonry"} for i in range(4))],
}


def test_analyze_and_plan_are_stateless(tmp_path, monkeypatch):
    _fake_models(monkeypatch)
    d = _clap_decay(tmp_path, monkeypatch)
    res = client.post("/api/analyze", json={"room": ROOM, "goal": "voice", "claps": [d, d]}).json()
    assert res["claps"] == 2 and abs(res["rt_mid_s"] - 0.9) < 0.15
    assert res["maps"]["sti"]["values"]
    plan = client.post("/api/plan", json={"room": ROOM, "goal": "voice", "claps": [d], "budget_eur": 300}).json()
    assert plan["source"] == "fallback" and plan["after_mid_s"] < plan["before_mid_s"]


def test_bad_band_data_is_rejected(monkeypatch):
    _fake_models(monkeypatch)
    bad = [{"band_hz": 1000, "t20_s": -3}]
    assert client.post("/api/analyze", json={"room": ROOM, "claps": [bad]}).status_code == 422
    assert client.post("/api/analyze", json={"room": ROOM, "claps": []}).status_code == 422


def test_model_calls_are_rate_limited(tmp_path, monkeypatch):
    from clapback import server

    _fake_models(monkeypatch)
    d = _clap_decay(tmp_path, monkeypatch)
    monkeypatch.setattr(server, "LLM_CALLS_PER_HOUR", 2)
    server._calls.clear()
    body = {"room": ROOM, "claps": [d]}
    codes = [client.post("/api/analyze", json=body, headers={"x-forwarded-for": "9.9.9.9"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
