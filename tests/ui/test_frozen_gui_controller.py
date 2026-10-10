#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests and regression test cases for frozen GUI smoke test controller logic.

Covers:
1. Difference between WindowSpecification (.exists()) and resolved wrappers (e.g. EditWrapper without .exists()).
2. Window filtering: selecting authentic visible main windows and ignoring Qt hidden helper windows.
3. Win32 ctypes 64-bit API signatures configuration.
4. Safe text setting and button clicking with fallbacks.
5. Windows automation execution with both child_window and descendants fallback paths.
6. Clean window closing via pywinauto close and 64-bit PostMessageW WM_CLOSE.
"""

from __future__ import annotations

import ctypes
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tests.ui.frozen_gui_smoke import (
    click_control,
    close_windows_application,
    is_control_existing,
    is_same_control,
    run_windows_automation,
    select_primary_windows,
    set_control_text,
    setup_win32_ctypes_signatures,
)


class StubWindowSpecification:
    """Simulates pywinauto.application.WindowSpecification."""

    def __init__(self, exists_result: bool = True, raise_on_exists: bool = False):
        self._exists_result = exists_result
        self._raise_on_exists = raise_on_exists
        self.text_set: str | None = None
        self.typed_keys: str | None = None
        self.clicked = False

    def exists(self, timeout: float = 2.0) -> bool:
        if self._raise_on_exists:
            raise RuntimeError("Specification lookup timeout")
        return self._exists_result

    def set_edit_text(self, text: str) -> None:
        self.text_set = text

    def type_keys(self, keys: str, with_spaces: bool = False) -> None:
        self.typed_keys = keys

    def click(self) -> None:
        self.clicked = True


class StubEditWrapper:
    """Simulates pywinauto.controls.uiawrapper.UIAWrapper / EditWrapper.

    Crucially, resolved wrappers DO NOT possess an .exists() method!
    """

    def __init__(self, handle: int = 1001):
        self.handle = handle
        self.text_set: str | None = None
        self.typed_keys: str | None = None

    def set_edit_text(self, text: str) -> None:
        self.text_set = text

    def type_keys(self, keys: str, with_spaces: bool = False) -> None:
        self.typed_keys = keys


class StubButtonWrapper:
    """Simulates resolved button wrapper (no .exists())."""

    def __init__(self, title: str = "开始执行", handle: int = 2001):
        self.title = title
        self.handle = handle
        self.clicked = False

    def window_text(self) -> str:
        return self.title

    def click(self) -> None:
        self.clicked = True


@pytest.mark.parametrize("handle", [0, 1234])
def test_virtual_controls_use_uia_identity_instead_of_shared_hwnd(handle):
    search = SimpleNamespace(
        handle=handle, element_info=SimpleNamespace(runtime_id=(1, 2))
    )
    image_input = SimpleNamespace(
        handle=handle, element_info=SimpleNamespace(runtime_id=(1, 3))
    )
    search_again = SimpleNamespace(
        handle=handle, element_info=SimpleNamespace(runtime_id=(1, 2))
    )
    assert not is_same_control(search, image_input)
    assert is_same_control(search, search_again)


# --- 1. Element Existence and Type Compatibility ---


def test_is_control_existing_with_window_specification() -> None:
    spec_true = StubWindowSpecification(exists_result=True)
    assert is_control_existing(spec_true, timeout=1.0) is True

    spec_false = StubWindowSpecification(exists_result=False)
    assert is_control_existing(spec_false, timeout=1.0) is False

    spec_error = StubWindowSpecification(raise_on_exists=True)
    assert is_control_existing(spec_error, timeout=1.0) is False


def test_is_control_existing_with_resolved_wrapper() -> None:
    wrapper = StubEditWrapper(handle=123)
    # Must NOT raise AttributeError: 'EditWrapper' object has no attribute 'exists'
    assert not hasattr(wrapper, "exists")
    assert is_control_existing(wrapper) is True
    assert is_control_existing(None) is False


# --- 2. Safe Text Setting and Button Clicking ---


def test_set_control_text_prefer_type_keys() -> None:
    wrapper = StubEditWrapper()
    ok = set_control_text(wrapper, "创建空标签", prefer_type_keys=True)
    assert ok is True
    assert wrapper.typed_keys == "创建空标签"
    assert wrapper.text_set is None


def test_set_control_text_prefer_set_edit_text() -> None:
    wrapper = StubEditWrapper()
    path_text = r"D:\test\data dir"
    ok = set_control_text(wrapper, path_text, prefer_type_keys=False)
    assert ok is True
    assert wrapper.text_set == path_text
    assert wrapper.typed_keys is None


def test_set_control_text_fallback_on_failure() -> None:
    mock_ctrl = MagicMock()
    mock_ctrl.set_edit_text.side_effect = RuntimeError("Value pattern unsupported")
    mock_ctrl.set_text.side_effect = AttributeError("No set_text")

    ok = set_control_text(mock_ctrl, "sample text", prefer_type_keys=False)
    assert ok is True
    mock_ctrl.type_keys.assert_called_once_with("sample text", with_spaces=True)


def test_click_control_success_and_fallback() -> None:
    # 1. Direct click
    btn1 = StubButtonWrapper()
    assert click_control(btn1) is True
    assert btn1.clicked is True

    # 2. Fallback to click_input when click fails
    mock_btn = MagicMock(spec=["click", "click_input"])
    mock_btn.click.side_effect = RuntimeError("Standard click failed")
    assert click_control(mock_btn) is True
    mock_btn.click_input.assert_called_once()

    # 3. None control
    assert click_control(None) is False


# --- 3. Control Identity Comparison ---


def test_is_same_control() -> None:
    e1 = StubEditWrapper(handle=100)
    e2 = StubEditWrapper(handle=100)
    e3 = StubEditWrapper(handle=200)

    assert is_same_control(e1, e1) is True
    assert is_same_control(e1, e2) is True
    assert is_same_control(e1, e3) is False
    assert is_same_control(e1, None) is False


# --- 4. Main Window Selection ---


def test_select_primary_windows_filters_helper_and_console() -> None:
    windows = [
        # Qt invisible helper window
        {
            "hwnd": 1001,
            "title": "",
            "class_name": "QEventDispatcherWin32_Internal_Widget",
            "visible": False,
        },
        # Windows console host leaked
        {
            "hwnd": 1002,
            "title": "C:\\Windows\\System32\\cmd.exe",
            "class_name": "ConsoleWindowClass",
            "visible": True,
        },
        # Another invisible message window
        {
            "hwnd": 1003,
            "title": "Qt6QWindowIcon",
            "class_name": "Qt6QWindowIcon",
            "visible": False,
        },
        # Authentic visible main application window
        {
            "hwnd": 1004,
            "title": "集成脚本工具",
            "class_name": "Qt663QWindowIcon",
            "visible": True,
        },
    ]

    selected = select_primary_windows(windows)
    assert len(selected) == 1
    assert selected[0]["hwnd"] == 1004
    assert selected[0]["title"] == "集成脚本工具"
    assert selected[0]["visible"] is True


def test_select_primary_windows_fallbacks() -> None:
    # Fallback when title does not match exactly, but is visible Qt window
    qt_windows = [
        {
            "hwnd": 2001,
            "title": "",
            "class_name": "QEventDispatcherWin32_Internal_Widget",
            "visible": False,
        },
        {
            "hwnd": 2002,
            "title": "My Qt App",
            "class_name": "QtWindow",
            "visible": True,
        },
    ]
    selected = select_primary_windows(qt_windows)
    assert len(selected) == 1
    assert selected[0]["hwnd"] == 2002


# --- 5. Win32 ctypes 64-bit Signatures ---


def test_setup_win32_ctypes_signatures() -> None:
    mock_user32 = MagicMock()
    mock_kernel32 = MagicMock()

    setup_win32_ctypes_signatures(mock_user32, mock_kernel32)

    # Verify PostMessageW 64-bit signatures
    assert hasattr(mock_user32.PostMessageW, "argtypes")
    assert len(mock_user32.PostMessageW.argtypes) == 4
    assert hasattr(mock_user32.PostMessageW, "restype")

    # Verify EnumWindows signatures
    assert hasattr(mock_user32.EnumWindows, "argtypes")
    assert len(mock_user32.EnumWindows.argtypes) == 2
    assert hasattr(mock_user32.EnumWindows, "restype")

    # Verify GetCurrentThreadId
    assert hasattr(mock_kernel32.GetCurrentThreadId, "argtypes")
    assert mock_kernel32.GetCurrentThreadId.argtypes == []
    assert hasattr(mock_kernel32.GetCurrentThreadId, "restype")


# --- 6. Windows Automation Execution (child_window vs descendants fallback) ---


def test_run_windows_automation_with_child_window_success() -> None:
    mock_main_dlg = MagicMock()

    search_spec = StubWindowSpecification(exists_result=True)
    img_spec = StubWindowSpecification(exists_result=True)
    lbl_spec = StubWindowSpecification(exists_result=True)
    btn_spec = StubWindowSpecification(exists_result=True)

    def child_window_side_effect(**kwargs: Any) -> Any:
        if kwargs.get("auto_id") == "search_input":
            return search_spec
        if kwargs.get("auto_id") == "images_dir":
            return img_spec
        if kwargs.get("auto_id") == "labels_dir":
            return lbl_spec
        if kwargs.get("title") == "开始执行":
            return btn_spec
        return StubWindowSpecification(exists_result=False)

    mock_main_dlg.child_window.side_effect = child_window_side_effect

    in_path = Path("/tmp/mock_input")
    out_path = Path("/tmp/mock_output")

    with patch("time.sleep"):
        performed, err = run_windows_automation(
            app_ctrl=MagicMock(),
            main_dlg=mock_main_dlg,
            input_imgs=in_path,
            output_lbls=out_path,
        )

    assert performed is True
    assert err is None
    assert search_spec.typed_keys == "创建空标签"
    assert img_spec.text_set == str(in_path)
    assert lbl_spec.text_set == str(out_path)
    assert btn_spec.clicked is True


def test_run_windows_automation_with_descendants_fallback_no_crash() -> None:
    """Key regression test: descendants returns EditWrapper which has NO .exists().

    Must NOT crash with AttributeError: 'EditWrapper' object has no attribute 'exists'.
    """
    mock_main_dlg = MagicMock()

    # All child_window lookups fail (exists() -> False)
    mock_main_dlg.child_window.return_value = StubWindowSpecification(
        exists_result=False
    )

    # descendants returns actual resolved wrappers (WITHOUT exists() method)
    search_wrapper = StubEditWrapper(handle=501)
    img_wrapper = StubEditWrapper(handle=502)
    lbl_wrapper = StubEditWrapper(handle=503)
    btn_wrapper = StubButtonWrapper(title="开始执行", handle=601)

    mock_main_dlg.descendants.side_effect = lambda control_type: (
        [search_wrapper, img_wrapper, lbl_wrapper]
        if control_type == "Edit"
        else [btn_wrapper]
    )

    in_path = Path("/tmp/test_imgs")
    out_path = Path("/tmp/test_lbls")

    with patch("time.sleep"):
        performed, err = run_windows_automation(
            app_ctrl=MagicMock(),
            main_dlg=mock_main_dlg,
            input_imgs=in_path,
            output_lbls=out_path,
        )

    assert performed is True
    assert err is None
    assert search_wrapper.typed_keys == "创建空标签"
    assert img_wrapper.text_set == str(in_path)
    assert lbl_wrapper.text_set == str(out_path)
    assert btn_wrapper.clicked is True


# --- 7. Application Window Close Protocol ---


def test_close_windows_application() -> None:
    mock_main_dlg = MagicMock()
    windows = [
        {"hwnd": 101, "title": "Helper", "class_name": "HelperClass", "visible": False},
        {
            "hwnd": 102,
            "title": "集成脚本工具",
            "class_name": "QtClass",
            "visible": True,
        },
    ]

    mock_proc = MagicMock()
    mock_proc.pid = 9999

    mock_windll = MagicMock()
    mock_user32 = MagicMock()
    mock_windll.user32 = mock_user32

    with (
        patch("tests.ui.frozen_gui_smoke.get_process_tree_pids", return_value=[9999]),
        patch(
            "tests.ui.frozen_gui_smoke.enumerate_windows_for_pid", return_value=windows
        ),
        patch.object(ctypes, "windll", mock_windll, create=True),
    ):
        close_windows_application(proc=mock_proc, wins=windows, main_dlg=mock_main_dlg)

    # 1. pywinauto close is invoked
    mock_main_dlg.close.assert_called_once()
    # 2. PostMessageW WM_CLOSE is sent strictly to visible main window hwnd 102
    mock_user32.PostMessageW.assert_called_once()
    args, _ = mock_user32.PostMessageW.call_args
    # First arg is HWND(102), second arg is 0x0010 (WM_CLOSE)
    assert args[1] == 0x0010
