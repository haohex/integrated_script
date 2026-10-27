#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Integrated Script Main Entry Point

这是集成脚本的主入口点，负责设置环境和启动应用程序。
"""

import os
import sys

# 添加 src 目录到 Python 路径
src_path = os.path.join(os.path.dirname(__file__), "src")
if os.path.isdir(src_path) and src_path not in sys.path:
    sys.path.insert(0, src_path)

# Windows 兼容性处理
if sys.platform == "win32":
    try:
        from integrated_script.core.windows_compat import (
            initialize_windows_compatibility,
        )

        compat_result = initialize_windows_compatibility()
        # 调试模式下显示兼容性初始化结果
        if "--debug-compat" in sys.argv:
            print(f"Windows兼容性初始化: {compat_result}")
    except Exception as e:
        # 如果兼容性初始化失败，继续运行但给出警告
        print(f"警告: Windows兼容性初始化失败: {e}")

# 导入主函数
from integrated_script.main import main

if __name__ == "__main__":
    sys.exit(main())
