# Drawing Web Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local web page with plain-language measurement boxes, a live preview of the real drawing, plain-language messages, and export buttons for the DXF, PNG, CSV and ZIP files. A visual design pass follows once the functionality is verified.

**Architecture:**

- The engine gains `render_drawing()`, which builds the drawing in memory, plus helpers that turn a drawing into SVG, DXF bytes or PNG bytes.
- `shipdraw.web` adds three layers:
  - a pure form↔job mapping (`form.py`);
  - an HTTP-free service (`api.py`);
  - a standard-library HTTP server (`server.py`).
- The page itself is static HTML, CSS and JS with no build step.
- `shipdraw serve` starts it, and `Start drawing tool.bat` wraps that command.

**Tech Stack:** Python 3.13 standard library `http.server`, plus ezdxf (`SVGBackend`), pydantic and pytest. The page uses plain HTML, CSS and JavaScript.

**Spec:** `docs/superpowers/specs/2026-10-03-drawing-web-page-design.md`

## Global Constraints

- Everything from the engine plan still applies:
  - only `src/shipdraw/render/` imports ezdxf or matplotlib;
  - layers are referred to by role;
  - user-facing messages are plain language.
- The server binds to `127.0.0.1` only. A `Host` header other than `127.0.0.1:<port>` or `localhost:<port>` gets **403**.
- The page loads nothing from the internet: no CDN and no web fonts.
- The preview is the engine's own drawing (ezdxf DXF → SVG), never a re-implementation in JavaScript.
- Branch: `feat/drawing-web-page`, created from `feat/bulkhead-engine`. Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Phase 2 (Task 7) is iterative visual work. Its acceptance criteria are written down, but its code is produced while iterating against screenshots. That is the one deliberate exception to "full code in the plan".

---

### Task 1: Render a drawing in memory (SVG, DXF bytes, PNG bytes)

**Files:**
- Modify (full rewrite): `src/shipdraw/pipeline.py`, `src/shipdraw/render/preview.py`
- Create: `src/shipdraw/render/files.py`
- Test: `tests/test_render_files.py`

**Interfaces:**
- Produces:
  - `pipeline.Rendered(report, parts, plan=None, bom=None, doc=None)`
  - `pipeline.render_drawing(job, standard, profiles) -> Rendered`
  - `render.preview.render_svg(doc, sheet_width_mm, sheet_height_mm) -> str`
  - `render.files.dxf_bytes(doc) -> bytes`
  - `render.files.png_bytes(doc, sheet_width_mm, sheet_height_mm) -> bytes`
- `build()` behaviour is unchanged, and the existing tests must stay green.

- [ ] **Step 1: Write the failing tests**

`tests/test_render_files.py`:

```python
import io

import ezdxf
import pytest

from shipdraw.job import Job
from shipdraw.pipeline import render_drawing
from shipdraw.render.files import dxf_bytes, png_bytes
from shipdraw.render.preview import render_svg


@pytest.fixture
def example_doc(example_job, standard, shipped_profiles):
    return render_drawing(example_job, standard, shipped_profiles).doc


def test_render_drawing_returns_everything_when_checks_pass(example_job, standard, shipped_profiles):
    rendered = render_drawing(example_job, standard, shipped_profiles)
    assert rendered.report.ok and rendered.doc is not None
    assert rendered.plan.scale == 20 and len(rendered.bom.rows) == 4
    assert len(rendered.parts.stiffeners) == 14


def test_render_drawing_has_no_document_when_checks_fail(job_dict, standard, shipped_profiles):
    job_dict["bulkhead"]["at_frame"] = 35
    rendered = render_drawing(Job.model_validate(job_dict), standard, shipped_profiles)
    assert not rendered.report.ok
    assert rendered.doc is None and rendered.bom is None and rendered.plan is None


def test_dxf_bytes_round_trip(example_doc):
    reread = ezdxf.read(io.StringIO(dxf_bytes(example_doc).decode("utf-8")))
    assert not reread.audit().has_errors
    assert len(reread.modelspace().query("DIMENSION")) == 27


def test_png_bytes(example_doc):
    assert png_bytes(example_doc, 841, 594)[:8] == b"\x89PNG\r\n\x1a\n"


def test_svg_preview_uses_layer_colours(example_doc):
    svg = render_svg(example_doc, 841, 594)
    assert svg.startswith("<svg") and 'viewBox="0 0 1000000' in svg
    assert "#00ff00" in svg  # STIFFENER layer is ACI 3, green
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `.venv/Scripts/python -m pytest tests/test_render_files.py -q`
Expected: collection ERROR `cannot import name 'render_drawing'`

- [ ] **Step 3: Implement**

`src/shipdraw/render/preview.py`:

```python
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
```

`src/shipdraw/render/files.py`:

```python
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
```

`src/shipdraw/pipeline.py`:

```python
"""The build pipeline: job → checks → drawing (in memory) → files.

Called by the CLI, by the drawing page, and later by the MCP server (build #2).
"""
from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from .bom import Bom, bom_csv, build_bom
from .checks import CheckReport, run_checks
from .job import Job
from .layout import SheetPlan, plan_sheet
from .profiles import ProfileLibrary
from .render.bom_table import draw_bom_table
from .render.bulkhead_view import draw_elevation
from .render.frame_view import draw_frame_strip
from .render.preview import render_png
from .render.sheet import draw_border, draw_title_block, new_document
from .standard import Standard
from .structure import BulkheadParts, build_parts

if TYPE_CHECKING:
    from ezdxf.document import Drawing


@dataclass(frozen=True)
class Rendered:
    """Everything the engine produced for one job. plan, bom and doc are None when the checks failed."""

    report: CheckReport
    parts: BulkheadParts
    plan: SheetPlan | None = None
    bom: Bom | None = None
    doc: Drawing | None = None


@dataclass(frozen=True)
class BuildResult:
    job: Job
    report: CheckReport
    scale: int | None
    stiffener_count: int
    bracket_count: int
    total_weight_kg: float | None
    seconds: float
    files: tuple[Path, ...] = ()

    @property
    def ok(self) -> bool:
        return self.report.ok


def render_drawing(job: Job, standard: Standard, profiles: ProfileLibrary) -> Rendered:
    parts = build_parts(job)
    report = run_checks(job, parts, standard, profiles)
    if not report.ok:
        return Rendered(report, parts)

    plan = plan_sheet(parts, standard)
    bom = build_bom(job, parts, profiles)
    doc = new_document(standard, plan.scale)
    msp = doc.modelspace()
    draw_border(msp, standard, plan.scale)
    draw_title_block(doc, job, standard, plan)
    draw_elevation(msp, job, parts, standard, plan)
    draw_frame_strip(msp, job, parts, standard, plan)
    draw_bom_table(msp, bom, standard, plan)
    return Rendered(report, parts, plan, bom, doc)


def build(
    job: Job, standard: Standard, profiles: ProfileLibrary, out_dir: Path, *, preview: bool = True
) -> BuildResult:
    started = time.perf_counter()
    rendered = render_drawing(job, standard, profiles)
    report, parts = rendered.report, rendered.parts
    if not report.ok:
        return BuildResult(
            job, report, None, len(parts.stiffeners), len(parts.brackets), None, time.perf_counter() - started
        )
    doc, bom, plan = rendered.doc, rendered.bom, rendered.plan

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = job.project.drawing_no
    files = [
        _write_atomic(out_dir / f"{stem}.dxf", doc.saveas),
        _write_atomic(
            out_dir / f"{stem}-bom.csv", lambda p: p.write_text(bom_csv(bom), encoding="utf-8", newline="")
        ),
    ]
    if preview:
        files.append(
            _write_atomic(
                out_dir / f"{stem}.png",
                lambda p: render_png(doc, p, standard.sheet.width, standard.sheet.height),
            )
        )

    result = BuildResult(
        job,
        report,
        plan.scale,
        len(parts.stiffeners),
        len(parts.brackets),
        bom.total_weight_kg,
        time.perf_counter() - started,
        tuple(files),
    )
    summary = format_summary(result)
    report_path = _write_atomic(
        out_dir / f"{stem}-report.txt", lambda p: p.write_text(summary + "\n", encoding="utf-8")
    )
    return replace(result, files=result.files + (report_path,))


