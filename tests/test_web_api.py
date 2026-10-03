import io
import zipfile

import ezdxf
import pytest

from shipdraw.web.api import DrawingService, ExportRefused
from shipdraw.web.form import DEFAULT_VALUES


@pytest.fixture
def service(standard, shipped_profiles):
    return DrawingService(standard, shipped_profiles)


def test_defaults_include_values_and_profiles(service):
    data = service.defaults()
    assert data["values"] == DEFAULT_VALUES
    assert data["profiles"][:5] == ["HP 120x7", "HP 140x7", "HP 160x8", "HP 180x9", "HP 200x10"]
    assert "FB 100x10" in data["profiles"]


def test_preview_of_the_example(service):
    result = service.preview(DEFAULT_VALUES)
    assert result["status"] == "warning"  # placeholder HP weight
    assert result["svg"].startswith("<svg")
    assert result["summary"] == {
        "drawing_no": "SY-101",
        "scale": 20,
        "stiffeners": 14,
        "brackets": 28,
        "total_weight_kg": 2581.3,
    }
    assert [row["qty"] for row in result["bom"]] == [1, 12, 2, 28]
    assert result["warnings"][0]["field"] == "profile"
    assert result["errors"] == [] and result["field_errors"] == {}


def test_preview_with_a_rule_error(service):
    result = service.preview({**DEFAULT_VALUES, "at_frame": "35"})
    assert result["status"] == "error" and result["svg"] is None and result["summary"] is None
    assert result["errors"] == [{"field": "at_frame", "text": "FR35 is outside the frame range FR20-FR30"}]


def test_preview_with_invalid_input(service):
    result = service.preview({**DEFAULT_VALUES, "width": "abc"})
    assert result["status"] == "invalid" and result["svg"] is None
    assert result["field_errors"] == {"width": "Enter a number"}


def test_export_dxf_opens_cleanly(service):
    export = service.export(DEFAULT_VALUES, "dxf")
    assert export.filename == "SY-101.dxf"
    doc = ezdxf.read(io.StringIO(export.data.decode("utf-8")))
    assert not doc.audit().has_errors
    assert len(doc.modelspace().query("DIMENSION")) == 27


def test_export_png_csv_and_zip(service):
    assert service.export(DEFAULT_VALUES, "png").data[:8] == b"\x89PNG\r\n\x1a\n"
    csv = service.export(DEFAULT_VALUES, "csv")
    assert csv.filename == "SY-101-bom.csv"
    assert csv.data.decode("utf-8").startswith("ITEM,DESCRIPTION")
    bundle = service.export(DEFAULT_VALUES, "zip")
    assert bundle.filename == "SY-101.zip"
    names = sorted(zipfile.ZipFile(io.BytesIO(bundle.data)).namelist())
    assert names == ["SY-101-bom.csv", "SY-101.dxf", "SY-101.png"]


@pytest.mark.parametrize(
    "changes, kind",
    [({"at_frame": "35"}, "dxf"), ({"width": "abc"}, "dxf"), ({}, "exe")],
)
def test_export_refused(service, changes, kind):
    with pytest.raises(ExportRefused):
        service.export({**DEFAULT_VALUES, **changes}, kind)
