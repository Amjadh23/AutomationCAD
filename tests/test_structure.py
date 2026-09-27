import pytest

from shipdraw.job import Job
from shipdraw.structure import Frame, build_parts, stiffener_positions

EXAMPLE_YS = [-3900, -3300, -2700, -2100, -1500, -900, -300, 300, 900, 1500, 2100, 2700, 3300, 3900]


def test_stiffener_positions_mirror_about_centreline():
    assert stiffener_positions(300, 600, 4500) == EXAMPLE_YS
    assert stiffener_positions(0, 600, 1500) == [-1200, -600, 0, 600, 1200]


def test_example_stiffeners(example_parts):
    assert [s.y for s in example_parts.stiffeners] == EXAMPLE_YS
    by_y = {s.y: s for s in example_parts.stiffeners}
    assert (by_y[3900].z_bottom, by_y[3900].z_top) == pytest.approx((300, 3500))
    assert by_y[3900].length == pytest.approx(3200)
    assert (by_y[300].z_bottom, by_y[300].z_top) == pytest.approx((0, 3500))


def test_example_brackets(example_parts):
    assert len(example_parts.brackets) == 28
    assert example_parts.bracket_problems == ()
    assert sorted(round(b.area) for b in example_parts.brackets)[:2] == [22097, 22097]  # the two on the chamfer


def test_example_frames(example_parts):
    assert len(example_parts.frames) == 11
    assert example_parts.frames[0] == Frame(20, 12000)
    assert example_parts.frames[-1] == Frame(30, 18000)
    assert example_parts.bulkhead_x == 15000


def test_stiffener_on_centreline_appears_once(job_dict):
    job_dict["bulkhead"]["stiffeners"]["first_at"] = 0
    ys = [s.y for s in build_parts(Job.model_validate(job_dict)).stiffeners]
    assert len(ys) == 15 and ys.count(0) == 1


def test_bottom_brackets_only(job_dict):
    job_dict["bulkhead"]["brackets"]["top"] = False
    assert len(build_parts(Job.model_validate(job_dict)).brackets) == 14


def test_brackets_that_do_not_fit_are_reported_not_raised(job_dict):
    job_dict["bulkhead"]["brackets"]["size"] = 500
    parts = build_parts(Job.model_validate(job_dict))
    assert len(parts.brackets) == 26
    assert len(parts.bracket_problems) == 2
    assert "y=3900" in " ".join(parts.bracket_problems)
