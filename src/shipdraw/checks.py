"""Deterministic rule checks, the rule-based reviewer. Errors block the drawing; warnings do not."""
from __future__ import annotations

from dataclasses import dataclass

from .geometry import outline_problems
from .job import Job
from .layout import NoScaleFitsError, plan_sheet
from .profiles import ProfileLibrary, UnknownProfileError
from .standard import Standard
from .structure import BulkheadParts


@dataclass(frozen=True)
class CheckReport:
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors


def run_checks(job: Job, parts: BulkheadParts, standard: Standard, profiles: ProfileLibrary) -> CheckReport:
    bh = job.bulkhead
    errors: list[str] = []
    warnings: list[str] = []

    shape_problems = outline_problems(list(parts.outline))
    errors += [f"bulkhead.outline_half: {problem}" for problem in shape_problems]

    if not job.frames.first <= bh.at_frame <= job.frames.last:
        errors.append(
            f"bulkhead.at_frame: FR{bh.at_frame} is outside the frame range "
            f"FR{job.frames.first}-FR{job.frames.last}"
        )

    if not parts.stiffeners:
        errors.append(
            "bulkhead.stiffeners: no stiffener position falls inside the outline (check first_at and spacing)"
        )

    ends = int(bh.brackets.top) + int(bh.brackets.bottom)
    if ends:
        too_short = [st for st in parts.stiffeners if bh.brackets.size >= st.length / ends]
        if too_short:
            shortest = min(too_short, key=lambda st: st.length)
            errors.append(
                f"bulkhead.brackets.size: {bh.brackets.size:g} mm brackets at {ends} end(s) are too large "
                f"for {len(too_short)} stiffener(s); the shortest is {shortest.length:.0f} mm at y={shortest.y:g}"
            )
    errors += [f"bulkhead.brackets: {problem}" for problem in parts.bracket_problems]

    try:
        weight = profiles.weight(bh.stiffeners.profile)
    except UnknownProfileError as exc:
        errors.append(f"bulkhead.stiffeners.profile: {exc}")
    else:
        if weight.placeholder:
            warnings.append(
                f"bulkhead.stiffeners.profile: the weight of {bh.stiffeners.profile} ({weight.kg_per_m:g} kg/m) "
                "is a placeholder in the profile library; BOM weights are estimates"
            )

    if not shape_problems:
        try:
            plan_sheet(parts, standard)
        except NoScaleFitsError as exc:
            errors.append(f"sheet: {exc}")

    limit = standard.rules.max_stiffener_spacing
    if bh.stiffeners.spacing > limit:
        warnings.append(
            f"bulkhead.stiffeners.spacing: {bh.stiffeners.spacing:g} mm is above the standard's maximum of {limit:g} mm"
        )

    return CheckReport(tuple(errors), tuple(warnings))