def _write_atomic(path: Path, write: Callable[[Path], object]) -> Path:
    """Write to a temporary sibling, then move it into place, so no half-written file is left."""
    tmp = path.with_name(f"{path.stem}.tmp{path.suffix}")
    try:
        write(tmp)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def format_summary(result: BuildResult) -> str:
    project = result.job.project
    report = result.report
    lines = [
        f"shipdraw: {project.drawing_no} {project.title}",
        f"Result: {'OK' if result.ok else 'FAILED'} "
        f"({len(report.errors)} error(s), {len(report.warnings)} warning(s))",
    ]
    if result.ok:
        lines += [
            f"Scale: 1:{result.scale}",
            f"Stiffeners: {result.stiffener_count}   Brackets: {result.bracket_count}",
            f"Total weight: {result.total_weight_kg:.1f} kg",
        ]
    lines.append(f"Time: {result.seconds:.2f} s")
    for heading, items in (("Errors", report.errors), ("Warnings", report.warnings)):
        if items:
            lines.append(f"{heading}:")
            lines += [f"  - {item}" for item in items]
    if result.files:
        lines.append("Files:")
        lines += [f"  {path}" for path in result.files]
    return "\n".join(lines)
```

- [ ] **Step 4: Run the new tests and the whole suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: 114 passed (the 109 existing plus 5 new)

- [ ] **Step 5: Commit**

```bash
git add src/shipdraw/pipeline.py src/shipdraw/render/preview.py src/shipdraw/render/files.py tests/test_render_files.py
git commit -m "feat: render drawings in memory as SVG, DXF bytes and PNG bytes" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Form ↔ job mapping

**Files:**
- Create: `src/shipdraw/web/__init__.py`, `src/shipdraw/web/form.py`
- Test: `tests/test_web_form.py`

**Interfaces:**
- Produces:
  - `DEFAULT_VALUES: dict`
  - the field-name tuples `TEXT_FIELDS`, `NUMBER_FIELDS`, `WHOLE_NUMBER_FIELDS` and `FLAG_FIELDS`
  - `FormError(field_errors: dict[str, str])`, where the key `""` marks an error that belongs to no single field
  - `form_to_job(values: dict) -> Job`
  - `outline_half(width, height, corner_cut) -> list[list[float]]`
  - `field_for(location: str) -> str | None`
  - `split_message(message: str) -> tuple[str | None, str]`

- [ ] **Step 1: Write the failing tests**

`tests/test_web_form.py`:

```python
import pytest

from shipdraw.web.form import DEFAULT_VALUES, FormError, form_to_job, outline_half, split_message


def with_changes(**changes):
    return {**DEFAULT_VALUES, **changes}


def field_errors(values):
    with pytest.raises(FormError) as info:
        form_to_job(values)
    return info.value.field_errors


def test_defaults_reproduce_the_example_job(example_job):
    job = form_to_job(DEFAULT_VALUES)
    assert job.bulkhead == example_job.bulkhead
    assert job.frames == example_job.frames
    assert job.project.model_dump(exclude={"date"}) == example_job.project.model_dump(exclude={"date"})


def test_square_corners_when_corner_cut_is_zero():
    assert outline_half(9000, 3500, 0) == [[0, 0], [4500, 0], [4500, 3500], [0, 3500]]
    assert outline_half(9000, 3500, 900) == [[0, 0], [3600, 0], [4500, 900], [4500, 3500], [0, 3500]]


def test_numbers_typed_as_text_are_accepted():
    job = form_to_job(with_changes(width="9,000", bar_spacing=" 600 ", at_frame="25"))
    assert job.bulkhead.stiffeners.spacing == 600
    assert job.bulkhead.outline_half[1] == (3600, 0)


@pytest.mark.parametrize(
    "field, value, message",
    [
        ("width", "abc", "Enter a number"),
        ("height", "", "Required"),
        ("at_frame", "25.5", "Enter a whole number"),
        ("width", "-100", "Must be more than 0"),
        ("corner_cut", "-5", "Can't be negative"),
        ("corner_cut", "5000", "smaller than half the width"),
        ("project_name", "  ", "Required"),
    ],
)
def test_field_errors(field, value, message):
    errors = field_errors(with_changes(**{field: value}))
    assert message in errors[field]


def test_engine_validation_is_mapped_back_to_fields():
    errors = field_errors(with_changes(bar_spacing="-600", drawing_no="SY/101", frame_last="10", profile="IPE 200"))
    assert set(errors) == {"bar_spacing", "drawing_no", "frame_last", "profile"}
    assert errors["bar_spacing"] == "Must be greater than 0"
    assert "letters" in errors["drawing_no"]
    assert errors["frame_last"] == "Last must be greater than first"
    assert errors["profile"].startswith("Profile 'IPE 200' must look like")


def test_split_message():
    assert split_message("bulkhead.at_frame: FR35 is outside the frame range FR20-FR30") == (
        "at_frame",
        "FR35 is outside the frame range FR20-FR30",
    )
    assert split_message("bulkhead.brackets: bottom bracket of the stiffener at y=3900: too short") == (
        "bracket_size",
        "Bottom bracket of the stiffener at y=3900: too short",
    )
    assert split_message("bulkhead.stiffeners.spacing: 800 mm is above")[0] == "bar_spacing"
    assert split_message("sheet: the drawing does not fit")[0] == "width"
    assert split_message("something odd happened") == (None, "Something odd happened")
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `.venv/Scripts/python -m pytest tests/test_web_form.py -q`
Expected: collection ERROR `No module named 'shipdraw.web'`

- [ ] **Step 3: Implement**

`src/shipdraw/web/__init__.py`:

```python
"""The drawing page: a local web server around the engine."""
```

`src/shipdraw/web/form.py`:

```python
"""The drawing page's plain form fields ↔ the engine's Job."""
from __future__ import annotations

import math

from pydantic import ValidationError

from ..job import Job

DEFAULT_VALUES: dict[str, object] = {
    "project_name": "OSV 60m",
    "drawing_no": "SY-101",
    "title": "TRANSVERSE BULKHEAD AT FR25",
    "drawn_by": "AH",
    "revision": "A",
    "frame_first": 20,
    "frame_last": 30,
    "frame_spacing": 600,
    "at_frame": 25,
    "width": 9000,
    "height": 3500,
    "corner_cut": 900,
    "plate_thickness": 8,
    "plate_grade": "AH36",
    "profile": "HP 160x8",
    "bar_spacing": 600,
    "first_at": 300,
    "brackets_top": True,
    "brackets_bottom": True,
    "bracket_size": 250,
    "bracket_thickness": 8,
}

TEXT_FIELDS = ("project_name", "drawing_no", "title", "drawn_by", "revision", "plate_grade", "profile")
NUMBER_FIELDS = (
    "frame_first",
    "frame_last",
    "frame_spacing",
    "at_frame",
    "width",
    "height",
    "corner_cut",
    "plate_thickness",
    "bar_spacing",
    "first_at",
    "bracket_size",
    "bracket_thickness",
)
WHOLE_NUMBER_FIELDS = ("frame_first", "frame_last", "at_frame")
FLAG_FIELDS = ("brackets_top", "brackets_bottom")

# Engine locations (job paths and rule-check prefixes) → form field. The longest matching prefix wins.
_FIELD_FOR_LOCATION = {
    "project.name": "project_name",
    "project.drawing_no": "drawing_no",
    "project.title": "title",
    "project.drawn_by": "drawn_by",
    "project.revision": "revision",
    "frames": "frame_last",
    "frames.first": "frame_first",
    "frames.last": "frame_last",
    "frames.spacing": "frame_spacing",
    "bulkhead.at_frame": "at_frame",
    "bulkhead.outline_half": "width",
    "bulkhead.plate.thickness": "plate_thickness",
    "bulkhead.plate.grade": "plate_grade",
    "bulkhead.stiffeners": "first_at",
    "bulkhead.stiffeners.profile": "profile",
    "bulkhead.stiffeners.spacing": "bar_spacing",
    "bulkhead.stiffeners.first_at": "first_at",
    "bulkhead.brackets": "bracket_size",
    "bulkhead.brackets.size": "bracket_size",
    "bulkhead.brackets.thickness": "bracket_thickness",
    "sheet": "width",
}


class FormError(ValueError):
    """Some boxes on the form are wrong. field_errors maps a field name ("" for none) to a message."""

    def __init__(self, field_errors: dict[str, str]):
        super().__init__("; ".join(f"{name or 'form'}: {text}" for name, text in field_errors.items()))
        self.field_errors = field_errors


def field_for(location: str) -> str | None:
    parts = location.split(".")
    while parts:
        field = _FIELD_FOR_LOCATION.get(".".join(parts))
        if field:
            return field
        parts.pop()
    return None


def _sentence(text: str) -> str:
    return text[:1].upper() + text[1:]


def split_message(message: str) -> tuple[str | None, str]:
    """'bulkhead.at_frame: FR35 is outside …' → ('at_frame', 'FR35 is outside …')."""
    location, separator, text = message.partition(": ")
    if separator and location and " " not in location:
        return field_for(location), _sentence(text)
    return None, _sentence(message)


