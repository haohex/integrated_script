#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""应用层结果规范化。

处理器/工作流对外返回的是历史 legacy dict，其中部分操作（例如
``YOLOProcessor.get_dataset_statistics``）只有 ``valid``/``statistics.is_valid``
而没有 ``success`` 字段。``OperationResult.from_legacy`` 会把缺失的 ``success``
当作 ``False``，导致真实有效的数据集被误判为失败。

这里在应用适配层补全语义，**不修改 processor/workflow 契约**：
- 仅在缺少 ``success`` 时根据已知语义键推断；
- 推断为失败且缺少错误信息时补一条可读错误；
- 已有 ``success``（含显式 ``False``）原样保留，不覆盖处理器结论。
"""

from __future__ import annotations

from typing import Any, Dict


def _infer_success(data: Dict[str, Any]) -> bool | None:
    """根据 legacy dict 的已知语义键推断 success，无法推断返回 None。"""
    # 取消结果是成功空操作，优先于统计有效性。
    if data.get("cancelled") is True or data.get("stage") == "cancelled":
        return True

    if isinstance(data.get("valid"), bool):
        return data["valid"]

    statistics = data.get("statistics")
    if isinstance(statistics, dict) and "is_valid" in statistics:
        return bool(statistics["is_valid"])

    if "consistent" in data:
        return bool(data["consistent"])

    return None


def _default_failure_message(data: Dict[str, Any]) -> str:
    """为缺少错误信息的失败结果生成可读信息。"""
    issues = data.get("issues")
    if isinstance(issues, (list, tuple)) and issues:
        return f"数据集验证未通过：发现 {len(issues)} 项问题"
    if "valid" in data:
        return "数据集验证未通过"
    if "consistent" in data:
        return "数据集类别不一致"
    return "操作未成功"


def normalize_legacy_result(legacy: Any) -> Dict[str, Any]:
    """返回补全 ``success``/``error`` 语义后的 legacy dict。"""
    data = dict(legacy or {})

    if "success" not in data or data.get("success") is None:
        inferred = _infer_success(data)
        if inferred is not None:
            data["success"] = inferred

    if (
        data.get("success") is False
        and not data.get("error")
        and not data.get("message")
    ):
        data["error"] = _default_failure_message(data)

    return data


__all__ = ["normalize_legacy_result"]
