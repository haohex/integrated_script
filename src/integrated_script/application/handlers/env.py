#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""环境检查、依赖检查与工作目录维护操作。

这些操作覆盖原有「环境检查与配置」菜单，但改为通过应用层交互确认，
不再直接使用 ``input`` / ``print``。打包态（``sys.frozen``）下不会自动
调用 pip 下载，只报告缺失依赖，避免破坏离线约定。
"""

from __future__ import annotations

import importlib
import os
import platform
import sys
from pathlib import Path
from typing import Any, Dict, List

from ..operations import TaskContext

CATEGORY = "环境检查与配置"

PACKAGE_IMPORT_MAP = {
    "Pillow": "PIL",
    "opencv-python": "cv2",
    "opencv-python-headless": "cv2",
    "PyYAML": "yaml",
    "pyyaml": "yaml",
    "scikit-learn": "sklearn",
    "beautifulsoup4": "bs4",
    "python-dateutil": "dateutil",
}

WORKSPACE_DIRECTORIES = ("logs", "temp")

DEFAULT_CONFIG_YAML = """# 默认配置文件
logging:
  level: INFO
  file: logs/integrated_script.log

processing:
  batch_size: 100
  max_workers: 4

image:
  quality: 95
  format: JPEG
"""


def _distribution_to_import_name(distribution: str) -> str:
    if distribution in PACKAGE_IMPORT_MAP:
        return PACKAGE_IMPORT_MAP[distribution]
    return distribution.replace("-", "_").lower()


def _read_requirements(working_directory: Path) -> List[str]:
    requirements_file = working_directory / "requirements.txt"
    if not requirements_file.exists():
        return []
    lines = requirements_file.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


def _parse_requirement_name(requirement: str) -> str:
    for separator in ("==", ">=", "<=", ">", "<", "~=", "!="):
        if separator in requirement:
            return requirement.split(separator)[0].strip()
    return requirement.strip()


def environment_system_info() -> Dict[str, Any]:
    """收集系统环境信息。"""
    return {
        "platform": f"{platform.system()} {platform.release()}",
        "python_version": sys.version.split()[0],
        "python_executable": sys.executable,
        "working_directory": os.getcwd(),
        "running_frozen": bool(getattr(sys, "frozen", False)),
    }


def check_dependencies(working_directory: Path) -> Dict[str, Any]:
    """检查 requirements.txt 中的依赖是否可导入。"""
    requirements = _read_requirements(working_directory)
    installed: List[str] = []
    missing: List[str] = []

    for requirement in requirements:
        package_name = _parse_requirement_name(requirement)
        import_name = _distribution_to_import_name(package_name)
        try:
            importlib.import_module(import_name)
            installed.append(package_name)
        except ImportError:
            missing.append(package_name)

    return {
        "requirements_file": str(working_directory / "requirements.txt"),
        "installed_count": len(installed),
        "missing_count": len(missing),
        "installed": installed,
        "missing": missing,
    }


def initialize_workspace(working_directory: Path) -> Dict[str, Any]:
    """创建工作目录与默认配置。"""
    created: List[str] = []
    existing: List[str] = []

    for directory in WORKSPACE_DIRECTORIES:
        path = working_directory / directory
        if path.exists():
            existing.append(str(path))
        else:
            path.mkdir(parents=True, exist_ok=True)
            created.append(str(path))

    default_config = working_directory / "config" / "default_config.yaml"
    if default_config.exists():
        existing.append(str(default_config))
    else:
        default_config.parent.mkdir(parents=True, exist_ok=True)
        default_config.write_text(DEFAULT_CONFIG_YAML, encoding="utf-8")
        created.append(str(default_config))

    return {"created": created, "existing": existing}


def _is_exe() -> bool:
    return bool(getattr(sys, "frozen", False)) and hasattr(sys, "_MEIPASS")


def handle_check_system(context: TaskContext, values: Dict[str, Any]) -> Dict[str, Any]:
    info = environment_system_info()
    for key, value in info.items():
        context.log(f"{key}: {value}")
    return {"success": True, "system_info": info}


def handle_check_dependencies(
    context: TaskContext, values: Dict[str, Any]
) -> Dict[str, Any]:
    result = check_dependencies(context.working_directory)
    context.log(
        f"已安装 {result['installed_count']} 个依赖，缺失 {result['missing_count']} 个"
    )
    if result["missing"]:
        context.log("缺失依赖: " + ", ".join(result["missing"]))
    return {"success": True, "dependencies": result}


def handle_initialize_workspace(
    context: TaskContext, values: Dict[str, Any]
) -> Dict[str, Any]:
    result = initialize_workspace(context.working_directory)
    context.log(
        f"新建: {len(result['created'])} 项，已存在: {len(result['existing'])} 项"
    )
    return {"success": True, "workspace": result}


def handle_install_dependencies(
    context: TaskContext, values: Dict[str, Any]
) -> Dict[str, Any]:
    """安装缺失依赖（打包态拒绝，避免离线环境自动下载）。"""
    dependencies = check_dependencies(context.working_directory)
    if not dependencies["missing"]:
        context.log("所有依赖均已安装。")
        return {"success": True, "dependencies": dependencies}

    if _is_exe():
        context.log(
            "当前为打包运行环境，不会自动执行 pip 下载；请使用源码环境维护依赖。"
        )
        return {
            "success": False,
            "error": "打包环境不支持自动安装依赖",
            "dependencies": dependencies,
        }

    if not context.confirm(
        "安装缺失依赖",
        "是否使用当前 Python 安装缺失依赖（需要联网）？",
        details=tuple(f"- {name}" for name in dependencies["missing"]),
        default=False,
    ):
        return {"success": True, "cancelled": True, "dependencies": dependencies}

    import subprocess

    completed = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
        cwd=str(context.working_directory),
        capture_output=True,
        text=True,
    )
    context.log(f"pip 退出码: {completed.returncode}")
    if completed.returncode != 0:
        context.log(completed.stderr.strip()[-2000:])

    return {
        "success": completed.returncode == 0,
        "dependencies": check_dependencies(context.working_directory),
    }


def handle_auto_fix_environment(
    context: TaskContext, values: Dict[str, Any]
) -> Dict[str, Any]:
    system_info = environment_system_info()
    dependencies = check_dependencies(context.working_directory)
    context.log(f"操作系统: {system_info['platform']}")
    context.log(f"Python: {system_info['python_version']}")

    if dependencies["missing"]:
        context.log("检测到缺失依赖: " + ", ".join(dependencies["missing"]))
        if _is_exe():
            context.log("当前为打包运行环境，不会自动执行 pip 下载。")
        install = context.confirm(
            "安装缺失依赖",
            "是否尝试使用当前 Python 安装缺失依赖（需要联网）？",
            details=[f"- {name}" for name in dependencies["missing"]],
            default=False,
        )
        if install:
            if _is_exe():
                context.log("打包环境跳过自动安装；请使用源码环境维护。")
            else:
                import subprocess

                completed = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pip",
                        "install",
                        "-r",
                        "requirements.txt",
                    ],
                    cwd=str(context.working_directory),
                    capture_output=True,
                    text=True,
                )
                context.log(f"pip 退出码: {completed.returncode}")
                if completed.returncode != 0:
                    context.log(completed.stderr.strip()[-2000:])
        else:
            context.log("已跳过依赖安装。")

    workspace = initialize_workspace(context.working_directory)
    context.log("工作目录已就绪。")

    return {
        "success": not dependencies["missing"],
        "system_info": system_info,
        "dependencies": dependencies,
        "workspace": workspace,
    }


__all__ = [
    "CATEGORY",
    "environment_system_info",
    "check_dependencies",
    "initialize_workspace",
    "handle_check_system",
    "handle_check_dependencies",
    "handle_initialize_workspace",
    "handle_install_dependencies",
    "handle_auto_fix_environment",
]
