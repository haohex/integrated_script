#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一应用层公开契约。

这些类型是 GUI / TUI 与后端之间冻结的接口，字段与方法签名不得随意更改。
任何前端都只依赖这里的类型，不直接导入 processors / workflows。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Tuple

from ..contracts.results import OperationResult

__all__ = [
    "ParameterSpec",
    "OperationSpec",
    "InteractionRequest",
    "TaskEvent",
]


@dataclass(frozen=True)
class ParameterSpec:
    """单个输入字段描述。

    Attributes:
        name: 字段键名（提交时使用的键）。
        label: 界面展示名称。
        kind: 字段类型，``str``/``text``/``path``/``paths``/``int``/``float``/
            ``bool``/``choice``。
        default: 默认值。
        required: 是否必填。
        choices: 选项列表，元素为 ``(显示名称, 实际值)``。
        help: 帮助说明。
    """

    name: str
    label: str
    kind: str = "str"
    default: Any = None
    required: bool = False
    choices: Tuple[Tuple[str, Any], ...] = ()
    help: str = ""


@dataclass(frozen=True)
class OperationSpec:
    """单个可执行操作的描述。"""

    id: str
    category: str
    label: str
    description: str
    fields: Tuple[ParameterSpec, ...] = ()
    destructive: bool = False


@dataclass(frozen=True)
class InteractionRequest:
    """后端向前端发起的交互请求。

    Attributes:
        kind: ``input`` 表示需要字段输入，``confirm`` 表示需要确认（前端提交
            ``{"confirmed": bool}``）。
    """

    id: str
    title: str
    message: str
    fields: Tuple[ParameterSpec, ...] = ()
    kind: str = "input"
    details: Tuple[str, ...] = ()


@dataclass(frozen=True)
class TaskEvent:
    """任务事件，携带所属任务 ID。"""

    task_id: str
    kind: str  # started, progress, log, interaction, completed
    message: str = ""
    current: int | None = None
    total: int | None = None
    interaction: InteractionRequest | None = None
    result: OperationResult | None = None
