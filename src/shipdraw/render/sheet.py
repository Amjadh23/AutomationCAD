"""DXF document setup and sheet furniture: layers, dimension style, border, title block."""
from __future__ import annotations

from typing import TYPE_CHECKING

import ezdxf
from ezdxf import units
from ezdxf.enums import TextEntityAlignment

from ..config import ConfigError

if TYPE_CHECKING:
    from ezdxf.document import Drawing

    from ..job import Job
    from ..layout import SheetPlan
    from ..standard import Standard

DIMSTYLE = "SHIPDRAW"
TITLE_BLOCK = "SD_TITLE"
_FIELD_LABEL_HEIGHT = 1.8  # paper mm
_FIELD_LABEL_GAP = 1.5  # paper mm between a field's value and its caption


def new_document(standard: Standard, scale: int) -> Drawing:
    doc = ezdxf.new("R2018", setup=True, units=units.MM)
    doc.header["$MEASUREMENT"] = 1  # metric
    doc.header["$LTSCALE"] = float(scale)  # linetype patterns sized for the plotted sheet
    for style in standard.layers.all():
        if style.linetype not in doc.linetypes:
            raise ConfigError(f"layer {style.name}: linetype {style.linetype!r} is not available")
        doc.layers.add(style.name, color=style.color, linetype=style.linetype, lineweight=style.lineweight)
    dim = standard.dimension
    doc.dimstyles.new(
        DIMSTYLE,
        dxfattribs={
            "dimscale": scale,
            "dimtxt": dim.text_height,
            "dimasz": dim.arrow_size,
            "dimexe": dim.extension_beyond,
            "dimexo": dim.extension_offset,
            "dimgap": dim.text_gap,
            "dimdec": 0,
            "dimzin": 8,  # suppress trailing zeros
            "dimtad": 1,  # text above the dimension line
        },
    )
    return doc


def add_text(layout, text: str, point, height: float, layer: str, align=TextEntityAlignment.LEFT):
    return layout.add_text(text, height=height, dxfattribs={"layer": layer}).set_placement(point, align=align)


def add_linear_dim(msp, p1, p2, base, angle: float, layer: str) -> None:
    msp.add_linear_dim(
        base=base, p1=p1, p2=p2, angle=angle, dimstyle=DIMSTYLE, dxfattribs={"layer": layer}
    ).render()


def draw_border(msp, standard: Standard, scale: int) -> None:
    sheet = standard.sheet
    layer = {"layer": standard.layers.border.name}
    w, h, m = sheet.width * scale, sheet.height * scale, sheet.margin * scale
    msp.add_lwpolyline([(0, 0), (w, 0), (w, h), (0, h)], close=True, dxfattribs=layer)
    msp.add_lwpolyline([(m, m), (w - m, m), (w - m, h - m), (m, h - m)], close=True, dxfattribs=layer)


def title_values(job: Job, scale: int) -> dict[str, str]:
    p = job.project
    return {
        "PROJECT": p.name,
        "DWG_NO": p.drawing_no,
        "TITLE": p.title,
        "SCALE": f"1:{scale}",
        "DRAWN": p.drawn_by,
        "DATE": p.date.isoformat(),
        "REV": p.revision,
    }


def draw_title_block(doc: Drawing, job: Job, standard: Standard, plan: SheetPlan) -> None:
    """Title block defined in paper mm, inserted scaled; its fields are editable attributes."""
    tb = standard.title_block
    layer = standard.layers.title.name
    on_layer = {"layer": layer}
    block = doc.blocks.new(TITLE_BLOCK)
    block.add_lwpolyline([(0, 0), (tb.width, 0), (tb.width, tb.height), (0, tb.height)], close=True, dxfattribs=on_layer)
    for x1, y1, x2, y2 in tb.lines:
        block.add_line((x1, y1), (x2, y2), dxfattribs=on_layer)
    for field in tb.fields:
        add_text(block, field.label, (field.x, field.y + field.height + _FIELD_LABEL_GAP), _FIELD_LABEL_HEIGHT, layer)
        block.add_attdef(field.tag, insert=(field.x, field.y), height=field.height, dxfattribs={**on_layer, "prompt": field.label})

    ref = doc.modelspace().add_blockref(
        TITLE_BLOCK, plan.title_block_origin, dxfattribs={"layer": layer, "xscale": plan.scale, "yscale": plan.scale}
    )
    ref.add_auto_attribs(title_values(job, plan.scale))
    for attrib in ref.attribs:
        attrib.dxf.layer = layer
