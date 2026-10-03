"""Drawing files as bytes, for downloads."""
from __future__ import annotations

import io
import tempfile
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from .preview import render_png

if TYPE_CHECKING:
    from ezdxf.document import Drawing

_PNG_LOCK = threading.Lock()  # matplotlib's pyplot is not thread-safe


def dxf_bytes(doc: Drawing) -> bytes:
    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue().encode(doc.output_encoding)


def png_bytes(doc: Drawing, sheet_width_mm: float, sheet_height_mm: float) -> bytes:
    with _PNG_LOCK, tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "sheet.png"
        render_png(doc, path, sheet_width_mm, sheet_height_mm)
        return path.read_bytes()
