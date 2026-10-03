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

    def hp_names(self) -> list[str]:
        return sorted(self._hp, key=lambda name: parse_profile(name).dims)

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