def outline_half(width: float, height: float, corner_cut: float) -> list[list[float]]:
    """Starboard half outline: a box, with a 45° cut at the bottom corner when corner_cut > 0."""
    half = width / 2
    if corner_cut == 0:
        return [[0, 0], [half, 0], [half, height], [0, height]]
    return [[0, 0], [half - corner_cut, 0], [half, corner_cut], [half, height], [0, height]]


def _read_number(raw: object, whole: bool) -> tuple[float | None, str | None]:
    if isinstance(raw, bool):
        return None, "Enter a number"
    if isinstance(raw, (int, float)):
        number = float(raw)
    else:
        text = str("" if raw is None else raw).strip().replace(",", "")
        if not text:
            return None, "Required"
        try:
            number = float(text)
        except ValueError:
            return None, "Enter a number"
    if not math.isfinite(number):
        return None, "Enter a number"
    if whole and not number.is_integer():
        return None, "Enter a whole number"
    return number, None


def _friendly(message: str) -> str:
    message = message.removeprefix("Value error, ")
    if "should match pattern" in message:
        return "Use only letters, numbers, - _ and ."
    if message.startswith("Input should be "):
        message = "Must be " + message.removeprefix("Input should be ")
    return _sentence(message)


def form_to_job(values: dict) -> Job:
    errors: dict[str, str] = {}
    numbers: dict[str, float] = {}
    for name in NUMBER_FIELDS:
        number, problem = _read_number(values.get(name), name in WHOLE_NUMBER_FIELDS)
        if problem:
            errors[name] = problem
        else:
            numbers[name] = number
    texts = {name: str(values.get(name) or "").strip() for name in TEXT_FIELDS}
    errors.update({name: "Required" for name, text in texts.items() if not text})
    flags = {name: bool(values.get(name)) for name in FLAG_FIELDS}

    for name in ("width", "height"):
        if name in numbers and numbers[name] <= 0:
            errors[name] = "Must be more than 0"
    if numbers.get("corner_cut", 0) < 0:
        errors["corner_cut"] = "Can't be negative"
    if not errors:
        width, height, cut = numbers["width"], numbers["height"], numbers["corner_cut"]
        if cut >= width / 2 or cut >= height:
            errors["corner_cut"] = "Must be smaller than half the width and smaller than the height"
    if errors:
        raise FormError(errors)

    data = {
        "project": {
            "name": texts["project_name"],
            "drawing_no": texts["drawing_no"],
            "title": texts["title"],
            "drawn_by": texts["drawn_by"],
            "revision": texts["revision"],
        },
        "frames": {
            "first": int(numbers["frame_first"]),
            "last": int(numbers["frame_last"]),
            "spacing": numbers["frame_spacing"],
        },
        "bulkhead": {
            "at_frame": int(numbers["at_frame"]),
            "outline_half": outline_half(numbers["width"], numbers["height"], numbers["corner_cut"]),
            "plate": {"thickness": numbers["plate_thickness"], "grade": texts["plate_grade"]},
            "stiffeners": {
                "profile": texts["profile"],
                "spacing": numbers["bar_spacing"],
                "first_at": numbers["first_at"],
            },
            "brackets": {
                "top": flags["brackets_top"],
                "bottom": flags["brackets_bottom"],
                "size": numbers["bracket_size"],
                "thickness": numbers["bracket_thickness"],
            },
        },
    }
    try:
        return Job.model_validate(data)
    except ValidationError as exc:
        field_errors: dict[str, str] = {}
        for err in exc.errors():
            location = ".".join(str(part) for part in err["loc"])
            field_errors.setdefault(field_for(location) or "", _friendly(err["msg"]))
        raise FormError(field_errors) from exc
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/Scripts/python -m pytest tests/test_web_form.py -q`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add src/shipdraw/web/__init__.py src/shipdraw/web/form.py tests/test_web_form.py
git commit -m "feat: plain-language form fields mapped to engine jobs" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Drawing service (defaults, preview, export)

**Files:**
- Modify: `src/shipdraw/profiles.py` (add `hp_names`)
- Create: `src/shipdraw/web/api.py`
- Test: `tests/test_web_api.py`, and append to `tests/test_profiles.py`

**Interfaces:**
- Produces:
  - `ProfileLibrary.hp_names() -> list[str]` (sorted by size)
  - `DrawingService(standard, profiles)`, with `.defaults()`, `.preview(values)` and `.export(values, kind) -> Export`
  - `Export(filename, content_type, data)`
  - `ExportRefused`
  - `EXPORT_KINDS = ("dxf", "png", "csv", "zip")`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_profiles.py`:

```python
def test_hp_names_are_sorted_by_size(shipped_profiles):
    assert shipped_profiles.hp_names() == ["HP 120x7", "HP 140x7", "HP 160x8", "HP 180x9", "HP 200x10"]
```

`tests/test_web_api.py`:

```python
import io
import zipfile

import ezdxf
import pytest

from shipdraw.web.api import DrawingService, ExportRefused
from shipdraw.web.form import DEFAULT_VALUES


@pytest.fixture
def service(standard, shipped_profiles):
    return DrawingService(standard, shipped_profiles)


def test_defaults_include_values_and_profiles(service):
    data = service.defaults()
    assert data["values"] == DEFAULT_VALUES
    assert data["profiles"][:5] == ["HP 120x7", "HP 140x7", "HP 160x8", "HP 180x9", "HP 200x10"]
    assert "FB 100x10" in data["profiles"]


def test_preview_of_the_example(service):
    result = service.preview(DEFAULT_VALUES)
    assert result["status"] == "warning"  # placeholder HP weight
    assert result["svg"].startswith("<svg")
    assert result["summary"] == {
        "drawing_no": "SY-101",
        "scale": 20,
        "stiffeners": 14,
        "brackets": 28,
        "total_weight_kg": 2581.3,
    }
    assert [row["qty"] for row in result["bom"]] == [1, 12, 2, 28]
    assert result["warnings"][0]["field"] == "profile"
    assert result["errors"] == [] and result["field_errors"] == {}


def test_preview_with_a_rule_error(service):
    result = service.preview({**DEFAULT_VALUES, "at_frame": "35"})
    assert result["status"] == "error" and result["svg"] is None and result["summary"] is None
    assert result["errors"] == [{"field": "at_frame", "text": "FR35 is outside the frame range FR20-FR30"}]


def test_preview_with_invalid_input(service):
    result = service.preview({**DEFAULT_VALUES, "width": "abc"})
    assert result["status"] == "invalid" and result["svg"] is None
    assert result["field_errors"] == {"width": "Enter a number"}


def test_export_dxf_opens_cleanly(service):
    export = service.export(DEFAULT_VALUES, "dxf")
    assert export.filename == "SY-101.dxf"
    doc = ezdxf.read(io.StringIO(export.data.decode("utf-8")))
    assert not doc.audit().has_errors
    assert len(doc.modelspace().query("DIMENSION")) == 27


def test_export_png_csv_and_zip(service):
    assert service.export(DEFAULT_VALUES, "png").data[:8] == b"\x89PNG\r\n\x1a\n"
    csv = service.export(DEFAULT_VALUES, "csv")
    assert csv.filename == "SY-101-bom.csv"
    assert csv.data.decode("utf-8").startswith("ITEM,DESCRIPTION")
    bundle = service.export(DEFAULT_VALUES, "zip")
    assert bundle.filename == "SY-101.zip"
    names = sorted(zipfile.ZipFile(io.BytesIO(bundle.data)).namelist())
    assert names == ["SY-101-bom.csv", "SY-101.dxf", "SY-101.png"]


@pytest.mark.parametrize(
    "changes, kind",
    [({"at_frame": "35"}, "dxf"), ({"width": "abc"}, "dxf"), ({}, "exe")],
)
def test_export_refused(service, changes, kind):
    with pytest.raises(ExportRefused):
        service.export({**DEFAULT_VALUES, **changes}, kind)
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `.venv/Scripts/python -m pytest tests/test_web_api.py tests/test_profiles.py -q`
Expected: collection ERROR `No module named 'shipdraw.web.api'`. The profiles test fails with `AttributeError: 'ProfileLibrary' object has no attribute 'hp_names'`.

- [ ] **Step 3: Implement**

In `src/shipdraw/profiles.py`, add this method to `ProfileLibrary`, after `load`:

```python
    def hp_names(self) -> list[str]:
        return sorted(self._hp, key=lambda name: parse_profile(name).dims)
```

`src/shipdraw/web/api.py`:

```python
"""What the drawing page asks for: defaults, previews and exports. No HTTP here."""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass

from ..bom import bom_csv
from ..pipeline import Rendered, render_drawing
from ..profiles import ProfileLibrary
from ..render.files import dxf_bytes, png_bytes
from ..render.preview import render_svg
from ..standard import Standard
from .form import DEFAULT_VALUES, FormError, form_to_job, split_message

