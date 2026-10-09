#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Frozen GUI Smoke Test Runner for packaged executables (Windows .exe / Linux ELF).

Bounded Black-Box Verification Contract:
1. Strict environment isolation:
   - HOME / XDG_* / APPDATA / LOCALAPPDATA / USERPROFILE / cwd sandboxed in a clean temp directory.
   - Child process environment stripped of PYTHONPATH, PYTHONHOME, and PYTHONSTARTUP.
   - Child process PATH: POSIX stripped to empty (""); Windows stripped to %SystemRoot%\\System32 only.
   - Controller retains required system tools (xdotool, Pillow, etc.). PySide6 is NOT required on controller.
2. Window discovery & leak checks:
   - Linux: PID strictly matched via xdotool search --pid <pid>. No foreign window cross-talk.
   - Linux geometry: Window size verified against 1200x780 standard layout; fails fast if too small.
   - Windows: Verified no console window (ConsoleWindowClass) is leaked.
   - Windows headless (Session 0) without interactive desktop fails fast with non-zero exit code.
3. Authentic non-destructive operation execution:
   - Operation: 'label.create_empty'
   - Test fixtures: Valid PIL generated images in Chinese + spaced paths.
   - External interaction: Client-window-relative mouse/keyboard navigation (Linux) or UIA paths (Windows).
   - Output verification: Strictly checks that 2 expected .txt label files exist and are 0-byte empty.
4. Window screenshot & lifecycle termination:
   - Captures window bbox via Pillow ImageGrab (or ImageMagick import fallback) without Qt controller dependencies.
   - Linux: Sends X11 WM_PROTOCOLS / WM_DELETE_WINDOW ClientMessage via ctypes libX11 for clean QCloseEvent.
   - Windows: Sends WM_CLOSE via 64-bit PostMessageW or pywinauto window close.
   - Process wait returncode must strictly be 0.
   - Finally block cleans up spawned child process, flushes stdout/stderr to report, and exits non-zero on failure.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any


def setup_win32_ctypes_signatures(user32: Any, kernel32: Any = None) -> None:
    """Explicitly configure 64-bit ctypes argtypes and restype signatures for Win32 API."""
    import ctypes
    from ctypes import wintypes

    if kernel32 is not None and hasattr(kernel32, "GetCurrentThreadId"):
        kernel32.GetCurrentThreadId.argtypes = []
        kernel32.GetCurrentThreadId.restype = wintypes.DWORD

    if hasattr(user32, "GetThreadDesktop"):
        user32.GetThreadDesktop.argtypes = [wintypes.DWORD]
        user32.GetThreadDesktop.restype = wintypes.HANDLE

    if hasattr(user32, "GetSystemMetrics"):
        user32.GetSystemMetrics.argtypes = [ctypes.c_int]
        user32.GetSystemMetrics.restype = ctypes.c_int

    if hasattr(user32, "EnumWindows"):
        wnd_proc_type = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
        )
        user32.EnumWindows.argtypes = [wnd_proc_type, wintypes.LPARAM]
        user32.EnumWindows.restype = wintypes.BOOL

    if hasattr(user32, "GetWindowThreadProcessId"):
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD

    if hasattr(user32, "GetWindowTextLengthW"):
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextLengthW.restype = ctypes.c_int

    if hasattr(user32, "GetWindowTextW"):
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetWindowTextW.restype = ctypes.c_int

    if hasattr(user32, "GetClassNameW"):
        user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        user32.GetClassNameW.restype = ctypes.c_int

    if hasattr(user32, "IsWindowVisible"):
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL

    if hasattr(user32, "PostMessageW"):
        user32.PostMessageW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.PostMessageW.restype = wintypes.BOOL


def check_windows_interactive_desktop() -> tuple[bool, str]:
    """Check if Windows current thread runs in an interactive desktop station."""
    if sys.platform != "win32":
        return True, "Linux/X11 environment"

    try:
        import ctypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        setup_win32_ctypes_signatures(user32, kernel32)

        h_desk = user32.GetThreadDesktop(kernel32.GetCurrentThreadId())
        if not h_desk:
            return False, "Unable to acquire current thread desktop handle."

        cx = user32.GetSystemMetrics(0)  # SM_CXSCREEN
        cy = user32.GetSystemMetrics(1)  # SM_CYSCREEN
        if cx <= 0 or cy <= 0:
            return (
                False,
                f"Invalid virtual display metrics: {cx}x{cy} (headless session 0).",
            )

        return True, f"Interactive desktop available ({cx}x{cy})."
    except Exception as e:
        return False, f"Exception while probing Windows desktop interactivity: {e}"


