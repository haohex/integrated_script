# -*- coding: utf-8 -*-
"""Regression tests verifying UI overflow boundaries, search auto-selection, and shortcut integrity."""

from __future__ import annotations

import tempfile
import time
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


def test_main_window_screen_adaptation_simulated_scales(qapp):
    """Regression test: verify MainWindow adapts to simulated 1024x768 screens at 100/125/150/175/200% scaling.

    Tests startup, compact mode, and result view states under clamped available geometry.
    Ensures primary action button is usable, forms/results scrollable, and window frame fits within screen.
    """
    from PySide6.QtCore import QRect

    from integrated_script.contracts.results import OperationResult

    # (scale, avail_width, avail_height)
    simulated_screens = [
        (1.0, 1024, 728),
        (1.25, 819, 582),
        (1.5, 683, 485),
        (1.75, 585, 416),
        (2.0, 512, 364),
    ]

    with tempfile.TemporaryDirectory() as td:
        cfg = ConfigManager(config_file=Path(td) / "c.json", auto_save=False)
        srv = AppService(cfg, working_directory=Path(td))
        try:
            win = MainWindow(service=srv)
            win.show()
            qapp.processEvents()

            tolerance = 2
            for scale, aw, ah in simulated_screens:
                avail_rect = QRect(0, 0, aw, ah)

                # State 1: Startup (Initial operation loaded)
                win._toggle_compact(False)
                win._clamp_to_screen(1200, 780, avail_override=avail_rect)
                qapp.processEvents()

                frame = win.frameGeometry()
                assert frame.left() >= avail_rect.left() - tolerance
                assert frame.top() >= avail_rect.top() - tolerance
                assert frame.right() <= avail_rect.right() + tolerance
                assert frame.bottom() <= avail_rect.bottom() + tolerance
                assert frame.width() <= avail_rect.width() + 2 * tolerance
                assert frame.height() <= avail_rect.height() + 2 * tolerance

                assert win.btn_execute.isVisible() and win.btn_execute.isEnabled()
                assert win.form_scroll.isVisible()
                assert win.nav_tree.isVisible()

                # State 2: Compact mode
                win._toggle_compact(True)
                win._clamp_to_screen(980, 600, avail_override=avail_rect)
                qapp.processEvents()

                frame_compact = win.frameGeometry()
                assert frame_compact.left() >= avail_rect.left() - tolerance
                assert frame_compact.top() >= avail_rect.top() - tolerance
                assert frame_compact.right() <= avail_rect.right() + tolerance
                assert frame_compact.bottom() <= avail_rect.bottom() + tolerance
                assert win.btn_execute.isVisible() and win.btn_execute.isEnabled()
                assert win.form_scroll.isVisible()

                # State 3: Result state (ResultView populated and displayed)
                mock_result = OperationResult(
                    success=True,
                    message="模拟完成",
                    payload={"processed_count": 10, "details": "测试"},
                )
                win.result_view.show_result(mock_result)
                win.result_view.setVisible(True)
                win.exec_panel.setVisible(False)
                win._clamp_to_screen(1200, 780, avail_override=avail_rect)
                qapp.processEvents()

                frame_result = win.frameGeometry()
                assert frame_result.left() >= avail_rect.left() - tolerance
                assert frame_result.top() >= avail_rect.top() - tolerance
                assert frame_result.right() <= avail_rect.right() + tolerance
                assert frame_result.bottom() <= avail_rect.bottom() + tolerance
                assert win.result_view.isVisible()
                assert win.result_view.btn_view_logs.isVisible()
                assert win.result_view.tabs.count() == 4
                assert win.result_view.tabs.tabText(3) == "执行日志"
                assert win.btn_execute.isVisible() and win.btn_execute.isEnabled()

                # Verify log tab focus in bounded screen does not clip or overflow
                win.result_view.btn_view_logs.click()
                qapp.processEvents()
                assert (
                    win.result_view.tabs.currentWidget()
                    == win.result_view.log_container
                )
                assert win.btn_execute.isVisible() and win.btn_execute.isEnabled()

                # Reset result view visibility for next iteration
                win.result_view.setVisible(False)

            win.close()
        finally:
            srv.close()


