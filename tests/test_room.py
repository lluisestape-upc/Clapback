import pytest

from clapback.room import Room


def test_box_geometry():
    r = Room.box(5, 4, 2.5)
    assert r.floor_area() == pytest.approx(20)
    assert r.volume() == pytest.approx(50)
    assert r.total_area() == pytest.approx(2 * 20 + 2 * (5 + 4) * 2.5)
    assert r.is_rectangular()


def test_l_shaped_room_is_not_rectangular():
    pts = [(0, 0), (6, 0), (6, 3), (3, 3), (3, 5), (0, 5)]
    r = Room(floor=[{"x": x, "y": y} for x, y in pts], height=2.5)
    assert r.floor_area() == pytest.approx(6 * 3 + 3 * 2)
    assert not r.is_rectangular()


def test_wall_index_is_checked():
    with pytest.raises(ValueError):
        Room.box(5, 4, 2.5, surfaces=[{"kind": "wall", "wall_index": 7, "material": "glass_window"}])
