# -*- coding: utf-8 -*-
"""Regression tests for progress contract (indeterminate vs determinate) and Rich markup path isolation."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from textual.widgets import Label, ProgressBar, RichLog

from integrated_script.application import AppService
from integrated_script.application.contracts import TaskEvent
from integrated_script.config import ConfigManager
from integrated_script.contracts.results import OperationResult
from integrated_script.ui.desktop.main_window import MainWindow
from integrated_script.ui.shared.theme import (
    get_theme_config_path_override,
    set_theme_config_path_override,
)
from integrated_script.ui.tui.app import TuiApp


@pytest.fixture(autouse=True)
def isolated_progress_state(monkeypatch, tmp_path):
    for name, directory in (
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_STATE_HOME", "state"),
        ("XDG_CACHE_HOME", "cache"),
        ("XDG_DATA_HOME", "data"),
    ):
        monkeypatch.setenv(name, str(tmp_path / directory))
    if os.name == "nt":
        import platformdirs.windows

        monkeypatch.setattr(
            platformdirs.windows,
            "get_win_folder",
            lambda name: str(tmp_path / "native_user" / name.lower()),
        )
    previous_theme_path = get_theme_config_path_override()
    set_theme_config_path_override(tmp_path / "theme.json")
    try:
        yield
    finally:
        set_theme_config_path_override(previous_theme_path)


def test_desktop_progress_contract_lifecycle(qapp, fake_service):
    """Verify GUI progress bar: indeterminate (0, 0) on unknown total/current, restores (0, 100) on known."""
    win = MainWindow(service=fake_service)
    win.show()
    try:
        win._select_operation_by_id("yolo.validate_detection")
        assert win.progress_bar.minimum() == 0
        assert win.progress_bar.maximum() == 100
        assert win.progress_bar.value() == 0

        # 1. Unknown total (None) -> Indeterminate
        event_unknown1 = TaskEvent(
            task_id="task_test_1",
            kind="progress",
            current=None,
            total=None,
            message="正在全盘扫描文件...",
        )
        win._handle_event(event_unknown1)
        assert win.progress_bar.minimum() == 0
        assert win.progress_bar.maximum() == 0
        assert win.lbl_step.text() == "正在全盘扫描文件..."
        assert win.lbl_status.text() == "正在执行..."
        assert "%" not in win.lbl_status.text()

        # 2. Known total (50 / 100) -> Determinate
        event_known1 = TaskEvent(
            task_id="task_test_1",
            kind="progress",
            current=50,
            total=100,
            message="正在校验图片 50/100",
        )
        win._handle_event(event_known1)
        assert win.progress_bar.minimum() == 0
        assert win.progress_bar.maximum() == 100
        assert win.progress_bar.value() == 50
        assert win.lbl_step.text() == "正在校验图片 50/100"
        assert "50%" in win.lbl_status.text()

        # 3. Unknown total again (0 total) -> Indeterminate
        event_unknown2 = TaskEvent(
            task_id="task_test_1",
            kind="progress",
            current=10,
            total=0,
            message="正在整理分析报告...",
        )
        win._handle_event(event_unknown2)
        assert win.progress_bar.minimum() == 0
        assert win.progress_bar.maximum() == 0
        assert win.lbl_step.text() == "正在整理分析报告..."
        assert win.lbl_status.text() == "正在执行..."
        assert "%" not in win.lbl_status.text()

        # 4. Completed event -> Range reset to 0..100
        event_completed = TaskEvent(
            task_id="task_test_1",
            kind="completed",
            result=OperationResult(
                success=True,
                message="分析完成",
            ),
        )
        win._handle_event(event_completed)
        assert win.progress_bar.minimum() == 0
        assert win.progress_bar.maximum() == 100
        assert win.progress_bar.value() == 100
        assert win.lbl_status.text() == "执行成功"

        # 5. Failed event -> Range reset to 0..100
        win._handle_event(event_unknown1)
        assert win.progress_bar.maximum() == 0
        event_failed = TaskEvent(
            task_id="task_test_1",
            kind="failed",
            message="运行时错误",
        )
        win._handle_event(event_failed)
        assert win.progress_bar.minimum() == 0
        assert win.progress_bar.maximum() == 100
        assert win.lbl_status.text() == "执行失败"
    finally:
        win.close()


@pytest.mark.asyncio
async def test_tui_progress_contract_lifecycle(fake_service):
    """Verify TUI progress bar: update(total=None, progress=0) on unknown, update(total=100) on known."""
    app = TuiApp(service=fake_service)
    async with app.run_test():
        clean_op = next(
            o
            for o in fake_service.list_operations()
            if o.id == "yolo.validate_detection"
        )
        app._load_operation_details(clean_op)

        pbar = app.query_one("#progress_bar", ProgressBar)
        assert pbar.total == 100
        assert pbar.progress == 0

        # 1. Unknown total (None) -> Indeterminate
        fake_service._events.append(
            TaskEvent(
                task_id="t_tui_1",
                kind="progress",
                current=None,
                total=None,
                message="正在扫描数据集...",
            )
        )
        app._poll_events()
        assert pbar.total is None
        assert pbar.progress == 0
        assert app.query_one("#lbl_step", Label).content.plain == "正在扫描数据集..."

        # 2. Known total (40/100) -> Determinate
        fake_service._events.append(
            TaskEvent(
                task_id="t_tui_1",
                kind="progress",
                current=40,
                total=100,
                message="处理中: 40/100",
            )
        )
        app._poll_events()
        assert pbar.total == 100
        assert pbar.progress == 40
        assert app.query_one("#lbl_step", Label).content.plain == "处理中: 40/100"

        # 3. Unknown total again (0 total) -> Indeterminate
        fake_service._events.append(
            TaskEvent(
                task_id="t_tui_1",
                kind="progress",
                current=None,
                total=0,
                message="等待外部进程...",
            )
        )
        app._poll_events()
        assert pbar.total is None
        assert pbar.progress == 0
        assert app.query_one("#lbl_step", Label).content.plain == "等待外部进程..."

        # 4. Completed event -> Consistent (total=100, progress=100)
        fake_service._events.append(
            TaskEvent(
                task_id="t_tui_1",
                kind="completed",
                result=OperationResult(
                    success=True,
                    message="全部完成",
                ),
            )
        )
        app._poll_events()
        assert pbar.total == 100
        assert pbar.progress == 100
        assert "执行成功" in str(app.query_one("#lbl_status", Label).content)


@pytest.mark.asyncio
async def test_tui_rich_markup_path_isolation(fake_service):
    """Verify raw POSIX paths like '/tmp/数据[/目录]' do not cause MarkupError and render literal text."""
    test_path = "/tmp/数据[/目录]"
    app = TuiApp(service=fake_service)
    async with app.run_test() as pilot:
        # Display exec panel so RichLog renders lines with known dimensions
        app.query_one("#exec_panel").styles.display = "block"

        # 1. Started event containing raw path
        fake_service._events.append(
            TaskEvent(
                task_id="t_path_1",
                kind="started",
                message=f"启动任务，目标路径: {test_path}",
            )
        )
        app._poll_events()
        await pilot.pause()
        step_text = app.query_one("#lbl_step", Label).content.plain
        assert test_path in step_text

        log_lines = [line.text for line in app.query_one("#log_view", RichLog).lines]
        assert any(test_path in line and "[INFO]" in line for line in log_lines)

        # 2. Progress event containing raw path
        fake_service._events.append(
            TaskEvent(
                task_id="t_path_1",
                kind="progress",
                current=30,
                total=100,
                message=f"正在分析文件: {test_path}/image.jpg",
            )
        )
        app._poll_events()
        await pilot.pause()
        step_text_2 = app.query_one("#lbl_step", Label).content.plain
        assert f"{test_path}/image.jpg" in step_text_2

        # 3. Log event containing raw path
        fake_service._events.append(
            TaskEvent(
                task_id="t_path_1",
                kind="log",
                message=f"跳过已存在目录: {test_path}/cache",
            )
        )
        app._poll_events()
        await pilot.pause()
        log_lines_updated = [
            line.text for line in app.query_one("#log_view", RichLog).lines
        ]
        assert any(f"{test_path}/cache" in line for line in log_lines_updated)


def test_real_service_contract_isolation(tmp_path: Path):
    """Verify contract isolation with explicit temporary ConfigManager and working_dir."""
    temp_dir = tmp_path / "temp"
    log_dir = tmp_path / "logs"
    temp_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    config = ConfigManager(config_file=tmp_path / "config.json", auto_save=False)
    config.set("paths.temp_dir", str(temp_dir))
    config.set("paths.log_dir", str(log_dir))

    service = AppService(config, working_directory=tmp_path)
    try:
        assert service.busy is False
        ops = service.list_operations()
        assert len(ops) > 0
    finally:
        service.close()
