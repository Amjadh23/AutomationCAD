# Bulkhead Drawing Engine v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Python command `shipdraw build <job.yaml>` that turns a small job file into a complete transverse-bulkhead drawing: a DXF that opens in AutoCAD, plus a PNG preview, a BOM CSV and a check report.

**Architecture:** Pure-Python layers with no DXF knowledge do the work:

- job and config loading;
- geometry;
- ship-structure rules;
- BOM;
- sheet layout;
- rule checks.

Only `src/shipdraw/render/` imports `ezdxf`; it draws the finished parts onto one A1 model-space sheet. `pipeline.build()` wires everything together, so the CLI now and the MCP server in build #2 both call a single function.

**Tech Stack:** Python 3.13, ezdxf 1.4, pydantic 2, PyYAML, matplotlib (preview only), pytest.

**Spec:** `docs/superpowers/specs/2026-09-28-bulkhead-drawing-engine-design.md`

**Deviations from the spec's architecture table.** All are refinements; no behaviour changes:

- **`config.py`** holds the shared plumbing: `CONFIG_DIR`, `ConfigError`, YAML loading and error formatting.
- **`profiles.py`** holds the profile library. It is a separate module because `job.py` needs profile-name parsing.
- **`layout.py`** holds scale selection and view placement, moved out of `render/sheet.py`. This keeps it pure, so `checks.py` can use it without importing ezdxf.
- **`pipeline.py`** holds `build(job, standard, profiles, out_dir, *, preview=True)`. It takes the profile library as an extra parameter, and `cli.py` is a thin wrapper around it.

## Global Constraints

- Python 3.13 in a local `.venv`. Run everything from the project root in Git Bash, using `.venv/Scripts/python -m …`.
- Only modules under `src/shipdraw/render/` may import `ezdxf` or `matplotlib`.
- Units are millimetres everywhere. Sizes in `config/standard.yaml` (sheet, zones, text, dimensions, title block) are **paper mm**; multiply by the sheet scale to get model units.
- DXF version R2018, model space only, `$INSUNITS` = 4 (mm).
- Code refers to layers only by role (`standard.layers.<role>.name`) and never hard-codes a layer name. Tests may use the shipped names.
- User-facing input or config problems raise `ConfigError` (CLI exit code 2). Rule problems are returned in a `CheckReport` (exit code 1; nothing written). Success is exit code 0, with or without warnings.
- The example job is `jobs/bhd-fr25.yaml`. Its expected results:
  - 14 stiffeners at ±300, ±900 … ±3900;
  - the ±3900 stiffeners run from z = 300 to z = 3500 (they start on the bilge chamfer); all others run from z = 0 to z = 3500;
  - 28 brackets;
  - sheet scale 1:20.
- Work on branch `feat/bulkhead-engine`. Every commit message ends with this trailer, passed as a second `-m`:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`

## File Structure

```
pyproject.toml                      package + deps + `shipdraw` entry point
.gitignore
README.md                           setup / usage for the draftsman
config/standard.yaml                PLACEHOLDER company standard (sheet, layers, text, dims, title block, rule limits)
config/profiles.yaml                HP bulb-flat weights (placeholders)
jobs/bhd-fr25.yaml                  example job
src/shipdraw/__init__.py
src/shipdraw/config.py              CONFIG_DIR, ConfigError, StrictModel, load_yaml, format_validation_error
src/shipdraw/standard.py            Standard model + load_standard()
src/shipdraw/profiles.py            parse_profile(), ProfileLibrary, ProfileWeight
src/shipdraw/job.py                 Job model + load_job()
src/shipdraw/geometry.py            pure 2-D geometry
src/shipdraw/structure.py           job → BulkheadParts
src/shipdraw/bom.py                 parts → Bom, bom_csv()
src/shipdraw/layout.py              plan_sheet(): scale + view placement
src/shipdraw/checks.py              run_checks() → CheckReport
src/shipdraw/render/__init__.py
src/shipdraw/render/sheet.py        new_document, add_text, add_linear_dim, draw_border, draw_title_block
src/shipdraw/render/bulkhead_view.py draw_elevation
src/shipdraw/render/frame_view.py   draw_frame_strip
src/shipdraw/render/bom_table.py    bom_cells, draw_bom_table
src/shipdraw/render/preview.py      render_png
src/shipdraw/pipeline.py            build(), BuildResult, format_summary
src/shipdraw/cli.py                 main()
tests/conftest.py                   shared fixtures (grows task by task)
tests/test_*.py                     one test file per module
```

---

### Task 1: Project scaffold, shared config plumbing, company standard

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `src/shipdraw/__init__.py`, `src/shipdraw/config.py`, `src/shipdraw/standard.py`, `config/standard.yaml`, `tests/conftest.py`
- Test: `tests/test_standard.py`

**Interfaces:**
- Produces:
  - `shipdraw.config`: `CONFIG_DIR: Path`, `class ConfigError(Exception)`, `class StrictModel(pydantic.BaseModel)`, `load_yaml(path) -> object`, `format_validation_error(path, exc, what: str) -> str`
  - `shipdraw.standard`: `load_standard(path=CONFIG_DIR / "standard.yaml") -> Standard`, `REQUIRED_TITLE_TAGS: tuple[str, ...]`, and the models `Standard`, `Sheet`, `Zones`, `Zone`, `LayerStyle`, `Layers` (with `.all() -> list[LayerStyle]`), `TextHeights`, `DimensionStyle`, `TitleBlock`, `TitleField`, `RuleLimits`
  - fixtures: `standard`, `write_yaml`

- [ ] **Step 1: Create the branch and scaffold**

```bash
git checkout -b feat/bulkhead-engine
mkdir -p src/shipdraw/render tests config jobs
```

`pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "shipdraw"
version = "0.1.0"
description = "Rule-based ship structural drawing engine (DXF for AutoCAD)"
requires-python = ">=3.13"
dependencies = ["ezdxf>=1.4", "pydantic>=2.7", "PyYAML>=6.0", "matplotlib>=3.9"]

[project.optional-dependencies]
dev = ["pytest>=8"]

[project.scripts]
shipdraw = "shipdraw.cli:main"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`.gitignore`:

```
.venv/
out/
__pycache__/
*.egg-info/
.pytest_cache/
```

`src/shipdraw/__init__.py`:

```python
"""shipdraw: rule-based ship structural drawing engine."""

__version__ = "0.1.0"
```

Install the package in editable mode. `.venv` already exists; if it doesn't, run `py -3.13 -m venv .venv` first.

```bash
.venv/Scripts/python -m pip install -e ".[dev]"
```

- [ ] **Step 2: Write the shared config module**

`src/shipdraw/config.py`:

```python
"""Shared config plumbing: config folder, YAML loading and user-facing errors."""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


class ConfigError(Exception):
    """A config or job file could not be read or is invalid. The message is user-facing."""


class StrictModel(BaseModel):
    """Base for all file-backed models: unknown keys are errors, instances are immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def load_yaml(path: Path) -> object:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc.strerror or exc}") from exc
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc


def format_validation_error(path: Path, exc: ValidationError, what: str) -> str:
    lines = [f"{path}: invalid {what}"]
    for err in exc.errors():
        where = ".".join(str(part) for part in err["loc"]) or "(top level)"
        lines.append(f"  {where}: {err['msg']}")
    return "\n".join(lines)
```

- [ ] **Step 3: Write the placeholder company standard**

`config/standard.yaml`:

```yaml
# PLACEHOLDER company drawing standard.
# Replace these values with the shipyard client's real standard when it arrives.
# Code looks layers up by role (border, plate, ...), so renaming a layer here is
# all that is needed. Sizes are in PAPER millimetres.
name: "Placeholder shipyard standard v0"

sheet:
  name: A1
  width: 841
  height: 594
  margin: 10
  scales: [20, 25, 50, 100]        # allowed 1:N; the largest drawing that fits wins
  zones:                            # from the sheet's bottom-left corner
    elevation: { x: 20,  y: 150, width: 620, height: 424 }
    frames:    { x: 20,  y: 20,  width: 620, height: 120 }
    bom:       { x: 651, y: 80,  width: 180, height: 504 }

layers:
  border:     { name: "BORDER",     color: 7, lineweight: 50 }
  title:      { name: "TITLE",      color: 7, lineweight: 25 }
  plate:      { name: "PLATE",      color: 7, lineweight: 50 }
  stiffener:  { name: "STIFFENER",  color: 3, lineweight: 35 }
  bracket:    { name: "BRACKET",    color: 4, lineweight: 35 }
  centreline: { name: "CENTRELINE", color: 1, linetype: "CENTER", lineweight: 18 }
  frame:      { name: "FRAME",      color: 8, lineweight: 18 }
  dim:        { name: "DIM",        color: 2, lineweight: 18 }
  text:       { name: "TEXT",       color: 7, lineweight: 18 }
  bom:        { name: "BOM",        color: 7, lineweight: 18 }

text:
  label: 2.5
  view_title: 5
  frame_number: 2.5
  bom: 2.5

dimension:
  text_height: 2.5
  arrow_size: 2.5
  extension_beyond: 1.25
  extension_offset: 1
  text_gap: 0.6

title_block:                        # origin at the block's bottom-left corner
  width: 180
  height: 60
  lines:
    - [0, 40, 180, 40]
    - [0, 20, 180, 20]
    - [80, 0, 80, 20]
    - [100, 0, 100, 20]
    - [125, 0, 125, 20]
    - [150, 0, 150, 20]
  fields:
    - { tag: PROJECT, label: "PROJECT",     x: 3,   y: 47, height: 5 }
    - { tag: TITLE,   label: "TITLE",       x: 3,   y: 27, height: 5 }
    - { tag: DWG_NO,  label: "DRAWING NO.", x: 3,   y: 6,  height: 5 }
    - { tag: REV,     label: "REV",         x: 83,  y: 6,  height: 3.5 }
    - { tag: SCALE,   label: "SCALE",       x: 103, y: 6,  height: 3.5 }
    - { tag: DRAWN,   label: "DRAWN",       x: 128, y: 6,  height: 3.5 }
    - { tag: DATE,    label: "DATE",        x: 153, y: 6,  height: 2.5 }

rules:
  max_stiffener_spacing: 700        # mm; above this the check report warns
```

`tests/conftest.py`:

```python
from pathlib import Path

import pytest
import yaml

from shipdraw.config import CONFIG_DIR

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def standard():
    from shipdraw.standard import load_standard

    return load_standard(CONFIG_DIR / "standard.yaml")


@pytest.fixture
def write_yaml(tmp_path):
    """Write a dict to a YAML file in tmp_path and return its path."""

    def _write(data, name: str = "data.yaml") -> Path:
        path = tmp_path / name
        path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
        return path

    return _write
```

- [ ] **Step 4: Write the failing tests**

`tests/test_standard.py`:

```python
import pytest
import yaml

from shipdraw.config import CONFIG_DIR, ConfigError
from shipdraw.standard import REQUIRED_TITLE_TAGS, load_standard


def shipped_dict():
    return yaml.safe_load((CONFIG_DIR / "standard.yaml").read_text(encoding="utf-8"))


def test_shipped_standard_loads():
    std = load_standard(CONFIG_DIR / "standard.yaml")
    assert std.sheet.name == "A1"
    assert (std.sheet.width, std.sheet.height) == (841, 594)
    assert std.sheet.scales == [20, 25, 50, 100]
    assert std.layers.centreline.linetype == "CENTER"
    assert len({layer.name for layer in std.layers.all()}) == 10
    assert set(REQUIRED_TITLE_TAGS) <= {f.tag for f in std.title_block.fields}
    assert std.rules.max_stiffener_spacing == 700


def test_default_path_is_the_shipped_standard():
    assert load_standard() == load_standard(CONFIG_DIR / "standard.yaml")


def test_missing_layer_role_is_reported(write_yaml):
    data = shipped_dict()
    del data["layers"]["bom"]
    with pytest.raises(ConfigError, match=r"layers\.bom"):
        load_standard(write_yaml(data))


def test_duplicate_layer_names_are_rejected(write_yaml):
    data = shipped_dict()
    data["layers"]["bom"]["name"] = "TEXT"
    with pytest.raises(ConfigError, match="repeated: TEXT"):
        load_standard(write_yaml(data))


def test_title_block_must_define_required_fields(write_yaml):
    data = shipped_dict()
    data["title_block"]["fields"] = [f for f in data["title_block"]["fields"] if f["tag"] != "REV"]
    with pytest.raises(ConfigError, match="must define fields: REV"):
        load_standard(write_yaml(data))


def test_invalid_yaml_is_reported(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("sheet: [unclosed", encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid YAML"):
        load_standard(path)


def test_missing_file_is_reported(tmp_path):
    with pytest.raises(ConfigError, match="cannot read"):
        load_standard(tmp_path / "nope.yaml")
```

- [ ] **Step 5: Run the tests and confirm they fail**

Run: `.venv/Scripts/python -m pytest tests/test_standard.py -v`
Expected: collection ERROR `ModuleNotFoundError: No module named 'shipdraw.standard'`

- [ ] **Step 6: Implement `standard.py`**

`src/shipdraw/standard.py`:

```python
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
```

- [ ] **Step 7: Run the tests and confirm they pass**