def test_client_348_real_app_service_and_result_scroll_lifecycle(qapp):
    """Regression test: client 512x348 with real AppService in completed/failed states.

    Verifies:
    1. Vertical space allocation giving result_view unclipped height.
    2. Result content scroll container allows browsing full table/log/payload.
    3. btn_toggle_params restores parameters and collapses back.
    4. Action buttons (execute, reset, copy) remain usable and unclipped.
    """
    from PIL import Image
    from PySide6.QtCore import QRect

    with tempfile.TemporaryDirectory() as td:
        p_td = Path(td)
        cfg = ConfigManager(config_file=p_td / "c.json", auto_save=False)
        srv = AppService(cfg, working_directory=p_td)
        win = None
        try:
            win = MainWindow(service=srv)
            avail_rect = QRect(0, 0, 512, 364)
            win._clamp_to_screen(512, 348, avail_override=avail_rect)
            win.resize(512, 348)
            win.show()
            qapp.processEvents()

            assert win.width() == 512
            assert win.height() == 348
            assert win.form_scroll.isVisible()
            assert not win.btn_toggle_params.isVisible()

            # Execute real operation: label.create_empty
            img_dir = p_td / "imgs"
            lbl_dir = p_td / "lbls"
            img_dir.mkdir(parents=True, exist_ok=True)
            lbl_dir.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (32, 32), color="red").save(img_dir / "img1.jpg", "JPEG")

            win._select_operation_by_id("label.create_empty")
            win.current_form.widgets["images_dir"].set_path(str(img_dir))
            win.current_form.widgets["labels_dir"].set_path(str(lbl_dir))

            win.btn_execute.click()
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                win._poll_events()
                qapp.processEvents()
                if not srv.busy and win.result_view.isVisible():
                    break
                time.sleep(0.01)

            assert not srv.busy, "AppService was still busy after 5.0s timeout"
            assert (
                win.result_view.isVisible()
            ), "result_view was not visible after 5.0s timeout"

            # 1. Result State Verification in 512x348
            assert win.result_view.isVisible()
            assert not win.form_scroll.isVisible()
            assert win.btn_toggle_params.isVisible()
            assert win.btn_toggle_params.text() == "展开参数"
            assert win.btn_execute.isVisible() and win.btn_execute.isEnabled()
            assert win.btn_reset.isVisible()

            # Verify real operation output: empty label file exists and is empty
            expected_lbl = lbl_dir / "img1.txt"
            assert expected_lbl.exists()
            assert expected_lbl.read_text(encoding="utf-8") == ""

            # Clipping check: result_view must NOT be clipped
            rv = win.result_view
            assert rv.size().width() >= rv.minimumSizeHint().width() - 2
            assert rv.size().height() >= rv.minimumSizeHint().height() - 2
            assert rv.scroll_area is not None
            assert rv.scroll_area.isVisible()

            # 2. Log entry and copying
            rv.btn_view_logs.click()
            qapp.processEvents()
            assert rv.tabs.currentWidget() == rv.log_container
            assert rv.btn_copy_log.isVisible() and rv.btn_copy_log.isEnabled()

            # 3. Parameters restoration & re-collapse
            win.btn_toggle_params.click()
            qapp.processEvents()
            assert win.form_scroll.isVisible()
            assert win.btn_toggle_params.text() == "收起参数"
            # Form values remain intact
            assert win.current_form.widgets["images_dir"].get_path() == str(img_dir)

            win.btn_toggle_params.click()
            qapp.processEvents()
            assert not win.form_scroll.isVisible()
            assert win.btn_toggle_params.text() == "展开参数"

            win.close()
        finally:
            if srv is not None:
                drain_deadline = time.monotonic() + 5.0
                while srv.busy and time.monotonic() < drain_deadline:
                    if win is not None:
                        win._poll_events()
                    qapp.processEvents()
                    time.sleep(0.01)
            if win is not None:
                win.close()
                qapp.processEvents()
            if srv is not None:
                srv.close()


def test_log_viewer_dialog_screen_containment_and_margins(qapp):
    """Regression test: LogViewerDialog adapts to 512x364 screen containment with native frames."""
    from PySide6.QtCore import QRect

    from integrated_script.ui.desktop.widgets.result_view import LogViewerDialog

    sample_logs = (
        "[INFO] Pipeline starting...\n[DEBUG] Processing item 1\n[SUCCESS] Completed."
    )
    dlg = LogViewerDialog(sample_logs)
    avail_rect = QRect(0, 0, 512, 364)
    dlg._clamp_to_screen(680, 440, avail_override=avail_rect)
    dlg.show()
    qapp.processEvents()

    fg = dlg.frameGeometry()
    tolerance = 2
    assert fg.left() >= avail_rect.left() - tolerance
    assert fg.top() >= avail_rect.top() - tolerance
    assert fg.right() <= avail_rect.right() + tolerance
    assert fg.bottom() <= avail_rect.bottom() + tolerance
    assert fg.width() <= avail_rect.width() + 2 * tolerance
    assert fg.height() <= avail_rect.height() + 2 * tolerance

    assert dlg.btn_copy.isVisible() and dlg.btn_copy.isEnabled()
    assert dlg.log_view.toPlainText() == sample_logs
    dlg.accept()


