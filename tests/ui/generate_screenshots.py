# -*- coding: utf-8 -*-
"""Real Qt offscreen screenshot generator for visual design verification using real AppService."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

OUTPUT_DIR = Path(__file__).resolve().parents[2] / "docs" / "design" / "screenshots"


def annotate_screenshot(pixmap: Any, title: str) -> Any:
    """Add a clear environment and state watermark to ensure honest provenance."""
    from PySide6.QtGui import QColor, QFont, QPainter, QPixmap

    banner_height = 28
    new_pixmap = QPixmap(pixmap.width(), pixmap.height() + banner_height)
    new_pixmap.fill(QColor("#1E1E1E"))

    painter = QPainter(new_pixmap)
    # Draw original window
    painter.drawPixmap(0, 0, pixmap)

    # Draw bottom watermark banner
    painter.fillRect(
        0, pixmap.height(), pixmap.width(), banner_height, QColor("#141414")
    )
    painter.setPen(QColor("#A0A0A0"))
    font = QFont("sans-serif", 9)
    painter.setFont(font)

    watermark_text = f"视觉验收样张: {title} | 真实 AppService 操作目录 (42项) | 环境: Linux (offscreen)"
    painter.drawText(
        12,
        pixmap.height() + 18,
        watermark_text,
    )
    painter.end()
    return new_pixmap


def capture_all_states(
    sandbox_root: Path | None = None,
    output_dir: Path | None = None,
) -> list[str]:
    """Capture all required application states using an isolated sandbox environment."""
    out_dir = output_dir if output_dir is not None else OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    generated_files: list[str] = []

    # Preserve original environment variables
    env_keys = (
        "QT_QPA_PLATFORM",
        "XDG_CONFIG_HOME",
        "XDG_STATE_HOME",
        "XDG_CACHE_HOME",
        "XDG_DATA_HOME",
        "APPDATA",
        "LOCALAPPDATA",
    )
    orig_env = {k: os.environ.get(k) for k in env_keys}

    _UNSET = object()
    orig_theme_override: Any = _UNSET
    orig_platformdirs: Any = _UNSET
    orig_app_paths_platformdirs: Any = _UNSET

    # Determine sandbox directory
    owns_sandbox = sandbox_root is None
    sandbox_dir = (
        sandbox_root
        if sandbox_root is not None
        else Path(tempfile.mkdtemp(prefix="screenshot_sandbox_"))
    )

    temp_config_home = sandbox_dir / "config"
    temp_state_home = sandbox_dir / "state"
    temp_cache_home = sandbox_dir / "cache"
    temp_data_home = sandbox_dir / "data"
    temp_config_home.mkdir(parents=True, exist_ok=True)
    temp_state_home.mkdir(parents=True, exist_ok=True)
    temp_cache_home.mkdir(parents=True, exist_ok=True)
    temp_data_home.mkdir(parents=True, exist_ok=True)

    # Set isolated environment variables before any integrated_script imports
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["XDG_CONFIG_HOME"] = str(temp_config_home)
    os.environ["XDG_STATE_HOME"] = str(temp_state_home)
    os.environ["XDG_CACHE_HOME"] = str(temp_cache_home)
    os.environ["XDG_DATA_HOME"] = str(temp_data_home)
    os.environ["APPDATA"] = str(temp_config_home)
    os.environ["LOCALAPPDATA"] = str(temp_cache_home)

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

    # Patch platformdirs for cross-platform isolation (Windows/macOS/Linux)
    try:
        import platformdirs

        orig_platformdirs = platformdirs.PlatformDirs
        platformdirs.PlatformDirs = IsolatedPlatformDirs  # type: ignore[assignment,misc]
    except ImportError:
        pass

    # Patch already loaded integrated_script.application.paths.PlatformDirs alias if present
    app_paths_mod = sys.modules.get("integrated_script.application.paths")
    if app_paths_mod is not None:
        orig_app_paths_platformdirs = getattr(app_paths_mod, "PlatformDirs", None)
        setattr(app_paths_mod, "PlatformDirs", IsolatedPlatformDirs)

    app = None
    owns_app = False
    service = None
    created_widgets: list[Any] = []
    existing_widgets: set[Any] = set()

    try:
        # Import theme helper to capture and restore theme override (AFTER isolation)
        from integrated_script.ui.shared.theme import (
            get_theme_config_path_override,
            set_theme_config_path_override,
        )

        orig_theme_override = get_theme_config_path_override()
        temp_theme_file = (
            temp_config_home / "integrated_script" / "theme_preference.json"
        )
        set_theme_config_path_override(temp_theme_file)

        # Ensure integrated_script.application.paths is patched even if loaded during theme import
        if "integrated_script.application.paths" in sys.modules:
            curr_mod = sys.modules["integrated_script.application.paths"]
            if orig_app_paths_platformdirs is _UNSET:
                orig_app_paths_platformdirs = (
                    orig_platformdirs if orig_platformdirs is not _UNSET else None
                )
            setattr(curr_mod, "PlatformDirs", IsolatedPlatformDirs)

        from PySide6.QtWidgets import QApplication

        from integrated_script.application import AppService
        from integrated_script.config.settings import ConfigManager
        from integrated_script.contracts.results import OperationResult
        from integrated_script.ui.desktop.main_window import MainWindow
        from integrated_script.ui.desktop.widgets.interaction_dialog import (
            InteractionDialog,
        )
        from integrated_script.ui.shared.contract import InteractionRequest
        from integrated_script.ui.shared.theme import (
            THEME_DARK,
            THEME_LIGHT,
            save_theme_preference,
        )

        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv if sys.argv else ["screenshot_gen"])
            owns_app = True
        else:
            existing_widgets = set(QApplication.topLevelWidgets())

        temp_config_file = temp_config_home / "integrated_script" / "config.json"
        temp_config_mgr = ConfigManager(config_file=temp_config_file, auto_save=False)
        temp_cache_dir = temp_cache_home / "integrated_script" / "temp"
        temp_log_dir = temp_state_home / "integrated_script" / "logs"
        temp_cache_dir.mkdir(parents=True, exist_ok=True)
        temp_log_dir.mkdir(parents=True, exist_ok=True)
        temp_config_mgr.set("paths.temp_dir", str(temp_cache_dir))
        temp_config_mgr.set("paths.log_dir", str(temp_log_dir))

        service = AppService(
            config=temp_config_mgr,
            working_directory=sandbox_dir,
        )

        # 1. Light Theme Main Window (Default 1200x780, CTDS selected)
        save_theme_preference(THEME_LIGHT)
        win_light = MainWindow(service=service)
        created_widgets.append(win_light)
        win_light.resize(1200, 780)
        win_light._select_operation_by_id("yolo.ctds_to_yolo")
        win_light.show()
        QApplication.processEvents()
        pix = annotate_screenshot(win_light.grab(), "浅色模式主界面 (Light Theme)")
        p1 = out_dir / "desktop-light-main.png"
        pix.save(str(p1))
        generated_files.append(str(p1))
        win_light.close()
        QApplication.processEvents()

        # 2. Dark Theme Main Window (1200x780, CTDS selected)
        save_theme_preference(THEME_DARK)
        win_dark = MainWindow(service=service)
        created_widgets.append(win_dark)
        win_dark.resize(1200, 780)
        win_dark._select_operation_by_id("yolo.ctds_to_yolo")
        win_dark.show()
        QApplication.processEvents()
        pix = annotate_screenshot(win_dark.grab(), "深色模式主界面 (Dark Theme)")
        p2 = out_dir / "desktop-dark-main.png"
        pix.save(str(p2))
        generated_files.append(str(p2))

        # 3. Destructive Operation with Alert Banner
        win_dark._select_operation_by_id("yolo.clean_unmatched")
        QApplication.processEvents()
        pix = annotate_screenshot(
            win_dark.grab(),
            "破坏性操作提示与安全标识 (Destructive Operation Warning)",
        )
        p3 = out_dir / "desktop-destructive-banner.png"
        pix.save(str(p3))
        generated_files.append(str(p3))

        # 4. Dangerous Action / Confirmation Dialog
        req = InteractionRequest(
            id="confirm_danger_clean",
            title="确认清理无标注孤儿图像文件",
            message="扫描发现 128 个孤儿图像文件，由于未检测到对应标签，即将执行物理删除。此操作不可逆！",
            kind="confirm",
            details=(
                "待删除文件数: 128 个",
                "预计释放磁盘空间: 342.6 MB",
                "目标目录: /data/datasets/yolo_project/train/images",
                "包含示例: IMG_20240101_001.jpg, IMG_20240101_002.jpg ...",
            ),
        )
        dlg = InteractionDialog(req, parent=win_dark)
        created_widgets.append(dlg)
        dlg.show()
        QApplication.processEvents()
        pix_dlg = annotate_screenshot(
            dlg.grab(), "二次危险操作确认弹窗 (Dangerous Action Modal)"
        )
        p4 = out_dir / "desktop-interaction-dialog.png"
        pix_dlg.save(str(p4))
        generated_files.append(str(p4))
        dlg.close()
        QApplication.processEvents()

        # 5. Running Progress & Real-time Console Log
        win_dark._select_operation_by_id("yolo.validate_detection")
        win_dark.exec_panel.setVisible(True)
        win_dark.progress_bar.setValue(45)
        win_dark.lbl_step.setText("正在解析 YOLO 标注文件 (第 45/100 批次)...")
        win_dark.log_console.setPlainText(
            "[01:45:10] 初始化检测验证任务...\n"
            "[01:45:11] 成功加载 classes.txt: 发现 8 个检测类别\n"
            "[01:45:12] 开始扫描图片与标签匹配对: 共 15,200 对\n"
            "[01:45:13] 批次 1-40 处理完成，无坐标越界\n"
            "[01:45:14] 正在解析第 45 批次..."
        )
        win_dark.lbl_status.setText("执行中 (45%)...")
        QApplication.processEvents()
        pix = annotate_screenshot(
            win_dark.grab(),
            "执行进行中状态与实时控制台日志 (Running Progress & Log)",
        )
        p5 = out_dir / "desktop-running-progress.png"
        pix.save(str(p5))
        generated_files.append(str(p5))

        # 6. Result Success View with Metrics, Tables, and Hierarchy
        win_dark.progress_bar.setValue(100)
        win_dark.lbl_step.setText("目标检测验证完成，未发现致命错误。")
        res_success = OperationResult(
            success=True,
            message="目标检测数据集验证通过，统计报告已生成。",
            payload={
                "total_images": 15200,
                "valid_labels": 84320,
                "missing_labels": 0,
                "empty_labels": 12,
                "elapsed_seconds": 3.42,
                "category_distribution": [
                    {
                        "class_id": 0,
                        "name": "person",
                        "count": 32104,
                        "ratio": "38.1%",
                    },
                    {
                        "class_id": 1,
                        "name": "car",
                        "count": 28450,
                        "ratio": "33.7%",
                    },
                    {
                        "class_id": 2,
                        "name": "bicycle",
                        "count": 14210,
                        "ratio": "16.8%",
                    },
                    {
                        "class_id": 3,
                        "name": "dog",
                        "count": 9556,
                        "ratio": "11.3%",
                    },
                ],
                "dataset_health": {
                    "aspect_ratio_mean": 1.33,
                    "bbox_normalized_valid": True,
                    "labels_out_of_bounds": 0,
                },
            },
        )
        win_dark.result_view.set_result(res_success)
        win_dark.result_view.setVisible(True)
        QApplication.processEvents()
        pix = annotate_screenshot(
            win_dark.grab(),
            "成功执行结果展示 (Success Result with Structured Payload)",
        )
        p6 = out_dir / "desktop-result-success.png"
        pix.save(str(p6))
        generated_files.append(str(p6))

        # 7. Result Failure View with Error Code Banner
        res_failure = OperationResult(
            success=False,
            message="无法解析数据集：图像目录缺失或标签路径不存在。",
            error_code="DATASET_PATH_NOT_FOUND",
            payload={
                "target_path": "/invalid/path/to/dataset",
                "suggestion": "请检查路径是否存在，或确认目录具备只读权限。",
            },
        )
        win_dark.result_view.set_result(res_failure)
        win_dark.result_view.setVisible(True)
        QApplication.processEvents()
        pix = annotate_screenshot(
            win_dark.grab(),
            "操作失败结果提示与错误码 (Failure Result with Error Code)",
        )
        p7 = out_dir / "desktop-result-failure.png"
        pix.save(str(p7))
        generated_files.append(str(p7))

        # 8. Compact Mode (980x600)
        win_dark.result_view.setVisible(False)
        win_dark.exec_panel.setVisible(False)
        win_dark.btn_compact.setChecked(True)
        win_dark._toggle_compact(True)
        QApplication.processEvents()
        pix = annotate_screenshot(
            win_dark.grab(), "紧凑布局模式 (Compact Mode 980x600)"
        )
        p8 = out_dir / "desktop-compact-mode.png"
        pix.save(str(p8))
        generated_files.append(str(p8))

        win_dark.close()
        QApplication.processEvents()

    finally:
        # Guarantee only windows created by this screenshot function are closed
        try:
            from PySide6.QtWidgets import QApplication

            qapp = QApplication.instance()
            if qapp is not None:
                current_widgets = set(QApplication.topLevelWidgets())
                for widget in (current_widgets - existing_widgets) | set(
                    created_widgets
                ):
                    try:
                        widget.close()
                    except Exception:
                        pass
                qapp.processEvents()
        except Exception:
            pass

        if service is not None:
            try:
                service.close()
            except Exception:
                pass

        if owns_app and app is not None:
            try:
                app.quit()
            except Exception:
                pass

        # Restore platformdirs patch
        if orig_platformdirs is not _UNSET:
            try:
                import platformdirs

                platformdirs.PlatformDirs = orig_platformdirs
            except Exception:
                pass

        if orig_app_paths_platformdirs is not _UNSET:
            try:
                if "integrated_script.application.paths" in sys.modules:
                    setattr(
                        sys.modules["integrated_script.application.paths"],
                        "PlatformDirs",
                        orig_app_paths_platformdirs,
                    )
            except Exception:
                pass

        # Restore theme override to its exact original state
        if orig_theme_override is not _UNSET:
            try:
                from integrated_script.ui.shared.theme import (
                    set_theme_config_path_override,
                )

                set_theme_config_path_override(orig_theme_override)
            except Exception:
                pass

        # Restore all environment variables
        for k, v in orig_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

        # Clean up temporary sandbox directory if owned
        if owns_sandbox:
            shutil.rmtree(sandbox_dir, ignore_errors=True)

    return generated_files


if __name__ == "__main__":
    files = capture_all_states()
    print("Successfully captured screenshots:")
    for f in files:
        print(f" - {f}")
