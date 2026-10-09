#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""YOLO 数据集相关操作处理器。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from ...processors import YOLOProcessor
from ...workflows import YoloWorkflow
from ..contracts import ParameterSpec
from ..helpers import (
    count_deleted_files,
    dataset_type_name,
    deletion_details,
    normalize_optional_text,
)
from ..operations import TaskContext

CATEGORY = "YOLO数据集处理"


def _workflow(context: TaskContext) -> YoloWorkflow:
    return YoloWorkflow(YOLOProcessor(config=context.config))


def _resolve_dataset_type(
    context: TaskContext,
    detected_type: str,
    confidence: float,
    *,
    stats: Dict[str, Any],
) -> str | None:
    """复现旧交互的数据集类型确认/切换逻辑。"""
    stats_lines = [f"{key}: {value}" for key, value in stats.items()]

    if detected_type == "mixed" or confidence < 0.8:
        context.log(
            f"检测结果: {dataset_type_name(detected_type)} (置信度 {confidence:.1%})"
        )
        for line in stats_lines:
            context.log(line)
        return _confirm_type(context, default=None)

    confirmed = context.confirm(
        "确认数据集类型",
        f"确认数据集类型为 {dataset_type_name(detected_type)}（置信度 {confidence:.1%}）吗？",
        details=tuple(stats_lines),
        default=True,
    )
    if confirmed:
        return detected_type
    return _confirm_type(context, default=None)


def _confirm_type(context: TaskContext, default: str | None) -> str | None:
    """让用户手动选择检测/分割/取消。"""
    field = ParameterSpec(
        name="dataset_type",
        label="数据集类型",
        kind="choice",
        default=default or "detection",
        required=True,
        choices=(
            ("目标检测数据集", "detection"),
            ("目标分割数据集", "segmentation"),
            ("取消处理", "cancel"),
        ),
    )
    response = context.ask(
        "选择数据集类型",
        "未自动确认，请手动选择数据集类型。",
        [field],
    )
    if response is None:
        return None
    choice = response.get("dataset_type")
    if choice == "cancel":
        return None
    return choice


def handle_process_ctds_dataset(
    context: TaskContext, values: Dict[str, Any]
) -> Dict[str, Any]:
    workflow = _workflow(context)
    dataset_path = values["dataset_path"]
    output_name = normalize_optional_text(values.get("output_name"))
    keep_empty_labels = bool(values.get("keep_empty_labels", False))

    context.log("正在预检测数据集类型...")
    result = workflow.process_ctds_dataset(
        dataset_path,
        output_name=output_name,
        keep_empty_labels=keep_empty_labels,
    )

    if result.get("stage") == "pre_detection":
        pre_detection = result.get("pre_detection_result", {})
        detected_type = pre_detection.get("dataset_type", "unknown")
        confidence = float(pre_detection.get("confidence", 0.0))
        stats = pre_detection.get("statistics", {}) or {}

        confirmed_type = _resolve_dataset_type(
            context, detected_type, confidence, stats=stats
        )
        if not confirmed_type:
            return {"success": True, "cancelled": True, "stage": "cancelled"}

        context.log(f"正在处理 {dataset_type_name(confirmed_type)} 数据...")
        result = workflow.continue_ctds_processing(
            result, confirmed_type, keep_empty_labels=keep_empty_labels
        )

    return result


def handle_convert_yolo_to_ctds(
    context: TaskContext, values: Dict[str, Any]
) -> Dict[str, Any]:
    workflow = _workflow(context)
    context.log("正在将 YOLO 数据集封装为 CTDS...")
    return workflow.convert_yolo_to_ctds_dataset(
        values["dataset_path"],
        output_path=normalize_optional_text(values.get("output_path")),
    )


