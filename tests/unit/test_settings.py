from pathlib import Path

import pytest

from integrated_script.config.exceptions import ConfigurationError
from integrated_script.config.settings import ConfigManager
from integrated_script.version import get_version


def test_creates_default_config_file_when_missing(tmp_path: Path) -> None:
    config_file = tmp_path / "config.json"
    assert not config_file.exists()

    manager = ConfigManager(config_file=config_file, auto_save=False)

    assert config_file.exists()
    assert manager.get("version") == get_version()
    assert "temp_dir" not in manager.get("paths")


def test_default_config_path_is_in_config_directory(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    manager = ConfigManager(auto_save=False, load_on_init=False)

    assert manager.config_file == tmp_path / "config" / "config.json"
    assert manager.config_file.parent.is_dir()
    assert not manager.config_file.exists()

    manager.save()

    assert manager.config_file.is_file()
    assert not (tmp_path / "config.json").exists()


@pytest.mark.parametrize("new_config_exists", [False, True])
def test_default_config_ignores_old_root_file(
    monkeypatch, tmp_path: Path, new_config_exists: bool
) -> None:
    monkeypatch.chdir(tmp_path)
    old_file = tmp_path / "config.json"
    old_content = '{"ui": {"theme": "old"}}'
    old_file.write_text(old_content, encoding="utf-8")
    if new_config_exists:
        new_file = tmp_path / "config" / "config.json"
        new_file.parent.mkdir()
        new_file.write_text('{"ui": {"theme": "new"}}', encoding="utf-8")

    manager = ConfigManager(auto_save=False)

    assert manager.get("ui.theme") == ("new" if new_config_exists else "default")
    assert manager.config_file.is_file()
    assert old_file.read_text(encoding="utf-8") == old_content


def test_legacy_temp_dir_is_ignored_when_loading(tmp_path: Path) -> None:
    config_file = tmp_path / "old.json"
    old_content = '{"paths": {"temp_dir": {"invalid": true}}}'
    config_file.write_text(old_content, encoding="utf-8")

    manager = ConfigManager(config_file=config_file, auto_save=False)

    assert "temp_dir" not in manager.get("paths")
    assert manager.validate()
    assert config_file.read_text(encoding="utf-8") == old_content


def test_set_and_get_nested_value_without_auto_save(tmp_path: Path) -> None:
    manager = ConfigManager(config_file=tmp_path / "config.json", auto_save=False)

    manager.set("paths.input_dir", "/data/input")

    assert manager.get("paths.input_dir") == "/data/input"
    assert manager.get("paths.not_exists", "fallback") == "fallback"


def test_update_merges_nested_config(tmp_path: Path) -> None:
    manager = ConfigManager(config_file=tmp_path / "config.json", auto_save=False)

    manager.update({"processing": {"batch_size": 8}})

    assert manager.get("processing.batch_size") == 8
    assert manager.get("processing.max_workers") == 4


def test_validate_raises_for_invalid_processing_type(tmp_path: Path) -> None:
    manager = ConfigManager(config_file=tmp_path / "config.json", auto_save=False)
    manager.set("processing.batch_size", "bad")

    with pytest.raises(ConfigurationError):
        manager.validate()


def test_load_invalid_json_raises_configuration_error(tmp_path: Path) -> None:
    config_file = tmp_path / "bad.json"
    config_file.write_text("{ invalid json", encoding="utf-8")

    with pytest.raises(ConfigurationError):
        ConfigManager(config_file=config_file, auto_save=False)


def test_get_all_does_not_mutate_internal_nested_config(tmp_path: Path) -> None:
    manager = ConfigManager(config_file=tmp_path / "config.json", auto_save=False)

    all_config = manager.get_all()
    all_config["paths"]["log_dir"] = "mutated-logs"

    assert manager.get("paths.log_dir") == "logs"


def test_load_from_file_updates_in_memory_config(tmp_path: Path) -> None:
    source_file = tmp_path / "source.json"
    source_file.write_text('{"processing": {"batch_size": 42}}', encoding="utf-8")

    manager = ConfigManager(config_file=tmp_path / "config.json", auto_save=False)
    manager.load_from_file(source_file)

    assert manager.get("processing.batch_size") == 42
    assert manager.get("processing.max_workers") == 4


def test_save_to_file_writes_current_config_to_target(tmp_path: Path) -> None:
    manager = ConfigManager(config_file=tmp_path / "config.json", auto_save=False)
    manager.set("ui.theme", "dark")

    target_file = tmp_path / "export.json"
    manager.save_to_file(target_file)

    exported = ConfigManager(config_file=target_file, auto_save=False)
    assert exported.get("ui.theme") == "dark"
