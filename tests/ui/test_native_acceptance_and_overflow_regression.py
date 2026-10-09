# -*- coding: utf-8 -*-
"""Regression tests verifying UI overflow boundaries, search auto-selection, and shortcut integrity."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import PropertyMock, patch

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from integrated_script.application import AppService
from integrated_script.config import ConfigManager
from integrated_script.ui.desktop.main_window import MainWindow
from integrated_script.ui.desktop.widgets.result_view import ResultView


def test_result_view_minimum_size_hint_bounded(qapp):
    """Test that ResultView minimumSizeHint remains bounded when loaded with long-path payloads."""
    rv = ResultView()
    long_payload = {
        "images_dir": (
            "/very/long/deeply/nested/directory/structure/path/that/used/to/overflow/"
            "all/the/screens/and/break/layout/images"
        ),
        "labels_dir": (
            "/very/long/deeply/nested/directory/structure/path/that/used/to/overflow/"
            "all/the/screens/and/break/layout/labels"
        ),
        "created_labels": [
            {
                "success": True,
                "action": "created",
                "image_file": (
                    "/long/path/with/spaces/and/chinese/chars/"
                    "样本 01_long_image_file_name_overflow_check.jpg"
                ),
                "label_file": (
                    "/long/path/with/spaces/and/chinese/chars/"
                    "样本 01_long_label_file_name_overflow_check.txt"
                ),
            }
            for _ in range(5)
        ],
        "statistics": {
            "total_images": 5,
            "created_count": 5,
            "skipped_count": 0,
            "failed_count": 0,
            "very_long_metric_description_key_to_test_wrap": 9999,
        },
    }
    rv.set_result({"success": True, "message": "执行成功", "payload": long_payload})
    rv.show()
    qapp.processEvents()

    # Minimum size hint must remain bounded below 500px so it never blows out MainWindow width
    min_hint = rv.minimumSizeHint()
    assert (
        min_hint.width() <= 500
    ), f"ResultView minimum width hint exceeded boundary: {min_hint.width()}"
    assert (
        min_hint.height() <= 300
    ), f"ResultView minimum height hint exceeded boundary: {min_hint.height()}"
    rv.close()


def test_search_auto_selects_first_matching_operation(qapp):
    """Test that typing query into search bar automatically selects first matched operation and loads its form."""
    with tempfile.TemporaryDirectory() as td:
        cfg = ConfigManager(config_file=Path(td) / "c.json", auto_save=False)
        srv = AppService(cfg, working_directory=Path(td))
        try:
            win = MainWindow(service=srv)
            win.show()
            qapp.processEvents()

            # Initially active operation is the first category's first item
            assert win.active_operation is not None

            # Filter with specific query
            win.search_input.setText("label.create_empty")
            qapp.processEvents()

            assert win.active_operation is not None
            assert win.active_operation.id == "label.create_empty"
            assert win.current_form is not None
            assert "images_dir" in win.current_form.widgets
            assert "labels_dir" in win.current_form.widgets

            # Filter with Chinese query
            win.search_input.setText("依赖")
            qapp.processEvents()

            assert win.active_operation is not None
            assert (
                "env.check_dependencies" in win.active_operation.id
                or "env." in win.active_operation.id
            )

            win.close()
        finally:
            srv.close()


def test_main_window_execute_button_has_shortcut(qapp):
    """Test that primary execute button provides Ctrl+Return shortcut for accessible keyboard flow."""
    with tempfile.TemporaryDirectory() as td:
        cfg = ConfigManager(config_file=Path(td) / "c.json", auto_save=False)
        srv = AppService(cfg, working_directory=Path(td))
        try:
            win = MainWindow(service=srv)
            shortcut = win.btn_execute.shortcut().toString()
            assert shortcut.lower() in (
                "ctrl+return",
                "ctrl+enter",
            ), f"Expected Ctrl+Return, got '{shortcut}'"
            win.close()
        finally:
            srv.close()


def test_nav_tree_enter_key_selection_and_busy_protection(qapp):
    """Regression test: Key_Return on nav_tree activates operation, while busy state protects active form."""
    with tempfile.TemporaryDirectory() as td:
        cfg = ConfigManager(config_file=Path(td) / "c.json", auto_save=False)
        srv = AppService(cfg, working_directory=Path(td))
        try:
            win = MainWindow(service=srv)
            win.show()
            qapp.processEvents()

            target_item = None
            for i in range(win.nav_tree.topLevelItemCount()):
                cat = win.nav_tree.topLevelItem(i)
                for j in range(cat.childCount()):
                    child = cat.child(j)
                    if child.data(0, Qt.ItemDataRole.UserRole) == "label.create_empty":
                        target_item = child
                        break
                if target_item:
                    break

            assert target_item is not None
            win.nav_tree.setCurrentItem(target_item)
            win.nav_tree.setFocus()
            QTest.keyClick(win.nav_tree, Qt.Key.Key_Return)
            qapp.processEvents()

            assert win.active_operation is not None
            assert win.active_operation.id == "label.create_empty"
            current_op_id = win.active_operation.id

            # When service becomes busy, switching operation must be ignored
            with patch.object(
                AppService, "busy", new_callable=PropertyMock, return_value=True
            ):
                win.search_input.setText("clean_unmatched")
                qapp.processEvents()
                assert win.active_operation.id == current_op_id

                for i in range(win.nav_tree.topLevelItemCount()):
                    cat = win.nav_tree.topLevelItem(i)
                    for j in range(cat.childCount()):
                        child = cat.child(j)
                        if (
                            child.data(0, Qt.ItemDataRole.UserRole)
                            == "yolo.clean_unmatched"
                        ):
                            win.nav_tree.setCurrentItem(child)
                            QTest.keyClick(win.nav_tree, Qt.Key.Key_Return)
                            win._on_nav_item_clicked(child, 0)
                            break

                qapp.processEvents()
                assert win.active_operation.id == current_op_id

            win.close()
        finally:
            srv.close()
