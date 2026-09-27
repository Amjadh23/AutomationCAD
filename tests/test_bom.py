import pytest

from shipdraw.bom import bom_csv, build_bom
from shipdraw.job import Job
from shipdraw.profiles import ProfileLibrary
from shipdraw.structure import build_parts

PLATE_KG = 30_690_000 * 8 * 7.85e-6  # outline area x thickness x density
BRACKET_KG = (26 * 31_250 + 2 * 31_250 * 2**-0.5) * 8 * 7.85e-6  # 26 right-angled + 2 on the chamfer


def test_example_bom(example_job, example_parts, verified_profiles):
    rows = build_bom(example_job, example_parts, verified_profiles).rows
    assert [r.item for r in rows] == [1, 2, 3, 4]
    assert (rows[0].description, rows[0].qty, rows[0].length_mm) == ("PL 8 AH36 (9000 x 3500)", 1, None)
    assert rows[0].weight_kg == pytest.approx(PLATE_KG)
    assert (rows[1].description, rows[1].qty, rows[1].length_mm) == ("HP 160x8", 12, 3500)
    assert rows[1].weight_kg == pytest.approx(12 * 3.5 * 12.4)
    assert (rows[2].description, rows[2].qty, rows[2].length_mm) == ("HP 160x8", 2, 3200)
    assert rows[2].weight_kg == pytest.approx(2 * 3.2 * 12.4)
    assert (rows[3].description, rows[3].qty, rows[3].length_mm) == ("BKT 250x250x8", 28, None)
    assert rows[3].weight_kg == pytest.approx(BRACKET_KG)


def test_total_weight(example_job, example_parts, verified_profiles):
    bom = build_bom(example_job, example_parts, verified_profiles)
    assert bom.total_weight_kg == pytest.approx(PLATE_KG + 12 * 3.5 * 12.4 + 2 * 3.2 * 12.4 + BRACKET_KG)


def bom_for(job_dict, profiles):
    job = Job.model_validate(job_dict)
    return build_bom(job, build_parts(job), profiles)


def test_flat_bar_stiffeners(job_dict):
    job_dict["bulkhead"]["stiffeners"]["profile"] = "FB 100x10"
    row = bom_for(job_dict, ProfileLibrary({})).rows[1]
    assert row.description == "FB 100x10"
    assert row.weight_kg == pytest.approx(12 * 3.5 * 7.85)


def test_angle_stiffeners_are_marked_approx(job_dict):
    job_dict["bulkhead"]["stiffeners"]["profile"] = "L 100x75x8"
    assert bom_for(job_dict, ProfileLibrary({})).rows[1].description == "L 100x75x8 (approx.)"


def test_no_bracket_row_without_brackets(job_dict, verified_profiles):
    job_dict["bulkhead"]["brackets"].update(top=False, bottom=False)
    assert [r.description for r in bom_for(job_dict, verified_profiles).rows][-1] == "HP 160x8"


def test_bom_csv(example_job, example_parts, verified_profiles):
    text = bom_csv(build_bom(example_job, example_parts, verified_profiles))
    lines = text.splitlines()
    assert lines[0] == "ITEM,DESCRIPTION,QTY,LENGTH_MM,WEIGHT_KG"
    assert lines[2] == "2,HP 160x8,12,3500,520.80"
    assert lines[-1].startswith(",TOTAL,,,")
    assert len(lines) == 6
