#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
windows_compat.py

Windows兼容性处理模块

提供Windows环境下的编码、颜色和控制台兼容性处理。
"""

import os
import sys


def setup_windows_console() -> bool:
    """设置Windows控制台兼容性

    Returns:
        bool: 是否成功设置
    """
    if sys.platform != "win32":
        return True

    success = True

    # 1. 设置控制台代码页为UTF-8
    try:
        import subprocess

        subprocess.run(["chcp", "65001"], capture_output=True, check=False)
    except Exception:
        pass

    # 2. 启用ANSI转义序列支持
    try:
        import ctypes
        from ctypes import wintypes

        # 获取控制台句柄
        kernel32 = ctypes.windll.kernel32

        # 标准输出
        stdout_handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        if stdout_handle != -1:
            mode = wintypes.DWORD()
            if kernel32.GetConsoleMode(stdout_handle, ctypes.byref(mode)):
                # 启用虚拟终端处理 (ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004)
                new_mode = mode.value | 0x0004
                kernel32.SetConsoleMode(stdout_handle, new_mode)

        # 标准错误
        stderr_handle = kernel32.GetStdHandle(-12)  # STD_ERROR_HANDLE
        if stderr_handle != -1:
            mode = wintypes.DWORD()
            if kernel32.GetConsoleMode(stderr_handle, ctypes.byref(mode)):
                new_mode = mode.value | 0x0004
                kernel32.SetConsoleMode(stderr_handle, new_mode)

    except Exception:
        success = False

    # 3. 设置环境变量
    os.environ["PYTHONIOENCODING"] = "utf-8"

    return success


def setup_console_encoding() -> bool:
    """设置控制台编码

    Returns:
        bool: 是否成功设置
    """
    if sys.platform != "win32":
        return True

    try:
        # 设置标准输入输出编码
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
            return True
        else:
            # Python 3.6及以下版本的兼容性处理
            import io

            # 重新包装标准输出
            if (
                not isinstance(sys.stdout, io.TextIOWrapper)
                or sys.stdout.encoding.lower() != "utf-8"
            ):
                sys.stdout = io.TextIOWrapper(
                    sys.stdout.buffer, encoding="utf-8", errors="replace", newline="\n"
                )

            if (
                not isinstance(sys.stderr, io.TextIOWrapper)
                or sys.stderr.encoding.lower() != "utf-8"
            ):
                sys.stderr = io.TextIOWrapper(
                    sys.stderr.buffer, encoding="utf-8", errors="replace", newline="\n"
                )
            return True

    except Exception:
        return False


def check_color_support() -> bool:
    """检查终端是否支持颜色

    Returns:
        bool: 是否支持颜色
    """
    # 检查环境变量
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True

    # Windows特殊检查
    if sys.platform == "win32":
        # Windows Terminal
        if os.environ.get("WT_SESSION"):
            return True

        # VS Code终端
        if os.environ.get("TERM_PROGRAM") == "vscode":
            return True

        # PowerShell
        if os.environ.get("PSModulePath"):
            return True

        # 检查Windows 10版本（支持ANSI）
        try:
            import platform

            version = platform.version()
            # Windows 10 build 10586及以上支持ANSI
            if version and "10." in version:
                build = int(version.split(".")[-1])
                if build >= 10586:
                    return True
        except Exception:
            pass

        # 默认Windows cmd不支持颜色
        return False

    # Unix系统检查
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def get_safe_print_function():
    """获取安全的打印函数

    Returns:
        callable: 安全的打印函数
    """

    def safe_print(*args, **kwargs):
        try:
            print(*args, **kwargs)
        except UnicodeEncodeError:
            # 如果编码失败，使用ASCII安全模式
            safe_args = []
            for arg in args:
                if isinstance(arg, str):
                    safe_args.append(arg.encode("ascii", "replace").decode("ascii"))
                else:
                    safe_args.append(
                        str(arg).encode("ascii", "replace").decode("ascii")
                    )
            print(*safe_args, **kwargs)
        except Exception:
            # 最后的备用方案
            try:
                print("[输出编码错误]")
            except Exception:
                pass

    return safe_print


def initialize_windows_compatibility() -> dict:
    """初始化Windows兼容性

    Returns:
        dict: 初始化结果
    """
    result = {
        "platform": sys.platform,
        "console_setup": False,
        "encoding_setup": False,
        "color_support": False,
        "encoding": getattr(sys.stdout, "encoding", "unknown"),
    }

    if sys.platform == "win32":
        result["console_setup"] = setup_windows_console()
        result["encoding_setup"] = setup_console_encoding()
    else:
        result["console_setup"] = True
        result["encoding_setup"] = True

    result["color_support"] = check_color_support()
    result["final_encoding"] = getattr(sys.stdout, "encoding", "unknown")

    return result


if __name__ == "__main__":
    # 测试兼容性设置
    print("=== Windows兼容性测试 ===")
    result = initialize_windows_compatibility()

    for key, value in result.items():
        print(f"{key}: {value}")

    print("\n=== 字符测试 ===")
    safe_print = get_safe_print_function()
    safe_print("中文测试: 你好世界")
    safe_print("特殊字符: ①②③④⑤ αβγδε")
    safe_print("Emoji测试: 🔍 ℹ️ ⚠️ ❌ 🚨")