Run: `.venv/Scripts/python -m pytest tests/test_standard.py -v`
Expected: 7 passed

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .gitignore src/shipdraw/__init__.py src/shipdraw/config.py src/shipdraw/standard.py config/standard.yaml tests/conftest.py tests/test_standard.py
git commit -m "feat: project scaffold and placeholder company standard" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Profile library

**Files:**
- Create: `src/shipdraw/profiles.py`, `config/profiles.yaml`
- Modify: `tests/conftest.py` (append fixtures)
- Test: `tests/test_profiles.py`

**Interfaces:**
- Consumes: `shipdraw.config` (Task 1)
- Produces:
  - `parse_profile(name: str) -> ProfileSpec`, which raises `ValueError` containing `"must look like"`
  - `ProfileSpec(kind: str, dims: tuple[float, ...])`
  - `ProfileWeight(kg_per_m: float, placeholder: bool = False, approx: bool = False)`
  - `ProfileLibrary(hp_entries: dict[str, ProfileWeight])`, with `.load(path=CONFIG_DIR / "profiles.yaml")` and `.weight(name) -> ProfileWeight`
  - `class UnknownProfileError(LookupError)`
  - `STEEL_DENSITY_KG_M3 = 7850.0`
  - fixtures: `verified_profiles` (HP 160x8 = 12.4 kg/m, not a placeholder) and `shipped_profiles`

- [ ] **Step 1: Write the failing tests**

`tests/test_profiles.py`:

```python
import pytest

from shipdraw.config import CONFIG_DIR, ConfigError
from shipdraw.profiles import (
    ProfileLibrary,
    ProfileSpec,
    ProfileWeight,
    UnknownProfileError,
    parse_profile,
)


@pytest.mark.parametrize(
    "name, kind, dims",
    [
        ("FB 100x10", "FB", (100.0, 10.0)),
        ("FB 80x6.5", "FB", (80.0, 6.5)),
        ("HP 160x8", "HP", (160.0, 8.0)),
        ("L 150x90x10", "L", (150.0, 90.0, 10.0)),
    ],
)
def test_parse_profile(name, kind, dims):
    assert parse_profile(name) == ProfileSpec(kind, dims)


@pytest.mark.parametrize("name", ["IPE 200", "FB 100", "HP160x8", "L 100x75", "fb 100x10", ""])
def test_parse_profile_rejects_unknown_shapes(name):
    with pytest.raises(ValueError, match="must look like"):
        parse_profile(name)


def test_flat_bar_weight_is_calculated():
    weight = ProfileLibrary({}).weight("FB 100x10")
    assert weight.kg_per_m == pytest.approx(7.85)
    assert not weight.placeholder and not weight.approx


def test_angle_weight_is_calculated_and_marked_approx():
    weight = ProfileLibrary({}).weight("L 150x90x10")
    assert weight.kg_per_m == pytest.approx(18.055)  # (150 + 90 - 10) * 10 * 7.85e-3
    assert weight.approx


def test_hp_weight_comes_from_the_library():
    library = ProfileLibrary({"HP 160x8": ProfileWeight(12.4, placeholder=True)})
    assert library.weight("HP 160x8") == ProfileWeight(12.4, placeholder=True)


def test_unknown_hp_raises():
    with pytest.raises(UnknownProfileError, match="HP 999x9"):
        ProfileLibrary({}).weight("HP 999x9")


def test_shipped_hp_values_are_flagged_placeholder():
    weight = ProfileLibrary.load(CONFIG_DIR / "profiles.yaml").weight("HP 160x8")
    assert weight.placeholder and weight.kg_per_m > 0


def test_library_rejects_non_hp_entries(write_yaml):
    path = write_yaml({"hp": {"FB 100x10": {"kg_per_m": 7.85}}})
    with pytest.raises(ConfigError, match="not an HP profile"):
        ProfileLibrary.load(path)


def test_library_rejects_bad_weight(write_yaml):
    path = write_yaml({"hp": {"HP 160x8": {"kg_per_m": -1}}})
    with pytest.raises(ConfigError, match=r"hp\.HP 160x8\.kg_per_m"):
        ProfileLibrary.load(path)
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `.venv/Scripts/python -m pytest tests/test_profiles.py -v`
Expected: collection ERROR `No module named 'shipdraw.profiles'`

- [ ] **Step 3: Implement the module and the library file**

`src/shipdraw/profiles.py`:

```python
"""Stiffener profiles: name parsing and weight per metre."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field, ValidationError

from .config import CONFIG_DIR, ConfigError, StrictModel, format_validation_error, load_yaml

STEEL_DENSITY_KG_M3 = 7850.0
# 1 mm² of cross-section over 1 m of length is 1e-6 m³ of steel.
_KG_PER_M_PER_MM2 = STEEL_DENSITY_KG_M3 * 1e-6

_NUM = r"(\d+(?:\.\d+)?)"
_PATTERNS = {
    "FB": re.compile(rf"^FB {_NUM}x{_NUM}$"),
    "HP": re.compile(rf"^HP {_NUM}x{_NUM}$"),
    "L": re.compile(rf"^L {_NUM}x{_NUM}x{_NUM}$"),
}


@dataclass(frozen=True)
class ProfileSpec:
    kind: str  # "FB", "HP" or "L"
    dims: tuple[float, ...]  # FB: (b, t); HP: (h, t); L: (a, b, t)


@dataclass(frozen=True)
class ProfileWeight:
    kg_per_m: float
    placeholder: bool = False  # value not yet checked against a supplier table
    approx: bool = False  # calculated with simplifications (angle root radius ignored)


class UnknownProfileError(LookupError):
    """The profile has no known weight. The message is user-facing."""


def parse_profile(name: str) -> ProfileSpec:
    for kind, pattern in _PATTERNS.items():
        match = pattern.match(name)
        if match:
            return ProfileSpec(kind, tuple(float(g) for g in match.groups()))
    raise ValueError(f"profile {name!r} must look like 'FB 100x10', 'L 150x90x10' or 'HP 160x8'")


class _HpEntry(StrictModel):
    kg_per_m: float = Field(gt=0)
    placeholder: bool = False


class _ProfilesFile(StrictModel):
    hp: dict[str, _HpEntry] = {}


class ProfileLibrary:
    """Weights per metre: calculated for FB and L, looked up for HP bulb flats."""

    def __init__(self, hp_entries: dict[str, ProfileWeight]):
        self._hp = dict(hp_entries)

    @classmethod
    def load(cls, path: Path = CONFIG_DIR / "profiles.yaml") -> ProfileLibrary:
        data = load_yaml(path) or {}
        try:
            parsed = _ProfilesFile.model_validate(data)
        except ValidationError as exc:
            raise ConfigError(format_validation_error(path, exc, "profile library")) from exc
        entries = {}
        for name, entry in parsed.hp.items():
            try:
                spec = parse_profile(name)
            except ValueError as exc:
                raise ConfigError(f"{path}: {exc}") from exc
            if spec.kind != "HP":
                raise ConfigError(f"{path}: {name!r} is listed under 'hp' but is not an HP profile")
            entries[name] = ProfileWeight(entry.kg_per_m, placeholder=entry.placeholder)
        return cls(entries)

    def weight(self, name: str) -> ProfileWeight:
        spec = parse_profile(name)
        if spec.kind == "FB":
            b, t = spec.dims
            return ProfileWeight(b * t * _KG_PER_M_PER_MM2)
        if spec.kind == "L":
            a, b, t = spec.dims
            return ProfileWeight((a + b - t) * t * _KG_PER_M_PER_MM2, approx=True)
        try:
            return self._hp[name]
        except KeyError:
            raise UnknownProfileError(f"HP profile {name!r} is not in the profile library") from None
```

`config/profiles.yaml`:

```yaml
# Stiffener profile library.
# FB (flat bar) and L (angle) weights are calculated from their dimensions.
# HP (bulb flat) weights must be listed here. Every value below is a PLACEHOLDER
# estimate: replace it with the supplier's table and delete "placeholder: true".
hp:
  "HP 120x7":  { kg_per_m: 7.8,  placeholder: true }
  "HP 140x7":  { kg_per_m: 9.3,  placeholder: true }
  "HP 160x8":  { kg_per_m: 12.4, placeholder: true }
  "HP 180x9":  { kg_per_m: 15.5, placeholder: true }
  "HP 200x10": { kg_per_m: 19.0, placeholder: true }
```

Append to `tests/conftest.py`:

```python
@pytest.fixture
def verified_profiles():
    """Library with one verified (non-placeholder) HP entry, independent of config/."""
    from shipdraw.profiles import ProfileLibrary, ProfileWeight

    return ProfileLibrary({"HP 160x8": ProfileWeight(12.4)})


@pytest.fixture
def shipped_profiles():
    from shipdraw.profiles import ProfileLibrary

    return ProfileLibrary.load(CONFIG_DIR / "profiles.yaml")
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/Scripts/python -m pytest tests/test_profiles.py -v`
Expected: 17 passed

- [ ] **Step 5: Commit**

```bash
git add src/shipdraw/profiles.py config/profiles.yaml tests/conftest.py tests/test_profiles.py
git commit -m "feat: stiffener profile library with weight per metre" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Job file model and example job

**Files:**
- Create: `src/shipdraw/job.py`, `jobs/bhd-fr25.yaml`
- Modify: `tests/conftest.py` (append fixtures)
- Test: `tests/test_job.py`

**Interfaces:**
- Consumes: `shipdraw.config`, `shipdraw.profiles.parse_profile`
- Produces:
  - `load_job(path) -> Job`, which raises `ConfigError`
  - the models:
    - `Job(project: ProjectInfo, frames: Frames, bulkhead: Bulkhead)`
    - `ProjectInfo(name, drawing_no, title, drawn_by, revision, date: datetime.date)`
    - `Frames(first: int, last: int, spacing: float)`
    - `Bulkhead(at_frame: int, outline_half: list[tuple[float, float]], plate: Plate, stiffeners: Stiffeners, brackets: Brackets)`
    - `Plate(thickness, grade)`
    - `Stiffeners(profile, spacing, first_at)`
    - `Brackets(top: bool, bottom: bool, size, thickness)`
  - fixtures: `EXAMPLE_JOB` (module constant in conftest), `job_dict` (a fresh dict copy of the example), `example_job`

- [ ] **Step 1: Write the example job**

`jobs/bhd-fr25.yaml`:

```yaml
# Example job: transverse bulkhead at FR25 of a 60 m offshore support vessel.
project:
  name: "OSV 60m"
  drawing_no: "SY-101"
  title: "TRANSVERSE BULKHEAD AT FR25"
  drawn_by: "AH"
  revision: "A"
  date: 2026-09-28
frames:
  first: 20
  last: 30
  spacing: 600
bulkhead:
  at_frame: 25
  outline_half:            # (y from CL, z from baseline) in mm; starboard half, CL to CL
    - [0, 0]
    - [3600, 0]
    - [4500, 900]          # 900 x 900 bilge chamfer
    - [4500, 3500]
    - [0, 3500]
  plate:      { thickness: 8, grade: "AH36" }
  stiffeners: { profile: "HP 160x8", spacing: 600, first_at: 300 }
  brackets:   { top: true, bottom: true, size: 250, thickness: 8 }
```

Append to `tests/conftest.py`:

```python
EXAMPLE_JOB = ROOT / "jobs" / "bhd-fr25.yaml"


@pytest.fixture
def job_dict():
    """A fresh, mutable copy of the example job as plain data."""
    return yaml.safe_load(EXAMPLE_JOB.read_text(encoding="utf-8"))


@pytest.fixture
def example_job():
    from shipdraw.job import load_job

    return load_job(EXAMPLE_JOB)
```

- [ ] **Step 2: Write the failing tests**

`tests/test_job.py`:

```python
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
```

- [ ] **Step 3: Run the tests and confirm they fail**

Run: `.venv/Scripts/python -m pytest tests/test_job.py -v`
Expected: ERRORs `No module named 'shipdraw.job'`

- [ ] **Step 4: Implement `job.py`**

`src/shipdraw/job.py`:

```python
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
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `.venv/Scripts/python -m pytest tests/test_job.py -v`
Expected: 11 passed

- [ ] **Step 6: Commit**

```bash
git add src/shipdraw/job.py jobs/bhd-fr25.yaml tests/conftest.py tests/test_job.py
git commit -m "feat: validated job file model and example bulkhead job" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Geometry

**Files:**
- Create: `src/shipdraw/geometry.py`
- Test: `tests/test_geometry.py`

**Interfaces:**
- Produces:
  - `Point = tuple[float, float]` and `EPS = 1e-6`
  - `mirror_half_outline(half) -> list[Point]`
  - `remove_collinear(points) -> list[Point]`
  - `polygon_area(points) -> float` (signed, positive when counter-clockwise)
  - `bounding_box(points) -> (min_x, min_y, max_x, max_y)`
  - `segments_intersect(p1, p2, q1, q2) -> bool`
  - `is_simple(points) -> bool`
  - `outline_problems(points) -> list[str]`
  - `clip_vertical(polygon, x) -> list[tuple[float, float]]`
  - `contains_point(polygon, p) -> bool` (boundary counts as inside)
  - `bracket_triangle(polygon, end, inward, size) -> tuple[Point, Point, Point]`
  - `class BracketFitError(ValueError)`

- [ ] **Step 1: Write the failing tests**

`tests/test_geometry.py`:

```python
import pytest

from shipdraw.geometry import (
    BracketFitError,
    bounding_box,
    bracket_triangle,
    clip_vertical,
    contains_point,
    is_simple,
    mirror_half_outline,
    outline_problems,
    polygon_area,
    remove_collinear,
)

HALF = [(0, 0), (3600, 0), (4500, 900), (4500, 3500), (0, 3500)]
FULL = [(3600, 0), (4500, 900), (4500, 3500), (-4500, 3500), (-4500, 900), (-3600, 0)]


def flat(points):
    return [c for p in points for c in p]


def test_mirror_builds_full_outline_without_centreline_vertices():
    assert mirror_half_outline(HALF) == FULL


def test_mirrored_outline_is_symmetric():
    full = mirror_half_outline(HALF)
    assert {(-x, y) for x, y in full} == set(full)


def test_remove_collinear_drops_duplicates_and_straight_runs():
    assert remove_collinear([(0, 0), (0, 0), (10, 0), (10, 10)]) == [(0, 0), (10, 0), (10, 10)]
    assert remove_collinear([(0, 0), (5, 0), (10, 0), (10, 10)]) == [(0, 0), (10, 0), (10, 10)]


def test_polygon_area_and_bounding_box():
    assert polygon_area(FULL) == pytest.approx(9000 * 3500 - 900 * 900)  # two 900x900/2 chamfers
    assert bounding_box(FULL) == (-4500, 0, 4500, 3500)


def test_clip_vertical_on_flat_bottom_and_chamfer():
    assert flat(clip_vertical(FULL, 300)) == pytest.approx([0, 3500])
    assert flat(clip_vertical(FULL, 3900)) == pytest.approx([300, 3500])
    assert flat(clip_vertical(FULL, 0)) == pytest.approx([0, 3500])


def test_clip_vertical_outside_or_on_side_is_empty():
    assert clip_vertical(FULL, 4500) == []
    assert clip_vertical(FULL, 5000) == []


def test_clip_vertical_returns_every_inside_span():
    c_shape = [(0, 0), (3000, 0), (3000, 1000), (1000, 1000), (1000, 2000), (3000, 2000), (3000, 3000), (0, 3000)]
    assert flat(clip_vertical(c_shape, 2000)) == pytest.approx([0, 1000, 2000, 3000])


def test_is_simple():
    assert is_simple(FULL)
    assert not is_simple([(0, 0), (10, 10), (10, 0), (0, 10)])  # bow tie
    assert not is_simple([(0, 0), (10, 0), (5, 0), (5, 5)])  # folds back on itself


def test_outline_problems():
    assert outline_problems(FULL) == []
    assert outline_problems([(0, 0), (1, 1)]) == ["outline needs at least 3 distinct corners, got 2"]
    assert outline_problems([(0, 0), (10, 0), (20, 0)]) == ["outline has zero area"]
    # asymmetric bow tie: a symmetric one has zero net area and would report that instead
    assert outline_problems([(0, 0), (10, 10), (10, 0), (0, 20)]) == ["outline crosses itself"]


def test_contains_point():
    assert contains_point(FULL, (0, 1000))
    assert contains_point(FULL, (4500, 2000))  # on the boundary
    assert not contains_point(FULL, (4400, 50))  # cut away by the chamfer
    assert not contains_point(FULL, (0, 4000))


def test_bottom_bracket_on_chamfer_runs_along_the_slope():
    tri = bracket_triangle(FULL, (3900, 300), (0, 1), 250)
    leg = 250 / 2**0.5
    assert flat(tri) == pytest.approx([3900, 300, 3900, 550, 3900 - leg, 300 - leg])


def test_top_bracket_points_towards_centreline():
    assert flat(bracket_triangle(FULL, (300, 3500), (0, -1), 250)) == pytest.approx([300, 3500, 300, 3250, 50, 3500])
    assert flat(bracket_triangle(FULL, (-300, 3500), (0, -1), 250)) == pytest.approx([-300, 3500, -300, 3250, -50, 3500])


def test_bracket_on_centreline_points_to_starboard():
    assert flat(bracket_triangle(FULL, (0, 0), (0, 1), 250)) == pytest.approx([0, 0, 0, 250, 250, 0])


def test_brackets_lie_inside_the_plate():
    for end, inward in [((3900, 300), (0, 1)), ((300, 3500), (0, -1)), ((-3300, 0), (0, 1))]:
        assert all(contains_point(FULL, p) for p in bracket_triangle(FULL, end, inward, 250))


def test_bracket_longer_than_the_edge_is_rejected():
    with pytest.raises(BracketFitError, match="only 424 mm"):
        bracket_triangle(FULL, (3900, 300), (0, 1), 500)
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `.venv/Scripts/python -m pytest tests/test_geometry.py -v`
Expected: collection ERROR `No module named 'shipdraw.geometry'`

- [ ] **Step 3: Implement `geometry.py`**

`src/shipdraw/geometry.py`:

```python
"""Pure 2-D geometry for straight-line outlines. No DXF and no ship knowledge.

