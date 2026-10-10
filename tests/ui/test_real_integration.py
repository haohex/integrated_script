# -*- coding: utf-8 -*-
"""Real integration tests connecting Desktop GUI and TUI with the actual AppService."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

import pytest
from textual.widgets import Label

from integrated_script.application import AppService
from integrated_script.config import ConfigManager
from integrated_script.ui.desktop.main_window import MainWindow
from integrated_script.ui.tui.app import TuiApp


@pytest.fixture
def real_service(tmp_path: Path):
    """Fixture providing a real AppService instance with lifecycle cleanup."""
    temp_dir = tmp_path / "temp"
    log_dir = tmp_path / "logs"
    temp_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    config = ConfigManager(config_file=tmp_path / "config.json", auto_save=False)
    config.set("paths.temp_dir", str(temp_dir))
    config.set("paths.log_dir", str(log_dir))

    service = AppService(config, working_directory=tmp_path)
    try:
        yield service
    finally:
        service.close()


def test_real_gui_config_view(qapp, real_service):
    """Test viewing config in desktop GUI against real AppService."""
    win = MainWindow(service=real_service)
    win.show()
    try:
        # Select config.view
        win._select_operation_by_id("config.view")
        assert win.active_operation is not None
        assert win.active_operation.id == "config.view"

        # Execute
        win.btn_execute.click()

        # Wait and poll for completion
        for _ in range(50):
            time.sleep(0.05)
            win._poll_events()
            if win.result_view.isVisible():
                break

        assert win.result_view.isVisible() is True
        assert win.lbl_status.text() == "执行成功"
    finally:
        win.close()


def test_real_gui_check_dependencies(qapp, real_service):
    """Test non-destructive dependency check in desktop GUI against real AppService."""
    win = MainWindow(service=real_service)
    win.show()
    try:
        # Select env.check_dependencies
        win._select_operation_by_id("env.check_dependencies")
        assert win.active_operation is not None
        assert win.active_operation.id == "env.check_dependencies"

        # Execute
        win.btn_execute.click()

        for _ in range(50):
            time.sleep(0.05)
            win._poll_events()
            if win.result_view.isVisible():
                break

        assert win.result_view.isVisible() is True
        assert win.lbl_status.text() == "执行成功"
    finally:
        win.close()


def test_real_gui_ctds_interaction_and_completion(qapp, real_service, monkeypatch):
    """Test CTDS conversion flow in desktop GUI with real AppService and interaction confirmation."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        source = Path(tmp_dir) / "ctds"
        obj_train_data = source / "obj_train_data"
        obj_train_data.mkdir(parents=True)
        (source / "obj.names").write_text("car\n", encoding="utf-8")
        (obj_train_data / "sample.txt").write_text(
            "0 0.5 0.5 0.2 0.2\n", encoding="utf-8"
        )
        (obj_train_data / "sample.jpg").write_text("img", encoding="utf-8")

        win = MainWindow(service=real_service)
        win.show()
        try:
            win._select_operation_by_id("yolo.ctds_to_yolo")
            assert win.active_operation.id == "yolo.ctds_to_yolo"

            # Populate form
            win.current_form.widgets["dataset_path"].line_edit.setText(str(source))
            win.current_form.widgets["output_name"].setText("demo_out")

            # Mock the modal interaction dialog execution to auto-accept with confirmation
            def mock_handle_interaction(task_id: str, request) -> None:
                real_service.respond(task_id, request.id, {"confirmed": True})

            monkeypatch.setattr(win, "_handle_interaction", mock_handle_interaction)

            # Trigger execution
            win.btn_execute.click()

            # Wait and poll for completion
            for _ in range(80):
                time.sleep(0.05)
                win._poll_events()
                if win.result_view.isVisible():
                    break

            assert win.result_view.isVisible() is True
            assert win.lbl_status.text() == "执行成功"
        finally:
            win.close()


@pytest.mark.asyncio
async def test_real_tui_config_view(real_service):
    """Test viewing config in TUI against real AppService."""
    app = TuiApp(service=real_service)
    async with app.run_test() as pilot:
        cfg_op = next(
            o for o in real_service.list_operations() if o.id == "config.view"
        )
        app._load_operation_details(cfg_op)

        app._on_btn_run()

        # Poll loop
        for _ in range(50):
            await pilot.pause(0.05)
            app._poll_events()
            if app.query_one("#result_panel").styles.display != "none":
                break

        status_lbl = app.query_one("#lbl_status", Label)
        assert "执行成功" in str(status_lbl.render())
