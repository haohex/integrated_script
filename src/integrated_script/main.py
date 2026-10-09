#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main.py

主程序入口

默认启动 Textual 终端界面；``--legacy-cli`` 使用旧交互式界面；
``--build`` 调用打包脚本。GUI 使用独立的 console-free 入口``gui_main``。
"""

import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from .config import ConfigManager
from .core.logging_config import get_logger, setup_logging
from .ui.interactive import InteractiveInterface
from .version import get_version


def setup_argument_parser():
    """设置命令行参数解析器

    Returns:
        argparse.ArgumentParser: 配置好的参数解析器
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="integrated_script",
        description="集成脚本工具 - 提供图像处理、数据集处理等功能",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  %(prog)s                                  # 启动交互式界面
  %(prog)s --build                          # 调用打包脚本

更多信息请访问: https://github.com/your-repo/integrated_script
        """,
    )

    # 全局选项
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {get_version()}"
    )

    parser.add_argument("--config", type=str, help="配置文件路径 (JSON或YAML格式)")

    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
        help="日志级别 (默认: INFO)",
    )

    parser.add_argument("--log-file", type=str, help="日志文件路径")

    parser.add_argument("--no-color", action="store_true", help="禁用彩色输出")

    parser.add_argument("--quiet", action="store_true", help="静默模式，减少输出")

    parser.add_argument("--verbose", action="store_true", help="详细模式，增加输出")

    parser.add_argument(
        "--build", action="store_true", help="调用根目录的build_exe.py进行打包"
    )

    parser.add_argument(
        "--legacy-cli",
        action="store_true",
        help="使用旧的交互式命令行界面（兼容回退）",
    )

    parser.add_argument(
        "--gui",
        action="store_true",
        help="直接启动 Qt 桌面界面",
    )

    return parser


def default_log_dir() -> str:
    """解析默认日志目录（用户可写目录，而不是安装目录）。"""
    from .application.paths import AppPaths

    return str(AppPaths.resolve().log_dir)


def setup_logging_from_args(args) -> None:
    """根据命令行参数设置日志

    Args:
        args: 命令行参数
    """
    # 确定日志级别
    log_level = args.log_level
    if args.quiet:
        log_level = "WARNING"
    elif args.verbose:
        log_level = "DEBUG"

    # 设置日志：显式 --log-file 优先，否则写入用户可写日志目录，
    # 避免在只读安装目录（打包态）写入日志。
    if args.log_file:
        log_dir = str(Path(args.log_file).parent)
    else:
        log_dir = default_log_dir()

    setup_logging(log_dir=log_dir, log_level=log_level, enable_error_file=True)


def load_config_from_args(args) -> ConfigManager:
    """根据命令行参数加载配置

    Args:
        args: 命令行参数

    Returns:
        ConfigManager: 配置管理器实例
    """
    if not args.config:
        return ConfigManager()

    try:
        config_manager = ConfigManager(config_file=args.config, load_on_init=False)
        config_manager.load_from_file(args.config)
        logger = get_logger(__name__)
        logger.info(f"已加载配置文件: {args.config}")
        return config_manager
    except Exception as e:
        logger = get_logger(__name__)
        logger.error(f"加载配置文件失败: {e}")
        sys.exit(1)


def run_interactive_mode(config_manager: ConfigManager) -> int:
    """运行旧的交互式命令行模式（兼容回退）。

    Args:
        config_manager: 配置管理器

    Returns:
        int: 退出代码
    """
    try:
        interface = InteractiveInterface(config_manager)
        interface.run()
        return 0
    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
        return 130
    except Exception as e:
        logger = get_logger(__name__)
        logger.error(f"交互式模式运行失败: {e}")
        return 1


def run_tui_mode(
    config_manager: Optional[ConfigManager], working_directory: Path
) -> int:
    """运行 Textual 终端界面（默认入口，惰性导入）。"""
    try:
        from .application import AppService
        from .ui.tui.app import run_tui
    except ImportError as e:
        logger = get_logger(__name__)
        logger.error(f"无法加载终端界面: {e}")
        print("错误: 当前安装缺少 Textual 终端界面组件，可使用 --legacy-cli 回退。")
        return 1

    service = AppService(config=config_manager, working_directory=working_directory)
    try:
        return int(run_tui(service))
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        logger = get_logger(__name__)
        logger.error(f"终端界面运行失败: {e}")
        return 1
    finally:
        _safe_close(service)


def run_gui_mode(
    config_manager: Optional[ConfigManager], working_directory: Path
) -> int:
    """运行 Qt 桌面界面（独立 console-free 入口，惰性导入）。"""
    try:
        from .application import AppService
        from .ui.desktop.app import run_gui
    except ImportError as e:
        logger = get_logger(__name__)
        logger.error(f"无法加载桌面界面: {e}")
        print("错误: 当前安装缺少 Qt 桌面界面组件。")
        return 1

    service = AppService(config=config_manager, working_directory=working_directory)
    try:
        return int(run_gui(service))
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        logger = get_logger(__name__)
        logger.error(f"桌面界面运行失败: {e}")
        return 1
    finally:
        _safe_close(service)


def _safe_close(service) -> None:
    try:
        service.close()
    except Exception:  # noqa: BLE001 - 关闭失败不应影响退出码
        pass


def gui_main(argv: Optional[List[str]] = None) -> int:
    """独立的 GUI 入口（Windows 下 console-free）。

    与 ``main`` 共享参数解析与配置加载，但默认启动 Qt 界面，便于打包为
    无控制台窗口的可执行文件。
    """
    parser = setup_argument_parser()
    args = parser.parse_args(argv)
    setup_logging_from_args(args)
    logger = get_logger(__name__)

    try:
        config_manager = load_config_from_args(args) if args.config else None
        logger.info("启动桌面界面")
        return run_gui_mode(config_manager, Path.cwd())
    except Exception as e:
        logger.error(f"程序运行失败: {e}")
        return 1


def run_build_mode() -> int:
    """运行打包模式

    Returns:
        int: 退出代码
    """
    logger = get_logger(__name__)

    # 查找项目根目录的build_exe.py
    current_dir = Path(__file__).parent
    # 向上查找到项目根目录
    project_root = current_dir
    while project_root.parent != project_root:
        build_script = project_root / "build_exe.py"
        if build_script.exists():
            break
        project_root = project_root.parent
    else:
        # 如果没找到，尝试相对于当前文件的几个可能位置
        possible_paths = [
            current_dir / "../../../build_exe.py",  # 从src/integrated_script向上3级
            current_dir / "../../build_exe.py",  # 从src/integrated_script向上2级
            current_dir / "../build_exe.py",  # 从src/integrated_script向上1级
        ]

        build_script = None
        for path in possible_paths:
            if path.exists():
                build_script = path.resolve()
                project_root = build_script.parent
                break

        if not build_script:
            logger.error("找不到build_exe.py文件")
            print("错误: 找不到build_exe.py文件")
            return 1

    logger.info(f"找到打包脚本: {build_script}")
    print(f"正在调用打包脚本: {build_script}")

    try:
        # 调用build_exe.py
        result = subprocess.run(
            [sys.executable, str(build_script)],
            cwd=str(project_root),
            capture_output=False,  # 让输出直接显示给用户
        )

        if result.returncode == 0:
            logger.info("打包完成")
            print("\n✅ 打包完成!")
        else:
            logger.error(f"打包失败，退出代码: {result.returncode}")
            print(f"\n❌ 打包失败，退出代码: {result.returncode}")

        return result.returncode

    except Exception as e:
        logger.error(f"调用打包脚本失败: {e}")
        print(f"错误: 调用打包脚本失败: {e}")
        return 1


def main(argv: Optional[List[str]] = None) -> int:
    """主函数

    Args:
        argv: 命令行参数列表，如果为None则使用sys.argv

    Returns:
        int: 退出代码
    """
    # 解析命令行参数
    parser = setup_argument_parser()
    args = parser.parse_args(argv)

    # 设置日志
    setup_logging_from_args(args)
    logger = get_logger(__name__)

    try:
        # 检查是否为打包模式
        if args.build:
            logger.info("启动打包模式")
            return run_build_mode()

        # 仅显式 --config 时预先加载指定配置；默认 GUI/TUI 由应用层
        # 解析用户目录配置，避免在 cwd 创建 config.json。
        config_manager = load_config_from_args(args) if args.config else None

        # 旧交互式命令行回退（保持旧的 cwd 配置语义）
        if getattr(args, "legacy_cli", False):
            logger.info("启动旧交互式命令行模式")
            if config_manager is None:
                config_manager = ConfigManager()
            return run_interactive_mode(config_manager)

        # Qt 桌面界面
        if getattr(args, "gui", False):
            logger.info("启动桌面界面")
            return run_gui_mode(config_manager, Path.cwd())

        # 默认终端界面
        logger.info("启动终端界面")
        return run_tui_mode(config_manager, Path.cwd())

    except Exception as e:
        logger.error(f"程序运行失败: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