Points are (x, y) tuples in millimetres. A polygon is a list of vertices with an
implied closing edge from the last vertex back to the first.
"""
from __future__ import annotations

import math
from collections.abc import Sequence

Point = tuple[float, float]
EPS = 1e-6


class BracketFitError(ValueError):
    """A bracket cannot be placed at a stiffener end. The message is user-facing."""


def mirror_half_outline(half: Sequence[Point]) -> list[Point]:
    """Full outline from a half outline on the +x side that starts and ends on x = 0."""
    points = [(float(x), float(y)) for x, y in half]
    mirrored = [(-x, y) for x, y in reversed(points[1:-1])]
    return remove_collinear(points + mirrored)


def remove_collinear(points: Sequence[Point]) -> list[Point]:
    """Drop duplicate vertices and vertices lying on a straight run between their neighbours."""
    pts = list(points)
    changed = True
    while changed and len(pts) >= 3:
        changed = False
        for i in range(len(pts)):
            prev, cur, nxt = pts[i - 1], pts[i], pts[(i + 1) % len(pts)]
            ax, ay = cur[0] - prev[0], cur[1] - prev[1]
            bx, by = nxt[0] - cur[0], nxt[1] - cur[1]
            la, lb = math.hypot(ax, ay), math.hypot(bx, by)
            duplicate = la < EPS or lb < EPS
            straight = not duplicate and abs(ax * by - ay * bx) <= EPS * la * lb and ax * bx + ay * by > 0
            if duplicate or straight:
                del pts[i]
                changed = True
                break
    return pts


def polygon_area(points: Sequence[Point]) -> float:
    """Signed area (shoelace formula): positive for counter-clockwise vertex order."""
    n = len(points)
    return 0.5 * sum(
        points[i][0] * points[(i + 1) % n][1] - points[(i + 1) % n][0] * points[i][1] for i in range(n)
    )


def bounding_box(points: Sequence[Point]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _side(a: Point, b: Point, p: Point) -> int:
    """+1 if p is left of the directed line a→b, -1 if right, 0 if within EPS of it."""
    length = math.hypot(b[0] - a[0], b[1] - a[1])
    if length < EPS:
        return 0
    distance = ((b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])) / length
    return 0 if abs(distance) <= EPS else (1 if distance > 0 else -1)


def _within_box(a: Point, b: Point, p: Point) -> bool:
    return (
        min(a[0], b[0]) - EPS <= p[0] <= max(a[0], b[0]) + EPS
        and min(a[1], b[1]) - EPS <= p[1] <= max(a[1], b[1]) + EPS
    )


def _on_segment(a: Point, b: Point, p: Point) -> bool:
    return _side(a, b, p) == 0 and _within_box(a, b, p)


def segments_intersect(p1: Point, p2: Point, q1: Point, q2: Point) -> bool:
    d1, d2 = _side(q1, q2, p1), _side(q1, q2, p2)
    d3, d4 = _side(p1, p2, q1), _side(p1, p2, q2)
    if d1 * d2 < 0 and d3 * d4 < 0:
        return True
    return (
        (d1 == 0 and _within_box(q1, q2, p1))
        or (d2 == 0 and _within_box(q1, q2, p2))
        or (d3 == 0 and _within_box(p1, p2, q1))
        or (d4 == 0 and _within_box(p1, p2, q2))
    )


def is_simple(points: Sequence[Point]) -> bool:
    """True if no two edges cross or touch, apart from neighbours sharing their common vertex."""
    n = len(points)
    if n < 3:
        return False
    edges = [(points[i], points[(i + 1) % n]) for i in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            (a1, a2), (b1, b2) = edges[i], edges[j]
            if j == i + 1 or (i == 0 and j == n - 1):
                shared, other_a, other_b = (a2, a1, b2) if j == i + 1 else (a1, a2, b1)
                folds_back = _side(shared, other_a, other_b) == 0 and (
                    (other_a[0] - shared[0]) * (other_b[0] - shared[0])
                    + (other_a[1] - shared[1]) * (other_b[1] - shared[1])
                    > 0
                )
                if folds_back:
                    return False
                continue
            if segments_intersect(a1, a2, b1, b2):
                return False
    return True


def outline_problems(points: Sequence[Point]) -> list[str]:
    if len(points) < 3:
        return [f"outline needs at least 3 distinct corners, got {len(points)}"]
    if abs(polygon_area(points)) < 1.0:
        return ["outline has zero area"]
    if not is_simple(points):
        return ["outline crosses itself"]
    return []


def clip_vertical(polygon: Sequence[Point], x: float) -> list[tuple[float, float]]:
    """Parts of the vertical line at x inside the polygon, as (y_low, y_high), bottom to top."""
    ys = []
    n = len(polygon)
    for i in range(n):
        (x1, y1), (x2, y2) = polygon[i], polygon[(i + 1) % n]
        if (x1 <= x < x2) or (x2 <= x < x1):  # half-open, so a vertex is counted once
            ys.append(y1 + (x - x1) * (y2 - y1) / (x2 - x1))
    ys.sort()
    return [(ys[k], ys[k + 1]) for k in range(0, len(ys) - 1, 2) if ys[k + 1] - ys[k] > EPS]


def contains_point(polygon: Sequence[Point], p: Point) -> bool:
    """True if p is inside the polygon or on its boundary."""
    n = len(polygon)
    if any(_on_segment(polygon[i], polygon[(i + 1) % n], p) for i in range(n)):
        return True
    inside = False
    for i in range(n):
        (x1, y1), (x2, y2) = polygon[i], polygon[(i + 1) % n]
        if (y1 > p[1]) != (y2 > p[1]):
            if p[0] < x1 + (p[1] - y1) * (x2 - x1) / (y2 - y1):
                inside = not inside
    return inside


def bracket_triangle(
    polygon: Sequence[Point], end: Point, inward: Point, size: float
) -> tuple[Point, Point, Point]:
    """Triangular bracket at a stiffener end.

    end:    the stiffener end point; it lies on the outline.
    inward: unit vector along the stiffener, pointing into the plate.
    One leg runs `size` along the stiffener. The other runs `size` along the outline
    edge that leaves `end` towards the centreline (x = 0); from x = 0 itself, towards +x.
    """
    candidates = []  # (|x| of the edge's far end, unit direction, length available)
    n = len(polygon)
    for i in range(n):
        a, b = polygon[i], polygon[(i + 1) % n]
        if not _on_segment(a, b, end):
            continue
        for far in (a, b):
            length = math.hypot(far[0] - end[0], far[1] - end[1])
            if length <= EPS:
                continue
            direction = ((far[0] - end[0]) / length, (far[1] - end[1]) / length)
            if abs(end[0]) <= EPS:
                towards_centre = direction[0] > EPS
            else:
                towards_centre = direction[0] * end[0] < -EPS
            if towards_centre:
                candidates.append((abs(far[0]), direction, length))
    if not candidates:
        raise BracketFitError(f"no outline edge runs from ({end[0]:g}, {end[1]:g}) towards the centreline")
    _, direction, length = min(candidates, key=lambda c: c[0])
    if length < size - EPS:
        raise BracketFitError(
            f"bracket at ({end[0]:g}, {end[1]:g}) needs {size:g} mm along the outline, "
            f"but the edge towards the centreline is only {length:.0f} mm"
        )
    ex, ey = end
    return (
        (ex, ey),
        (ex + inward[0] * size, ey + inward[1] * size),
        (ex + direction[0] * size, ey + direction[1] * size),
    )
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/Scripts/python -m pytest tests/test_geometry.py -v`
Expected: 15 passed

- [ ] **Step 5: Commit**

```bash
git add src/shipdraw/geometry.py tests/test_geometry.py
git commit -m "feat: pure geometry for outlines, clipping and bracket triangles" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Structure rules (job → parts)

**Files:**
- Create: `src/shipdraw/structure.py`
- Modify: `tests/conftest.py` (append the `example_parts` fixture)
- Test: `tests/test_structure.py`

**Interfaces:**
- Consumes: `shipdraw.geometry`, `shipdraw.job.Job`
- Produces:
  - `build_parts(job: Job) -> BulkheadParts`
  - `stiffener_positions(first_at, spacing, max_half_breadth) -> list[float]` (port to starboard)
  - the part types:
    - `Stiffener(y, z_bottom, z_top)` with `.length`
    - `Bracket(corners)` with `.area`
    - `Frame(number: int, x: float)`
    - `BulkheadParts(outline: tuple[Point, ...], stiffeners: tuple[Stiffener, ...], brackets: tuple[Bracket, ...], frames: tuple[Frame, ...], bulkhead_x: float, bracket_problems: tuple[str, ...])`
  - fixture: `example_parts`

- [ ] **Step 1: Write the failing tests**

Append to `tests/conftest.py`:

```python
@pytest.fixture
def example_parts(example_job):
    from shipdraw.structure import build_parts

    return build_parts(example_job)
```

`tests/test_structure.py`:

```python
import pytest

from shipdraw.job import Job
from shipdraw.structure import Frame, build_parts, stiffener_positions

EXAMPLE_YS = [-3900, -3300, -2700, -2100, -1500, -900, -300, 300, 900, 1500, 2100, 2700, 3300, 3900]


def test_stiffener_positions_mirror_about_centreline():
    assert stiffener_positions(300, 600, 4500) == EXAMPLE_YS
    assert stiffener_positions(0, 600, 1500) == [-1200, -600, 0, 600, 1200]


def test_example_stiffeners(example_parts):
    assert [s.y for s in example_parts.stiffeners] == EXAMPLE_YS
    by_y = {s.y: s for s in example_parts.stiffeners}
    assert (by_y[3900].z_bottom, by_y[3900].z_top) == pytest.approx((300, 3500))
    assert by_y[3900].length == pytest.approx(3200)
    assert (by_y[300].z_bottom, by_y[300].z_top) == pytest.approx((0, 3500))


def test_example_brackets(example_parts):
    assert len(example_parts.brackets) == 28
    assert example_parts.bracket_problems == ()
    assert sorted(round(b.area) for b in example_parts.brackets)[:2] == [22097, 22097]  # the two on the chamfer


def test_example_frames(example_parts):
    assert len(example_parts.frames) == 11
    assert example_parts.frames[0] == Frame(20, 12000)
    assert example_parts.frames[-1] == Frame(30, 18000)
    assert example_parts.bulkhead_x == 15000


def test_stiffener_on_centreline_appears_once(job_dict):
    job_dict["bulkhead"]["stiffeners"]["first_at"] = 0
    ys = [s.y for s in build_parts(Job.model_validate(job_dict)).stiffeners]
    assert len(ys) == 15 and ys.count(0) == 1


def test_bottom_brackets_only(job_dict):
    job_dict["bulkhead"]["brackets"]["top"] = False
    assert len(build_parts(Job.model_validate(job_dict)).brackets) == 14


def test_brackets_that_do_not_fit_are_reported_not_raised(job_dict):
    job_dict["bulkhead"]["brackets"]["size"] = 500
    parts = build_parts(Job.model_validate(job_dict))
    assert len(parts.brackets) == 26
    assert len(parts.bracket_problems) == 2
    assert "y=3900" in " ".join(parts.bracket_problems)
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `.venv/Scripts/python -m pytest tests/test_structure.py -v`
Expected: collection ERROR `No module named 'shipdraw.structure'`

- [ ] **Step 3: Implement `structure.py`**

`src/shipdraw/structure.py`:

```python
"""Ship-structure rules: turn a job into the parts to draw. No DXF here.

