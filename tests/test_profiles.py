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


def test_hp_names_are_sorted_by_size(shipped_profiles):
    assert shipped_profiles.hp_names() == ["HP 120x7", "HP 140x7", "HP 160x8", "HP 180x9", "HP 200x10"]