def handle_yolo_to_xlabel(
    context: TaskContext, values: Dict[str, Any]
) -> Dict[str, Any]:
    workflow = _workflow(context)
    dataset_path = values["dataset_path"]
    output_dir = normalize_optional_text(values.get("output_path"))
    requested = values.get("dataset_type", "auto")

    if requested == "auto":
        detection = workflow.detect_yolo_dataset_type(dataset_path)
        if not detection.get("success", True):
            return detection
        detected_type = detection.get("detected_type", "unknown")
        if detected_type == "unknown":
            return {
                "success": False,
                "error": "未检测到有效标签，无法自动判断数据集类型",
            }
        confirmed_type = _resolve_dataset_type(
            context,
            detected_type,
            float(detection.get("confidence", 0.0)),
            stats=detection.get("statistics", {}) or {},
        )
        if not confirmed_type:
            return {"success": True, "cancelled": True}
    else:
        confirmed_type = requested

    if confirmed_type == "segmentation":
        context.log("正在转换为 X-label 分割格式...")
        return workflow.convert_yolo_to_xlabel_segmentation(
            dataset_path, output_dir=output_dir
        )

    context.log("正在转换为 X-label 检测格式...")
    return workflow.convert_yolo_to_xlabel(dataset_path, output_dir=output_dir)


def _parse_class_order(classes: List[str], raw: Any) -> List[str]:
    default = sorted(classes)
    text = str(raw or "").strip()
    if not text:
        return default
    try:
        indexes = [int(token) for token in text.split()]
        if len(indexes) != len(default):
            raise ValueError("数量不一致")
        if set(indexes) != set(range(len(default))):
            raise ValueError("编号不合法")
        return [default[index] for index in indexes]
    except Exception:
        return default


def handle_xlabel_to_yolo(
    context: TaskContext, values: Dict[str, Any]
) -> Dict[str, Any]:
    workflow = _workflow(context)
    dataset_path = values["dataset_path"]
    output_dir = normalize_optional_text(values.get("output_path"))
    requested = values.get("dataset_type", "auto")

    if requested == "auto":
        detection = workflow.detect_xlabel_dataset_type(dataset_path)
        if not detection.get("success", True):
            return detection
        detected_type = detection.get("detected_type", "unknown")
        if detected_type == "unknown":
            return {
                "success": False,
                "error": "未检测到有效标注，无法自动判断数据集类型",
            }
        confirmed_type = _resolve_dataset_type(
            context,
            detected_type,
            float(detection.get("confidence", 0.0)),
            stats=detection.get("statistics", {}) or {},
        )
        if not confirmed_type:
            return {"success": True, "cancelled": True}
    else:
        confirmed_type = requested

    if confirmed_type == "segmentation":
        classes = sorted(workflow.detect_xlabel_segmentation_classes(dataset_path))
    else:
        classes = sorted(workflow.detect_xlabel_classes(dataset_path))

    if not classes:
        return {"success": False, "error": "未检测到任何类别"}

    context.log("当前类别顺序（= class_id）:")
    for index, name in enumerate(sorted(classes)):
        context.log(f"  {index}: {name}")

    class_order = None
    if values.get("class_order"):
        class_order = _parse_class_order(classes, values.get("class_order"))
    elif values.get("edit_class_order"):
        response = context.ask(
            "调整类别顺序",
            "输入新的编号顺序（空格分隔，例如 2 1 0），留空使用当前顺序。",
            [
                ParameterSpec(
                    name="class_order",
                    label="类别顺序",
                    kind="str",
                    default="",
                )
            ],
        )
        if response is None:
            return {"success": True, "cancelled": True}
        class_order = _parse_class_order(classes, response.get("class_order"))

    if class_order is None:
        class_order = sorted(classes)

    context.log("最终类别与 ID 映射:")
    for index, name in enumerate(class_order):
        context.log(f"  {index}: {name}")

    if confirmed_type == "segmentation":
        context.log("正在转换 X-label 分割数据集...")
        return workflow.convert_xlabel_to_yolo_segmentation(
            dataset_path, output_dir=output_dir, class_order=class_order
        )

    context.log("正在转换 X-label 数据集...")
    return workflow.convert_xlabel_to_yolo(
        dataset_path, output_dir=output_dir, class_order=class_order
    )


