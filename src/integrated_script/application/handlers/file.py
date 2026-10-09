#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文件操作相关操作处理器。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from ...processors import FileProcessor
from ...workflows import FileWorkflow
from ..contracts import ParameterSpec
from ..operations import TaskContext

CATEGORY = "文件操作"

_SUFFIX_FIELD = ParameterSpec(
    name="suffix",
    label="文件后缀",
    kind="str",
    required=True,
    help="例如 .jpg",
)


def _workflow(context: TaskContext) -> FileWorkflow:
    return FileWorkflow(FileProcessor(config=context.config))


def _default_suffix(source_dir: str) -> str:
    """检测目录中的默认文件后缀（与旧交互一致：取字典序首个后缀）。

    仅在未显式提供后缀时使用；目录中没有带后缀的文件时返回空字符串。
    """
    try:
        entries = list(Path(source_dir).iterdir())
    except OSError:
        return ""
    extensions = {
        entry.suffix.lower() for entry in entries if entry.is_file() and entry.suffix
    }
    if not extensions:
        return ""
    return sorted(extensions)[0]


def handle_organize(context: TaskContext, values: Dict[str, Any]) -> Dict[str, Any]:
    workflow = _workflow(context)
    context.log("正在按扩展名组织文件...")
    return workflow.organize_by_extension(
        values["source_dir"],
        output_dir=values.get("output_dir") or None,
        copy_files=bool(values.get("copy_files", False)),
    )


def handle_copy(context: TaskContext, values: Dict[str, Any]) -> Dict[str, Any]:
    workflow = _workflow(context)
    context.log("正在复制文件...")
    return workflow.copy_files(
        values["source_path"],
        values["dest_path"],
        recursive=bool(values.get("recursive", False)),
    )


def handle_move(context: TaskContext, values: Dict[str, Any]) -> Dict[str, Any]:
    workflow = _workflow(context)
    context.log("正在移动文件...")
    return workflow.move_files(
        values["source_path"],
        values["dest_path"],
        recursive=bool(values.get("recursive", False)),
    )


def handle_move_images_by_count(
    context: TaskContext, values: Dict[str, Any]
) -> Dict[str, Any]:
    workflow = _workflow(context)
    context.log("正在按数量移动图片...")
    return workflow.move_images_by_count(
        values["source_path"],
        values["dest_path"],
        count=int(values["count"]),
        overwrite=bool(values.get("overwrite", False)),
    )


def handle_rename_single_dir(
    context: TaskContext, values: Dict[str, Any]
) -> Dict[str, Any]:
    workflow = _workflow(context)
    source_dir = values["source_dir"]

    prefix = values.get("prefix", "")
    if prefix is None:
        prefix = ""
    digits = int(values.get("digits") or 5)
    if digits < 1 or digits > 10:
        digits = 5
    suffix = str(values.get("suffix") or "").strip()
    if not suffix:
        # 旧交互在留空时自动检测目录后缀，避免重命名后丢失扩展名。
        suffix = _default_suffix(source_dir)
    if not suffix:
        # 旧交互：目录中没有任何带后缀的文件时，必须询问用户并提供后缀，
        # 用户关闭/留空时取消操作且不写入任何文件。
        answer = context.ask(
            "未检测到文件后缀",
            "源目录中没有带后缀的文件，请输入重命名使用的文件后缀。",
            (_SUFFIX_FIELD,),
        )
        if not answer:
            return {"success": True, "cancelled": True}
        suffix = str(answer.get("suffix") or "").strip()
        if not suffix:
            return {"success": True, "cancelled": True}
    if suffix and not suffix.startswith("."):
        suffix = "." + suffix
    shuffle_order = bool(values.get("shuffle_order", False))

    if prefix:
        pattern = f"{prefix}_{{index:0{digits}d}}{suffix}"
    else:
        pattern = f"{{index:0{digits}d}}{suffix}"

    details = [f"重命名模式: {pattern}", f"打乱顺序: {'是' if shuffle_order else '否'}"]
    if not context.confirm(
        "确认重命名模式",
        "确认使用此重命名模式？",
        details=tuple(details),
        default=False,
    ):
        return {"success": True, "cancelled": True}

    context.log("正在重命名文件...")
    return workflow.rename_files_with_temp(
        source_dir, pattern, shuffle_order=shuffle_order
    )


