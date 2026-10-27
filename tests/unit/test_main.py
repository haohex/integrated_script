from pathlib import Path
from types import SimpleNamespace
from typing import List, cast

import pytest

from integrated_script.main import (
    ConfigManager,
    load_config_from_args,
    main,
    run_build_mode,
    run_interactive_mode,
    setup_argument_parser,
    setup_logging_from_args,
)
from integrated_script.version import get_version


class _Logger:
    def __init__(self):
        self.infos: List[str] = []
        self.errors: List[str] = []

    def info(self, message: str) -> None:
        self.infos.append(message)

    def error(self, message: str) -> None:
        self.errors.append(message)


class _DummyInterfaceSuccess:
    def __init__(self, _config):
        pass

    def run(self):
        return None


class _DummyInterfaceInterrupt:
    def __init__(self, _config):
        pass

    def run(self):
        raise KeyboardInterrupt


class _DummyInterfaceFailure:
    def __init__(self, _config):
        pass

    def run(self):
        raise RuntimeError("boom")


class _DummyResult:
    def __init__(self, returncode: int):
        self.returncode = returncode


def _args(**overrides):
    data = {
        "log_level": "INFO",
        "quiet": False,
        "verbose": False,
        "log_file": None,
        "config": None,
        "build": False,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_setup_argument_parser_parses_build_flag() -> None:
    parser = setup_argument_parser()

    args = parser.parse_args(["--build"])

    assert args.build is True


def test_setup_argument_parser_version_matches_unified_source(capsys) -> None:
    parser = setup_argument_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["--version"])

    captured = capsys.readouterr()
    assert get_version() in captured.out


def test_setup_logging_from_args_respects_quiet(monkeypatch) -> None:
    captured = {}

    def _fake_setup_logging(log_dir, log_level, enable_error_file):
        captured["log_dir"] = log_dir
        captured["log_level"] = log_level
        captured["enable_error_file"] = enable_error_file

    monkeypatch.setattr("integrated_script.main.setup_logging", _fake_setup_logging)

    setup_logging_from_args(_args(quiet=True))

    assert captured == {
        "log_dir": "logs",
        "log_level": "WARNING",
        "enable_error_file": True,
    }


def test_setup_logging_from_args_uses_verbose_and_log_file_dir(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured = {}

    def _fake_setup_logging(log_dir, log_level, enable_error_file):
        captured["log_dir"] = log_dir
        captured["log_level"] = log_level
        captured["enable_error_file"] = enable_error_file

    monkeypatch.setattr("integrated_script.main.setup_logging", _fake_setup_logging)

    log_file = tmp_path / "logs" / "run.log"
    setup_logging_from_args(_args(verbose=True, log_file=str(log_file)))

    assert captured == {
        "log_dir": str(log_file.parent),
        "log_level": "DEBUG",
        "enable_error_file": True,
    }


def test_load_config_from_args_returns_manager_without_custom_path() -> None:
    manager = load_config_from_args(_args(config=None))

    assert manager is not None


def test_load_config_from_args_loads_custom_config_success(
    monkeypatch, tmp_path: Path
) -> None:
    logger = _Logger()

    config_path = tmp_path / "custom.json"
    config_path.write_text('{"version": "1.0.0"}', encoding="utf-8")

    monkeypatch.setattr("integrated_script.main.get_logger", lambda _name: logger)

    manager = load_config_from_args(_args(config=str(config_path)))

    assert manager is not None
    assert manager.config_file == config_path
    assert any("已加载配置文件" in message for message in logger.infos)


def test_load_config_from_args_exits_when_config_load_fails(
    monkeypatch, tmp_path: Path
) -> None:
    logger = _Logger()

    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text("[invalid", encoding="utf-8")

    monkeypatch.setattr("integrated_script.main.get_logger", lambda _name: logger)

    with pytest.raises(SystemExit) as exc_info:
        load_config_from_args(_args(config=str(bad_yaml)))

    assert exc_info.value.code == 1
    assert any("加载配置文件失败" in message for message in logger.errors)


def test_run_interactive_mode_returns_zero_on_success(monkeypatch) -> None:
    monkeypatch.setattr(
        "integrated_script.main.InteractiveInterface",
        _DummyInterfaceSuccess,
    )

    result = run_interactive_mode(config_manager=cast(ConfigManager, object()))

    assert result == 0


def test_run_interactive_mode_returns_130_on_keyboard_interrupt(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "integrated_script.main.InteractiveInterface",
        _DummyInterfaceInterrupt,
    )

    result = run_interactive_mode(config_manager=cast(ConfigManager, object()))

    assert result == 130


def test_run_interactive_mode_returns_one_on_exception(monkeypatch) -> None:
    logger = _Logger()

    monkeypatch.setattr(
        "integrated_script.main.InteractiveInterface",
        _DummyInterfaceFailure,
    )
    monkeypatch.setattr("integrated_script.main.get_logger", lambda _name: logger)

    result = run_interactive_mode(config_manager=cast(ConfigManager, object()))

    assert result == 1
    assert any("交互式模式运行失败" in message for message in logger.errors)


def test_run_build_mode_returns_one_when_script_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "integrated_script.main.__file__",
        str(tmp_path / "src" / "main.py"),
    )

    result = run_build_mode()

    assert result == 1


