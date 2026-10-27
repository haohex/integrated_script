"""Merge and class-mapping internals for YOLO processor Phase 3 migration slices."""

from __future__ import annotations

import os
import re
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from ...config.exceptions import DatasetError
from ...core.progress import progress_context
from ...core.utils import create_directory, get_file_list, validate_path
from .helpers import build_label_mapping

if TYPE_CHECKING:
    from ..yolo_processor import YOLOProcessor


def detect_name_conflicts_internal(
    processor: "YOLOProcessor",
    dataset_paths: List[Path],
    image_manifest: Optional[List[List[Path]]] = None,
) -> Dict[str, Any]:
    """检测平铺输出中不区分大小写的图片 stem 冲突。"""
    if image_manifest is None:
        image_manifest = [
            get_file_list(path, processor.image_extensions, recursive=True)
            for path in dataset_paths
        ]
    counts: Dict[str, int] = {}
    for images in image_manifest:
        for image in images:
            stem = image.stem.casefold()
            counts[stem] = counts.get(stem, 0) + 1
    conflicts = sorted(stem for stem, count in counts.items() if count > 1)
    return {
        "has_conflict": bool(conflicts),
        "conflict_count": len(conflicts),
        "examples": conflicts[:5],
    }


def merge_datasets_internal(
    processor: "YOLOProcessor",
    dataset_paths: List[str],
    output_path: str,
    output_name: Optional[str] = None,
    image_prefix: Optional[str] = None,
) -> Dict[str, Any]:
    """合并多个YOLO数据集。"""
    try:
        processor.logger.info(f"开始合并 {len(dataset_paths)} 个数据集")

        validated_paths = []
        for path in dataset_paths:
            validated_path = validate_path(path, must_exist=True, must_be_dir=True)
            validated_paths.append(validated_path)

        classes_validation = processor._validate_classes_consistency(validated_paths)
        if not classes_validation["consistent"]:
            raise DatasetError(
                f"数据集classes.txt不一致: {classes_validation['details']}"
            )

        common_classes = classes_validation["classes"]

        pre_scanned_images = [
            get_file_list(dataset_path, processor.image_extensions, recursive=True)
            for dataset_path in validated_paths
        ]
        conflicts = detect_name_conflicts_internal(
            processor, validated_paths, pre_scanned_images
        )
        if image_prefix is None and conflicts["has_conflict"]:
            raise DatasetError("存在文件名冲突，请指定图片前缀")
        if image_prefix == "":
            raise DatasetError("图片前缀不能为空字符串")
        if not output_name:
            output_name = processor._generate_output_name(
                common_classes,
                validated_paths,
                image_manifest=pre_scanned_images,
            )

        output_dir = Path(output_path) / output_name
        create_directory(output_dir)

        merge_result = processor._merge_dataset_files(
            validated_paths,
            output_dir,
            image_prefix,
            common_classes,
            pre_scanned_images=pre_scanned_images,
        )

        processor.logger.info(f"数据集合并完成: {output_dir}")

        return {
            "success": True,
            "output_path": str(output_dir),
            "output_name": output_name,
            "merged_datasets": len(validated_paths),
            "total_images": merge_result["total_images"],
            "total_labels": merge_result["total_labels"],
            "classes": common_classes,
            "statistics": merge_result["statistics"],
        }

    except Exception as e:
        processor.logger.error(f"数据集合并失败: {str(e)}")
        raise DatasetError(f"数据集合并失败: {str(e)}") from e