Bulkhead coordinates: y is transverse (+ to starboard), z is height above baseline.
Frame coordinates: x = frame number x frame spacing, FR0 at x = 0.
"""
from __future__ import annotations

from dataclasses import dataclass

from .geometry import (
    EPS,
    BracketFitError,
    Point,
    bounding_box,
    bracket_triangle,
    clip_vertical,
    mirror_half_outline,
    polygon_area,
)
from .job import Job


@dataclass(frozen=True)
class Stiffener:
    y: float
    z_bottom: float
    z_top: float

    @property
    def length(self) -> float:
        return self.z_top - self.z_bottom


@dataclass(frozen=True)
class Bracket:
    corners: tuple[Point, Point, Point]  # (y, z)

    @property
    def area(self) -> float:
        return abs(polygon_area(self.corners))


@dataclass(frozen=True)
class Frame:
    number: int
    x: float


@dataclass(frozen=True)
class BulkheadParts:
    outline: tuple[Point, ...]
    stiffeners: tuple[Stiffener, ...]
    brackets: tuple[Bracket, ...]
    frames: tuple[Frame, ...]
    bulkhead_x: float
    bracket_problems: tuple[str, ...] = ()


def stiffener_positions(first_at: float, spacing: float, max_half_breadth: float) -> list[float]:
    """y = first_at + k * spacing while inside the half breadth, mirrored to port."""
    starboard = []
    k = 0
    while (y := first_at + k * spacing) < max_half_breadth - EPS:
        starboard.append(y)
        k += 1
    port = [-y for y in reversed(starboard) if y > EPS]
    return port + starboard


def build_parts(job: Job) -> BulkheadParts:
    """Never raises for rule problems: checks.run_checks reports them."""
    bh = job.bulkhead
    outline = mirror_half_outline(bh.outline_half)
    max_half_breadth = bounding_box(outline)[2]

    stiffeners = [
        Stiffener(y, z_low, z_high)
        for y in stiffener_positions(bh.stiffeners.first_at, bh.stiffeners.spacing, max_half_breadth)
        for z_low, z_high in clip_vertical(outline, y)
    ]

    ends = []
    if bh.brackets.bottom:
        ends.append(("bottom", (0.0, 1.0)))
    if bh.brackets.top:
        ends.append(("top", (0.0, -1.0)))
    brackets, problems = [], []
    for st in stiffeners:
        for which, inward in ends:
            end = (st.y, st.z_bottom if which == "bottom" else st.z_top)
            try:
                brackets.append(Bracket(bracket_triangle(outline, end, inward, bh.brackets.size)))
            except BracketFitError as exc:
                problems.append(f"{which} bracket of the stiffener at y={st.y:g}: {exc}")

    frames = tuple(Frame(n, n * job.frames.spacing) for n in range(job.frames.first, job.frames.last + 1))
    return BulkheadParts(
        outline=tuple(outline),
        stiffeners=tuple(stiffeners),
        brackets=tuple(brackets),
        frames=frames,
        bulkhead_x=bh.at_frame * job.frames.spacing,
        bracket_problems=tuple(problems),
    )
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/Scripts/python -m pytest tests/test_structure.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/shipdraw/structure.py tests/conftest.py tests/test_structure.py
git commit -m "feat: structure rules for stiffener layout, brackets and frames" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Bill of materials

**Files:**
- Create: `src/shipdraw/bom.py`
- Test: `tests/test_bom.py`

**Interfaces:**
- Consumes: `Job`, `BulkheadParts`, `ProfileLibrary`, `STEEL_DENSITY_KG_M3`, `geometry.bounding_box`, `geometry.polygon_area`
- Produces:
  - `BomRow(item: int, description: str, qty: int, length_mm: float | None, weight_kg: float)`
  - `Bom(rows: tuple[BomRow, ...])` with `.total_weight_kg`
  - `build_bom(job, parts, profiles) -> Bom`
  - `bom_csv(bom) -> str`

- [ ] **Step 1: Write the failing tests**

`tests/test_bom.py`:

```python
import pytest

from shipdraw.bom import bom_csv, build_bom
from shipdraw.job import Job
from shipdraw.profiles import ProfileLibrary
from shipdraw.structure import build_parts

PLATE_KG = 30_690_000 * 8 * 7.85e-6  # outline area x thickness x density
BRACKET_KG = (26 * 31_250 + 2 * 31_250 * 2**-0.5) * 8 * 7.85e-6  # 26 right-angled + 2 on the chamfer


def test_example_bom(example_job, example_parts, verified_profiles):
    rows = build_bom(example_job, example_parts, verified_profiles).rows
    assert [r.item for r in rows] == [1, 2, 3, 4]
    assert (rows[0].description, rows[0].qty, rows[0].length_mm) == ("PL 8 AH36 (9000 x 3500)", 1, None)
    assert rows[0].weight_kg == pytest.approx(PLATE_KG)
    assert (rows[1].description, rows[1].qty, rows[1].length_mm) == ("HP 160x8", 12, 3500)
    assert rows[1].weight_kg == pytest.approx(12 * 3.5 * 12.4)
    assert (rows[2].description, rows[2].qty, rows[2].length_mm) == ("HP 160x8", 2, 3200)
    assert rows[2].weight_kg == pytest.approx(2 * 3.2 * 12.4)
    assert (rows[3].description, rows[3].qty, rows[3].length_mm) == ("BKT 250x250x8", 28, None)
    assert rows[3].weight_kg == pytest.approx(BRACKET_KG)


def test_total_weight(example_job, example_parts, verified_profiles):
    bom = build_bom(example_job, example_parts, verified_profiles)
    assert bom.total_weight_kg == pytest.approx(PLATE_KG + 12 * 3.5 * 12.4 + 2 * 3.2 * 12.4 + BRACKET_KG)


def bom_for(job_dict, profiles):
    job = Job.model_validate(job_dict)
    return build_bom(job, build_parts(job), profiles)


def test_flat_bar_stiffeners(job_dict):
    job_dict["bulkhead"]["stiffeners"]["profile"] = "FB 100x10"
    row = bom_for(job_dict, ProfileLibrary({})).rows[1]
    assert row.description == "FB 100x10"
    assert row.weight_kg == pytest.approx(12 * 3.5 * 7.85)


def test_angle_stiffeners_are_marked_approx(job_dict):
    job_dict["bulkhead"]["stiffeners"]["profile"] = "L 100x75x8"
    assert bom_for(job_dict, ProfileLibrary({})).rows[1].description == "L 100x75x8 (approx.)"


def test_no_bracket_row_without_brackets(job_dict, verified_profiles):
    job_dict["bulkhead"]["brackets"].update(top=False, bottom=False)
    assert [r.description for r in bom_for(job_dict, verified_profiles).rows][-1] == "HP 160x8"


def test_bom_csv(example_job, example_parts, verified_profiles):
    text = bom_csv(build_bom(example_job, example_parts, verified_profiles))
    lines = text.splitlines()
    assert lines[0] == "ITEM,DESCRIPTION,QTY,LENGTH_MM,WEIGHT_KG"
    assert lines[2] == "2,HP 160x8,12,3500,520.80"
    assert lines[-1].startswith(",TOTAL,,,")
    assert len(lines) == 6
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `.venv/Scripts/python -m pytest tests/test_bom.py -v`
Expected: collection ERROR `No module named 'shipdraw.bom'`

- [ ] **Step 3: Implement `bom.py`**

`src/shipdraw/bom.py`:

```python
"""Bill of materials from the drawn parts."""
from __future__ import annotations

import csv
import io
from collections import Counter
from dataclasses import dataclass

from .geometry import bounding_box, polygon_area
from .job import Job
from .profiles import STEEL_DENSITY_KG_M3, ProfileLibrary
from .structure import BulkheadParts

_KG_PER_MM3 = STEEL_DENSITY_KG_M3 * 1e-9


@dataclass(frozen=True)
class BomRow:
    item: int
    description: str
    qty: int
    length_mm: float | None  # length of one piece; None where it does not apply
    weight_kg: float  # all pieces in the row


@dataclass(frozen=True)
class Bom:
    rows: tuple[BomRow, ...]

    @property
    def total_weight_kg(self) -> float:
        return sum(row.weight_kg for row in self.rows)


def build_bom(job: Job, parts: BulkheadParts, profiles: ProfileLibrary) -> Bom:
    bh = job.bulkhead
    rows: list[tuple[str, int, float | None, float]] = []

    min_y, min_z, max_y, max_z = bounding_box(parts.outline)
    plate_kg = abs(polygon_area(parts.outline)) * bh.plate.thickness * _KG_PER_MM3
    rows.append(
        (f"PL {bh.plate.thickness:g} {bh.plate.grade} ({max_y - min_y:g} x {max_z - min_z:g})", 1, None, plate_kg)
    )

    weight = profiles.weight(bh.stiffeners.profile)
    description = bh.stiffeners.profile + (" (approx.)" if weight.approx else "")
    lengths = Counter(round(st.length) for st in parts.stiffeners)
    for length in sorted(lengths, reverse=True):
        qty = lengths[length]
        rows.append((description, qty, float(length), qty * length / 1000 * weight.kg_per_m))

    if parts.brackets:
        size, t = bh.brackets.size, bh.brackets.thickness
        bracket_kg = sum(b.area for b in parts.brackets) * t * _KG_PER_MM3
        rows.append((f"BKT {size:g}x{size:g}x{t:g}", len(parts.brackets), None, bracket_kg))

    return Bom(tuple(BomRow(i, *row) for i, row in enumerate(rows, start=1)))


def bom_csv(bom: Bom) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["ITEM", "DESCRIPTION", "QTY", "LENGTH_MM", "WEIGHT_KG"])
    for row in bom.rows:
        length = "" if row.length_mm is None else f"{row.length_mm:.0f}"
        writer.writerow([row.item, row.description, row.qty, length, f"{row.weight_kg:.2f}"])
    writer.writerow(["", "TOTAL", "", "", f"{bom.total_weight_kg:.2f}"])
    return buffer.getvalue()
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/Scripts/python -m pytest tests/test_bom.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/shipdraw/bom.py tests/test_bom.py
git commit -m "feat: bill of materials with plate, stiffener and bracket weights" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Sheet layout (scale selection and view placement)

**Files:**
- Create: `src/shipdraw/layout.py`
- Modify: `tests/conftest.py` (append the `example_plan` fixture)
- Test: `tests/test_layout.py`

**Interfaces:**
- Consumes: `BulkheadParts`, `Standard`, `Zone`, `geometry.bounding_box`
- Produces:
  - `plan_sheet(parts, standard) -> SheetPlan`, which raises `NoScaleFitsError(ValueError)`
  - `SheetPlan(scale: int, elevation_offset: (dx, dy), frames_offset: (dx, dy), bom_top_left: (x, y), title_block_origin: (x, y))`. All values are in model units. The offsets are added to view coordinates: (y, z) for the elevation, (x, 0) for the frame strip.
  - `Pad(left, right, bottom, top)`, plus the constants `ELEVATION_PAD` and `FRAMES_PAD` (paper mm reserved for annotations)
  - fixture: `example_plan`

- [ ] **Step 1: Write the failing tests**

Append to `tests/conftest.py`:

```python
@pytest.fixture
def example_plan(example_parts, standard):
    from shipdraw.layout import plan_sheet

    return plan_sheet(example_parts, standard)
```

`tests/test_layout.py`:

```python
import pytest

from shipdraw.geometry import bounding_box
from shipdraw.job import Job
from shipdraw.layout import ELEVATION_PAD, FRAMES_PAD, NoScaleFitsError, plan_sheet
from shipdraw.structure import build_parts


def parts_with_half_breadth(job_dict, half_breadth):
    job_dict["bulkhead"]["outline_half"] = [[0, 0], [half_breadth, 0], [half_breadth, 3500], [0, 3500]]
    return build_parts(Job.model_validate(job_dict))


def test_example_fits_at_1_to_20(example_plan):
    assert example_plan.scale == 20


def test_wider_bulkhead_drops_to_a_smaller_scale(job_dict, standard):
    assert plan_sheet(parts_with_half_breadth(job_dict, 12000), standard).scale == 50


def test_too_large_for_any_scale(job_dict, standard):
    with pytest.raises(NoScaleFitsError, match="does not fit the A1 sheet at any allowed scale"):
        plan_sheet(parts_with_half_breadth(job_dict, 40000), standard)


def test_elevation_is_centred_in_its_zone(example_plan, example_parts, standard):
    s, zone = example_plan.scale, standard.sheet.zones.elevation
    min_y, min_z, max_y, max_z = bounding_box(example_parts.outline)
    dx, dy = example_plan.elevation_offset
    left, right = min_y + dx - ELEVATION_PAD.left * s, max_y + dx + ELEVATION_PAD.right * s
    bottom, top = min_z + dy - ELEVATION_PAD.bottom * s, max_z + dy + ELEVATION_PAD.top * s
    assert (left + right) / 2 == pytest.approx((zone.x + zone.width / 2) * s)
    assert (bottom + top) / 2 == pytest.approx((zone.y + zone.height / 2) * s)


def test_frame_strip_is_centred_in_its_zone(example_plan, example_parts, standard):
    s, zone = example_plan.scale, standard.sheet.zones.frames
    dx, dy = example_plan.frames_offset
    left = example_parts.frames[0].x + dx - FRAMES_PAD.left * s
    right = example_parts.frames[-1].x + dx + FRAMES_PAD.right * s
    assert (left + right) / 2 == pytest.approx((zone.x + zone.width / 2) * s)
    assert (dy - FRAMES_PAD.bottom * s + dy + FRAMES_PAD.top * s) / 2 == pytest.approx((zone.y + zone.height / 2) * s)


def test_bom_and_title_block_positions(example_plan):
    assert example_plan.bom_top_left == (651 * 20, 584 * 20)
    assert example_plan.title_block_origin == ((841 - 10 - 180) * 20, 10 * 20)
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `.venv/Scripts/python -m pytest tests/test_layout.py -v`
Expected: collection ERROR `No module named 'shipdraw.layout'`

- [ ] **Step 3: Implement `layout.py`**

`src/shipdraw/layout.py`:

```python
"""Sheet layout: choose the drawing scale and place each view in its zone. No DXF here.

