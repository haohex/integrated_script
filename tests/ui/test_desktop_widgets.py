# -*- coding: utf-8 -*-
"""Unit tests for desktop Qt widgets: FormBuilder, PathPicker, ResultView, and InteractionDialog."""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QApplication, QToolButton

from integrated_script.contracts.results import OperationResult
from integrated_script.ui.desktop.widgets.form_builder import (
    FormBuilder,
    NullableBoolEdit,
    NullableNumberEdit,
)
from integrated_script.ui.desktop.widgets.interaction_dialog import (
    InteractionDialog,
)
from integrated_script.ui.desktop.widgets.path_picker import (
    PathPicker,
    PathsEditor,
)
from integrated_script.ui.desktop.widgets.result_view import ResultView
from integrated_script.ui.shared.contract import (
    InteractionRequest,
    ParameterSpec,
)


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_form_builder_all_field_types(qapp):
    fields = (
        ParameterSpec(
            name="str_field",
            label="String Field",
            kind="str",
            default="hello",
            required=True,
        ),
        ParameterSpec(
            name="text_field",
            label="Text Field",
            kind="text",
            default="multiline\ntext",
        ),
        ParameterSpec(
            name="path_field",
            label="Path Field",
            kind="path",
            default="/tmp/test",
        ),
        ParameterSpec(
            name="paths_field",
            label="Paths Field",
            kind="paths",
            default="/tmp/1\n/tmp/2",
        ),
        ParameterSpec(name="int_field", label="Int Field", kind="int", default=42),
        ParameterSpec(
            name="float_field", label="Float Field", kind="float", default=3.14
        ),
        ParameterSpec(name="bool_field", label="Bool Field", kind="bool", default=True),
        ParameterSpec(
            name="choice_field",
            label="Choice Field",
            kind="choice",
            default="opt2",
            choices=(("Option 1", "opt1"), ("Option 2", "opt2")),
        ),
    )

    fb = FormBuilder(fields)
    values = fb.get_values()

    assert values["str_field"] == "hello"
    assert "multiline" in values["text_field"]
    assert values["path_field"] == "/tmp/test"
    assert "/tmp/1" in values["paths_field"]
    assert values["int_field"] == 42
    assert abs(values["float_field"] - 3.14) < 1e-4
    assert values["bool_field"] is True
    assert values["choice_field"] == "opt2"

    # Validation should pass
    assert len(fb.validate()) == 0


def test_form_builder_nullable_defaults_preserved(qapp):
    """Empirical check for FormBuilder nullable preservation: default=None must not become 0 or False."""
    fields = (
        ParameterSpec("n", "保持原值", "int", None),
        ParameterSpec("b", "保持原值", "bool", None),
        ParameterSpec("f", "保持原值", "float", None),
    )
    fb = FormBuilder(fields)
    vals = fb.get_values()
    assert vals == {"n": None, "b": None, "f": None}

    # reset_defaults should also preserve None
    fb.reset_defaults()
    assert fb.get_values() == {"n": None, "b": None, "f": None}


def test_form_builder_nullable_explicit_zero_and_false(qapp):
    """Explicit 0 and False must be accurately conveyed without collapsing to None or default."""
    fields = (
        ParameterSpec("n", "保持原值", "int", None),
        ParameterSpec("b", "保持原值", "bool", None),
        ParameterSpec("f", "保持原值", "float", None),
    )
    fb = FormBuilder(fields)
    widget_n = fb.widgets["n"]
    assert isinstance(widget_n, NullableNumberEdit)
    widget_n.setText("0")

    widget_f = fb.widgets["f"]
    assert isinstance(widget_f, NullableNumberEdit)
    widget_f.setText("0.0")

    widget_b = fb.widgets["b"]
    assert isinstance(widget_b, NullableBoolEdit)
    widget_b.setValue(False)

    vals = fb.get_values()
    assert vals["n"] == 0
    assert vals["f"] == 0.0
    assert vals["b"] is False


def test_form_builder_validation_required(qapp):
    fields = (
        ParameterSpec(
            name="req_str",
            label="Required Str",
            kind="str",
            default="",
            required=True,
        ),
        ParameterSpec(
            name="req_int",
            label="Required Int",
            kind="int",
            default=None,
            required=True,
        ),
    )
    fb = FormBuilder(fields)
    errors = fb.validate()
    assert len(errors) == 2
    assert "必填项" in errors[0]
    assert "必填项" in errors[1]

    # Typing 0 should satisfy required validation
    fb.widgets["req_str"].setText("valid")
    fb.widgets["req_int"].setText("0")
    assert len(fb.validate()) == 0
    assert fb.get_values()["req_int"] == 0


