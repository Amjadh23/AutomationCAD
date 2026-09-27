import pytest

from shipdraw.geometry import (
    BracketFitError,
    bounding_box,
    bracket_triangle,
    clip_vertical,
    contains_point,
    is_simple,
    mirror_half_outline,
    outline_problems,
    polygon_area,
    remove_collinear,
)

HALF = [(0, 0), (3600, 0), (4500, 900), (4500, 3500), (0, 3500)]
FULL = [(3600, 0), (4500, 900), (4500, 3500), (-4500, 3500), (-4500, 900), (-3600, 0)]


def flat(points):
    return [c for p in points for c in p]


def test_mirror_builds_full_outline_without_centreline_vertices():
    assert mirror_half_outline(HALF) == FULL


def test_mirrored_outline_is_symmetric():
    full = mirror_half_outline(HALF)
    assert {(-x, y) for x, y in full} == set(full)


def test_remove_collinear_drops_duplicates_and_straight_runs():
    assert remove_collinear([(0, 0), (0, 0), (10, 0), (10, 10)]) == [(0, 0), (10, 0), (10, 10)]
    assert remove_collinear([(0, 0), (5, 0), (10, 0), (10, 10)]) == [(0, 0), (10, 0), (10, 10)]


def test_polygon_area_and_bounding_box():
    assert polygon_area(FULL) == pytest.approx(9000 * 3500 - 900 * 900)  # two 900x900/2 chamfers
    assert bounding_box(FULL) == (-4500, 0, 4500, 3500)


def test_clip_vertical_on_flat_bottom_and_chamfer():
    assert flat(clip_vertical(FULL, 300)) == pytest.approx([0, 3500])
    assert flat(clip_vertical(FULL, 3900)) == pytest.approx([300, 3500])
    assert flat(clip_vertical(FULL, 0)) == pytest.approx([0, 3500])


def test_clip_vertical_outside_or_on_side_is_empty():
    assert clip_vertical(FULL, 4500) == []
    assert clip_vertical(FULL, 5000) == []


def test_clip_vertical_returns_every_inside_span():
    c_shape = [(0, 0), (3000, 0), (3000, 1000), (1000, 1000), (1000, 2000), (3000, 2000), (3000, 3000), (0, 3000)]
    assert flat(clip_vertical(c_shape, 2000)) == pytest.approx([0, 1000, 2000, 3000])


def test_is_simple():
    assert is_simple(FULL)
    assert not is_simple([(0, 0), (10, 10), (10, 0), (0, 10)])  # bow tie
    assert not is_simple([(0, 0), (10, 0), (5, 0), (5, 5)])  # folds back on itself


def test_outline_problems():
    assert outline_problems(FULL) == []
    assert outline_problems([(0, 0), (1, 1)]) == ["outline needs at least 3 distinct corners, got 2"]
    assert outline_problems([(0, 0), (10, 0), (20, 0)]) == ["outline has zero area"]
    # asymmetric bow tie: a symmetric one has zero net area and would report that instead
    assert outline_problems([(0, 0), (10, 10), (10, 0), (0, 20)]) == ["outline crosses itself"]


def test_contains_point():
    assert contains_point(FULL, (0, 1000))
    assert contains_point(FULL, (4500, 2000))  # on the boundary
    assert not contains_point(FULL, (4400, 50))  # cut away by the chamfer
    assert not contains_point(FULL, (0, 4000))


def test_bottom_bracket_on_chamfer_runs_along_the_slope():
    tri = bracket_triangle(FULL, (3900, 300), (0, 1), 250)
    leg = 250 / 2**0.5
    assert flat(tri) == pytest.approx([3900, 300, 3900, 550, 3900 - leg, 300 - leg])


def test_top_bracket_points_towards_centreline():
    assert flat(bracket_triangle(FULL, (300, 3500), (0, -1), 250)) == pytest.approx([300, 3500, 300, 3250, 50, 3500])
    assert flat(bracket_triangle(FULL, (-300, 3500), (0, -1), 250)) == pytest.approx([-300, 3500, -300, 3250, -50, 3500])


def test_bracket_on_centreline_points_to_starboard():
    assert flat(bracket_triangle(FULL, (0, 0), (0, 1), 250)) == pytest.approx([0, 0, 0, 250, 250, 0])


def test_brackets_lie_inside_the_plate():
    for end, inward in [((3900, 300), (0, 1)), ((300, 3500), (0, -1)), ((-3300, 0), (0, 1))]:
        assert all(contains_point(FULL, p) for p in bracket_triangle(FULL, end, inward, 250))


def test_bracket_longer_than_the_edge_is_rejected():
    with pytest.raises(BracketFitError, match="only 424 mm"):
        bracket_triangle(FULL, (3900, 300), (0, 1), 500)
