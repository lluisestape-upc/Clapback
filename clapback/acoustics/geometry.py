"""Room geometry for the 3D views: early reflections, where treatments go,
and where to sit.

Surfaces are the walls of the floor polygon (named A, B, C… in its order;
the app puts windows on wall A and labels the walls in 3D), the floor and
the ceiling.

Early reflections by image sources (Allen & Berkley 1979 for boxes, Borish
1984 for any polyhedron): the source mirrored in a surface, and again in a
second one, gives the path of a specular reflection, which is real if every
reflection point lies on its surface. Level relative to the direct sound,
with each surface's mid-band absorption:

    L = 20 lg(r_direct / r_path) + 10 lg Π (1 - α_i)

Orders 1 and 2 arrive in the first ~20 ms; an absorber at their reflection
points removes them, which is where place() puts panels.

Where to sit: the modal response from 30 Hz to the Schroeder frequency at
every point of the floor at ear height; the spread of that response in dB is
how uneven the bass is there. The best seat is the most even point at least
0.5 m from every wall.
"""

from __future__ import annotations

import math
import string
from dataclasses import dataclass

import numpy as np

from .. import materials
from ..room import Point3, Room
from .modes import SPEED_OF_SOUND, room_modes

MID = (2, 3)            # indices of 500 Hz and 1 kHz
EPS = 1e-6
EAR_Z = 1.2
WALL_CLEARANCE = 0.5    # a seat closer than this to a wall doesn't count
TILE = {                # default piece (width, height) in m when there is no real product
    "panel_50": (0.6, 0.6), "panel_100": (0.6, 0.6), "curtain": (0.7, 2.4),
    "bookshelf": (0.8, 2.0), "rug": (2.0, 3.0),
}
LABEL = {"panel_50": "panel", "panel_100": "thick panel", "curtain": "curtain", "bookshelf": "bookshelf", "rug": "rug"}


def wall_name(i: int) -> str:
    return f"wall {string.ascii_uppercase[i % 26]}"


@dataclass
class Plane:
    name: str
    kind: str                     # wall | floor | ceiling
    index: int | None
    point: np.ndarray
    normal: np.ndarray            # unit, pointing into the room
    alpha: float                  # mid-band absorption, patches included
    start: np.ndarray | None = None   # walls: first corner, direction along, length
    along: np.ndarray | None = None
    length: float = 0.0


def _alpha_mid(material: str) -> float:
    a = materials.get(material).alpha
    return (a[MID[0]] + a[MID[1]]) / 2


def _surface_alpha(room: Room, kind: str, index: int | None) -> float:
    s = next((s for s in room.surfaces if s.kind == kind and (kind != "wall" or s.wall_index == index)), None)
    if s is None:
        return _alpha_mid("plaster_on_masonry")
    area = room.surface_area(kind, index)
    patch = sum(p.area_m2 for p in s.patches)
    total = _alpha_mid(s.material) * max(area - patch, 0.0) + sum(_alpha_mid(p.material) * p.area_m2 for p in s.patches)
    return total / area if area > 0 else _alpha_mid(s.material)


def _ccw(room: Room) -> bool:
    pts = room.floor
    return sum(pts[i].x * pts[(i + 1) % len(pts)].y - pts[(i + 1) % len(pts)].x * pts[i].y for i in range(len(pts))) > 0


def planes(room: Room) -> list[Plane]:
    out = [
        Plane("floor", "floor", None, np.zeros(3), np.array([0.0, 0.0, 1.0]), _surface_alpha(room, "floor", None)),
        Plane("ceiling", "ceiling", None, np.array([0.0, 0.0, room.height]), np.array([0.0, 0.0, -1.0]),
              _surface_alpha(room, "ceiling", None)),
    ]
    sign = 1.0 if _ccw(room) else -1.0
    n = len(room.floor)
    for i in range(n):
        a, b = room.floor[i], room.floor[(i + 1) % n]
        d = np.array([b.x - a.x, b.y - a.y])
        length = float(np.linalg.norm(d))
        u = d / length
        normal = sign * np.array([-u[1], u[0], 0.0])
        out.append(Plane(wall_name(i), "wall", i, np.array([a.x, a.y, 0.0]), normal, _surface_alpha(room, "wall", i),
                         start=np.array([a.x, a.y, 0.0]), along=np.array([u[0], u[1], 0.0]), length=length))
    return out


