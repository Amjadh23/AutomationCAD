"""Previews of a drawing: PNG (black on white, like a plot) and SVG (CAD colours on a dark sheet)."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ezdxf.addons.drawing import Frontend, RenderContext, layout, svg
from ezdxf.addons.drawing import matplotlib as mpl_draw
from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration

if TYPE_CHECKING:
    from ezdxf.document import Drawing

SCREEN_BACKGROUND = "#0d1117"
_PLOT_STYLE = Configuration(color_policy=ColorPolicy.BLACK, background_policy=BackgroundPolicy.WHITE)
_SCREEN_STYLE = Configuration(
    color_policy=ColorPolicy.COLOR, background_policy=BackgroundPolicy.CUSTOM, custom_bg_color=SCREEN_BACKGROUND
)
_MM_PER_INCH = 25.4


def render_png(doc: Drawing, path: Path, sheet_width_mm: float, sheet_height_mm: float, dpi: int = 150) -> None:
    # Below ~150 dpi the rasteriser drops strokes from the 1.8 mm title-block captions.
    mpl_draw.qsave(
        doc.modelspace(),
        path,
        bg="#FFFFFF",
        config=_PLOT_STYLE,
        dpi=dpi,
        size_inches=(sheet_width_mm / _MM_PER_INCH, sheet_height_mm / _MM_PER_INCH),
    )


def render_svg(doc: Drawing, sheet_width_mm: float, sheet_height_mm: float) -> str:
    """The whole sheet as SVG markup, in AutoCAD layer colours on a dark background."""
    backend = svg.SVGBackend()
    Frontend(RenderContext(doc), backend, config=_SCREEN_STYLE).draw_layout(doc.modelspace())
    page = layout.Page(sheet_width_mm, sheet_height_mm, layout.Units.mm)
    return backend.get_string(page, settings=layout.Settings(fit_page=True), xml_declaration=False)
