"""Bill of materials from the drawn parts."""
from __future__ import annotations

import csv
import io
from collections import Counter
from dataclasses import dataclass

from .geometry import bounding_box, polygon_area
from .job import Job
from .profiles import STEEL_DENSITY_KG_M3, ProfileLibrary
from .structure import BulkheadParts

_KG_PER_MM3 = STEEL_DENSITY_KG_M3 * 1e-9


@dataclass(frozen=True)
class BomRow:
    item: int
    description: str
    qty: int
    length_mm: float | None  # length of one piece; None where it does not apply
    weight_kg: float  # all pieces in the row


@dataclass(frozen=True)
class Bom:
    rows: tuple[BomRow, ...]

    @property
    def total_weight_kg(self) -> float:
        return sum(row.weight_kg for row in self.rows)


def build_bom(job: Job, parts: BulkheadParts, profiles: ProfileLibrary) -> Bom:
    bh = job.bulkhead
    rows: list[tuple[str, int, float | None, float]] = []

    min_y, min_z, max_y, max_z = bounding_box(parts.outline)
    plate_kg = abs(polygon_area(parts.outline)) * bh.plate.thickness * _KG_PER_MM3
    rows.append(
        (f"PL {bh.plate.thickness:g} {bh.plate.grade} ({max_y - min_y:g} x {max_z - min_z:g})", 1, None, plate_kg)
    )

    weight = profiles.weight(bh.stiffeners.profile)
    description = bh.stiffeners.profile + (" (approx.)" if weight.approx else "")
    lengths = Counter(round(st.length) for st in parts.stiffeners)
    for length in sorted(lengths, reverse=True):
        qty = lengths[length]
        rows.append((description, qty, float(length), qty * length / 1000 * weight.kg_per_m))

    if parts.brackets:
        size, t = bh.brackets.size, bh.brackets.thickness
        bracket_kg = sum(b.area for b in parts.brackets) * t * _KG_PER_MM3
        rows.append((f"BKT {size:g}x{size:g}x{t:g}", len(parts.brackets), None, bracket_kg))

    return Bom(tuple(BomRow(i, *row) for i, row in enumerate(rows, start=1)))


def bom_csv(bom: Bom) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["ITEM", "DESCRIPTION", "QTY", "LENGTH_MM", "WEIGHT_KG"])
    for row in bom.rows:
        length = "" if row.length_mm is None else f"{row.length_mm:.0f}"
        writer.writerow([row.item, row.description, row.qty, length, f"{row.weight_kg:.2f}"])
    writer.writerow(["", "TOTAL", "", "", f"{bom.total_weight_kg:.2f}"])
    return buffer.getvalue()
