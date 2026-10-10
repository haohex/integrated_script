#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图像处理相关操作处理器。"""

from __future__ import annotations

import math
import multiprocessing
from pathlib import Path
from typing import Any, Dict

from ...processors import ImageProcessor
from ...workflows import ImageWorkflow
from ..helpers import count_images, default_converted_output, parse_size
from ..operations import TaskContext

CATEGORY = "图像处理"


def _workflow(context: TaskContext) -> ImageWorkflow:
    return ImageWorkflow(ImageProcessor(config=context.config))


def handle_convert(context: TaskContext, values: Dict[str, Any]) -> Dict[str, Any]:
    workflow = _workflow(context)
    input_path = Path(values["input_path"])
    output_path = values.get("output_path") or default_converted_output(input_path)
    target_format = str(values["target_format"]).lstrip(".")
    quality = values.get("quality")
    if quality is None and target_format.lower() in {"jpg", "jpeg"}:
        quality = 95
    recursive = bool(values.get("recursive", False))

    context.log(f"正在转换图像格式: {input_path} -> {target_format}")
    return workflow.convert_format(
        str(input_path),
        target_format,
        output_path=str(output_path),
        quality=quality,
        recursive=recursive,
    )


def handle_resize(context: TaskContext, values: Dict[str, Any]) -> Dict[str, Any]:
    workflow = _workflow(context)
    input_path = Path(values["input_path"])
    target_size = parse_size(values["size"])

    if input_path.is_dir():
        default_output = input_path.parent / f"{input_path.name}_sized"
    else:
        default_output = (
            input_path.parent / f"{input_path.stem}_sized{input_path.suffix}"
        )

    output_path = values.get("output_path") or str(default_output)
    recursive = bool(values.get("recursive", False))

    context.log(f"正在调整图像尺寸为 {target_size[0]}x{target_size[1]}...")
    return workflow.resize_images(
        str(input_path),
        str(output_path),
        target_size=target_size,
        maintain_aspect_ratio=bool(values.get("keep_aspect", True)),
        recursive=recursive,
    )


def handle_compress(context: TaskContext, values: Dict[str, Any]) -> Dict[str, Any]:
    workflow = _workflow(context)
    input_path = Path(values["input_path"])

    if input_path.is_file():
        default_output = str(
            input_path.parent / f"{input_path.stem}_compressed{input_path.suffix}"
        )
    else:
        default_output = str(input_path.parent / f"{input_path.name}_compressed")
    output_path = values.get("output_path") or default_output

    target_format = values.get("target_format")
    if target_format in (None, "", "original"):
        target_format = None

    max_size = None
    if values.get("max_size"):
        max_size = parse_size(values["max_size"])

    recursive = bool(values.get("recursive", False))
    total_images = count_images(input_path, recursive)

    batch_size = 1000
    batch_count = max(1, math.ceil(total_images / batch_size))
    cpu_count = multiprocessing.cpu_count()
    default_processes = min(cpu_count, batch_count)
    max_processes = values.get("max_processes") or default_processes

    context.log(
        f"发现图片文件: {total_images} 张，批次: {batch_count}，进程: {max_processes}"
    )
    return workflow.compress_images_multiprocess_batch(
        input_dir=str(input_path),
        output_dir=str(output_path),
        quality=int(values.get("quality", 85)),
        target_format=target_format,
        recursive=recursive,
        max_size=max_size,
        batch_count=batch_count,
        max_processes=int(max_processes),
    )


def handle_repair(context: TaskContext, values: Dict[str, Any]) -> Dict[str, Any]:
    workflow = _workflow(context)
    context.log("正在尝试用 OpenCV 读取图像，失败则重新保存...")
    return workflow.repair_images_with_opencv(
        values["directory"],
        recursive=bool(values.get("recursive", True)),
        include_hidden=False,
    )


def handle_info(context: TaskContext, values: Dict[str, Any]) -> Dict[str, Any]:
    workflow = _workflow(context)
    context.log("正在获取图像信息...")
    return workflow.get_image_info(
        values["image_path"],
        recursive=bool(values.get("recursive", False)),
    )
