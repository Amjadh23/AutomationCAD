import pytest

from shipdraw.geometry import bounding_box
from shipdraw.job import Job
from shipdraw.layout import ELEVATION_PAD, FRAMES_PAD, NoScaleFitsError, plan_sheet
from shipdraw.structure import build_parts


def parts_with_half_breadth(job_dict, half_breadth):
    job_dict["bulkhead"]["outline_half"] = [[0, 0], [half_breadth, 0], [half_breadth, 3500], [0, 3500]]
    return build_parts(Job.model_validate(job_dict))


def test_example_fits_at_1_to_20(example_plan):
    assert example_plan.scale == 20


def test_wider_bulkhead_drops_to_a_smaller_scale(job_dict, standard):
    assert plan_sheet(parts_with_half_breadth(job_dict, 12000), standard).scale == 50


def test_too_large_for_any_scale(job_dict, standard):
    with pytest.raises(NoScaleFitsError, match="does not fit the A1 sheet at any allowed scale"):
        plan_sheet(parts_with_half_breadth(job_dict, 40000), standard)


def test_elevation_is_centred_in_its_zone(example_plan, example_parts, standard):
    s, zone = example_plan.scale, standard.sheet.zones.elevation
    min_y, min_z, max_y, max_z = bounding_box(example_parts.outline)
    dx, dy = example_plan.elevation_offset
    left, right = min_y + dx - ELEVATION_PAD.left * s, max_y + dx + ELEVATION_PAD.right * s
    bottom, top = min_z + dy - ELEVATION_PAD.bottom * s, max_z + dy + ELEVATION_PAD.top * s
    assert (left + right) / 2 == pytest.approx((zone.x + zone.width / 2) * s)
    assert (bottom + top) / 2 == pytest.approx((zone.y + zone.height / 2) * s)


def test_frame_strip_is_centred_in_its_zone(example_plan, example_parts, standard):
    s, zone = example_plan.scale, standard.sheet.zones.frames
    dx, dy = example_plan.frames_offset
    left = example_parts.frames[0].x + dx - FRAMES_PAD.left * s
    right = example_parts.frames[-1].x + dx + FRAMES_PAD.right * s
    assert (left + right) / 2 == pytest.approx((zone.x + zone.width / 2) * s)
    assert (dy - FRAMES_PAD.bottom * s + dy + FRAMES_PAD.top * s) / 2 == pytest.approx((zone.y + zone.height / 2) * s)


def test_bom_and_title_block_positions(example_plan):
    assert example_plan.bom_top_left == (651 * 20, 584 * 20)
    assert example_plan.title_block_origin == ((841 - 10 - 180) * 20, 10 * 20)
