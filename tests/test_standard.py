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