The sheet is drawn in model space at 1:1 mm with the border scaled up, so a paper
size of P mm becomes P * scale model units.
"""
from __future__ import annotations

from dataclasses import dataclass

from .geometry import bounding_box
from .standard import Standard, Zone
from .structure import BulkheadParts


@dataclass(frozen=True)
class Pad:
    """Paper mm reserved around a view's geometry for its annotations."""

    left: float
    right: float
    bottom: float
    top: float


# The render/ view modules draw their annotations inside these pads.
ELEVATION_PAD = Pad(left=25, right=80, bottom=45, top=15)
FRAMES_PAD = Pad(left=10, right=10, bottom=35, top=22)

Box = tuple[float, float, float, float]


class NoScaleFitsError(ValueError):
    """The views do not fit the sheet at any allowed scale. The message is user-facing."""


@dataclass(frozen=True)
class SheetPlan:
    scale: int
    elevation_offset: tuple[float, float]
    frames_offset: tuple[float, float]
    bom_top_left: tuple[float, float]
    title_block_origin: tuple[float, float]


def _fits(zone: Zone, box: Box, pad: Pad, scale: int) -> bool:
    width, height = box[2] - box[0], box[3] - box[1]
    return (
        width / scale + pad.left + pad.right <= zone.width + 1e-9
        and height / scale + pad.bottom + pad.top <= zone.height + 1e-9
    )


def _centring_offset(zone: Zone, box: Box, pad: Pad, scale: int) -> tuple[float, float]:
    """Offset that centres the box plus its pad inside the zone, in model units."""
    min_x, min_y, max_x, max_y = box
    content_w = (max_x - min_x) + (pad.left + pad.right) * scale
    content_h = (max_y - min_y) + (pad.bottom + pad.top) * scale
    left = zone.x * scale + (zone.width * scale - content_w) / 2
    bottom = zone.y * scale + (zone.height * scale - content_h) / 2
    return (left + pad.left * scale - min_x, bottom + pad.bottom * scale - min_y)


def plan_sheet(parts: BulkheadParts, standard: Standard) -> SheetPlan:
    sheet, zones = standard.sheet, standard.sheet.zones
    elevation_box = bounding_box(parts.outline)
    frames_box = (parts.frames[0].x, 0.0, parts.frames[-1].x, 0.0)
    views = [(zones.elevation, elevation_box, ELEVATION_PAD), (zones.frames, frames_box, FRAMES_PAD)]

    for scale in sorted(sheet.scales):
        if all(_fits(zone, box, pad, scale) for zone, box, pad in views):
            break
    else:
        allowed = ", ".join(f"1:{s}" for s in sorted(sheet.scales))
        raise NoScaleFitsError(f"the drawing does not fit the {sheet.name} sheet at any allowed scale ({allowed})")

    tb, bom = standard.title_block, zones.bom
    return SheetPlan(
        scale=scale,
        elevation_offset=_centring_offset(zones.elevation, elevation_box, ELEVATION_PAD, scale),
        frames_offset=_centring_offset(zones.frames, frames_box, FRAMES_PAD, scale),
        bom_top_left=(bom.x * scale, (bom.y + bom.height) * scale),
        title_block_origin=((sheet.width - sheet.margin - tb.width) * scale, sheet.margin * scale),
    )
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/Scripts/python -m pytest tests/test_layout.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/shipdraw/layout.py tests/conftest.py tests/test_layout.py
git commit -m "feat: sheet layout with automatic scale selection" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Rule checks

**Files:**
- Create: `src/shipdraw/checks.py`
- Test: `tests/test_checks.py`

**Interfaces:**
- Consumes: `Job`, `BulkheadParts`, `Standard`, `ProfileLibrary`, `UnknownProfileError`, `geometry.outline_problems`, `layout.plan_sheet`, `NoScaleFitsError`
- Produces:
  - `CheckReport(errors: tuple[str, ...], warnings: tuple[str, ...])` with `.ok`
  - `run_checks(job, parts, standard, profiles) -> CheckReport`

- [ ] **Step 1: Write the failing tests**

`tests/test_checks.py`:

```python
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
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `.venv/Scripts/python -m pytest tests/test_checks.py -v`
Expected: collection ERROR `No module named 'shipdraw.checks'`

- [ ] **Step 3: Implement `checks.py`**

`src/shipdraw/checks.py`:

```python
"""Deterministic rule checks, the rule-based reviewer. Errors block the drawing; warnings do not."""
from __future__ import annotations

from dataclasses import dataclass

from .geometry import outline_problems
from .job import Job
from .layout import NoScaleFitsError, plan_sheet
from .profiles import ProfileLibrary, UnknownProfileError
from .standard import Standard
from .structure import BulkheadParts


@dataclass(frozen=True)
class CheckReport:
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors


def run_checks(job: Job, parts: BulkheadParts, standard: Standard, profiles: ProfileLibrary) -> CheckReport:
    bh = job.bulkhead
    errors: list[str] = []
    warnings: list[str] = []

    shape_problems = outline_problems(list(parts.outline))
    errors += [f"bulkhead.outline_half: {problem}" for problem in shape_problems]

    if not job.frames.first <= bh.at_frame <= job.frames.last:
        errors.append(
            f"bulkhead.at_frame: FR{bh.at_frame} is outside the frame range "
            f"FR{job.frames.first}-FR{job.frames.last}"
        )

    if not parts.stiffeners:
        errors.append(
            "bulkhead.stiffeners: no stiffener position falls inside the outline (check first_at and spacing)"
        )

    ends = int(bh.brackets.top) + int(bh.brackets.bottom)
    if ends:
        too_short = [st for st in parts.stiffeners if bh.brackets.size >= st.length / ends]
        if too_short:
            shortest = min(too_short, key=lambda st: st.length)
            errors.append(
                f"bulkhead.brackets.size: {bh.brackets.size:g} mm brackets at {ends} end(s) are too large "
                f"for {len(too_short)} stiffener(s); the shortest is {shortest.length:.0f} mm at y={shortest.y:g}"
            )
    errors += [f"bulkhead.brackets: {problem}" for problem in parts.bracket_problems]

    try:
        weight = profiles.weight(bh.stiffeners.profile)
    except UnknownProfileError as exc:
        errors.append(f"bulkhead.stiffeners.profile: {exc}")
    else:
        if weight.placeholder:
            warnings.append(
                f"bulkhead.stiffeners.profile: the weight of {bh.stiffeners.profile} ({weight.kg_per_m:g} kg/m) "
                "is a placeholder in the profile library; BOM weights are estimates"
            )

    if not shape_problems:
        try:
            plan_sheet(parts, standard)
        except NoScaleFitsError as exc:
            errors.append(f"sheet: {exc}")

    limit = standard.rules.max_stiffener_spacing
    if bh.stiffeners.spacing > limit:
        warnings.append(
            f"bulkhead.stiffeners.spacing: {bh.stiffeners.spacing:g} mm is above the standard's maximum of {limit:g} mm"
        )

    return CheckReport(tuple(errors), tuple(warnings))
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/Scripts/python -m pytest tests/test_checks.py -v`
Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add src/shipdraw/checks.py tests/test_checks.py
git commit -m "feat: rule checks reporting errors and warnings" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: DXF sheet: document, layers, dimension style, border, title block

**Files:**
- Create: `src/shipdraw/render/__init__.py`, `src/shipdraw/render/sheet.py`
- Test: `tests/test_render_sheet.py`

**Interfaces:**
- Consumes: `Standard`, `LayerStyle`, `Job`, `SheetPlan`, `ConfigError`
- Produces:
  - `new_document(standard, scale) -> ezdxf Drawing`, which raises `ConfigError` for an unknown linetype
  - `DIMSTYLE = "SHIPDRAW"` and `TITLE_BLOCK = "SD_TITLE"`
  - `add_text(layout, text, point, height, layer, align=TextEntityAlignment.LEFT)`
  - `add_linear_dim(msp, p1, p2, base, angle, layer)`
  - `draw_border(msp, standard, scale)`
  - `draw_title_block(doc, job, standard, plan)`
  - `title_values(job, scale) -> dict[str, str]`

- [ ] **Step 1: Write the failing tests**

`tests/test_render_sheet.py`:

```python
import ezdxf
import pytest

from shipdraw.config import ConfigError
from shipdraw.render.sheet import (
    DIMSTYLE,
    TITLE_BLOCK,
    draw_border,
    draw_title_block,
    new_document,
    title_values,
)
from shipdraw.standard import LayerStyle


def test_document_has_every_standard_layer(standard):
    doc = new_document(standard, 20)
    for style in standard.layers.all():
        layer = doc.layers.get(style.name)
        assert layer.color == style.color
        assert layer.dxf.linetype.upper() == style.linetype.upper()
        assert layer.dxf.lineweight == style.lineweight