def handle_rename_images_labels(
    context: TaskContext, values: Dict[str, Any]
) -> Dict[str, Any]:
    workflow = _workflow(context)
    source_dir = Path(values["source_dir"])
    images_dir = source_dir / "images"
    labels_dir = source_dir / "labels"

    if not images_dir.exists():
        return {"success": False, "error": f"未找到 images 目录: {images_dir}"}
    if not labels_dir.exists():
        return {"success": False, "error": f"未找到 labels 目录: {labels_dir}"}

    prefix = values.get("prefix", "")
    if prefix is None:
        prefix = ""
    digits = int(values.get("digits") or 5)
    if digits < 1 or digits > 10:
        digits = 5
    shuffle_order = bool(values.get("shuffle_order", False))

    if not context.confirm(
        "确认同步重命名",
        "确认开始同步重命名 images 和 labels 文件？",
        details=(
            f"前缀: {prefix or '（无前缀）'}",
            f"数字位数: {digits}",
            f"打乱顺序: {'是' if shuffle_order else '否'}",
        ),
        default=False,
    ):
        return {"success": True, "cancelled": True}

    context.log("正在同步重命名 images 和 labels 文件...")
    return workflow.rename_images_labels_sync(
        str(images_dir), str(labels_dir), prefix, digits, shuffle_order
    )


def handle_rename_images_labels_legacy(
    context: TaskContext, values: Dict[str, Any]
) -> Dict[str, Any]:
    """传统模式：序号不补零（digits=0）。"""
    workflow = _workflow(context)
    source_dir = Path(values["source_dir"])
    images_dir = source_dir / "images"
    labels_dir = source_dir / "labels"

    if not images_dir.exists():
        return {"success": False, "error": f"未找到 images 目录: {images_dir}"}
    if not labels_dir.exists():
        return {"success": False, "error": f"未找到 labels 目录: {labels_dir}"}

    prefix = values.get("prefix", "")
    if prefix is None:
        prefix = ""
    shuffle_order = bool(values.get("shuffle_order", False))

    if not context.confirm(
        "确认同步重命名（传统模式）",
        "确认开始同步重命名 images 和 labels 文件（序号不补零）？",
        details=(
            f"前缀: {prefix or '（无前缀）'}",
            f"打乱顺序: {'是' if shuffle_order else '否'}",
        ),
        default=False,
    ):
        return {"success": True, "cancelled": True}

    context.log("正在以传统模式同步重命名 images 和 labels 文件...")
    return workflow.rename_images_labels_sync(
        str(images_dir), str(labels_dir), prefix, 0, shuffle_order
    )


def handle_delete_json(context: TaskContext, values: Dict[str, Any]) -> Dict[str, Any]:
    workflow = _workflow(context)
    target_dir = values["target_dir"]

    preview = workflow.delete_json_files_recursive(target_dir, dry_run=True)
    stats = preview.get("statistics", {})
    total = int(stats.get("total_files", 0))
    if total == 0:
        context.log("未找到任何 JSON 文件。")
        return preview

    json_files = preview.get("json_files", [])
    details = [str(path) for path in json_files[:10]]
    if total > 10:
        details.append(f"... 还有 {total - 10} 个文件")

    if not context.confirm(
        "确认删除 JSON 文件",
        f"此操作将永久删除 {total} 个 JSON 文件，是否继续？",
        details=tuple(details),
        default=False,
    ):
        return {"success": True, "cancelled": True}

    context.log("正在删除 JSON 文件...")
    return workflow.delete_json_files_recursive(target_dir, dry_run=False)
