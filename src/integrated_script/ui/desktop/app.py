# -*- coding: utf-8 -*-
"""Desktop application entry point and Qt initialization."""

from __future__ import annotations

import sys

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from integrated_script.ui.desktop.main_window import MainWindow
from integrated_script.ui.desktop.widgets.icon_provider import get_icon
from integrated_script.ui.shared.contract import AppService


def setup_application_font(qapp: QApplication) -> QFont:
    """Resolve platform-native font family with Chinese fallback using Qt QFont APIs."""
    available_families = set(QFontDatabase.families())

    if sys.platform == "win32":
        candidates = ["Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei", "SimSun"]
    elif sys.platform == "darwin":
        candidates = [".AppleSystemUIFont", "PingFang SC", "Helvetica Neue", "Arial"]
    else:
        candidates = [
            "Ubuntu",
            "Noto Sans CJK SC",
            "Noto Sans",
            "DejaVu Sans",
            "WenQuanYi Micro Hei",
            "sans-serif",
        ]

    matched = [f for f in candidates if f in available_families or f == "sans-serif"]
    family = matched[0] if matched else "sans-serif"
    font = QFont(family, 10)
    if len(matched) > 1:
        font.setFamilies(matched)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    qapp.setFont(font)
    return font


def run_gui(service: AppService | None = None) -> int:
    """Launch the PySide6 Qt Widgets desktop application."""
    if service is None:
        try:
            from integrated_script.application import AppService as _RealService

            service = _RealService()
        except ImportError as e:
            raise RuntimeError(
                f"无法启动桌面界面：后端应用服务 (integrated_script.application.AppService) 未就绪或导入失败: {e}"
            ) from e

    qapp = QApplication.instance()
    owns_app = False
    if not isinstance(qapp, QApplication):
        qapp = QApplication(sys.argv)
        owns_app = True

    # Typography: Platform native font family and size with Chinese fallbacks
    setup_application_font(qapp)
    qapp.setWindowIcon(get_icon("app", size=32))

    window = MainWindow(service=service)
    window.show()

    if owns_app:
        return qapp.exec()
    return 0


if __name__ == "__main__":
    sys.exit(run_gui())