def test_form_builder_reset_defaults(qapp):
    fields = (ParameterSpec(name="num", label="Number", kind="int", default=100),)
    fb = FormBuilder(fields)
    fb.widgets["num"].setValue(999)
    assert fb.get_values()["num"] == 999

    fb.reset_defaults()
    assert fb.get_values()["num"] == 100


def test_path_picker_and_editor(qapp, monkeypatch):
    picker = PathPicker(default='  "/var/log"  ')
    assert picker.get_path() == "/var/log"
    picker.set_path("/etc/hosts")
    assert picker.get_path() == "/etc/hosts"

    # InstantPopup and button text validation
    assert picker.browse_button.text() == "浏览… ▾"
    assert (
        picker.browse_button.popupMode() == QToolButton.ToolButtonPopupMode.InstantPopup
    )
    menu = picker.browse_button.menu()
    assert menu is not None
    actions = menu.actions()
    assert len(actions) == 3
    assert "选择目录" in actions[0].text()
    assert "选择已有文件" in actions[1].text()
    assert "保存文件" in actions[2].text()

    # Trigger directory action
    monkeypatch.setattr(
        "PySide6.QtWidgets.QFileDialog.getExistingDirectory",
        lambda *args, **kwargs: "/custom/dir",
    )
    actions[0].trigger()
    assert picker.get_path() == "/custom/dir"

    editor = PathsEditor(default="/path/a\n/path/b")
    assert editor.get_path_list() == ["/path/a", "/path/b"]


def test_result_view_success_and_failure(qapp):
    rv = ResultView()
    rv.show()

    # Success with rich payload
    res_success = OperationResult(
        success=True,
        message="处理成功完成",
        payload={
            "total_items": 500,
            "processed": 498,
            "items_table": [
                {"name": "file1.jpg", "size": "1.2MB"},
                {"name": "file2.jpg", "size": "3.4MB"},
            ],
            "details": {"sub_key": "sub_value"},
        },
    )
    rv.set_result(res_success)
    assert rv.msg_label.text() == "处理成功完成"
    assert not rv.error_code_badge.isVisible()
    assert rv.table_widget.rowCount() == 2

    # Failure with error code
    res_fail = OperationResult(
        success=False,
        message="文件读取错误",
        error_code="IO_READ_ERROR",
        payload={"file": "missing.txt"},
    )
    rv.set_result(res_fail)
    assert "文件读取错误" in rv.msg_label.text()
    assert rv.error_code_badge.isVisible()
    assert "IO_READ_ERROR" in rv.error_code_badge.text()


def test_interaction_dialog_confirm(qapp):
    req = InteractionRequest(
        id="test_req",
        title="确认测试",
        message="确定要执行操作吗？",
        kind="confirm",
        details=("警告详情 1", "警告详情 2"),
    )
    dlg = InteractionDialog(req)
    dlg._on_confirm()
    assert dlg.response_data == {"confirmed": True}

    dlg._on_cancel()
    assert dlg.response_data == {"confirmed": False}


def test_result_view_execution_logs_and_dialog(qapp):
    from integrated_script.ui.desktop.widgets.result_view import LogViewerDialog

    rv = ResultView()
    rv.show()

    # Initial state: tabs count is 4, tab 3 is execution logs
    assert rv.tabs.count() == 4
    assert rv.tabs.tabText(3) == "执行日志"
    assert rv.btn_view_logs.isVisible()

    # Set logs and test retrieval
    test_logs = (
        "2026-10-09 12:00:00 [INFO] 步骤 1 开始\n2026-10-09 12:00:01 [INFO] 步骤 1 完成"
    )
    rv.set_logs(test_logs)
    assert rv.get_logs() == test_logs
    assert rv.log_view.toPlainText() == test_logs

    # Click banner view logs button -> switches to log tab
    rv.tabs.setCurrentIndex(0)
    assert rv.tabs.currentIndex() == 0
    rv.btn_view_logs.click()
    assert rv.tabs.currentWidget() == rv.log_container

    # Copy log action
    rv._copy_log_to_clipboard()
    cb = QApplication.clipboard()
    if cb:
        assert cb.text() == test_logs

    # Failure automatically switches to log container
    res_fail = OperationResult(
        success=False,
        message="校验失败",
        error_code="VALIDATION_ERROR",
        payload={"reason": "bad format"},
    )
    rv.set_result(res_fail, logs=test_logs)
    assert rv.tabs.currentWidget() == rv.log_container

    # Standalone LogViewerDialog
    dlg = LogViewerDialog(test_logs, parent=rv)
    assert dlg.log_view.toPlainText() == test_logs
    dlg._copy_to_clipboard()
    if cb:
        assert cb.text() == test_logs
    dlg.close()

    # Clear logs
    rv.clear_logs()
    assert rv.get_logs() == ""
    assert rv.log_view.toPlainText() == ""
    rv.close()
