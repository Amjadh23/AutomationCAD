from shipdraw.checks import run_checks
from shipdraw.job import Job
from shipdraw.structure import build_parts


def check(job_dict, standard, profiles):
    job = Job.model_validate(job_dict)
    return run_checks(job, build_parts(job), standard, profiles)


def only_error(report, text):
    assert not report.ok
    assert any(text in e for e in report.errors), report.errors


def test_example_passes_cleanly_with_verified_profiles(job_dict, standard, verified_profiles):
    report = check(job_dict, standard, verified_profiles)
    assert report.ok and report.errors == () and report.warnings == ()


def test_placeholder_profile_weight_is_a_warning(job_dict, standard, shipped_profiles):
    report = check(job_dict, standard, shipped_profiles)
    assert report.ok
    assert len(report.warnings) == 1 and "placeholder" in report.warnings[0]


def test_self_crossing_outline(job_dict, standard, verified_profiles):
    # crosses itself but keeps a non-zero net area (a symmetric figure-8 would read as zero area)
    job_dict["bulkhead"]["outline_half"] = [[0, 0], [3000, 3500], [4000, 500], [0, 3500]]
    only_error(check(job_dict, standard, verified_profiles), "crosses itself")


def test_bulkhead_frame_outside_range(job_dict, standard, verified_profiles):
    job_dict["bulkhead"]["at_frame"] = 35
    only_error(check(job_dict, standard, verified_profiles), "FR35 is outside the frame range FR20-FR30")


def test_no_stiffener_inside_outline(job_dict, standard, verified_profiles):
    job_dict["bulkhead"]["stiffeners"]["first_at"] = 5000
    only_error(check(job_dict, standard, verified_profiles), "no stiffener position falls inside the outline")


def test_bracket_too_large_for_stiffener(job_dict, standard, verified_profiles):
    job_dict["bulkhead"]["brackets"]["size"] = 1700
    only_error(check(job_dict, standard, verified_profiles), "too large for 2 stiffener(s)")


def test_bracket_that_does_not_fit_on_the_edge(job_dict, standard, verified_profiles):
    job_dict["bulkhead"]["brackets"]["size"] = 500
    only_error(check(job_dict, standard, verified_profiles), "only 424 mm")


def test_unknown_profile(job_dict, standard, verified_profiles):
    job_dict["bulkhead"]["stiffeners"]["profile"] = "HP 999x9"
    only_error(check(job_dict, standard, verified_profiles), "not in the profile library")


def test_drawing_too_large_for_sheet(job_dict, standard, verified_profiles):
    job_dict["bulkhead"]["outline_half"] = [[0, 0], [40000, 0], [40000, 3500], [0, 3500]]
    only_error(check(job_dict, standard, verified_profiles), "does not fit the A1 sheet")


def test_wide_stiffener_spacing_is_a_warning(job_dict, standard, verified_profiles):
    job_dict["bulkhead"]["stiffeners"]["spacing"] = 800
    report = check(job_dict, standard, verified_profiles)
    assert report.ok
    assert any("above the standard's maximum of 700 mm" in w for w in report.warnings)
