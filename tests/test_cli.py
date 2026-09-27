import pytest

from conftest import EXAMPLE_JOB
from shipdraw.cli import main


def test_build_example(tmp_path, capsys):
    code = main(["build", str(EXAMPLE_JOB), "-o", str(tmp_path), "--no-preview"])
    assert code == 0
    assert "Result: OK" in capsys.readouterr().out
    assert (tmp_path / "SY-101.dxf").exists()


def test_invalid_job_exits_2(job_dict, write_yaml, tmp_path, capsys):
    job_dict["bulkhead"]["stiffeners"]["spacing"] = -600
    code = main(["build", str(write_yaml(job_dict)), "-o", str(tmp_path / "out")])
    assert code == 2
    assert "bulkhead.stiffeners.spacing" in capsys.readouterr().err


def test_rule_error_exits_1(job_dict, write_yaml, tmp_path, capsys):
    job_dict["bulkhead"]["at_frame"] = 35
    code = main(["build", str(write_yaml(job_dict)), "-o", str(tmp_path / "out")])
    assert code == 1
    out = capsys.readouterr().out
    assert "Result: FAILED" in out and "outside the frame range" in out


def test_missing_command_is_a_usage_error():
    with pytest.raises(SystemExit) as exit_info:
        main([])
    assert exit_info.value.code == 2