def merge_different_type_datasets_internal(
    processor: "YOLOProcessor",
    dataset_paths: List[str],
    output_path: str,
    output_name: Optional[str] = None,
    image_prefix: Optional[str] = None,
    dataset_order: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """合并多个不同类型的 YOLO 数据集。"""
    try:
        processor.logger.info(f"开始合并 {len(dataset_paths)} 个不同类型数据集")

        validated_paths = []
        for path in dataset_paths:
            validated_path = validate_path(path, must_exist=True, must_be_dir=True)
            validated_paths.append(validated_path)

        if dataset_order:
            if len(dataset_order) != len(validated_paths):
                raise DatasetError("数据集顺序列表长度与数据集数量不匹配")
            if set(dataset_order) != set(range(len(validated_paths))):
                raise DatasetError("数据集顺序列表包含无效索引")
            validated_paths = [validated_paths[i] for i in dataset_order]

        all_classes_info = processor._collect_all_classes_info(validated_paths)

        unified_classes, class_mappings = processor._create_unified_class_mapping(
            all_classes_info
        )

        pre_scanned_images = [
            get_file_list(dataset_path, processor.image_extensions, recursive=True)
            for dataset_path in validated_paths
        ]
        conflicts = detect_name_conflicts_internal(
            processor, validated_paths, pre_scanned_images
        )
        if image_prefix is None and conflicts["has_conflict"]:
            raise DatasetError("存在文件名冲突，请指定图片前缀")
        if image_prefix == "":
            raise DatasetError("图片前缀不能为空字符串")
        if not output_name:
            output_name = processor._generate_different_output_name(
                unified_classes,
                validated_paths,
                image_manifest=pre_scanned_images,
            )

        output_dir = Path(output_path) / output_name
        create_directory(output_dir)

        merge_result = processor._merge_different_dataset_files(
            validated_paths,
            output_dir,
            image_prefix,
            unified_classes,
            class_mappings,
            pre_scanned_images=pre_scanned_images,
        )

        processor.logger.info(f"不同类型数据集合并完成: {output_dir}")

        return {
            "success": True,
            "output_path": str(output_dir),
            "output_name": output_name,
            "merged_datasets": len(validated_paths),
            "total_images": merge_result["total_images"],
            "total_labels": merge_result["total_labels"],
            "unified_classes": unified_classes,
            "class_mappings": class_mappings,
            "statistics": merge_result["statistics"],
        }

    except Exception as e:
        processor.logger.error(f"不同类型数据集合并失败: {str(e)}")
        raise DatasetError(f"不同类型数据集合并失败: {str(e)}") from e


def collect_all_classes_info_internal(
    processor: "YOLOProcessor", dataset_paths: List[Path]
) -> List[Dict[str, Any]]:
    """收集所有数据集的类别信息。"""
    all_classes_info = []

    for i, dataset_path in enumerate(dataset_paths):
        classes_file = dataset_path / processor.classes_file
        if not classes_file.exists():
            raise DatasetError(
                f"数据集 {dataset_path} 缺少 {processor.classes_file} 文件"
            )

        try:
            with open(classes_file, "r", encoding="utf-8") as f:
                classes = [line.strip() for line in f.readlines() if line.strip()]

            all_classes_info.append(
                {
                    "dataset_index": i,
                    "dataset_path": dataset_path,
                    "classes": classes,
                }
            )
        except Exception as e:
            raise DatasetError(f"读取 {classes_file} 失败: {str(e)}") from e

    return all_classes_info


def create_unified_class_mapping_internal(
    _processor: "YOLOProcessor", all_classes_info: List[Dict[str, Any]]
) -> Tuple[List[str], List[Dict[int, int]]]:
    """创建统一的类别映射。"""
    all_unique_classes = []
    seen_classes = set()

    for classes_info in all_classes_info:
        for class_name in classes_info["classes"]:
            if class_name not in seen_classes:
                all_unique_classes.append(class_name)
                seen_classes.add(class_name)

    class_mappings = []
    for classes_info in all_classes_info:
        mapping = {}
        for old_class_id, class_name in enumerate(classes_info["classes"]):
            new_class_id = all_unique_classes.index(class_name)
            mapping[old_class_id] = new_class_id
        class_mappings.append(mapping)

    return all_unique_classes, class_mappings


def build_label_mapping_internal(
    processor: "YOLOProcessor", label_files: List[Path]
) -> Dict[str, Path]:
    """构建标签文件映射索引。"""
    return build_label_mapping(label_files, processor.classes_file)


def merge_dataset_parallel_internal(
    processor: "YOLOProcessor",
    image_files: List[Path],
    images_dir: Path,
    labels_dir: Path,
    image_prefix: Optional[str],
    start_index: int,
    label_mapping: Dict[str, Path],
    dataset_num: int,
) -> Dict[str, int]:
    """并行合并数据集文件。"""
    images_processed = 0
    labels_processed = 0
    failed_count = 0

    lock = threading.Lock()

    def copy_file_batch(batch_args):
        """批量复制文件对（减少系统调用开销）。"""
        batch_tasks = batch_args
        batch_images = 0
        batch_labels = 0
        batch_failed = 0

        copy_operations = []

        for img_file, file_index in batch_tasks:
            try:
                new_name = (
                    img_file.name
                    if image_prefix is None
                    else f"{image_prefix}_{file_index:05d}{img_file.suffix}"
                )
                new_img_path = images_dir / new_name
                copy_operations.append((img_file, new_img_path, "image"))

                base_name = img_file.stem
                label_file = label_mapping.get(base_name)

                if label_file and label_file.exists():
                    new_label_name = (
                        label_file.name
                        if image_prefix is None
                        else f"{image_prefix}_{file_index:05d}.txt"
                    )
                    new_label_path = labels_dir / new_label_name
                    copy_operations.append((label_file, new_label_path, "label"))

            except Exception as e:
                processor.logger.error(f"准备文件操作失败 {img_file}: {str(e)}")
                batch_failed += 1

        for src_file, dst_file, file_type in copy_operations:
            try:
                if not dst_file.parent.exists():
                    dst_file.parent.mkdir(parents=True, exist_ok=True)

                if src_file.stat().st_size < 1024 * 1024:
                    shutil.copy2(src_file, dst_file)
                else:
                    shutil.copyfile(src_file, dst_file)

                if file_type == "image":
                    batch_images += 1
                else:
                    batch_labels += 1

            except Exception as e:
                processor.logger.error(
                    f"复制文件失败 {src_file} -> {dst_file}: {str(e)}"
                )
                batch_failed += 1

        with lock:
            nonlocal images_processed, labels_processed, failed_count
            images_processed += batch_images
            labels_processed += batch_labels
            failed_count += batch_failed

        return len(batch_tasks)

    tasks = [(img_file, start_index + i) for i, img_file in enumerate(image_files)]
    if not tasks:
        return {
            "images_processed": 0,
            "labels_processed": 0,
            "failed_count": 0,
        }

    batch_size = max(1, len(tasks) // (os.cpu_count() or 4))
    batch_size = min(batch_size, 100)

    batches = [tasks[i : i + batch_size] for i in range(0, len(tasks), batch_size)]

    max_workers = min(len(batches), (os.cpu_count() or 4) * 2, 16)

    processor.logger.info(
        f"使用 {max_workers} 个线程处理 {len(batches)} 个批次，每批次 {batch_size} 个文件"
    )

    with progress_context(
        len(image_files), f"并行合并数据集 {dataset_num}"
    ) as progress:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_batch = {
                executor.submit(copy_file_batch, batch): batch for batch in batches
            }

            for future in as_completed(future_to_batch):
                try:
                    processed_count = future.result()
                    progress.update_progress(processed_count)
                except Exception as e:
                    batch = future_to_batch[future]
                    processor.logger.error(
                        f"批次执行异常 (批次大小: {len(batch)}): {str(e)}"
                    )
                    progress.update_progress(len(batch))

    if failed_count > 0:
        processor.logger.warning(
            f"数据集 {dataset_num} 有 {failed_count} 个文件复制失败"
        )

    return {
        "images_processed": images_processed,
        "labels_processed": labels_processed,
        "failed_count": failed_count,
    }


def generate_output_name_internal(
    _processor: "YOLOProcessor",
    classes: List[str],
    dataset_paths: List[Path],
    image_manifest: Optional[List[List[Path]]] = None,
) -> str:
    """为一致类别数据集生成输出目录名称。"""
    if image_manifest is None:
        image_manifest = [
            get_file_list(dataset_path, _processor.image_extensions, recursive=True)
            for dataset_path in dataset_paths
        ]

    total_images = sum(len(image_files) for image_files in image_manifest)

    classes_prefix = "_".join(classes[:3])
    if len(classes) > 3:
        classes_prefix += f"_etc{len(classes)}"

    output_name = f"{classes_prefix}_merged_{total_images}imgs"
    output_name = re.sub(r'[<>:"/\\|?*]', "_", output_name)
    return output_name


def generate_different_output_name_internal(
    processor: "YOLOProcessor",
    unified_classes: List[str],
    dataset_paths: List[Path],
    image_manifest: Optional[List[List[Path]]] = None,
) -> str:
    """为不同类别数据集合并生成输出目录名称。"""
    if image_manifest is None:
        image_manifest = [
            get_file_list(dataset_path, processor.image_extensions, recursive=True)
            for dataset_path in dataset_paths
        ]

    total_images = sum(len(image_files) for image_files in image_manifest)

    classes_prefix = "_".join(unified_classes[:3])
    if len(unified_classes) > 3:
        classes_prefix += f"_etc{len(unified_classes)}"

    output_name = f"{classes_prefix}_mixed_{len(dataset_paths)}ds_{total_images}imgs"
    output_name = re.sub(r'[<>:"/\\|?*]', "_", output_name)
    return output_name


def validate_classes_consistency_internal(
    processor: "YOLOProcessor", dataset_paths: List[Path]
) -> Dict[str, Any]:
    """验证多个数据集 classes.txt 一致性。"""
    classes_info = []

    for dataset_path in dataset_paths:
        classes_file = dataset_path / processor.classes_file
        if not classes_file.exists():
            return {
                "consistent": False,
                "details": f"数据集 {dataset_path} 缺少 {processor.classes_file} 文件",
                "classes": None,
            }

        try:
            with open(classes_file, "r", encoding="utf-8") as f:
                classes = [line.strip() for line in f.readlines() if line.strip()]
            classes_info.append({"path": dataset_path, "classes": classes})
        except Exception as e:
            return {
                "consistent": False,
                "details": f"读取 {classes_file} 失败: {str(e)}",
                "classes": None,
            }

    if not classes_info:
        return {
            "consistent": False,
            "details": "没有找到有效的classes.txt文件",
            "classes": None,
        }

    reference_classes = classes_info[0]["classes"]

    for info in classes_info[1:]:
        if info["classes"] != reference_classes:
            return {
                "consistent": False,
                "details": f"数据集 {info['path']} 的类别与其他数据集不一致",
                "classes": None,
            }

    return {
        "consistent": True,
        "details": "所有数据集的类别一致",
        "classes": reference_classes,
    }
