#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Native visual acceptance runner for Desktop GUI across high-DPI scaling factors.

Features:
- Enforces native platform plugins (Windows 'windows' / Linux Xvfb 'xcb'), strictly forbidding 'offscreen'.
- Runs each scale in a clean subprocess setting QT_SCALE_FACTOR prior to any Qt imports.
- Explicitly documents QT_SCALE_FACTOR as application scaling verification, not physical OS DPI test.
- Total sandboxed isolation of HOME / XDG_* / APPDATA / LOCALAPPDATA / PlatformDirs.
- Executes real backend operations:
    1) 'label.create_empty' with Chinese and spaced directory paths.
    2) 'image.convert' converting real PNG images to JPEG, strictly verified via PIL.open (format & dimensions).
- Checks window & frame geometry against screen.availableGeometry() (clamp smaller screen + scroll).
- Verifies primary action button and scroll areas remain visible and usable.
- Bounded execution timeout: <= 90s per scale factor subprocess.
- Non-zero exit code on failure, structured acceptance_report.json and summary_acceptance.json.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

# Ensure project src is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def parse_scales(scale_arg: str) -> list[float]:
    """Parse single or comma-separated scale strings into float list."""
    parts = [s.strip() for s in scale_arg.split(",") if s.strip()]
    scales: list[float] = []
    for p in parts:
        try:
            val = float(p)
            scales.append(val)
        except ValueError:
            raise ValueError(f"Invalid scale factor: '{p}'. Must be numeric.")
    if not scales:
        scales = [1.0]
    return scales


# ==============================================================================
# SUBPROCESS WORKER: Isolated Native Acceptance Run
# ==============================================================================


