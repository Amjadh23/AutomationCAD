import pytest
from ezdxf import bbox

from shipdraw.render.bulkhead_view import draw_elevation
from shipdraw.render.sheet import new_document


@pytest.fixture
def elevation(standard, example_job, example_parts, example_plan):
    msp = new_document(standard, example_plan.scale).modelspace()
    draw_elevation(msp, example_job, example_parts, standard, example_plan)
    return msp


def on(msp, kind, layer):
    return list(msp.query(f'{kind}[layer=="{layer}"]'))


def test_plate_outline_is_the_offset_outline(elevation, standard, example_parts, example_plan):
    (plate,) = on(elevation, "LWPOLYLINE", standard.layers.plate.name)
    dx, dy = example_plan.elevation_offset
    assert plate.closed
    expected = [c for y, z in example_parts.outline for c in (y + dx, z + dy)]
    assert [c for p in plate.get_points("xy") for c in p] == pytest.approx(expected)


def test_stiffeners_and_brackets(elevation, standard, example_plan):
    dx, dy = example_plan.elevation_offset
    stiffeners = on(elevation, "LINE", standard.layers.stiffener.name)
    assert len(stiffeners) == 14
    (outer,) = [line for line in stiffeners if line.dxf.start.x == pytest.approx(3900 + dx)]
    assert (outer.dxf.start.y - dy, outer.dxf.end.y - dy) == pytest.approx((300, 3500))
    assert len(on(elevation, "LWPOLYLINE", standard.layers.bracket.name)) == 28


def test_centreline_and_baseline(elevation, standard):
    assert len(on(elevation, "LINE", standard.layers.centreline.name)) == 2


def test_labels_and_leaders(elevation, standard):
    texts = {t.dxf.text for t in on(elevation, "TEXT", standard.layers.text.name)}
    assert texts == {
        "CL",
        "BL",
        "PL 8 AH36",
        "HP 160x8 @ 600 TYP.",
        "BKT 250x250x8 TYP.",
        "BULKHEAD AT FR25 (LOOKING FWD)",
    }
    assert len(on(elevation, "LINE", standard.layers.text.name)) == 3


def test_dimensions(elevation, standard):
    dims = on(elevation, "DIMENSION", standard.layers.dim.name)
    # 15 spacing links (side, 14 stiffeners, side), overall breadth, overall height
    assert sorted(round(d.get_measurement()) for d in dims) == [600] * 15 + [3500, 9000]


def test_elevation_stays_inside_its_zone(elevation, standard, example_plan):
    box = bbox.extents(elevation)
    zone, s = standard.sheet.zones.elevation, example_plan.scale
    assert box.extmin.x >= zone.x * s and box.extmin.y >= zone.y * s
    assert box.extmax.x <= (zone.x + zone.width) * s and box.extmax.y <= (zone.y + zone.height) * s
