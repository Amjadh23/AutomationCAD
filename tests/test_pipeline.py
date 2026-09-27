import ezdxf
import matplotlib.image as mpimg

from shipdraw.job import Job
from shipdraw.pipeline import build, format_summary
from shipdraw.render.sheet import title_values


def test_example_build_writes_all_outputs(example_job, standard, shipped_profiles, tmp_path):
    out = tmp_path / "out"
    result = build(example_job, standard, shipped_profiles, out)
    assert result.ok and result.scale == 20
    assert result.stiffener_count == 14 and result.bracket_count == 28
    names = sorted(p.name for p in out.iterdir())
    assert names == ["SY-101-bom.csv", "SY-101-report.txt", "SY-101.dxf", "SY-101.png"]
    assert sorted(p.name for p in result.files) == names


def test_dxf_round_trip(example_job, standard, shipped_profiles, tmp_path):
    build(example_job, standard, shipped_profiles, tmp_path, preview=False)
    doc = ezdxf.readfile(tmp_path / "SY-101.dxf")
    assert not doc.audit().has_errors
    allowed = {style.name for style in standard.layers.all()}
    assert allowed <= {layer.dxf.name for layer in doc.layers}
    msp = doc.modelspace()
    for entity in msp:
        assert entity.dxf.layer in allowed, (entity.dxftype(), entity.dxf.layer)
    (title,) = msp.query("INSERT")
    assert {a.dxf.tag: a.dxf.text for a in title.attribs} == title_values(example_job, 20)
    assert len(msp.query("DIMENSION")) == 17 + 10  # elevation + frame strip


def test_csv_and_report(example_job, standard, shipped_profiles, tmp_path):
    build(example_job, standard, shipped_profiles, tmp_path, preview=False)
    csv_lines = (tmp_path / "SY-101-bom.csv").read_text(encoding="utf-8").splitlines()
    assert csv_lines[0] == "ITEM,DESCRIPTION,QTY,LENGTH_MM,WEIGHT_KG" and len(csv_lines) == 6
    report = (tmp_path / "SY-101-report.txt").read_text(encoding="utf-8")
    assert "Result: OK" in report and "Scale: 1:20" in report and "placeholder" in report


def test_preview_is_a_landscape_sheet_image(example_job, standard, shipped_profiles, tmp_path):
    build(example_job, standard, shipped_profiles, tmp_path)
    height, width = mpimg.imread(tmp_path / "SY-101.png").shape[:2]
    assert width > height and width >= 3000


def test_no_preview_skips_the_png(example_job, standard, shipped_profiles, tmp_path):
    build(example_job, standard, shipped_profiles, tmp_path, preview=False)
    assert not (tmp_path / "SY-101.png").exists()


def test_rule_errors_write_nothing(job_dict, standard, shipped_profiles, tmp_path):
    job_dict["bulkhead"]["at_frame"] = 35
    out = tmp_path / "out"
    result = build(Job.model_validate(job_dict), standard, shipped_profiles, out)
    assert not result.ok and result.files == () and result.scale is None
    assert not out.exists()
    summary = format_summary(result)
    assert "Result: FAILED" in summary and "outside the frame range" in summary
