from pathlib import Path

import pytest

from integrated_script.config.exceptions import PathError, ProcessingError
from integrated_script.config.settings import ConfigManager
from integrated_script.core.base import BaseProcessor


class DummyProcessor(BaseProcessor):
    def __init__(self, config: ConfigManager):
        self.initialize_called = False
        self.cleanup_called = False
        self.should_validate = True
        self.should_fail = False
        super().__init__(config=config, name="DummyProcessor")

    def initialize(self) -> None:
        self.initialize_called = True

    def validate_input(self, *_args, **_kwargs) -> bool:
        return self.should_validate

    def process(self, value: int = 0) -> dict[str, int]:
        if self.should_fail:
            raise RuntimeError("boom")
        return {"value": value}

    def cleanup(self) -> None:
        self.cleanup_called = True


class DefaultHookProcessor(BaseProcessor):
    def initialize(self) -> None:
        return None

    def process(self, value: int = 0) -> int:
        return value


class InitFailProcessor(BaseProcessor):
    def initialize(self) -> None:
        raise RuntimeError("init-fail")

    def process(self, value: int = 0) -> int:
        return value


class CleanupFailProcessor(BaseProcessor):
    def initialize(self) -> None:
        return None

    def process(self, _value: int = 0) -> int:
        raise RuntimeError("process-fail")

    def cleanup(self) -> None:
        raise RuntimeError("cleanup-fail")


def _build_config(tmp_path: Path) -> ConfigManager:
    config = ConfigManager(
        config_file=tmp_path / "config.json",
        auto_save=False,
    )
    config.set("paths.log_dir", str(tmp_path / "logs"))
    return config


def test_base_processor_initializes_without_creating_temp(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    config = _build_config(tmp_path)

    processor = DummyProcessor(config=config)

    assert processor.initialize_called
    assert not (tmp_path / "temp").exists()
    assert (tmp_path / "logs").exists()


def test_base_processor_ignores_legacy_temp_dir(tmp_path: Path) -> None:
    config = _build_config(tmp_path)
    legacy_temp = tmp_path / "legacy-temp"
    config.set("paths.temp_dir", str(legacy_temp))

    processor = DummyProcessor(config=config)

    assert processor.initialize_called
    assert not legacy_temp.exists()
    assert (tmp_path / "logs").exists()


def test_run_returns_process_result_and_calls_cleanup(tmp_path: Path) -> None:
    processor = DummyProcessor(config=_build_config(tmp_path))

    result = processor.run(value=3)

    assert result == {"value": 3}
    assert processor.cleanup_called


def test_run_raises_when_validation_fails(tmp_path: Path) -> None:
    processor = DummyProcessor(config=_build_config(tmp_path))
    processor.should_validate = False

    with pytest.raises(ProcessingError):
        processor.run(value=1)

    assert processor.cleanup_called


def test_run_raises_when_processor_not_initialized(tmp_path: Path) -> None:
    processor = DummyProcessor(config=_build_config(tmp_path))
    processor._initialized = False

    with pytest.raises(ProcessingError):
        processor.run()


def test_run_raises_when_processor_already_processing(tmp_path: Path) -> None:
    processor = DummyProcessor(config=_build_config(tmp_path))
    processor._processing = True

    with pytest.raises(ProcessingError):
        processor.run()


def test_run_resets_processing_flag_after_failure(tmp_path: Path) -> None:
    processor = DummyProcessor(config=_build_config(tmp_path))
    processor.should_fail = True

    with pytest.raises(RuntimeError):
        processor.run(value=2)

    assert processor._processing is False
    assert processor.cleanup_called


def test_validate_path_checks_dir_and_file_requirements(
    tmp_path: Path,
) -> None:
    processor = DummyProcessor(config=_build_config(tmp_path))

    file_path = tmp_path / "item.txt"
    file_path.write_text("x", encoding="utf-8")

    with pytest.raises(PathError):
        processor.validate_path(file_path, must_be_dir=True)

    with pytest.raises(PathError):
        processor.validate_path(tmp_path, must_be_file=True)


def test_validate_path_raises_when_missing(tmp_path: Path) -> None:
    processor = DummyProcessor(config=_build_config(tmp_path))

    with pytest.raises(PathError):
        processor.validate_path(tmp_path / "not-exists", must_exist=True)


def test_validate_path_returns_input_path_object_without_resolving(
    tmp_path: Path,
) -> None:
    processor = DummyProcessor(config=_build_config(tmp_path))

    relative_path = Path("tmp") / "demo"
    validated = processor.validate_path(relative_path, must_exist=False)

    assert validated == relative_path


def test_get_file_list_filters_extensions_and_recursive_flag(
    tmp_path: Path,
) -> None:
    processor = DummyProcessor(config=_build_config(tmp_path))

    root_txt = tmp_path / "root.txt"
    root_jpg = tmp_path / "root.jpg"
    hidden_txt = tmp_path / ".hidden.txt"
    nested_dir = tmp_path / "nested"
    nested_dir.mkdir()
    nested_txt = nested_dir / "nested.txt"

    root_txt.write_text("x", encoding="utf-8")
    root_jpg.write_text("x", encoding="utf-8")
    hidden_txt.write_text("x", encoding="utf-8")
    nested_txt.write_text("x", encoding="utf-8")

    non_recursive = processor.get_file_list(
        tmp_path,
        extensions=[".txt"],
        recursive=False,
    )
    recursive = processor.get_file_list(
        tmp_path,
        extensions=[".txt"],
        recursive=True,
    )

    assert sorted(path.name for path in non_recursive) == [".hidden.txt", "root.txt"]
    assert sorted(path.name for path in recursive) == [
        ".hidden.txt",
        "nested.txt",
        "root.txt",
    ]


def test_context_manager_calls_cleanup_on_exit(tmp_path: Path) -> None:
    processor = DummyProcessor(config=_build_config(tmp_path))
    processor.cleanup_called = False

    with processor as ctx:
        assert ctx is processor

    assert processor.cleanup_called


def test_str_and_repr_include_processor_state(tmp_path: Path) -> None:
    processor = DummyProcessor(config=_build_config(tmp_path))

    output = str(processor)

    assert "DummyProcessor" in output
    assert "initialized=True" in output
    assert repr(processor) == output


def test_default_validate_input_returns_true(tmp_path: Path) -> None:
    processor = DefaultHookProcessor(
        config=_build_config(tmp_path),
        name="Default",
    )

    assert processor.validate_input() is True


def test_default_cleanup_method_is_callable(tmp_path: Path) -> None:
    processor = DefaultHookProcessor(
        config=_build_config(tmp_path),
        name="Default",
    )

    processor.cleanup()


def test_initialize_wraps_exceptions_as_processing_error(
    tmp_path: Path,
) -> None:
    with pytest.raises(ProcessingError):
        InitFailProcessor(config=_build_config(tmp_path), name="InitFail")


def test_run_keeps_original_error_when_cleanup_fails(tmp_path: Path) -> None:
    processor = CleanupFailProcessor(
        config=_build_config(tmp_path),
        name="CleanupFail",
    )

    with pytest.raises(RuntimeError, match="process-fail"):
        processor.run()
