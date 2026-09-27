"""Bulkhead elevation looking forward: plate, CL/BL, stiffeners, brackets, labels, dimensions."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ezdxf.enums import TextEntityAlignment

from ..geometry import EPS, Point, bounding_box, clip_vertical
from .sheet import add_linear_dim, add_text

if TYPE_CHECKING:
    from ..job import Job
    from ..layout import SheetPlan
    from ..standard import Standard
    from ..structure import Bracket, BulkheadParts

# Paper-mm distances. Keep them inside layout.ELEVATION_PAD (left 25, right 80, bottom 45, top 15).
LINE_OVERRUN = 5  # CL and BL run this far past the plate
CHAIN_DIM = 12  # stiffener spacing chain, below the lowest point
OVERALL_DIM = 24  # overall breadth, below the chain
TITLE_GAP = 36  # top of the view title, below the lowest point
HEIGHT_DIM = 18  # overall height, left of the plate
LABEL_GAP = 15  # labels start this far right of the plate


def _centroid(bracket: Bracket) -> Point:
    return (sum(c[0] for c in bracket.corners) / 3, sum(c[1] for c in bracket.corners) / 3)


def draw_elevation(msp, job: Job, parts: BulkheadParts, standard: Standard, plan: SheetPlan) -> None:
    s = plan.scale
    dx, dy = plan.elevation_offset
    layers = standard.layers
    bh = job.bulkhead
    outline = list(parts.outline)
    min_y, min_z, max_y, max_z = bounding_box(outline)
    text_h = standard.text.label * s

    def at(y: float, z: float) -> Point:
        return (y + dx, z + dy)

    # Plate, centreline, baseline
    msp.add_lwpolyline([at(*p) for p in outline], close=True, dxfattribs={"layer": layers.plate.name})
    run = LINE_OVERRUN * s
    msp.add_line(at(0, min_z - run), at(0, max_z + run), dxfattribs={"layer": layers.centreline.name})
    msp.add_line(at(min_y - run, 0), at(max_y + run, 0), dxfattribs={"layer": layers.centreline.name})
    add_text(msp, "CL", at(0, max_z + run + s), text_h, layers.text.name, TextEntityAlignment.BOTTOM_CENTER)
    add_text(msp, "BL", at(min_y - run - s, 0), text_h, layers.text.name, TextEntityAlignment.MIDDLE_RIGHT)

    # Stiffeners and brackets
    for st in parts.stiffeners:
        msp.add_line(at(st.y, st.z_bottom), at(st.y, st.z_top), dxfattribs={"layer": layers.stiffener.name})
    for bracket in parts.brackets:
        msp.add_lwpolyline([at(*c) for c in bracket.corners], close=True, dxfattribs={"layer": layers.bracket.name})

    # Labels on the right, each with a straight leader to a typical item
    height = max_z - min_z
    labels: list[tuple[str, Point, float]] = []  # (text, target point, label z)
    ys = sorted({st.y for st in parts.stiffeners})
    panel_y = (ys[-1] + max_y) / 2 if ys else (min_y + max_y) / 2
    spans = clip_vertical(outline, panel_y)
    if spans:
        labels.append((f"PL {bh.plate.thickness:g} {bh.plate.grade}", (panel_y, sum(spans[0]) / 2), min_z + 0.8 * height))
    if parts.stiffeners:
        outer = max(parts.stiffeners, key=lambda st: (st.y, -st.z_bottom))
        target = (outer.y, (outer.z_bottom + outer.z_top) / 2)
        labels.append((f"{bh.stiffeners.profile} @ {bh.stiffeners.spacing:g} TYP.", target, min_z + 0.5 * height))
    if parts.brackets:
        typical = max(parts.brackets, key=lambda b: (_centroid(b)[0], -_centroid(b)[1]))
        size, t = bh.brackets.size, bh.brackets.thickness
        labels.append((f"BKT {size:g}x{size:g}x{t:g} TYP.", _centroid(typical), min_z + 0.2 * height))
    label_y = max_y + LABEL_GAP * s
    for text, target, label_z in labels:
        add_text(msp, text, at(label_y, label_z), text_h, layers.text.name, TextEntityAlignment.MIDDLE_LEFT)
        msp.add_line(at(label_y - s, label_z), at(*target), dxfattribs={"layer": layers.text.name})

    # Dimensions: spacing chain side-to-side through every stiffener, overall breadth, overall height
    lowest_end: dict[float, float] = {}
    for st in parts.stiffeners:
        lowest_end[st.y] = min(lowest_end.get(st.y, st.z_bottom), st.z_bottom)
    left_z = min(z for y, z in outline if abs(y - min_y) <= EPS)
    right_z = min(z for y, z in outline if abs(y - max_y) <= EPS)
    chain = [(min_y, left_z), *sorted(lowest_end.items()), (max_y, right_z)]
    dim_layer = layers.dim.name
    for p1, p2 in zip(chain, chain[1:]):
        add_linear_dim(msp, at(*p1), at(*p2), at(p1[0], min_z - CHAIN_DIM * s), 0, dim_layer)
    add_linear_dim(msp, at(*chain[0]), at(*chain[-1]), at(chain[0][0], min_z - OVERALL_DIM * s), 0, dim_layer)
    lowest = min(outline, key=lambda p: (p[1], p[0]))
    highest = max(outline, key=lambda p: (p[1], -p[0]))
    add_linear_dim(msp, at(*lowest), at(*highest), at(min_y - HEIGHT_DIM * s, lowest[1]), 90, dim_layer)

    add_text(
        msp,
        f"BULKHEAD AT FR{bh.at_frame} (LOOKING FWD)",
        at((min_y + max_y) / 2, min_z - TITLE_GAP * s),
        standard.text.view_title * s,
        layers.text.name,
        TextEntityAlignment.TOP_CENTER,
    )
