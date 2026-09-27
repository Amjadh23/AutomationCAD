"""Ship-structure rules: turn a job into the parts to draw. No DXF here.

Bulkhead coordinates: y is transverse (+ to starboard), z is height above baseline.
Frame coordinates: x = frame number x frame spacing, FR0 at x = 0.
"""
from __future__ import annotations

from dataclasses import dataclass

from .geometry import (
    EPS,
    BracketFitError,
    Point,
    bounding_box,
    bracket_triangle,
    clip_vertical,
    mirror_half_outline,
    polygon_area,
)
from .job import Job


@dataclass(frozen=True)
class Stiffener:
    y: float
    z_bottom: float
    z_top: float

    @property
    def length(self) -> float:
        return self.z_top - self.z_bottom


@dataclass(frozen=True)
class Bracket:
    corners: tuple[Point, Point, Point]  # (y, z)

    @property
    def area(self) -> float:
        return abs(polygon_area(self.corners))


@dataclass(frozen=True)
class Frame:
    number: int
    x: float


@dataclass(frozen=True)
class BulkheadParts:
    outline: tuple[Point, ...]
    stiffeners: tuple[Stiffener, ...]
    brackets: tuple[Bracket, ...]
    frames: tuple[Frame, ...]
    bulkhead_x: float
    bracket_problems: tuple[str, ...] = ()


def stiffener_positions(first_at: float, spacing: float, max_half_breadth: float) -> list[float]:
    """y = first_at + k * spacing while inside the half breadth, mirrored to port."""
    starboard = []
    k = 0
    while (y := first_at + k * spacing) < max_half_breadth - EPS:
        starboard.append(y)
        k += 1
    port = [-y for y in reversed(starboard) if y > EPS]
    return port + starboard


def build_parts(job: Job) -> BulkheadParts:
    """Never raises for rule problems: checks.run_checks reports them."""
    bh = job.bulkhead
    outline = mirror_half_outline(bh.outline_half)
    max_half_breadth = bounding_box(outline)[2]

    stiffeners = [
        Stiffener(y, z_low, z_high)
        for y in stiffener_positions(bh.stiffeners.first_at, bh.stiffeners.spacing, max_half_breadth)
        for z_low, z_high in clip_vertical(outline, y)
    ]

    ends = []
    if bh.brackets.bottom:
        ends.append(("bottom", (0.0, 1.0)))
    if bh.brackets.top:
        ends.append(("top", (0.0, -1.0)))
    brackets, problems = [], []
    for st in stiffeners:
        for which, inward in ends:
            end = (st.y, st.z_bottom if which == "bottom" else st.z_top)
            try:
                brackets.append(Bracket(bracket_triangle(outline, end, inward, bh.brackets.size)))
            except BracketFitError as exc:
                problems.append(f"{which} bracket of the stiffener at y={st.y:g}: {exc}")

    frames = tuple(Frame(n, n * job.frames.spacing) for n in range(job.frames.first, job.frames.last + 1))
    return BulkheadParts(
        outline=tuple(outline),
        stiffeners=tuple(stiffeners),
        brackets=tuple(brackets),
        frames=frames,
        bulkhead_x=bh.at_frame * job.frames.spacing,
        bracket_problems=tuple(problems),
    )
