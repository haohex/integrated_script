#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""终端交互适配器（legacy 回退，不依赖 Qt / Textual）。

``--legacy-cli`` 需要环境检查/依赖检查等操作仍然可用，同时新的 GUI/TUI
默认入口会用应用层交互替代终端输入。这里提供一个最小实现，复用既有的
终端提示语义，仅作为兼容回退，不参与新界面设计。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from ..config.settings import ConfigManager
from .contracts import ParameterSpec
from .operations import TaskContext
from .values import coerce_values

_TRUE_VALUES = {"y", "yes", "是", "1", "true"}


class ConsoleTaskContext(TaskContext):
    """通过 stdin/stdout 完成交互的任务上下文。"""

    def __init__(
        self,
        config: ConfigManager,
        working_directory: Path,
        *,
        input_func=None,
        output_func=None,
    ):
        super().__init__(config, working_directory)
        self._input = input_func or input
        self._output = output_func or print

    def log(self, message: str) -> None:
        if message:
            self._output(message)

    def progress(self, current: int, total: Optional[int], message: str = "") -> None:
        if total:
            percent = (current / total) * 100 if total else 0.0
            self._output(f"\r{message}: {percent:.1f}% ({current}/{total})", end="")
        elif message:
            self._output(message)

    def confirm(
        self,
        title: str,
        message: str,
        *,
        details: Sequence[str] = (),
        default: bool = False,
    ) -> bool:
        self._output(f"\n=== {title} ===")
        if message:
            self._output(message)
        for line in details:
            self._output(line)
        marker = "y" if default else "n"
        answer = self._input(f"是否继续? (y/n, 默认: {marker}): ").strip().lower()
        if not answer:
            return default
        return answer in _TRUE_VALUES

    def ask(
        self,
        title: str,
        message: str,
        fields: Sequence[ParameterSpec],
        *,
        kind: str = "input",
    ) -> Optional[Dict[str, Any]]:
        self._output(f"\n=== {title} ===")
        if message:
            self._output(message)

        raw: Dict[str, Any] = {}
        try:
            for spec in fields:
                if spec.kind == "bool":
                    answer = (
                        self._input(
                            f"{spec.label} (y/n, 默认: {'y' if spec.default else 'n'}): "
                        )
                        .strip()
                        .lower()
                    )
                    raw[spec.name] = spec.default if not answer else answer
                    continue

                default_text = "" if spec.default is None else f"[{spec.default}] "
                answer = self._input(f"{spec.label}: {default_text}")
                raw[spec.name] = answer if answer.strip() else spec.default

            return coerce_values(fields, raw, base_dir=self.working_directory)
        except (EOFError, KeyboardInterrupt):
            return None
        except ValueError as exc:
            self._output(f"输入无效: {exc}")
            return None


__all__ = ["ConsoleTaskContext"]
