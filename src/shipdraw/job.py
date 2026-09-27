"""Job file: the parameters for one drawing, validated."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from pydantic import Field, ValidationError, field_validator, model_validator

from .config import ConfigError, StrictModel, format_validation_error, load_yaml
from .profiles import parse_profile


class ProjectInfo(StrictModel):
    name: str
    drawing_no: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")  # also the output file name
    title: str
    drawn_by: str
    revision: str
    date: dt.date = Field(default_factory=dt.date.today)


class Frames(StrictModel):
    first: int
    last: int
    spacing: float = Field(gt=0)

    @model_validator(mode="after")
    def _last_after_first(self) -> Frames:
        if self.last <= self.first:
            raise ValueError("last must be greater than first")
        return self


class Plate(StrictModel):
    thickness: float = Field(gt=0)
    grade: str = Field(min_length=1)


class Stiffeners(StrictModel):
    profile: str
    spacing: float = Field(gt=0)
    first_at: float = Field(ge=0)

    @field_validator("profile")
    @classmethod
    def _known_shape(cls, value: str) -> str:
        parse_profile(value)
        return value


class Brackets(StrictModel):
    top: bool
    bottom: bool
    size: float = Field(gt=0)
    thickness: float = Field(gt=0)


class Bulkhead(StrictModel):
    at_frame: int
    outline_half: list[tuple[float, float]] = Field(min_length=3)
    plate: Plate
    stiffeners: Stiffeners
    brackets: Brackets

    @field_validator("outline_half")
    @classmethod
    def _starboard_half_between_centreline_points(cls, points):
        for y, z in points:
            if y < 0 or z < 0:
                raise ValueError(f"point ({y:g}, {z:g}) has a negative coordinate; y and z must be >= 0")
        if points[0][0] != 0 or points[-1][0] != 0:
            raise ValueError("the first and last points must lie on the centreline (y = 0)")
        return points


class Job(StrictModel):
    project: ProjectInfo
    frames: Frames
    bulkhead: Bulkhead


def load_job(path: Path) -> Job:
    data = load_yaml(path)
    try:
        return Job.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(format_validation_error(path, exc, "job file")) from exc