def test_document_scales_dimensions_and_linetypes(standard):
    doc = new_document(standard, 20)
    assert doc.dimstyles.get(DIMSTYLE).dxf.dimscale == 20
    assert doc.header["$LTSCALE"] == 20
    assert doc.header["$INSUNITS"] == 4  # millimetres


def test_unknown_linetype_is_a_config_error(standard):
    layers = standard.layers.model_copy(update={"frame": LayerStyle(name="FRAME", color=8, linetype="NOPE")})
    with pytest.raises(ConfigError, match="NOPE"):
        new_document(standard.model_copy(update={"layers": layers}), 20)


def test_border_is_sheet_size_times_scale(standard):
    doc = new_document(standard, 20)
    msp = doc.modelspace()
    draw_border(msp, standard, 20)
    borders = list(msp.query(f'LWPOLYLINE[layer=="{standard.layers.border.name}"]'))
    assert len(borders) == 2
    corners = [p for e in borders for p in e.get_points("xy")]
    assert max(x for x, _ in corners) == pytest.approx(841 * 20)
    assert max(y for _, y in corners) == pytest.approx(594 * 20)
    assert min(x for x, _ in corners) == pytest.approx(0)


def test_title_values(example_job):
    assert title_values(example_job, 20) == {
        "PROJECT": "OSV 60m",
        "DWG_NO": "SY-101",
        "TITLE": "TRANSVERSE BULKHEAD AT FR25",
        "SCALE": "1:20",
        "DRAWN": "AH",
        "DATE": "2026-09-28",
        "REV": "A",
    }


def test_title_block_attributes_survive_a_round_trip(standard, example_job, example_plan, tmp_path):
    doc = new_document(standard, example_plan.scale)
    draw_title_block(doc, example_job, standard, example_plan)
    doc.saveas(tmp_path / "tb.dxf")

    reread = ezdxf.readfile(tmp_path / "tb.dxf")
    assert not reread.audit().has_errors
    (ref,) = reread.modelspace().query("INSERT")
    assert ref.dxf.name == TITLE_BLOCK
    assert (ref.dxf.insert.x, ref.dxf.insert.y) == pytest.approx(example_plan.title_block_origin)
    assert ref.dxf.xscale == example_plan.scale
    assert {a.dxf.tag: a.dxf.text for a in ref.attribs} == title_values(example_job, example_plan.scale)
    assert {a.dxf.layer for a in ref.attribs} == {standard.layers.title.name}
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `.venv/Scripts/python -m pytest tests/test_render_sheet.py -v`
Expected: collection ERROR `No module named 'shipdraw.render'`

- [ ] **Step 3: Implement the sheet module**

`src/shipdraw/render/__init__.py`:

```python
"""DXF rendering. The only package allowed to import ezdxf."""
```

`src/shipdraw/render/sheet.py`:

```python
"""DXF document setup and sheet furniture: layers, dimension style, border, title block."""
from __future__ import annotations

from typing import TYPE_CHECKING

import ezdxf
from ezdxf import units
from ezdxf.enums import TextEntityAlignment

from ..config import ConfigError

if TYPE_CHECKING:
    from ezdxf.document import Drawing

    from ..job import Job
    from ..layout import SheetPlan
    from ..standard import Standard

DIMSTYLE = "SHIPDRAW"
TITLE_BLOCK = "SD_TITLE"
_FIELD_LABEL_HEIGHT = 1.8  # paper mm
_FIELD_LABEL_GAP = 1.5  # paper mm between a field's value and its caption


def new_document(standard: Standard, scale: int) -> Drawing:
    doc = ezdxf.new("R2018", setup=True, units=units.MM)
    doc.header["$MEASUREMENT"] = 1  # metric
    doc.header["$LTSCALE"] = float(scale)  # linetype patterns sized for the plotted sheet
    for style in standard.layers.all():
        if style.linetype not in doc.linetypes:
            raise ConfigError(f"layer {style.name}: linetype {style.linetype!r} is not available")
        doc.layers.add(style.name, color=style.color, linetype=style.linetype, lineweight=style.lineweight)
    dim = standard.dimension
    doc.dimstyles.new(
        DIMSTYLE,
        dxfattribs={
            "dimscale": scale,
            "dimtxt": dim.text_height,
            "dimasz": dim.arrow_size,
            "dimexe": dim.extension_beyond,
            "dimexo": dim.extension_offset,
            "dimgap": dim.text_gap,
            "dimdec": 0,
            "dimzin": 8,  # suppress trailing zeros
            "dimtad": 1,  # text above the dimension line
        },
    )
    return doc


def add_text(layout, text: str, point, height: float, layer: str, align=TextEntityAlignment.LEFT):
    return layout.add_text(text, height=height, dxfattribs={"layer": layer}).set_placement(point, align=align)


def add_linear_dim(msp, p1, p2, base, angle: float, layer: str) -> None:
    msp.add_linear_dim(
        base=base, p1=p1, p2=p2, angle=angle, dimstyle=DIMSTYLE, dxfattribs={"layer": layer}
    ).render()


def draw_border(msp, standard: Standard, scale: int) -> None:
    sheet = standard.sheet
    layer = {"layer": standard.layers.border.name}
    w, h, m = sheet.width * scale, sheet.height * scale, sheet.margin * scale
    msp.add_lwpolyline([(0, 0), (w, 0), (w, h), (0, h)], close=True, dxfattribs=layer)
    msp.add_lwpolyline([(m, m), (w - m, m), (w - m, h - m), (m, h - m)], close=True, dxfattribs=layer)


def title_values(job: Job, scale: int) -> dict[str, str]:
    p = job.project
    return {
        "PROJECT": p.name,
        "DWG_NO": p.drawing_no,
        "TITLE": p.title,
        "SCALE": f"1:{scale}",
        "DRAWN": p.drawn_by,
        "DATE": p.date.isoformat(),
        "REV": p.revision,
    }


def draw_title_block(doc: Drawing, job: Job, standard: Standard, plan: SheetPlan) -> None:
    """Title block defined in paper mm, inserted scaled; its fields are editable attributes."""
    tb = standard.title_block
    layer = standard.layers.title.name
    on_layer = {"layer": layer}
    block = doc.blocks.new(TITLE_BLOCK)
    block.add_lwpolyline([(0, 0), (tb.width, 0), (tb.width, tb.height), (0, tb.height)], close=True, dxfattribs=on_layer)
    for x1, y1, x2, y2 in tb.lines:
        block.add_line((x1, y1), (x2, y2), dxfattribs=on_layer)
    for field in tb.fields:
        add_text(block, field.label, (field.x, field.y + field.height + _FIELD_LABEL_GAP), _FIELD_LABEL_HEIGHT, layer)
        block.add_attdef(field.tag, insert=(field.x, field.y), height=field.height, dxfattribs={**on_layer, "prompt": field.label})

    ref = doc.modelspace().add_blockref(
        TITLE_BLOCK, plan.title_block_origin, dxfattribs={"layer": layer, "xscale": plan.scale, "yscale": plan.scale}
    )
    ref.add_auto_attribs(title_values(job, plan.scale))
    for attrib in ref.attribs:
        attrib.dxf.layer = layer
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/Scripts/python -m pytest tests/test_render_sheet.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add src/shipdraw/render/__init__.py src/shipdraw/render/sheet.py tests/test_render_sheet.py
git commit -m "feat: DXF document with standard layers, border and title block" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 10: Bulkhead elevation view

**Files:**
- Create: `src/shipdraw/render/bulkhead_view.py`
- Test: `tests/test_render_elevation.py`

**Interfaces:**
- Consumes: `add_text`, `add_linear_dim`, `new_document` (Task 9); `SheetPlan`; `BulkheadParts`; `geometry.bounding_box`, `geometry.clip_vertical`, `geometry.EPS`
- Produces: `draw_elevation(msp, job, parts, standard, plan) -> None`

- [ ] **Step 1: Write the failing tests**

`tests/test_render_elevation.py`:

```python
import pytest
from ezdxf import bbox

from shipdraw.render.bulkhead_view import draw_elevation
from shipdraw.render.sheet import new_document


@pytest.fixture
def elevation(standard, example_job, example_parts, example_plan):
    msp = new_document(standard, example_plan.scale).modelspace()
    draw_elevation(msp, example_job, example_parts, standard, example_plan)
    return msp


def on(msp, kind, layer):
    return list(msp.query(f'{kind}[layer=="{layer}"]'))


def test_plate_outline_is_the_offset_outline(elevation, standard, example_parts, example_plan):
    (plate,) = on(elevation, "LWPOLYLINE", standard.layers.plate.name)
    dx, dy = example_plan.elevation_offset
    assert plate.closed
    expected = [c for y, z in example_parts.outline for c in (y + dx, z + dy)]
    assert [c for p in plate.get_points("xy") for c in p] == pytest.approx(expected)


def test_stiffeners_and_brackets(elevation, standard, example_plan):
    dx, dy = example_plan.elevation_offset
    stiffeners = on(elevation, "LINE", standard.layers.stiffener.name)
    assert len(stiffeners) == 14
    (outer,) = [line for line in stiffeners if line.dxf.start.x == pytest.approx(3900 + dx)]
    assert (outer.dxf.start.y - dy, outer.dxf.end.y - dy) == pytest.approx((300, 3500))
    assert len(on(elevation, "LWPOLYLINE", standard.layers.bracket.name)) == 28


def test_centreline_and_baseline(elevation, standard):
    assert len(on(elevation, "LINE", standard.layers.centreline.name)) == 2


def test_labels_and_leaders(elevation, standard):
    texts = {t.dxf.text for t in on(elevation, "TEXT", standard.layers.text.name)}
    assert texts == {
        "CL",
        "BL",
        "PL 8 AH36",
        "HP 160x8 @ 600 TYP.",
        "BKT 250x250x8 TYP.",
        "BULKHEAD AT FR25 (LOOKING FWD)",
    }
    assert len(on(elevation, "LINE", standard.layers.text.name)) == 3


def test_dimensions(elevation, standard):
    dims = on(elevation, "DIMENSION", standard.layers.dim.name)
    # 15 spacing links (side, 14 stiffeners, side), overall breadth, overall height
    assert sorted(round(d.get_measurement()) for d in dims) == [600] * 15 + [3500, 9000]


def test_elevation_stays_inside_its_zone(elevation, standard, example_plan):
    box = bbox.extents(elevation)
    zone, s = standard.sheet.zones.elevation, example_plan.scale
    assert box.extmin.x >= zone.x * s and box.extmin.y >= zone.y * s
    assert box.extmax.x <= (zone.x + zone.width) * s and box.extmax.y <= (zone.y + zone.height) * s
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `.venv/Scripts/python -m pytest tests/test_render_elevation.py -v`
Expected: collection ERROR `No module named 'shipdraw.render.bulkhead_view'`

- [ ] **Step 3: Implement the elevation view**

`src/shipdraw/render/bulkhead_view.py`:

