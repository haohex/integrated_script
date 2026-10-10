#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""应用层结果规范化测试（真实 legacy dict 形状）。"""

from integrated_script.application.results import normalize_legacy_result
from integrated_script.contracts.results import OperationResult


def test_statistics_result_with_valid_flag_is_normalized_to_success() -> None:
    """``get_dataset_statistics_internal`` 只返回 valid，没有 success。"""
    legacy = {
        "statistics": {"is_valid": True, "total_images": 2},
        "valid": True,
        "classes_file": None,
        "issues": [],
    }

    normalized = normalize_legacy_result(legacy)

    assert normalized["success"] is True
    assert normalized["valid"] is True
    assert OperationResult.from_legacy(normalized).success is True


def test_invalid_statistics_result_is_failure_with_readable_error() -> None:
    legacy = {
        "statistics": {"is_valid": False, "orphaned_images": 1},
        "valid": False,
        "issues": [{"type": "orphaned_images", "count": 1}],
    }

    normalized = normalize_legacy_result(legacy)

    assert normalized["success"] is False
    assert normalized["error"]
    result = OperationResult.from_legacy(normalized)
    assert result.success is False
    assert result.message


def test_existing_success_is_never_overridden() -> None:
    legacy = {"success": False, "valid": True, "error": "写入失败"}

    normalized = normalize_legacy_result(legacy)

    assert normalized["success"] is False
    assert normalized["error"] == "写入失败"


def test_classes_consistency_result_is_normalized() -> None:
    consistent = {"consistent": True, "classes": ["a"], "details": "ok"}
    inconsistent = {"consistent": False, "classes": None, "details": "不一致"}

    assert normalize_legacy_result(consistent)["success"] is True
    failed = normalize_legacy_result(inconsistent)
    assert failed["success"] is False
    assert failed["error"]


def test_unknown_shape_without_semantics_is_left_for_from_legacy() -> None:
    legacy = {"total_files": 3, "failed_files": []}

    normalized = normalize_legacy_result(legacy)

    assert "success" not in normalized
    assert OperationResult.from_legacy(normalized).success is False


def test_cancelled_result_is_treated_as_successful_noop() -> None:
    legacy = {"cancelled": True, "statistics": {"is_valid": False}}

    normalized = normalize_legacy_result(legacy)

    assert normalized["success"] is True
