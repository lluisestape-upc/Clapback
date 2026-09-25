"""Room model shared by every input path.

Typed dimensions and the phone scan both produce a `Room`. The acoustics
engine only ever sees this schema, so a broken scan can't break the engine.

Coordinates are metres. The floor polygon lies in the x/y plane at z = 0 and
the ceiling is flat at z = height. Walls are implied: wall i runs from
floor[i] to floor[(i + 1) % n].
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

OCTAVE_BANDS_HZ = (125, 250, 500, 1000, 2000, 4000)

SurfaceKind = Literal["floor", "ceiling", "wall"]


class Point2(BaseModel):
    x: float
    y: float


class Point3(BaseModel):
    x: float
    y: float
    z: float


class Surface(BaseModel):
    """One surface and what it is made of.

    `wall_index` is set only for walls. `patches` lets part of a surface be a
    different material (a window in a wall, a rug on a floor) without
    splitting the geometry.
    """

    kind: SurfaceKind
    wall_index: int | None = None
    material: str = Field(description="id from data/materials.json")
    patches: list[Patch] = Field(default_factory=list)


class Patch(BaseModel):
    material: str
    area_m2: float = Field(gt=0)


class Room(BaseModel):
    name: str = "room"
    floor: list[Point2] = Field(min_length=3)
    height: float = Field(gt=0)
    surfaces: list[Surface] = Field(default_factory=list)
    source: Point3 | None = None
    receivers: list[Point3] = Field(default_factory=list)

    @classmethod
    def box(cls, length: float, width: float, height: float, **kw) -> Room:
        """Rectangular room from typed dimensions (the MVP input)."""
        floor = [
            Point2(x=0, y=0),
            Point2(x=length, y=0),
            Point2(x=length, y=width),
            Point2(x=0, y=width),
        ]
        return cls(floor=floor, height=height, **kw)

    @model_validator(mode="after")
    def _check_walls(self) -> Room:
        n = len(self.floor)
        for s in self.surfaces:
            if s.kind == "wall" and (s.wall_index is None or not 0 <= s.wall_index < n):
                raise ValueError(f"wall_index must be in 0..{n - 1}")
        return self

    # Geometry --------------------------------------------------------------

    def floor_area(self) -> float:
        """Shoelace formula; works for any simple polygon."""
        pts = self.floor
        s = 0.0
        for i, p in enumerate(pts):
            q = pts[(i + 1) % len(pts)]
            s += p.x * q.y - q.x * p.y
        return abs(s) / 2

    def wall_length(self, i: int) -> float:
        p, q = self.floor[i], self.floor[(i + 1) % len(self.floor)]
        return ((q.x - p.x) ** 2 + (q.y - p.y) ** 2) ** 0.5

    def volume(self) -> float:
        return self.floor_area() * self.height

    def surface_area(self, kind: SurfaceKind, wall_index: int | None = None) -> float:
        if kind in ("floor", "ceiling"):
            return self.floor_area()
        assert wall_index is not None
        return self.wall_length(wall_index) * self.height

    def total_area(self) -> float:
        walls = sum(self.wall_length(i) for i in range(len(self.floor))) * self.height
        return 2 * self.floor_area() + walls

    def is_rectangular(self, tol: float = 0.05) -> bool:
        """True if the floor is a 4-corner polygon with right angles (within tol)."""
        if len(self.floor) != 4:
            return False
        for i in range(4):
            a, b, c = self.floor[i - 1], self.floor[i], self.floor[(i + 1) % 4]
            v1 = (a.x - b.x, a.y - b.y)
            v2 = (c.x - b.x, c.y - b.y)
            dot = v1[0] * v2[0] + v1[1] * v2[1]
            n1 = (v1[0] ** 2 + v1[1] ** 2) ** 0.5
            n2 = (v2[0] ** 2 + v2[1] ** 2) ** 0.5
            if abs(dot / (n1 * n2)) > tol:
                return False
        return True


Surface.model_rebuild()