```python
"""Bulkhead elevation looking forward: plate, CL/BL, stiffeners, brackets, labels, dimensions."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ezdxf.enums import TextEntityAlignment

from ..geometry import EPS, Point, bounding_box, clip_vertical
from .sheet import add_linear_dim, add_text

if TYPE_CHECKING:
    from ..job import Job
    from ..layout import SheetPlan
    from ..standard import Standard
    from ..structure import Bracket, BulkheadParts

# Paper-mm distances. Keep them inside layout.ELEVATION_PAD (left 25, right 80, bottom 45, top 15).
LINE_OVERRUN = 5  # CL and BL run this far past the plate
CHAIN_DIM = 12  # stiffener spacing chain, below the lowest point
OVERALL_DIM = 24  # overall breadth, below the chain
TITLE_GAP = 36  # top of the view title, below the lowest point
HEIGHT_DIM = 18  # overall height, left of the plate
LABEL_GAP = 15  # labels start this far right of the plate


def _centroid(bracket: Bracket) -> Point:
    return (sum(c[0] for c in bracket.corners) / 3, sum(c[1] for c in bracket.corners) / 3)


def draw_elevation(msp, job: Job, parts: BulkheadParts, standard: Standard, plan: SheetPlan) -> None:
    s = plan.scale
    dx, dy = plan.elevation_offset
    layers = standard.layers
    bh = job.bulkhead
    outline = list(parts.outline)
    min_y, min_z, max_y, max_z = bounding_box(outline)
    text_h = standard.text.label * s

    def at(y: float, z: float) -> Point:
        return (y + dx, z + dy)

    # Plate, centreline, baseline
    msp.add_lwpolyline([at(*p) for p in outline], close=True, dxfattribs={"layer": layers.plate.name})
    run = LINE_OVERRUN * s
    msp.add_line(at(0, min_z - run), at(0, max_z + run), dxfattribs={"layer": layers.centreline.name})
    msp.add_line(at(min_y - run, 0), at(max_y + run, 0), dxfattribs={"layer": layers.centreline.name})
    add_text(msp, "CL", at(0, max_z + run + s), text_h, layers.text.name, TextEntityAlignment.BOTTOM_CENTER)
    add_text(msp, "BL", at(min_y - run - s, 0), text_h, layers.text.name, TextEntityAlignment.MIDDLE_RIGHT)

    # Stiffeners and brackets
    for st in parts.stiffeners:
        msp.add_line(at(st.y, st.z_bottom), at(st.y, st.z_top), dxfattribs={"layer": layers.stiffener.name})
    for bracket in parts.brackets:
        msp.add_lwpolyline([at(*c) for c in bracket.corners], close=True, dxfattribs={"layer": layers.bracket.name})

    # Labels on the right, each with a straight leader to a typical item
    height = max_z - min_z
    labels: list[tuple[str, Point, float]] = []  # (text, target point, label z)
    ys = sorted({st.y for st in parts.stiffeners})
    panel_y = (ys[-1] + max_y) / 2 if ys else (min_y + max_y) / 2
    spans = clip_vertical(outline, panel_y)
    if spans:
        labels.append((f"PL {bh.plate.thickness:g} {bh.plate.grade}", (panel_y, sum(spans[0]) / 2), min_z + 0.8 * height))
    if parts.stiffeners:
        outer = max(parts.stiffeners, key=lambda st: (st.y, -st.z_bottom))
        target = (outer.y, (outer.z_bottom + outer.z_top) / 2)
        labels.append((f"{bh.stiffeners.profile} @ {bh.stiffeners.spacing:g} TYP.", target, min_z + 0.5 * height))
    if parts.brackets:
        typical = max(parts.brackets, key=lambda b: (_centroid(b)[0], -_centroid(b)[1]))
        size, t = bh.brackets.size, bh.brackets.thickness
        labels.append((f"BKT {size:g}x{size:g}x{t:g} TYP.", _centroid(typical), min_z + 0.2 * height))
    label_y = max_y + LABEL_GAP * s
    for text, target, label_z in labels:
        add_text(msp, text, at(label_y, label_z), text_h, layers.text.name, TextEntityAlignment.MIDDLE_LEFT)
        msp.add_line(at(label_y - s, label_z), at(*target), dxfattribs={"layer": layers.text.name})

    # Dimensions: spacing chain side-to-side through every stiffener, overall breadth, overall height
    lowest_end: dict[float, float] = {}
    for st in parts.stiffeners:
        lowest_end[st.y] = min(lowest_end.get(st.y, st.z_bottom), st.z_bottom)
    left_z = min(z for y, z in outline if abs(y - min_y) <= EPS)
    right_z = min(z for y, z in outline if abs(y - max_y) <= EPS)
    chain = [(min_y, left_z), *sorted(lowest_end.items()), (max_y, right_z)]
    dim_layer = layers.dim.name
    for p1, p2 in zip(chain, chain[1:]):
        add_linear_dim(msp, at(*p1), at(*p2), at(p1[0], min_z - CHAIN_DIM * s), 0, dim_layer)
    add_linear_dim(msp, at(*chain[0]), at(*chain[-1]), at(chain[0][0], min_z - OVERALL_DIM * s), 0, dim_layer)
    lowest = min(outline, key=lambda p: (p[1], p[0]))
    highest = max(outline, key=lambda p: (p[1], -p[0]))
    add_linear_dim(msp, at(*lowest), at(*highest), at(min_y - HEIGHT_DIM * s, lowest[1]), 90, dim_layer)

    add_text(
        msp,
        f"BULKHEAD AT FR{bh.at_frame} (LOOKING FWD)",
        at((min_y + max_y) / 2, min_z - TITLE_GAP * s),
        standard.text.view_title * s,
        layers.text.name,
        TextEntityAlignment.TOP_CENTER,
    )
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/Scripts/python -m pytest tests/test_render_elevation.py -v`
Expected: 6 passed. If `test_elevation_stays_inside_its_zone` fails, increase the matching `ELEVATION_PAD` side in `layout.py` (and re-run `tests/test_layout.py`). Never shrink the zone test.

- [ ] **Step 5: Commit**

```bash
git add src/shipdraw/render/bulkhead_view.py tests/test_render_elevation.py
git commit -m "feat: bulkhead elevation view with labels and dimensions" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 11: Frame layout strip

**Files:**
- Create: `src/shipdraw/render/frame_view.py`
- Test: `tests/test_render_frames.py`

**Interfaces:**
- Consumes: `add_text`, `add_linear_dim`, `new_document`; `SheetPlan`; `BulkheadParts`
- Produces: `draw_frame_strip(msp, job, parts, standard, plan) -> None`

- [ ] **Step 1: Write the failing tests**

`tests/test_render_frames.py`:

```python
import pytest
from ezdxf import bbox

from shipdraw.render.frame_view import draw_frame_strip
from shipdraw.render.sheet import new_document


@pytest.fixture
def strip(standard, example_job, example_parts, example_plan):
    msp = new_document(standard, example_plan.scale).modelspace()
    draw_frame_strip(msp, example_job, example_parts, standard, example_plan)
    return msp


def on(msp, kind, layer):
    return list(msp.query(f'{kind}[layer=="{layer}"]'))


def test_frame_ticks_and_baseline(strip, standard, example_plan):
    lines = on(strip, "LINE", standard.layers.frame.name)
    assert len(lines) == 12  # 11 ticks + baseline
    dx = example_plan.frames_offset[0]
    ticks = sorted(round(line.dxf.start.x - dx) for line in lines if line.dxf.start.x == line.dxf.end.x)
    assert ticks == [n * 600 for n in range(20, 31)]


def test_bulkhead_frame_is_marked(strip, standard, example_plan):
    (mark,) = on(strip, "LINE", standard.layers.plate.name)
    assert mark.dxf.start.x == pytest.approx(25 * 600 + example_plan.frames_offset[0])


def test_frame_labels(strip, standard):
    texts = {t.dxf.text for t in on(strip, "TEXT", standard.layers.text.name)}
    assert {f"FR{n}" for n in range(20, 31)} <= texts
    assert {"BHD", "FRAME LAYOUT FR20-FR30"} <= texts


def test_frame_spacing_dimensions(strip, standard):
    dims = on(strip, "DIMENSION", standard.layers.dim.name)
    assert [round(d.get_measurement()) for d in dims] == [600] * 10


def test_frame_strip_stays_inside_its_zone(strip, standard, example_plan):
    box = bbox.extents(strip)
    zone, s = standard.sheet.zones.frames, example_plan.scale
    assert box.extmin.x >= zone.x * s and box.extmin.y >= zone.y * s
    assert box.extmax.x <= (zone.x + zone.width) * s and box.extmax.y <= (zone.y + zone.height) * s
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `.venv/Scripts/python -m pytest tests/test_render_frames.py -v`
Expected: collection ERROR `No module named 'shipdraw.render.frame_view'`

- [ ] **Step 3: Implement the frame strip**

`src/shipdraw/render/frame_view.py`:

```python
"""Frame layout strip: frame ticks and numbers, spacing chain, bulkhead position."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ezdxf.enums import TextEntityAlignment

from ..geometry import Point
from .sheet import add_linear_dim, add_text

if TYPE_CHECKING:
    from ..job import Job
    from ..layout import SheetPlan
    from ..standard import Standard
    from ..structure import BulkheadParts

# Paper-mm distances. Keep them inside layout.FRAMES_PAD (bottom 35, top 22).
TICK = 8  # frame tick height above the strip baseline
LABEL_GAP = 2  # between a tick and its frame number, and between rows of text
CHAIN_DIM = 10  # spacing chain, below the strip
TITLE_GAP = 22  # top of the view title, below the strip


def draw_frame_strip(msp, job: Job, parts: BulkheadParts, standard: Standard, plan: SheetPlan) -> None:
    s = plan.scale
    dx, dy = plan.frames_offset
    layers = standard.layers
    first, last = parts.frames[0], parts.frames[-1]
    tick = TICK * s
    number_h = standard.text.frame_number * s

    def at(x: float, y: float = 0.0) -> Point:
        return (x + dx, y + dy)

    msp.add_line(at(first.x), at(last.x), dxfattribs={"layer": layers.frame.name})
    for frame in parts.frames:
        msp.add_line(at(frame.x), at(frame.x, tick), dxfattribs={"layer": layers.frame.name})
        add_text(
            msp, f"FR{frame.number}", at(frame.x, tick + LABEL_GAP * s), number_h, layers.text.name,
            TextEntityAlignment.BOTTOM_CENTER,
        )

    msp.add_line(at(parts.bulkhead_x), at(parts.bulkhead_x, tick), dxfattribs={"layer": layers.plate.name})
    add_text(
        msp, "BHD", at(parts.bulkhead_x, tick + 2 * LABEL_GAP * s + number_h), number_h, layers.text.name,
        TextEntityAlignment.BOTTOM_CENTER,
    )

    for a, b in zip(parts.frames, parts.frames[1:]):
        add_linear_dim(msp, at(a.x), at(b.x), at(a.x, -CHAIN_DIM * s), 0, layers.dim.name)

    add_text(
        msp,
        f"FRAME LAYOUT FR{first.number}-FR{last.number}",
        at((first.x + last.x) / 2, -TITLE_GAP * s),
        standard.text.view_title * s,
        layers.text.name,
        TextEntityAlignment.TOP_CENTER,
    )
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/Scripts/python -m pytest tests/test_render_frames.py -v`
Expected: 5 passed. If the zone test fails, widen `FRAMES_PAD` in `layout.py`.

- [ ] **Step 5: Commit**

```bash
git add src/shipdraw/render/frame_view.py tests/test_render_frames.py
git commit -m "feat: frame layout strip with bulkhead position" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 12: BOM table on the sheet

**Files:**
- Create: `src/shipdraw/render/bom_table.py`
- Test: `tests/test_render_bom_table.py`

**Interfaces:**
- Consumes: `add_text`, `new_document`; `Bom`, `BomRow`; `SheetPlan`
- Produces:
  - `COLUMNS: tuple[tuple[str, float], ...]` (header text, width in paper mm)
  - `bom_cells(bom) -> list[tuple[str, ...]]` (header row, one row per BOM row, then the TOTAL row)
  - `draw_bom_table(msp, bom, standard, plan) -> None`

- [ ] **Step 1: Write the failing tests**

`tests/test_render_bom_table.py`:

```python
from ezdxf import bbox

from shipdraw.bom import Bom, BomRow
from shipdraw.render.bom_table import COLUMNS, bom_cells, draw_bom_table
from shipdraw.render.sheet import new_document

BOM = Bom(
    (
        BomRow(1, "PL 8 AH36 (9000 x 3500)", 1, None, 1927.332),
        BomRow(2, "HP 160x8", 12, 3500.0, 520.8),
        BomRow(3, "HP 160x8", 2, 3200.0, 79.36),
        BomRow(4, "BKT 250x250x8", 28, None, 53.8004),
    )
)


def test_bom_cells():
    cells = bom_cells(BOM)
    assert cells[0] == ("ITEM", "DESCRIPTION", "QTY", "LENGTH (mm)", "WEIGHT (kg)")
    assert cells[1] == ("1", "PL 8 AH36 (9000 x 3500)", "1", "-", "1927.3")
    assert cells[2] == ("2", "HP 160x8", "12", "3500", "520.8")
    assert cells[-1] == ("", "TOTAL", "", "", "2581.3")
    assert len(cells) == 6


def test_table_grid_and_text(standard, example_plan):
    msp = new_document(standard, example_plan.scale).modelspace()
    draw_bom_table(msp, BOM, standard, example_plan)
    layer = standard.layers.bom.name
    assert len(msp.query(f'LINE[layer=="{layer}"]')) == (6 + 1) + (len(COLUMNS) + 1)
    texts = [t.dxf.text for t in msp.query(f'TEXT[layer=="{layer}"]')]
    assert {"BILL OF MATERIALS", "TOTAL", "2581.3", "PL 8 AH36 (9000 x 3500)"} <= set(texts)
    assert all(e.dxf.layer == layer for e in msp)


def test_table_stays_inside_the_bom_zone(standard, example_plan):
    msp = new_document(standard, example_plan.scale).modelspace()
    draw_bom_table(msp, BOM, standard, example_plan)
    box = bbox.extents(msp)
    zone, s = standard.sheet.zones.bom, example_plan.scale
    assert box.extmin.x >= zone.x * s and box.extmin.y >= zone.y * s
    assert box.extmax.x <= (zone.x + zone.width) * s and box.extmax.y <= (zone.y + zone.height) * s
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `.venv/Scripts/python -m pytest tests/test_render_bom_table.py -v`
Expected: collection ERROR `No module named 'shipdraw.render.bom_table'`

- [ ] **Step 3: Implement the table**

`src/shipdraw/render/bom_table.py`:

