"""Frame layout strip: frame ticks and numbers, spacing chain, bulkhead position."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ezdxf.enums import TextEntityAlignment

from ..geometry import Point
from .sheet import add_linear_dim, add_text

if TYPE_CHECKING:
    from ..job import Job
    from ..layout import SheetPlan
    from ..standard import Standard
    from ..structure import BulkheadParts

# Paper-mm distances. Keep them inside layout.FRAMES_PAD (bottom 35, top 22).
TICK = 8  # frame tick height above the strip baseline
LABEL_GAP = 2  # between a tick and its frame number, and between rows of text
CHAIN_DIM = 10  # spacing chain, below the strip
TITLE_GAP = 22  # top of the view title, below the strip


def draw_frame_strip(msp, job: Job, parts: BulkheadParts, standard: Standard, plan: SheetPlan) -> None:
    s = plan.scale
    dx, dy = plan.frames_offset
    layers = standard.layers
    first, last = parts.frames[0], parts.frames[-1]
    tick = TICK * s
    number_h = standard.text.frame_number * s

    def at(x: float, y: float = 0.0) -> Point:
        return (x + dx, y + dy)

    msp.add_line(at(first.x), at(last.x), dxfattribs={"layer": layers.frame.name})
    for frame in parts.frames:
        msp.add_line(at(frame.x), at(frame.x, tick), dxfattribs={"layer": layers.frame.name})
        add_text(
            msp, f"FR{frame.number}", at(frame.x, tick + LABEL_GAP * s), number_h, layers.text.name,
            TextEntityAlignment.BOTTOM_CENTER,
        )

    msp.add_line(at(parts.bulkhead_x), at(parts.bulkhead_x, tick), dxfattribs={"layer": layers.plate.name})
    add_text(
        msp, "BHD", at(parts.bulkhead_x, tick + 2 * LABEL_GAP * s + number_h), number_h, layers.text.name,
        TextEntityAlignment.BOTTOM_CENTER,
    )

    for a, b in zip(parts.frames, parts.frames[1:]):
        add_linear_dim(msp, at(a.x), at(b.x), at(a.x, -CHAIN_DIM * s), 0, layers.dim.name)

    add_text(
        msp,
        f"FRAME LAYOUT FR{first.number}-FR{last.number}",
        at((first.x + last.x) / 2, -TITLE_GAP * s),
        standard.text.view_title * s,
        layers.text.name,
        TextEntityAlignment.TOP_CENTER,
    )