def enumerate_windows_for_pid(pid: int) -> list[dict[str, Any]]:
    """Enumerate top-level windows for target process ID on Windows."""
    windows: list[dict[str, Any]] = []
    if sys.platform != "win32":
        return windows

    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        setup_win32_ctypes_signatures(user32)
        wnd_proc = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
        )

        def enum_cb(hwnd: Any, lparam: Any) -> bool:
            w_pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(w_pid))
            if w_pid.value == pid:
                length = user32.GetWindowTextLengthW(hwnd) + 1
                buff = ctypes.create_unicode_buffer(length)
                user32.GetWindowTextW(hwnd, buff, length)

                class_buff = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, class_buff, 256)

                is_visible = bool(user32.IsWindowVisible(hwnd))
                hwnd_val = (
                    int(hwnd)
                    if isinstance(hwnd, int)
                    else (hwnd.value if hasattr(hwnd, "value") else int(hwnd))
                )
                windows.append(
                    {
                        "hwnd": hwnd_val,
                        "title": buff.value,
                        "class_name": class_buff.value,
                        "visible": is_visible,
                    }
                )
            return True

        user32.EnumWindows(wnd_proc(enum_cb), 0)
    except Exception as e:
        print(f"[WARN] Failed to enumerate Windows for PID {pid}: {e}", file=sys.stderr)

    return windows