```python
"""Bill of materials drawn as a table in the BOM zone."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ezdxf.enums import TextEntityAlignment

from .sheet import add_text

if TYPE_CHECKING:
    from ..bom import Bom
    from ..layout import SheetPlan
    from ..standard import Standard

# (header, width in paper mm)
COLUMNS: tuple[tuple[str, float], ...] = (
    ("ITEM", 12),
    ("DESCRIPTION", 80),
    ("QTY", 14),
    ("LENGTH (mm)", 30),
    ("WEIGHT (kg)", 30),
)
_RIGHT_ALIGNED = {0, 2, 3, 4}  # numeric columns (body rows only)
ROW_HEIGHT = 7.0  # paper mm
CELL_PAD = 1.5  # paper mm
CAPTION_SPACE = 9.0  # paper mm from the zone top to the table top


def bom_cells(bom: Bom) -> list[tuple[str, ...]]:
    cells = [tuple(header for header, _ in COLUMNS)]
    for row in bom.rows:
        length = "-" if row.length_mm is None else f"{row.length_mm:.0f}"
        cells.append((str(row.item), row.description, str(row.qty), length, f"{row.weight_kg:.1f}"))
    cells.append(("", "TOTAL", "", "", f"{bom.total_weight_kg:.1f}"))
    return cells


def draw_bom_table(msp, bom: Bom, standard: Standard, plan: SheetPlan) -> None:
    s = plan.scale
    layer = standard.layers.bom.name
    x0, zone_top = plan.bom_top_left
    add_text(msp, "BILL OF MATERIALS", (x0, zone_top - s), standard.text.view_title * s, layer, TextEntityAlignment.TOP_LEFT)

    cells = bom_cells(bom)
    row_h = ROW_HEIGHT * s
    table_top = zone_top - CAPTION_SPACE * s
    table_bottom = table_top - len(cells) * row_h
    xs = [x0]
    for _, width in COLUMNS:
        xs.append(xs[-1] + width * s)

    for i in range(len(cells) + 1):
        y = table_top - i * row_h
        msp.add_line((xs[0], y), (xs[-1], y), dxfattribs={"layer": layer})
    for x in xs:
        msp.add_line((x, table_top), (x, table_bottom), dxfattribs={"layer": layer})

    text_h, pad = standard.text.bom * s, CELL_PAD * s
    for i, row in enumerate(cells):
        y = table_top - (i + 0.5) * row_h
        for j, value in enumerate(row):
            if not value:
                continue
            if i > 0 and j in _RIGHT_ALIGNED:
                add_text(msp, value, (xs[j + 1] - pad, y), text_h, layer, TextEntityAlignment.MIDDLE_RIGHT)
            else:
                add_text(msp, value, (xs[j] + pad, y), text_h, layer, TextEntityAlignment.MIDDLE_LEFT)
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/Scripts/python -m pytest tests/test_render_bom_table.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/shipdraw/render/bom_table.py tests/test_render_bom_table.py
git commit -m "feat: BOM table on the drawing sheet" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 13: Build pipeline, preview and report

**Files:**
- Create: `src/shipdraw/render/preview.py`, `src/shipdraw/pipeline.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: every earlier module
- Produces:
  - `build(job, standard, profiles, out_dir, *, preview=True) -> BuildResult`
  - `BuildResult(job, report, scale, stiffener_count, bracket_count, total_weight_kg, seconds, files)` with `.ok`
  - `format_summary(result) -> str`
  - `render_png(doc, path, sheet_width_mm, sheet_height_mm, dpi=150)`
  - Output files in `out_dir`: `<dwg>.dxf`, `<dwg>-bom.csv`, `<dwg>.png` (when `preview` is set) and `<dwg>-report.txt`, each written atomically. Nothing is written when there are rule errors.

- [ ] **Step 1: Write the failing tests**

`tests/test_pipeline.py`:

```python
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
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `.venv/Scripts/python -m pytest tests/test_pipeline.py -v`
Expected: collection ERROR `No module named 'shipdraw.pipeline'`

- [ ] **Step 3: Implement the preview**

`src/shipdraw/render/preview.py`:

```python
"""PNG preview of a drawing, black on white like a plot."""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ezdxf.addons.drawing import matplotlib as mpl_draw
from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration

if TYPE_CHECKING:
    from ezdxf.document import Drawing

_PLOT_STYLE = Configuration(color_policy=ColorPolicy.BLACK, background_policy=BackgroundPolicy.WHITE)
_MM_PER_INCH = 25.4


def render_png(doc: Drawing, path: Path, sheet_width_mm: float, sheet_height_mm: float, dpi: int = 150) -> None:
    # Below ~150 dpi the rasteriser drops strokes from the 1.8 mm title-block captions.
    mpl_draw.qsave(
        doc.modelspace(),
        path,
        bg="#FFFFFF",
        config=_PLOT_STYLE,
        dpi=dpi,
        size_inches=(sheet_width_mm / _MM_PER_INCH, sheet_height_mm / _MM_PER_INCH),
    )
```

- [ ] **Step 4: Implement the pipeline**

`src/shipdraw/pipeline.py`:

```python
"""The build pipeline: job → checks → drawing files.

Called by the CLI now and by the MCP server (build #2) later.
"""
from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from .bom import bom_csv, build_bom
from .checks import CheckReport, run_checks
from .job import Job
from .layout import plan_sheet
from .profiles import ProfileLibrary
from .render.bom_table import draw_bom_table
from .render.bulkhead_view import draw_elevation
from .render.frame_view import draw_frame_strip
from .render.preview import render_png
from .render.sheet import draw_border, draw_title_block, new_document
from .standard import Standard
from .structure import build_parts


@dataclass(frozen=True)
class BuildResult:
    job: Job
    report: CheckReport
    scale: int | None
    stiffener_count: int
    bracket_count: int
    total_weight_kg: float | None
    seconds: float
    files: tuple[Path, ...] = ()

    @property
    def ok(self) -> bool:
        return self.report.ok


def build(
    job: Job, standard: Standard, profiles: ProfileLibrary, out_dir: Path, *, preview: bool = True
) -> BuildResult:
    started = time.perf_counter()
    parts = build_parts(job)
    report = run_checks(job, parts, standard, profiles)
    if not report.ok:
        return BuildResult(
            job, report, None, len(parts.stiffeners), len(parts.brackets), None, time.perf_counter() - started
        )

    plan = plan_sheet(parts, standard)
    bom = build_bom(job, parts, profiles)
    doc = new_document(standard, plan.scale)
    msp = doc.modelspace()
    draw_border(msp, standard, plan.scale)
    draw_title_block(doc, job, standard, plan)
    draw_elevation(msp, job, parts, standard, plan)
    draw_frame_strip(msp, job, parts, standard, plan)
    draw_bom_table(msp, bom, standard, plan)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = job.project.drawing_no
    files = [
        _write_atomic(out_dir / f"{stem}.dxf", doc.saveas),
        _write_atomic(
            out_dir / f"{stem}-bom.csv", lambda p: p.write_text(bom_csv(bom), encoding="utf-8", newline="")
        ),
    ]
    if preview:
        files.append(
            _write_atomic(
                out_dir / f"{stem}.png",
                lambda p: render_png(doc, p, standard.sheet.width, standard.sheet.height),
            )
        )

    result = BuildResult(
        job,
        report,
        plan.scale,
        len(parts.stiffeners),
        len(parts.brackets),
        bom.total_weight_kg,
        time.perf_counter() - started,
        tuple(files),
    )
    summary = format_summary(result)
    report_path = _write_atomic(
        out_dir / f"{stem}-report.txt", lambda p: p.write_text(summary + "\n", encoding="utf-8")
    )
    return replace(result, files=result.files + (report_path,))


def _write_atomic(path: Path, write: Callable[[Path], object]) -> Path:
    """Write to a temporary sibling, then move it into place, so no half-written file is left."""
    tmp = path.with_name(f"{path.stem}.tmp{path.suffix}")
    try:
        write(tmp)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


def format_summary(result: BuildResult) -> str:
    project = result.job.project
    report = result.report
    lines = [
        f"shipdraw: {project.drawing_no} {project.title}",
        f"Result: {'OK' if result.ok else 'FAILED'} "
        f"({len(report.errors)} error(s), {len(report.warnings)} warning(s))",
    ]
    if result.ok:
        lines += [
            f"Scale: 1:{result.scale}",
            f"Stiffeners: {result.stiffener_count}   Brackets: {result.bracket_count}",
            f"Total weight: {result.total_weight_kg:.1f} kg",
        ]
    lines.append(f"Time: {result.seconds:.2f} s")
    for heading, items in (("Errors", report.errors), ("Warnings", report.warnings)):
        if items:
            lines.append(f"{heading}:")
            lines += [f"  - {item}" for item in items]
    if result.files:
        lines.append("Files:")
        lines += [f"  {path}" for path in result.files]
    return "\n".join(lines)
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `.venv/Scripts/python -m pytest tests/test_pipeline.py -v`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add src/shipdraw/render/preview.py src/shipdraw/pipeline.py tests/test_pipeline.py
git commit -m "feat: build pipeline writing DXF, BOM CSV, preview and report" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 14: Command line, README and visual check

**Files:**
- Create: `src/shipdraw/cli.py`, `README.md`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `load_job`, `load_standard`, `ProfileLibrary.load`, `build`, `format_summary`, `ConfigError`, `CONFIG_DIR`
- Produces: `main(argv: list[str] | None = None) -> int`, installed as the `shipdraw` command. Exit codes: 0 = OK, 1 = rule errors, 2 = bad input or usage.

- [ ] **Step 1: Write the failing tests**

`tests/test_cli.py`:

```python
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
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `.venv/Scripts/python -m pytest tests/test_cli.py -v`
Expected: collection ERROR `No module named 'shipdraw.cli'`

- [ ] **Step 3: Implement the CLI**

`src/shipdraw/cli.py`:

```python
"""Command line: shipdraw build <job.yaml>."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import CONFIG_DIR, ConfigError
from .job import load_job
from .pipeline import build, format_summary
from .profiles import ProfileLibrary
from .standard import load_standard


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="shipdraw", description="Generate ship structural drawings (DXF) from job files.")
    commands = parser.add_subparsers(dest="command", required=True)
    build_cmd = commands.add_parser("build", help="build one drawing from a job file")
    build_cmd.add_argument("job", type=Path, help="job file (YAML)")
    build_cmd.add_argument("-o", "--out", type=Path, default=Path("out"), help="output folder (default: out)")
    build_cmd.add_argument("--config", type=Path, default=CONFIG_DIR, help="folder with standard.yaml and profiles.yaml")
    build_cmd.add_argument("--no-preview", action="store_true", help="skip the PNG preview")
    args = parser.parse_args(argv)

    try:
        job = load_job(args.job)
        standard = load_standard(args.config / "standard.yaml")
        profiles = ProfileLibrary.load(args.config / "profiles.yaml")
        result = build(job, standard, profiles, args.out, preview=not args.no_preview)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(format_summary(result))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `.venv/Scripts/python -m pytest tests/test_cli.py -v`
Expected: 4 passed

- [ ] **Step 5: Write the README**

`README.md`:

````markdown
# shipdraw: bulkhead drawing engine (v1)

Generates a complete transverse-bulkhead drawing for AutoCAD from a small job file:
plate outline, stiffeners, brackets, frame layout, dimensions, BOM and title block,
with every entity on the company's layers.

## Setup (once)

```bash
py -3.13 -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"
```

## Make a drawing

```bash
.venv/Scripts/shipdraw build jobs/bhd-fr25.yaml
```

This writes to `out/`:

| File | What it is |
|---|---|
| `SY-101.dxf` | the drawing; open it in AutoCAD |
| `SY-101.png` | preview image |
| `SY-101-bom.csv` | bill of materials for Excel |
| `SY-101-report.txt` | rule-check results |

To make a new drawing, copy `jobs/bhd-fr25.yaml`, change the values and run the same command on your copy.

Exit codes: `0` = drawing written, `1` = rule errors (nothing written; see the report on screen), `2` = the job or config file is invalid.

## Company standard

- `config/standard.yaml` holds the sheet, layers, text sizes, dimension style, title block and rule limits. **All values are placeholders** until the client's standard is supplied. Change them there; no code changes are needed.
- `config/profiles.yaml` holds the HP bulb-flat weights. **These are placeholder estimates** (the report warns while they are in use). Replace them with the supplier's table.

## Tests

```bash
.venv/Scripts/python -m pytest
```
````

- [ ] **Step 6: Run the full suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all tests pass (109 in total)

- [ ] **Step 7: Build the example for real and inspect the preview**

Run: `.venv/Scripts/shipdraw build jobs/bhd-fr25.yaml`
Expected: exit code 0; the summary shows `Result: OK (0 error(s), 1 warning(s))`, `Scale: 1:20`, `Stiffeners: 14   Brackets: 28`, and the HP placeholder warning.

Open `out/SY-101.png` with the Read tool and check it visually:

- border and title block, with all 7 fields filled;
- the elevation, showing the chamfered outline, 14 stiffeners, brackets, CL/BL, three labels with leaders, the dimension chains and the view title;
- the frame strip FR20–FR30, with BHD at FR25;
- the BOM table, with 4 rows and a total;
- no overlapping text.

If anything overlaps, adjust the paper-mm constants in the view module and the matching pad in `layout.py`, then re-run the full suite. Record what you saw in the task report.

- [ ] **Step 8: Commit**

```bash
git add src/shipdraw/cli.py tests/test_cli.py README.md
git commit -m "feat: shipdraw command line and README" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 9: Hand over for the AutoCAD acceptance check (manual, by the user)**

Tell the user v1 is "verified in ezdxf, pending AutoCAD check", and ask them to open `out/SY-101.dxf` in AutoCAD and confirm that:

1. it opens with no errors or recovery prompt;
2. the layers match `config/standard.yaml`;
3. the dimensions are editable;
4. the title block edits with `ATTEDIT`.