def _in_floor(room: Room, x: float, y: float) -> bool:
    inside = False
    pts = room.floor
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        if (a.y > y) != (b.y > y) and x < a.x + (y - a.y) * (b.x - a.x) / (b.y - a.y):
            inside = not inside
    return inside


def on_surface(room: Room, pl: Plane, p: np.ndarray) -> bool:
    if pl.kind == "wall":
        t = float(np.dot(p - pl.start, pl.along))
        return -EPS <= t <= pl.length + EPS and -EPS <= p[2] <= room.height + EPS
    return _in_floor(room, float(p[0]), float(p[1]))


def reflect(p: np.ndarray, pl: Plane) -> np.ndarray:
    return p - 2 * float(np.dot(p - pl.point, pl.normal)) * pl.normal


def _cross(a: np.ndarray, b: np.ndarray, pl: Plane) -> np.ndarray | None:
    """Where segment a→b crosses the plane, if it does."""
    da, db = float(np.dot(a - pl.point, pl.normal)), float(np.dot(b - pl.point, pl.normal))
    if da * db >= 0:
        return None
    return a + (da / (da - db)) * (b - a)


def _vec(p: Point3) -> np.ndarray:
    return np.array([p.x, p.y, p.z], dtype=float)


def _path(pls: list[Plane], pts: list[np.ndarray], length: float, direct: float) -> dict:
    absorb = math.prod(1 - pl.alpha for pl in pls)
    return {
        "order": len(pls),
        "surfaces": [pl.name for pl in pls],
        "points": [[round(float(v), 3) for v in p] for p in pts],
        "length_m": round(length, 3),
        "delay_ms": round((length - direct) / SPEED_OF_SOUND * 1000, 2),
        "level_db": round(20 * math.log10(direct / length) + 10 * math.log10(max(absorb, 1e-6)), 1),
    }


def early_reflections(room: Room, source: Point3, listener: Point3, max_order: int = 2,
                      range_db: float = 20.0) -> list[dict]:
    """Specular reflection paths of order 1 and 2, strongest first, down to
    range_db below the strongest one."""
    S, R = _vec(source), _vec(listener)
    direct = max(float(np.linalg.norm(R - S)), 0.05)
    pls = planes(room)
    out = []
    for a in pls:
        img = reflect(S, a)
        p = _cross(R, img, a)
        if p is not None and on_surface(room, a, p):
            out.append(_path([a], [p], float(np.linalg.norm(R - img)), direct))
    if max_order >= 2:
        for a in pls:
            img1 = reflect(S, a)
            if float(np.dot(img1 - a.point, a.normal)) >= 0:
                continue
            for b in pls:
                if b is a:
                    continue
                img2 = reflect(img1, b)
                pb = _cross(R, img2, b)
                if pb is None or not on_surface(room, b, pb):
                    continue
                pa = _cross(pb, img1, a)
                if pa is None or not on_surface(room, a, pa):
                    continue
                out.append(_path([a, b], [pa, pb], float(np.linalg.norm(R - img2)), direct))
    out.sort(key=lambda p: -p["level_db"])
    return [p for p in out if p["level_db"] >= out[0]["level_db"] - range_db] if out else []


