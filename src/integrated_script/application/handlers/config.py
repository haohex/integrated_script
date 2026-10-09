#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""配置管理相关操作处理器。

配置读写保持既有的扁平结构（复用 ``ConfigManager``），GUI/TUI 只通过
应用层读取/修改。主题等界面偏好由前端自行保存，不写入业务配置。
"""

from __future__ import annotations

import copy
import json
from typing import Any, Dict

from ...config.settings import ConfigManager
from ..contracts import ParameterSpec
from ..operations import TaskContext

CATEGORY = "配置管理"

_ALLOWED_INTERFACE_THEMES = {"system", "light", "dark"}


def _load_config_file(context: TaskContext, config_file: str) -> ConfigManager:
    temp = ConfigManager(config_file=config_file, auto_save=False, load_on_init=False)
    temp.load_from_file(config_file)
    return temp


def handle_view_config(context: TaskContext, values: Dict[str, Any]) -> Dict[str, Any]:
    config = context.config.get_all()
    context.log("=== 当前配置 ===")
    for section, section_values in config.items():
        context.log(f"[{section}]")
        if isinstance(section_values, dict):
            for key, value in section_values.items():
                context.log(f"  {key}: {value}")
        else:
            context.log(f"  {section_values}")
    return {
        "success": True,
        "config": config,
        "config_file": str(context.config.config_file),
    }


def handle_load_config(context: TaskContext, values: Dict[str, Any]) -> Dict[str, Any]:
    config_file = values["config_file"]
    temp = _load_config_file(context, config_file)
    context.config.update(temp.get_all())
    context.log(f"配置文件已加载: {config_file}")
    return {
        "success": True,
        "config_file": config_file,
        "config": context.config.get_all(),
    }


def handle_save_config(context: TaskContext, values: Dict[str, Any]) -> Dict[str, Any]:
    config_file = values["config_file"]
    context.config.save_to_file(config_file)
    context.log(f"配置已保存到: {config_file}")
    return {"success": True, "config_file": config_file}


def handle_reset_config(context: TaskContext, values: Dict[str, Any]) -> Dict[str, Any]:
    if not context.confirm("重置配置", "确认重置为默认配置？", default=False):
        return {"success": True, "cancelled": True}
    context.config.reset()
    context.log("配置已重置为默认值")
    return {"success": True, "config": context.config.get_all()}


def handle_edit_config(context: TaskContext, values: Dict[str, Any]) -> Dict[str, Any]:
    """修改配置：只更新提供的字段，未提供的保持原值。"""
    updates: Dict[str, Any] = {}

    if values.get("log_level"):
        context.config.set("log_level", values["log_level"])
        updates["log_level"] = values["log_level"]

    for section in ("paths", "processing", "image_processing", "yolo", "ui"):
        section_values = {
            key: value
            for key, value in values.items()
            if key.startswith(f"{section}__") and value not in (None, "")
        }
        if not section_values:
            continue
        for key, value in section_values.items():
            real_key = key.split("__", 1)[1]
            context.config.set(f"{section}.{real_key}", value)
            updates.setdefault(section, {})[real_key] = value

    context.log("配置已更新")
    return {"success": True, "config": context.config.get_all(), "updates": updates}


def handle_set_log_level(
    context: TaskContext, values: Dict[str, Any]
) -> Dict[str, Any]:
    level = str(values["log_level"]).upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
        return {"success": False, "error": f"无效的日志级别: {level}"}

    context.config.set("log_level", level)
    try:
        from ...core.logging_config import set_log_level

        set_log_level(level)
    except Exception as exc:  # noqa: BLE001
        context.log(f"应用日志级别时出现问题: {exc}")

    context.log(f"日志级别已设置为: {level}")
    return {"success": True, "log_level": level}


# 供操作目录使用的字段定义
LOG_LEVEL_FIELDS = (
    ParameterSpec(
        name="log_level",
        label="日志级别",
        kind="choice",
        default="INFO",
        required=True,
        choices=(
            ("DEBUG - 详细调试信息", "DEBUG"),
            ("INFO - 一般信息", "INFO"),
            ("WARNING - 警告信息", "WARNING"),
            ("ERROR - 错误信息", "ERROR"),
        ),
    ),
)

ALLOWED_THEMES = _ALLOWED_INTERFACE_THEMES


def validate_config_json(text: str) -> Dict[str, Any]:
    """校验配置 JSON 文本（前端导入用）。"""
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("配置根对象必须是字典")
    return copy.deepcopy(data)


__all__ = [
    "CATEGORY",
    "handle_view_config",
    "handle_load_config",
    "handle_save_config",
    "handle_reset_config",
    "handle_edit_config",
    "handle_set_log_level",
    "LOG_LEVEL_FIELDS",
    "validate_config_json",
]