def test_run_build_mode_returns_zero_when_subprocess_succeeds(
    monkeypatch,
    tmp_path: Path,
) -> None:
    logger = _Logger()
    calls = {}

    module_file = tmp_path / "src" / "integrated_script" / "main.py"
    module_file.parent.mkdir(parents=True)
    module_file.write_text("", encoding="utf-8")

    build_script = tmp_path / "build_exe.py"
    build_script.write_text("print('ok')", encoding="utf-8")

    monkeypatch.setattr("integrated_script.main.__file__", str(module_file))
    monkeypatch.setattr("integrated_script.main.get_logger", lambda _name: logger)

    def _fake_run(cmd, cwd, capture_output):
        calls["cmd"] = cmd
        calls["cwd"] = cwd
        calls["capture_output"] = capture_output
        return _DummyResult(returncode=0)

    monkeypatch.setattr("integrated_script.main.subprocess.run", _fake_run)

    result = run_build_mode()

    assert result == 0
    assert calls["cmd"][1] == str(build_script)
    assert calls["cwd"] == str(tmp_path)
    assert calls["capture_output"] is False


def test_run_build_mode_returns_subprocess_error_code(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module_file = tmp_path / "src" / "integrated_script" / "main.py"
    module_file.parent.mkdir(parents=True)
    module_file.write_text("", encoding="utf-8")

    build_script = tmp_path / "build_exe.py"
    build_script.write_text("print('ok')", encoding="utf-8")

    monkeypatch.setattr("integrated_script.main.__file__", str(module_file))
    monkeypatch.setattr(
        "integrated_script.main.subprocess.run",
        lambda *_args, **_kwargs: _DummyResult(returncode=3),
    )

    result = run_build_mode()

    assert result == 3


def test_run_build_mode_returns_one_when_subprocess_raises(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module_file = tmp_path / "src" / "integrated_script" / "main.py"
    module_file.parent.mkdir(parents=True)
    module_file.write_text("", encoding="utf-8")

    build_script = tmp_path / "build_exe.py"
    build_script.write_text("print('ok')", encoding="utf-8")

    monkeypatch.setattr("integrated_script.main.__file__", str(module_file))

    def _raise_run(*_args, **_kwargs):
        raise RuntimeError("spawn failed")

    monkeypatch.setattr("integrated_script.main.subprocess.run", _raise_run)

    result = run_build_mode()

    assert result == 1


def test_main_build_branch_returns_sub_result(monkeypatch) -> None:
    monkeypatch.setattr("integrated_script.main.run_build_mode", lambda: 7)

    result = main(["--build"])

    assert result == 7


def test_main_interactive_branch_returns_sub_result(monkeypatch) -> None:
    monkeypatch.setattr(
        "integrated_script.main.setup_logging_from_args", lambda _args: None
    )
    monkeypatch.setattr(
        "integrated_script.main.load_config_from_args", lambda _args: object()
    )
    monkeypatch.setattr("integrated_script.main.run_interactive_mode", lambda _cfg: 0)

    result = main([])

    assert result == 0


def test_main_returns_one_on_unhandled_exception(monkeypatch) -> None:
    logger = _Logger()

    monkeypatch.setattr(
        "integrated_script.main.setup_logging_from_args", lambda _args: None
    )
    monkeypatch.setattr("integrated_script.main.get_logger", lambda _name: logger)
    monkeypatch.setattr(
        "integrated_script.main.load_config_from_args", lambda _args: object()
    )

    def _raise_run_interactive(_config):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(
        "integrated_script.main.run_interactive_mode", _raise_run_interactive
    )

    result = main([])

    assert result == 1
    assert any("程序运行失败" in message for message in logger.errors)


def test_unified_version_matches_pyproject() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    pyproject = (repo_root / "pyproject.toml").read_text(encoding="utf-8")

    in_project_section = False
    pyproject_version = None
    for line in pyproject.splitlines():
        stripped = line.strip()
        if stripped == "[project]":
            in_project_section = True
            continue
        if in_project_section and stripped.startswith("[") and stripped != "[project]":
            break
        if in_project_section and stripped.startswith("version"):
            pyproject_version = stripped.split("=", 1)[1].strip().strip("\"'")
            break

    assert pyproject_version is not None
    assert get_version() == pyproject_version