def default_listener(room: Room, goal: str, source: Point3, seat: Point3 | None) -> Point3:
    """Voice: the mic, 25 cm in front of the talker towards the nearest wall
    (a desk against the wall). Otherwise the best seat, or the middle."""
    if goal == "voice":
        pl = min((p for p in planes(room) if p.kind == "wall"),
                 key=lambda p: float(np.dot(_vec(source) - p.point, p.normal)))
        m = _vec(source) - 0.25 * pl.normal
        return Point3(x=round(float(m[0]), 3), y=round(float(m[1]), 3), z=source.z)
    if seat:
        return seat
    xs, ys = [p.x for p in room.floor], [p.y for p in room.floor]
    return Point3(x=(min(xs) + max(xs)) / 2, y=(min(ys) + max(ys)) / 2, z=EAR_Z)


# ---------- where to sit ----------

def bass_evenness(room: Room, source: Point3, rt_low_s: float, f_hi: float, step_m: float = 0.25) -> dict:
    """Spread (dB) of the modal response from 30 Hz to f_hi at every point
    at ear height, and the most even point away from the walls.
    Rectangular rooms only (the modal model needs a box)."""
    xs, ys = [p.x for p in room.floor], [p.y for p in room.floor]
    x0, y0 = min(xs), min(ys)
    lx, ly, lz = max(xs) - x0, max(ys) - y0, room.height
    gx = np.arange(x0 + step_m / 2, x0 + lx, step_m)
    gy = np.arange(y0 + step_m / 2, y0 + ly, step_m)
    X, Y = np.meshgrid(gx - x0, gy - y0)
    freqs = np.geomspace(30.0, max(60.0, f_hi), 48)
    w = 2 * np.pi * freqs[:, None, None]
    delta = 6.91 / max(rt_low_s, 0.1)
    p = np.zeros((len(freqs), *X.shape), dtype=complex)
    for m in room_modes(lx, ly, lz, f_max=2 * f_hi) + [None]:
        n = m.n if m else (0, 0, 0)
        wn = 2 * np.pi * (m.freq_hz if m else 0.0)
        lam = math.prod(1.0 if k == 0 else 0.5 for k in n)
        psi_s = (math.cos(n[0] * math.pi * (source.x - x0) / lx) * math.cos(n[1] * math.pi * (source.y - y0) / ly)
                 * math.cos(n[2] * math.pi * source.z / lz))
        psi_r = np.cos(n[0] * np.pi * X / lx) * np.cos(n[1] * np.pi * Y / ly) * math.cos(n[2] * math.pi * EAR_Z / lz)
        p += psi_r[None] * psi_s / (lam * (wn**2 - w**2 + 2j * delta * w))
    db = 20 * np.log10(np.abs(p) + 1e-12)
    spread = db.std(axis=0)
    ok = ((X >= WALL_CLEARANCE) & (X <= lx - WALL_CLEARANCE) & (Y >= WALL_CLEARANCE) & (Y <= ly - WALL_CLEARANCE))
    masked = np.where(ok, spread, np.inf)
    j, i = np.unravel_index(int(np.argmin(masked)), masked.shape)
    return {
        "grid": {"xs": gx.round(3).tolist(), "ys": gy.round(3).tolist(), "values": spread.round(2).tolist(), "unit": "dB"},
        "seat": {"x": round(float(gx[i]), 3), "y": round(float(gy[j]), 3), "z": EAR_Z},
        "seat_spread_db": round(float(spread[j, i]), 1),
        "median_spread_db": round(float(np.median(spread[ok] if ok.any() else spread)), 1),
        "f_hi_hz": round(float(freqs[-1])),
    }


# ---------- where treatments go ----------

def _tile_ok(room: Room, pl: Plane, c: np.ndarray, w: float, h: float) -> bool:
    if pl.kind == "wall":
        t = float(np.dot(c - pl.start, pl.along))
        return w / 2 - EPS <= t <= pl.length - w / 2 + EPS and h / 2 - EPS <= c[2] <= room.height - h / 2 + EPS
    return all(_in_floor(room, c[0] + sx * w / 2, c[1] + sy * h / 2) for sx in (-0.99, 0.99) for sy in (-0.99, 0.99))


