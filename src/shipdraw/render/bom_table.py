"""Bill of materials drawn as a table in the BOM zone."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ezdxf.enums import TextEntityAlignment

from .sheet import add_text

if TYPE_CHECKING:
    from ..bom import Bom
    from ..layout import SheetPlan
    from ..standard import Standard

# (header, width in paper mm)
COLUMNS: tuple[tuple[str, float], ...] = (
    ("ITEM", 12),
    ("DESCRIPTION", 80),
    ("QTY", 14),
    ("LENGTH (mm)", 30),
    ("WEIGHT (kg)", 30),
)
_RIGHT_ALIGNED = {0, 2, 3, 4}  # numeric columns (body rows only)
ROW_HEIGHT = 7.0  # paper mm
CELL_PAD = 1.5  # paper mm
CAPTION_SPACE = 9.0  # paper mm from the zone top to the table top


def bom_cells(bom: Bom) -> list[tuple[str, ...]]:
    cells = [tuple(header for header, _ in COLUMNS)]
    for row in bom.rows:
        length = "-" if row.length_mm is None else f"{row.length_mm:.0f}"
        cells.append((str(row.item), row.description, str(row.qty), length, f"{row.weight_kg:.1f}"))
    cells.append(("", "TOTAL", "", "", f"{bom.total_weight_kg:.1f}"))
    return cells


def draw_bom_table(msp, bom: Bom, standard: Standard, plan: SheetPlan) -> None:
    s = plan.scale
    layer = standard.layers.bom.name
    x0, zone_top = plan.bom_top_left
    add_text(msp, "BILL OF MATERIALS", (x0, zone_top - s), standard.text.view_title * s, layer, TextEntityAlignment.TOP_LEFT)

    cells = bom_cells(bom)
    row_h = ROW_HEIGHT * s
    table_top = zone_top - CAPTION_SPACE * s
    table_bottom = table_top - len(cells) * row_h
    xs = [x0]
    for _, width in COLUMNS:
        xs.append(xs[-1] + width * s)

    for i in range(len(cells) + 1):
        y = table_top - i * row_h
        msp.add_line((xs[0], y), (xs[-1], y), dxfattribs={"layer": layer})
    for x in xs:
        msp.add_line((x, table_top), (x, table_bottom), dxfattribs={"layer": layer})

    text_h, pad = standard.text.bom * s, CELL_PAD * s
    for i, row in enumerate(cells):
        y = table_top - (i + 0.5) * row_h
        for j, value in enumerate(row):
            if not value:
                continue
            if i > 0 and j in _RIGHT_ALIGNED:
                add_text(msp, value, (xs[j + 1] - pad, y), text_h, layer, TextEntityAlignment.MIDDLE_RIGHT)
            else:
                add_text(msp, value, (xs[j] + pad, y), text_h, layer, TextEntityAlignment.MIDDLE_LEFT)
