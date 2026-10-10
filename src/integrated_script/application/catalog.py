#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""操作目录：与既有菜单逐项对应的完整操作清单。

目录顺序与旧交互菜单一致，保证所有既有开放功能都能在 GUI/TUI 中访问。
默认值与旧交互保持一致；破坏性操作标记 ``destructive=True``，确认逻辑
统一由应用层处理器通过 ``TaskContext.confirm`` 完成。
"""

from __future__ import annotations

import sys
from typing import List, Tuple

from .contracts import OperationSpec, ParameterSpec
from .handlers import config as config_handlers
from .handlers import env as env_handlers
from .handlers import file as file_handlers
from .handlers import image as image_handlers
from .handlers import label as label_handlers
from .handlers import yolo as yolo_handlers
from .operations import Operation

# ---------------------------------------------------------------------------
# 复用的字段定义
# ---------------------------------------------------------------------------

_DATASET_PATH = ParameterSpec(
    name="dataset_path",
    label="数据集路径",
    kind="path",
    required=True,
    help="CTDS / YOLO / X-label 数据集目录",
)

_OUTPUT_NAME = ParameterSpec(
    name="output_name",
    label="项目名称",
    kind="str",
    default="",
    help="留空自动生成",
)

_DATASET_TYPE = ParameterSpec(
    name="dataset_type",
    label="数据集类型",
    kind="choice",
    default="auto",
    choices=(
        ("自动识别", "auto"),
        ("目标检测数据集", "detection"),
        ("目标分割数据集", "segmentation"),
    ),
)

_OUTPUT_PATH = ParameterSpec(
    name="output_path",
    label="输出路径",
    kind="path",
    default="",
    help="留空使用默认输出",
)


def _op(
    operation_id: str,
    category: str,
    label: str,
    description: str,
    handler,
    fields: Tuple[ParameterSpec, ...] = (),
    *,
    destructive: bool = False,
) -> Operation:
    spec = OperationSpec(
        id=operation_id,
        category=category,
        label=label,
        description=description,
        fields=fields,
        destructive=destructive,
    )
    return Operation(spec=spec, handler=handler, fields=fields)


def _yolo_operations() -> List[Operation]:
    category = yolo_handlers.CATEGORY
    return [
        _op(
            "yolo.ctds_to_yolo",
            category,
            "CTDS数据转YOLO格式",
            "处理 CTDS 标注，剔除空标签/非法标注并按确认的类型生成 YOLO 数据集。",
            yolo_handlers.handle_process_ctds_dataset,
            (
                _DATASET_PATH,
                _OUTPUT_NAME,
                ParameterSpec(
                    name="keep_empty_labels",
                    label="保留空标签文件",
                    kind="bool",
                    default=False,
                ),
            ),
        ),
        _op(
            "yolo.yolo_to_ctds",
            category,
            "YOLO数据转CTDS格式",
            "把 YOLO 数据集重新封装为 CTDS 结构（obj.names + obj_train_data）。",
            yolo_handlers.handle_convert_yolo_to_ctds,
            (_DATASET_PATH, _OUTPUT_PATH),
        ),
        _op(
            "yolo.yolo_to_xlabel",
            category,
            "YOLO数据转X-label",
            "把 YOLO 数据集转换为 X-label/Labelme JSON，可自动或手动指定类型。",
            yolo_handlers.handle_yolo_to_xlabel,
            (_DATASET_PATH, _OUTPUT_PATH, _DATASET_TYPE),
        ),
        _op(
            "yolo.xlabel_to_yolo",
            category,
            "X-label数据转YOLO",
            "把 Labelme/X-label JSON 转换为 YOLO 数据集，可确认或调整类别顺序。",
            yolo_handlers.handle_xlabel_to_yolo,
            (
                _DATASET_PATH,
                _OUTPUT_PATH,
                _DATASET_TYPE,
                ParameterSpec(
                    name="edit_class_order",
                    label="调整类别顺序",
                    kind="bool",
                    default=False,
                    help="勾选后处理前会请求输入新的类别编号顺序",
                ),
                ParameterSpec(
                    name="class_order",
                    label="类别顺序",
                    kind="str",
                    default="",
                    help="可选，空格分隔的编号，如 2 1 0",
                ),
            ),
        ),
        _op(
            "yolo.validate_detection",
            category,
            "目标检测数据集验证",
            "校验 images 与 labels 是否一一匹配，可选择发现问题时清理。",
            yolo_handlers.handle_validate_detection_dataset,
            (
                _DATASET_PATH,
                ParameterSpec(
                    name="auto_clean",
                    label="发现问题时清理",
                    kind="bool",
                    default=True,
                ),
            ),
        ),
        _op(
            "yolo.validate_segmentation",
            category,
            "目标分割数据集验证",
            "校验分割标签格式与文件配对，可选择移动无效标签并清理。",
            yolo_handlers.handle_validate_segmentation_dataset,
            (
                _DATASET_PATH,
                ParameterSpec(
                    name="move_invalid",
                    label="移动无效标签到上级目录",
                    kind="bool",
                    default=True,
                ),
                ParameterSpec(
                    name="auto_clean",
                    label="发现问题时清理",
                    kind="bool",
                    default=True,
                ),
            ),
        ),
        _op(
            "yolo.clean_unmatched",
            category,
            "清理不匹配文件",
            "删除 images/labels 中无配对或格式无效的文件。",
            yolo_handlers.handle_clean_unmatched,
            (
                _DATASET_PATH,
                ParameterSpec(
                    name="dry_run",
                    label="仅试运行不删除",
                    kind="bool",
                    default=False,
                ),
            ),
            destructive=True,
        ),
        _op(
            "yolo.merge_same",
            category,
            "合并多个数据集(相同类型)",
            "合并 classes.txt 一致的多个 YOLO 数据集并统一图片前缀。",
            yolo_handlers.handle_merge_datasets,
            (
                ParameterSpec(
                    name="dataset_paths",
                    label="数据集路径（每行一个）",
                    kind="paths",
                    required=True,
                ),
                ParameterSpec(
                    name="output_path",
                    label="输出路径",
                    kind="path",
                    default="",
                    help="留空使用当前目录",
                ),
                _OUTPUT_NAME,
                ParameterSpec(
                    name="image_prefix",
                    label="图片前缀",
                    kind="str",
                    default="",
                    help="留空自动生成",
                ),
            ),
        ),
        _op(
            "yolo.merge_different",
            category,
            "合并多个数据集(不同类型)",
            "合并类别不同的多个 YOLO 数据集，生成统一类别映射。",
            yolo_handlers.handle_merge_different_datasets,
            (
                ParameterSpec(
                    name="dataset_paths",
                    label="数据集路径（每行一个）",
                    kind="paths",
                    required=True,
                ),
                ParameterSpec(
                    name="output_path",
                    label="输出路径",
                    kind="path",
                    default="",
                    help="留空使用当前目录",
                ),
                _OUTPUT_NAME,
                ParameterSpec(
                    name="image_prefix",
                    label="图片前缀",
                    kind="str",
                    default="",
                ),
                ParameterSpec(
                    name="dataset_order",
                    label="处理顺序",
                    kind="str",
                    default="",
                    help="空格分隔的索引，如 1 0 2；留空使用默认顺序",
                ),
            ),
        ),
    ]


def _image_operations() -> List[Operation]:
    category = image_handlers.CATEGORY
    return [
        _op(
            "image.convert",
            category,
            "格式转换",
            "在 jpg/png/bmp/tiff/webp 之间转换图像格式。",
            image_handlers.handle_convert,
            (
                ParameterSpec(
                    name="input_path",
                    label="输入路径（文件或目录）",
                    kind="path",
                    required=True,
                ),
                _OUTPUT_PATH,
                ParameterSpec(
                    name="target_format",
                    label="目标格式",
                    kind="choice",
                    required=True,
                    default="jpg",
                    choices=(
                        ("JPG", "jpg"),
                        ("JPEG", "jpeg"),
                        ("PNG", "png"),
                        ("BMP", "bmp"),
                        ("TIFF", "tiff"),
                        ("WEBP", "webp"),
                    ),
                ),
                ParameterSpec(
                    name="quality",
                    label="JPEG 质量 (1-100)",
                    kind="int",
                    default=95,
                ),
                ParameterSpec(
                    name="recursive",
                    label="递归处理子目录",
                    kind="bool",
                    default=True,
                ),
            ),
        ),
        _op(
            "image.resize",
            category,
            "尺寸调整",
            "调整图像尺寸，支持 WxH 或单个数字。",
            image_handlers.handle_resize,
            (
                ParameterSpec(
                    name="input_path",
                    label="输入路径（文件或目录）",
                    kind="path",
                    required=True,
                ),
                _OUTPUT_PATH,
                ParameterSpec(
                    name="size",
                    label="目标尺寸",
                    kind="str",
                    required=True,
                    help="如 800x600 或 800",
                ),
                ParameterSpec(
                    name="keep_aspect",
                    label="保持宽高比",
                    kind="bool",
                    default=True,
                ),
                ParameterSpec(
                    name="recursive",
                    label="递归处理子目录",
                    kind="bool",
                    default=True,
                ),
            ),
        ),
        _op(
            "image.compress",
            category,
            "图像压缩",
            "多进程分批压缩图像，可限制最大尺寸并转换格式。",
            image_handlers.handle_compress,
            (
                ParameterSpec(
                    name="input_path",
                    label="输入路径（文件或目录）",
                    kind="path",
                    required=True,
                ),
                _OUTPUT_PATH,
                ParameterSpec(
                    name="quality",
                    label="压缩质量 (1-100)",
                    kind="int",
                    default=85,
                ),
                ParameterSpec(
                    name="target_format",
                    label="目标格式",
                    kind="choice",
                    default="original",
                    choices=(
                        ("保持原格式", "original"),
                        ("转换为 JPG", "jpg"),
                        ("转换为 PNG", "png"),
                        ("转换为 WebP", "webp"),
                    ),
                ),
                ParameterSpec(
                    name="max_size",
                    label="最大尺寸",
                    kind="str",
                    default="",
                    help="留空不限制；如 1920x1080",
                ),
                ParameterSpec(
                    name="recursive",
                    label="递归处理子目录",
                    kind="bool",
                    default=True,
                ),
                ParameterSpec(
                    name="max_processes",
                    label="最大进程数",
                    kind="int",
                    default=0,
                    help="0 表示自动",
                ),
            ),
        ),
        _op(
            "image.repair",
            category,
            "修复 OpenCV 读取错误的图像",
            "用 OpenCV 读取图像，失败的重新保存修复。",
            image_handlers.handle_repair,
            (
                ParameterSpec(
                    name="directory",
                    label="图像目录",
                    kind="path",
                    required=True,
                ),
                ParameterSpec(
                    name="recursive",
                    label="递归子目录",
                    kind="bool",
                    default=True,
                ),
            ),
        ),
        _op(
            "image.info",
            category,
            "获取图像信息",
            "统计单文件或目录中图像的尺寸、格式与大小。",
            image_handlers.handle_info,
            (
                ParameterSpec(
                    name="image_path",
                    label="图像路径（文件或目录）",
                    kind="path",
                    required=True,
                ),
                ParameterSpec(
                    name="recursive",
                    label="递归处理子目录",
                    kind="bool",
                    default=True,
                ),
            ),
        ),
    ]


def _file_operations() -> List[Operation]:
    category = file_handlers.CATEGORY
    source_path = ParameterSpec(
        name="source_path", label="源路径", kind="path", required=True
    )
    dest_path = ParameterSpec(
        name="dest_path",
        label="目标路径",
        kind="path",
        required=True,
        help="目标不存在时会被创建",
    )
    recursive = ParameterSpec(
        name="recursive", label="递归处理", kind="bool", default=False
    )
    rename_fields = (
        ParameterSpec(
            name="source_dir",
            label="源目录",
            kind="path",
            required=True,
        ),
        ParameterSpec(
            name="prefix",
            label="文件名前缀",
            kind="str",
            default="",
            help="留空表示无前缀",
        ),
    )
    return [
        _op(
            "file.rename_single_dir",
            category,
            "单目录重命名",
            "按前缀与数字位数重命名单个目录中的文件。",
            file_handlers.handle_rename_single_dir,
            rename_fields
            + (
                ParameterSpec(
                    name="digits",
                    label="数字位数",
                    kind="int",
                    default=5,
                ),
                ParameterSpec(
                    name="suffix",
                    label="文件后缀",
                    kind="str",
                    default="",
                    help="留空自动检测；检测不到时会请求输入",
                ),
                ParameterSpec(
                    name="shuffle_order",
                    label="打乱文件顺序",
                    kind="bool",
                    default=False,
                ),
            ),
            destructive=True,
        ),
        _op(
            "file.rename_images_labels",
            category,
            "数据集重命名",
            "同步重命名 images 与 labels 中的对应文件（补零）。",
            file_handlers.handle_rename_images_labels,
            rename_fields
            + (
                ParameterSpec(
                    name="digits",
                    label="数字位数",
                    kind="int",
                    default=5,
                ),
                ParameterSpec(
                    name="shuffle_order",
                    label="打乱文件顺序",
                    kind="bool",
                    default=False,
                ),
            ),
            destructive=True,
        ),
        _op(
            "file.rename_images_labels_legacy",
            category,
            "数据集重命名（传统模式）",
            "同步重命名 images 与 labels，序号不补零。",
            file_handlers.handle_rename_images_labels_legacy,
            rename_fields
            + (
                ParameterSpec(
                    name="shuffle_order",
                    label="打乱文件顺序",
                    kind="bool",
                    default=False,
                ),
            ),
            destructive=True,
        ),
        _op(
            "file.organize",
            category,
            "按扩展名组织文件",
            "按扩展名把文件移动或复制到分类子目录。",
            file_handlers.handle_organize,
            (
                ParameterSpec(
                    name="source_dir",
                    label="源目录",
                    kind="path",
                    required=True,
                ),
                ParameterSpec(
                    name="output_dir",
                    label="输出目录",
                    kind="path",
                    default="",
                    help="留空使用源目录",
                ),
                ParameterSpec(
                    name="copy_files",
                    label="复制而不是移动",
                    kind="bool",
                    default=False,
                ),
            ),
        ),
        _op(
            "file.delete_json",
            category,
            "递归删除JSON文件",
            "递归删除目标目录中的所有 JSON 文件。",
            file_handlers.handle_delete_json,
            (
                ParameterSpec(
                    name="target_dir",
                    label="目标目录",
                    kind="path",
                    required=True,
                ),
            ),
            destructive=True,
        ),
        _op(
            "file.copy",
            category,
            "批量复制文件",
            "批量复制文件或目录。",
            file_handlers.handle_copy,
            (source_path, dest_path, recursive),
        ),
        _op(
            "file.move",
            category,
            "批量移动文件",
            "批量移动文件或目录。",
            file_handlers.handle_move,
            (source_path, dest_path, recursive),
            destructive=True,
        ),
        _op(
            "file.move_images_by_count",
            category,
            "按数量移动图片",
            "按数量从源目录移动图片到目标目录。",
            file_handlers.handle_move_images_by_count,
            (
                ParameterSpec(
                    name="source_path",
                    label="源目录",
                    kind="path",
                    required=True,
                ),
                dest_path,
                ParameterSpec(
                    name="count",
                    label="移动数量",
                    kind="int",
                    required=True,
                    help="9999 表示移动全部",
                ),
                ParameterSpec(
                    name="overwrite",
                    label="覆盖同名文件",
                    kind="bool",
                    default=False,
                ),
            ),
            destructive=True,
        ),
    ]


def _label_operations() -> List[Operation]:
    category = label_handlers.CATEGORY
    images_subdir = ParameterSpec(
        name="images_subdir", label="图像子目录名", kind="str", default="images"
    )
    labels_subdir = ParameterSpec(
        name="labels_subdir", label="标签子目录名", kind="str", default="labels"
    )
    return [
        _op(
            "label.create_empty",
            category,
            "创建空标签文件",
            "为图像目录中的每张图片创建空标签文件。",
            label_handlers.handle_create_empty,
            (
                ParameterSpec(
                    name="images_dir",
                    label="图像目录",
                    kind="path",
                    required=True,
                ),
                ParameterSpec(
                    name="labels_dir",
                    label="标签目录",
                    kind="path",
                    default="",
                    help="留空使用同级 labels 目录",
                ),
                ParameterSpec(
                    name="overwrite",
                    label="覆盖已存在标签",
                    kind="bool",
                    default=False,
                ),
            ),
        ),
        _op(
            "label.flip",
            category,
            "翻转标签坐标",
            "水平/垂直翻转 YOLO 标签坐标。",
            label_handlers.handle_flip,
            (
                ParameterSpec(
                    name="labels_dir",
                    label="标签目录",
                    kind="path",
                    required=True,
                ),
                ParameterSpec(
                    name="flip_type",
                    label="翻转类型",
                    kind="choice",
                    default="horizontal",
                    choices=(
                        ("水平翻转", "horizontal"),
                        ("垂直翻转", "vertical"),
                        ("双向翻转", "both"),
                    ),
                ),
                ParameterSpec(
                    name="backup",
                    label="备份原文件",
                    kind="bool",
                    default=True,
                ),
            ),
        ),
        _op(
            "label.filter",
            category,
            "过滤标签类别",
            "按类别保留或移除标签行。",
            label_handlers.handle_filter,
            (
                ParameterSpec(
                    name="labels_dir",
                    label="标签目录",
                    kind="path",
                    required=True,
                ),
                ParameterSpec(
                    name="classes",
                    label="目标类别",
                    kind="str",
                    required=True,
                    help="逗号分隔，如 0,1,2",
                ),
                ParameterSpec(
                    name="action",
                    label="操作类型",
                    kind="choice",
                    default="keep",
                    choices=(("保留", "keep"), ("移除", "remove")),
                ),
                ParameterSpec(
                    name="backup",
                    label="备份原文件",
                    kind="bool",
                    default=True,
                ),
            ),
        ),
        _op(
            "label.remove_empty",
            category,
            "删除空标签",
            "删除空标签文件及对应图像。",
            label_handlers.handle_remove_empty,
            (
                ParameterSpec(
                    name="dataset_dir",
                    label="数据集目录",
                    kind="path",
                    required=True,
                ),
                images_subdir,
                labels_subdir,
            ),
            destructive=True,
        ),
        _op(
            "label.remove_class",
            category,
            "删除只包含指定类别标签",
            "删除只包含指定类别的标签及对应图像。",
            label_handlers.handle_remove_class,
            (
                ParameterSpec(
                    name="dataset_dir",
                    label="数据集目录",
                    kind="path",
                    required=True,
                ),
                ParameterSpec(
                    name="target_class",
                    label="类别编号",
                    kind="int",
                    default=None,
                    help="留空时处理前会请求选择",
                ),
                images_subdir,
                labels_subdir,
            ),
            destructive=True,
        ),
    ]


def _env_operations() -> List[Operation]:
    category = env_handlers.CATEGORY
    return [
        _op(
            "env.auto_fix",
            category,
            "一键检查并修复所有环境",
            "检查系统、依赖、工作目录，并按需确认安装或初始化。",
            env_handlers.handle_auto_fix_environment,
        ),
        _op(
            "env.check_dependencies",
            category,
            "仅检查Python依赖",
            "检查 requirements.txt 中的依赖是否可导入。",
            env_handlers.handle_check_dependencies,
        ),
        _op(
            "env.install_dependencies",
            category,
            "仅安装缺失依赖",
            "使用当前 Python 安装缺失依赖（打包环境不自动下载）。",
            env_handlers.handle_install_dependencies,
        ),
        _op(
            "env.initialize_workspace",
            category,
            "仅初始化工作目录",
            "创建 logs/temp 目录与默认配置。",
            env_handlers.handle_initialize_workspace,
        ),
        _op(
            "env.check_system",
            category,
            "系统环境检查",
            "显示操作系统、Python 版本与工作目录信息。",
            env_handlers.handle_check_system,
        ),
    ]


def _config_operations() -> List[Operation]:
    category = config_handlers.CATEGORY
    path_fields = (
        ParameterSpec(
            name="paths__input_dir",
            label="输入目录",
            kind="path",
            default="",
        ),
        ParameterSpec(
            name="paths__output_dir",
            label="输出目录",
            kind="path",
            default="",
        ),
        ParameterSpec(
            name="paths__temp_dir",
            label="临时目录",
            kind="path",
            default="",
        ),
        ParameterSpec(
            name="paths__log_dir",
            label="日志目录",
            kind="path",
            default="",
        ),
    )
    processing_fields = (
        ParameterSpec(
            name="processing__batch_size", label="批处理大小", kind="int", default=None
        ),
        ParameterSpec(
            name="processing__max_workers",
            label="最大工作线程",
            kind="int",
            default=None,
        ),
        ParameterSpec(
            name="processing__timeout", label="超时时间(秒)", kind="int", default=None
        ),
        ParameterSpec(
            name="processing__retry_count", label="重试次数", kind="int", default=None
        ),
    )
    image_fields = (
        ParameterSpec(
            name="image_processing__default_output_format",
            label="默认输出格式",
            kind="choice",
            default="",
            choices=(
                ("保持不变", ""),
                ("jpg", "jpg"),
                ("jpeg", "jpeg"),
                ("png", "png"),
                ("webp", "webp"),
            ),
        ),
        ParameterSpec(
            name="image_processing__jpeg_quality",
            label="JPEG 质量",
            kind="int",
            default=None,
        ),
        ParameterSpec(
            name="image_processing__png_compression",
            label="PNG 压缩级别",
            kind="int",
            default=None,
        ),
        ParameterSpec(
            name="image_processing__webp_quality",
            label="WebP 质量",
            kind="int",
            default=None,
        ),
        ParameterSpec(
            name="image_processing__chunk_size",
            label="分块大小",
            kind="int",
            default=None,
        ),
    )
    yolo_fields = (
        ParameterSpec(
            name="yolo__label_format", label="标签格式", kind="str", default=""
        ),
        ParameterSpec(
            name="yolo__classes_file", label="类别文件", kind="str", default=""
        ),
        ParameterSpec(
            name="yolo__validate_on_load",
            label="加载时验证",
            kind="bool",
            default=None,
        ),
    )
    return [
        _op(
            "config.view",
            category,
            "查看当前配置",
            "显示当前生效的完整配置。",
            config_handlers.handle_view_config,
        ),
        _op(
            "config.set_log_level",
            category,
            "日志级别设置",
            "查看并设置日志级别。",
            config_handlers.handle_set_log_level,
            config_handlers.LOG_LEVEL_FIELDS,
        ),
        _op(
            "config.edit_paths",
            category,
            "路径配置",
            "修改输入/输出/临时/日志目录。",
            config_handlers.handle_edit_config,
            path_fields,
        ),
        _op(
            "config.edit_processing",
            category,
            "处理配置",
            "修改批处理大小、线程数、超时与重试。",
            config_handlers.handle_edit_config,
            processing_fields,
        ),
        _op(
            "config.edit_image",
            category,
            "图像处理配置",
            "修改图像处理默认输出格式与质量参数。",
            config_handlers.handle_edit_config,
            image_fields,
        ),
        _op(
            "config.edit_yolo",
            category,
            "YOLO配置",
            "修改标签格式、类别文件与加载校验。",
            config_handlers.handle_edit_config,
            yolo_fields,
        ),
        _op(
            "config.edit_ui",
            category,
            "界面配置",
            "修改语言、主题与进度显示（业务配置）。",
            config_handlers.handle_edit_config,
            (
                ParameterSpec(
                    name="ui__language",
                    label="语言",
                    kind="str",
                    default="",
                ),
                ParameterSpec(
                    name="ui__theme",
                    label="主题",
                    kind="str",
                    default="",
                ),
                ParameterSpec(
                    name="ui__show_progress",
                    label="显示进度",
                    kind="bool",
                    default=None,
                ),
            ),
        ),
        _op(
            "config.load",
            category,
            "加载配置文件",
            "从指定 JSON/YAML 文件加载并合并配置。",
            config_handlers.handle_load_config,
            (
                ParameterSpec(
                    name="config_file",
                    label="配置文件路径",
                    kind="path",
                    required=True,
                ),
            ),
        ),
        _op(
            "config.save",
            category,
            "保存配置文件",
            "把当前配置保存到指定文件。",
            config_handlers.handle_save_config,
            (
                ParameterSpec(
                    name="config_file",
                    label="配置文件路径",
                    kind="path",
                    required=True,
                ),
            ),
        ),
        _op(
            "config.reset",
            category,
            "重置为默认配置",
            "把配置重置为内置默认值。",
            config_handlers.handle_reset_config,
            destructive=True,
        ),
    ]


def _is_frozen() -> bool:
    """是否运行在 PyInstaller 等冻结产物中。"""
    return bool(getattr(sys, "frozen", False))


def build_operations() -> Tuple[Operation, ...]:
    """构建完整操作目录（保持旧菜单顺序）。

    源码运行（含旧交互界面）保留全部操作；冻结产物隐藏「环境检查与配置」
    入口——打包环境无法安装缺失依赖，暴露这些按钮只会误导用户。
    """
    operations: List[Operation] = []
    operations.extend(_yolo_operations())
    operations.extend(_image_operations())
    operations.extend(_file_operations())
    operations.extend(_label_operations())
    if not _is_frozen():
        operations.extend(_env_operations())
    operations.extend(_config_operations())
    return tuple(operations)


def category_order() -> Tuple[str, ...]:
    """类别展示顺序（与旧主菜单一致）。

    这里保留环境类占位以稳定索引；冻结产物中该类别下没有操作，界面会自行
    跳过空类别。
    """
    return (
        yolo_handlers.CATEGORY,
        image_handlers.CATEGORY,
        file_handlers.CATEGORY,
        label_handlers.CATEGORY,
        env_handlers.CATEGORY,
        config_handlers.CATEGORY,
    )


__all__ = ["build_operations", "category_order"]