def _local(pl: Plane, p: np.ndarray) -> tuple[float, float]:
    """In-plane coordinates: (along the wall, height) or (x, y)."""
    if pl.kind == "wall":
        return float(np.dot(p - pl.start, pl.along)), float(p[2])
    return float(p[0]), float(p[1])


def _candidates(room: Room, pl: Plane, tid: str, w: float, h: float) -> list[np.ndarray]:
    step_w, step_h = max(w / 2, 0.1), max(h / 2, 0.1)
    out = []
    if pl.kind == "wall":
        if tid == "bookshelf":
            zs = [h / 2]                                          # stands on the floor
        elif tid == "curtain":
            zs = [min(room.height - 0.05, 2.6) - h / 2]           # hangs from a rail
        else:
            zs = list(np.arange(max(0.3 + h / 2, h / 2), room.height - h / 2 + EPS, step_h))
        for t in np.arange(w / 2, pl.length - w / 2 + EPS, step_w):
            for z in zs:
                out.append(pl.start + t * pl.along + np.array([0.0, 0.0, z]))
    else:
        xs, ys = [p.x for p in room.floor], [p.y for p in room.floor]
        z = 0.0 if pl.kind == "floor" else room.height
        for x in np.arange(min(xs) + w / 2, max(xs) - w / 2 + EPS, step_w):
            for y in np.arange(min(ys) + h / 2, max(ys) - h / 2 + EPS, step_h):
                out.append(np.array([x, y, z]))
    return [c for c in out if _tile_ok(room, pl, c, w, h)]


def _overlaps(a: tuple, b: tuple) -> bool:
    (u1, v1, w1, h1), (u2, v2, w2, h2) = a, b
    return abs(u1 - u2) < (w1 + w2) / 2 - 0.01 and abs(v1 - v2) < (h1 + h2) / 2 - 0.01


def place(room: Room, treatments: list[dict], reflections: list[dict],
          sizes: dict[str, tuple[float, float]] | None = None) -> dict:
    """Rectangles for every planned treatment, on the surfaces its kind can
    go on, strongest early reflections first, then around ear height.

    treatments: [{id, where, area_m2}], as the plan gives them.
    sizes: real product sizes (width, height in m) by treatment id.
    """
    pls = {p.name: p for p in planes(room)}
    walls = [p for p in pls.values() if p.kind == "wall"]
    windows = [p for p in walls if any(
        s.kind == "wall" and s.wall_index == p.index
        and (s.material.startswith("glass") or any(q.material.startswith("glass") for q in s.patches))
        for s in room.surfaces)]
    hits: dict[str, list[tuple[float, float, float]]] = {}
    for r in reflections:
        weight = 10 ** (r["level_db"] / 10)
        for name, pt in zip(r["surfaces"], r["points"]):
            u, v = _local(pls[name], np.array(pt))
            hits.setdefault(name, []).append((u, v, weight))

    taken: dict[str, list[tuple]] = {}
    rects, groups = [], []
    for t in treatments:
        tid, where = t["id"], t["where"]
        w, h = (sizes or {}).get(tid) or TILE.get(tid, (0.6, 0.6))
        if tid == "curtain":
            w = w / 2  # hung at double fullness: covers half its width
        if where == "wall":
            targets = walls
        elif where == "window":
            targets = windows or walls[:1]
        else:
            targets = [pls[where]] if where in pls else []
        count = max(1, round(t["area_m2"] / (w * h)))
        placed = []
        for _ in range(count):
            best, best_score = None, -1.0
            for pl in targets:
                for c in _candidates(room, pl, tid, w, h):
                    u, v = _local(pl, c)
                    box = (u, v, w, h)
                    if any(_overlaps(box, o) for o in taken.get(pl.name, [])):
                        continue
                    score = sum(wt for (hu, hv, wt) in hits.get(pl.name, [])
                                if abs(hu - u) <= w / 2 + 0.15 and abs(hv - v) <= h / 2 + 0.15)
                    if pl.kind == "wall" and tid.startswith("panel"):
                        score += 1e-4 / (1 + abs(v - EAR_Z))          # otherwise, ear height
                    if tid == "panel_100" and pl.kind == "wall":
                        score += 1e-4 * (u < 0.7 or u > pl.length - 0.7)  # and corners for bass
                    if score > best_score:
                        best, best_score = (pl, c, box), score
            if best is None:
                break
            pl, c, box = best
            taken.setdefault(pl.name, []).append(box)
            along = pl.along if pl.kind == "wall" else np.array([1.0, 0.0, 0.0])
            rect = {"id": tid, "surface": pl.name, "center": [round(float(v), 3) for v in c], "w": round(w, 3),
                    "h": round(h, 3), "normal": [round(float(v), 3) for v in pl.normal],
                    "along": [round(float(v), 3) for v in along]}
            rects.append(rect)
            placed.append((pl, box))
        groups += _describe(tid, placed, walls)
    return {"rects": rects, "groups": groups}