EXPORT_KINDS = ("dxf", "png", "csv", "zip")
COMMON_PROFILES = ("FB 80x8", "FB 100x10", "FB 120x10", "L 75x50x6", "L 100x75x8", "L 150x90x10")


@dataclass(frozen=True)
class Export:
    filename: str
    content_type: str
    data: bytes


class ExportRefused(ValueError):
    """The drawing can't be exported as it stands. The message is user-facing."""


def _issue(message: str) -> dict:
    field, text = split_message(message)
    return {"field": field, "text": text}


class DrawingService:
    def __init__(self, standard: Standard, profiles: ProfileLibrary):
        self.standard = standard
        self.profiles = profiles

    def defaults(self) -> dict:
        return {"values": dict(DEFAULT_VALUES), "profiles": [*self.profiles.hp_names(), *COMMON_PROFILES]}

    def preview(self, values: dict) -> dict:
        result = {
            "status": "invalid",
            "field_errors": {},
            "errors": [],
            "warnings": [],
            "summary": None,
            "bom": None,
            "svg": None,
        }
        try:
            job = form_to_job(values)
        except FormError as exc:
            result["field_errors"] = exc.field_errors
            return result
        rendered = render_drawing(job, self.standard, self.profiles)
        result["errors"] = [_issue(message) for message in rendered.report.errors]
        result["warnings"] = [_issue(message) for message in rendered.report.warnings]
        if not rendered.report.ok:
            result["status"] = "error"
            return result
        sheet = self.standard.sheet
        result.update(
            status="warning" if result["warnings"] else "ok",
            summary={
                "drawing_no": job.project.drawing_no,
                "scale": rendered.plan.scale,
                "stiffeners": len(rendered.parts.stiffeners),
                "brackets": len(rendered.parts.brackets),
                "total_weight_kg": round(rendered.bom.total_weight_kg, 1),
            },
            bom=[
                {
                    "item": row.item,
                    "description": row.description,
                    "qty": row.qty,
                    "length_mm": row.length_mm,
                    "weight_kg": round(row.weight_kg, 1),
                }
                for row in rendered.bom.rows
            ],
            svg=render_svg(rendered.doc, sheet.width, sheet.height),
        )
        return result

    def export(self, values: dict, kind: str) -> Export:
        if kind not in EXPORT_KINDS:
            raise ExportRefused(f"unknown export type {kind!r}")
        try:
            job = form_to_job(values)
        except FormError as exc:
            raise ExportRefused("fix the highlighted boxes first") from exc
        rendered = render_drawing(job, self.standard, self.profiles)
        if not rendered.report.ok:
            raise ExportRefused("fix the problems listed under the preview first")
        stem = job.project.drawing_no
        files = self._files(rendered, stem, ("dxf", "png", "csv") if kind == "zip" else (kind,))
        if kind != "zip":
            return files[0]
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
            for item in files:
                bundle.writestr(item.filename, item.data)
        return Export(f"{stem}.zip", "application/zip", buffer.getvalue())

    def _files(self, rendered: Rendered, stem: str, kinds: tuple[str, ...]) -> list[Export]:
        sheet = self.standard.sheet
        makers = {
            "dxf": lambda: Export(f"{stem}.dxf", "application/dxf", dxf_bytes(rendered.doc)),
            "png": lambda: Export(f"{stem}.png", "image/png", png_bytes(rendered.doc, sheet.width, sheet.height)),
            "csv": lambda: Export(f"{stem}-bom.csv", "text/csv; charset=utf-8", bom_csv(rendered.bom).encode("utf-8")),
        }
        return [makers[kind]() for kind in kinds]
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/Scripts/python -m pytest tests/test_web_api.py tests/test_profiles.py -q`
Expected: all passed (9 in `test_web_api.py`, 18 in `test_profiles.py`)

- [ ] **Step 5: Commit**

```bash
git add src/shipdraw/profiles.py src/shipdraw/web/api.py tests/test_web_api.py tests/test_profiles.py
git commit -m "feat: drawing service for page previews and exports" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Local HTTP server

**Files:**
- Create: `src/shipdraw/web/server.py`, `src/shipdraw/web/static/index.html` (a placeholder for now; Task 6 replaces it), `src/shipdraw/web/static/app.js` and `src/shipdraw/web/static/app.css` (empty for now)
- Test: `tests/test_web_server.py`

**Interfaces:**
- Produces:
  - `create_server(service, host="127.0.0.1", port=8765) -> ThreadingHTTPServer` (falls back to a free port when the requested one is busy)
  - `serve(service, port=8765, open_browser=True)`
  - `STATIC_DIR`

- [ ] **Step 1: Write the failing tests**

`tests/test_web_server.py`:

```python
import http.client
import json
import socket
import threading

import pytest

from shipdraw.web.api import DrawingService
from shipdraw.web.form import DEFAULT_VALUES
from shipdraw.web.server import create_server


@pytest.fixture
def server(standard, shipped_profiles):
    srv = create_server(DrawingService(standard, shipped_profiles), port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield srv
    srv.shutdown()
    srv.server_close()


def call(server, method, path, body=None, raw=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=60)
    payload = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    conn.request(method, path, body=payload, headers={"Content-Type": "application/json", **(headers or {})})
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return response, data


def test_listens_on_this_computer_only(server):
    assert server.server_address[0] == "127.0.0.1"


def test_page_and_assets(server):
    response, data = call(server, "GET", "/")
    assert response.status == 200 and response.getheader("Content-Type").startswith("text/html")
    assert b"<title>" in data
    assert call(server, "GET", "/static/app.js")[0].getheader("Content-Type").startswith("text/javascript")
    assert call(server, "GET", "/static/app.css")[0].status == 200


@pytest.mark.parametrize("path", ["/static/../pyproject.toml", "/static/%2e%2e/pyproject.toml", "/static/nope.js", "/nope"])
def test_nothing_outside_the_static_folder(server, path):
    assert call(server, "GET", path)[0].status == 404


def test_defaults_and_preview(server):
    response, data = call(server, "GET", "/api/defaults")
    assert response.status == 200 and json.loads(data)["values"]["drawing_no"] == "SY-101"
    response, data = call(server, "POST", "/api/preview", body=DEFAULT_VALUES)
    result = json.loads(data)
    assert response.status == 200 and result["status"] == "warning" and result["svg"].startswith("<svg")


def test_export_is_a_download(server):
    response, data = call(server, "POST", "/api/export/dxf", body=DEFAULT_VALUES)
    assert response.status == 200
    assert response.getheader("Content-Disposition") == 'attachment; filename="SY-101.dxf"'
    assert b"SECTION" in data[:40]


def test_refused_export_is_422(server):
    response, data = call(server, "POST", "/api/export/dxf", body={**DEFAULT_VALUES, "at_frame": "35"})
    assert response.status == 422 and "fix the problems" in json.loads(data)["error"]


@pytest.mark.parametrize("raw", [b"[1, 2]", b"not json", b"\xff\xfe"])
def test_body_must_be_a_json_object(server, raw):
    assert call(server, "POST", "/api/preview", raw=raw)[0].status == 400


def test_oversized_body_is_413(server):
    conn = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=30)
    conn.putrequest("POST", "/api/preview")
    conn.putheader("Content-Length", "10000000")
    conn.endheaders()
    assert conn.getresponse().status == 413
    conn.close()


def test_foreign_host_is_403(server):
    assert call(server, "GET", "/api/defaults", headers={"Host": "evil.example"})[0].status == 403


def test_busy_port_falls_back_to_a_free_one(standard, shipped_profiles):
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    blocker.listen()
    busy = blocker.getsockname()[1]
    try:
        srv = create_server(DrawingService(standard, shipped_profiles), port=busy)
        try:
            assert srv.server_address[1] != busy
        finally:
            srv.server_close()
    finally:
        blocker.close()
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `.venv/Scripts/python -m pytest tests/test_web_server.py -q`
Expected: collection ERROR `No module named 'shipdraw.web.server'`

- [ ] **Step 3: Implement**

`src/shipdraw/web/server.py`:

```python
"""Local web server for the drawing page. It listens on this computer only (127.0.0.1)."""
from __future__ import annotations

import json
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .api import DrawingService, ExportRefused

STATIC_DIR = Path(__file__).resolve().parent / "static"
MAX_BODY_BYTES = 100_000
_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


class _Server(ThreadingHTTPServer):
    allow_reuse_address = False  # on Windows, address reuse would let two servers share one port
    daemon_threads = True