def _clean_unmatched(
    context: TaskContext,
    workflow: YoloWorkflow,
    dataset_path: str,
) -> Dict[str, Any]:
    preview = workflow.clean_unmatched_files(dataset_path, dry_run=True)
    total = count_deleted_files(preview.get("deleted_files", {}))
    if total == 0:
        context.log("数据集已经完全匹配，无需清理。")
        return preview

    details = deletion_details(preview.get("deleted_files", {}))
    if not context.confirm(
        "确认删除不匹配文件",
        f"将删除 {total} 个不匹配文件，是否继续？",
        details=tuple(details),
        default=False,
    ):
        return {"success": True, "cancelled": True}

    context.log("正在删除文件...")
    return workflow.clean_unmatched_files(dataset_path, dry_run=False)


def handle_validate_detection_dataset(
    context: TaskContext, values: Dict[str, Any]
) -> Dict[str, Any]:
    workflow = _workflow(context)
    dataset_path = values["dataset_path"]

    context.log("正在验证目标检测数据集...")
    result = workflow.get_dataset_statistics(dataset_path)

    statistics = result.get("statistics", {})
    if statistics and not statistics.get("is_valid", True):
        has_issues = (
            statistics.get("orphaned_images", 0) > 0
            or statistics.get("orphaned_labels", 0) > 0
        )
        if has_issues and bool(values.get("auto_clean", False)):
            clean_result = _clean_unmatched(context, workflow, dataset_path)
            result = dict(result)
            result["clean_result"] = clean_result
            if not clean_result.get("cancelled"):
                result["revalidated"] = workflow.get_dataset_statistics(dataset_path)

    return result


def handle_validate_segmentation_dataset(
    context: TaskContext, values: Dict[str, Any]
) -> Dict[str, Any]:
    from ..helpers import scan_invalid_segmentation_files

    workflow = _workflow(context)
    dataset_path = values["dataset_path"]

    context.log("正在验证目标分割数据集...")
    result = dict(workflow.get_dataset_statistics(dataset_path))

    invalid_files = scan_invalid_segmentation_files(Path(dataset_path))
    result["invalid_segmentation_files"] = [
        {"file": str(path), "reason": reason} for path, reason in invalid_files
    ]

    if invalid_files:
        context.log(f"发现 {len(invalid_files)} 个不符合分割格式的标签文件。")
        if bool(values.get("move_invalid", False)) and context.confirm(
            "移动无效标签",
            "是否将无效文件移动到数据集上级目录？",
            details=tuple(
                f"{path.name}: {reason}" for path, reason in invalid_files[:5]
            ),
            default=False,
        ):
            result["move_result"] = _move_invalid_segmentation_files(
                Path(dataset_path), invalid_files
            )

    statistics = result.get("statistics", {})
    if statistics and not statistics.get("is_valid", True):
        has_issues = (
            statistics.get("orphaned_images", 0) > 0
            or statistics.get("orphaned_labels", 0) > 0
        )
        if has_issues and bool(values.get("auto_clean", False)):
            result["clean_result"] = _clean_unmatched(context, workflow, dataset_path)

    return result


def _move_invalid_segmentation_files(
    dataset_path: Path, invalid_files: List[Any]
) -> Dict[str, Any]:
    """把无效分割文件移动到数据集上级目录（保留旧命名与结构）。"""
    import shutil

    from ..helpers import detect_root_and_subdirs

    root = detect_root_and_subdirs(dataset_path)
    invalid_dir = root.parent / "invalid_segmentation_files"
    invalid_images_dir = invalid_dir / "images"
    invalid_labels_dir = invalid_dir / "labels"
    invalid_dir.mkdir(exist_ok=True)
    invalid_images_dir.mkdir(exist_ok=True)
    invalid_labels_dir.mkdir(exist_ok=True)

    images_dir = root / "images"
    moved = 0
    for label_file, _reason in invalid_files:
        try:
            shutil.move(str(label_file), str(invalid_labels_dir / label_file.name))
            for ext in (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".ti"):
                image_file = images_dir / f"{label_file.stem}{ext}"
                if image_file.exists():
                    shutil.move(
                        str(image_file), str(invalid_images_dir / image_file.name)
                    )
                    break
            moved += 1
        except Exception:  # noqa: BLE001
            continue

    classes_file = root / "classes.txt"
    if classes_file.exists():
        try:
            shutil.copy2(str(classes_file), str(invalid_dir / "classes.txt"))
        except Exception:  # noqa: BLE001
            pass

    return {"moved_count": moved, "target_dir": str(invalid_dir)}


