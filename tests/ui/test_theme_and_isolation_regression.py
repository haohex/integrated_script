# -*- coding: utf-8 -*-
"""Regression tests for system theme resolution, Qt signals, and screenshot isolation."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication

import tests.ui.generate_screenshots as gs
from integrated_script.contracts.results import OperationResult
from integrated_script.ui.desktop.main_window import MainWindow
from integrated_script.ui.desktop.widgets.icon_provider import get_icon
from integrated_script.ui.desktop.widgets.result_view import ResultView
from integrated_script.ui.shared.theme import (
    THEME_DARK,
    THEME_LIGHT,
    THEME_SYSTEM,
    get_palette,
    get_theme_config_path_override,
    resolve_effective_theme,
    save_theme_preference,
    set_theme_config_path_override,
)
from tests.ui.generate_screenshots import capture_all_states


class _MockScheme:
    def __init__(self, name: str):
        self.name = name


@pytest.fixture(autouse=True)
def _clean_theme_override(tmp_path, qapp):
    orig = get_theme_config_path_override()
    temp_theme_file = tmp_path / "theme_preference.json"
    set_theme_config_path_override(temp_theme_file)
    save_theme_preference(THEME_SYSTEM)
    yield
    set_theme_config_path_override(orig)


def test_qt_dark_light_signals(qapp, fake_service, tmp_path):
    """Test that MainWindow updates effective theme on Qt system colorSchemeChanged signals."""
    save_theme_preference(THEME_SYSTEM)
    win = MainWindow(service=fake_service)
    try:
        assert win._style_hints_connected is True

        hints = qapp.styleHints()
        orig_scheme = getattr(hints, "colorScheme", lambda: None)()
        try:
            # When QtHints.setColorScheme is available, test real attribute switch
            if hasattr(hints, "setColorScheme") and hasattr(Qt, "ColorScheme"):
                try:
                    hints.setColorScheme(Qt.ColorScheme.Dark)
                except Exception:
                    pass
            # Emit real Qt signal
            hints.colorSchemeChanged.emit(Qt.ColorScheme.Dark)
            assert win._current_effective_theme == THEME_DARK

            if hasattr(hints, "setColorScheme") and hasattr(Qt, "ColorScheme"):
                try:
                    hints.setColorScheme(Qt.ColorScheme.Light)
                except Exception:
                    pass
            hints.colorSchemeChanged.emit(Qt.ColorScheme.Light)
            assert win._current_effective_theme == THEME_LIGHT
        finally:
            if hasattr(hints, "setColorScheme") and orig_scheme is not None:
                try:
                    hints.setColorScheme(orig_scheme)
                except Exception:
                    pass

        # Unknown scheme fallback
        win._on_system_color_scheme_changed(_MockScheme("Unknown"))
        assert win._current_effective_theme == THEME_LIGHT
    finally:
        win.close()


def test_explicit_theme_protection(qapp, fake_service, tmp_path):
    """Test that explicit user light/dark preference is not overwritten by system colorSchemeChanged."""
    hints = qapp.styleHints()

    # User explicitly selects Light
    save_theme_preference(THEME_LIGHT)
    win = MainWindow(service=fake_service)
    try:
        assert win._current_effective_theme == THEME_LIGHT

        # System signal emits Dark while user preference is explicit Light
        hints.colorSchemeChanged.emit(Qt.ColorScheme.Dark)
        assert win._current_effective_theme == THEME_LIGHT
        win._on_system_color_scheme_changed(_MockScheme("Dark"))
        assert win._current_effective_theme == THEME_LIGHT

        # User explicitly selects Dark
        save_theme_preference(THEME_DARK)
        win._apply_theme_for_mode(THEME_DARK)
        assert win._current_effective_theme == THEME_DARK

        # System signal emits Light while user preference is explicit Dark
        hints.colorSchemeChanged.emit(Qt.ColorScheme.Light)
        assert win._current_effective_theme == THEME_DARK
        win._on_system_color_scheme_changed(_MockScheme("Light"))
        assert win._current_effective_theme == THEME_DARK
    finally:
        win.close()


def test_unknown_from_dark_not_polluted_by_qss(qapp, fake_service, tmp_path):
    """Test that switching from dark to system when Qt colorScheme is Unknown falls back to light,

    and is not polluted by the application's previously applied dark QSS palette.
    """
    save_theme_preference(THEME_DARK)
    win = MainWindow(service=fake_service)
    try:
        win._apply_theme_for_mode(THEME_DARK)
        assert win._current_effective_theme == THEME_DARK

        # Switch to system mode with an Unknown color scheme
        save_theme_preference(THEME_SYSTEM)
        win._on_system_color_scheme_changed(_MockScheme("Unknown"))
        assert win._current_effective_theme == THEME_LIGHT

        # Verify resolve_effective_theme directly with active QApplication
        eff = resolve_effective_theme(THEME_SYSTEM, system_app=QApplication.instance())
        # Since offscreen platform has Unknown color scheme, it must fall back to Light
        assert eff == THEME_LIGHT
    finally:
        win.close()


def test_result_and_icon_consistency(qapp, tmp_path):
    """Test that ResultView and icon_provider maintain theme consistency with banner preservation."""
    save_theme_preference(THEME_DARK)
    dark_pal = get_palette(THEME_DARK)
    light_pal = get_palette(THEME_LIGHT)

    res_view = ResultView()
    try:
        res = OperationResult(
            success=True,
            message="操作成功完成",
            payload={"count": 42, "status": "ok"},
        )
        res_view.set_result(res)

        # In dark mode, banner styling reflects dark status_success_bg
        assert dark_pal["status_success_bg"] in res_view.banner.styleSheet()
        assert res_view.current_payload["count"] == 42

        # Switch active tab to Hierarchy tree
        res_view.tabs.setCurrentIndex(1)
        assert res_view.tabs.currentIndex() == 1

        # Now update theme to light
        res_view.update_theme(THEME_LIGHT)

        # Banner updated to light palette
        assert light_pal["status_success_bg"] in res_view.banner.styleSheet()

        # Payload and tab state are preserved
        assert res_view.current_payload["count"] == 42
        assert res_view.tabs.currentIndex() == 1

        # Icon provider loads correctly under both themes
        icon_dark = get_icon("check", theme_name=THEME_DARK)
        assert not icon_dark.isNull()
        icon_light = get_icon("check", theme_name=THEME_LIGHT)
        assert not icon_light.isNull()
    finally:
        res_view.close()


def test_busy_close_preserves_system_signal(qapp, fake_service, tmp_path):
    """Test that rejecting closeEvent when busy preserves system color scheme signal connection."""
    save_theme_preference(THEME_SYSTEM)
    win = MainWindow(service=fake_service)
    try:
        assert win._style_hints_connected is True

        # Simulate busy task
        fake_service._busy = True
        close_evt = QCloseEvent()
        win.closeEvent(close_evt)

        # Event was rejected and listener is still connected
        assert close_evt.isAccepted() is False
        assert win._style_hints_connected is True

        # System signal still functions while busy window remains open
        qapp.styleHints().colorSchemeChanged.emit(Qt.ColorScheme.Dark)
        assert win._current_effective_theme == THEME_DARK

        # Task finishes and window closes
        fake_service._busy = False
        close_evt2 = QCloseEvent()
        win.closeEvent(close_evt2)

        assert close_evt2.isAccepted() is True
        assert win._style_hints_connected is False
    finally:
        win.close()


def test_no_qt_subprocess_import_shared():
    """Verify that importing integrated_script.ui.shared in a subprocess does not import PySide6."""
    code = (
        "import integrated_script.ui.shared as s; "
        "import integrated_script.ui.shared.theme as t; "
        "import sys; "
        "qt = [m for m in sys.modules if m.startswith('PySide6')]; "
        "assert not qt, f'PySide6 modules unexpectedly loaded: {qt}'"
    )
    repo_root = Path(__file__).resolve().parents[2]
    sub_env = os.environ.copy()
    sub_env["PYTHONPATH"] = f"{repo_root / 'src'}{os.pathsep}{repo_root}"
    res = subprocess.run(
        [sys.executable, "-c", code],
        env=sub_env,
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"Subprocess stdout: {res.stdout}, stderr: {res.stderr}"


def test_screenshot_isolation_success_and_exception(tmp_path, monkeypatch, qapp):
    """Test screenshot capture sandbox isolation: sentinel untouched, env and override restored."""
    # Monkeypatch OUTPUT_DIR to tmp_path so tests never overwrite docs/design/screenshots
    test_out = tmp_path / "screenshots"
    monkeypatch.setattr(gs, "OUTPUT_DIR", test_out)

    sentinel_dir = tmp_path / "user_home"
    sentinel_dir.mkdir(parents=True, exist_ok=True)
    sentinel_file = sentinel_dir / "theme_preference.json"
    sentinel_file.write_text('{"theme": "sentinel_value"}', encoding="utf-8")

    set_theme_config_path_override(sentinel_file)

    env_keys = (
        "QT_QPA_PLATFORM",
        "XDG_CONFIG_HOME",
        "XDG_STATE_HOME",
        "XDG_CACHE_HOME",
        "XDG_DATA_HOME",
        "APPDATA",
        "LOCALAPPDATA",
    )
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "orig_config"))
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "orig_appdata"))
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    orig_env_snapshot = {k: os.environ.get(k) for k in env_keys}

    import platformdirs

    import integrated_script.application.paths as app_paths

    orig_pd = platformdirs.PlatformDirs
    orig_app_pd = app_paths.PlatformDirs

    # 1. Successful capture run
    sandbox1 = tmp_path / "sandbox1"
    files = capture_all_states(sandbox_root=sandbox1)
    assert len(files) == 8
    for f in files:
        assert Path(f).is_file()
        assert Path(f).parent == test_out

    # Sentinel file and state restored
    assert sentinel_file.read_text(encoding="utf-8") == '{"theme": "sentinel_value"}'
    assert get_theme_config_path_override() == sentinel_file

    # PlatformDirs alias and environment restored
    assert platformdirs.PlatformDirs is orig_pd
    assert app_paths.PlatformDirs is orig_app_pd
    for k in env_keys:
        assert (
            os.environ.get(k) == orig_env_snapshot[k]
        ), f"Env key {k} was not restored after success"

    # 2. Simulated artificial exception
    def _crash_annotate(*args, **kwargs):
        raise RuntimeError("Artificial crash during screenshot generation")

    monkeypatch.setattr(gs, "annotate_screenshot", _crash_annotate)

    sandbox2 = tmp_path / "sandbox2"
    with pytest.raises(RuntimeError, match="Artificial crash"):
        capture_all_states(sandbox_root=sandbox2)

    # Sentinel file, override, PlatformDirs alias, and env must be restored even after exception
    assert sentinel_file.read_text(encoding="utf-8") == '{"theme": "sentinel_value"}'
    assert get_theme_config_path_override() == sentinel_file
    assert platformdirs.PlatformDirs is orig_pd
    assert app_paths.PlatformDirs is orig_app_pd
    for k in env_keys:
        assert (
            os.environ.get(k) == orig_env_snapshot[k]
        ), f"Env key {k} was not restored after exception"


def test_cold_start_subprocess_isolation(tmp_path):
    """Cold-start subprocess test ensuring no state/config/log files leak and PlatformDirs alias restored."""
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir(parents=True, exist_ok=True)
    mock_config = fake_home / ".config"
    mock_state = fake_home / ".local" / "state"
    mock_cache = fake_home / ".cache"
    mock_data = fake_home / ".local" / "share"
    mock_config.mkdir(parents=True, exist_ok=True)
    mock_state.mkdir(parents=True, exist_ok=True)
    mock_cache.mkdir(parents=True, exist_ok=True)
    mock_data.mkdir(parents=True, exist_ok=True)

    sentinel_log = mock_state / "sentinel.log"
    sentinel_log.write_text("initial_sentinel_data", encoding="utf-8")

    sub_output = tmp_path / "sub_screenshots"
    sub_sandbox1 = tmp_path / "sub_sandbox1"
    sub_sandbox2 = tmp_path / "sub_sandbox2"

    initial_home_files = set(fake_home.rglob("*"))

    repo_root = Path(__file__).resolve().parents[2]
    sub_env = os.environ.copy()
    sub_env["HOME"] = str(fake_home)
    sub_env["USERPROFILE"] = str(fake_home)
    sub_env["XDG_CONFIG_HOME"] = str(mock_config)
    sub_env["XDG_STATE_HOME"] = str(mock_state)
    sub_env["XDG_CACHE_HOME"] = str(mock_cache)
    sub_env["XDG_DATA_HOME"] = str(mock_data)
    sub_env["QT_QPA_PLATFORM"] = "offscreen"
    sub_env.pop("APPDATA", None)
    sub_env.pop("LOCALAPPDATA", None)
    sub_env["PYTHONPATH"] = f"{repo_root / 'src'}{os.pathsep}{repo_root}"

    code = (
        "import sys\n"
        "from pathlib import Path\n"
        "import platformdirs\n"
        "orig_pd = platformdirs.PlatformDirs\n"
        "assert 'integrated_script.application.paths' not in sys.modules\n"
        "assert 'integrated_script.application' not in sys.modules\n"
        "import tests.ui.generate_screenshots as gs\n"
        f"gs.OUTPUT_DIR = Path({repr(str(sub_output))})\n"
        f"files1 = gs.capture_all_states(sandbox_root=Path({repr(str(sub_sandbox1))}))\n"
        "assert len(files1) == 8, f'Expected 8 files, got {len(files1)}'\n"
        "import integrated_script.application.paths as app_paths\n"
        "assert platformdirs.PlatformDirs is orig_pd\n"
        "assert app_paths.PlatformDirs is orig_pd\n"
        f"files2 = gs.capture_all_states(sandbox_root=Path({repr(str(sub_sandbox2))}))\n"
        "assert len(files2) == 8, f'Expected 8 files, got {len(files2)}'\n"
        "assert platformdirs.PlatformDirs is orig_pd\n"
        "assert app_paths.PlatformDirs is orig_pd\n"
    )

    res = subprocess.run(
        [sys.executable, "-c", code],
        env=sub_env,
        capture_output=True,
        text=True,
    )
    assert (
        res.returncode == 0
    ), f"Subprocess failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"

    # Sentinel log is untouched
    assert sentinel_log.read_text(encoding="utf-8") == "initial_sentinel_data"

    # Mock user directory must not have any new state/config/log files
    remaining_home_files = set(fake_home.rglob("*"))
    new_files = remaining_home_files - initial_home_files
    assert not new_files, f"Subprocess leaked files into mock home: {new_files}"

    # Output files exist in temporary directory only
    out_files = list(sub_output.glob("*.png"))
    assert len(out_files) == 8