def make_handler(service: DrawingService) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "shipdraw"

        def log_message(self, format, *args):  # keep the console window quiet
            pass

        def do_GET(self):
            if not self._host_allowed():
                return self._json(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
            path = self.path.split("?", 1)[0]
            if path == "/":
                return self._static("index.html")
            if path.startswith("/static/"):
                return self._static(path[len("/static/"):])
            if path == "/api/defaults":
                return self._json(HTTPStatus.OK, service.defaults())
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self):
            if not self._host_allowed():
                return self._json(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
            path = self.path.split("?", 1)[0]
            values = self._read_json()
            if values is None:
                return
            if path == "/api/preview":
                return self._json(HTTPStatus.OK, service.preview(values))
            if path.startswith("/api/export/"):
                try:
                    export = service.export(values, path[len("/api/export/"):])
                except ExportRefused as exc:
                    return self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(exc)})
                return self._send(
                    HTTPStatus.OK,
                    export.content_type,
                    export.data,
                    {"Content-Disposition": f'attachment; filename="{export.filename}"'},
                )
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def _host_allowed(self) -> bool:
            port = self.server.server_address[1]
            return self.headers.get("Host", "") in {f"127.0.0.1:{port}", f"localhost:{port}"}

        def _read_json(self) -> dict | None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = -1
            if length < 0 or length > MAX_BODY_BYTES:
                self.close_connection = True
                self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "request too large"})
                return None
            try:
                data = json.loads(self.rfile.read(length) or b"null")
            except (UnicodeDecodeError, json.JSONDecodeError):
                data = None
            if not isinstance(data, dict):
                self._json(HTTPStatus.BAD_REQUEST, {"error": "expected a JSON object"})
                return None
            return data

        def _static(self, name: str) -> None:
            target = (STATIC_DIR / name).resolve()
            if target.parent != STATIC_DIR or target.suffix not in _CONTENT_TYPES or not target.is_file():
                return self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            self._send(HTTPStatus.OK, _CONTENT_TYPES[target.suffix], target.read_bytes(), {"Cache-Control": "no-cache"})

        def _json(self, status: HTTPStatus, payload: dict) -> None:
            self._send(status, "application/json; charset=utf-8", json.dumps(payload).encode("utf-8"))

        def _send(self, status: HTTPStatus, content_type: str, body: bytes, headers: dict | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

    return Handler


def create_server(service: DrawingService, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    handler = make_handler(service)
    try:
        return _Server((host, port), handler)
    except OSError:  # port busy: let the operating system pick a free one
        return _Server((host, 0), handler)


def serve(service: DrawingService, port: int = 8765, open_browser: bool = True) -> None:
    server = create_server(service, port=port)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Bulkhead drawing tool is running at {url}")
    print("Keep this window open while you use the page. Close it (or press Ctrl+C) to stop.")
    if open_browser:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
```

Create placeholder static files so that the routes have something to serve. Task 6 replaces them.

```bash
mkdir -p src/shipdraw/web/static
printf '<!doctype html><title>Bulkhead Drawing Tool</title>\n' > src/shipdraw/web/static/index.html
: > src/shipdraw/web/static/app.js
: > src/shipdraw/web/static/app.css
```

The static files must be shipped with the package. With setuptools, package data needs to be declared, so add this to `pyproject.toml`:

```toml
[tool.setuptools.package-data]
"shipdraw.web" = ["static/*"]
```

The install is editable, so this only matters for future non-editable installs.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/Scripts/python -m pytest tests/test_web_server.py -q`
Expected: 15 passed

- [ ] **Step 5: Commit**

```bash
git add src/shipdraw/web/server.py src/shipdraw/web/static pyproject.toml tests/test_web_server.py
git commit -m "feat: local web server for the drawing page" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: `shipdraw serve` and the double-click start file

**Files:**
- Modify (full rewrite): `src/shipdraw/cli.py`
- Create: `Start drawing tool.bat`
- Modify: `README.md` (insert a section)
- Test: append to `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_cli.py`:

```python
def test_serve_starts_the_page_server(monkeypatch):
    calls = {}

    def fake_serve(service, port, open_browser):
        calls.update(service=service, port=port, open_browser=open_browser)

    monkeypatch.setattr("shipdraw.cli.serve", fake_serve)
    assert main(["serve", "--port", "9000", "--no-browser"]) == 0
    assert calls["port"] == 9000 and calls["open_browser"] is False
    assert calls["service"].defaults()["values"]["drawing_no"] == "SY-101"
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `.venv/Scripts/python -m pytest tests/test_cli.py -q`
Expected: FAIL. Either `AttributeError: <module 'shipdraw.cli'> has no attribute 'serve'`, or argparse rejects `serve` and exits with code 2.

- [ ] **Step 3: Implement**

`src/shipdraw/cli.py`:

```python
"""Command line: `shipdraw build <job.yaml>` and `shipdraw serve`."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import CONFIG_DIR, ConfigError
from .job import load_job
from .pipeline import build, format_summary
from .profiles import ProfileLibrary
from .standard import load_standard
from .web.api import DrawingService
from .web.server import serve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="shipdraw", description="Generate ship structural drawings (DXF) from job files.")
    commands = parser.add_subparsers(dest="command", required=True)
    build_cmd = commands.add_parser("build", help="build one drawing from a job file")
    build_cmd.add_argument("job", type=Path, help="job file (YAML)")
    build_cmd.add_argument("-o", "--out", type=Path, default=Path("out"), help="output folder (default: out)")
    build_cmd.add_argument("--no-preview", action="store_true", help="skip the PNG preview")
    serve_cmd = commands.add_parser("serve", help="open the drawing page in your browser")
    serve_cmd.add_argument("--port", type=int, default=8765, help="port to use (a free one is picked if it is busy)")
    serve_cmd.add_argument("--no-browser", action="store_true", help="don't open the browser")
    for command in (build_cmd, serve_cmd):
        command.add_argument("--config", type=Path, default=CONFIG_DIR, help="folder with standard.yaml and profiles.yaml")
    args = parser.parse_args(argv)

    try:
        standard = load_standard(args.config / "standard.yaml")
        profiles = ProfileLibrary.load(args.config / "profiles.yaml")
        if args.command == "serve":
            serve(DrawingService(standard, profiles), port=args.port, open_browser=not args.no_browser)
            return 0
        job = load_job(args.job)
        result = build(job, standard, profiles, args.out, preview=not args.no_preview)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(format_summary(result))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
```

`Start drawing tool.bat`:

```bat
@echo off
cd /d "%~dp0"
title Bulkhead drawing tool
if not exist ".venv\Scripts\shipdraw.exe" (
  echo The drawing tool is not installed yet. See README.md, section "Setup".
  pause
  exit /b 1
)
".venv\Scripts\shipdraw.exe" serve
pause
```

In `README.md`, insert the following section immediately before `## Company standard`:

```markdown
## The drawing page (no commands needed)

Double-click **`Start drawing tool.bat`**. A black window opens; keep it open, and your browser shows the page.

1. Type the measurements on the left. The drawing on the right updates by itself.
2. Red boxes need fixing. Yellow notes are just for your attention.
3. Use the buttons at the top to download the AutoCAD file, the picture, the Excel list, or everything as a .zip.

Close the black window to stop the tool.
```

- [ ] **Step 4: Run the full suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add src/shipdraw/cli.py "Start drawing tool.bat" README.md tests/test_cli.py
git commit -m "feat: shipdraw serve and double-click start file" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: The page (functional)

**Files:**
- Replace: `src/shipdraw/web/static/index.html`, `src/shipdraw/web/static/app.js`, `src/shipdraw/web/static/app.css`
- Create: `.claude/launch.json` (for browser verification)

- [ ] **Step 1: Write the page**

`src/shipdraw/web/static/index.html`:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Bulkhead Drawing Tool</title>
  <link rel="stylesheet" href="/static/app.css">
  <script src="/static/app.js" defer></script>
</head>
<body>
  <header class="topbar">
    <div class="brand">
      <span class="brand-name">shipdraw</span>
      <span class="brand-sub">Bulkhead drawing tool</span>
    </div>
    <nav class="exports" aria-label="Export">
      <button type="button" class="btn" data-export="dxf" disabled>AutoCAD file <small>.dxf</small></button>
      <button type="button" class="btn" data-export="png" disabled>Picture <small>.png</small></button>
      <button type="button" class="btn" data-export="csv" disabled>Excel list <small>.csv</small></button>
      <button type="button" class="btn btn-primary" data-export="zip" disabled>Everything <small>.zip</small></button>
    </nav>
  </header>

  <main class="workspace">
    <aside class="panel inputs" aria-label="Measurements">
      <div class="panel-head">
        <h2>Measurements</h2>
        <button type="button" class="link" id="reset">Reset to example</button>
      </div>
      <form id="form" novalidate autocomplete="off"></form>
      <datalist id="profiles"></datalist>
    </aside>

    <section class="panel preview" aria-label="Drawing preview">
      <div class="panel-head">
        <h2>Live preview</h2>
        <span class="busy" id="busy" hidden>Updating…</span>
        <div class="zoom">
          <button type="button" class="icon" id="zoom-out" aria-label="Zoom out">−</button>
          <button type="button" class="icon" id="zoom-fit">Fit</button>
          <button type="button" class="icon" id="zoom-in" aria-label="Zoom in">+</button>
        </div>
      </div>
      <div class="stage" id="stage">
        <div class="sheet" id="sheet"></div>
        <p class="placeholder" id="placeholder">Preparing the drawing…</p>
      </div>
    </section>

    <section class="panel results" aria-label="Checks and material list">
      <div class="status" id="status" data-state="idle" aria-live="polite">
        <strong id="status-title">Starting…</strong>
        <span id="status-detail"></span>
      </div>
      <ul class="issues" id="issues"></ul>
      <dl class="summary" id="summary"></dl>
      <table class="bom" id="bom" hidden>
        <thead>
          <tr><th>#</th><th>Item</th><th class="num">Qty</th><th class="num">Length (mm)</th><th class="num">Weight (kg)</th></tr>
        </thead>
        <tbody></tbody>
        <tfoot>
          <tr><td></td><td>Total</td><td></td><td></td><td class="num" id="bom-total"></td></tr>
        </tfoot>
      </table>
    </section>
  </main>

  <div class="toast" id="toast" role="status" hidden></div>
</body>
</html>
```

`src/shipdraw/web/static/app.js`:

```js
"use strict";

// Plain-language form. Field names must match shipdraw/web/form.py.
const SECTIONS = [
  { title: "Wall shape", fields: [
    { name: "width", label: "Width", unit: "mm", hint: "Full width of the wall, side to side." },
    { name: "height", label: "Height", unit: "mm", hint: "From the bottom of the ship to the top of the wall." },
    { name: "corner_cut", label: "Corner cut", unit: "mm", hint: "The two bottom corners are cut off at 45°. Use 0 for square corners." },
  ] },
  { title: "Steel bars", subtitle: "stiffeners", fields: [
    { name: "profile", label: "Bar type", type: "text", list: "profiles", hint: "HP = bulb flat, FB = flat bar, L = angle. For example HP 160x8." },
    { name: "bar_spacing", label: "Every", unit: "mm", hint: "Distance between two bars." },
    { name: "first_at", label: "First bar at", unit: "mm", hint: "Distance from the middle line to the first bar. 0 puts a bar on the middle line." },
  ] },
  { title: "Corner triangles", subtitle: "brackets", fields: [
    { name: "brackets_bottom", label: "At the bottom", type: "checkbox" },
    { name: "brackets_top", label: "At the top", type: "checkbox" },
    { name: "bracket_size", label: "Size", unit: "mm", hint: "Length of each short side of the triangle." },
    { name: "bracket_thickness", label: "Thickness", unit: "mm" },
  ] },
  { title: "Wall plate", fields: [
    { name: "plate_thickness", label: "Thickness", unit: "mm" },
    { name: "plate_grade", label: "Steel grade", type: "text", hint: "For example AH36." },
  ] },
  { title: "Position in the ship", fields: [
    { name: "at_frame", label: "At frame", unit: "no.", hint: "Frames are the ship's ribs, numbered from the back. The wall sits on this one." },
    { name: "frame_first", label: "Show frames from", unit: "no." },
    { name: "frame_last", label: "Show frames to", unit: "no." },
    { name: "frame_spacing", label: "Frame spacing", unit: "mm", hint: "Distance between two frames." },
  ] },
  { title: "Title block", fields: [
    { name: "project_name", label: "Project", type: "text" },
    { name: "drawing_no", label: "Drawing no.", type: "text", hint: "Also used as the file name." },
    { name: "title", label: "Title", type: "text" },
    { name: "drawn_by", label: "Drawn by", type: "text" },
    { name: "revision", label: "Revision", type: "text" },
  ] },
];

const LABELS = Object.fromEntries(SECTIONS.flatMap((section) => section.fields.map((f) => [f.name, f.label])));
const PREVIEW_DELAY_MS = 350;
const MAX_ZOOM = 8;
const $ = (selector) => document.querySelector(selector);
const plural = (count, word, suffix = "s") => `${count} ${word}${count === 1 ? "" : suffix}`;
const capitalize = (text) => text.charAt(0).toUpperCase() + text.slice(1);
const formatNumber = (value, digits = 0) =>
  Number(value).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });

