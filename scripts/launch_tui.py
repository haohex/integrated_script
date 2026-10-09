#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""冻结/打包后的终端界面（TUI）启动器。

该入口在解析参数、创建任何进程或线程之前调用 ``multiprocessing.freeze_support()``，
确保图片压缩所用的进程池在冻结环境中不会重复启动整套界面。
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

    from integrated_script.main import main as app_main

    arguments = sys.argv[1:]
    return int(app_main(arguments) or 0)


if __name__ == "__main__":
    sys.exit(main())