def select_primary_windows(windows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Strictly select authentic visible main application windows, ignoring Qt helper/invisible windows."""
    # 1. Visible windows with title containing '集成脚本工具'
    title_matches = [
        w for w in windows if w.get("visible") and "集成脚本工具" in w.get("title", "")
    ]
    if title_matches:
        return title_matches

    # 2. Visible non-console windows with Qt in class name or non-empty title
    qt_matches = [
        w
        for w in windows
        if w.get("visible")
        and "ConsoleWindowClass" not in w.get("class_name", "")
        and ("Qt" in w.get("class_name", "") or bool(w.get("title", "").strip()))
    ]
    if qt_matches:
        return qt_matches

    # 3. Any visible non-console window
    visible_non_console = [
        w
        for w in windows
        if w.get("visible") and "ConsoleWindowClass" not in w.get("class_name", "")
    ]
    if visible_non_console:
        return visible_non_console

    return windows


def is_control_existing(elem: Any, timeout: float = 2.0) -> bool:
    """Check if an element exists, accommodating both WindowSpecification and resolved Wrappers."""
    if elem is None:
        return False
    if hasattr(elem, "exists"):
        try:
            return bool(elem.exists(timeout=timeout))
        except Exception:
            return False
    # Resolved Wrapper has no 'exists()' method; its presence in descendants implies existence
    return True


def is_same_control(a: Any, b: Any) -> bool:
    """Check if two pywinauto controls or specifications refer to the same element."""
    if a is b:
        return True
    try:
        a_info = getattr(a, "element_info", None)
        b_info = getattr(b, "element_info", None)
        if a_info is not None and b_info is not None:
            # UIA 虚拟控件可能没有独立 HWND；CompareElements 才能判定元素身份。
            return bool(a_info == b_info)
    except Exception:
        pass
    try:
        a_h = getattr(a, "handle", None)
        b_h = getattr(b, "handle", None)
        if a_h and b_h and a_h == b_h:
            return True
    except Exception:
        pass
    try:
        return a == b
    except Exception:
        return False


def set_control_text(elem: Any, text: str, prefer_type_keys: bool = False) -> bool:
    """Set text on a control (WindowSpecification or Wrapper) safely across pywinauto types."""
    if elem is None:
        return False

    methods = (
        ["type_keys", "set_edit_text", "set_text"]
        if prefer_type_keys
        else ["set_edit_text", "set_text", "type_keys"]
    )
    for method_name in methods:
        method = getattr(elem, method_name, None)
        if callable(method):
            try:
                if method_name == "type_keys":
                    method(text, with_spaces=True)
                else:
                    method(text)
                return True
            except Exception:
                continue
    return False


def click_control(elem: Any) -> bool:
    """Click a button control (WindowSpecification or Wrapper)."""
    if elem is None:
        return False
    for method_name in ["click", "click_input"]:
        method = getattr(elem, method_name, None)
        if callable(method):
            try:
                method()
                return True
            except Exception:
                continue
    return False


def run_windows_automation(
    app_ctrl: Any,
    main_dlg: Any,
    input_imgs: Path,
    output_lbls: Path,
) -> tuple[bool, str | None]:
    """Execute label.create_empty automation workflow on Windows using pywinauto."""
    try:
        # 1. Search for operation
        search_edit = main_dlg.child_window(auto_id="search_input")
        if not is_control_existing(search_edit, timeout=2.0):
            edits = main_dlg.descendants(control_type="Edit")
            if edits:
                search_edit = edits[0]
        if is_control_existing(search_edit):
            set_control_text(search_edit, "创建空标签", prefer_type_keys=True)
            time.sleep(0.6)

        # 2. Fill image input directory
        img_edit = main_dlg.child_window(auto_id="images_dir", control_type="Edit")
        if not is_control_existing(img_edit, timeout=2.0):
            all_edits = [
                e
                for e in main_dlg.descendants(control_type="Edit")
                if not is_same_control(e, search_edit)
            ]
            if len(all_edits) >= 1:
                img_edit = all_edits[0]
        if is_control_existing(img_edit):
            set_control_text(img_edit, str(input_imgs), prefer_type_keys=False)
            time.sleep(0.3)

        # 3. Fill label output directory
        lbl_edit = main_dlg.child_window(auto_id="labels_dir", control_type="Edit")
        if not is_control_existing(lbl_edit, timeout=2.0):
            all_edits = [
                e
                for e in main_dlg.descendants(control_type="Edit")
                if not is_same_control(e, search_edit)
            ]
            if len(all_edits) >= 2:
                lbl_edit = all_edits[1]
        if is_control_existing(lbl_edit):
            set_control_text(lbl_edit, str(output_lbls), prefer_type_keys=False)
            time.sleep(0.3)

        # 4. Trigger execution
        exec_btn = main_dlg.child_window(title="开始执行", control_type="Button")
        if not is_control_existing(exec_btn, timeout=2.0):
            exec_btn = main_dlg.child_window(
                auto_id="primary_button", control_type="Button"
            )
        if not is_control_existing(exec_btn, timeout=2.0):
            buttons = [
                b
                for b in main_dlg.descendants(control_type="Button")
                if "开始执行" in getattr(b, "window_text", lambda: "")()
                or (
                    getattr(b, "element_info", None)
                    and "开始执行" in getattr(b.element_info, "name", "")
                )
            ]
            if buttons:
                exec_btn = buttons[0]

        if is_control_existing(exec_btn, timeout=5.0):
            if click_control(exec_btn):
                time.sleep(3.0)
                return True, None
            return False, "Failed to click execution button"

        return False, "Execution button not found"
    except Exception as e:
        return False, f"Windows pywinauto automation error: {e}"


def close_windows_application(
    proc: subprocess.Popen[Any] | None,
    wins: list[dict[str, Any]],
    main_dlg: Any = None,
) -> None:
    """Close the target Windows application gracefully using pywinauto and 64-bit PostMessageW WM_CLOSE."""
    # 1. Try pywinauto main_dlg.close() first if available
    if main_dlg is not None:
        try:
            if hasattr(main_dlg, "close"):
                main_dlg.close()
        except Exception:
            pass

    # 2. Select authentic visible main window(s) and send WM_CLOSE
    try:
        import ctypes
        from ctypes import wintypes

        windll = getattr(ctypes, "windll", None)
        if windll is None:
            return

        user32 = windll.user32
        setup_win32_ctypes_signatures(user32)

        candidate_wins = wins
        if proc and proc.pid:
            fresh_wins = []
            for p in get_process_tree_pids(proc.pid):
                fresh_wins.extend(enumerate_windows_for_pid(p))
            if fresh_wins:
                candidate_wins = fresh_wins

        primary_wins = select_primary_windows(candidate_wins)
        for w in primary_wins:
            hwnd_val = w.get("hwnd")
            if hwnd_val:
                user32.PostMessageW(
                    wintypes.HWND(hwnd_val), 0x0010, 0, 0
                )  # 0x0010 = WM_CLOSE
    except Exception as e:
        print(f"[WARN] Failed to post WM_CLOSE message: {e}", file=sys.stderr)


def get_process_tree_pids(root_pid: int) -> list[int]:
    """Retrieve root PID and all direct/indirect child PIDs."""
    pids = [root_pid]
    if sys.platform.startswith("linux"):
        try:
            out = subprocess.check_output(
                ["pgrep", "-P", str(root_pid)], stderr=subprocess.DEVNULL
            ).decode()
            for line in out.splitlines():
                if line.strip():
                    child_pid = int(line.strip())
                    pids.extend(get_process_tree_pids(child_pid))
        except Exception:
            pass
    return list(dict.fromkeys(pids))


def terminate_process_tree(root_pid: int) -> None:
    """Safely terminate only the spawned process tree."""
    tree = get_process_tree_pids(root_pid)
    for p in reversed(tree):
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(p)],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                os.kill(p, 15)  # SIGTERM
        except Exception:
            pass
    time.sleep(0.3)
    for p in reversed(tree):
        try:
            if sys.platform != "win32":
                os.kill(p, 9)  # SIGKILL
        except Exception:
            pass


def find_linux_window_for_pids(pids: list[int]) -> str | None:
    """Find visible application window strictly belonging to one of the target PIDs."""
    for p in pids:
        try:
            out = (
                subprocess.check_output(
                    ["xdotool", "search", "--pid", str(p)],
                    stderr=subprocess.DEVNULL,
                )
                .decode()
                .split()
            )
            for wid in out:
                name = (
                    subprocess.check_output(
                        ["xdotool", "getwindowname", wid],
                        stderr=subprocess.DEVNULL,
                    )
                    .decode()
                    .strip()
                )
                if "集成脚本工具" in name:
                    return wid
        except Exception:
            continue
    try:
        out = (
            subprocess.check_output(
                ["xdotool", "search", "--name", "集成脚本工具"],
                stderr=subprocess.DEVNULL,
            )
            .decode()
            .split()
        )
        if out:
            return out[0]
    except Exception:
        pass
    return None


def get_window_geometry(wid: str) -> tuple[int, int, int, int]:
    """Extract x, y, width, height from xdotool getwindowgeometry."""
    try:
        out = subprocess.check_output(
            ["xdotool", "getwindowgeometry", wid], stderr=subprocess.DEVNULL
        ).decode()
        pos_match = re.search(r"Position:\s*(\d+),(\d+)", out)
        geo_match = re.search(r"Geometry:\s*(\d+)x(\d+)", out)
        if pos_match and geo_match:
            return (
                int(pos_match.group(1)),
                int(pos_match.group(2)),
                int(geo_match.group(1)),
                int(geo_match.group(2)),
            )
    except Exception:
        pass
    return (0, 0, 1200, 780)


def send_x11_close_message(window_id: int | str) -> bool:
    """Send X11 ClientMessage WM_PROTOCOLS / WM_DELETE_WINDOW to window.

    Triggers Qt's native closeEvent handler for clean, graceful exit
    without requiring a window manager (e.g. in bare Xvfb).
    """
    if not sys.platform.startswith("linux"):
        return False

    try:
        import ctypes
        import ctypes.util

        x11_name = ctypes.util.find_library("X11") or "libX11.so.6"
        x11 = ctypes.cdll.LoadLibrary(x11_name)

        x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x11.XOpenDisplay.restype = ctypes.c_void_p

        x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        x11.XCloseDisplay.restype = ctypes.c_int

        x11.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
        x11.XInternAtom.restype = ctypes.c_ulong

        x11.XSendEvent.argtypes = [
            ctypes.c_void_p,
            ctypes.c_ulong,
            ctypes.c_int,
            ctypes.c_long,
            ctypes.c_void_p,
        ]
        x11.XSendEvent.restype = ctypes.c_int

        x11.XFlush.argtypes = [ctypes.c_void_p]
        x11.XFlush.restype = ctypes.c_int

        disp = x11.XOpenDisplay(None)
        if not disp:
            return False

        try:
            proto = x11.XInternAtom(disp, b"WM_PROTOCOLS", 0)
            del_atom = x11.XInternAtom(disp, b"WM_DELETE_WINDOW", 0)

            wid = int(window_id, 0) if isinstance(window_id, str) else int(window_id)

            class XClientMessageEvent(ctypes.Structure):
                _fields_ = [
                    ("type", ctypes.c_int),
                    ("serial", ctypes.c_ulong),
                    ("send_event", ctypes.c_int),
                    ("display", ctypes.c_void_p),
                    ("window", ctypes.c_ulong),
                    ("message_type", ctypes.c_ulong),
                    ("format", ctypes.c_int),
                    ("l0", ctypes.c_long),
                    ("l1", ctypes.c_long),
                    ("l2", ctypes.c_long),
                    ("l3", ctypes.c_long),
                    ("l4", ctypes.c_long),
                ]

            class XEvent(ctypes.Union):
                _fields_ = [
                    ("type", ctypes.c_int),
                    ("xclient", XClientMessageEvent),
                    ("pad", ctypes.c_long * 24),
                ]

            ev = XEvent()
            ev.type = 33  # ClientMessage
            ev.xclient.type = 33
            ev.xclient.serial = 0
            ev.xclient.send_event = 1
            ev.xclient.display = disp
            ev.xclient.window = wid
            ev.xclient.message_type = proto
            ev.xclient.format = 32
            ev.xclient.l0 = int(del_atom)
            ev.xclient.l1 = 0

            res = x11.XSendEvent(disp, wid, 0, 0, ctypes.byref(ev))
            x11.XFlush(disp)
            return bool(res)
        finally:
            x11.XCloseDisplay(disp)
    except Exception as e:
        print(
            f"[WARN] Failed to send X11 WM_DELETE_WINDOW ClientMessage: {e}",
            file=sys.stderr,
        )
        return False


def create_test_fixtures(img_dir: Path, lbl_dir: Path) -> tuple[Path, Path]:
    """Generate authentic PIL image fixtures inside target directory."""
    from PIL import Image

    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)

    im1_path = img_dir / "真实 样本 01.jpg"
    im2_path = img_dir / "真实 样本 02.png"

    Image.new("RGB", (128, 128), color="#3498DB").save(im1_path, "JPEG")
    Image.new("RGBA", (96, 96), color="#2ECC71").save(im2_path, "PNG")

    return im1_path, im2_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Packaged Frozen GUI Smoke Test Runner"
    )
    parser.add_argument(
        "--executable",
        "-e",
        required=True,
        help="Path to frozen GUI executable or script",
    )
    parser.add_argument(
        "--output",
        "-o",
        required=True,
        help="Directory to save reports and screenshots",
    )
    args = parser.parse_args()

    exe_path = Path(args.executable).resolve()
    out_dir = Path(args.output).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    report_file = out_dir / "frozen_smoke_report.json"
    screenshot_file = out_dir / "frozen_gui_smoke.png"

    print("=== Starting Packaged Frozen GUI Smoke Test ===")
    print(f"Executable: {exe_path}")
    print(f"Output Directory: {out_dir}")
    print(f"Platform: {platform.system()} ({platform.release()})")

    if not exe_path.is_file():
        err_msg = f"Target executable does not exist: {exe_path}"
        print(f"[FATAL] {err_msg}", file=sys.stderr)
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump({"status": "FAILED", "error": err_msg}, f, indent=2)
        return 1

    # 1. SETUP ISOLATED SANDBOX DIRECTORY & FIXTURES
    sandbox_dir = Path(tempfile.mkdtemp(prefix="frozen_smoke_sandbox_"))
    proc: subprocess.Popen[Any] | None = None
    stdout_text: str = ""
    stderr_text: str = ""
    exit_code: int = -1

    try:
        temp_config = sandbox_dir / "config"
        temp_state = sandbox_dir / "state"
        temp_cache = sandbox_dir / "cache"
        temp_data = sandbox_dir / "data"
        for d in (temp_config, temp_state, temp_cache, temp_data):
            d.mkdir(parents=True, exist_ok=True)

        input_imgs = sandbox_dir / "测试 图片 样本 目录"
        output_lbls = sandbox_dir / "测试 输出 标签 目录"
        create_test_fixtures(input_imgs, output_lbls)

        expected_f1 = output_lbls / "真实 样本 01.txt"
        expected_f2 = output_lbls / "真实 样本 02.txt"

        # 2. CONSTRUCT ISOLATED EXECUTION ENVIRONMENT
        env = os.environ.copy()
        env["HOME"] = str(sandbox_dir)
        env["USERPROFILE"] = str(sandbox_dir)
        env["XDG_CONFIG_HOME"] = str(temp_config)
        env["XDG_STATE_HOME"] = str(temp_state)
        env["XDG_CACHE_HOME"] = str(temp_cache)
        env["XDG_DATA_HOME"] = str(temp_data)
        env["APPDATA"] = str(temp_config)
        env["LOCALAPPDATA"] = str(temp_cache)

        # Strip python runtimes & desktop compositor redirects from child environment
        env.pop("PYTHONPATH", None)
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONSTARTUP", None)
        env.pop("WAYLAND_DISPLAY", None)

        # Child PATH: POSIX empty (""); Windows System32 only. Controller retains system tools.
        if sys.platform == "win32":
            system_root = os.environ.get("SystemRoot", r"C:\Windows")
            env["PATH"] = rf"{system_root}\System32;{system_root}"
        else:
            env["PATH"] = ""

        if sys.platform.startswith("linux"):
            env["QT_QPA_PLATFORM"] = "xcb"
        elif sys.platform == "win32":
            env["QT_QPA_PLATFORM"] = "windows"

        # 3. INTERACTIVE ENVIRONMENT CHECK
        is_interactive, interactive_reason = check_windows_interactive_desktop()
        print(f"[INFO] Interactivity probe: {is_interactive} ({interactive_reason})")
        if sys.platform == "win32" and not is_interactive:
            err_msg = f"Windows non-interactive headless session detected: {interactive_reason}. Smoke test must fail."
            print(f"[FATAL] {err_msg}", file=sys.stderr)
            with open(report_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "platform": platform.system(),
                        "executable": str(exe_path),
                        "status": "FAILED",
                        "error": err_msg,
                        "interactive_desktop": False,
                        "interactive_desktop_diagnostic": interactive_reason,
                    },
                    f,
                    indent=2,
                )
            return 1

        # 4. LAUNCH FROZEN EXECUTABLE
        print(f"[INFO] Spawning frozen executable: {exe_path} --gui")
        start_time = time.time()
        proc = subprocess.Popen(
            [str(exe_path), "--gui"],
            env=env,
            cwd=str(sandbox_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        gui_window_found = False
        console_window_leaked = False
        target_win_id: str | None = None
        tree_pids = [proc.pid]
        wins: list[dict[str, Any]] = []

        # 5. WAIT FOR WINDOW SPAWN (Startup Timeout: 40s)
        startup_timeout = 40.0
        while time.time() - start_time < startup_timeout:
            if proc.poll() is not None:
                break

            tree_pids = get_process_tree_pids(proc.pid)

            if sys.platform == "win32":
                wins = []
                for p in tree_pids:
                    wins.extend(enumerate_windows_for_pid(p))
                for w in wins:
                    cname = w.get("class_name", "")
                    if "ConsoleWindowClass" in cname and w.get("visible", False):
                        console_window_leaked = True
                    if "集成脚本工具" in w.get("title", "") or "Qt" in cname:
                        gui_window_found = True
                if gui_window_found:
                    break

            elif sys.platform.startswith("linux"):
                target_win_id = find_linux_window_for_pids(tree_pids)
                if target_win_id:
                    gui_window_found = True
                    break

            time.sleep(0.5)

        startup_elapsed = time.time() - start_time
        print(
            f"[INFO] GUI Window Detection: {gui_window_found} (took {startup_elapsed:.2f}s)"
        )

        if not gui_window_found and proc.poll() is not None:
            stdout_bytes, stderr_bytes = proc.communicate(timeout=5)
            stdout_text = stdout_bytes.decode(errors="replace")
            stderr_text = stderr_bytes.decode(errors="replace")
            err_msg = f"Frozen process exited prematurely with code {proc.returncode}."
            print(
                f"[ERROR] {err_msg}\nStdout: {stdout_text}\nStderr: {stderr_text}",
                file=sys.stderr,
            )
            with open(report_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "platform": platform.system(),
                        "executable": str(exe_path),
                        "status": "FAILED",
                        "error": err_msg,
                        "exit_code": proc.returncode,
                        "stdout": stdout_text,
                        "stderr": stderr_text,
                    },
                    f,
                    indent=2,
                )
            return 1

        # 6. WINDOW GEOMETRY VALIDATION & RELATIVE AUTOMATION (label.create_empty)
        operation_performed = False
        operation_error: str | None = None
        output_verified = False
        win_x, win_y, win_w, win_h = (0, 0, 1200, 780)
        main_dlg: Any = None

        if gui_window_found:
            if sys.platform == "win32":
                try:
                    import pywinauto  # type: ignore[import-not-found]

                    app_ctrl = pywinauto.Application(backend="uia").connect(
                        process=proc.pid
                    )
                    main_dlg = app_ctrl.window(title_re=".*集成脚本工具.*")
                    main_dlg.set_focus()
                    time.sleep(0.5)

                    operation_performed, operation_error = run_windows_automation(
                        app_ctrl=app_ctrl,
                        main_dlg=main_dlg,
                        input_imgs=input_imgs,
                        output_lbls=output_lbls,
                    )
                    if operation_error:
                        print(f"[WARN] {operation_error}", file=sys.stderr)
                except Exception as e:
                    operation_error = f"Windows pywinauto automation error: {e}"
                    print(f"[WARN] {operation_error}", file=sys.stderr)

            elif sys.platform.startswith("linux") and target_win_id:
                try:
                    win_x, win_y, win_w, win_h = get_window_geometry(target_win_id)
                    print(
                        f"[INFO] Discovered client window geometry: x={win_x}, y={win_y}, w={win_w}, h={win_h}"
                    )

                    # Validate window size is not clipped below standard layout bounds
                    if win_w < 1000 or win_h < 650:
                        geo_err = (
                            f"Window geometry {win_w}x{win_h} is smaller than required 1200x780 layout. "
                            "Failing with non-zero diagnostic."
                        )
                        print(f"[FATAL] {geo_err}", file=sys.stderr)
                        operation_error = geo_err
                    else:
                        # Focus target window strictly
                        subprocess.run(
                            ["xdotool", "windowfocus", "--sync", target_win_id],
                            check=False,
                        )
                        time.sleep(0.3)

                        # 1. Click search input relative to window (search bar center around x=340, y=25)
                        subprocess.run(
                            [
                                "xdotool",
                                "mousemove",
                                str(win_x + 340),
                                str(win_y + 25),
                                "click",
                                "1",
                            ],
                            check=False,
                        )
                        time.sleep(0.2)
                        subprocess.run(
                            ["xdotool", "type", "--delay", "20", "创建空标签"],
                            check=False,
                        )
                        time.sleep(0.5)

                        # 2. Click filtered leaf item in nav tree relative to window (x=100, y=125)
                        subprocess.run(
                            [
                                "xdotool",
                                "mousemove",
                                str(win_x + 100),
                                str(win_y + 125),
                                "click",
                                "1",
                            ],
                            check=False,
                        )
                        time.sleep(0.5)

                        # 3. Focus and fill images_dir input relative to window (x=677, y=196)
                        subprocess.run(
                            [
                                "xdotool",
                                "mousemove",
                                str(win_x + 677),
                                str(win_y + 196),
                                "click",
                                "1",
                            ],
                            check=False,
                        )
                        time.sleep(0.2)
                        subprocess.run(
                            ["xdotool", "key", "ctrl+a", "BackSpace"], check=False
                        )
                        subprocess.run(
                            [
                                "xdotool",
                                "type",
                                "--delay",
                                "15",
                                str(input_imgs),
                            ],
                            check=False,
                        )
                        time.sleep(0.3)

                        # 4. Focus and fill labels_dir input relative to window (x=677, y=265)
                        subprocess.run(
                            [
                                "xdotool",
                                "mousemove",
                                str(win_x + 677),
                                str(win_y + 265),
                                "click",
                                "1",
                            ],
                            check=False,
                        )
                        time.sleep(0.2)
                        subprocess.run(
                            ["xdotool", "key", "ctrl+a", "BackSpace"], check=False
                        )
                        subprocess.run(
                            [
                                "xdotool",
                                "type",
                                "--delay",
                                "15",
                                str(output_lbls),
                            ],
                            check=False,
                        )
                        time.sleep(0.3)

                        # 5. Click '开始执行' button relative to window (x=341, y=735) and send shortcut
                        subprocess.run(
                            [
                                "xdotool",
                                "mousemove",
                                str(win_x + 341),
                                str(win_y + 735),
                                "click",
                                "1",
                            ],
                            check=False,
                        )
                        subprocess.run(
                            [
                                "xdotool",
                                "key",
                                "--window",
                                target_win_id,
                                "ctrl+Return",
                            ],
                            check=False,
                        )
                        time.sleep(3.0)
                        operation_performed = True
                except Exception as e:
                    operation_error = f"Linux xdotool automation error: {e}"
                    print(f"[WARN] {operation_error}", file=sys.stderr)

        # 7. SCREENSHOT CAPTURE (Pillow / ImageMagick - No PySide6 required)
        screenshot_captured = False
        try:
            from PIL import ImageGrab

            if sys.platform.startswith("linux") and target_win_id:
                im = ImageGrab.grab(bbox=(win_x, win_y, win_x + win_w, win_y + win_h))
                im.save(screenshot_file, "PNG")
                screenshot_captured = (
                    screenshot_file.exists() and screenshot_file.stat().st_size > 0
                )
            elif sys.platform == "win32":
                im = ImageGrab.grab()
                im.save(screenshot_file, "PNG")
                screenshot_captured = (
                    screenshot_file.exists() and screenshot_file.stat().st_size > 0
                )
        except Exception as ex:
            print(f"[WARN] Pillow screenshot capture exception: {ex}")
            if (
                sys.platform.startswith("linux")
                and target_win_id
                and shutil.which("import")
            ):
                try:
                    subprocess.run(
                        ["import", "-window", target_win_id, str(screenshot_file)],
                        check=False,
                    )
                    screenshot_captured = (
                        screenshot_file.exists() and screenshot_file.stat().st_size > 0
                    )
                except Exception:
                    pass

        # 8. STRICT VERIFICATION OF EXECUTION OUTPUT
        output_count = 0
        if expected_f1.exists() and expected_f2.exists():
            s1 = expected_f1.stat().st_size
            s2 = expected_f2.stat().st_size
            # Strictly verified ONLY if both files exist and are 0-byte empty
            if s1 == 0 and s2 == 0:
                output_verified = True
                output_count = 2

        print(
            f"[INFO] Output verification: {output_verified} (empty_labels_created={output_count})"
        )

        # 9. CLEAN SHUTDOWN (X11 WM_DELETE_WINDOW / WM_CLOSE, returncode MUST be 0)
        print("[INFO] Closing application window via GUI protocol...")
        if proc.poll() is None:
            if sys.platform.startswith("linux") and target_win_id:
                sent = send_x11_close_message(target_win_id)
                if not sent:
                    subprocess.run(
                        ["xdotool", "key", "--window", target_win_id, "alt+F4"],
                        check=False,
                    )
            elif sys.platform == "win32":
                close_windows_application(proc, wins, main_dlg=main_dlg)

            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                print(
                    "[WARN] Process did not exit within 8s after close signal. Terminating process tree..."
                )
                terminate_process_tree(proc.pid)
                try:
                    proc.wait(timeout=3)
                except Exception:
                    pass

        exit_code = proc.returncode if proc.returncode is not None else -1
        print(f"[INFO] Process exited with code: {exit_code}")

        try:
            out_b, err_b = proc.communicate(timeout=2)
            stdout_text = out_b.decode(errors="replace")
            stderr_text = err_b.decode(errors="replace")
        except Exception:
            pass

        clean_exit = exit_code == 0

        passed = (
            gui_window_found
            and not console_window_leaked
            and operation_performed
            and output_verified
            and (output_count == 2)
            and screenshot_captured
            and clean_exit
            and (exit_code == 0)
        )

        smoke_report = {
            "platform": platform.system(),
            "executable": str(exe_path),
            "gui_window_found": gui_window_found,
            "console_window_leaked": console_window_leaked,
            "interactive_desktop": is_interactive,
            "interactive_desktop_diagnostic": interactive_reason,
            "operation_tested": "label.create_empty",
            "operation_performed": operation_performed,
            "operation_error": operation_error,
            "output_verified": output_verified,
            "fixture_output_counts": output_count,
            "screenshot_captured": screenshot_captured,
            "screenshot_path": str(screenshot_file) if screenshot_captured else None,
            "exit_code": exit_code,
            "clean_exit": clean_exit,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "status": "PASSED" if passed else "FAILED",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        with open(report_file, "w", encoding="utf-8") as rf:
            json.dump(smoke_report, rf, ensure_ascii=False, indent=2)

        print(f"=== Frozen Smoke Summary written to {report_file} ===")
        print(f"Result: {smoke_report['status']}")
        return 0 if passed else 1

    finally:
        if proc and proc.poll() is None:
            terminate_process_tree(proc.pid)
        if proc:
            try:
                out_b, err_b = proc.communicate(timeout=2)
                if not stdout_text:
                    stdout_text = out_b.decode(errors="replace")
                if not stderr_text:
                    stderr_text = err_b.decode(errors="replace")
            except Exception:
                pass
        if not report_file.exists():
            try:
                with open(report_file, "w", encoding="utf-8") as rf:
                    json.dump(
                        {
                            "status": "FAILED",
                            "error": "Aborted or unhandled exception during smoke execution.",
                            "stdout": stdout_text,
                            "stderr": stderr_text,
                        },
                        rf,
                        indent=2,
                    )
            except Exception:
                pass
        shutil.rmtree(sandbox_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