const state = { defaults: null, request: null, timer: null, hasDrawing: false, canExport: false, view: { scale: 1, x: 0, y: 0 } };

// ---------- form ----------

function buildForm() {
  const form = $("#form");
  for (const section of SECTIONS) {
    const fieldset = document.createElement("fieldset");
    const legend = document.createElement("legend");
    legend.textContent = section.title;
    if (section.subtitle) {
      const small = document.createElement("small");
      small.textContent = section.subtitle;
      legend.append(" ", small);
    }
    fieldset.append(legend, ...section.fields.map(buildField));
    form.append(fieldset);
  }
  form.addEventListener("input", () => schedulePreview());
  form.addEventListener("change", () => schedulePreview());
  form.addEventListener("submit", (event) => event.preventDefault());
}

function buildField(field) {
  const wrapper = document.createElement("div");
  wrapper.className = field.type === "checkbox" ? "field field-check" : "field";
  wrapper.dataset.field = field.name;
  const id = `f-${field.name}`;
  const input = document.createElement("input");
  input.id = id;
  input.name = field.name;
  const label = document.createElement("label");
  label.htmlFor = id;
  label.textContent = field.label;

  if (field.type === "checkbox") {
    input.type = "checkbox";
    wrapper.append(input, label);
    return wrapper;
  }

  input.type = "text";
  input.inputMode = field.type === "text" ? "text" : "decimal";
  input.spellcheck = false;
  if (field.list) input.setAttribute("list", field.list);
  const box = document.createElement("div");
  box.className = "input";
  box.append(input);
  if (field.unit) {
    const unit = document.createElement("span");
    unit.className = "unit";
    unit.textContent = field.unit;
    box.append(unit);
  }
  const message = document.createElement("p");
  message.className = "message";
  message.id = `${id}-msg`;
  input.setAttribute("aria-describedby", message.id);
  wrapper.append(label, box);
  if (field.hint) {
    const hint = document.createElement("p");
    hint.className = "hint";
    hint.textContent = field.hint;
    wrapper.append(hint);
  }
  wrapper.append(message);
  return wrapper;
}

function readValues() {
  const values = {};
  for (const input of $("#form").querySelectorAll("input")) {
    values[input.name] = input.type === "checkbox" ? input.checked : input.value;
  }
  return values;
}

function setValues(values) {
  const form = $("#form");
  for (const [name, value] of Object.entries(values)) {
    const input = form.elements.namedItem(name);
    if (!input) continue;
    if (input.type === "checkbox") input.checked = Boolean(value);
    else input.value = String(value);
  }
}

function focusField(name) {
  const input = $("#form").elements.namedItem(name);
  if (!input) return;
  input.scrollIntoView({ block: "center", behavior: "smooth" });
  input.focus({ preventScroll: true });
}

// ---------- preview requests ----------

function schedulePreview(delay = PREVIEW_DELAY_MS) {
  clearTimeout(state.timer);
  state.timer = setTimeout(runPreview, delay);
}

async function runPreview() {
  state.request?.abort();
  const request = new AbortController();
  state.request = request;
  setBusy(true);
  try {
    const response = await fetch("/api/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(readValues()),
      signal: request.signal,
    });
    if (!response.ok) throw new Error(`server answered ${response.status}`);
    showResult(await response.json());
  } catch (error) {
    if (error.name !== "AbortError") showOffline();
  } finally {
    if (state.request === request) {
      state.request = null;
      setBusy(false);
    }
  }
}

// ---------- results ----------

function showResult(result) {
  clearFieldMarks();
  for (const [name, text] of Object.entries(result.field_errors)) markField(name, "error", text);
  for (const issue of result.errors) if (issue.field) markField(issue.field, "error", issue.text);
  for (const issue of result.warnings) if (issue.field) markField(issue.field, "warning", issue.text);

  const details = {
    ok: ["Drawing ready", "Everything checks out."],
    warning: ["Drawing ready", `${plural(result.warnings.length, "note")} below.`],
    error: ["Can't draw this yet", `${plural(result.errors.length, "problem")} to fix below.`],
    invalid: ["Check the highlighted boxes", `${plural(Object.keys(result.field_errors).length, "box", "es")} need attention.`],
  };
  setStatus(result.status, ...details[result.status]);
  showIssues(result);
  showDrawing(result.svg);
  showSummary(result.summary);
  showBom(result.bom, result.summary);
  setExportsEnabled(result.status === "ok" || result.status === "warning");
}

