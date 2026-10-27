#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
image_processor.py

图像处理器

提供图像格式转换、尺寸调整、质量优化等功能。
"""

import math
import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

try:
    from tqdm import tqdm

    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

try:
    import cv2

    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

try:
    from PIL import Image

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from ...config.exceptions import FileProcessingError, ProcessingError
from ...core.base import BaseProcessor
from ...core.progress import process_with_progress
from ...core.utils import (
    create_directory,
    cv2_imread_unicode,
    cv2_imwrite_unicode,
    format_file_size,
    get_file_list,
    get_unique_filename,
    validate_path,
)


class ImageProcessor(BaseProcessor):
    """图像处理器

    提供图像格式转换、尺寸调整、质量优化等功能。

    Attributes:
        supported_formats (List[str]): 支持的图像格式
        default_quality (int): 默认图像质量
    """

    def __init__(self, **kwargs):
        """初始化图像处理器"""
        # 先设置属性，再调用父类初始化
        self.supported_formats = [".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"]
        self.default_quality = 95

        # 检查依赖
        self._check_dependencies()

        # 调用父类初始化
        super().__init__(name="ImageProcessor", **kwargs)

    def initialize(self) -> None:
        """初始化处理器"""
        self.logger.info("图像处理器初始化完成")
        self.logger.debug(f"支持的格式: {self.supported_formats}")
        self.logger.debug(f"OpenCV可用: {CV2_AVAILABLE}")
        self.logger.debug(f"PIL可用: {PIL_AVAILABLE}")

    def _check_dependencies(self) -> None:
        """检查依赖库"""
        if not CV2_AVAILABLE and not PIL_AVAILABLE:
            raise ProcessingError(
                "图像处理需要安装 opencv-python 或 Pillow 库\n"
                "请运行: pip install opencv-python Pillow",
                error_code="MISSING_DEPENDENCIES",
                context={"missing_dependencies": ["opencv-python", "Pillow"]},
            )

        if not PIL_AVAILABLE:
            self.logger.warning("Pillow 库未安装，某些功能可能不可用")

        if not CV2_AVAILABLE:
            self.logger.warning("OpenCV 库未安装，某些功能可能不可用")

    def process(self, *args, **kwargs) -> Any:
        """主要处理方法（由子方法实现具体功能）"""
        raise NotImplementedError("请使用具体的处理方法")

    def convert_format(
        self,
        input_path: str,
        target_format: str,
        output_path: Optional[str] = None,
        quality: Optional[int] = None,
        recursive: bool = False,
    ) -> Dict[str, Any]:
        """转换图像格式（兼容性方法）

        Args:
            input_path: 输入路径（文件或目录）
            target_format: 目标格式
            output_path: 输出路径（可选）
            quality: 图像质量 (1-100)
            recursive: 是否递归处理

        Returns:
            Dict[str, Any]: 转换结果
        """
        # 处理单个文件的情况
        input_path_obj = Path(input_path)
        if input_path_obj.is_file():
            # 单个文件转换
            if output_path is None:
                output_path_obj = (
                    input_path_obj.parent
                    / f"{input_path_obj.stem}.{target_format.lstrip('.')}"
                )
            else:
                output_path_obj = Path(output_path)
                if output_path_obj.is_dir():
                    output_path_obj = (
                        output_path_obj
                        / f"{input_path_obj.stem}.{target_format.lstrip('.')}"
                    )

            # 转换单个文件
            self._convert_single_image(
                input_path_obj,
                output_path_obj,
                target_format,
                quality or self.default_quality,
            )

            # 返回结果
            input_size = input_path_obj.stat().st_size
            output_size = output_path_obj.stat().st_size

            return {
                "success": True,
                "input_file": str(input_path_obj),
                "output_file": str(output_path_obj),
                "input_size": input_size,
                "output_size": output_size,
                "compression_ratio": (
                    output_size / input_size if input_size > 0 else 1.0
                ),
                "statistics": {
                    "total_files": 1,
                    "converted_count": 1,
                    "failed_count": 0,
                },
            }

        # 目录转换
        if output_path is None:
            output_path = f"{input_path}_converted"

        return self.convert_images(
            input_path, output_path, target_format, quality, recursive
        )

    def convert_images(
        self,
        input_dir: str,
        output_dir: str,
        target_format: str = "jpg",
        quality: Optional[int] = None,
        recursive: bool = False,
    ) -> Dict[str, Any]:
        """批量转换图像格式

        Args:
            input_dir: 输入目录
            output_dir: 输出目录
            target_format: 目标格式
            quality: 图像质量 (1-100)
            recursive: 是否递归处理

        Returns:
            Dict[str, Any]: 转换结果
        """
        try:
            input_path = validate_path(input_dir, must_exist=True, must_be_dir=True)
            output_path = validate_path(output_dir, must_exist=False)

            # 创建输出目录
            create_directory(output_path)

            # 标准化目标格式
            target_format = target_format.lower().lstrip(".")
            if f".{target_format}" not in self.supported_formats:
                raise ProcessingError(f"不支持的目标格式: {target_format}")

            quality = quality or self.default_quality

            self.logger.info(f"开始转换图像: {input_path} -> {output_path}")
            self.logger.info(f"目标格式: {target_format}, 质量: {quality}")

            # 获取图像文件列表
            image_files = get_file_list(input_path, self.supported_formats, recursive)
            self.logger.info(f"找到 {len(image_files)} 个图像文件")
            if len(image_files) == 0:
                self.logger.warning(f"在目录 {input_path} 中没有找到支持的图像文件")
                self.logger.info(f"支持的格式: {self.supported_formats}")
                # 列出目录中的所有文件用于调试
                all_files = list(input_path.glob("*"))
                self.logger.info(
                    f"目录中的所有文件: {[f.name for f in all_files if f.is_file()]}"
                )

            result: Dict[str, Any] = {
                "success": True,
                "input_dir": str(input_path),
                "output_dir": str(output_path),
                "target_format": target_format,
                "quality": quality,
                "converted_files": [],
                "failed_files": [],
                "statistics": {
                    "total_files": len(image_files),
                    "converted_count": 0,
                    "failed_count": 0,
                    "total_input_size": 0,
                    "total_output_size": 0,
                },
            }

            # 转换图像
            def convert_single_image(img_file: Path) -> Dict[str, Any]:
                try:
                    # 计算输入文件大小
                    input_size = img_file.stat().st_size

                    # 生成输出文件路径
                    if recursive:
                        # 保持目录结构
                        rel_path = img_file.relative_to(input_path)
                        output_file = output_path / rel_path.with_suffix(
                            f".{target_format}"
                        )
                        create_directory(output_file.parent)
                    else:
                        output_file = output_path / f"{img_file.stem}.{target_format}"

                    # 确保文件名唯一
                    output_file = get_unique_filename(
                        output_file.parent, output_file.name
                    )

                    # 转换图像
                    self._convert_single_image(
                        img_file, output_file, target_format, quality
                    )

                    # 计算输出文件大小
                    output_size = output_file.stat().st_size

                    return {
                        "success": True,
                        "input_file": str(img_file),
                        "output_file": str(output_file),
                        "input_size": input_size,
                        "output_size": output_size,
                        "compression_ratio": (
                            output_size / input_size if input_size > 0 else 1.0
                        ),
                    }

                except Exception as e:
                    # 记录详细错误信息
                    error_msg = f"压缩文件 {img_file} 失败: {str(e)}"
                    self.logger.error(error_msg)
                    return {
                        "success": False,
                        "input_file": str(img_file),
                        "error": str(e),
                    }

            # 批量处理
            conversion_results = process_with_progress(
                image_files, convert_single_image, f"转换为 {target_format.upper()}"
            )

            # 统计结果
            for conv_result in conversion_results:
                if conv_result and conv_result["success"]:
                    result["converted_files"].append(conv_result)
                    result["statistics"]["converted_count"] += 1
                    result["statistics"]["total_input_size"] += conv_result[
                        "input_size"
                    ]
                    result["statistics"]["total_output_size"] += conv_result[
                        "output_size"
                    ]
                elif conv_result:
                    result["failed_files"].append(conv_result)
                    result["statistics"]["failed_count"] += 1
                    result["success"] = False

            # 添加格式化的大小信息
            result["statistics"]["total_input_size_formatted"] = format_file_size(
                result["statistics"]["total_input_size"]
            )
            result["statistics"]["total_output_size_formatted"] = format_file_size(
                result["statistics"]["total_output_size"]
            )

            if result["statistics"]["total_input_size"] > 0:
                result["statistics"]["overall_compression_ratio"] = (
                    result["statistics"]["total_output_size"]
                    / result["statistics"]["total_input_size"]
                )
            else:
                result["statistics"]["overall_compression_ratio"] = 1.0

            self.logger.info(f"图像转换完成: {result['statistics']}")
            return result

        except Exception as e:
            raise ProcessingError(f"图像转换失败: {str(e)}")

    def resize_images(
        self,
        input_dir: str,
        output_dir: str,
        target_size: Tuple[int, int],
        maintain_aspect_ratio: bool = True,
        recursive: bool = False,
    ) -> Dict[str, Any]:
        """调整图像尺寸

        Args:
            input_dir: 输入路径（文件或目录）
            output_dir: 输出路径
            target_size: 目标尺寸 (width, height)
            maintain_aspect_ratio: 是否保持宽高比
            recursive: 是否递归处理

        Returns:
            Dict[str, Any]: 调整结果
        """
        try:
            input_path = validate_path(input_dir, must_exist=True)

            # 处理单个文件的情况
            if input_path.is_file():
                # 单个文件调整
                if output_dir is None or output_dir == input_dir:
                    output_path = (
                        input_path.parent
                        / f"{input_path.stem}_resized{input_path.suffix}"
                    )
                else:
                    output_path = Path(output_dir)
                    if output_path.is_dir():
                        output_path = output_path / input_path.name

                # 获取原始尺寸
                original_size = self._get_image_size(input_path)

                # 调整单个文件
                self._resize_single_image(
                    input_path, output_path, target_size, maintain_aspect_ratio
                )

                # 获取新尺寸
                new_size = self._get_image_size(output_path)

                return {
                    "success": True,
                    "input_file": str(input_path),
                    "output_file": str(output_path),
                    "target_size": target_size,
                    "maintain_aspect_ratio": maintain_aspect_ratio,
                    "original_size": original_size,
                    "new_size": new_size,
                    "statistics": {
                        "total_files": 1,
                        "resized_count": 1,
                        "failed_count": 0,
                    },
                }

            # 处理目录的情况
            if not input_path.is_dir():
                raise ProcessingError(f"输入路径既不是文件也不是目录: {input_path}")

            output_path = validate_path(output_dir, must_exist=False)

            create_directory(output_path)

            self.logger.info(f"开始调整图像尺寸: {input_path} -> {output_path}")
            self.logger.info(
                f"目标尺寸: {target_size}, 保持宽高比: {maintain_aspect_ratio}"
            )

            # 获取图像文件列表
            image_files = get_file_list(input_path, self.supported_formats, recursive)

            result: Dict[str, Any] = {
                "success": True,
                "input_dir": str(input_path),
                "output_dir": str(output_path),
                "target_size": target_size,
                "maintain_aspect_ratio": maintain_aspect_ratio,
                "resized_files": [],
                "failed_files": [],
                "statistics": {
                    "total_files": len(image_files),
                    "resized_count": 0,
                    "failed_count": 0,
                },
            }

            # 调整图像尺寸
            def resize_single_image(img_file: Path) -> Dict[str, Any]:
                try:
                    # 生成输出文件路径
                    if recursive:
                        rel_path = img_file.relative_to(input_path)
                        output_file = output_path / rel_path
                        create_directory(output_file.parent)
                    else:
                        output_file = output_path / img_file.name

                    # 确保文件名唯一
                    output_file = get_unique_filename(
                        output_file.parent, output_file.name
                    )

                    # 获取原始尺寸
                    original_size = self._get_image_size(img_file)

                    # 调整图像尺寸
                    self._resize_single_image(
                        img_file, output_file, target_size, maintain_aspect_ratio
                    )

                    # 获取新尺寸
                    new_size = self._get_image_size(output_file)

                    return {
                        "success": True,
                        "input_file": str(img_file),
                        "output_file": str(output_file),
                        "original_size": original_size,
                        "new_size": new_size,
                    }

                except Exception as e:
                    return {
                        "success": False,
                        "input_file": str(img_file),
                        "error": str(e),
                    }

            # 批量处理
            resize_results = process_with_progress(
                image_files,
                resize_single_image,
                f"调整尺寸到 {target_size[0]}x{target_size[1]}",
            )

            # 统计结果
            for resize_result in resize_results:
                if resize_result and resize_result["success"]:
                    result["resized_files"].append(resize_result)
                    result["statistics"]["resized_count"] += 1
                elif resize_result:
                    result["failed_files"].append(resize_result)
                    result["statistics"]["failed_count"] += 1
                    result["success"] = False

            self.logger.info(f"图像尺寸调整完成: {result['statistics']}")
            return result

        except Exception as e:
            raise ProcessingError(f"图像尺寸调整失败: {str(e)}")

    def _convert_single_image(
        self, input_file: Path, output_file: Path, target_format: str, quality: int
    ) -> None:
        """转换单个图像文件

        Args:
            input_file: 输入文件路径
            output_file: 输出文件路径
            target_format: 目标格式
            quality: 图像质量
        """
        if PIL_AVAILABLE:
            self._convert_with_pil(input_file, output_file, target_format, quality)
        elif CV2_AVAILABLE:
            self._convert_with_cv2(input_file, output_file, target_format, quality)
        else:
            raise ProcessingError("没有可用的图像处理库")

    def repair_images_with_opencv(
        self,
        directory: Union[str, Path],
        extensions: Optional[List[str]] = None,
        recursive: bool = False,
        include_hidden: bool = False,
    ) -> Dict[str, Any]:
        """尝试使用 OpenCV 读取目录中的图像，加载失败时重新保存"""

        if not CV2_AVAILABLE:
            raise ProcessingError(
                "修复图像需要安装 opencv-python，可通过 pip install opencv-python 安装。"
            )

        dir_path = validate_path(
            os.fsdecode(directory), must_exist=True, must_be_dir=True
        )

        normalized_extensions = self._normalize_extensions(extensions)
        if not normalized_extensions:
            normalized_extensions = [".jpg", ".jpeg", ".png"]

        image_files = []
        entries = dir_path.rglob("*") if recursive else dir_path.iterdir()
        for entry in entries:
            if not entry.is_file():
                continue
            if not include_hidden and entry.name.startswith("."):
                continue
            if entry.suffix.lower() not in normalized_extensions:
                continue
            image_files.append(entry)

        repaired_files: List[str] = []
        failed_files: List[Dict[str, Any]] = []
        loaded_files: List[str] = []
        total_files = len(image_files)

        iterator = image_files
        using_tqdm = TQDM_AVAILABLE and total_files > 0
        if using_tqdm:
            iterator = tqdm(image_files, desc="修复图像", unit="张", total=total_files)

        for img_file in iterator:
            try:
                self._load_and_rewrite(img_file)
                repaired_files.append(str(img_file))
                loaded_files.append(str(img_file))
                continue
            except Exception as exc:
                failed_files.append(
                    {
                        "file": str(img_file),
                        "error": str(exc),
                    }
                )

        if not using_tqdm and total_files > 0:
            print()

        result = {
            "success": True,
            "directory": str(dir_path),
            "extensions": normalized_extensions,
            "recursive": recursive,
            "total_files": total_files,
            "loaded_without_issue": len(loaded_files),
            "repaired_count": len(repaired_files),
            "repaired_files": repaired_files,
            "failed_count": len(failed_files),
            "failed_files": failed_files,
        }

        self.logger.info(
            "图像修复完成: %s，重新保存 %s 张，失败 %s 张",
            dir_path,
            len(repaired_files),
            len(failed_files),
        )

        return result

    def _load_and_rewrite(self, image_path: Path) -> Any:
        try:
            raw = image_path.read_bytes()
        except Exception as exc:
            raise FileProcessingError(
                f"读取图像字节失败: {exc}",
                file_path=str(image_path),
                operation="read_image",
            )

        array = np.frombuffer(raw, dtype=np.uint8)
        image = cv2.imdecode(array, cv2.IMREAD_UNCHANGED)
        if image is None:
            raise FileProcessingError(
                "OpenCV 解码失败",
                file_path=str(image_path),
                operation="read_image",
            )

        suffix = image_path.suffix.lower()
        if suffix in {".jpg", ".jpeg"}:
            fmt = ".jpg"
            params = [cv2.IMWRITE_JPEG_QUALITY, 95]
        elif suffix == ".png":
            fmt = ".png"
            params = [cv2.IMWRITE_PNG_COMPRESSION, 3]
        else:
            # 尽量保留原后缀，但回退到 PNG 以保证通道兼容
            fmt = suffix if suffix and suffix.startswith(".") else ".png"
            params = []
        success, encoded = cv2.imencode(fmt, image, params)
        if not success:
            raise FileProcessingError(
                "OpenCV 无法编码图像",
                file_path=str(image_path),
                operation="encode_image",
            )

        image_path.write_bytes(encoded.tobytes())
        return image

    def _normalize_extensions(self, extensions: Optional[List[str]]) -> List[str]:
        if not extensions:
            return []

        normalized: List[str] = []
        for ext in extensions:
            if not isinstance(ext, str):
                continue
            clean_ext = ext.strip().lower()
            if not clean_ext:
                continue
            if not clean_ext.startswith("."):
                clean_ext = f".{clean_ext}"
            normalized.append(clean_ext)

        return normalized

    def _convert_with_pil(
        self, input_file: Path, output_file: Path, target_format: str, quality: int
    ) -> None:
        """使用PIL转换图像"""
        try:
            with Image.open(input_file) as source_img:
                # 转换为RGB模式（如果需要）
                if target_format.lower() in ["jpg", "jpeg"] and source_img.mode in [
                    "RGBA",
                    "P",
                ]:
                    # 创建白色背景
                    background = Image.new("RGB", source_img.size, (255, 255, 255))
                    rgba_img = (
                        source_img.convert("RGBA")
                        if source_img.mode == "P"
                        else source_img
                    )
                    background.paste(
                        rgba_img,
                        mask=rgba_img.split()[-1] if rgba_img.mode == "RGBA" else None,
                    )
                    final_img = background
                else:
                    final_img = source_img

                # 保存图像
                save_kwargs = {}
                if target_format.lower() in ["jpg", "jpeg"]:
                    save_kwargs["quality"] = quality
                    save_kwargs["optimize"] = True
                elif target_format.lower() == "png":
                    save_kwargs["optimize"] = True
                elif target_format.lower() == "webp":
                    save_kwargs["quality"] = quality
                    save_kwargs["method"] = 6

                # 修复JPG格式问题
                pil_format = target_format.upper()
                if pil_format == "JPG":
                    pil_format = "JPEG"  # PIL使用JPEG而不是JPG
                final_img.save(output_file, format=pil_format, **save_kwargs)
        except Exception as e:
            raise FileProcessingError(
                f"PIL转换图像失败: {str(e)}",
                file_path=str(input_file),
                operation="convert",
            )

    def _convert_with_cv2(
        self, input_file: Path, output_file: Path, target_format: str, quality: int
    ) -> None:
        """使用OpenCV转换图像"""
        try:
            # 读取图像
            img = cv2_imread_unicode(input_file)
            if img is None:
                raise FileProcessingError(f"无法读取图像: {input_file}")

            # 设置保存参数
            save_params = []
            if target_format.lower() in ["jpg", "jpeg"]:
                save_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
            elif target_format.lower() == "png":
                # PNG压缩级别 (0-9)
                compression_level = int((100 - quality) / 10)
                save_params = [cv2.IMWRITE_PNG_COMPRESSION, compression_level]
            elif target_format.lower() == "webp":
                save_params = [cv2.IMWRITE_WEBP_QUALITY, quality]

            # 保存图像
            success = cv2_imwrite_unicode(output_file, img, save_params)
            if not success:
                raise FileProcessingError(f"保存图像失败: {output_file}")

        except Exception as e:
            raise FileProcessingError(
                f"OpenCV转换图像失败: {str(e)}",
                file_path=str(input_file),
                operation="convert",
            )

    def _resize_single_image(
        self,
        input_file: Path,
        output_file: Path,
        target_size: Tuple[int, int],
        maintain_aspect_ratio: bool,
    ) -> None:
        """调整单个图像尺寸"""
        if PIL_AVAILABLE:
            self._resize_with_pil(
                input_file, output_file, target_size, maintain_aspect_ratio
            )
        elif CV2_AVAILABLE:
            self._resize_with_cv2(
                input_file, output_file, target_size, maintain_aspect_ratio
            )
        else:
            raise ProcessingError("没有可用的图像处理库")

    def _resize_with_pil(
        self,
        input_file: Path,
        output_file: Path,
        target_size: Tuple[int, int],
        maintain_aspect_ratio: bool,
    ) -> None:
        """使用PIL调整图像尺寸"""
        try:
            with Image.open(input_file) as source_img:
                if maintain_aspect_ratio:
                    # 保持宽高比
                    source_img.thumbnail(target_size, Image.Resampling.LANCZOS)
                    source_img.save(output_file)
                else:
                    # 直接调整到目标尺寸
                    resized_img = source_img.resize(
                        target_size, Image.Resampling.LANCZOS
                    )
                    resized_img.save(output_file)

        except Exception as e:
            raise FileProcessingError(
                f"PIL调整图像尺寸失败: {str(e)}",
                file_path=str(input_file),
                operation="resize",
            )

    def _resize_with_cv2(
        self,
        input_file: Path,
        output_file: Path,
        target_size: Tuple[int, int],
        maintain_aspect_ratio: bool,
    ) -> None:
        """使用OpenCV调整图像尺寸"""
        try:
            # 读取图像
            img = cv2_imread_unicode(input_file)
            if img is None:
                raise FileProcessingError(f"无法读取图像: {input_file}")

            h, w = img.shape[:2]
            target_w, target_h = target_size

            if maintain_aspect_ratio:
                # 计算缩放比例
                scale = min(target_w / w, target_h / h)
                new_w = int(w * scale)
                new_h = int(h * scale)
            else:
                new_w, new_h = target_w, target_h

            # 调整尺寸
            resized_img = cv2.resize(
                img, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4
            )

            # 保存图像
            success = cv2_imwrite_unicode(output_file, resized_img)
            if not success:
                raise FileProcessingError(f"保存图像失败: {output_file}")

        except Exception as e:
            raise FileProcessingError(
                f"OpenCV调整图像尺寸失败: {str(e)}",
                file_path=str(input_file),
                operation="resize",
            )

    def _get_image_size(self, image_file: Path) -> Tuple[int, int]:
        """获取图像尺寸

        Args:
            image_file: 图像文件路径

        Returns:
            Tuple[int, int]: 图像尺寸 (width, height)
        """
        if PIL_AVAILABLE:
            try:
                with Image.open(image_file) as img:
                    return img.size
            except Exception:
                pass

        if CV2_AVAILABLE:
            try:
                img = cv2_imread_unicode(image_file)
                if img is not None:
                    h, w = img.shape[:2]
                    return (w, h)
            except Exception:
                pass

        raise ProcessingError(f"无法获取图像尺寸: {image_file}")

    def compress_images(
        self,
        input_dir: str,
        output_dir: Optional[str] = None,
        quality: int = 85,
        target_format: Optional[str] = None,
        recursive: bool = False,
        max_size: Optional[Tuple[int, int]] = None,
    ) -> Dict[str, Any]:
        """压缩图像

        Args:
            input_dir: 输入路径（文件或目录）
            output_dir: 输出目录（可选，默认为输入目录下的compressed子目录）
            quality: 压缩质量 (1-100，默认85)
            target_format: 目标格式（可选，默认保持原格式）
            recursive: 是否递归处理
            max_size: 最大尺寸限制 (width, height)，超过此尺寸的图像会被缩小

        Returns:
            Dict[str, Any]: 压缩结果
        """
        # 参数验证（在try块外，让验证错误能够正确抛出）
        input_path = validate_path(input_dir, must_exist=True)

        # 验证质量参数
        if not 1 <= quality <= 100:
            raise ProcessingError("质量参数必须在1-100之间")

        try:
            # 处理单个文件的情况
            if input_path.is_file():
                # 确定输出格式
                output_format = target_format or input_path.suffix.lstrip(".").lower()
                if output_format not in ["jpg", "jpeg", "png", "webp"]:
                    output_format = "jpg"  # 默认转为jpg以获得更好的压缩

                # 设置输出路径
                if output_dir is None:
                    output_path = (
                        input_path.parent
                        / f"{input_path.stem}_compressed.{output_format}"
                    )
                else:
                    output_dir_path = validate_path(output_dir, must_exist=False)
                    create_directory(output_dir_path)
                    output_path = (
                        output_dir_path
                        / f"{input_path.stem}_compressed.{output_format}"
                    )

                # 确保文件名唯一
                output_path = get_unique_filename(output_path.parent, output_path.name)

                self.logger.info(f"开始压缩单个图像: {input_path} -> {output_path}")
                self.logger.info(f"压缩质量: {quality}")
                if max_size:
                    self.logger.info(f"最大尺寸限制: {max_size}")

                # 计算输入文件大小
                input_size = input_path.stat().st_size

                # 压缩图像
                self._compress_single_image(
                    input_path, output_path, quality, output_format, max_size
                )

                # 计算输出文件大小
                output_size = output_path.stat().st_size
                space_saved = input_size - output_size
                compression_ratio = (
                    (1 - output_size / input_size) * 100 if input_size > 0 else 0
                )

                return {
                    "success": True,
                    "input_file": str(input_path),
                    "output_file": str(output_path),
                    "quality": quality,
                    "target_format": output_format,
                    "max_size": max_size,
                    "input_size": input_size,
                    "output_size": output_size,
                    "space_saved": space_saved,
                    "compression_ratio": compression_ratio,
                    "statistics": {
                        "total_files": 1,
                        "compressed_count": 1,
                        "failed_count": 0,
                        "total_input_size": input_size,
                        "total_output_size": output_size,
                        "space_saved": space_saved,
                        "total_input_size_formatted": format_file_size(input_size),
                        "total_output_size_formatted": format_file_size(output_size),
                        "space_saved_formatted": format_file_size(space_saved),
                        "overall_compression_ratio": compression_ratio / 100,
                        "overall_space_saved_percentage": compression_ratio,
                    },
                }

            # 处理目录的情况
            if not input_path.is_dir():
                raise ProcessingError(f"输入路径既不是文件也不是目录: {input_path}")

            # 设置输出目录
            if output_dir is None:
                output_path = input_path / "compressed"
            else:
                output_path = validate_path(output_dir, must_exist=False)

            create_directory(output_path)

            self.logger.info(f"开始压缩图像: {input_path} -> {output_path}")
            self.logger.info(f"压缩质量: {quality}")
            if max_size:
                self.logger.info(f"最大尺寸限制: {max_size}")

            # 获取图像文件列表
            image_files = get_file_list(input_path, self.supported_formats, recursive)

            result: Dict[str, Any] = {
                "success": True,
                "input_dir": str(input_path),
                "output_dir": str(output_path),
                "quality": quality,
                "target_format": target_format,
                "max_size": max_size,
                "compressed_files": [],
                "failed_files": [],
                "statistics": {
                    "total_files": len(image_files),
                    "compressed_count": 0,
                    "failed_count": 0,
                    "total_input_size": 0,
                    "total_output_size": 0,
                    "space_saved": 0,
                },
            }

            # 压缩图像
            def compress_single_image(img_file: Path) -> Dict[str, Any]:
                try:
                    # 计算输入文件大小
                    input_size = img_file.stat().st_size

                    # 确定输出格式
                    output_format = target_format or img_file.suffix.lstrip(".").lower()
                    if output_format not in ["jpg", "jpeg", "png", "webp"]:
                        output_format = "jpg"  # 默认转为jpg以获得更好的压缩

                    # 生成输出文件路径
                    if recursive:
                        # 保持目录结构
                        rel_path = img_file.relative_to(input_path)
                        output_file = output_path / rel_path.with_suffix(
                            f".{output_format}"
                        )
                        create_directory(output_file.parent)
                    else:
                        output_file = output_path / f"{img_file.stem}.{output_format}"

                    # 确保文件名唯一
                    output_file = get_unique_filename(
                        output_file.parent, output_file.name
                    )

                    # 压缩图像
                    self._compress_single_image(
                        img_file, output_file, quality, output_format, max_size
                    )

                    # 计算输出文件大小
                    output_size = output_file.stat().st_size
                    space_saved = input_size - output_size

                    return {
                        "success": True,
                        "input_file": str(img_file),
                        "output_file": str(output_file),
                        "input_size": input_size,
                        "output_size": output_size,
                        "space_saved": space_saved,
                        "compression_ratio": (
                            output_size / input_size if input_size > 0 else 1.0
                        ),
                        "space_saved_percentage": (
                            (space_saved / input_size * 100) if input_size > 0 else 0
                        ),
                    }

                except Exception as e:
                    return {
                        "success": False,
                        "input_file": str(img_file),
                        "error": str(e),
                    }

            # 并发批量处理 - 使用线程池提升性能
            import gc

            from ...core.progress import progress_context

            compression_results = []

            self.logger.info(f"使用顺序处理模式处理 {len(image_files)} 个图像文件")

            # 显示总体进度
            with progress_context(
                len(image_files), "图像压缩总进度", True, leave=True, position=0
            ) as overall_progress:

                # 顺序处理
                for img_file in image_files:
                    try:
                        single_result = compress_single_image(img_file)
                        compression_results.append(single_result)
                    except Exception as e:
                        self.logger.error(f"处理文件 {img_file} 时出错: {str(e)}")
                        compression_results.append(
                            {
                                "success": False,
                                "input_file": str(img_file),
                                "error": str(e),
                            }
                        )

                    # 更新总体进度
                    overall_progress.update_progress(1)

                    # 每处理完10个文件进行一次垃圾回收
                    if len(compression_results) % 10 == 0:
                        gc.collect()

                self.logger.info(
                    f"顺序处理完成，共处理 {len(compression_results)} 个文件"
                )

                # 最终垃圾回收
                gc.collect()

            # 统计结果
            for comp_result in compression_results:
                if comp_result and comp_result["success"]:
                    result["compressed_files"].append(comp_result)
                    result["statistics"]["compressed_count"] += 1
                    # 只有成功的结果才有这些字段
                    if "input_size" in comp_result:
                        result["statistics"]["total_input_size"] += comp_result[
                            "input_size"
                        ]
                    if "output_size" in comp_result:
                        result["statistics"]["total_output_size"] += comp_result[
                            "output_size"
                        ]
                    if "space_saved" in comp_result:
                        result["statistics"]["space_saved"] += comp_result[
                            "space_saved"
                        ]
                elif comp_result:
                    result["failed_files"].append(comp_result)
                    result["statistics"]["failed_count"] += 1
                    result["success"] = False
                    # 记录失败文件的错误信息
                    if "error" in comp_result:
                        self.logger.error(
                            f"文件 {comp_result['input_file']} 压缩失败: {comp_result['error']}"
                        )

            # 添加格式化的大小信息
            result["statistics"]["total_input_size_formatted"] = format_file_size(
                result["statistics"]["total_input_size"]
            )
            result["statistics"]["total_output_size_formatted"] = format_file_size(
                result["statistics"]["total_output_size"]
            )
            result["statistics"]["space_saved_formatted"] = format_file_size(
                result["statistics"]["space_saved"]
            )

            if result["statistics"]["total_input_size"] > 0:
                result["statistics"]["overall_compression_ratio"] = (
                    result["statistics"]["total_output_size"]
                    / result["statistics"]["total_input_size"]
                )
                result["statistics"]["overall_space_saved_percentage"] = (
                    result["statistics"]["space_saved"]
                    / result["statistics"]["total_input_size"]
                    * 100
                )
            else:
                result["statistics"]["overall_compression_ratio"] = 1.0
                result["statistics"]["overall_space_saved_percentage"] = 0.0

            self.logger.info(f"图像压缩完成: {result['statistics']}")
            return result

        except Exception as e:
            error_msg = f"图像压缩失败: {str(e)}"
            self.logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "input_dir": str(input_path) if "input_path" in locals() else input_dir,
                "output_dir": (
                    str(output_path) if "output_path" in locals() else output_dir
                ),
                "quality": quality,
                "target_format": target_format,
                "max_size": max_size,
                "compressed_files": [],
                "failed_files": [],
                "statistics": {
                    "total_files": 0,
                    "compressed_count": 0,
                    "failed_count": 0,
                    "total_input_size": 0,
                    "total_output_size": 0,
                    "space_saved": 0,
                },
            }

    def compress_images_multiprocess_batch(
        self,
        input_dir: str,
        output_dir: Optional[str] = None,
        quality: int = 85,
        target_format: Optional[str] = None,
        recursive: bool = False,
        max_size: Optional[Tuple[int, int]] = None,
        batch_count: int = 100,
        max_processes: Optional[int] = None,
    ) -> Dict[str, Any]:
        """使用多进程分批处理压缩图像

        Args:
            input_dir: 输入路径（文件或目录）
            output_dir: 输出目录（可选，默认为输入目录下的compressed子目录）
            quality: 压缩质量 (1-100，默认85)
            target_format: 目标格式（可选，默认保持原格式）
            recursive: 是否递归处理
            max_size: 最大尺寸限制 (width, height)，超过此尺寸的图像会被缩小
            batch_count: 批次数量（默认100）
            max_processes: 最大进程数（默认为CPU核心数）

        Returns:
            Dict[str, Any]: 压缩结果
        """
        # 参数验证
        input_path = validate_path(input_dir, must_exist=True)

        # 处理单个文件的情况
        if input_path.is_file():
            return self.compress_images(
                input_dir, output_dir, quality, target_format, recursive, max_size
            )

        # 设置输出目录
        if output_dir is None:
            output_path = input_path / "compressed"
        else:
            output_path = validate_path(output_dir, must_exist=False)

        create_directory(output_path)

        self.logger.info(f"开始多进程分批压缩图像: {input_path} -> {output_path}")
        self.logger.info(f"压缩质量: {quality}")
        self.logger.info(f"批次数量: {batch_count}")
        if max_size:
            self.logger.info(f"最大尺寸限制: {max_size}")

        # 获取图像文件列表
        image_files = get_file_list(input_path, self.supported_formats, recursive)

        if not image_files:
            self.logger.warning("未找到任何图像文件")
            return {
                "success": True,
                "input_dir": str(input_path),
                "output_dir": str(output_path),
                "quality": quality,
                "target_format": target_format,
                "max_size": max_size,
                "compressed_files": [],
                "failed_files": [],
                "statistics": {
                    "total_files": 0,
                    "compressed_count": 0,
                    "failed_count": 0,
                    "total_input_size": 0,
                    "total_output_size": 0,
                    "space_saved": 0,
                },
            }

        # 计算批次大小
        total_files = len(image_files)
        batch_size = max(1, math.ceil(total_files / batch_count))
        actual_batch_count = math.ceil(total_files / batch_size)

        self.logger.info(f"总文件数: {total_files}")
        self.logger.info(f"批次大小: {batch_size}")
        self.logger.info(f"实际批次数: {actual_batch_count}")

        # 设置进程数
        if max_processes is None:
            max_processes = min(multiprocessing.cpu_count(), actual_batch_count)
        else:
            max_processes = min(max_processes, actual_batch_count)

        self.logger.info(f"使用 {max_processes} 个进程处理 {actual_batch_count} 个批次")
        self.logger.info("=" * 60)
        self.logger.info("开始多进程图像压缩处理，请稍候...")
        self.logger.info("注意：处理过程中可能看起来程序无响应，这是正常现象")
        self.logger.info("=" * 60)

        # 分批处理
        batches = []
        for i in range(0, total_files, batch_size):
            batch = image_files[i : i + batch_size]
            batches.append(batch)

        # 初始化结果
        result: Dict[str, Any] = {
            "success": True,
            "input_dir": str(input_path),
            "output_dir": str(output_path),
            "quality": quality,
            "target_format": target_format,
            "max_size": max_size,
            "compressed_files": [],
            "failed_files": [],
            "statistics": {
                "total_files": total_files,
                "compressed_count": 0,
                "failed_count": 0,
                "total_input_size": 0,
                "total_output_size": 0,
                "space_saved": 0,
            },
        }

        # 使用进程池处理批次
        self.logger.info("正在压缩图像...")

        # 初始化进度跟踪变量
        completed_batches = 0
        processed_files = 0

        # 创建进度队列用于子进程通信
        import multiprocessing as mp

        manager = mp.Manager()
        progress_queue = manager.Queue()

        # 创建进度条
        if TQDM_AVAILABLE:
            progress_bar = tqdm(
                total=total_files,
                desc="压缩图像",
                unit="文件",
                ncols=80,
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
            )
        else:
            progress_bar = None
            self.logger.info(f"开始处理 {total_files} 个文件...")

        with ProcessPoolExecutor(max_workers=max_processes) as executor:
            # 提交所有批次任务
            future_to_batch = {
                executor.submit(
                    _process_batch_worker,
                    batch,
                    str(input_path),
                    str(output_path),
                    quality,
                    target_format,
                    max_size,
                    recursive,
                    progress_queue,
                ): i
                for i, batch in enumerate(batches)
            }

            if not TQDM_AVAILABLE:
                self.logger.info(f"已提交 {len(future_to_batch)} 个批次任务到进程池")

            # 启动进度监听线程
            import threading

            progress_thread_running = True

            def progress_listener():
                nonlocal processed_files
                while progress_thread_running:
                    try:
                        # 从队列中获取进度更新（非阻塞）
                        progress_update = progress_queue.get(timeout=0.1)
                        processed_files += progress_update

                        # 更新进度条
                        if progress_bar:
                            progress_bar.update(progress_update)

                    except Exception:
                        # 队列为空或超时，继续循环
                        continue

            # 启动进度监听线程
            progress_thread = threading.Thread(target=progress_listener, daemon=True)
            progress_thread.start()

            # 处理完成的批次
            for future in as_completed(future_to_batch):
                batch_index = future_to_batch[future]
                try:
                    batch_result = future.result()

                    # 合并批次结果
                    result["compressed_files"].extend(batch_result["compressed_files"])
                    result["failed_files"].extend(batch_result["failed_files"])

                    # 更新统计信息
                    stats = result["statistics"]
                    batch_stats = batch_result["statistics"]
                    stats["compressed_count"] += batch_stats["compressed_count"]
                    stats["failed_count"] += batch_stats["failed_count"]
                    stats["total_input_size"] += batch_stats["total_input_size"]
                    stats["total_output_size"] += batch_stats["total_output_size"]
                    stats["space_saved"] += batch_stats["space_saved"]

                    # 更新批次计数
                    completed_batches += 1

                    # 更新进度条描述，显示成功/失败统计
                    if progress_bar:
                        success_count = stats["compressed_count"]
                        failed_count = stats["failed_count"]
                        progress_bar.set_postfix(
                            {
                                "成功": success_count,
                                "失败": failed_count,
                                "批次": f"{completed_batches}/{actual_batch_count}",
                            }
                        )
                    else:
                        # 如果没有 tqdm，显示简化的进度信息
                        progress_percent = (processed_files / total_files) * 100
                        self.logger.info(
                            f"进度: {processed_files}/{total_files} ({progress_percent:.1f}%) - "
                            f"成功: {stats['compressed_count']}, 失败: {stats['failed_count']}"
                        )

                except Exception as e:
                    self.logger.error(f"批次 {batch_index + 1} 处理失败: {str(e)}")
                    # 将批次中的所有文件标记为失败
                    batch = batches[batch_index]
                    batch_size_actual = len(batch)
                    for img_file in batch:
                        result["failed_files"].append(
                            {
                                "success": False,
                                "input_file": str(img_file),
                                "error": f"批次处理失败: {str(e)}",
                            }
                        )

                    # 更新批次计数和失败统计
                    completed_batches += 1
                    result["statistics"]["failed_count"] += batch_size_actual

                    # 手动更新进度条（因为失败的批次不会通过队列报告进度）
                    if progress_bar:
                        progress_bar.update(batch_size_actual)
                        progress_bar.set_postfix(
                            {
                                "成功": result["statistics"]["compressed_count"],
                                "失败": result["statistics"]["failed_count"],
                                "批次": f"{completed_batches}/{actual_batch_count}",
                            }
                        )

        # 停止进度监听线程
        progress_thread_running = False
        if "progress_thread" in locals():
            progress_thread.join(timeout=1.0)  # 等待线程结束，最多1秒

        # 处理队列中剩余的进度更新
        try:
            while not progress_queue.empty():
                progress_update = progress_queue.get_nowait()
                if progress_bar:
                    progress_bar.update(progress_update)
        except Exception:
            pass

        # 关闭进度条
        if progress_bar:
            progress_bar.close()

        # 添加格式化的大小信息
        stats = result["statistics"]
        stats["total_input_size_formatted"] = format_file_size(
            stats["total_input_size"]
        )
        stats["total_output_size_formatted"] = format_file_size(
            stats["total_output_size"]
        )
        stats["space_saved_formatted"] = format_file_size(stats["space_saved"])

        if stats["total_input_size"] > 0:
            stats["overall_compression_ratio"] = (
                stats["total_output_size"] / stats["total_input_size"]
            )
            stats["overall_space_saved_percentage"] = (
                stats["space_saved"] / stats["total_input_size"]
            ) * 100
        else:
            stats["overall_compression_ratio"] = 1.0
            stats["overall_space_saved_percentage"] = 0.0

        # 显示最终完成信息
        self.logger.info("=" * 60)
        self.logger.info("图像压缩处理完成！")
        self.logger.info(f"总文件数: {stats['total_files']}")
        self.logger.info(f"成功压缩: {stats['compressed_count']} 个文件")
        self.logger.info(f"处理失败: {stats['failed_count']} 个文件")
        self.logger.info(
            f"空间节省: {stats['space_saved_formatted']} ({stats['overall_space_saved_percentage']:.1f}%)"
        )
        self.logger.info(f"输出目录: {output_path}")
        self.logger.info("=" * 60)

        return result

    def _compress_single_image(
        self,
        input_file: Path,
        output_file: Path,
        quality: int,
        target_format: str,
        max_size: Optional[Tuple[int, int]] = None,
    ) -> None:
        """压缩单个图像"""
        try:
            if PIL_AVAILABLE:
                self._compress_with_pil(
                    input_file, output_file, quality, target_format, max_size
                )
            elif CV2_AVAILABLE:
                self._compress_with_cv2(
                    input_file, output_file, quality, target_format, max_size
                )
            else:
                raise ProcessingError("没有可用的图像处理库")
        finally:
            # 确保每张图片处理完后进行内存清理
            import gc

            gc.collect()

    def _compress_with_pil(
        self,
        input_file: Path,
        output_file: Path,
        quality: int,
        target_format: str,
        max_size: Optional[Tuple[int, int]] = None,
    ) -> None:
        """使用PIL压缩图像"""
        original_img = None
        processed_img = None

        try:
            # 打开图像
            original_img = Image.open(input_file)

            # 转换为RGB模式（如果需要）
            if target_format.lower() in ["jpg", "jpeg"] and original_img.mode in [
                "RGBA",
                "LA",
            ]:
                # 创建白色背景
                background = Image.new("RGB", original_img.size, (255, 255, 255))
                if original_img.mode == "RGBA":
                    background.paste(
                        original_img, mask=original_img.split()[-1]
                    )  # 使用alpha通道作为mask
                else:
                    background.paste(original_img)
                processed_img = background
            else:
                # 如果不需要格式转换，直接使用原图像
                processed_img = original_img

            # 调整尺寸（如果指定了最大尺寸）
            if max_size:
                # 使用thumbnail方法就地修改，减少内存使用
                processed_img.thumbnail(max_size, Image.Resampling.LANCZOS)

            # 设置保存参数
            save_kwargs = {}
            if target_format.lower() in ["jpg", "jpeg"]:
                save_kwargs["quality"] = quality
                save_kwargs["optimize"] = True
                save_kwargs["progressive"] = True
            elif target_format.lower() == "png":
                save_kwargs["optimize"] = True
                # PNG压缩级别基于质量计算
                save_kwargs["compress_level"] = max(
                    1, min(9, int((100 - quality) / 10))
                )
            elif target_format.lower() == "webp":
                save_kwargs["quality"] = quality
                save_kwargs["method"] = 6
                save_kwargs["optimize"] = True

            # 保存图像 - 修复格式名称
            pil_format = target_format.upper()
            if pil_format == "JPG":
                pil_format = "JPEG"  # PIL使用JPEG而不是JPG
            processed_img.save(output_file, format=pil_format, **save_kwargs)

        except Exception as e:
            raise FileProcessingError(
                f"PIL压缩图像失败: {str(e)}",
                file_path=str(input_file),
                operation="compress",
            )
        finally:
            # 确保图像对象被正确关闭和释放
            if processed_img and processed_img != original_img:
                try:
                    processed_img.close()
                except Exception:
                    pass
            if original_img:
                try:
                    original_img.close()
                except Exception:
                    pass

    def _compress_with_cv2(
        self,
        input_file: Path,
        output_file: Path,
        quality: int,
        target_format: str,
        max_size: Optional[Tuple[int, int]] = None,
    ) -> None:
        """使用OpenCV压缩图像"""
        img = None
        try:
            # 读取图像
            img = cv2_imread_unicode(input_file)
            if img is None:
                raise FileProcessingError(f"无法读取图像: {input_file}")

            # 调整尺寸（如果指定了最大尺寸）
            if max_size:
                h, w = img.shape[:2]
                max_w, max_h = max_size

                if w > max_w or h > max_h:
                    # 计算缩放比例
                    scale = min(max_w / w, max_h / h)
                    new_w = int(w * scale)
                    new_h = int(h * scale)
                    # 就地调整尺寸，减少内存使用
                    resized_img = cv2.resize(
                        img, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4
                    )
                    # 立即释放原图像内存
                    del img
                    img = resized_img

            # 设置保存参数
            save_params = []
            if target_format.lower() in ["jpg", "jpeg"]:
                save_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
            elif target_format.lower() == "png":
                # PNG压缩级别 (0-9)
                compression_level = max(1, min(9, int((100 - quality) / 10)))
                save_params = [cv2.IMWRITE_PNG_COMPRESSION, compression_level]
            elif target_format.lower() == "webp":
                save_params = [cv2.IMWRITE_WEBP_QUALITY, quality]

            # 立即保存图像
            success = cv2_imwrite_unicode(output_file, img, save_params)
            if not success:
                raise FileProcessingError(f"保存图像失败: {output_file}")

            # 立即释放图像内存
            del img
            img = None

        except Exception as e:
            # 确保在异常情况下也释放内存
            if img is not None:
                del img
            raise FileProcessingError(
                f"OpenCV压缩图像失败: {str(e)}",
                file_path=str(input_file),
                operation="compress",
            )

    def get_image_info(
        self, image_file: str, recursive: bool = False
    ) -> Dict[str, Any]:
        """获取图像信息

        Args:
            image_file: 图像文件或目录路径
            recursive: 是否递归处理子目录（仅当输入为目录时有效）

        Returns:
            Dict[str, Any]: 图像信息
        """
        try:
            img_path = validate_path(image_file, must_exist=True)

            # 处理单个文件的情况
            if img_path.is_file():
                info = {
                    "success": True,
                    "file_path": str(img_path),
                    "file_size": img_path.stat().st_size,
                    "file_size_formatted": format_file_size(img_path.stat().st_size),
                    "format": img_path.suffix.lower(),
                }

                # 获取图像尺寸
                try:
                    width, height = self._get_image_size(img_path)
                    info.update(
                        {
                            "width": width,
                            "height": height,
                            "aspect_ratio": width / height if height > 0 else 0,
                            "total_pixels": width * height,
                        }
                    )
                except Exception as e:
                    self.logger.warning(f"获取图像尺寸失败: {str(e)}")
                    info.update(
                        {"width": 0, "height": 0, "aspect_ratio": 0, "total_pixels": 0}
                    )

                # 使用PIL获取更多信息
                if PIL_AVAILABLE:
                    try:
                        with Image.open(img_path) as img:
                            info.update(
                                {
                                    "mode": img.mode,
                                    "has_transparency": img.mode in ["RGBA", "LA"]
                                    or "transparency" in img.info,
                                }
                            )
                    except Exception:
                        pass

                return info

            # 处理目录的情况
            if not img_path.is_dir():
                raise ProcessingError(f"输入路径既不是文件也不是目录: {img_path}")

            self.logger.info(f"开始获取目录中图像信息: {img_path}")

            # 获取图像文件列表
            image_files = get_file_list(img_path, self.supported_formats, recursive)

            result: Dict[str, Any] = {
                "success": True,
                "input_dir": str(img_path),
                "recursive": recursive,
                "image_info_list": [],
                "failed_files": [],
                "statistics": {
                    "total_files": len(image_files),
                    "processed_count": 0,
                    "failed_count": 0,
                    "total_size": 0,
                    "total_pixels": 0,
                },
            }

            # 获取每个图像的信息
            def get_single_info(img_file: Path) -> Dict[str, Any]:
                try:
                    # 递归调用获取单个文件信息
                    single_info = self.get_image_info(str(img_file))
                    return single_info
                except Exception as e:
                    self.logger.error(f"获取文件 {img_file} 信息失败: {str(e)}")
                    return {
                        "success": False,
                        "file_path": str(img_file),
                        "error": str(e),
                    }

            # 批量处理
            info_results = process_with_progress(
                image_files, get_single_info, "获取图像信息"
            )

            # 统计结果
            for info_result in info_results:
                if info_result and info_result["success"]:
                    result["image_info_list"].append(info_result)
                    result["statistics"]["processed_count"] += 1
                    if "file_size" in info_result:
                        result["statistics"]["total_size"] += info_result["file_size"]
                    if "total_pixels" in info_result:
                        result["statistics"]["total_pixels"] += info_result[
                            "total_pixels"
                        ]
                elif info_result:
                    result["failed_files"].append(info_result)
                    result["statistics"]["failed_count"] += 1
                    result["success"] = False

            # 添加汇总信息
            if result["statistics"]["processed_count"] > 0:
                result["statistics"]["average_file_size"] = (
                    result["statistics"]["total_size"]
                    / result["statistics"]["processed_count"]
                )
                result["statistics"]["total_size_formatted"] = format_file_size(
                    result["statistics"]["total_size"]
                )

            self.logger.info(f"图像信息获取完成: {result['statistics']}")
            return result

        except Exception as e:
            raise ProcessingError(f"获取图像信息失败: {str(e)}")


def _process_batch_worker(
    batch_files: List[Path],
    input_dir: str,
    output_dir: str,
    quality: int,
    target_format: Optional[str],
    max_size: Optional[Tuple[int, int]],
    recursive: bool,
    progress_queue=None,
) -> Dict[str, Any]:
    """批次处理工作函数，在独立进程中运行

    Args:
        batch_files: 当前批次要处理的文件列表
        input_dir: 输入目录
        output_dir: 输出目录
        quality: 压缩质量
        target_format: 目标格式
        max_size: 最大尺寸限制
        recursive: 是否递归处理

    Returns:
        Dict[str, Any]: 批次处理结果
    """
    import gc
    from pathlib import Path

    # 重新导入必要的模块（因为在新进程中）
    try:
        from PIL import Image

        PIL_AVAILABLE = True
    except ImportError:
        PIL_AVAILABLE = False

    try:
        import cv2

        CV2_AVAILABLE = True
    except ImportError:
        CV2_AVAILABLE = False

    # 在多进程环境中使用绝对导入
    try:
        from integrated_script.core.utils import create_directory, get_unique_filename
    except ImportError:
        # 如果绝对导入失败，尝试相对导入
        from ...core.utils import create_directory, get_unique_filename

    input_path = Path(input_dir)
    output_path = Path(output_dir)

    # 初始化批次结果
    batch_result: Dict[str, Any] = {
        "compressed_files": [],
        "failed_files": [],
        "statistics": {
            "compressed_count": 0,
            "failed_count": 0,
            "total_input_size": 0,
            "total_output_size": 0,
            "space_saved": 0,
        },
    }

    def compress_single_image_worker(img_file: Path) -> Dict[str, Any]:
        """压缩单个图像的工作函数"""
        try:
            # 计算输入文件大小
            input_size = img_file.stat().st_size

            # 确定输出格式
            output_format = target_format or img_file.suffix.lstrip(".").lower()
            if output_format not in ["jpg", "jpeg", "png", "webp"]:
                output_format = "jpg"  # 默认转为jpg以获得更好的压缩

            # 生成输出文件路径
            if recursive:
                # 保持目录结构
                rel_path = img_file.relative_to(input_path)
                output_file = output_path / rel_path.with_suffix(f".{output_format}")
                create_directory(output_file.parent)
            else:
                output_file = output_path / f"{img_file.stem}.{output_format}"

            # 确保文件名唯一
            output_file = get_unique_filename(output_file.parent, output_file.name)

            # 压缩图像 - 直接在这里实现压缩逻辑
            try:
                if PIL_AVAILABLE:
                    # 使用PIL压缩
                    original_img = None
                    processed_img = None

                    try:
                        # 打开图像
                        original_img = Image.open(img_file)

                        # 转换为RGB模式（如果需要）
                        if output_format.lower() in [
                            "jpg",
                            "jpeg",
                        ] and original_img.mode in ["RGBA", "LA"]:
                            # 创建白色背景
                            background = Image.new(
                                "RGB", original_img.size, (255, 255, 255)
                            )
                            if original_img.mode == "RGBA":
                                background.paste(
                                    original_img, mask=original_img.split()[-1]
                                )
                            else:
                                background.paste(original_img)
                            processed_img = background
                        else:
                            processed_img = original_img.copy()

                        # 调整尺寸（如果需要）
                        if max_size:
                            processed_img.thumbnail(max_size, Image.Resampling.LANCZOS)

                        # 保存图像
                        save_kwargs = {}
                        if output_format.lower() in ["jpg", "jpeg"]:
                            save_kwargs["quality"] = quality
                            save_kwargs["optimize"] = True
                        elif output_format.lower() == "png":
                            save_kwargs["optimize"] = True
                        elif output_format.lower() == "webp":
                            save_kwargs["quality"] = quality
                            save_kwargs["method"] = 6

                        # 映射格式名称以符合PIL的要求
                        pil_format = output_format.upper()
                        if pil_format == "JPG":
                            pil_format = "JPEG"

                        processed_img.save(
                            output_file, format=pil_format, **save_kwargs
                        )

                    finally:
                        # 清理内存
                        if original_img:
                            original_img.close()
                        if processed_img and processed_img != original_img:
                            processed_img.close()
                        gc.collect()

                elif CV2_AVAILABLE:
                    # 使用OpenCV压缩
                    img = None

                    try:
                        # 读取图像
                        img = cv2_imread_unicode(img_file, cv2.IMREAD_COLOR)
                        if img is None:
                            raise Exception(f"无法读取图像: {img_file}")

                        # 调整尺寸（如果需要）
                        if max_size:
                            height, width = img.shape[:2]
                            max_width, max_height = max_size

                            # 计算缩放比例
                            scale = min(max_width / width, max_height / height)
                            if scale < 1:
                                new_width = int(width * scale)
                                new_height = int(height * scale)
                                img = cv2.resize(
                                    img,
                                    (new_width, new_height),
                                    interpolation=cv2.INTER_LANCZOS4,
                                )

                        # 设置压缩参数
                        if output_format.lower() in ["jpg", "jpeg"]:
                            encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
                        elif output_format.lower() == "png":
                            # PNG压缩级别 (0-9)
                            compression_level = int((100 - quality) / 100 * 9)
                            encode_params = [
                                cv2.IMWRITE_PNG_COMPRESSION,
                                compression_level,
                            ]
                        elif output_format.lower() == "webp":
                            encode_params = [cv2.IMWRITE_WEBP_QUALITY, quality]
                        else:
                            encode_params = []

                        # 保存图像
                        success = cv2_imwrite_unicode(output_file, img, encode_params)
                        if not success:
                            raise Exception(f"保存图像失败: {output_file}")

                    finally:
                        # 清理内存
                        if img is not None:
                            del img
                        gc.collect()

                else:
                    raise Exception("没有可用的图像处理库")

            finally:
                # 确保每张图片处理完后进行内存清理
                gc.collect()

            # 计算输出文件大小
            output_size = output_file.stat().st_size
            space_saved = input_size - output_size

            return {
                "success": True,
                "input_file": str(img_file),
                "output_file": str(output_file),
                "input_size": input_size,
                "output_size": output_size,
                "space_saved": space_saved,
                "compression_ratio": (
                    output_size / input_size if input_size > 0 else 1.0
                ),
                "space_saved_percentage": (
                    (space_saved / input_size * 100) if input_size > 0 else 0
                ),
            }

        except Exception as e:
            return {
                "success": False,
                "input_file": str(img_file),
                "error": str(e),
            }

    # 处理批次中的所有文件
    processed_count = 0

    for img_file in batch_files:
        try:
            single_result = compress_single_image_worker(img_file)
            processed_count += 1

            if single_result["success"]:
                batch_result["compressed_files"].append(single_result)
                batch_result["statistics"]["compressed_count"] += 1
                batch_result["statistics"]["total_input_size"] += single_result[
                    "input_size"
                ]
                batch_result["statistics"]["total_output_size"] += single_result[
                    "output_size"
                ]
                batch_result["statistics"]["space_saved"] += single_result[
                    "space_saved"
                ]
            else:
                batch_result["failed_files"].append(single_result)
                batch_result["statistics"]["failed_count"] += 1

        except Exception as e:
            # 处理意外错误
            processed_count += 1
            error_msg = str(e)
            batch_result["failed_files"].append(
                {
                    "success": False,
                    "input_file": str(img_file),
                    "error": error_msg,
                }
            )
            batch_result["statistics"]["failed_count"] += 1

        # 向主进程报告进度
        if progress_queue is not None:
            try:
                progress_queue.put(1)  # 报告处理了1个文件
            except Exception:
                pass  # 忽略队列错误

        # 定期进行垃圾回收
        if processed_count % 10 == 0:
            gc.collect()

    # 最终垃圾回收
    gc.collect()

    return batch_result