def _describe(tid: str, placed: list, walls: list[Plane]) -> list[str]:
    """One line per surface: how many pieces and where, measured from walls
    the user can find (they are lettered in the 3D view)."""
    by: dict[str, list] = {}
    for pl, box in placed:
        by.setdefault(pl.name, []).append((pl, box))
    first, last = walls[0], walls[-1]
    out = []
    for name, items in by.items():
        pl = items[0][0]
        k = len(items)
        what = f"{k} {LABEL.get(tid, tid)}{'s' if k > 1 else ''}"
        title = name[0].upper() + name[1:]
        boxes = sorted(b for _, b in items)
        if pl.kind == "wall":
            prev = walls[(pl.index - 1) % len(walls)].name
            spots = ", ".join(f"{u:.1f}" for u, *_ in boxes)
            if tid == "curtain":
                top = max(v + h / 2 for _, v, _, h in boxes)
                how = f"hanging from a rail {top:.1f} m high"
            elif tid == "bookshelf":
                how = "standing on the floor"
            else:
                spots = ", ".join(f"{u:.1f} m ({v:.1f} m high)" for u, v, *_ in boxes)
                out.append(f"{title}: {what}, centred {spots} from the corner with {prev}.")
                continue
            out.append(f"{title}: {what}, centred {spots} m from the corner with {prev}, {how}.")
        else:
            spots = "; ".join(
                f"{_dist(first, u, v):.1f} m from {first.name} and {_dist(last, u, v):.1f} m from {last.name}"
                for u, v, *_ in boxes)
            out.append(f"{title}: {what}, centred {spots}.")
    return out


def _dist(wall: Plane, x: float, y: float) -> float:
    return float(np.dot(np.array([x, y, 0.0]) - wall.point, wall.normal))


def reflections_after(room: Room, reflections: list[dict], rects: list[dict],
                      treatment_alpha: dict[str, float]) -> list[dict]:
    """The same paths with the treatments in place: a reflection point on a
    treatment takes the treatment's absorption instead of the surface's."""
    pls = {p.name: p for p in planes(room)}
    out = []
    for r in reflections:
        level, covered = r["level_db"], False
        for name, pt in zip(r["surfaces"], r["points"]):
            pl = pls[name]
            u, v = _local(pl, np.array(pt))
            for rc in rects:
                if rc["surface"] != name:
                    continue
                cu, cv = _local(pl, np.array(rc["center"]))
                if abs(u - cu) <= rc["w"] / 2 + 0.05 and abs(v - cv) <= rc["h"] / 2 + 0.05:
                    a_new = treatment_alpha.get(rc["id"], pl.alpha)
                    level += 10 * math.log10(max(1 - a_new, 1e-6) / max(1 - pl.alpha, 1e-6))
                    covered = True
                    break
        out.append({**r, "level_after_db": round(level, 1), "covered": covered})
    return out
