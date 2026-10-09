#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""标签处理相关操作处理器。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from ...application.contracts import ParameterSpec
from ...processors import LabelProcessor
from ...workflows import LabelWorkflow
from ..helpers import parse_int_list
from ..operations import TaskContext

CATEGORY = "标签处理"


def _workflow(context: TaskContext) -> LabelWorkflow:
    return LabelWorkflow(LabelProcessor(config=context.config))


def handle_create_empty(context: TaskContext, values: Dict[str, Any]) -> Dict[str, Any]:
    workflow = _workflow(context)
    images_dir = Path(values["images_dir"])
    labels_dir = values.get("labels_dir") or str(images_dir.parent / "labels")

    context.log("正在创建空标签文件...")
    return workflow.create_empty_labels(
        str(images_dir),
        labels_dir=str(labels_dir),
        overwrite=bool(values.get("overwrite", False)),
    )


def handle_flip(context: TaskContext, values: Dict[str, Any]) -> Dict[str, Any]:
    workflow = _workflow(context)
    context.log("正在翻转标签坐标...")
    return workflow.flip_labels(
        values["labels_dir"],
        flip_type=values.get("flip_type", "horizontal"),
        backup=bool(values.get("backup", True)),
    )


def handle_filter(context: TaskContext, values: Dict[str, Any]) -> Dict[str, Any]:
    workflow = _workflow(context)
    raw_classes = values.get("classes")
    if isinstance(raw_classes, (list, tuple)):
        target_classes = [int(item) for item in raw_classes]
    else:
        target_classes = parse_int_list(raw_classes)

    context.log("正在过滤标签类别...")
    return workflow.filter_labels_by_class(
        values["labels_dir"],
        target_classes=target_classes,
        action=values.get("action", "keep"),
        backup=bool(values.get("backup", True)),
    )


def _read_classes(context: TaskContext, dataset_dir: Path) -> List[str] | None:
    classes_file = dataset_dir / "classes.txt"
    if not classes_file.exists():
        context.log(f"未找到 classes.txt 文件: {classes_file}")
        return None
    try:
        with open(classes_file, "r", encoding="utf-8") as handle:
            classes = [line.strip() for line in handle.readlines() if line.strip()]
    except Exception as exc:  # noqa: BLE001
        context.log(f"读取 classes.txt 失败: {exc}")
        return None
    if not classes:
        context.log("classes.txt 文件为空")
        return None
    return classes


def handle_remove_empty(context: TaskContext, values: Dict[str, Any]) -> Dict[str, Any]:
    workflow = _workflow(context)
    images_subdir = values.get("images_subdir") or "images"
    labels_subdir = values.get("labels_subdir") or "labels"

    if not context.confirm(
        "确认删除空标签及对应图像",
        "此操作将永久删除文件，是否继续？",
        default=False,
    ):
        return {"success": True, "cancelled": True}

    context.log("正在删除空标签及对应图像...")
    return workflow.remove_empty_labels_and_images(
        values["dataset_dir"],
        images_subdir=images_subdir,
        labels_subdir=labels_subdir,
    )


def handle_remove_class(context: TaskContext, values: Dict[str, Any]) -> Dict[str, Any]:
    workflow = _workflow(context)
    dataset_dir = Path(values["dataset_dir"])
    classes = _read_classes(context, dataset_dir)
    if classes is None:
        return {"success": False, "error": "无法读取 classes.txt"}

    context.log("数据集类别列表:")
    for index, name in enumerate(classes):
        context.log(f"  {index}: {name}")

    if values.get("target_class") in (None, ""):
        response = context.ask(
            "选择要删除的类别",
            f"请选择要删除的类别编号 (0-{len(classes) - 1})。",
            [
                ParameterSpec(
                    name="target_class",
                    label="类别编号",
                    kind="int",
                    required=True,
                )
            ],
        )
        if response is None:
            return {"success": True, "cancelled": True}
        target_class = int(response["target_class"])
    else:
        target_class = int(values["target_class"])

    if target_class < 0 or target_class >= len(classes):
        return {"success": False, "error": f"类别编号越界: {target_class}"}

    class_name = classes[target_class]
    images_subdir = values.get("images_subdir") or "images"
    labels_subdir = values.get("labels_subdir") or "labels"

    if not context.confirm(
        "确认删除指定类别",
        f"此操作将永久删除只包含类别 {target_class}({class_name}) 的文件，是否继续？",
        default=False,
    ):
        return {"success": True, "cancelled": True}

    context.log(f"正在删除只包含类别 {target_class}({class_name}) 的标签及图像...")
    return workflow.remove_labels_with_only_class(
        str(dataset_dir),
        target_class=target_class,
        images_subdir=images_subdir,
        labels_subdir=labels_subdir,
    )
