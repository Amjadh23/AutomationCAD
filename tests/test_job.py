import datetime as dt

import pytest

from shipdraw.config import ConfigError
from shipdraw.job import load_job


def test_example_job_loads(example_job):
    assert example_job.project.drawing_no == "SY-101"
    assert example_job.project.date == dt.date(2026, 9, 28)
    assert example_job.frames.spacing == 600.0
    assert example_job.bulkhead.outline_half[2] == (4500.0, 900.0)
    assert example_job.bulkhead.stiffeners.profile == "HP 160x8"
    assert example_job.bulkhead.brackets.top is True


def test_date_defaults_to_today(job_dict, write_yaml):
    del job_dict["project"]["date"]
    assert load_job(write_yaml(job_dict)).project.date == dt.date.today()


def invalid(job_dict, write_yaml, pattern):
    with pytest.raises(ConfigError, match=pattern):
        load_job(write_yaml(job_dict))


def test_negative_spacing(job_dict, write_yaml):
    job_dict["bulkhead"]["stiffeners"]["spacing"] = -600
    invalid(job_dict, write_yaml, r"bulkhead\.stiffeners\.spacing")


def test_last_frame_must_follow_first(job_dict, write_yaml):
    job_dict["frames"]["last"] = 20
    invalid(job_dict, write_yaml, r"frames: .*last must be greater than first")


def test_outline_must_start_and_end_on_centreline(job_dict, write_yaml):
    job_dict["bulkhead"]["outline_half"][0] = [100, 0]
    invalid(job_dict, write_yaml, r"bulkhead\.outline_half: .*centreline")


def test_outline_coordinates_must_not_be_negative(job_dict, write_yaml):
    job_dict["bulkhead"]["outline_half"][1] = [3600, -5]
    invalid(job_dict, write_yaml, r"bulkhead\.outline_half: .*negative")


def test_outline_needs_three_points(job_dict, write_yaml):
    job_dict["bulkhead"]["outline_half"] = [[0, 0], [0, 3500]]
    invalid(job_dict, write_yaml, r"bulkhead\.outline_half")


def test_profile_shape_is_checked(job_dict, write_yaml):
    job_dict["bulkhead"]["stiffeners"]["profile"] = "IPE 200"
    invalid(job_dict, write_yaml, r"bulkhead\.stiffeners\.profile: .*must look like")


def test_unknown_keys_are_rejected(job_dict, write_yaml):
    job_dict["bulkhead"]["colour"] = "red"
    invalid(job_dict, write_yaml, r"bulkhead\.colour")


def test_drawing_number_must_be_file_safe(job_dict, write_yaml):
    job_dict["project"]["drawing_no"] = "SY/101"
    invalid(job_dict, write_yaml, r"project\.drawing_no")


def test_empty_file_is_rejected(tmp_path):
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid job file"):
        load_job(path)
