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
