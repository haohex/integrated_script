#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
yolo_processor.py

YOLO数据集处理器

提供YOLO数据集的验证、清理、转换等功能。
"""

import json
import random
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from ..config.exceptions import DatasetError  # type: ignore
from ..core.progress import progress_context  # type: ignore
from ..core.utils import (  # type: ignore
    copy_file_safe,
    create_directory,
    cv2_imread_unicode,
    cv2_imwrite_unicode,
    get_file_list,
    validate_path,
)
from .dataset_processor import DatasetProcessor  # type: ignore
from .yolo import (
    build_label_mapping_internal,
    clean_unmatched_files_internal,
    collect_all_classes_info_internal,
    continue_ctds_processing_internal,
    create_unified_class_mapping_internal,
    execute_ctds_processing_internal,
    format_duration,
    generate_different_output_name_internal,
    generate_output_name_internal,
    get_dataset_statistics_internal,
    get_project_name,
    merge_dataset_parallel_internal,
    merge_datasets_internal,
    merge_different_type_datasets_internal,
    process_ctds_dataset_internal,
    scan_xlabel_dataset_recursive,
    validate_classes_consistency_internal,
)
from .yolo.merge import detect_name_conflicts_internal


class YOLOProcessor(DatasetProcessor):
    """YOLO数据集处理器

    提供YOLO数据集的各种处理功能，包括验证、清理、转换等。

    Attributes:
        image_extensions (List[str]): 支持的图像格式
        label_extension (str): 标签文件扩展名
    """

    def __init__(self, **kwargs):
        """初始化YOLO处理器"""
        # 先设置默认属性，确保即使初始化失败也有基本属性
        self.image_extensions = [".jpg", ".jpeg", ".png", ".bmp"]
        self.label_extension = ".txt"
        self.classes_file = "classes.txt"

        # 调用父类初始化
        super().__init__(**kwargs)

        # 从配置获取支持的格式（覆盖默认值）
        try:
            self.image_extensions = self.get_config(
                "yolo.image_formats", self.image_extensions
            )
            self.label_extension = self.get_config(
                "yolo.label_format", self.label_extension
            )
            self.classes_file = self.get_config("yolo.classes_file", self.classes_file)
        except Exception as e:
            self.logger.warning(f"从配置获取YOLO设置失败，使用默认值: {e}")

    def initialize(self) -> None:
        """初始化处理器"""
        self.logger.info("YOLO处理器初始化完成")
        self.logger.debug(f"支持的图像格式: {self.image_extensions}")
        self.logger.debug(f"标签文件格式: {self.label_extension}")

    def process(self, *args, **kwargs) -> Any:
        """主要处理方法（由子方法实现具体功能）"""
        raise NotImplementedError("请使用具体的处理方法")

    def get_dataset_statistics(self, dataset_path: str) -> Dict[str, Any]:
        """获取数据集统计信息。"""
        return get_dataset_statistics_internal(self, dataset_path)

    def clean_unmatched_files(
        self, dataset_path: str, dry_run: bool = False
    ) -> Dict[str, Any]:
        """清理数据集中不匹配的文件。"""
        return clean_unmatched_files_internal(self, dataset_path, dry_run)

    def process_ctds_dataset(
        self,
        input_path: str,
        output_name: Optional[str] = None,
        keep_empty_labels: bool = False,
    ) -> Dict[str, Any]:
        """CTDS数据转YOLO格式。"""
        return process_ctds_dataset_internal(
            self,
            input_path=input_path,
            output_name=output_name,
            keep_empty_labels=keep_empty_labels,
        )

    def detect_xlabel_classes(self, source_dir: str) -> Set[str]:
        """扫描X-label/Labelme JSON中的类别名称"""
        source_path = validate_path(source_dir, must_exist=True, must_be_dir=True)
        scan_result = scan_xlabel_dataset_recursive(
            source_path,
            warn_json_read_failed=lambda json_path, error: self.logger.warning(
                f"读取JSON失败 {json_path}: {error}"
            ),
        )
        return scan_result["classes"]

    def detect_xlabel_dataset_type(self, source_dir: str) -> Dict[str, Any]:
        """检测X-label数据集类型（检测/分割/混合）"""
        source_path = validate_path(source_dir, must_exist=True, must_be_dir=True)

        scan_result = scan_xlabel_dataset_recursive(
            source_path,
            warn_json_read_failed=lambda json_path, error: self.logger.warning(
                f"读取JSON失败 {json_path}: {error}"
            ),
        )

        total_shapes = scan_result["total_shapes"]
        detection_like = scan_result["detection_like"]
        segmentation_like = scan_result["segmentation_like"]

        if total_shapes == 0:
            detected_type = "unknown"
            confidence = 0.0
        elif detection_like > 0 and segmentation_like > 0:
            detected_type = "mixed"
            confidence = max(detection_like, segmentation_like) / total_shapes
        elif segmentation_like > 0:
            detected_type = "segmentation"
            confidence = segmentation_like / total_shapes
        else:
            detected_type = "detection"
            confidence = detection_like / total_shapes

        return {
            "detected_type": detected_type,
            "confidence": confidence,
            "statistics": {
                "total_shapes": total_shapes,
                "detection_like": detection_like,
                "segmentation_like": segmentation_like,
            },
        }

    def detect_yolo_dataset_type(self, dataset_path: str) -> Dict[str, Any]:
        """检测YOLO数据集类型（检测/分割/混合）"""
        dataset_dir = validate_path(dataset_path, must_exist=True, must_be_dir=True)
        dataset_dir = self._detect_dataset_root(dataset_dir)

        labels_dir = dataset_dir / "labels"
        if not labels_dir.exists():
            raise DatasetError("未找到labels目录", dataset_path=str(dataset_dir))

        label_files = list(labels_dir.glob("*.txt"))
        if not label_files:
            return {
                "detected_type": "unknown",
                "confidence": 0.0,
                "statistics": {
                    "total_files": 0,
                    "detection_files": 0,
                    "segmentation_files": 0,
                },
            }

        sample_size = min(100, len(label_files))
        sample_files = random.sample(label_files, sample_size)

        detection_files = 0
        segmentation_files = 0

        for label_file in sample_files:
            try:
                with label_file.open("r", encoding="utf-8") as f:
                    lines = [line.strip() for line in f if line.strip()]
                if not lines:
                    continue

                detection_lines = 0
                segmentation_lines = 0
                for line in lines:
                    parts = line.split()
                    if len(parts) == 5:
                        detection_lines += 1
                    else:
                        segmentation_lines += 1

                if detection_lines >= segmentation_lines:
                    detection_files += 1
                else:
                    segmentation_files += 1
            except Exception as e:
                self.logger.warning(f"分析标签失败 {label_file}: {e}")

        total = detection_files + segmentation_files
        if total == 0:
            detected_type = "unknown"
            confidence = 0.0
        elif detection_files > 0 and segmentation_files > 0:
            detected_type = "mixed"
            confidence = max(detection_files, segmentation_files) / total
        elif segmentation_files > 0:
            detected_type = "segmentation"
            confidence = segmentation_files / total
        else:
            detected_type = "detection"
            confidence = detection_files / total

        return {
            "detected_type": detected_type,
            "confidence": confidence,
            "statistics": {
                "total_files": len(label_files),
                "detection_files": detection_files,
                "segmentation_files": segmentation_files,
            },
        }

    def detect_xlabel_segmentation_classes(self, source_dir: str) -> Set[str]:
        """扫描X-label分割JSON中的类别名称"""
        source_path = validate_path(source_dir, must_exist=True, must_be_dir=True)
        scan_result = scan_xlabel_dataset_recursive(
            source_path,
            warn_json_read_failed=lambda json_path, error: self.logger.warning(
                f"读取JSON失败 {json_path}: {error}"
            ),
        )
        return scan_result["classes"]

    def convert_xlabel_to_yolo(
        self,
        source_dir: str,
        output_dir: Optional[str] = None,
        class_order: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """X-label数据转YOLO格式（基于Labelme JSON）"""
        source_path = validate_path(source_dir, must_exist=True, must_be_dir=True)

        if output_dir:
            output_path = Path(output_dir)
        else:
            name = source_path.name
            output_path = source_path.parent / f"{name}_dataset"

        create_directory(output_path)
        images_dir = output_path / "images"
        labels_dir = output_path / "labels"
        create_directory(images_dir)
        create_directory(labels_dir)

        scan_result = scan_xlabel_dataset_recursive(
            source_path,
            warn_json_read_failed=lambda json_path, error: self.logger.warning(
                f"读取JSON失败 {json_path}: {error}"
            ),
        )

        detected_classes: Set[str] = scan_result["classes"]
        if not detected_classes:
            raise DatasetError("未检测到任何类别", dataset_path=str(source_path))

        if class_order:
            if len(class_order) != len(set(class_order)):
                raise DatasetError(
                    "class_order包含重复类别", dataset_path=str(source_path)
                )
            if set(class_order) != detected_classes:
                raise DatasetError(
                    "class_order与检测到的类别不一致",
                    dataset_path=str(source_path),
                )
            final_classes = class_order
        else:
            final_classes = sorted(detected_classes)
        class_mapping = {name: idx for idx, name in enumerate(final_classes)}

        json_files: List[Path] = scan_result["json_files"]

        result: Dict[str, Any] = {
            "success": True,
            "input_path": str(source_path),
            "output_path": str(output_path),
            "classes": final_classes,
            "class_mapping": class_mapping,
            "statistics": {
                "json_files": len(json_files),
                "converted": 0,
                "missing_images": 0,
                "skipped": 0,
                "errors": 0,
            },
        }

        def polygon_to_bbox(
            points: List[List[float]],
        ) -> Tuple[float, float, float, float]:
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            return min(xs), min(ys), max(xs), max(ys)

        def normalize_bbox(
            xmin: float,
            ymin: float,
            xmax: float,
            ymax: float,
            img_w: int,
            img_h: int,
        ) -> Tuple[float, float, float, float]:
            x_center = ((xmin + xmax) / 2) / img_w
            y_center = ((ymin + ymax) / 2) / img_h
            width = (xmax - xmin) / img_w
            height = (ymax - ymin) / img_h

            return (
                max(0, min(1, x_center)),
                max(0, min(1, y_center)),
                max(0, min(1, width)),
                max(0, min(1, height)),
            )

        with progress_context(len(json_files), "X-label转YOLO") as progress:
            for json_path in json_files:
                try:
                    with json_path.open("r", encoding="utf-8") as f:
                        data = json.load(f)

                    img_w = data.get("imageWidth")
                    img_h = data.get("imageHeight")
                    if not img_w or not img_h:
                        raise ValueError("缺少 imageWidth/imageHeight")

                    base_name = json_path.stem
                    img_path: Optional[Path] = None
                    for ext in self.image_extensions:
                        candidate = json_path.with_name(base_name + ext)
                        if candidate.exists():
                            img_path = candidate
                            break

                    if not img_path:
                        result["statistics"]["missing_images"] += 1
                        result["statistics"]["skipped"] += 1
                        self.logger.warning(f"未找到图片: {json_path}")
                        continue

                    copy_file_safe(img_path, images_dir / img_path.name)

                    label_file = labels_dir / f"{base_name}{self.label_extension}"
                    with label_file.open("w", encoding="utf-8") as f:
                        for shape in data.get("shapes", []):
                            label = shape.get("label")
                            if label not in class_mapping:
                                continue

                            points = shape.get("points", [])
                            if len(points) < 2:
                                continue

                            xmin, ymin, xmax, ymax = polygon_to_bbox(points)
                            x, y, w, h = normalize_bbox(
                                xmin, ymin, xmax, ymax, img_w, img_h
                            )

                            class_id = class_mapping[label]
                            f.write(f"{class_id} {x:.10f} {y:.10f} {w:.10f} {h:.10f}\n")

                    result["statistics"]["converted"] += 1
                except Exception as e:
                    result["statistics"]["errors"] += 1
                    result["success"] = False
                    self.logger.error(f"处理失败 {json_path}: {e}")
                finally:
                    progress.update_progress(1)

        classes_path = output_path / self.classes_file
        with classes_path.open("w", encoding="utf-8") as f:
            for cls in final_classes:
                f.write(f"{cls}\n")

        return result

    def convert_xlabel_to_yolo_segmentation(
        self,
        source_dir: str,
        output_dir: Optional[str] = None,
        class_order: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """X-label数据转YOLO分割格式（基于Labelme JSON）"""
        source_path = validate_path(source_dir, must_exist=True, must_be_dir=True)

        if output_dir:
            output_path = Path(output_dir)
        else:
            name = source_path.name
            output_path = source_path.parent / f"{name}_dataset"

        create_directory(output_path)
        images_dir = output_path / "images"
        labels_dir = output_path / "labels"
        create_directory(images_dir)
        create_directory(labels_dir)

        scan_result = scan_xlabel_dataset_recursive(
            source_path,
            warn_json_read_failed=lambda json_path, error: self.logger.warning(
                f"读取JSON失败 {json_path}: {error}"
            ),
        )

        json_files: List[Path] = scan_result["json_files"]
        detected_classes: Set[str] = scan_result["classes"]
        if not detected_classes:
            raise DatasetError("未检测到任何类别", dataset_path=str(source_path))

        if class_order:
            if len(class_order) != len(set(class_order)):
                raise DatasetError(
                    "class_order包含重复类别", dataset_path=str(source_path)
                )
            if set(class_order) != detected_classes:
                raise DatasetError(
                    "class_order与检测到的类别不一致",
                    dataset_path=str(source_path),
                )
            final_classes = class_order
        else:
            final_classes = sorted(detected_classes)
        class_mapping = {name: idx for idx, name in enumerate(final_classes)}

        result: Dict[str, Any] = {
            "success": True,
            "input_path": str(source_path),
            "output_path": str(output_path),
            "classes": final_classes,
            "class_mapping": class_mapping,
            "statistics": {
                "json_files": len(json_files),
                "converted": 0,
                "missing_images": 0,
                "skipped": 0,
                "errors": 0,
            },
        }

        def normalize_polygon(
            points: List[List[float]], img_w: int, img_h: int
        ) -> List[float]:
            normalized: List[float] = []
            for point in points:
                x, y = point
                x = max(0, min(1, x / img_w))
                y = max(0, min(1, y / img_h))
                normalized.extend([x, y])
            return normalized

        with progress_context(len(json_files), "X-label转YOLO-分割") as progress:
            for json_path in json_files:
                try:
                    with json_path.open("r", encoding="utf-8") as f:
                        data = json.load(f)

                    img_w = data.get("imageWidth")
                    img_h = data.get("imageHeight")
                    if not img_w or not img_h:
                        raise ValueError("缺少 imageWidth/imageHeight")

                    image_path = data.get("imagePath")
                    if not image_path:
                        raise ValueError("缺少 imagePath")
                    base_name = Path(image_path).stem
                    img_path: Optional[Path] = None
                    for ext in self.image_extensions:
                        candidate = json_path.with_name(base_name + ext)
                        if candidate.exists():
                            img_path = candidate
                            break

                    if not img_path:
                        result["statistics"]["missing_images"] += 1
                        result["statistics"]["skipped"] += 1
                        self.logger.warning(f"未找到图片: {json_path}")
                        continue

                    copy_file_safe(img_path, images_dir / img_path.name)

                    label_file = labels_dir / f"{base_name}{self.label_extension}"
                    with label_file.open("w", encoding="utf-8") as f:
                        for shape in data.get("shapes", []):
                            label = shape.get("label")
                            if label not in class_mapping:
                                continue

                            points = shape.get("points", [])
                            if len(points) < 3:
                                continue

                            coords = normalize_polygon(points, img_w, img_h)
                            if not coords:
                                continue

                            class_id = class_mapping[label]
                            coords_str = " ".join(f"{v:.10f}" for v in coords)
                            f.write(f"{class_id} {coords_str}\n")

                    result["statistics"]["converted"] += 1
                except Exception as e:
                    result["statistics"]["errors"] += 1
                    result["success"] = False
                    self.logger.error(f"处理失败 {json_path}: {e}")
                finally:
                    progress.update_progress(1)

        classes_path = output_path / self.classes_file
        with classes_path.open("w", encoding="utf-8") as f:
            for cls in final_classes:
                f.write(f"{cls}\n")

        return result

    def convert_yolo_to_xlabel(
        self, dataset_path: str, output_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """YOLO检测数据集转X-label格式"""
        return self._convert_yolo_to_xlabel(dataset_path, output_dir, mode="detection")

    def convert_yolo_to_xlabel_segmentation(
        self, dataset_path: str, output_dir: Optional[str] = None
    ) -> Dict[str, Any]:
        """YOLO分割数据集转X-label格式"""
        return self._convert_yolo_to_xlabel(
            dataset_path, output_dir, mode="segmentation"
        )

    def _convert_yolo_to_xlabel(
        self, dataset_path: str, output_dir: Optional[str], mode: str
    ) -> Dict[str, Any]:
        dataset_dir = validate_path(dataset_path, must_exist=True, must_be_dir=True)
        dataset_dir = self._detect_dataset_root(dataset_dir)

        images_dir = dataset_dir / "images"
        labels_dir = dataset_dir / "labels"
        if not images_dir.exists():
            raise DatasetError("未找到images目录", dataset_path=str(dataset_dir))
        if not labels_dir.exists():
            raise DatasetError("未找到labels目录", dataset_path=str(dataset_dir))

        if output_dir:
            output_path = Path(output_dir)
        else:
            output_path = dataset_dir.parent / f"{dataset_dir.name}_xlabel"
        create_directory(output_path)

        # 读取类别文件
        classes_file = dataset_dir / self.classes_file
        class_names: List[str] = []
        if classes_file.exists():
            with classes_file.open("r", encoding="utf-8") as f:
                class_names = [line.strip() for line in f if line.strip()]

        image_files = get_file_list(images_dir, self.image_extensions, recursive=False)

        result: Dict[str, Any] = {
            "success": True,
            "input_path": str(dataset_dir),
            "output_path": str(output_path),
            "mode": mode,
            "statistics": {
                "total_images": len(image_files),
                "converted": 0,
                "missing_labels": 0,
                "missing_images": 0,
                "errors": 0,
            },
        }

        def class_name_from_id(class_id: int) -> str:
            if 0 <= class_id < len(class_names):
                return class_names[class_id]
            return f"class_{class_id}"

        def load_image_size(image_path: Path) -> Tuple[int, int]:
            from PIL import Image

            with Image.open(image_path) as img:
                return img.size  # (width, height)

        def clamp(value: float, min_value: float, max_value: float) -> float:
            return max(min_value, min(max_value, value))

        with progress_context(len(image_files), "YOLO转X-label") as progress:
            for img_path in image_files:
                try:
                    base_name = img_path.stem
                    label_path = labels_dir / f"{base_name}{self.label_extension}"

                    if not label_path.exists():
                        result["statistics"]["missing_labels"] += 1
                        progress.update_progress(1)
                        continue

                    img_w, img_h = load_image_size(img_path)

                    shapes: List[Dict[str, Any]] = []
                    with label_path.open("r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            parts = line.split()
                            if len(parts) < 5:
                                continue

                            try:
                                class_id = int(float(parts[0]))
                            except ValueError:
                                continue

                            label = class_name_from_id(class_id)

                            if mode == "detection":
                                if len(parts) != 5:
                                    continue
                                x_center, y_center, width, height = map(
                                    float, parts[1:5]
                                )
                                xmin = (x_center - width / 2.0) * img_w
                                ymin = (y_center - height / 2.0) * img_h
                                xmax = (x_center + width / 2.0) * img_w
                                ymax = (y_center + height / 2.0) * img_h

                                xmin = clamp(xmin, 0.0, img_w)
                                xmax = clamp(xmax, 0.0, img_w)
                                ymin = clamp(ymin, 0.0, img_h)
                                ymax = clamp(ymax, 0.0, img_h)

                                points = [
                                    [xmin, ymin],
                                    [xmax, ymin],
                                    [xmax, ymax],
                                    [xmin, ymax],
                                ]
                                shape_type = "rectangle"
                            else:
                                coords = list(map(float, parts[1:]))
                                if len(coords) < 6 or len(coords) % 2 != 0:
                                    continue
                                points = []
                                for i in range(0, len(coords), 2):
                                    x = clamp(coords[i] * img_w, 0.0, img_w)
                                    y = clamp(coords[i + 1] * img_h, 0.0, img_h)
                                    points.append([x, y])
                                shape_type = "polygon"

                            shapes.append(
                                {
                                    "label": label,
                                    "score": None,
                                    "points": points,
                                    "group_id": None,
                                    "description": None,
                                    "difficult": False,
                                    "shape_type": shape_type,
                                    "flags": {},
                                    "attributes": {},
                                    "kie_linking": [],
                                }
                            )

                    if not shapes:
                        progress.update_progress(1)
                        continue

                    # 复制图片
                    copy_file_safe(img_path, output_path / img_path.name)

                    json_data: Dict[str, Any] = {
                        "version": "3.3.5",
                        "flags": {},
                        "shapes": shapes,
                        "imagePath": img_path.name,
                        "imageData": None,
                        "imageHeight": img_h,
                        "imageWidth": img_w,
                    }

                    json_path = output_path / f"{base_name}.json"
                    with json_path.open("w", encoding="utf-8") as f:
                        json.dump(json_data, f, ensure_ascii=False, indent=2)

                    result["statistics"]["converted"] += 1
                except Exception as e:
                    result["statistics"]["errors"] += 1
                    result["success"] = False
                    self.logger.error(f"转换失败 {img_path}: {e}")
                finally:
                    progress.update_progress(1)

        return result

    def continue_ctds_processing(
        self,
        pre_result: Dict[str, Any],
        confirmed_type: str,
        keep_empty_labels: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """继续CTDS数据处理（在用户确认数据集类型后）

        Args:
            pre_result: 预检测结果
            confirmed_type: 用户确认的数据集类型

        Returns:
            Dict[str, Any]: 处理结果
        """
        return continue_ctds_processing_internal(
            self,
            pre_result=pre_result,
            confirmed_type=confirmed_type,
            keep_empty_labels=keep_empty_labels,
        )

    def _execute_ctds_processing(
        self,
        input_dir: Path,
        project_name: str,
        obj_names_path: Path,
        obj_train_data_path: Path,
        confirmed_type: str,
        pre_detection_result: Dict[str, Any],
        keep_empty_labels: bool = False,
    ) -> Dict[str, Any]:
        """执行CTDS数据处理的核心逻辑"""
        return execute_ctds_processing_internal(
            self,
            input_dir=input_dir,
            project_name=project_name,
            obj_names_path=obj_names_path,
            obj_train_data_path=obj_train_data_path,
            confirmed_type=confirmed_type,
            pre_detection_result=pre_detection_result,
            keep_empty_labels=keep_empty_labels,
        )

    def _get_project_name(
        self,
        obj_names_path: Path,
        manual_name: Optional[str] = None,
    ) -> str:
        """获取项目名称。"""
        return get_project_name(self, obj_names_path, manual_name)

    def _validate_ctds_label_file(
        self,
        label_file: Path,
        dataset_type: str = "detection",
    ) -> str:
        """单次读取并校验 CTDS 标签文件。

        Returns:
            str: "empty" | "valid" | "invalid" | "out_of_bounds"
        """
        try:
            with open(label_file, "r", encoding="utf-8") as file:
                lines = file.readlines()
        except Exception as error:  # noqa: BLE001
            self.logger.error(f"检查标签文件失败 {label_file}: {str(error)}")
            return "invalid"

        has_non_empty_line = False

        for line in lines:
            stripped_line = line.strip()
            if not stripped_line:
                continue

            has_non_empty_line = True
            data = stripped_line.split()

            if dataset_type == "segmentation":
                if len(data) < 7:
                    self.logger.debug(
                        f"文件 {label_file} 分割数据格式错误，需要至少7列: {stripped_line}"
                    )
                    return "invalid"
                if len(data) % 2 == 0:
                    self.logger.debug(
                        f"文件 {label_file} 分割数据列数应为奇数: {stripped_line}"
                    )
                    return "invalid"
                coord_values = data[1:]
            else:
                if len(data) < 5:
                    self.logger.debug(
                        f"文件 {label_file} 检测数据格式错误，需要至少5列: {stripped_line}"
                    )
                    return "invalid"
                if len(data) != 5:
                    self.logger.debug(
                        f"文件 {label_file} 检测数据列数应为5: {stripped_line}"
                    )
                    return "invalid"
                coord_values = data[1:5]

            try:
                class_id = int(data[0])
            except ValueError:
                self.logger.debug(
                    f"文件 {label_file} 中类别ID格式错误: {stripped_line}"
                )
                return "invalid"
            if class_id < 0:
                self.logger.debug(
                    f"文件 {label_file} 中类别ID不能为负数: {stripped_line}"
                )
                return "invalid"

            for index, coord_str in enumerate(coord_values):
                try:
                    coord = float(coord_str)
                except ValueError:
                    self.logger.debug(
                        f"文件 {label_file} 中坐标格式错误: {stripped_line} "
                        f"(第{index+2}列: {coord_str})"
                    )
                    return "invalid"
                if coord < 0.0:
                    self.logger.debug(
                        f"文件 {label_file} 中存在负数坐标: {stripped_line} "
                        f"(第{index+2}列: {coord})"
                    )
                    return "out_of_bounds"
                if coord > 1.0:
                    self.logger.debug(
                        f"文件 {label_file} 中坐标超出范围[0,1]: {stripped_line} "
                        f"(第{index+2}列: {coord})"
                    )
                    return "out_of_bounds"

        if not has_non_empty_line:
            return "empty"

        return "valid"

    def _contains_invalid_ctds_data(
        self, label_file: Path, dataset_type: str = "detection"
    ) -> bool:
        """兼容旧入口：判断标签是否包含无效数据。"""
        return self._validate_ctds_label_file(label_file, dataset_type) in {
            "invalid",
            "out_of_bounds",
        }

    def _is_empty_label_file(self, label_file: Path) -> bool:
        """兼容旧入口：判断标签是否为空（或仅包含空行）。"""
        return self._validate_ctds_label_file(label_file) == "empty"

    def detect_dataset_type(self, dataset_path: str) -> Dict[str, Any]:
        """自动检测 CTDS 数据集类型（检测 / 分割）。"""
        try:
            self.logger.info(f"开始检测数据集类型，路径: {dataset_path}")
            dataset_dir = validate_path(dataset_path, must_exist=True, must_be_dir=True)
            self.logger.info(f"验证路径成功: {dataset_dir}")

            labels_dir = dataset_dir
            self.logger.info(f"查找obj_train_data目录: {labels_dir}")
            if not labels_dir.exists():
                self.logger.error(f"obj_train_data目录不存在: {labels_dir}")
                return {
                    "success": False,
                    "error": "未找到obj_train_data目录",
                    "dataset_type": "unknown",
                }

            label_files = list(labels_dir.glob("*.txt"))
            self.logger.info(f"找到 {len(label_files)} 个txt文件")
            if not label_files:
                self.logger.error("obj_train_data目录中没有找到txt文件")
                return {
                    "success": False,
                    "error": "obj_train_data目录中没有找到txt文件",
                    "dataset_type": "unknown",
                }

            sample_size = min(100, len(label_files))
            sample_files = random.sample(label_files, sample_size)
            self.logger.info(f"随机选择 {sample_size} 个文件进行分析")

            detection_files = 0
            segmentation_files = 0
            analyzed_files = []

            for i, label_file in enumerate(sample_files):
                try:
                    self.logger.info(
                        f"分析文件 {i + 1}/{sample_size}: {label_file.name}"
                    )
                    with open(label_file, "r", encoding="utf-8") as f:
                        lines = f.readlines()

                    self.logger.info(f"文件 {label_file.name} 共有 {len(lines)} 行")

                    detection_lines = 0
                    segmentation_lines = 0
                    valid_lines = 0

                    for line_num, line in enumerate(lines):
                        line = line.strip()
                        if not line:
                            continue

                        parts = line.split()
                        valid_lines += 1

                        if len(parts) == 5:
                            detection_lines += 1
                            if line_num < 3:
                                self.logger.info(
                                    f"文件 {label_file.name} 第 {line_num + 1} 行: {len(parts)} 列 - {line[:50]}..."
                                )
                        else:
                            segmentation_lines += 1
                            if line_num < 3:
                                self.logger.info(
                                    f"文件 {label_file.name} 第 {line_num + 1} 行: {len(parts)} 列 - {line[:50]}..."
                                )

                    if valid_lines == 0:
                        self.logger.warning(
                            f"文件 {label_file.name} 没有找到有效数据行"
                        )
                        continue

                    if detection_lines > segmentation_lines:
                        detection_files += 1
                        file_type = "detection"
                        dominant_columns = 5
                        self.logger.info(
                            f"文件 {label_file.name} 判定为检测格式 (检测行:{detection_lines}, 分割行:{segmentation_lines})"
                        )
                    else:
                        segmentation_files += 1
                        file_type = "segmentation"
                        dominant_columns = max(
                            [
                                len(line.split())
                                for line in lines
                                if line.strip() and len(line.split()) != 5
                            ],
                            default=0,
                        )
                        self.logger.info(
                            f"文件 {label_file.name} 判定为分割格式 (检测行:{detection_lines}, 分割行:{segmentation_lines})"
                        )

                    analyzed_files.append(
                        {
                            "file": label_file.name,
                            "type": file_type,
                            "columns": dominant_columns,
                            "detection_lines": detection_lines,
                            "segmentation_lines": segmentation_lines,
                            "total_lines": valid_lines,
                        }
                    )

                except Exception as e:
                    self.logger.error(f"分析标签文件失败 {label_file}: {str(e)}")
                    continue

            total_analyzed = detection_files + segmentation_files
            self.logger.info(
                f"分析结果: 检测文件={detection_files}, 分割文件={segmentation_files}, 总计={total_analyzed}"
            )

            if total_analyzed == 0:
                dataset_type = "unknown"
                confidence = 0.0
                self.logger.warning("没有成功分析任何文件，数据集类型未知")
            elif detection_files > segmentation_files:
                dataset_type = "detection"
                confidence = detection_files / total_analyzed
                self.logger.info(f"判定为检测数据集，置信度: {confidence:.2f}")
            elif segmentation_files > detection_files:
                dataset_type = "segmentation"
                confidence = segmentation_files / total_analyzed
                self.logger.info(f"判定为分割数据集，置信度: {confidence:.2f}")
            else:
                dataset_type = "mixed"
                confidence = 0.5
                self.logger.info("判定为混合数据集")

            result = {
                "success": True,
                "dataset_type": dataset_type,
                "confidence": confidence,
                "statistics": {
                    "total_files_available": len(label_files),
                    "files_analyzed": total_analyzed,
                    "detection_files": detection_files,
                    "segmentation_files": segmentation_files,
                },
                "sample_files": analyzed_files[:5],
            }

            self.logger.info(f"数据集类型检测完成: {result}")
            return result

        except Exception as e:
            self.logger.error(f"数据集类型检测异常: {str(e)}")
            return {"success": False, "error": str(e), "dataset_type": "unknown"}

    def _build_images_index(self, directory: Path) -> Dict[str, Path]:
        """建立图像 stem 到文件路径的索引（大小写不敏感）。"""
        if not directory.exists():
            return {}

        valid_exts = {ext.lower() for ext in self.image_extensions}
        image_index: Dict[str, Path] = {}
        for entry in directory.iterdir():
            if not entry.is_file():
                continue
            if entry.suffix.lower() not in valid_exts:
                continue
            image_index[entry.stem.lower()] = entry
        return image_index

    def convert_yolo_to_ctds_dataset(
        self, yolo_dataset_path: str, output_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """将YOLO数据集重新封装为CTDS格式"""
        dataset_dir = None

        try:
            dataset_dir = validate_path(
                yolo_dataset_path, must_exist=True, must_be_dir=True
            )
            self.logger.info(f"开始将YOLO数据集转换为CTDS格式: {dataset_dir}")

            labels_dir = dataset_dir / "labels"
            images_dir = dataset_dir / "images"

            if not labels_dir.exists() or not labels_dir.is_dir():
                raise DatasetError(
                    "未找到 labels 目录",
                    dataset_path=str(labels_dir),
                )

            if not images_dir.exists() or not images_dir.is_dir():
                raise DatasetError(
                    "未找到 images 目录",
                    dataset_path=str(images_dir),
                )

            class_candidates = [
                dataset_dir / "obj.names",
                dataset_dir / self.classes_file,
            ]
            classes_source = None
            for candidate in class_candidates:
                if candidate.exists() and candidate.is_file():
                    classes_source = candidate
                    break

            if not classes_source:
                raise DatasetError(
                    "未找到 obj.names 或 classes.txt 文件",
                    dataset_path=str(dataset_dir),
                )

            if output_path:
                output_dir = Path(output_path).resolve()
            else:
                output_dir = (dataset_dir.parent / f"{dataset_dir.name}_ctds").resolve()

            if output_dir == dataset_dir:
                raise DatasetError(
                    "CTDS 输出目录不能与原始YOLO数据集相同",
                    dataset_path=str(output_dir),
                )

            if output_dir.exists():
                if not output_dir.is_dir():
                    raise DatasetError(
                        "CTDS 输出路径存在但不是目录",
                        dataset_path=str(output_dir),
                    )
                if any(output_dir.iterdir()):
                    raise DatasetError(
                        "CTDS 输出目录已存在且非空，请先清理",
                        dataset_path=str(output_dir),
                    )

            create_directory(output_dir)
            obj_train_data_dir = output_dir / "obj_train_data"
            create_directory(obj_train_data_dir)
            obj_names_path = output_dir / "obj.names"
            copy_file_safe(classes_source, obj_names_path)

            try:
                with open(classes_source, "r", encoding="utf-8") as f:
                    class_lines = [line.strip() for line in f if line.strip()]
            except Exception as e:
                raise DatasetError(
                    f"读取类别文件失败: {str(e)}",
                    dataset_path=str(classes_source),
                )
            num_classes = len(class_lines)

            label_files = sorted(
                f
                for f in labels_dir.glob("*.txt")
                if f.is_file() and f.name.lower() != "train.txt"
            )

            result: Dict[str, Any] = {
                "success": True,
                "source_dataset": str(dataset_dir),
                "output_path": str(output_dir),
                "classes_source": str(classes_source),
                "processed_files": {
                    "labels": [],
                    "images": [],
                    "classes_file": str(obj_names_path),
                },
                "missing_images": [],
                "statistics": {
                    "total_labels": len(label_files),
                    "labels_copied": 0,
                    "images_copied": 0,
                    "missing_images": 0,
                    "classes_count": num_classes,
                },
            }

            copied_labels = 0
            copied_images = 0
            missing_images = []
            train_image_names = []
            image_index = self._build_images_index(images_dir)

            with progress_context(len(label_files), "YOLO转CTDS") as progress:
                for label_file in label_files:
                    try:
                        target_label = obj_train_data_dir / label_file.name
                        copy_file_safe(label_file, target_label)
                        result["processed_files"]["labels"].append(str(target_label))
                        copied_labels += 1

                        base_name = label_file.stem
                        image_file = image_index.get(base_name.lower())

                        if image_file:
                            target_image = obj_train_data_dir / image_file.name
                            copy_file_safe(image_file, target_image)
                            result["processed_files"]["images"].append(
                                str(target_image)
                            )
                            copied_images += 1
                            train_image_names.append(target_image.name)
                        else:
                            missing_images.append(str(label_file.name))

                    except Exception as e:
                        self.logger.error(f"复制文件失败 {label_file}: {str(e)}")
                        result["success"] = False
                    finally:
                        progress.update_progress(1)

            result["missing_images"] = missing_images
            result["statistics"]["labels_copied"] = copied_labels
            result["statistics"]["images_copied"] = copied_images
            result["statistics"]["missing_images"] = len(missing_images)

            train_txt_path = output_dir / "train.txt"
            try:
                unique_train_names = train_image_names
                if unique_train_names:
                    train_txt_path.write_text(
                        "\n".join(unique_train_names), encoding="utf-8"
                    )
                else:
                    train_txt_path.write_text("", encoding="utf-8")
            except Exception as e:
                self.logger.warning(f"写入train.txt失败: {e}")

            obj_data_path = output_dir / "obj.data"
            try:
                obj_data_content = (
                    f"classes = {num_classes}\n"
                    "train = data/train.txt\n"
                    "names = data/obj.names\n"
                    "backup = backup/\n"
                )
                obj_data_path.write_text(obj_data_content, encoding="utf-8")
            except Exception as e:
                self.logger.warning(f"写入obj.data失败: {e}")

            result["generated_files"] = {
                "obj_data": str(obj_data_path),
                "train_file": str(train_txt_path),
                "obj_train_data": str(obj_train_data_dir),
            }

            self.logger.info(
                f"YOLO转CTDS完成: {copied_labels} 个标签, {copied_images} 张图像写入 {obj_train_data_dir}"
            )

            if missing_images:
                self.logger.warning(
                    f"以下标签未找到对应图像: {', '.join(missing_images[:5])}"
                    + (" ..." if len(missing_images) > 5 else "")
                )

            return result

        except Exception as e:
            self.logger.error(f"YOLO转CTDS失败: {str(e)}")
            raise DatasetError(
                f"YOLO转CTDS失败: {str(e)}",
                dataset_path=str(dataset_dir) if dataset_dir else yolo_dataset_path,
            )

    def _convert_images_with_opencv(self, images_dir: Path) -> None:
        """使用OpenCV重新保存图像

        Args:
            images_dir: 图像目录
        """
        try:
            # 只处理jpg文件
            jpg_files = [f for f in images_dir.iterdir() if f.suffix.lower() == ".jpg"]

            if not jpg_files:
                return

            self.logger.info(f"使用OpenCV重新保存 {len(jpg_files)} 个图像文件")

            with progress_context(len(jpg_files), "重新保存图像") as progress:
                for img_file in jpg_files:
                    try:
                        img = cv2_imread_unicode(img_file)
                        if img is not None:
                            cv2_imwrite_unicode(img_file, img)
                        else:
                            self.logger.warning(f"无法读取图像文件: {img_file}")
                    except Exception as e:
                        self.logger.warning(f"处理图像文件失败 {img_file}: {str(e)}")

                    progress.update_progress(1)

            self.logger.info("图像重新保存完成")

        except ImportError:
            raise
        except Exception as e:
            self.logger.error(f"OpenCV图像转换失败: {str(e)}")
            raise

    def detect_name_conflicts(self, dataset_paths: List[Path]) -> Dict[str, Any]:
        """检测待合并图片的名称冲突。"""
        return detect_name_conflicts_internal(self, dataset_paths)

    def merge_datasets(
        self,
        dataset_paths: List[str],
        output_path: str,
        output_name: Optional[str] = None,
        image_prefix: Optional[str] = None,
    ) -> Dict[str, Any]:
        """合并多个YOLO数据集。"""
        return merge_datasets_internal(
            self,
            dataset_paths=dataset_paths,
            output_path=output_path,
            output_name=output_name,
            image_prefix=image_prefix,
        )

    def merge_different_type_datasets(
        self,
        dataset_paths: List[str],
        output_path: str,
        output_name: Optional[str] = None,
        image_prefix: Optional[str] = None,
        dataset_order: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """合并多个不同类型的YOLO数据集。"""
        return merge_different_type_datasets_internal(
            self,
            dataset_paths=dataset_paths,
            output_path=output_path,
            output_name=output_name,
            image_prefix=image_prefix,
            dataset_order=dataset_order,
        )

    def _collect_all_classes_info(
        self, dataset_paths: List[Path]
    ) -> List[Dict[str, Any]]:
        """收集所有数据集的类别信息。"""
        return collect_all_classes_info_internal(self, dataset_paths)

    def _create_unified_class_mapping(
        self, all_classes_info: List[Dict[str, Any]]
    ) -> Tuple[List[str], List[Dict[int, int]]]:
        """创建统一的类别映射。"""
        return create_unified_class_mapping_internal(self, all_classes_info)

    def _generate_different_output_name(
        self,
        unified_classes: List[str],
        dataset_paths: List[Path],
        image_manifest: Optional[List[List[Path]]] = None,
    ) -> str:
        """为不同类型数据集生成输出目录名称。"""
        return generate_different_output_name_internal(
            self,
            unified_classes,
            dataset_paths,
            image_manifest=image_manifest,
        )

    def _merge_different_dataset_files(
        self,
        dataset_paths: List[Path],
        output_dir: Path,
        image_prefix: Optional[str],
        unified_classes: List[str],
        class_mappings: List[Dict[int, int]],
        pre_scanned_images: Optional[List[List[Path]]] = None,
    ) -> Dict[str, Any]:
        """合并不同类型数据集文件

        Args:
            dataset_paths: 数据集路径列表
            output_dir: 输出目录
            image_prefix: 图片前缀
            unified_classes: 统一类别列表
            class_mappings: 类别映射列表

        Returns:
            Dict[str, Any]: 合并结果
        """
        # 性能监控开始
        start_time = time.time()
        total_images = 0
        total_labels = 0
        statistics = []

        # 创建输出子目录
        images_dir = output_dir / "images"
        labels_dir = output_dir / "labels"
        create_directory(images_dir)
        create_directory(labels_dir)

        # 创建统一的classes.txt
        classes_file = output_dir / self.classes_file
        with open(classes_file, "w", encoding="utf-8") as f:
            for class_name in unified_classes:
                f.write(f"{class_name}\n")

        current_index = 1
        pre_scanned_image_lists: List[Optional[List[Path]]]
        if pre_scanned_images is not None:
            pre_scanned_image_lists = [image_list for image_list in pre_scanned_images]
        else:
            pre_scanned_image_lists = [None for _ in dataset_paths]

        for i, dataset_path in enumerate(dataset_paths):
            dataset_start_time = time.time()
            self.logger.info(f"处理数据集 {i+1}/{len(dataset_paths)}: {dataset_path}")

            # 获取数据集文件
            image_files = pre_scanned_image_lists[i]
            if image_files is None:
                image_files = get_file_list(
                    dataset_path, self.image_extensions, recursive=True
                )
            label_files = get_file_list(
                dataset_path, [self.label_extension], recursive=True
            )

            # 过滤掉classes.txt
            label_files = [lbl for lbl in label_files if lbl.name != self.classes_file]

            dataset_stats = {
                "dataset_path": str(dataset_path),
                "images_count": len(image_files),
                "labels_count": len(label_files),
                "start_index": current_index,
            }

            # 建立标签映射索引
            label_mapping = self._build_label_mapping(label_files)

            # 处理图像和标签文件
            images_processed = 0
            labels_processed = 0

            for image_file in image_files:
                try:
                    # 生成新的文件名
                    new_name = (
                        image_file.name
                        if image_prefix is None
                        else f"{image_prefix}_{current_index:05d}{image_file.suffix}"
                    )
                    new_image_path = images_dir / new_name

                    # 复制图像文件
                    copy_file_safe(image_file, new_image_path)
                    images_processed += 1

                    # 查找对应的标签文件
                    stem = image_file.stem
                    if stem in label_mapping:
                        label_file = label_mapping[stem]
                        new_label_name = (
                            label_file.name
                            if image_prefix is None
                            else f"{image_prefix}_{current_index:05d}.txt"
                        )
                        new_label_path = labels_dir / new_label_name

                        # 复制并转换标签文件
                        self._copy_and_convert_label(
                            label_file, new_label_path, class_mappings[i]
                        )
                        labels_processed += 1

                except Exception as e:
                    self.logger.error(f"处理文件失败 {image_file}: {str(e)}")
                finally:
                    current_index += 1

            dataset_time = time.time() - dataset_start_time
            dataset_stats.update(
                {
                    "end_index": current_index - 1,
                    "images_processed": images_processed,
                    "labels_processed": labels_processed,
                    "processing_time": round(dataset_time, 2),
                }
            )

            statistics.append(dataset_stats)
            total_images += images_processed
            total_labels += labels_processed

            self.logger.info(
                f"数据集 {i+1} 处理完成: {images_processed} 图像, {labels_processed} 标签"
            )

        total_time = time.time() - start_time

        return {
            "total_images": total_images,
            "total_labels": total_labels,
            "statistics": statistics,
            "processing_time": round(total_time, 2),
        }

    def _copy_and_convert_label(
        self, source_label: Path, target_label: Path, class_mapping: Dict[int, int]
    ) -> None:
        """复制并转换标签文件的类别ID

        Args:
            source_label: 源标签文件
            target_label: 目标标签文件
            class_mapping: 类别映射字典
        """
        try:
            with open(source_label, "r", encoding="utf-8") as f:
                lines = f.readlines()

            converted_lines = []
            for line in lines:
                line = line.strip()
                if not line:
                    continue

                parts = line.split()
                if len(parts) < 5:  # 至少需要类别ID和4个坐标
                    continue

                try:
                    old_class_id = int(parts[0])
                    if old_class_id in class_mapping:
                        new_class_id = class_mapping[old_class_id]
                        parts[0] = str(new_class_id)
                        converted_lines.append(" ".join(parts))
                    else:
                        self.logger.warning(
                            f"标签文件 {source_label} 中发现未知类别ID: {old_class_id}"
                        )
                except ValueError:
                    self.logger.warning(
                        f"标签文件 {source_label} 中发现无效类别ID: {parts[0]}"
                    )

            with open(target_label, "w", encoding="utf-8") as f:
                for line in converted_lines:
                    f.write(f"{line}\n")

        except Exception as e:
            self.logger.error(f"转换标签文件失败 {source_label}: {str(e)}")
            raise

    def _validate_classes_consistency(
        self, dataset_paths: List[Path]
    ) -> Dict[str, Any]:
        """验证所有数据集的classes.txt是否一致。"""
        return validate_classes_consistency_internal(self, dataset_paths)

    def _generate_output_name(
        self,
        classes: List[str],
        dataset_paths: List[Path],
        image_manifest: Optional[List[List[Path]]] = None,
    ) -> str:
        """生成输出目录名称。"""
        return generate_output_name_internal(
            self,
            classes,
            dataset_paths,
            image_manifest=image_manifest,
        )

    def _merge_dataset_files(
        self,
        dataset_paths: List[Path],
        output_dir: Path,
        image_prefix: Optional[str],
        classes: List[str],
        pre_scanned_images: Optional[List[List[Path]]] = None,
    ) -> Dict[str, Any]:
        """合并数据集文件（优化版本）

        Args:
            dataset_paths: 数据集路径列表
            output_dir: 输出目录
            image_prefix: 图片前缀
            classes: 类别列表

        Returns:
            Dict[str, Any]: 合并结果
        """
        # 性能监控开始
        start_time = time.time()
        total_images = 0
        total_labels = 0
        statistics: List[Dict[str, Any]] = []
        dataset_times: List[float] = []
        total_size_bytes = 0
        performance_stats: Dict[str, Any] = {
            "start_time": start_time,
            "dataset_times": dataset_times,
            "total_size_bytes": 0,
            "avg_file_size": 0,
        }

        # 创建输出子目录
        images_dir = output_dir / "images"
        labels_dir = output_dir / "labels"
        create_directory(images_dir)
        create_directory(labels_dir)

        # 复制classes.txt
        classes_file = output_dir / self.classes_file
        with open(classes_file, "w", encoding="utf-8") as f:
            for class_name in classes:
                f.write(f"{class_name}\n")

        current_index = 1
        pre_scanned_image_lists: List[Optional[List[Path]]]
        if pre_scanned_images is not None:
            pre_scanned_image_lists = [image_list for image_list in pre_scanned_images]
        else:
            pre_scanned_image_lists = [None for _ in dataset_paths]

        for i, dataset_path in enumerate(dataset_paths):
            dataset_start_time = time.time()
            self.logger.info(f"处理数据集 {i+1}/{len(dataset_paths)}: {dataset_path}")

            # 获取数据集文件
            image_files = pre_scanned_image_lists[i]
            if image_files is None:
                image_files = get_file_list(
                    dataset_path, self.image_extensions, recursive=True
                )
            label_files = get_file_list(
                dataset_path, [self.label_extension], recursive=True
            )

            # 过滤掉classes.txt
            label_files = [lbl for lbl in label_files if lbl.name != self.classes_file]

            # 计算数据集大小
            dataset_size = sum(f.stat().st_size for f in image_files if f.exists())
            dataset_size += sum(f.stat().st_size for f in label_files if f.exists())
            total_size_bytes += dataset_size
            performance_stats["total_size_bytes"] = total_size_bytes

            dataset_stats = {
                "dataset_path": str(dataset_path),
                "images_count": len(image_files),
                "labels_count": len(label_files),
                "start_index": current_index,
                "dataset_size_mb": round(dataset_size / (1024 * 1024), 2),
            }

            # 预建立标签映射索引（优化点1）
            mapping_start = time.time()
            self.logger.info("建立标签映射索引...")
            label_mapping = self._build_label_mapping(label_files)
            mapping_time = time.time() - mapping_start

            # 使用并行处理（优化点2）
            processing_start = time.time()
            dataset_result = self._merge_dataset_parallel(
                image_files,
                images_dir,
                labels_dir,
                image_prefix,
                current_index,
                label_mapping,
                i + 1,
            )
            processing_time = time.time() - processing_start

            total_images += dataset_result["images_processed"]
            total_labels += dataset_result["labels_processed"]
            current_index += dataset_result["images_processed"]

            dataset_end_time = time.time()
            dataset_total_time = dataset_end_time - dataset_start_time

            # 计算处理速度
            files_per_second = (
                len(image_files) / dataset_total_time if dataset_total_time > 0 else 0
            )
            mb_per_second = (
                (dataset_size / (1024 * 1024)) / dataset_total_time
                if dataset_total_time > 0
                else 0
            )

            dataset_stats.update(
                {
                    "end_index": current_index - 1,
                    "processing_time_seconds": round(dataset_total_time, 2),
                    "mapping_time_seconds": round(mapping_time, 3),
                    "copy_time_seconds": round(processing_time, 2),
                    "files_per_second": round(files_per_second, 1),
                    "mb_per_second": round(mb_per_second, 1),
                    "failed_count": dataset_result.get("failed_count", 0),
                }
            )

            dataset_times.append(dataset_total_time)
            statistics.append(dataset_stats)

            self.logger.info(
                f"数据集 {i+1} 完成: {len(image_files)} 文件, "
                f"{round(dataset_total_time, 1)}秒, "
                f"{round(files_per_second, 1)} 文件/秒, "
                f"{round(mb_per_second, 1)} MB/秒"
            )

        # 计算总体性能统计
        end_time = time.time()
        total_time = end_time - start_time
        performance_stats["avg_file_size"] = (
            round(total_size_bytes / total_images / 1024, 1) if total_images > 0 else 0
        )
        performance_stats.update(
            {
                "end_time": end_time,
                "total_time_seconds": round(total_time, 2),
                "total_time_formatted": self._format_duration(total_time),
                "overall_files_per_second": (
                    round(total_images / total_time, 1) if total_time > 0 else 0
                ),
                "overall_mb_per_second": (
                    round(
                        (performance_stats["total_size_bytes"] / (1024 * 1024))
                        / total_time,
                        1,
                    )
                    if total_time > 0
                    else 0
                ),
            }
        )

        self.logger.info(f"合并完成! 总计: {total_images} 图像, {total_labels} 标签")
        self.logger.info(f"总耗时: {performance_stats['total_time_formatted']}")
        self.logger.info(
            f"平均速度: {performance_stats['overall_files_per_second']} 文件/秒, "
            f"{performance_stats['overall_mb_per_second']} MB/秒"
        )

        return {
            "total_images": total_images,
            "total_labels": total_labels,
            "statistics": statistics,
            "performance": performance_stats,
        }

    def _build_label_mapping(self, label_files: List[Path]) -> Dict[str, Path]:
        """预建立标签文件映射索引

        Args:
            label_files: 标签文件列表

        Returns:
            Dict[str, Path]: 基础名称到标签文件路径的映射
        """
        return build_label_mapping_internal(self, label_files)

    def _format_duration(self, seconds: float) -> str:
        """格式化时间显示

        Args:
            seconds: 秒数

        Returns:
            str: 格式化的时间字符串
        """
        return format_duration(seconds)

    def _merge_dataset_parallel(
        self,
        image_files: List[Path],
        images_dir: Path,
        labels_dir: Path,
        image_prefix: Optional[str],
        start_index: int,
        label_mapping: Dict[str, Path],
        dataset_num: int,
    ) -> Dict[str, int]:
        """并行合并数据集文件

        Args:
            image_files: 图像文件列表
            images_dir: 图像输出目录
            labels_dir: 标签输出目录
            image_prefix: 图片前缀
            start_index: 起始索引
            label_mapping: 标签文件映射
            dataset_num: 数据集编号

        Returns:
            Dict[str, int]: 处理结果统计
        """
        return merge_dataset_parallel_internal(
            self,
            image_files=image_files,
            images_dir=images_dir,
            labels_dir=labels_dir,
            image_prefix=image_prefix,
            start_index=start_index,
            label_mapping=label_mapping,
            dataset_num=dataset_num,
        )
