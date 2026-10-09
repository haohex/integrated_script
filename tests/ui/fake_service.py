# -*- coding: utf-8 -*-
"""Test-only Fake AppService implementation for UI testing and isolated fixtures."""

from __future__ import annotations

import uuid
from typing import Any

from integrated_script.contracts.results import OperationResult
from integrated_script.ui.shared.contract import (
    InteractionRequest,
    OperationSpec,
    ParameterSpec,
    TaskEvent,
)


class FakeAppService:
    """Contract-compliant mock service for testing, visual capture, and isolated unit tests."""

    def __init__(self, simulate_delays: bool = False):
        self.simulate_delays = simulate_delays
        self._busy = False
        self._current_task_id: str | None = None
        self._events: list[TaskEvent] = []
        self._pending_interaction: InteractionRequest | None = None
        self._waiting_response = False
        self._closed = False
        self._operations = self._build_operations()

    def _build_operations(self) -> tuple[OperationSpec, ...]:
        return (
            OperationSpec(
                id="yolo.ctds_to_yolo",
                category="YOLO数据集处理",
                label="CTDS数据转YOLO格式",
                description="处理 CTDS 标注，剔除空标签/非法标注并按确认的类型生成 YOLO 数据集。",
                destructive=True,
                fields=(
                    ParameterSpec(
                        name="dataset_path",
                        label="数据集路径",
                        kind="path",
                        required=True,
                        help="CTDS / YOLO / X-label 数据集目录",
                    ),
                    ParameterSpec(
                        name="output_name",
                        label="项目名称",
                        kind="str",
                        default="",
                        help="留空自动生成",
                    ),
                    ParameterSpec(
                        name="keep_empty_labels",
                        label="保留空标签文件",
                        kind="bool",
                        default=False,
                    ),
                ),
            ),
            OperationSpec(
                id="yolo.clean_unmatched",
                category="YOLO数据集处理",
                label="清理不匹配文件",
                description="清理没有对应标签的图像或没有对应图像的标签文件。",
                destructive=True,
                fields=(
                    ParameterSpec(
                        name="dataset_path",
                        label="数据集路径",
                        kind="path",
                        required=True,
                    ),
                ),
            ),
            OperationSpec(
                id="yolo.validate_detection",
                category="YOLO数据集处理",
                label="目标检测数据集验证",
                description="检查图像与标签匹配度、标签越界、类别分布与无效标注。",
                fields=(
                    ParameterSpec(
                        name="dataset_path",
                        label="数据集路径",
                        kind="path",
                        required=True,
                    ),
                ),
            ),
            OperationSpec(
                id="config.view",
                category="配置管理",
                label="查看当前配置",
                description="读取并展示全局配置文件与生效的运行时默认参数。",
                fields=(),
            ),
            OperationSpec(
                id="env.check_dependencies",
                category="环境检查与配置",
                label="仅检查Python依赖",
                description="检查 Python 运行时环境与依赖包安装状态。",
                fields=(),
            ),
        )

    def list_operations(self) -> tuple[OperationSpec, ...]:
        return self._operations

    def start(self, operation_id: str, values: dict[str, Any]) -> str:
        if self._busy:
            raise ValueError("Service is already busy with another operation")

        self._busy = True
        self._current_task_id = str(uuid.uuid4())
        self._events.clear()
        self._waiting_response = False
        self._pending_interaction = None

        task_id = self._current_task_id

        self._events.append(
            TaskEvent(
                task_id=task_id, kind="started", message=f"已开始操作: {operation_id}"
            )
        )

        if operation_id == "yolo.ctds_to_yolo":
            self._events.append(
                TaskEvent(
                    task_id=task_id,
                    kind="log",
                    message="正在扫描 CTDS 根目录与 obj.names...",
                )
            )
            req = InteractionRequest(
                id="req_ctds_confirm",
                title="CTDS 数据集转换确认",
                message="此操作将重构数据集目录结构并可能覆盖原有文件，请核对信息：",
                kind="confirm",
                details=(
                    "检测到 1,420 张图像与 1,398 个标签文件",
                    "将剔除 22 个非法/空标注样本",
                    "将生成标准 images/ 与 labels/ 子目录",
                    "原始 obj.names 将复制并重命名为 classes.txt",
                ),
            )
            self._pending_interaction = req
            self._waiting_response = True
            self._events.append(
                TaskEvent(task_id=task_id, kind="interaction", interaction=req)
            )

        elif operation_id == "yolo.clean_unmatched":
            req = InteractionRequest(
                id="req_clean_confirm",
                title="危险操作：确认清理未匹配文件",
                message="即将永久删除以下检测到的孤立文件：",
                kind="confirm",
                details=(
                    "孤立图像 (无对应txt): 14 个文件",
                    "孤立标签 (无对应jpg): 3 个文件",
                ),
            )
            self._pending_interaction = req
            self._waiting_response = True
            self._events.append(
                TaskEvent(task_id=task_id, kind="interaction", interaction=req)
            )

        elif operation_id == "yolo.validate_detection":
            self._events.append(
                TaskEvent(
                    task_id=task_id,
                    kind="progress",
                    current=25,
                    total=100,
                    message="正在解析类别文件...",
                )
            )
            self._events.append(
                TaskEvent(
                    task_id=task_id,
                    kind="progress",
                    current=65,
                    total=100,
                    message="正在核对坐标边界与越界框...",
                )
            )
            self._events.append(
                TaskEvent(
                    task_id=task_id,
                    kind="progress",
                    current=100,
                    total=100,
                    message="统计分析完成",
                )
            )
            payload = {
                "total_images": 1520,
                "total_labels": 1520,
                "valid_annotations": 8432,
                "invalid_annotations": 0,
                "categories_count": 4,
                "classes_distribution": [
                    {
                        "class_id": 0,
                        "class_name": "car",
                        "count": 4210,
                        "ratio": "49.9%",
                    },
                    {
                        "class_id": 1,
                        "class_name": "truck",
                        "count": 2150,
                        "ratio": "25.5%",
                    },
                    {
                        "class_id": 2,
                        "class_name": "bus",
                        "count": 1322,
                        "ratio": "15.7%",
                    },
                    {
                        "class_id": 3,
                        "class_name": "pedestrian",
                        "count": 750,
                        "ratio": "8.9%",
                    },
                ],
                "dataset_health": "Optimal (No issues detected)",
                "execution_seconds": 1.48,
            }
            res = OperationResult(
                success=True,
                message="目标检测数据集验证通过，未发现越界标注。",
                payload=payload,
            )
            self._events.append(
                TaskEvent(task_id=task_id, kind="completed", result=res)
            )
            self._busy = False

        elif operation_id == "env.check_dependencies":
            payload = {
                "python_version": "3.11.15",
                "packages": [
                    {"package": "PySide6", "installed": "6.8.3", "status": "OK"},
                    {"package": "Textual", "installed": "8.2.8", "status": "OK"},
                    {"package": "pytest", "installed": "9.1.1", "status": "OK"},
                ],
                "all_passed": True,
            }
            res = OperationResult(
                success=True,
                message="所有必要依赖均已正确安装并兼容。",
                payload=payload,
            )
            self._events.append(
                TaskEvent(task_id=task_id, kind="completed", result=res)
            )
            self._busy = False

        else:
            self._events.append(
                TaskEvent(
                    task_id=task_id,
                    kind="progress",
                    current=100,
                    total=100,
                    message="操作完成",
                )
            )
            payload = {
                "operation": operation_id,
                "parameters_received": values,
                "status": "completed_successfully",
            }
            res = OperationResult(
                success=True, message="操作执行成功。", payload=payload
            )
            self._events.append(
                TaskEvent(task_id=task_id, kind="completed", result=res)
            )
            self._busy = False

        return task_id

    def poll_events(self) -> list[TaskEvent]:
        events = list(self._events)
        self._events.clear()
        return events

    def respond(self, task_id: str, request_id: str, values: dict[str, Any]) -> None:
        if task_id != self._current_task_id or not self._waiting_response:
            return

        self._waiting_response = False
        self._pending_interaction = None

        if values.get("_cancelled") is True or values.get("confirmed") is False:
            res = OperationResult(
                success=False,
                message="用户已取消本次交互操作。",
                error_code="OPERATION_CANCELLED",
                payload={
                    "task_id": task_id,
                    "request_id": request_id,
                    "cancelled": True,
                },
            )
            self._events.append(
                TaskEvent(task_id=task_id, kind="completed", result=res)
            )
            self._busy = False
            return

        self._events.append(
            TaskEvent(
                task_id=task_id, kind="log", message="收到用户确认，继续执行核心转换..."
            )
        )
        self._events.append(
            TaskEvent(
                task_id=task_id,
                kind="progress",
                current=100,
                total=100,
                message="数据写入并校验完成",
            )
        )
        res = OperationResult(
            success=True,
            message="CTDS 数据集转换及重构顺利完成。",
            payload={"task_id": task_id, "total_images_processed": 1398},
        )
        self._events.append(TaskEvent(task_id=task_id, kind="completed", result=res))
        self._busy = False

    @property
    def busy(self) -> bool:
        return self._busy

    def close(self) -> None:
        self._closed = True
