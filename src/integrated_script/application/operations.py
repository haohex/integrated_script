#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""操作模型与任务上下文契约。

``TaskContext`` 是操作处理器与运行器之间的最小接口：处理器只通过它做确认、
提问、进度与日志，便于在不依赖 Qt / Textual 的情况下直接单元测试。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ..config.settings import ConfigManager
from .contracts import InteractionRequest, OperationSpec, ParameterSpec


class TaskContext:
    """操作处理器可用能力的基类（运行器负责实现）。

    处理器不得直接使用 ``input`` / ``print`` / ``tqdm``；所有交互都通过本类。
    """

    def __init__(self, config: ConfigManager, working_directory: Path):
        self.config = config
        self.working_directory = working_directory

    # ---- 交互 -----------------------------------------------------------
    def confirm(
        self,
        title: str,
        message: str,
        *,
        details: Sequence[str] = (),
        default: bool = False,
    ) -> bool:
        """请求确认，返回用户是否确认。"""
        raise NotImplementedError

    def ask(
        self,
        title: str,
        message: str,
        fields: Sequence[ParameterSpec],
        *,
        kind: str = "input",
    ) -> Optional[Dict[str, Any]]:
        """请求字段输入，返回已解析的值或 None（取消/关闭）。"""
        raise NotImplementedError

    # ---- 进度 / 日志 ----------------------------------------------------
    def log(self, message: str) -> None:
        """记录一条任务日志。"""
        raise NotImplementedError

    def progress(self, current: int, total: Optional[int], message: str = "") -> None:
        """上报进度（total 为 None 表示不确定总量）。"""
        raise NotImplementedError

    # core.progress 的 sink 协议实现
    def progress_started(self, description: str, total: int, unit: str) -> None:
        self.progress(0, total or None, description)

    def progress_updated(self, current: int, total: int, description: str = "") -> None:
        self.progress(current, total or None, description)

    def progress_closed(self, current: int, total: int) -> None:
        self.progress(current, total or None, "")

    def progress_postfix(self, values: Dict[str, Any]) -> None:
        _ = values


@dataclass(frozen=True)
class Operation:
    """操作定义：公开描述 + 处理器 + 使用的字段。"""

    spec: OperationSpec
    handler: Callable[[TaskContext, Dict[str, Any]], Dict[str, Any]]
    fields: Tuple[ParameterSpec, ...] = field(default_factory=tuple)

    @property
    def id(self) -> str:
        return self.spec.id


@dataclass
class TaskState:
    """一次任务的可变状态。"""

    task_id: str
    operation: Operation
    values: Dict[str, Any]
    interaction: Optional[InteractionRequest] = None
    response: Optional[Dict[str, Any]] = None
    cancelled: bool = False
    events: List[Any] = field(default_factory=list)


__all__ = ["TaskContext", "Operation", "TaskState"]
