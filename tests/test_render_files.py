import io

import ezdxf
import pytest

from shipdraw.job import Job
from shipdraw.pipeline import render_drawing
from shipdraw.render.files import dxf_bytes, png_bytes
from shipdraw.render.preview import render_svg


@pytest.fixture
def example_doc(example_job, standard, shipped_profiles):
    return render_drawing(example_job, standard, shipped_profiles).doc


def test_render_drawing_returns_everything_when_checks_pass(example_job, standard, shipped_profiles):
    rendered = render_drawing(example_job, standard, shipped_profiles)
    assert rendered.report.ok and rendered.doc is not None
    assert rendered.plan.scale == 20 and len(rendered.bom.rows) == 4
    assert len(rendered.parts.stiffeners) == 14


def test_render_drawing_has_no_document_when_checks_fail(job_dict, standard, shipped_profiles):
    job_dict["bulkhead"]["at_frame"] = 35
    rendered = render_drawing(Job.model_validate(job_dict), standard, shipped_profiles)
    assert not rendered.report.ok
    assert rendered.doc is None and rendered.bom is None and rendered.plan is None


def test_dxf_bytes_round_trip(example_doc):
    reread = ezdxf.read(io.StringIO(dxf_bytes(example_doc).decode("utf-8")))
    assert not reread.audit().has_errors
    assert len(reread.modelspace().query("DIMENSION")) == 27


def test_png_bytes(example_doc):
    assert png_bytes(example_doc, 841, 594)[:8] == b"\x89PNG\r\n\x1a\n"


def test_svg_preview_uses_layer_colours(example_doc):
    svg = render_svg(example_doc, 841, 594)
    assert svg.startswith("<svg") and 'viewBox="0 0 1000000' in svg
    assert "#00ff00" in svg  # STIFFENER layer is ACI 3, green
