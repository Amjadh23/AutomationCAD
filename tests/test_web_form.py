import pytest

from shipdraw.web.form import DEFAULT_VALUES, FormError, form_to_job, outline_half, split_message


def with_changes(**changes):
    return {**DEFAULT_VALUES, **changes}


def field_errors(values):
    with pytest.raises(FormError) as info:
        form_to_job(values)
    return info.value.field_errors


def test_defaults_reproduce_the_example_job(example_job):
    job = form_to_job(DEFAULT_VALUES)
    assert job.bulkhead == example_job.bulkhead
    assert job.frames == example_job.frames
    assert job.project.model_dump(exclude={"date"}) == example_job.project.model_dump(exclude={"date"})


def test_square_corners_when_corner_cut_is_zero():
    assert outline_half(9000, 3500, 0) == [[0, 0], [4500, 0], [4500, 3500], [0, 3500]]
    assert outline_half(9000, 3500, 900) == [[0, 0], [3600, 0], [4500, 900], [4500, 3500], [0, 3500]]


def test_numbers_typed_as_text_are_accepted():
    job = form_to_job(with_changes(width="9,000", bar_spacing=" 600 ", at_frame="25"))
    assert job.bulkhead.stiffeners.spacing == 600
    assert job.bulkhead.outline_half[1] == (3600, 0)


@pytest.mark.parametrize(
    "field, value, message",
    [
        ("width", "abc", "Enter a number"),
        ("height", "", "Required"),
        ("at_frame", "25.5", "Enter a whole number"),
        ("width", "-100", "Must be more than 0"),
        ("corner_cut", "-5", "Can't be negative"),
        ("corner_cut", "5000", "smaller than half the width"),
        ("project_name", "  ", "Required"),
    ],
)
def test_field_errors(field, value, message):
    errors = field_errors(with_changes(**{field: value}))
    assert message in errors[field]


def test_engine_validation_is_mapped_back_to_fields():
    errors = field_errors(with_changes(bar_spacing="-600", drawing_no="SY/101", frame_last="10", profile="IPE 200"))
    assert set(errors) == {"bar_spacing", "drawing_no", "frame_last", "profile"}
    assert errors["bar_spacing"] == "Must be greater than 0"
    assert "letters" in errors["drawing_no"]
    assert errors["frame_last"] == "Last must be greater than first"
    assert errors["profile"].startswith("Profile 'IPE 200' must look like")


def test_split_message():
    assert split_message("bulkhead.at_frame: FR35 is outside the frame range FR20-FR30") == (
        "at_frame",
        "FR35 is outside the frame range FR20-FR30",
    )
    assert split_message("bulkhead.brackets: bottom bracket of the stiffener at y=3900: too short") == (
        "bracket_size",
        "Bottom bracket of the stiffener at y=3900: too short",
    )
    assert split_message("bulkhead.stiffeners.spacing: 800 mm is above")[0] == "bar_spacing"
    assert split_message("sheet: the drawing does not fit")[0] == "width"
    assert split_message("something odd happened") == (None, "Something odd happened")