def handle_clean_unmatched(
    context: TaskContext, values: Dict[str, Any]
) -> Dict[str, Any]:
    workflow = _workflow(context)
    dataset_path = values["dataset_path"]

    if bool(values.get("dry_run", False)):
        context.log("正在进行试运行...")
        return workflow.clean_unmatched_files(dataset_path, dry_run=True)

    return _clean_unmatched(context, workflow, dataset_path)


def handle_merge_datasets(
    context: TaskContext, values: Dict[str, Any]
) -> Dict[str, Any]:
    workflow = _workflow(context)
    dataset_paths = [Path(path) for path in values["dataset_paths"]]
    output_path = values.get("output_path") or "."
    output_name = normalize_optional_text(values.get("output_name"))
    image_prefix = normalize_optional_text(values.get("image_prefix"))

    context.log("正在验证数据集兼容性...")
    validation = workflow.validate_classes_consistency(dataset_paths)
    if not validation.get("consistent"):
        return {
            "success": False,
            "error": validation.get("details", "数据集 classes.txt 不一致"),
        }

    classes = validation.get("classes", [])
    context.log(f"类别列表: {', '.join(classes)}")
    if not output_name:
        context.log(
            f"建议输出目录名: {workflow.generate_output_name(classes, dataset_paths)}"
        )

    if not context.confirm(
        "确认合并数据集",
        f"将合并 {len(dataset_paths)} 个数据集到 {output_path}，是否继续？",
        details=tuple(str(path) for path in dataset_paths),
        default=False,
    ):
        return {"success": True, "cancelled": True}

    context.log("正在合并数据集...")
    return workflow.merge_datasets(
        dataset_paths=dataset_paths,
        output_path=output_path,
        output_name=output_name,
        image_prefix=image_prefix,
    )


def handle_merge_different_datasets(
    context: TaskContext, values: Dict[str, Any]
) -> Dict[str, Any]:
    workflow = _workflow(context)
    dataset_paths = list(values["dataset_paths"])
    output_path = values.get("output_path") or "."
    output_name = normalize_optional_text(values.get("output_name"))
    image_prefix = normalize_optional_text(values.get("image_prefix"))

    path_objects = [Path(path) for path in dataset_paths]
    all_classes_info = workflow.collect_all_classes_info(path_objects)

    context.log("=== 数据集类别信息 ===")
    for index, info in enumerate(all_classes_info):
        context.log(f"数据集 {index + 1}: {info['dataset_path'].name}")
        context.log(f"  类别数: {len(info['classes'])}")

    dataset_order = None
    if values.get("dataset_order"):
        try:
            order = [int(token) for token in str(values["dataset_order"]).split()]
            if len(order) == len(dataset_paths) and set(order) == set(
                range(len(dataset_paths))
            ):
                dataset_order = order
            else:
                context.log("处理顺序数量或编号不合法，使用默认顺序。")
        except ValueError:
            context.log("处理顺序格式错误，使用默认顺序。")

    unified_classes, class_mappings = workflow.create_unified_class_mapping(
        all_classes_info
    )
    context.log(f"合并后总类别数: {len(unified_classes)}")
    for index, (info, mapping) in enumerate(zip(all_classes_info, class_mappings)):
        context.log(f"数据集 {index + 1} ({info['dataset_path'].name}) 映射已生成")

    if not output_name:
        context.log(
            "建议输出目录名: "
            + workflow.generate_different_output_name(unified_classes, path_objects)
        )

    if not context.confirm(
        "确认合并数据集",
        f"将合并 {len(dataset_paths)} 个不同类型数据集到 {output_path}，是否继续？",
        details=tuple(dataset_paths),
        default=False,
    ):
        return {"success": True, "cancelled": True}

    context.log("正在合并不同类型数据集...")
    return workflow.merge_different_type_datasets(
        dataset_paths=dataset_paths,
        output_path=output_path,
        output_name=output_name,
        image_prefix=image_prefix,
        dataset_order=dataset_order,
    )
