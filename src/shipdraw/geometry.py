"""Pure 2-D geometry for straight-line outlines. No DXF and no ship knowledge.

Points are (x, y) tuples in millimetres. A polygon is a list of vertices with an
implied closing edge from the last vertex back to the first.
"""
from __future__ import annotations

import math
from collections.abc import Sequence

Point = tuple[float, float]
EPS = 1e-6


class BracketFitError(ValueError):
    """A bracket cannot be placed at a stiffener end. The message is user-facing."""


def mirror_half_outline(half: Sequence[Point]) -> list[Point]:
    """Full outline from a half outline on the +x side that starts and ends on x = 0."""
    points = [(float(x), float(y)) for x, y in half]
    mirrored = [(-x, y) for x, y in reversed(points[1:-1])]
    return remove_collinear(points + mirrored)


def remove_collinear(points: Sequence[Point]) -> list[Point]:
    """Drop duplicate vertices and vertices lying on a straight run between their neighbours."""
    pts = list(points)
    changed = True
    while changed and len(pts) >= 3:
        changed = False
        for i in range(len(pts)):
            prev, cur, nxt = pts[i - 1], pts[i], pts[(i + 1) % len(pts)]
            ax, ay = cur[0] - prev[0], cur[1] - prev[1]
            bx, by = nxt[0] - cur[0], nxt[1] - cur[1]
            la, lb = math.hypot(ax, ay), math.hypot(bx, by)
            duplicate = la < EPS or lb < EPS
            straight = not duplicate and abs(ax * by - ay * bx) <= EPS * la * lb and ax * bx + ay * by > 0
            if duplicate or straight:
                del pts[i]
                changed = True
                break
    return pts


def polygon_area(points: Sequence[Point]) -> float:
    """Signed area (shoelace formula): positive for counter-clockwise vertex order."""
    n = len(points)
    return 0.5 * sum(
        points[i][0] * points[(i + 1) % n][1] - points[(i + 1) % n][0] * points[i][1] for i in range(n)
    )


def bounding_box(points: Sequence[Point]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _side(a: Point, b: Point, p: Point) -> int:
    """+1 if p is left of the directed line a→b, -1 if right, 0 if within EPS of it."""
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    if length < EPS:
        return 0
    distance = ((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])) / length
    return 0 if abs(distance) <= EPS else (1 if distance > 0 else -1)


def _within_box(a: Point, b: Point, p: Point) -> bool:
    return (
        min(a[0], b[0]) - EPS <= p[0] <= max(a[0], b[0]) + EPS
        and min(a[1], b[1]) - EPS <= p[1] <= max(a[1], b[1]) + EPS
    )


def _on_segment(a: Point, b: Point, p: Point) -> bool:
    return _side(a, b, p) == 0 and _within_box(a, b, p)


def segments_intersect(p1: Point, p2: Point, q1: Point, q2: Point) -> bool:
    d1, d2 = _side(q1, q2, p1), _side(q1, q2, p2)
    d3, d4 = _side(p1, p2, q1), _side(p1, p2, q2)
    if d1 * d2 < 0 and d3 * d4 < 0:
        return True
    return (
        (d1 == 0 and _within_box(q1, q2, p1))
        or (d2 == 0 and _within_box(q1, q2, p2))
        or (d3 == 0 and _within_box(p1, p2, q1))
        or (d4 == 0 and _within_box(p1, p2, q2))
    )


def is_simple(points: Sequence[Point]) -> bool:
    """True if no two edges cross or touch, apart from neighbours sharing their common vertex."""
    n = len(points)
    if n < 3:
        return False
    edges = [(points[i], points[(i + 1) % n]) for i in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            (a1, a2), (b1, b2) = edges[i], edges[j]
            if j == i + 1 or (i == 0 and j == n - 1):
                shared, other_a, other_b = (a2, a1, b2) if j == i + 1 else (a1, a2, b1)
                folds_back = _side(shared, other_a, other_b) == 0 and (
                    (other_a[0] - shared[0]) * (other_b[0] - shared[0])
                    + (other_a[1] - shared[1]) * (other_b[1] - shared[1])
                    > 0
                )
                if folds_back:
                    return False
                continue
            if segments_intersect(a1, a2, b1, b2):
                return False
    return True


def outline_problems(points: Sequence[Point]) -> list[str]:
    if len(points) < 3:
        return [f"outline needs at least 3 distinct corners, got {len(points)}"]
    if abs(polygon_area(points)) < 1.0:
        return ["outline has zero area"]
    if not is_simple(points):
        return ["outline crosses itself"]
    return []


def clip_vertical(polygon: Sequence[Point], x: float) -> list[tuple[float, float]]:
    """Parts of the vertical line at x inside the polygon, as (y_low, y_high), bottom to top."""
    ys = []
    n = len(polygon)
    for i in range(n):
        (x1, y1), (x2, y2) = polygon[i], polygon[(i + 1) % n]
        if (x1 <= x < x2) or (x2 <= x < x1):  # half-open, so a vertex is counted once
            ys.append(y1 + (x - x1) * (y2 - y1) / (x2 - x1))
    ys.sort()
    return [(ys[k], ys[k + 1]) for k in range(0, len(ys) - 1, 2) if ys[k + 1] - ys[k] > EPS]


def contains_point(polygon: Sequence[Point], p: Point) -> bool:
    """True if p is inside the polygon or on its boundary."""
    n = len(polygon)
    if any(_on_segment(polygon[i], polygon[(i + 1) % n], p) for i in range(n)):
        return True
    inside = False
    for i in range(n):
        (x1, y1), (x2, y2) = polygon[i], polygon[(i + 1) % n]
        if (y1 > p[1]) != (y2 > p[1]):
            if p[0] < x1 + (p[1] - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
    return inside


def bracket_triangle(
    polygon: Sequence[Point], end: Point, inward: Point, size: float
) -> tuple[Point, Point, Point]:
    """Triangular bracket at a stiffener end.

    end:    the stiffener end point; it lies on the outline.
    inward: unit vector along the stiffener, pointing into the plate.
    One leg runs `size` along the stiffener. The other runs `size` along the outline
    edge that leaves `end` towards the centreline (x = 0); from x = 0 itself, towards +x.
    """
    candidates = []  # (|x| of the edge's far end, unit direction, length available)
    n = len(polygon)
    for i in range(n):
        a, b = polygon[i], polygon[(i + 1) % n]
        if not _on_segment(a, b, end):
            continue
        for far in (a, b):
            length = math.hypot(far[0] - end[0], far[1] - end[1])
            if length <= EPS:
                continue
            direction = ((far[0] - end[0]) / length, (far[1] - end[1]) / length)
            if abs(end[0]) <= EPS:
                towards_centre = direction[0] > EPS
            else:
                towards_centre = direction[0] * end[0] < -EPS
            if towards_centre:
                candidates.append((abs(far[0]), direction, length))
    if not candidates:
        raise BracketFitError(f"no outline edge runs from ({end[0]:g}, {end[1]:g}) towards the centreline")
    _, direction, length = min(candidates, key=lambda c: c[0])
    if length < size - EPS:
        raise BracketFitError(
            f"bracket at ({end[0]:g}, {end[1]:g}) needs {size:g} mm along the outline, "
            f"but the edge towards the centreline is only {length:.0f} mm"
        )
    ex, ey = end
    return (
        (ex, ey),
        (ex + inward[0] * size, ey + inward[1] * size),
        (ex + direction[0] * size, ey + direction[1] * size),
    )
