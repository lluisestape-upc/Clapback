"""Image sources, placement and seats against cases with exact answers."""

import math

import numpy as np
import pytest

from clapback.acoustics import geometry
from clapback.room import Point2, Point3, Room

PLASTER = "plaster_on_masonry"


def box(l=6.0, w=4.0, h=3.0, clockwise=False):
    floor = [(0, 0), (l, 0), (l, w), (0, w)]
    if clockwise:
        floor = floor[::-1]
    surfaces = [{"kind": "floor", "material": "wood_floor_on_joists"}, {"kind": "ceiling", "material": PLASTER},
                *({"kind": "wall", "wall_index": i, "material": PLASTER} for i in range(4))]
    return Room(floor=[Point2(x=x, y=y) for x, y in floor], height=h, surfaces=surfaces)


S, R = Point3(x=1, y=2, z=1.5), Point3(x=4, y=2, z=1.5)


def first_order(room):
    return {p["surfaces"][0]: p for p in geometry.early_reflections(room, S, R, max_order=1, range_db=99)}


def test_floor_reflection_is_where_the_mirror_says():
    p = first_order(box())["floor"]
    assert p["points"][0] == pytest.approx([2.5, 2.0, 0.0])
    assert p["length_m"] == pytest.approx(math.hypot(3, 3), abs=1e-3)
    assert p["delay_ms"] == pytest.approx((math.hypot(3, 3) - 3) / 343 * 1000, abs=0.05)
    alpha = geometry._surface_alpha(box(), "floor", None)
    assert p["level_db"] == pytest.approx(20 * math.log10(3 / math.hypot(3, 3)) + 10 * math.log10(1 - alpha), abs=0.1)


def test_a_box_has_six_first_order_reflections_on_their_surfaces():
    room = box()
    paths = first_order(room)
    assert set(paths) == {"floor", "ceiling", "wall A", "wall B", "wall C", "wall D"}
    pls = {p.name: p for p in geometry.planes(room)}
    for name, p in paths.items():
        pt = np.array(p["points"][0])
        assert abs(np.dot(pt - pls[name].point, pls[name].normal)) < 1e-9
        assert geometry.on_surface(room, pls[name], pt)


def test_floor_then_ceiling_matches_the_image_source():
    paths = geometry.early_reflections(box(), S, R, max_order=2, range_db=99)
    fc = next(p for p in paths if p["surfaces"] == ["floor", "ceiling"])
    # source z 1.5 → floor image -1.5 → ceiling (z=3) image 7.5
    assert fc["length_m"] == pytest.approx(math.hypot(3, 7.5 - 1.5), abs=1e-3)
    assert fc["points"][0][2] == pytest.approx(0) and fc["points"][1][2] == pytest.approx(3)


def test_winding_of_the_floor_polygon_does_not_matter():
    a = {tuple(p["surfaces"]): p["length_m"] for p in geometry.early_reflections(box(), S, R, range_db=99)}
    b = {tuple(p["surfaces"]): p["length_m"] for p in geometry.early_reflections(box(clockwise=True), S, R, range_db=99)}
    assert sorted(a.values()) == pytest.approx(sorted(b.values()))


def test_voice_listener_is_the_mic_towards_the_nearest_wall():
    src = Point3(x=0.6, y=2, z=1.4)
    mic = geometry.default_listener(box(), "voice", src, None)
    assert (mic.x, mic.y, mic.z) == pytest.approx((0.35, 2, 1.4))


def test_best_seat_is_away_from_walls_and_more_even_than_most():
    room = box(5.5, 4.5, 2.6)
    out = geometry.bass_evenness(room, Point3(x=0.6, y=2.25, z=1.1), rt_low_s=0.6, f_hi=150)
    seat = out["seat"]
    assert 0.5 <= seat["x"] <= 5.0 and 0.5 <= seat["y"] <= 4.0
    assert out["seat_spread_db"] <= out["median_spread_db"]


def test_panels_go_on_the_strongest_wall_reflection_without_overlapping():
    room = box()
    refl = geometry.early_reflections(room, S, R, range_db=99)
    out = geometry.place(room, [{"id": "panel_50", "where": "wall", "area_m2": 3.6}], refl)
    rects = out["rects"]
    assert len(rects) == 10                                   # 3.6 m² of 0.6 × 0.6 m panels
    walls1 = [p for p in refl if p["surfaces"][0].startswith("wall") and p["order"] == 1]
    top = [p for p in walls1 if p["level_db"] >= walls1[0]["level_db"] - 0.1]   # ties: walls A and D are both 5 m
    first = rects[0]
    assert any(first["surface"] == p["surfaces"][0]
               and np.linalg.norm(np.array(first["center"]) - np.array(p["points"][0])) < 0.5 for p in top)
    boxes = [(r["surface"], *r["center"]) for r in rects]
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            if a["surface"] == b["surface"]:
                d = np.abs(np.array(a["center"]) - np.array(b["center"]))
                assert not (d[2] < 0.59 and np.hypot(d[0], d[1]) < 0.59), boxes
    assert out["groups"] and "panel" in out["groups"][0]


def test_a_rug_covers_the_floor_reflection_and_a_panel_removes_its_reflection():
    room = box()
    refl = geometry.early_reflections(room, S, R, range_db=99)
    out = geometry.place(room, [{"id": "rug", "where": "floor", "area_m2": 6.0}], refl)
    rug = out["rects"][0]
    assert rug["surface"] == "floor"
    assert abs(rug["center"][0] - 2.5) <= 1.0 and abs(rug["center"][1] - 2.0) <= 1.5
    after = geometry.reflections_after(room, refl, out["rects"], {"rug": 0.6})
    floor = next(p for p in after if p["surfaces"] == ["floor"])
    assert floor["covered"] and floor["level_after_db"] < floor["level_db"] - 2
