"""Sheet layout: choose the drawing scale and place each view in its zone. No DXF here.

The sheet is drawn in model space at 1:1 mm with the border scaled up, so a paper
size of P mm becomes P * scale model units.
"""
from __future__ import annotations

from dataclasses import dataclass

from .geometry import bounding_box
from .standard import Standard, Zone
from .structure import BulkheadParts


@dataclass(frozen=True)
class Pad:
    """Paper mm reserved around a view's geometry for its annotations."""

    left: float
    right: float
    bottom: float
    top: float


# The render/ view modules draw their annotations inside these pads.
ELEVATION_PAD = Pad(left=25, right=80, bottom=45, top=15)
FRAMES_PAD = Pad(left=10, right=10, bottom=35, top=22)

Box = tuple[float, float, float, float]


class NoScaleFitsError(ValueError):
    """The views do not fit the sheet at any allowed scale. The message is user-facing."""


@dataclass(frozen=True)
class SheetPlan:
    scale: int
    elevation_offset: tuple[float, float]
    frames_offset: tuple[float, float]
    bom_top_left: tuple[float, float]
    title_block_origin: tuple[float, float]


def _fits(zone: Zone, box: Box, pad: Pad, scale: int) -> bool:
    width, height = box[2] - box[0], box[3] - box[1]
    return (
        width / scale + pad.left + pad.right <= zone.width + 1e-9
        and height / scale + pad.bottom + pad.top <= zone.height + 1e-9
    )


def _centring_offset(zone: Zone, box: Box, pad: Pad, scale: int) -> tuple[float, float]:
    """Offset that centres the box plus its pad inside the zone, in model units."""
    min_x, min_y, max_x, max_y = box
    content_w = (max_x - min_x) + (pad.left + pad.right) * scale
    content_h = (max_y - min_y) + (pad.bottom + pad.top) * scale
    left = zone.x * scale + (zone.width * scale - content_w) / 2
    bottom = zone.y * scale + (zone.height * scale - content_h) / 2
    return (left + pad.left * scale - min_x, bottom + pad.bottom * scale - min_y)


def plan_sheet(parts: BulkheadParts, standard: Standard) -> SheetPlan:
    sheet, zones = standard.sheet, standard.sheet.zones
    elevation_box = bounding_box(parts.outline)
    frames_box = (parts.frames[0].x, 0.0, parts.frames[-1].x, 0.0)
    views = [(zones.elevation, elevation_box, ELEVATION_PAD), (zones.frames, frames_box, FRAMES_PAD)]

    for scale in sorted(sheet.scales):
        if all(_fits(zone, box, pad, scale) for zone, box, pad in views):
            break
    else:
        allowed = ", ".join(f"1:{s}" for s in sorted(sheet.scales))
        raise NoScaleFitsError(f"the drawing does not fit the {sheet.name} sheet at any allowed scale ({allowed})")

    tb, bom = standard.title_block, zones.bom
    return SheetPlan(
        scale=scale,
        elevation_offset=_centring_offset(zones.elevation, elevation_box, ELEVATION_PAD, scale),
        frames_offset=_centring_offset(zones.frames, frames_box, FRAMES_PAD, scale),
        bom_top_left=(bom.x * scale, (bom.y + bom.height) * scale),
        title_block_origin=((sheet.width - sheet.margin - tb.width) * scale, sheet.margin * scale),
    )