function setStatus(kind, title, detail) {
  $("#status").dataset.state = kind;
  $("#status-title").textContent = title;
  $("#status-detail").textContent = detail;
}

function showOffline() {
  setStatus("offline", "Can't reach the drawing engine", "Is its black window still open? If you closed it, start the tool again.");
  setExportsEnabled(false);
}

function setBusy(busy) {
  $("#busy").hidden = !busy;
  $(".preview").classList.toggle("is-busy", busy);
}

function markField(name, kind, text) {
  const field = document.querySelector(`.field[data-field="${name}"]`);
  if (!field || field.dataset.state === "error" || (field.dataset.state === "warning" && kind === "warning")) return;
  field.dataset.state = kind;
  const message = field.querySelector(".message");
  if (message) message.textContent = text;
  field.querySelector("input")?.setAttribute("aria-invalid", String(kind === "error"));
}

function clearFieldMarks() {
  for (const field of document.querySelectorAll(".field[data-state]")) {
    delete field.dataset.state;
    const message = field.querySelector(".message");
    if (message) message.textContent = "";
    field.querySelector("input")?.removeAttribute("aria-invalid");
  }
}

function showIssues(result) {
  const list = $("#issues");
  list.replaceChildren();
  const items = [
    ...Object.entries(result.field_errors).filter(([name]) => !LABELS[name]).map(([, text]) => ({ kind: "error", text })),
    ...result.errors.map((issue) => ({ kind: "error", ...issue })),
    ...result.warnings.map((issue) => ({ kind: "warning", ...issue })),
  ];
  for (const item of items) {
    const li = document.createElement("li");
    li.className = `issue issue-${item.kind}`;
    if (item.field && LABELS[item.field]) {
      const where = document.createElement("button");
      where.type = "button";
      where.className = "issue-field";
      where.textContent = LABELS[item.field];
      where.addEventListener("click", () => focusField(item.field));
      li.append(where, " ");
    }
    li.append(item.text);
    list.append(li);
  }
}

function showDrawing(svg) {
  const sheet = $("#sheet");
  const placeholder = $("#placeholder");
  if (svg) {
    sheet.innerHTML = svg;
    sheet.classList.remove("stale");
    placeholder.hidden = true;
    if (!state.hasDrawing) {
      state.hasDrawing = true;
      fitView();
    }
    return;
  }
  sheet.classList.add("stale");
  if (!state.hasDrawing) {
    placeholder.hidden = false;
    placeholder.textContent = "The drawing appears here once the measurements are valid.";
  }
}

function showSummary(summary) {
  const box = $("#summary");
  box.replaceChildren();
  if (!summary) return;
  const items = [
    ["Scale", `1:${summary.scale}`],
    ["Steel bars", summary.stiffeners],
    ["Corner triangles", summary.brackets],
    ["Total weight", `${formatNumber(summary.total_weight_kg, 1)} kg`],
  ];
  for (const [term, value] of items) {
    const item = document.createElement("div");
    const dt = document.createElement("dt");
    dt.textContent = term;
    const dd = document.createElement("dd");
    dd.textContent = value;
    item.append(dt, dd);
    box.append(item);
  }
}

function showBom(rows, summary) {
  const table = $("#bom");
  if (!rows) {
    table.hidden = true;
    return;
  }
  const body = table.tBodies[0];
  body.replaceChildren();
  for (const row of rows) {
    const tr = document.createElement("tr");
    const cells = [
      [row.item, false],
      [row.description, false],
      [row.qty, true],
      [row.length_mm == null ? "–" : formatNumber(row.length_mm), true],
      [formatNumber(row.weight_kg, 1), true],
    ];
    for (const [value, numeric] of cells) {
      const td = document.createElement("td");
      td.textContent = value;
      if (numeric) td.className = "num";
      tr.append(td);
    }
    body.append(tr);
  }
  $("#bom-total").textContent = formatNumber(summary.total_weight_kg, 1);
  table.hidden = false;
}

// ---------- exports ----------

function setExportsEnabled(enabled) {
  state.canExport = enabled;
  for (const button of document.querySelectorAll("[data-export]")) {
    if (!button.classList.contains("working")) button.disabled = !enabled;
  }
}

