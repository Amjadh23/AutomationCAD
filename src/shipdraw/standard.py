"""Company drawing standard: sheet, layers, text, dimensions, title block, rule limits.

Everything that is "company style" lives in config/standard.yaml, so adopting the
client's real standard is a config change, not a code change.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import Field, ValidationError, model_validator

from .config import CONFIG_DIR, ConfigError, StrictModel, format_validation_error, load_yaml

REQUIRED_TITLE_TAGS = ("PROJECT", "TITLE", "DWG_NO", "REV", "SCALE", "DRAWN", "DATE")


class Zone(StrictModel):
    """Rectangle on the sheet in paper mm, measured from the sheet's bottom-left corner."""

    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class Zones(StrictModel):
    elevation: Zone
    frames: Zone
    bom: Zone


class Sheet(StrictModel):
    name: str
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    margin: float = Field(ge=0)
    scales: list[int] = Field(min_length=1)
    zones: Zones


class LayerStyle(StrictModel):
    name: str = Field(min_length=1)
    color: int = Field(ge=1, le=255)
    linetype: str = "Continuous"
    lineweight: int = Field(default=25, ge=0, le=211)  # hundredths of a mm


class Layers(StrictModel):
    border: LayerStyle
    title: LayerStyle
    plate: LayerStyle
    stiffener: LayerStyle
    bracket: LayerStyle
    centreline: LayerStyle
    frame: LayerStyle
    dim: LayerStyle
    text: LayerStyle
    bom: LayerStyle

    def all(self) -> list[LayerStyle]:
        return [getattr(self, role) for role in type(self).model_fields]

    @model_validator(mode="after")
    def _unique_names(self) -> Layers:
        names = [style.name.upper() for style in self.all()]
        repeated = sorted({name for name in names if names.count(name) > 1})
        if repeated:
            raise ValueError(f"layer names must be unique, repeated: {', '.join(repeated)}")
        return self


class TextHeights(StrictModel):
    """Paper mm."""

    label: float = Field(gt=0)
    view_title: float = Field(gt=0)
    frame_number: float = Field(gt=0)
    bom: float = Field(gt=0)


class DimensionStyle(StrictModel):
    """Paper mm."""

    text_height: float = Field(gt=0)
    arrow_size: float = Field(gt=0)
    extension_beyond: float = Field(ge=0)
    extension_offset: float = Field(ge=0)
    text_gap: float = Field(ge=0)


class TitleField(StrictModel):
    tag: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    label: str
    x: float
    y: float
    height: float = Field(gt=0)


class TitleBlock(StrictModel):
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    lines: list[tuple[float, float, float, float]] = []
    fields: list[TitleField] = Field(min_length=1)

    @model_validator(mode="after")
    def _required_fields(self) -> TitleBlock:
        tags = {f.tag for f in self.fields}
        missing = [tag for tag in REQUIRED_TITLE_TAGS if tag not in tags]
        if missing:
            raise ValueError(f"title block must define fields: {', '.join(missing)}")
        return self


class RuleLimits(StrictModel):
    max_stiffener_spacing: float = Field(gt=0)


class Standard(StrictModel):
    name: str
    sheet: Sheet
    layers: Layers
    text: TextHeights
    dimension: DimensionStyle
    title_block: TitleBlock
    rules: RuleLimits


def load_standard(path: Path = CONFIG_DIR / "standard.yaml") -> Standard:
    data = load_yaml(path)
    try:
        return Standard.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(format_validation_error(path, exc, "drawing standard")) from exc
