import pytest
from ezdxf import bbox

from shipdraw.render.frame_view import draw_frame_strip
from shipdraw.render.sheet import new_document


@pytest.fixture
def strip(standard, example_job, example_parts, example_plan):
    msp = new_document(standard, example_plan.scale).modelspace()
    draw_frame_strip(msp, example_job, example_parts, standard, example_plan)
    return msp


def on(msp, kind, layer):
    return list(msp.query(f'{kind}[layer=="{layer}"]'))


def test_frame_ticks_and_baseline(strip, standard, example_plan):
    lines = on(strip, "LINE", standard.layers.frame.name)
    assert len(lines) == 12  # 11 ticks + baseline
    dx = example_plan.frames_offset[0]
    ticks = sorted(round(line.dxf.start.x - dx) for line in lines if line.dxf.start.x == line.dxf.end.x)
    assert ticks == [n * 600 for n in range(20, 31)]


def test_bulkhead_frame_is_marked(strip, standard, example_plan):
    (mark,) = on(strip, "LINE", standard.layers.plate.name)
    assert mark.dxf.start.x == pytest.approx(25 * 600 + example_plan.frames_offset[0])


def test_frame_labels(strip, standard):
    texts = {t.dxf.text for t in on(strip, "TEXT", standard.layers.text.name)}
    assert {f"FR{n}" for n in range(20, 31)} <= texts
    assert {"BHD", "FRAME LAYOUT FR20-FR30"} <= texts


def test_frame_spacing_dimensions(strip, standard):
    dims = on(strip, "DIMENSION", standard.layers.dim.name)
    assert [round(d.get_measurement()) for d in dims] == [600] * 10


def test_frame_strip_stays_inside_its_zone(strip, standard, example_plan):
    box = bbox.extents(strip)
    zone, s = standard.sheet.zones.frames, example_plan.scale
    assert box.extmin.x >= zone.x * s and box.extmin.y >= zone.y * s
    assert box.extmax.x <= (zone.x + zone.width) * s and box.extmax.y <= (zone.y + zone.height) * s
