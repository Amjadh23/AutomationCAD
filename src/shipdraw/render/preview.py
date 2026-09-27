"""PNG preview of a drawing, black on white like a plot."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ezdxf.addons.drawing import matplotlib as mpl_draw
from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration

if TYPE_CHECKING:
    from ezdxf.document import Drawing

_PLOT_STYLE = Configuration(color_policy=ColorPolicy.BLACK, background_policy=BackgroundPolicy.WHITE)
_MM_PER_INCH = 25.4


def render_png(doc: Drawing, path: Path, sheet_width_mm: float, sheet_height_mm: float, dpi: int = 100) -> None:
    mpl_draw.qsave(
        doc.modelspace(),
        path,
        bg="#FFFFFF",
        config=_PLOT_STYLE,
        dpi=dpi,
        size_inches=(sheet_width_mm / _MM_PER_INCH, sheet_height_mm / _MM_PER_INCH),
    )
