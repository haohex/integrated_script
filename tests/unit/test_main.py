from pathlib import Path
from types import SimpleNamespace
from typing import List, cast

import pytest

from integrated_script.main import (
    ConfigManager,
    default_log_dir,
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
        "legacy_cli": False,
        "gui": False,
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


def test_setup_argument_parser_parses_frontend_flags() -> None:
    parser = setup_argument_parser()

    legacy = parser.parse_args(["--legacy-cli"])
    gui = parser.parse_args(["--gui"])

    assert legacy.legacy_cli is True
    assert legacy.gui is False
    assert gui.gui is True
    assert gui.legacy_cli is False


def test_setup_logging_from_args_respects_quiet(monkeypatch) -> None:
    captured = {}

    def _fake_setup_logging(log_dir, log_level, enable_error_file):
        captured["log_dir"] = log_dir
        captured["log_level"] = log_level
        captured["enable_error_file"] = enable_error_file

    monkeypatch.setattr("integrated_script.main.setup_logging", _fake_setup_logging)
    monkeypatch.setattr(
        "integrated_script.main.default_log_dir", lambda: "/tmp/user-logs"
    )

    setup_logging_from_args(_args(quiet=True))

    assert captured == {
        "log_dir": "/tmp/user-logs",
        "log_level": "WARNING",
        "enable_error_file": True,
    }


def test_default_log_dir_is_not_cwd_logs() -> None:
    log_dir = Path(default_log_dir())
    assert log_dir.is_absolute()
    assert log_dir != Path.cwd() / "logs"


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


def test_main_default_branch_uses_tui(monkeypatch) -> None:
    calls = {}

    monkeypatch.setattr(
        "integrated_script.main.setup_logging_from_args", lambda _args: None
    )
    monkeypatch.setattr(
        "integrated_script.main.load_config_from_args", lambda _args: None
    )

    def _fake_tui(config_manager, working_directory):
        calls["config"] = config_manager
        calls["cwd"] = working_directory
        return 0

    monkeypatch.setattr("integrated_script.main.run_tui_mode", _fake_tui)
    monkeypatch.setattr(
        "integrated_script.main.run_interactive_mode",
        lambda _cfg: pytest.fail("默认入口不应进入旧交互模式"),
    )

    result = main([])

    assert result == 0
    assert calls["config"] is None
    assert calls["cwd"] == Path.cwd()


def test_main_default_branch_does_not_create_cwd_config(
    monkeypatch, tmp_path: Path
) -> None:
    """默认 TUI 入口不得在 cwd 创建 config.json。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "integrated_script.main.setup_logging_from_args", lambda _args: None
    )
    monkeypatch.setattr("integrated_script.main.run_tui_mode", lambda _cfg, _cwd: 0)

    assert main([]) == 0
    assert not (tmp_path / "config.json").exists()


def test_main_legacy_cli_branch_uses_interactive_mode(monkeypatch) -> None:
    captured = {}

    monkeypatch.setattr(
        "integrated_script.main.setup_logging_from_args", lambda _args: None
    )
    monkeypatch.setattr(
        "integrated_script.main.run_interactive_mode",
        lambda cfg: captured.update({"config": cfg}) or 0,
    )
    monkeypatch.setattr(
        "integrated_script.main.run_tui_mode",
        lambda *_args: pytest.fail("--legacy-cli 不应进入 TUI"),
    )

    result = main(["--legacy-cli"])

    assert result == 0
    assert isinstance(captured["config"], ConfigManager)


def test_main_gui_branch_uses_gui_mode(monkeypatch) -> None:
    captured = {}

    monkeypatch.setattr(
        "integrated_script.main.setup_logging_from_args", lambda _args: None
    )
    monkeypatch.setattr(
        "integrated_script.main.run_gui_mode",
        lambda cfg, cwd: captured.update({"config": cfg, "cwd": cwd}) or 0,
    )
    monkeypatch.setattr(
        "integrated_script.main.run_tui_mode",
        lambda *_args: pytest.fail("--gui 不应进入 TUI"),
    )

    result = main(["--gui"])

    assert result == 0
    assert captured["config"] is None
    assert captured["cwd"] == Path.cwd()


def test_main_returns_one_on_unhandled_exception(monkeypatch) -> None:
    logger = _Logger()

    monkeypatch.setattr(
        "integrated_script.main.setup_logging_from_args", lambda _args: None
    )
    monkeypatch.setattr("integrated_script.main.get_logger", lambda _name: logger)
    monkeypatch.setattr(
        "integrated_script.main.load_config_from_args", lambda _args: object()
    )

    def _raise_run_tui(_config, _cwd):
        raise RuntimeError("unexpected")

    monkeypatch.setattr("integrated_script.main.run_tui_mode", _raise_run_tui)

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
