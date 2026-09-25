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
