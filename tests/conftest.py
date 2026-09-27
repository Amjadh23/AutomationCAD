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


@pytest.fixture
def verified_profiles():
    """Library with one verified (non-placeholder) HP entry, independent of config/."""
    from shipdraw.profiles import ProfileLibrary, ProfileWeight

    return ProfileLibrary({"HP 160x8": ProfileWeight(12.4)})


@pytest.fixture
def shipped_profiles():
    from shipdraw.profiles import ProfileLibrary

    return ProfileLibrary.load(CONFIG_DIR / "profiles.yaml")
