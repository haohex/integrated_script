#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""统一应用层。

公开冻结契约：``ParameterSpec`` / ``OperationSpec`` / ``InteractionRequest`` /
``TaskEvent`` / ``AppService``。前端只依赖本包，不直接导入 processors。

本包不导入 Qt / Textual。
"""

from .contracts import InteractionRequest, OperationSpec, ParameterSpec, TaskEvent
from .paths import AppPaths
from .service import AppService, TaskClosedError
from .values import ValueCoercionError

__all__ = [
    "ParameterSpec",
    "OperationSpec",
    "InteractionRequest",
    "TaskEvent",
    "AppService",
    "AppPaths",
    "TaskClosedError",
    "ValueCoercionError",
]