def test_result_view_windows_long_path_viewport_containment_and_zero_hscroll(qapp):
    """Verify ResultView with authentic Windows long paths (unbroken tokens + Chinese):
    1. At standard result width 700 and small screen width 326 / height 120:
       - scroll_area.horizontalScrollBar().maximum() == 0 (no horizontal scrolling).
       - Banner and '查看日志' (btn_view_logs) remain fully inside the viewport width.
       - Vertical scrolling is enabled (verticalScrollBar().maximum() > 0 on small heights).
    2. All payload data remains accessible in structured tree and JSON views.
    """
    import json

    from integrated_script.contracts.results import OperationResult

    rv = ResultView()
    win_img_dir = r"C:\Users\runneradmin\AppData\Local\Temp\integ_smoke_a1b2c3d4e5f6\测试图像目录_无空格长路径样本集"
    win_lbl_dir = r"C:\Users\runneradmin\AppData\Local\Temp\integ_smoke_a1b2c3d4e5f6\输出标签目录_无空格长路径样本集"

    long_payload = {
        "images_dir": win_img_dir,
        "labels_dir": win_lbl_dir,
        "created_labels": [
            {
                "success": True,
                "action": "created",
                "image_file": win_img_dir + r"\样本图片_01_无空格长路径样本.jpg",
                "label_file": win_lbl_dir + r"\样本标签_01_无空格长路径样本.txt",
            },
            {
                "success": True,
                "action": "created",
                "image_file": win_img_dir + r"\样本图片_02_无空格长路径样本.jpg",
                "label_file": win_lbl_dir + r"\样本标签_02_无空格长路径样本.txt",
            },
        ],
        "statistics": {
            "total_images": 2,
            "created_count": 2,
            "skipped_count": 0,
            "failed_count": 0,
        },
    }

    op_result = OperationResult(
        success=True,
        message="空白标签创建完成，无空格长路径已顺利处理。",
        payload=long_payload,
    )
    rv.set_result(
        op_result, logs="[INFO] 正在处理样本...\n[SUCCESS] 全部2个标签创建完成。"
    )
    rv.show()
    qapp.processEvents()

    test_geometries = [(700, 500), (326, 120)]
    for target_w, target_h in test_geometries:
        rv.resize(target_w, target_h)
        qapp.processEvents()

        vp_width = rv.scroll_area.viewport().width()
        hbar = rv.scroll_area.horizontalScrollBar()
        vbar = rv.scroll_area.verticalScrollBar()

        # 1. No horizontal scrolling anywhere in ResultView
        assert (
            hbar.maximum() == 0
        ), f"Horizontal scrollbar maximum is {hbar.maximum()} (expected 0) at {target_w}x{target_h}"

        # 2. Banner and '查看日志' button inside viewport width
        btn_top_right = rv.btn_view_logs.mapTo(
            rv.scroll_area.viewport(), rv.btn_view_logs.rect().topRight()
        )
        assert (
            btn_top_right.x() <= vp_width
        ), f"'查看日志' right edge ({btn_top_right.x()}) exceeded viewport width ({vp_width}) at {target_w}x{target_h}"

        # 3. Vertical scrollability preserved on small height
        if target_h <= 120:
            assert (
                vbar.maximum() > 0
            ), "Expected vertical scrollbar to be active for height 120"

    # 4. Payload integrity: all fields accessible in tree and raw JSON
    assert rv.current_payload["images_dir"] == win_img_dir
    assert rv.current_payload["labels_dir"] == win_lbl_dir
    assert len(rv.current_payload["created_labels"]) == 2
    parsed_json = json.loads(rv.json_view.toPlainText())
    assert parsed_json["images_dir"] == win_img_dir
    assert rv.tree_widget.topLevelItemCount() > 0
    assert rv.table_widget.rowCount() == 2

    rv.close()
