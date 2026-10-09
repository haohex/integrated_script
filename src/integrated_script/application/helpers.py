#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""操作处理器共用的纯函数辅助。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DATASET_TYPE_NAMES = {
    "detection": "目标检测数据集",
    "segmentation": "目标分割数据集",
    "mixed": "混合格式数据集",
    "unknown": "未知类型数据集",
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def dataset_type_name(dataset_type: str) -> str:
    """数据集类型的中文展示名称。"""
    return DATASET_TYPE_NAMES.get(dataset_type, "未知类型")


def parse_size(size_text: Any) -> Tuple[int, int]:
    """解析 ``WxH`` 或单个数字为 ``(宽, 高)``。"""
    text = str(size_text or "").strip().lower()
    if not text:
        raise ValueError("目标尺寸不能为空")

    if "x" in text:
        parts = text.split("x")
        if len(parts) == 2:
            width = int(parts[0])
            height = int(parts[1])
            if width <= 0 or height <= 0:
                raise ValueError("目标尺寸必须为正整数")
            return (width, height)
        raise ValueError(f"无效的尺寸格式: {size_text}")

    value = int(text)
    if value <= 0:
        raise ValueError("目标尺寸必须为正整数")
    return (value, value)


def default_converted_output(input_path: Path, suffix: str = "_converted") -> str:
    """单文件/目录转换类操作的默认输出路径。"""
    if input_path.is_file():
        return str(input_path.parent / f"{input_path.stem}{suffix}")
    return str(input_path.parent / f"{input_path.name}{suffix}")


def detect_root_and_subdirs(dataset_dir: Path) -> Path:
    """若输入的是 images/labels 子目录，返回其数据集根目录。"""
    if dataset_dir.name.lower() in {"images", "labels"}:
        return dataset_dir.parent
    return dataset_dir


def scan_invalid_segmentation_files(
    dataset_path: Path,
) -> List[Tuple[Path, str]]:
    """扫描分割标签格式不符合要求的文件（只读）。

    只检查 ``labels`` 目录下的 ``*.txt``，与既有交互层判定保持一致：
    非空行至少 7 列、类别为整数、坐标为浮点数。
    """
    dataset_dir = detect_root_and_subdirs(Path(dataset_path))

    labels_dir = dataset_dir / "labels"
    if not labels_dir.exists():
        return []

    invalid_files: List[Tuple[Path, str]] = []

    for label_file in sorted(labels_dir.glob("*.txt")):
        try:
            with open(label_file, "r", encoding="utf-8") as handle:
                lines = handle.readlines()

            for line_num, line in enumerate(lines, 1):
                stripped = line.strip()
                if not stripped:
                    continue

                parts = stripped.split()
                if len(parts) < 7:
                    invalid_files.append(
                        (label_file, f"第{line_num}行只有{len(parts)}列，需要至少7列")
                    )
                    break

                try:
                    int(parts[0])
                except ValueError:
                    invalid_files.append(
                        (label_file, f"第{line_num}行类别'{parts[0]}'不是有效整数")
                    )
                    break

                try:
                    for coord in parts[1:]:
                        float(coord)
                except ValueError:
                    invalid_files.append((label_file, f"第{line_num}行包含无效坐标值"))
                    break
        except Exception as exc:  # noqa: BLE001
            invalid_files.append((label_file, f"读取文件失败: {exc}"))

    return invalid_files


def count_images(input_path: Path, recursive: bool) -> int:
    """统计输入路径下的图片数量。"""
    if input_path.is_file():
        return 1
    if not input_path.is_dir():
        return 0

    total = 0
    iterator = input_path.rglob("*") if recursive else input_path.iterdir()
    for entry in iterator:
        if entry.is_file() and entry.suffix.lower() in IMAGE_EXTENSIONS:
            total += 1
    return total


def count_deleted_files(deleted_files: Dict[str, Any]) -> int:
    """统计待删除文件总数。"""
    total = 0
    for value in (deleted_files or {}).values():
        if isinstance(value, (list, tuple, set)):
            total += len(value)
    return total


def deletion_details(deleted_files: Dict[str, Any], limit: int = 5) -> List[str]:
    """生成待删除文件的摘要行。"""
    labels = {
        "orphaned_images": "孤立图片",
        "orphaned_labels": "孤立标签",
        "invalid_labels": "无效标签",
        "empty_labels": "空标签",
    }
    details: List[str] = []
    for key, value in (deleted_files or {}).items():
        if not value:
            continue
        name = labels.get(key, key)
        details.append(f"{name}: {len(value)} 个")
        for item in list(value)[:limit]:
            details.append(f"  - {item}")
        if len(value) > limit:
            details.append(f"  ... 还有 {len(value) - limit} 个")
    return details


def parse_int_list(value: Any) -> List[int]:
    """解析逗号或空格分隔的整数列表。"""
    text = str(value or "").replace(",", " ").replace("，", " ")
    tokens = [token for token in text.split() if token]
    if not tokens:
        raise ValueError("至少需要一个整数")
    return [int(token) for token in tokens]


def normalize_optional_text(value: Any) -> Optional[str]:
    """空字符串归一化为 None。"""
    if value is None:
        return None
    text = str(value).strip()
    return text or None
