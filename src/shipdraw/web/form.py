"""The drawing page's plain form fields ↔ the engine's Job."""
from __future__ import annotations

import math

from pydantic import ValidationError

from ..job import Job

DEFAULT_VALUES: dict[str, object] = {
    "project_name": "OSV 60m",
    "drawing_no": "SY-101",
    "title": "TRANSVERSE BULKHEAD AT FR25",
    "drawn_by": "AH",
    "revision": "A",
    "frame_first": 20,
    "frame_last": 30,
    "frame_spacing": 600,
    "at_frame": 25,
    "width": 9000,
    "height": 3500,
    "corner_cut": 900,
    "plate_thickness": 8,
    "plate_grade": "AH36",
    "profile": "HP 160x8",
    "bar_spacing": 600,
    "first_at": 300,
    "brackets_top": True,
    "brackets_bottom": True,
    "bracket_size": 250,
    "bracket_thickness": 8,
}

TEXT_FIELDS = ("project_name", "drawing_no", "title", "drawn_by", "revision", "plate_grade", "profile")
NUMBER_FIELDS = (
    "frame_first",
    "frame_last",
    "frame_spacing",
    "at_frame",
    "width",
    "height",
    "corner_cut",
    "plate_thickness",
    "bar_spacing",
    "first_at",
    "bracket_size",
    "bracket_thickness",
)
WHOLE_NUMBER_FIELDS = ("frame_first", "frame_last", "at_frame")
FLAG_FIELDS = ("brackets_top", "brackets_bottom")

# Engine locations (job paths and rule-check prefixes) → form field. The longest matching prefix wins.
_FIELD_FOR_LOCATION = {
    "project.name": "project_name",
    "project.drawing_no": "drawing_no",
    "project.title": "title",
    "project.drawn_by": "drawn_by",
    "project.revision": "revision",
    "frames": "frame_last",
    "frames.first": "frame_first",
    "frames.last": "frame_last",
    "frames.spacing": "frame_spacing",
    "bulkhead.at_frame": "at_frame",
    "bulkhead.outline_half": "width",
    "bulkhead.plate.thickness": "plate_thickness",
    "bulkhead.plate.grade": "plate_grade",
    "bulkhead.stiffeners": "first_at",
    "bulkhead.stiffeners.profile": "profile",
    "bulkhead.stiffeners.spacing": "bar_spacing",
    "bulkhead.stiffeners.first_at": "first_at",
    "bulkhead.brackets": "bracket_size",
    "bulkhead.brackets.size": "bracket_size",
    "bulkhead.brackets.thickness": "bracket_thickness",
    "sheet": "width",
}


class FormError(ValueError):
    """Some boxes on the form are wrong. field_errors maps a field name ("" for none) to a message."""

    def __init__(self, field_errors: dict[str, str]):
        super().__init__("; ".join(f"{name or 'form'}: {text}" for name, text in field_errors.items()))
        self.field_errors = field_errors


def field_for(location: str) -> str | None:
    parts = location.split(".")
    while parts:
        field = _FIELD_FOR_LOCATION.get(".".join(parts))
        if field:
            return field
        parts.pop()
    return None


def _sentence(text: str) -> str:
    return text[:1].upper() + text[1:]


def split_message(message: str) -> tuple[str | None, str]:
    """'bulkhead.at_frame: FR35 is outside …' → ('at_frame', 'FR35 is outside …')."""
    location, separator, text = message.partition(": ")
    if separator and location and " " not in location:
        return field_for(location), _sentence(text)
    return None, _sentence(message)


def outline_half(width: float, height: float, corner_cut: float) -> list[list[float]]:
    """Starboard half outline: a box, with a 45° cut at the bottom corner when corner_cut > 0."""
    half = width / 2
    if corner_cut == 0:
        return [[0, 0], [half, 0], [half, height], [0, height]]
    return [[0, 0], [half - corner_cut, 0], [half, corner_cut], [half, height], [0, height]]


def _read_number(raw: object, whole: bool) -> tuple[float | None, str | None]:
    if isinstance(raw, bool):
        return None, "Enter a number"
    if isinstance(raw, (int, float)):
        number = float(raw)
    else:
        text = str("" if raw is None else raw).strip().replace(",", "")
        if not text:
            return None, "Required"
        try:
            number = float(text)
        except ValueError:
            return None, "Enter a number"
    if not math.isfinite(number):
        return None, "Enter a number"
    if whole and not number.is_integer():
        return None, "Enter a whole number"
    return number, None


def _friendly(message: str) -> str:
    message = message.removeprefix("Value error, ")
    if "should match pattern" in message:
        return "Use only letters, numbers, - _ and ."
    if message.startswith("Input should be "):
        message = "Must be " + message.removeprefix("Input should be ")
    return _sentence(message)


def form_to_job(values: dict) -> Job:
    errors: dict[str, str] = {}
    numbers: dict[str, float] = {}
    for name in NUMBER_FIELDS:
        number, problem = _read_number(values.get(name), name in WHOLE_NUMBER_FIELDS)
        if problem:
            errors[name] = problem
        else:
            numbers[name] = number
    texts = {name: str(values.get(name) or "").strip() for name in TEXT_FIELDS}
    errors.update({name: "Required" for name, text in texts.items() if not text})
    flags = {name: bool(values.get(name)) for name in FLAG_FIELDS}

    for name in ("width", "height"):
        if name in numbers and numbers[name] <= 0:
            errors[name] = "Must be more than 0"
    if numbers.get("corner_cut", 0) < 0:
        errors["corner_cut"] = "Can't be negative"
    if not errors:
        width, height, cut = numbers["width"], numbers["height"], numbers["corner_cut"]
        if cut >= width / 2 or cut >= height:
            errors["corner_cut"] = "Must be smaller than half the width and smaller than the height"
    if errors:
        raise FormError(errors)

    data = {
        "project": {
            "name": texts["project_name"],
            "drawing_no": texts["drawing_no"],
            "title": texts["title"],
            "drawn_by": texts["drawn_by"],
            "revision": texts["revision"],
        },
        "frames": {
            "first": int(numbers["frame_first"]),
            "last": int(numbers["frame_last"]),
            "spacing": numbers["frame_spacing"],
        },
        "bulkhead": {
            "at_frame": int(numbers["at_frame"]),
            "outline_half": outline_half(numbers["width"], numbers["height"], numbers["corner_cut"]),
            "plate": {"thickness": numbers["plate_thickness"], "grade": texts["plate_grade"]},
            "stiffeners": {
                "profile": texts["profile"],
                "spacing": numbers["bar_spacing"],
                "first_at": numbers["first_at"],
            },
            "brackets": {
                "top": flags["brackets_top"],
                "bottom": flags["brackets_bottom"],
                "size": numbers["bracket_size"],
                "thickness": numbers["bracket_thickness"],
            },
        },
    }
    try:
        return Job.model_validate(data)
    except ValidationError as exc:
        field_errors: dict[str, str] = {}
        for err in exc.errors():
            location = ".".join(str(part) for part in err["loc"])
            field_errors.setdefault(field_for(location) or "", _friendly(err["msg"]))
        raise FormError(field_errors) from exc