async function exportFile(kind, button) {
  button.disabled = true;
  button.classList.add("working");
  try {
    const response = await fetch(`/api/export/${kind}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(readValues()),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      toast(data.error ? `${capitalize(data.error)}.` : "Export failed.", "error");
      return;
    }
    const blob = await response.blob();
    const name = /filename="([^"]+)"/.exec(response.headers.get("Content-Disposition") || "")?.[1] || `drawing.${kind}`;
    const url = URL.createObjectURL(blob);
    const link = Object.assign(document.createElement("a"), { href: url, download: name });
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10_000);
    toast(`Saved ${name} to your Downloads folder.`, "ok");
  } catch {
    toast("Can't reach the drawing engine. Is its black window still open?", "error");
  } finally {
    button.classList.remove("working");
    button.disabled = !state.canExport;
  }
}

function toast(text, kind) {
  const element = $("#toast");
  element.textContent = text;
  element.dataset.kind = kind;
  element.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { element.hidden = true; }, 4000);
}

// ---------- zoom and pan ----------

function applyView() {
  const stage = $("#stage").getBoundingClientRect();
  const view = state.view;
  view.x = Math.min(0, Math.max(stage.width - stage.width * view.scale, view.x));
  view.y = Math.min(0, Math.max(stage.height - stage.height * view.scale, view.y));
  $("#sheet").style.transform = `translate(${view.x}px, ${view.y}px) scale(${view.scale})`;
  $("#stage").classList.toggle("zoomed", view.scale > 1);
}

function fitView() {
  state.view = { scale: 1, x: 0, y: 0 };
  applyView();
}

function zoomAt(factor, cx, cy) {
  const view = state.view;
  const scale = Math.min(MAX_ZOOM, Math.max(1, view.scale * factor));
  const k = scale / view.scale;
  view.x = cx - (cx - view.x) * k;
  view.y = cy - (cy - view.y) * k;
  view.scale = scale;
  applyView();
}

function zoomAtCentre(factor) {
  const stage = $("#stage").getBoundingClientRect();
  zoomAt(factor, stage.width / 2, stage.height / 2);
}

function setupViewer() {
  const stage = $("#stage");
  stage.addEventListener("wheel", (event) => {
    event.preventDefault();
    const box = stage.getBoundingClientRect();
    zoomAt(event.deltaY < 0 ? 1.15 : 1 / 1.15, event.clientX - box.left, event.clientY - box.top);
  }, { passive: false });

  let drag = null;
  stage.addEventListener("pointerdown", (event) => {
    if (state.view.scale === 1) return;
    drag = { x: event.clientX - state.view.x, y: event.clientY - state.view.y };
    stage.setPointerCapture(event.pointerId);
    stage.classList.add("dragging");
  });
  stage.addEventListener("pointermove", (event) => {
    if (!drag) return;
    state.view.x = event.clientX - drag.x;
    state.view.y = event.clientY - drag.y;
    applyView();
  });
  const endDrag = () => {
    drag = null;
    stage.classList.remove("dragging");
  };
  stage.addEventListener("pointerup", endDrag);
  stage.addEventListener("pointercancel", endDrag);
  stage.addEventListener("dblclick", fitView);
  $("#zoom-in").addEventListener("click", () => zoomAtCentre(1.25));
  $("#zoom-out").addEventListener("click", () => zoomAtCentre(0.8));
  $("#zoom-fit").addEventListener("click", fitView);
  window.addEventListener("resize", applyView);
}

// ---------- start ----------

async function init() {
  buildForm();
  setupViewer();
  for (const button of document.querySelectorAll("[data-export]")) {
    button.addEventListener("click", () => exportFile(button.dataset.export, button));
  }
  $("#reset").addEventListener("click", () => {
    if (!state.defaults) return;
    setValues(state.defaults);
    schedulePreview(0);
  });
  try {
    const response = await fetch("/api/defaults");
    const data = await response.json();
    state.defaults = data.values;
    $("#profiles").replaceChildren(...data.profiles.map((name) => Object.assign(document.createElement("option"), { value: name })));
    setValues(data.values);
    schedulePreview(0);
  } catch {
    showOffline();
  }
}

document.addEventListener("DOMContentLoaded", init);
```

`src/shipdraw/web/static/app.css`. This is functional styling only; Task 7 replaces it.

```css
:root {
  --bg: #eef1f5; --panel: #ffffff; --text: #18202b; --muted: #5b6676; --line: #d6dce5;
  --accent: #0b6bcb; --ok: #1a7f37; --warn: #9a6700; --err: #c62828; --sheet: #0d1117;
  font-family: "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif;
  color: var(--text); background: var(--bg);
}
* { box-sizing: border-box; }
body { margin: 0; min-height: 100vh; display: flex; flex-direction: column; }
.topbar { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 12px 20px; background: var(--panel); border-bottom: 1px solid var(--line); }
.brand-name { font-weight: 600; font-size: 18px; }
.brand-sub { color: var(--muted); margin-left: 8px; }
.exports { display: flex; gap: 8px; flex-wrap: wrap; }
.btn { font: inherit; padding: 8px 12px; border-radius: 6px; border: 1px solid var(--line); background: var(--panel); color: var(--text); cursor: pointer; }
.btn small { color: var(--muted); }
.btn-primary { background: var(--accent); color: #fff; border-color: var(--accent); }
.btn-primary small { color: #dce9f8; }
.btn:disabled { opacity: .45; cursor: not-allowed; }
.btn.working { cursor: progress; opacity: .7; }
.workspace { flex: 1; display: grid; grid-template-columns: 340px minmax(0, 1fr); grid-template-rows: auto 1fr; grid-template-areas: "inputs preview" "inputs results"; gap: 16px; padding: 16px 20px; }
.panel { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 16px; min-width: 0; }
.inputs { grid-area: inputs; overflow: auto; max-height: calc(100vh - 100px); }
.preview { grid-area: preview; }
.results { grid-area: results; }
.panel-head { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.panel-head h2 { font-size: 15px; margin: 0; flex: 1; }
fieldset { border: 0; padding: 0; margin: 0 0 18px; }
legend { font-weight: 600; margin-bottom: 8px; }
legend small { font-weight: 400; color: var(--muted); }
.field { margin-bottom: 10px; }
.field label { display: block; font-size: 13px; margin-bottom: 4px; }
.input { display: flex; align-items: center; border: 1px solid var(--line); border-radius: 6px; background: #fff; }
.input input { flex: 1; min-width: 0; border: 0; padding: 7px 9px; font: inherit; background: transparent; color: inherit; font-variant-numeric: tabular-nums; }
.input input:focus { outline: none; }
.input:focus-within { outline: 2px solid var(--accent); outline-offset: 1px; }
.unit { padding: 0 9px; color: var(--muted); font-size: 12px; }
.hint { margin: 4px 0 0; font-size: 12px; color: var(--muted); }
.message { margin: 4px 0 0; font-size: 12px; }
.message:empty { display: none; }
.field[data-state="error"] .input { border-color: var(--err); }
.field[data-state="error"] .message { color: var(--err); }
.field[data-state="warning"] .input { border-color: var(--warn); }
.field[data-state="warning"] .message { color: var(--warn); }
.field-check { display: flex; align-items: center; gap: 8px; }
.field-check label { margin: 0; font-size: 14px; }
.link { font: inherit; font-size: 13px; border: 0; background: none; color: var(--accent); cursor: pointer; padding: 0; }
.zoom { display: flex; gap: 4px; }
.icon { font: inherit; min-width: 32px; padding: 4px 8px; border: 1px solid var(--line); background: var(--panel); color: var(--text); border-radius: 6px; cursor: pointer; }
.busy { font-size: 12px; color: var(--muted); }
.stage { position: relative; overflow: hidden; aspect-ratio: 841 / 594; background: var(--sheet); border-radius: 6px; touch-action: none; }
.stage.zoomed { cursor: grab; }
.stage.dragging { cursor: grabbing; }
.sheet { position: absolute; inset: 0; transform-origin: 0 0; transition: opacity .2s; }
.sheet svg { display: block; width: 100%; height: 100%; }
.sheet.stale { opacity: .35; filter: grayscale(1); }
.placeholder { position: absolute; inset: 0; display: grid; place-items: center; margin: 0; color: #8b96a8; }
.status { padding: 10px 12px; border-radius: 6px; border: 1px solid var(--line); display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
.status[data-state="ok"] { border-color: var(--ok); color: var(--ok); }
.status[data-state="warning"] { border-color: var(--warn); color: var(--warn); }
.status[data-state="error"], .status[data-state="invalid"], .status[data-state="offline"] { border-color: var(--err); color: var(--err); }
.issues { list-style: none; padding: 0; margin: 10px 0; }
.issue { padding: 6px 0; font-size: 14px; border-bottom: 1px solid var(--line); }
.issue-error { color: var(--err); }
.issue-warning { color: var(--warn); }
.issue-field { font: inherit; font-weight: 600; border: 0; background: none; color: inherit; text-decoration: underline; cursor: pointer; padding: 0; }
.summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin: 12px 0; }
.summary div { border: 1px solid var(--line); border-radius: 6px; padding: 8px 10px; }
.summary dt { font-size: 12px; color: var(--muted); }
.summary dd { margin: 2px 0 0; font-size: 18px; font-weight: 600; font-variant-numeric: tabular-nums; }
.bom { width: 100%; border-collapse: collapse; font-size: 14px; }
.bom th, .bom td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--line); }
.bom .num { text-align: right; font-variant-numeric: tabular-nums; }
.bom tfoot td { font-weight: 600; }
.toast { position: fixed; right: 20px; bottom: 20px; padding: 10px 14px; border-radius: 6px; background: #18202b; color: #fff; }
.toast[data-kind="error"] { background: var(--err); }
@media (max-width: 900px) {
  .workspace { grid-template-columns: 1fr; grid-template-areas: "preview" "results" "inputs"; }
  .inputs { max-height: none; }
}
```

`.claude/launch.json`:

```json
{
  "version": "0.0.1",
  "configurations": [
    {
      "name": "drawing-tool",
      "runtimeExecutable": ".venv/Scripts/shipdraw.exe",
      "runtimeArgs": ["serve", "--no-browser", "--port", "8765"],
      "port": 8765
    }
  ]
}
```

- [ ] **Step 2: Re-run the server tests**

Run: `.venv/Scripts/python -m pytest tests/test_web_server.py -q`
Expected: all passed (the real page has a `<title>`)

- [ ] **Step 3: Verify in the built-in browser**

Start the page with `preview_start` (name `drawing-tool`) and check each of these. Record what you observe:

1. The page loads, the status reads "Drawing ready" with 1 note, and the example sheet is visible in CAD colours.
2. Set **Every** to `500`. Within about a second the drawing updates, with more bars and a changed BOM.
3. Set **Width** to `abc`. The Width box turns red with "Enter a number", and the exports are disabled.
4. Set **At frame** to `35`. The status reads "Can't draw this yet", the field shows the FR35 message, and the old drawing is dimmed.
5. Click **Reset to example**. Everything returns to the defaults.
6. Each export button triggers a download, with no error toast. Check this by watching `/api/export/*` return 200 in the network requests.
7. The mouse wheel zooms, drag pans, and **Fit** and double-click reset the view.
8. The console shows no errors.

- [ ] **Step 4: Commit**

```bash
git add src/shipdraw/web/static .claude/launch.json
git commit -m "feat: drawing page with live preview, checks, BOM and exports" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7 (Phase 2): Visual design pass

**Files:** `src/shipdraw/web/static/*`, plus a favicon and a logo as inline SVG.

**Direction (from the spec):**

- **Theme:** a "drafting room" theme. The background is deep ink-navy with a faint blueprint grid, and the drawing is the hero.
- **Accents:** cyan for primary actions and focus, amber for warnings, and a restrained red for errors.
- **Typography:** Segoe UI Variable Display for headings, Text for body, and tabular figures with Cascadia Mono / Consolas for numbers.
- **Restraint:** no gradient soup, no emoji icons, no generic card spam, and no purple-to-pink AI defaults. Every element earns its place.

**Animations** (all of them disabled under `prefers-reduced-motion`):

- a plotter-style draw-on of the sheet on the first load (stroke-dashoffset over the SVG paths, with `pathLength="1"` set in JS);
- a soft cross-fade on updates;
- a thin scanning line over the preview while it computes;
- status-pill colour transitions and count-up on the summary numbers;
- press and hover micro-interactions on the buttons;
- the toast slides in.

**Acceptance:**

- [ ] Everything in Task 6, Step 3 still passes after the redesign (re-run it).
- [ ] Screenshots at 1440×900 and 1280×800 look polished, with no overlaps, clipped text or orphan scrollbars, and a clear hierarchy. Tablet width (768) stays usable.
- [ ] Contrast is AA for text, and focus rings are visible on every control.
- [ ] Reduced motion turns the animations off; check this with the emulated media.
- [ ] The full pytest suite passes.
- [ ] Commit: `feat: drafting-room visual design with plotter animation`.
