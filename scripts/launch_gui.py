#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""冻结/打包后的桌面界面（GUI）启动器。

Windows 下该入口会被 PyInstaller 以 ``--windowed`` 方式打包，因此不出现控制台窗口。
``multiprocessing.freeze_support()`` 必须在解析参数与启动 Qt 之前调用。
"""

from __future__ import annotations

import multiprocessing
import sys
from pathlib import Path


def _ensure_source_on_path() -> None:
    """未安装项目时允许直接从仓库运行该启动器。"""
    src = Path(__file__).resolve().parent.parent / "src"
    if src.is_dir():
        entry = str(src)
        if entry not in sys.path:
            sys.path.insert(0, entry)


def main() -> int:
    multiprocessing.freeze_support()
    _ensure_source_on_path()

    from integrated_script.main import gui_main

    arguments = sys.argv[1:]
    return int(gui_main(arguments) or 0)


if __name__ == "__main__":
    sys.exit(main())
