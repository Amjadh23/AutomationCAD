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
