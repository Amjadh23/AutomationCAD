import ezdxf
import pytest

from shipdraw.config import ConfigError
from shipdraw.render.sheet import (
    DIMSTYLE,
    TITLE_BLOCK,
    draw_border,
    draw_title_block,
    new_document,
    title_values,
)
from shipdraw.standard import LayerStyle


def test_document_has_every_standard_layer(standard):
    doc = new_document(standard, 20)
    for style in standard.layers.all():
        layer = doc.layers.get(style.name)
        assert layer.color == style.color
        assert layer.dxf.linetype.upper() == style.linetype.upper()
        assert layer.dxf.lineweight == style.lineweight


def test_document_scales_dimensions_and_linetypes(standard):
    doc = new_document(standard, 20)
    assert doc.dimstyles.get(DIMSTYLE).dxf.dimscale == 20
    assert doc.header["$LTSCALE"] == 20
    assert doc.header["$INSUNITS"] == 4  # millimetres


def test_unknown_linetype_is_a_config_error(standard):
    layers = standard.layers.model_copy(update={"frame": LayerStyle(name="FRAME", color=8, linetype="NOPE")})
    with pytest.raises(ConfigError, match="NOPE"):
        new_document(standard.model_copy(update={"layers": layers}), 20)


def test_border_is_sheet_size_times_scale(standard):
    doc = new_document(standard, 20)
    msp = doc.modelspace()
    draw_border(msp, standard, 20)
    borders = list(msp.query(f'LWPOLYLINE[layer=="{standard.layers.border.name}"]'))
    assert len(borders) == 2
    corners = [p for e in borders for p in e.get_points("xy")]
    assert max(x for x, _ in corners) == pytest.approx(841 * 20)
    assert max(y for _, y in corners) == pytest.approx(594 * 20)
    assert min(x for x, _ in corners) == pytest.approx(0)


def test_title_values(example_job):
    assert title_values(example_job, 20) == {
        "PROJECT": "OSV 60m",
        "DWG_NO": "SY-101",
        "TITLE": "TRANSVERSE BULKHEAD AT FR25",
        "SCALE": "1:20",
        "DRAWN": "AH",
        "DATE": "2026-09-28",
        "REV": "A",
    }


def test_title_block_attributes_survive_a_round_trip(standard, example_job, example_plan, tmp_path):
    doc = new_document(standard, example_plan.scale)
    draw_title_block(doc, example_job, standard, example_plan)
    doc.saveas(tmp_path / "tb.dxf")

    reread = ezdxf.readfile(tmp_path / "tb.dxf")
    assert not reread.audit().has_errors
    (ref,) = reread.modelspace().query("INSERT")
    assert ref.dxf.name == TITLE_BLOCK
    assert (ref.dxf.insert.x, ref.dxf.insert.y) == pytest.approx(example_plan.title_block_origin)
    assert ref.dxf.xscale == example_plan.scale
    assert {a.dxf.tag: a.dxf.text for a in ref.attribs} == title_values(example_job, example_plan.scale)
    assert {a.dxf.layer for a in ref.attribs} == {standard.layers.title.name}