def run_single_scale_worker(scale: float, output_dir: Path) -> dict[str, Any]:
    """Execute acceptance tests for a single scale in the current isolated subprocess."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. PRE-IMPORT ISOLATION SANDBOX
    sandbox_root = Path(tempfile.mkdtemp(prefix=f"native_acc_{scale}_"))
    temp_config_home = sandbox_root / "config"
    temp_state_home = sandbox_root / "state"
    temp_cache_home = sandbox_root / "cache"
    temp_data_home = sandbox_root / "data"

    for d in (temp_config_home, temp_state_home, temp_cache_home, temp_data_home):
        d.mkdir(parents=True, exist_ok=True)

    os.environ["HOME"] = str(sandbox_root)
    os.environ["USERPROFILE"] = str(sandbox_root)
    os.environ["XDG_CONFIG_HOME"] = str(temp_config_home)
    os.environ["XDG_STATE_HOME"] = str(temp_state_home)
    os.environ["XDG_CACHE_HOME"] = str(temp_cache_home)
    os.environ["XDG_DATA_HOME"] = str(temp_data_home)
    os.environ["APPDATA"] = str(temp_config_home)
    os.environ["LOCALAPPDATA"] = str(temp_cache_home)

    # High-DPI Application Scaling Configuration
    os.environ["QT_SCALE_FACTOR"] = str(scale)
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"

    # Strict Platform Policy: Prohibit 'offscreen'
    cur_qpa = os.environ.get("QT_QPA_PLATFORM", "").strip().lower()
    if cur_qpa == "offscreen":
        raise RuntimeError(
            "Native acceptance strictly forbids QT_QPA_PLATFORM=offscreen!"
        )
    if sys.platform.startswith("linux"):
        os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    elif sys.platform == "win32":
        os.environ.setdefault("QT_QPA_PLATFORM", "windows")

    # Patch platformdirs before application imports
    class IsolatedPlatformDirs:
        def __init__(
            self,
            appname: str | None = None,
            appauthor: str | None = None,
            *args: Any,
            **kwargs: Any,
        ) -> None:
            self.appname = appname or "integrated_script"
            self.appauthor = appauthor or "IntegratedScript"
            self.user_config_dir = str(temp_config_home / self.appname)
            self.user_log_dir = str(temp_state_home / self.appname / "logs")
            self.user_cache_dir = str(temp_cache_home / self.appname)
            self.user_state_dir = str(temp_state_home / self.appname)
            self.user_data_dir = str(temp_data_home / self.appname)

    try:
        import platformdirs

        platformdirs.PlatformDirs = IsolatedPlatformDirs  # type: ignore[assignment,misc]
    except ImportError:
        pass

    # 2. APPLICATION IMPORTS (AFTER ISOLATION)
    from PIL import Image
    from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
    from PySide6.QtWidgets import QApplication

    from integrated_script.application import AppService, InteractionRequest
    from integrated_script.config import ConfigManager
    from integrated_script.ui.desktop.app import setup_application_font
    from integrated_script.ui.desktop.main_window import MainWindow
    from integrated_script.ui.desktop.widgets.interaction_dialog import (
        InteractionDialog,
    )
    from integrated_script.ui.shared.theme import (
        THEME_DARK,
        THEME_LIGHT,
        set_theme_config_path_override,
    )

    theme_file = temp_config_home / "theme_preference.json"
    set_theme_config_path_override(theme_file)

    # 3. INITIALIZE QT APPLICATION
    raw_app = QApplication.instance()
    if raw_app is None:
        app = QApplication(
            ["native_acceptance", "-platform", os.environ.get("QT_QPA_PLATFORM", "xcb")]
        )
    else:
        assert isinstance(raw_app, QApplication)
        app = raw_app

    setup_application_font(app)

    platform_name = app.platformName().lower()
    if platform_name == "offscreen":
        raise RuntimeError(
            f"Native acceptance failed: Active Qt platform is '{platform_name}', but native platform is required."
        )

    # 4. INITIALIZE REAL APPSERVICE WITH TEST CONFIG
    app_config = ConfigManager(
        config_file=temp_config_home / "app_config.json", auto_save=False
    )
    app_config.set("paths.temp_dir", str(sandbox_root / "temp"))
    app_config.set("paths.log_dir", str(temp_state_home / "logs"))
    service = AppService(app_config, working_directory=sandbox_root)

    win = MainWindow(service=service)
    win.show()
    app.processEvents()

    # 5. FIXTURE CREATION (Real files with spaces & Chinese names)
    label_test_base = sandbox_root / "测试 样本 目录 空格"
    img_dir = label_test_base / "图片 输入"
    lbl_dir = label_test_base / "标签 输出"
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)

    # Write 2 valid test images
    Image.new("RGB", (64, 64), color="blue").save(img_dir / "样本 01.jpg", "JPEG")
    Image.new("RGBA", (48, 48), color="green").save(img_dir / "测试 02.png", "PNG")

    # Create real PNG fixtures for image.convert
    img_conv_base = sandbox_root / "图像 格式 转换"
    conv_in_dir = img_conv_base / "png_sources"
    conv_out_dir = img_conv_base / "jpeg_outputs"
    conv_in_dir.mkdir(parents=True, exist_ok=True)
    conv_out_dir.mkdir(parents=True, exist_ok=True)

    p1 = conv_in_dir / "图1 样本.png"
    p2 = conv_in_dir / "图2 示例.png"
    Image.new("RGB", (64, 64), color="#FF5733").save(p1, "PNG")
    Image.new("RGB", (48, 48), color="#33FF57").save(p2, "PNG")

    screenshots_info: dict[str, str] = {}
    clipping_report: dict[str, Any] = {}
    operation_results: dict[str, Any] = {}

    def capture_widget(widget: Any, filename: str, watermark_title: str) -> Path:
        """Capture widget pixmap with authentic provenance watermark."""
        app.processEvents()
        time.sleep(0.08)
        pixmap = widget.grab()

        banner_height = 28
        combined = QPixmap(pixmap.width(), pixmap.height() + banner_height)
        combined.fill(QColor("#181818"))

        painter = QPainter(combined)
        painter.drawPixmap(0, 0, pixmap)
        painter.fillRect(
            0, pixmap.height(), pixmap.width(), banner_height, QColor("#101010")
        )
        painter.setPen(QColor("#9E9E9E"))
        font = QFont("sans-serif", 9)
        painter.setFont(font)

        plat_desc = (
            "Windows (windows plugin)"
            if sys.platform == "win32"
            else f"Linux (Xvfb {platform_name})"
        )
        wm_text = (
            f"原生验收 | 状态: {watermark_title} | 缩放: {scale*100:.0f}% (QT_SCALE_FACTOR) | "
            f"平台: {plat_desc} | 标题条: Qt Client Area"
        )
        painter.drawText(12, pixmap.height() + 18, wm_text)
        painter.end()

        out_path = output_dir / filename
        combined.save(str(out_path), "PNG")
        screenshots_info[filename] = str(out_path)
        return out_path

    try:
        # A. CAPTURE LIGHT MODE MAIN
        win._apply_theme_for_mode(THEME_LIGHT)
        app.processEvents()
        capture_widget(win, "light_main.png", "浅色模式主界面")

        # B. CAPTURE DARK MODE MAIN
        win._apply_theme_for_mode(THEME_DARK)
        app.processEvents()
        capture_widget(win, "dark_main.png", "深色模式主界面")

        # C. CAPTURE COMPACT MODE MAIN
        win._toggle_compact(True)
        app.processEvents()
        capture_widget(win, "compact_main.png", "紧凑布局模式")
        win._toggle_compact(False)
        app.processEvents()

        # D. CAPTURE MODAL DIALOG
        modal_req = InteractionRequest(
            id="req_acceptance_confirm",
            title="二次确认演示",
            message="检测到 2 个目标文件已存在。确认继续执行转换操作吗？",
            kind="confirm",
            details=("受影响路径: /tmp/sample_dataset", "保留现有文件: 否"),
        )
        dlg = InteractionDialog(request=modal_req, parent=win)
        dlg.show()
        app.processEvents()
        capture_widget(dlg, "interaction_confirm_dialog.png", "二次确认模态弹窗")
        dlg.reject()
        dlg.close()
        app.processEvents()

        # E. EXECUTE OPERATION 1: label.create_empty
        win._select_operation_by_id("label.create_empty")
        assert win.active_operation is not None
        assert win.active_operation.id == "label.create_empty"
        assert win.current_form is not None

        win.current_form.widgets["images_dir"].set_path(str(img_dir))
        win.current_form.widgets["labels_dir"].set_path(str(lbl_dir))
        win.btn_execute.click()

        # Wait for completion
        t0 = time.time()
        for _ in range(80):
            time.sleep(0.05)
            win._poll_events()
            app.processEvents()
            if win.result_view.isVisible():
                break
        t_label_elapsed = time.time() - t0

        created_f1 = lbl_dir / "样本 01.txt"
        created_f2 = lbl_dir / "测试 02.txt"
        label_success = (
            win.result_view.isVisible()
            and created_f1.exists()
            and created_f1.stat().st_size == 0
            and created_f2.exists()
            and created_f2.stat().st_size == 0
        )
        assert (
            label_success
        ), f"label.create_empty failed or output labels invalid: {created_f1}, {created_f2}"
        capture_widget(win, "op_label_empty_result.png", "创建空标签完成结果")

        operation_results["label.create_empty"] = {
            "success": True,
            "created_labels": [created_f1.name, created_f2.name],
            "sizes_bytes": [created_f1.stat().st_size, created_f2.stat().st_size],
            "elapsed_seconds": round(t_label_elapsed, 3),
            "status_text": win.lbl_status.text(),
        }

        # F. EXECUTE OPERATION 2: image.convert (PNG -> JPEG)
        win._select_operation_by_id("image.convert")
        assert win.active_operation is not None
        assert win.active_operation.id == "image.convert"
        assert win.current_form is not None

        win.current_form.widgets["input_path"].set_path(str(conv_in_dir))
        win.current_form.widgets["output_path"].set_path(str(conv_out_dir))
        target_fmt_widget = win.current_form.widgets["target_format"]
        target_fmt_widget.setCurrentText("JPEG")
        win.current_form.widgets["quality"].setValue(90)
        win.btn_execute.click()

        t0 = time.time()
        for _ in range(80):
            time.sleep(0.05)
            win._poll_events()
            app.processEvents()
            if win.result_view.isVisible():
                break
        t_conv_elapsed = time.time() - t0

        converted_f1 = conv_out_dir / "图1 样本.jpeg"
        converted_f2 = conv_out_dir / "图2 示例.jpeg"
        assert (
            converted_f1.exists() and converted_f2.exists()
        ), "Converted files missing"

        # Strict PIL image format & dimension validation
        with Image.open(converted_f1) as img1:
            assert (
                img1.format == "JPEG"
            ), f"Expected JPEG format for {converted_f1}, got {img1.format}"
            assert img1.size == (64, 64), f"Expected size (64, 64), got {img1.size}"
        with Image.open(converted_f2) as img2:
            assert (
                img2.format == "JPEG"
            ), f"Expected JPEG format for {converted_f2}, got {img2.format}"
            assert img2.size == (48, 48), f"Expected size (48, 48), got {img2.size}"

        convert_success = (
            win.result_view.isVisible()
            and converted_f1.stat().st_size > 0
            and converted_f2.stat().st_size > 0
        )
        assert convert_success, "image.convert failed"
        capture_widget(win, "op_image_convert_result.png", "PNG转JPEG完成结果")

        operation_results["image.convert"] = {
            "success": True,
            "converted_files": [converted_f1.name, converted_f2.name],
            "verified_format": "JPEG",
            "verified_dimensions": ["64x64", "48x48"],
            "sizes_bytes": [converted_f1.stat().st_size, converted_f2.stat().st_size],
            "elapsed_seconds": round(t_conv_elapsed, 3),
            "status_text": win.lbl_status.text(),
        }

        # G. KEY WIDGET CLIPPING & AVAILABLE SCREEN ADAPTATION CHECKS
        screen = app.primaryScreen()
        assert screen is not None
        avail_geo = screen.availableGeometry()
        screen_geo = screen.geometry()
        win_geo = win.geometry()
        frame_geo = win.frameGeometry()

        dpi_info = {
            "logical_dpi": round(screen.logicalDotsPerInch(), 2),
            "physical_dpi": round(screen.physicalDotsPerInch(), 2),
            "device_pixel_ratio": round(screen.devicePixelRatio(), 2),
            "scale_validation_type": (
                "QT_SCALE_FACTOR application scaling verification "
                "(not physical Windows OS DPI hardware test)"
            ),
        }

        def check_widget_clipping(name: str, w: Any) -> dict[str, Any]:
            size = w.size()
            min_hint = w.minimumSizeHint()
            if name == "main_window":
                is_clipped = (size.width() < w.minimumWidth() - 2) or (
                    size.height() < w.minimumHeight() - 2
                )
            else:
                is_clipped = (size.width() < min_hint.width() - 2) or (
                    size.height() < min_hint.height() - 2
                )
            return {
                "visible": w.isVisible(),
                "width": size.width(),
                "height": size.height(),
                "min_hint_width": min_hint.width(),
                "min_hint_height": min_hint.height(),
                "clipped": is_clipped,
            }

        clipping_report = {
            "main_window": check_widget_clipping("main_window", win),
            "nav_tree": check_widget_clipping("nav_tree", win.nav_tree),
            "form_scroll": check_widget_clipping("form_scroll", win.form_scroll),
            "btn_execute": check_widget_clipping("btn_execute", win.btn_execute),
            "lbl_status": check_widget_clipping("lbl_status", win.lbl_status),
            "result_view": check_widget_clipping("result_view", win.result_view),
        }

        # Screen Containment Verification: Window frame should strictly reside within available screen bounds
        # Allow up to 2 logical pixels tolerance for native OS invisible resize borders / drop shadow margins.
        containment_tolerance = 2
        frame_within_left = frame_geo.left() >= (
            avail_geo.left() - containment_tolerance
        )
        frame_within_top = frame_geo.top() >= (avail_geo.top() - containment_tolerance)
        frame_within_right = frame_geo.right() <= (
            avail_geo.right() + containment_tolerance
        )
        frame_within_bottom = frame_geo.bottom() <= (
            avail_geo.bottom() + containment_tolerance
        )
        frame_fits_width = frame_geo.width() <= (
            avail_geo.width() + 2 * containment_tolerance
        )
        frame_fits_height = frame_geo.height() <= (
            avail_geo.height() + 2 * containment_tolerance
        )

        fits_available_screen = (
            frame_within_left
            and frame_within_top
            and frame_within_right
            and frame_within_bottom
            and frame_fits_width
            and frame_fits_height
        )

        btn_exec_usable = win.btn_execute.isVisible() and win.btn_execute.isEnabled()
        form_scroll_usable = win.form_scroll.isVisible()

        screen_adaptation = {
            "screen_geometry": {
                "x": screen_geo.x(),
                "y": screen_geo.y(),
                "width": screen_geo.width(),
                "height": screen_geo.height(),
            },
            "screen_available_geometry": {
                "x": avail_geo.x(),
                "y": avail_geo.y(),
                "width": avail_geo.width(),
                "height": avail_geo.height(),
            },
            "window_geometry": {
                "x": win_geo.x(),
                "y": win_geo.y(),
                "width": win_geo.width(),
                "height": win_geo.height(),
            },
            "window_frame_geometry": {
                "x": frame_geo.x(),
                "y": frame_geo.y(),
                "width": frame_geo.width(),
                "height": frame_geo.height(),
            },
            "containment_tolerance_px": containment_tolerance,
            "containment_checks": {
                "within_left": frame_within_left,
                "within_top": frame_within_top,
                "within_right": frame_within_right,
                "within_bottom": frame_within_bottom,
                "fits_width": frame_fits_width,
                "fits_height": frame_fits_height,
            },
            "fits_available_screen": fits_available_screen,
            "primary_action_usable": btn_exec_usable,
            "form_scroll_usable": form_scroll_usable,
        }

        any_severe_clip = any(c.get("clipped", False) for c in clipping_report.values())
        overall_passed = (
            (not any_severe_clip) and fits_available_screen and btn_exec_usable
        )

        report: dict[str, Any] = {
            "scale": scale,
            "platform": {
                "system": platform.system(),
                "release": platform.release(),
                "qt_platform": platform_name,
                "native_titlebar_included": False,
                "titlebar_note": "Qt widget grab captures client area; native OS border and titlebar excluded.",
                "synthetic": False,
            },
            "dpi": dpi_info,
            "screen_adaptation": screen_adaptation,
            "operations_tested": operation_results,
            "clipping_report": clipping_report,
            "clipping_checks_passed": not any_severe_clip,
            "screenshots": screenshots_info,
            "status": "PASSED" if overall_passed else "FAILED",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

        report_file = output_dir / "acceptance_report.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        return report

    finally:
        win.close()
        service.close()
        shutil.rmtree(sandbox_root, ignore_errors=True)


# ==============================================================================
# MAIN CLI DISPATCHER
# ==============================================================================


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Desktop GUI Native Visual Acceptance Runner"
    )
    parser.add_argument(
        "--output",
        "-o",
        required=True,
        help="Output directory for reports and screenshots",
    )
    parser.add_argument(
        "--scale",
        "-s",
        default="1,2",
        help="Scale factor (single value e.g. 1.25 or comma-separated list e.g. 1,1.25,1.5,1.75,2)",
    )
    parser.add_argument(
        "--single-run",
        action="store_true",
        help="Internal flag for executing single scale subprocess",
    )

    args = parser.parse_args()
    output_root = Path(args.output).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    if args.single_run:
        scale_val = float(args.scale)
        try:
            report = run_single_scale_worker(scale_val, output_root)
            print(
                f"[OK] Scale {scale_val} completed. Report: {output_root / 'acceptance_report.json'}"
            )
            return 0 if report.get("status") == "PASSED" else 1
        except Exception as e:
            import traceback

            traceback.print_exc()
            diag_file = output_root / "acceptance_error.json"
            with open(diag_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "scale": scale_val,
                        "error": str(e),
                        "traceback": traceback.format_exc(),
                    },
                    f,
                    indent=2,
                )
            print(f"[FAIL] Scale {scale_val} encountered error: {e}", file=sys.stderr)
            return 1

    scales = parse_scales(args.scale)
    print("=== Starting Native Desktop GUI Acceptance ===")
    print(f"Platform: {platform.system()} ({platform.release()})")
    print(f"Target Scales: {scales}")
    print(f"Output Root: {output_root}")

    # Check Linux DISPLAY requirement
    if sys.platform.startswith("linux"):
        display = os.environ.get("DISPLAY")
        if not display:
            xvfb_which = shutil.which("xvfb-run")
            if xvfb_which:
                print(
                    "[INFO] DISPLAY not set, but xvfb-run found. Re-invoking entire suite under xvfb-run..."
                )
                cmd = [
                    xvfb_which,
                    "-a",
                    "-s",
                    "-screen 0 1920x1080x24",
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--output",
                    str(output_root),
                    "--scale",
                    args.scale,
                ]
                res = subprocess.run(cmd)
                return res.returncode
            else:
                print(
                    "[ERROR] DISPLAY environment variable missing and xvfb-run not found. Native Qt xcb requires X11.",
                    file=sys.stderr,
                )
                return 1

    summary: dict[str, Any] = {
        "platform": platform.system(),
        "scales_attempted": scales,
        "results": {},
        "all_passed": True,
    }

    for s in scales:
        scale_str = f"{s:g}".replace(".", "_")
        scale_dir = output_root / f"scale_{scale_str}"
        scale_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n--- Running Scale: {s} (dir: {scale_dir.name}) ---")
        worker_cmd = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--output",
            str(scale_dir),
            "--scale",
            str(s),
            "--single-run",
        ]

        worker_env = os.environ.copy()
        worker_env["QT_SCALE_FACTOR"] = str(s)
        worker_env["QT_ENABLE_HIGHDPI_SCALING"] = "1"

        try:
            res = subprocess.run(worker_cmd, env=worker_env, timeout=90)
            if res.returncode == 0:
                rep_path = scale_dir / "acceptance_report.json"
                rep_data = {}
                if rep_path.exists():
                    with open(rep_path, "r", encoding="utf-8") as rf:
                        rep_data = json.load(rf)
                summary["results"][str(s)] = {"passed": True, "report": rep_data}
                print(f"--- Scale {s}: PASSED ---")
            else:
                summary["results"][str(s)] = {
                    "passed": False,
                    "returncode": res.returncode,
                }
                summary["all_passed"] = False
                print(
                    f"--- Scale {s}: FAILED (exit code {res.returncode}) ---",
                    file=sys.stderr,
                )
        except subprocess.TimeoutExpired:
            summary["results"][str(s)] = {"passed": False, "timeout": True}
            summary["all_passed"] = False
            print(f"--- Scale {s}: FAILED (Timeout exceeded 90s) ---", file=sys.stderr)

    summary_file = output_root / "summary_acceptance.json"
    with open(summary_file, "w", encoding="utf-8") as sf:
        json.dump(summary, sf, ensure_ascii=False, indent=2)

    print(f"\n=== Native Acceptance Summary written to {summary_file} ===")
    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
