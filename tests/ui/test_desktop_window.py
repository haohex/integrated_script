# -*- coding: utf-8 -*-
"""Unit tests for desktop MainWindow interactions."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from integrated_script.ui.desktop.main_window import MainWindow


def test_main_window_init_and_categories(qapp, fake_service):
    win = MainWindow(service=fake_service)
    assert win.nav_tree.topLevelItemCount() > 0
    assert win.active_operation is not None
    assert win.lbl_op_title.text() != ""
    win.close()


def test_main_window_search_filter(qapp, fake_service):
    win = MainWindow(service=fake_service)

    # Search for an operation by label keyword
    win.search_input.setText("CTDS")
    # Category containing CTDS should be visible
    cat_items = [
        win.nav_tree.topLevelItem(i) for i in range(win.nav_tree.topLevelItemCount())
    ]
    visible_cats = [c for c in cat_items if not c.isHidden()]
    assert len(visible_cats) >= 1

    # Search for non-existent keyword
    win.search_input.setText("NON_EXISTENT_KEYWORD_XYZ")
    visible_cats_after = [c for c in cat_items if not c.isHidden()]
    assert len(visible_cats_after) == 0

    # Clear filter restores visibility
    win.search_input.setText("")
    visible_restored = [c for c in cat_items if not c.isHidden()]
    assert len(visible_restored) == len(cat_items)
    win.close()


def test_main_window_destructive_operation_banner(qapp, fake_service):
    win = MainWindow(service=fake_service)
    win.show()

    # Select clean_unmatched (destructive)
    win._select_operation_by_id("yolo.clean_unmatched")
    assert win.active_operation.destructive is True
    assert win.lbl_op_destructive.isVisible() is True
    assert win.destructive_banner.isVisible() is True

    # Select validate_detection (non-destructive)
    win._select_operation_by_id("yolo.validate_detection")
    assert win.active_operation.destructive is False
    assert win.lbl_op_destructive.isVisible() is False
    assert win.destructive_banner.isVisible() is False
    win.close()


def test_main_window_execution_and_result(qapp, fake_service):
    win = MainWindow(service=fake_service)
    win.show()

    win._select_operation_by_id("yolo.validate_detection")
    assert win.btn_execute.isEnabled() is True

    # Fill required field
    win.current_form.widgets["dataset_path"].line_edit.setText("/tmp/test_dataset")

    # Click execute
    win.btn_execute.click()

    # Poll service events
    win._poll_events()

    # ResultView should now be displayed
    assert win.result_view.isVisible() is True
    assert win.lbl_status.text() == "执行成功"
    win.close()


def test_main_window_compact_mode_toggle(qapp, fake_service):
    win = MainWindow(service=fake_service)

    win.btn_compact.setChecked(True)
    win._toggle_compact()
    assert win.width() <= 980
    assert win.height() <= 600

    win.btn_compact.setChecked(False)
    win._toggle_compact()
    assert win.width() <= 1200
    assert win.height() <= 780
    win.close()


def test_main_window_close_event_safety(qapp, fake_service):
    win = MainWindow(service=fake_service)
    win.show()

    # When service is busy, closeEvent should be ignored
    fake_service._busy = True
    win.close()
    assert win.isVisible() is True

    # When service is idle, closeEvent should accept
    fake_service._busy = False
    win.close()
    assert win.isVisible() is False


def test_main_window_theme_options_and_nav_tree_style(qapp, fake_service):
    win = MainWindow(service=fake_service)
    # Check theme combo options
    combo_texts = [win.theme_combo.itemText(i) for i in range(win.theme_combo.count())]
    assert combo_texts == ["跟随系统", "浅色", "深色"]

    # Check QSS continuous selection rule for QTreeWidget
    from integrated_script.ui.desktop.styles import generate_qss

    qss_light = generate_qss("light")
    assert "show-decoration-selected: 1;" in qss_light
    assert "QTreeWidget::branch:selected" in qss_light
    assert "margin: 0px;" in qss_light
    assert "border-radius: 0px;" in qss_light
    win.close()


def test_main_window_keyboard_navigation_enter_activates_leaf(qapp, fake_service):
    """Verify that pressing Return/Enter on a nav_tree leaf item activates and loads the operation."""
    win = MainWindow(service=fake_service)
    win.show()

    # Find the clean_unmatched item in tree
    target_item = None
    for i in range(win.nav_tree.topLevelItemCount()):
        cat = win.nav_tree.topLevelItem(i)
        for j in range(cat.childCount()):
            child = cat.child(j)
            if child.data(0, Qt.ItemDataRole.UserRole) == "yolo.clean_unmatched":
                target_item = child
                break
        if target_item:
            break

    assert target_item is not None
    # Set current item and focus tree
    win.nav_tree.setCurrentItem(target_item)
    win.nav_tree.setFocus()

    # Real QTest key click on tree widget
    QTest.keyClick(win.nav_tree, Qt.Key.Key_Return)
    qapp.processEvents()

    assert win.active_operation is not None
    assert win.active_operation.id == "yolo.clean_unmatched"
    assert win.lbl_op_title.text() == win.active_operation.label
    win.close()


def test_main_window_busy_state_protects_active_operation(qapp, fake_service):
    """Verify search auto-selection and tree item activation do NOT overwrite form when busy."""
    win = MainWindow(service=fake_service)
    win.show()

    win._select_operation_by_id("yolo.validate_detection")
    orig_op = win.active_operation
    assert orig_op is not None and orig_op.id == "yolo.validate_detection"

    # Set service to busy
    fake_service._busy = True

    # Attempt search filter that matches another operation
    win.search_input.setText("clean_unmatched")
    qapp.processEvents()
    # Active operation must remain untouched
    assert win.active_operation.id == orig_op.id

    # Attempt tree click/activation
    for i in range(win.nav_tree.topLevelItemCount()):
        cat = win.nav_tree.topLevelItem(i)
        for j in range(cat.childCount()):
            child = cat.child(j)
            if child.data(0, Qt.ItemDataRole.UserRole) == "yolo.clean_unmatched":
                win.nav_tree.setCurrentItem(child)
                QTest.keyClick(win.nav_tree, Qt.Key.Key_Return)
                win._on_nav_item_clicked(child, 0)
                break

    qapp.processEvents()
    assert win.active_operation.id == orig_op.id

    fake_service._busy = False
    win.close()


def test_main_window_execution_logs_lifecycle_and_isolation(qapp, fake_service):
    """Verify execution logs lifecycle: accessible in ResultView, isolated across runs, switching on failure."""
    from integrated_script.contracts.results import OperationResult
    from integrated_script.ui.shared.contract import TaskEvent

    win = MainWindow(service=fake_service)
    win.show()
    qapp.processEvents()

    win._select_operation_by_id("yolo.validate_detection")
    win.current_form.widgets["dataset_path"].line_edit.setText("/tmp/test_dataset")

    # 1. Run 1: Emit logs and complete
    task_id_1 = "task_001"
    win.active_task_id = task_id_1
    win.exec_panel.setVisible(True)
    win.result_view.setVisible(False)
    win.log_edit.clear()
    win.result_view.clear_logs()

    win._handle_event(
        TaskEvent(
            task_id=task_id_1, kind="log", message="[Run 1] Initializing pipeline..."
        )
    )
    win._handle_event(
        TaskEvent(
            task_id=task_id_1, kind="log", message="[Run 1] Processing batch 1..."
        )
    )
    res_1 = OperationResult(success=True, message="Run 1 完成", payload={"count": 10})
    win._handle_event(TaskEvent(task_id=task_id_1, kind="completed", result=res_1))
    qapp.processEvents()

    assert not win.exec_panel.isVisible()
    assert win.result_view.isVisible()
    assert "[Run 1] Initializing pipeline..." in win.result_view.get_logs()
    assert "[Run 1] Processing batch 1..." in win.result_view.get_logs()
    assert win.result_view.btn_view_logs.isVisible()

    # Click banner view logs button to switch to log tab
    win.result_view.btn_view_logs.click()
    assert win.result_view.tabs.currentWidget() == win.result_view.log_container

    # 2. Run 2 (Rerun): Ensure logs do NOT leak from Run 1
    task_id_2 = "task_002"
    win.active_task_id = task_id_2
    # Simulate user clicking execute again
    win.exec_panel.setVisible(True)
    win.result_view.setVisible(False)
    win.log_edit.clear()
    win.result_view.clear_logs()

    assert win.result_view.get_logs() == ""
    assert win.log_edit.toPlainText() == ""

    win._handle_event(
        TaskEvent(
            task_id=task_id_2, kind="log", message="[Run 2] Brand new task execution..."
        )
    )
    res_2 = OperationResult(success=True, message="Run 2 完成", payload={"count": 20})
    win._handle_event(TaskEvent(task_id=task_id_2, kind="completed", result=res_2))
    qapp.processEvents()

    assert not win.exec_panel.isVisible()
    assert win.result_view.isVisible()
    assert "[Run 2] Brand new task execution..." in win.result_view.get_logs()
    assert "Run 1" not in win.result_view.get_logs()

    # 3. Run 3: Failure state automatically focuses execution log tab
    task_id_3 = "task_003"
    win.active_task_id = task_id_3
    win.exec_panel.setVisible(True)
    win.result_view.setVisible(False)
    win.log_edit.clear()
    win.result_view.clear_logs()

    win._handle_event(
        TaskEvent(
            task_id=task_id_3,
            kind="log",
            message="[Run 3] Syntax error in file line 42",
        )
    )
    res_3 = OperationResult(
        success=False, message="Run 3 失败", error_code="SYNTAX_ERROR"
    )
    win._handle_event(TaskEvent(task_id=task_id_3, kind="failed", result=res_3))
    qapp.processEvents()

    assert win.lbl_status.text() == "执行失败"
    assert not win.exec_panel.isVisible()
    assert win.result_view.isVisible()
    # On failure, ResultView must automatically switch to execution logs tab
    assert win.result_view.tabs.currentWidget() == win.result_view.log_container
    assert "[Run 3] Syntax error in file line 42" in win.result_view.get_logs()
    assert "Run 2" not in win.result_view.get_logs()

    # 4. Switch operation clears all execution and result views
    win._select_operation_by_id("yolo.clean_unmatched")
    assert not win.exec_panel.isVisible()
    assert not win.result_view.isVisible()
    assert win.result_view.get_logs() == ""
    assert win.log_edit.toPlainText() == ""

    win.close()
