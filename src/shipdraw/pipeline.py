"""The build pipeline: job → checks → drawing files.

Called by the CLI now and by the MCP server (build #2) later.
"""
from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from .bom import bom_csv, build_bom
from .checks import CheckReport, run_checks
from .job import Job
from .layout import plan_sheet
from .profiles import ProfileLibrary
from .render.bom_table import draw_bom_table
from .render.bulkhead_view import draw_elevation
from .render.frame_view import draw_frame_strip
from .render.preview import render_png
from .render.sheet import draw_border, draw_title_block, new_document
from .standard import Standard
from .structure import build_parts


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


def build(
    job: Job, standard: Standard, profiles: ProfileLibrary, out_dir: Path, *, preview: bool = True
) -> BuildResult:
    started = time.perf_counter()
    parts = build_parts(job)
    report = run_checks(job, parts, standard, profiles)
    if not report.ok:
        return BuildResult(
            job, report, None, len(parts.stiffeners), len(parts.brackets), None, time.perf_counter() - started
        )

    plan = plan_sheet(parts, standard)
    bom = build_bom(job, parts, profiles)
    doc = new_document(standard, plan.scale)
    msp = doc.modelspace()
    draw_border(msp, standard, plan.scale)
    draw_title_block(doc, job, standard, plan)
    draw_elevation(msp, job, parts, standard, plan)
    draw_frame_strip(msp, job, parts, standard, plan)
    draw_bom_table(msp, bom, standard, plan)

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
