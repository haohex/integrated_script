#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""输入值解析与类型强制。

应用层统一负责把前端提交的原始值（字符串 / 布尔 / 选择值）转换为业务需要的
Python 类型。前端只负责收集，不做业务语义解析。

路径规则：
- 只剥离成对的外层引号，展开 ``~`` 与环境变量；
- 相对路径基于捕获的工作目录解析；
- POSIX 下反斜杠是合法文件名，不做 Windows 风格替换；
- POSIX 下检测到 Windows 盘符或 UNC 路径时给出可操作的错误，不做猜测映射。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Iterable, List, Optional

from .contracts import ParameterSpec

_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_UNC_RE = re.compile(r"^(\\\\|//)")

_TRUE_VALUES = {"y", "yes", "是", "1", "true", "on"}
_FALSE_VALUES = {"n", "no", "否", "0", "false", "off"}

PATH_KINDS = {"path", "paths"}


class ValueCoercionError(ValueError):
    """字段值解析失败。"""


def _strip_paired_quotes(value: str) -> str:
    """仅剥离成对的外层引号，保留内部内容原样。"""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _is_foreign_windows_path(value: str) -> bool:
    return bool(_WINDOWS_DRIVE_RE.match(value) or _UNC_RE.match(value))


def parse_path(value: Any, *, base_dir: Optional[Path] = None) -> str:
    """解析单个路径字段，返回字符串形式路径。"""
    if value is None:
        raise ValueCoercionError("路径不能为空")

    raw = str(value).strip()
    if not raw:
        raise ValueCoercionError("路径不能为空")

    raw = _strip_paired_quotes(raw)
    raw = os.path.expanduser(os.path.expandvars(raw))

    if not raw:
        raise ValueCoercionError("路径不能为空")

    if os.name != "nt" and _is_foreign_windows_path(raw):
        raise ValueCoercionError(
            f"路径 {raw!r} 看起来是 Windows 盘符或 UNC 路径，当前系统无法直接访问。"
            "请在当前系统上提供本地路径（例如挂载后的 POSIX 路径或相对路径）。"
        )

    path = Path(raw)
    if not path.is_absolute():
        base = base_dir if base_dir is not None else Path.cwd()
        path = Path(os.path.abspath(str(base / raw)))
    return str(path)


def split_paths(value: Any) -> List[str]:
    """把换行分隔的多路径文本拆分为路径列表。"""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        items: Iterable[Any] = value
    else:
        items = str(value).splitlines()

    result: List[str] = []
    for item in items:
        text = str(item).strip()
        if text:
            result.append(text)
    return result


def parse_paths(value: Any, *, base_dir: Optional[Path] = None) -> List[str]:
    """解析多路径字段（换行或列表），返回路径字符串列表。"""
    return [parse_path(item, base_dir=base_dir) for item in split_paths(value)]


def parse_bool(value: Any) -> bool:
    """把前端值转换为布尔值。"""
    if isinstance(value, bool):
        return value
    if value is None:
        raise ValueCoercionError("需要布尔值")
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)

    text = str(value).strip().lower()
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    raise ValueCoercionError(f"无法识别的布尔值: {value!r}")


def _resolve_choice(spec: ParameterSpec, value: Any) -> Any:
    for label, actual in spec.choices:
        if value == actual or str(value) == str(actual) or str(value) == str(label):
            return actual
    raise ValueCoercionError(f"字段 {spec.label} 的值 {value!r} 不在允许的选项中")


def coerce_value(
    spec: ParameterSpec,
    value: Any,
    *,
    base_dir: Optional[Path] = None,
) -> Any:
    """按字段类型强制转换单个值。"""
    kind = spec.kind

    if kind in ("str", "text"):
        return "" if value is None else str(value)
    if kind == "path":
        return parse_path(value, base_dir=base_dir)
    if kind == "paths":
        return parse_paths(value, base_dir=base_dir)
    if kind == "int":
        if isinstance(value, bool):
            raise ValueCoercionError(f"字段 {spec.label} 需要整数")
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            raise ValueCoercionError(f"字段 {spec.label} 需要整数，收到 {value!r}")
    if kind == "float":
        try:
            return float(str(value).strip())
        except (TypeError, ValueError):
            raise ValueCoercionError(f"字段 {spec.label} 需要数字，收到 {value!r}")
    if kind == "bool":
        return parse_bool(value)
    if kind == "choice":
        return _resolve_choice(spec, value)

    raise ValueCoercionError(f"未知字段类型: {kind}")


def _is_empty(spec: ParameterSpec, value: Any) -> bool:
    if value is None:
        return True
    if spec.kind == "paths":
        return len(value) == 0
    if spec.kind in ("str", "text", "path"):
        return str(value).strip() == ""
    return False


def coerce_values(
    fields: Iterable[ParameterSpec],
    values: dict,
    *,
    base_dir: Optional[Path] = None,
) -> dict:
    """按字段定义强制转换整个提交值字典。

    未提供的字段使用默认值；默认值为 None 且必填时给出中文错误。
    """
    result: dict = {}
    values = values or {}

    for spec in fields:
        if spec.name in values:
            raw = values[spec.name]
        else:
            raw = spec.default

        if _is_empty(spec, raw):
            if spec.required:
                raise ValueCoercionError(f"字段「{spec.label}」为必填项")
            result[spec.name] = raw
            continue

        result[spec.name] = coerce_value(spec, raw, base_dir=base_dir)

    return result


__all__ = [
    "ValueCoercionError",
    "parse_path",
    "parse_paths",
    "split_paths",
    "parse_bool",
    "coerce_value",
    "coerce_values",
]
