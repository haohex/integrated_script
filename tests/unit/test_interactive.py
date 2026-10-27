from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

from integrated_script.config.settings import ConfigManager
from integrated_script.ui.interactive import InteractiveInterface
from integrated_script.workflows.file_workflow import FileWorkflow


class _StubYoloProcessor:
    def __init__(
        self,
        pre_result: Dict[str, Any],
        continue_result: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.pre_result = pre_result
        self.continue_result = continue_result or {"success": True}
        self.process_called = False
        self.continue_called = False
        self.last_continue_args: Optional[Tuple[Dict[str, Any], str]] = None
        self.last_continue_kwargs: Dict[str, Any] = {}

    def process_ctds_dataset(
        self, _dataset_path: str, **_kwargs: Any
    ) -> Dict[str, Any]:
        self.process_called = True
        return self.pre_result

    def continue_ctds_processing(
        self,
        _pre_result: Dict[str, Any],
        _confirmed_type: str,
        **_kwargs: Any,
    ) -> Dict[str, Any]:
        self.continue_called = True
        self.last_continue_args = (_pre_result, _confirmed_type)
        self.last_continue_kwargs = _kwargs
        return self.continue_result

    def convert_yolo_to_ctds_dataset(
        self,
        dataset_path: str,
        output_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "success": True,
            "dataset_path": dataset_path,
            "output_path": output_path or "/tmp/ctds",
            "statistics": {
                "total_labels": 1,
                "labels_copied": 1,
                "images_copied": 1,
                "missing_images": 0,
            },
            "missing_images": [],
        }


class _RecordingYoloWorkflow:
    instances: List["_RecordingYoloWorkflow"] = []

    def __init__(self, processor: Any) -> None:
        self.processor = processor
        self.process_calls: List[Tuple[str, Optional[str], bool]] = []
        self.continue_calls: List[Tuple[Dict[str, Any], str, Optional[bool]]] = []
        self.convert_calls: List[Tuple[str, Optional[str]]] = []
        _RecordingYoloWorkflow.instances.append(self)

    def process_ctds_dataset(
        self,
        input_path: str,
        output_name: Optional[str] = None,
        keep_empty_labels: bool = False,
    ) -> Dict[str, Any]:
        self.process_calls.append((input_path, output_name, keep_empty_labels))
        return {
            "success": True,
            "stage": "pre_detection",
            "pre_detection_result": {
                "dataset_type": "detection",
                "confidence": 0.95,
            },
        }

    def continue_ctds_processing(
        self,
        pre_result: Dict[str, Any],
        confirmed_type: str,
        keep_empty_labels: Optional[bool] = None,
    ) -> Dict[str, Any]:
        self.continue_calls.append((pre_result, confirmed_type, keep_empty_labels))
        return {
            "success": True,
            "output_path": "/tmp/output",
            "project_name": "demo",
            "statistics": {"final_count": 1},
        }

    def convert_yolo_to_ctds_dataset(
        self,
        dataset_path: str,
        output_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        self.convert_calls.append((dataset_path, output_path))
        return {
            "success": True,
            "dataset_path": dataset_path,
            "output_path": output_path or "/tmp/ctds",
            "statistics": {
                "total_labels": 1,
                "labels_copied": 1,
                "images_copied": 1,
                "missing_images": 0,
            },
            "missing_images": [],
        }


@pytest.fixture(autouse=True)
def _reset_recording_workflow_state() -> None:
    _RecordingYoloWorkflow.instances.clear()


@pytest.fixture
def interface_with_non_exe(monkeypatch, tmp_path) -> InteractiveInterface:
    monkeypatch.setattr(InteractiveInterface, "_is_running_as_exe", lambda self: False)
    config = ConfigManager(config_file=tmp_path / "config.json", auto_save=False)
    return InteractiveInterface(config_manager=config)


@pytest.fixture
def interface_with_exe(monkeypatch, tmp_path) -> InteractiveInterface:
    monkeypatch.setattr(InteractiveInterface, "_is_running_as_exe", lambda self: True)
    config = ConfigManager(config_file=tmp_path / "config.json", auto_save=False)
    return InteractiveInterface(config_manager=config)


def test_main_menu_includes_environment_entry_when_not_exe(
    interface_with_non_exe,
) -> None:
    options = [
        name for name, _ in interface_with_non_exe.menu_system.main_menu["options"]
    ]

    assert "环境检查与配置" in options


def test_main_menu_hides_environment_entry_when_exe(interface_with_exe) -> None:
    options = [name for name, _ in interface_with_exe.menu_system.main_menu["options"]]

    assert "环境检查与配置" not in options


def test_get_processor_reuses_cached_instance(interface_with_non_exe) -> None:
    processor1 = interface_with_non_exe._get_processor("file")
    processor2 = interface_with_non_exe._get_processor("file")

    assert processor1 is processor2


def test_get_processor_unknown_key_raises_key_error(interface_with_non_exe) -> None:
    with pytest.raises(KeyError):
        interface_with_non_exe._get_processor("unknown")


def test_get_user_confirmed_type_returns_none_when_low_confidence_user_cancels(
    interface_with_non_exe, monkeypatch
) -> None:
    monkeypatch.setattr("builtins.input", lambda _prompt="": "3")

    confirmed = interface_with_non_exe._get_user_confirmed_type(
        detected_type="mixed", confidence=0.5
    )

    assert confirmed is None


def test_get_user_confirmed_type_returns_detected_type_when_high_confidence_confirmed(
    interface_with_non_exe, monkeypatch
) -> None:
    monkeypatch.setattr(
        interface_with_non_exe, "_get_yes_no_input", lambda *_a, **_k: True
    )

    confirmed = interface_with_non_exe._get_user_confirmed_type(
        detected_type="detection", confidence=0.95
    )

    assert confirmed == "detection"


def test_yolo_process_ctds_aborts_when_user_cancels_confirmation(
    interface_with_non_exe, monkeypatch
) -> None:
    pre_result = {
        "stage": "pre_detection",
        "pre_detection_result": {"dataset_type": "detection", "confidence": 0.95},
    }
    processor = _StubYoloProcessor(pre_result=pre_result)

    monkeypatch.setattr(
        interface_with_non_exe,
        "_get_path_input",
        lambda _prompt, must_exist=True: "/tmp/ctds-dataset",
    )
    monkeypatch.setattr(
        interface_with_non_exe, "_get_processor", lambda _name: processor
    )
    monkeypatch.setattr(
        interface_with_non_exe, "_get_yes_no_input", lambda *_a, **_k: False
    )
    monkeypatch.setattr(
        interface_with_non_exe,
        "_get_user_confirmed_type",
        lambda _detected_type, _confidence: None,
    )
    monkeypatch.setattr(interface_with_non_exe, "_pause", lambda: None)
    inputs = iter([""])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    interface_with_non_exe._yolo_process_ctds()

    assert processor.process_called is True
    assert processor.continue_called is False


def test_yolo_process_ctds_continues_after_user_confirmation(
    interface_with_non_exe, monkeypatch
) -> None:
    pre_result = {
        "stage": "pre_detection",
        "pre_detection_result": {"dataset_type": "detection", "confidence": 0.95},
    }
    continue_result = {
        "success": True,
        "output_path": "/tmp/output",
        "project_name": "demo",
        "statistics": {"final_count": 1},
    }
    processor = _StubYoloProcessor(
        pre_result=pre_result, continue_result=continue_result
    )
    displayed = {}

    monkeypatch.setattr(
        interface_with_non_exe,
        "_get_path_input",
        lambda _prompt, must_exist=True: "/tmp/ctds-dataset",
    )
    monkeypatch.setattr(
        interface_with_non_exe, "_get_processor", lambda _name: processor
    )
    monkeypatch.setattr(
        interface_with_non_exe, "_get_yes_no_input", lambda *_a, **_k: False
    )
    monkeypatch.setattr(
        interface_with_non_exe,
        "_get_user_confirmed_type",
        lambda _detected_type, _confidence: "detection",
    )
    monkeypatch.setattr(
        interface_with_non_exe,
        "_display_ctds_result",
        lambda result: displayed.setdefault("result", result),
    )
    monkeypatch.setattr(interface_with_non_exe, "_pause", lambda: None)
    inputs = iter([""])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    interface_with_non_exe._yolo_process_ctds()

    assert processor.process_called is True
    assert processor.continue_called is True
    assert processor.last_continue_args is not None
    assert processor.last_continue_args[1] == "detection"
    assert processor.last_continue_kwargs.get("keep_empty_labels") is False
    assert displayed["result"] == continue_result


def test_yolo_process_ctds_uses_yolo_workflow_adapter(
    interface_with_non_exe, monkeypatch
) -> None:
    marker_processor = object()
    displayed: Dict[str, Any] = {}

    monkeypatch.setattr(
        "integrated_script.ui.interactive.YoloWorkflow",
        _RecordingYoloWorkflow,
    )
    monkeypatch.setattr(
        interface_with_non_exe,
        "_get_path_input",
        lambda _prompt, must_exist=True: "/tmp/ctds-dataset",
    )
    monkeypatch.setattr(
        interface_with_non_exe, "_get_processor", lambda _name: marker_processor
    )
    monkeypatch.setattr(
        interface_with_non_exe, "_get_yes_no_input", lambda *_a, **_k: False
    )
    monkeypatch.setattr(
        interface_with_non_exe,
        "_get_user_confirmed_type",
        lambda _detected_type, _confidence: "detection",
    )
    monkeypatch.setattr(
        interface_with_non_exe,
        "_display_ctds_result",
        lambda result: displayed.setdefault("result", result),
    )
    monkeypatch.setattr(interface_with_non_exe, "_pause", lambda: None)
    inputs = iter([""])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    interface_with_non_exe._yolo_process_ctds()

    assert len(_RecordingYoloWorkflow.instances) == 1
    workflow = _RecordingYoloWorkflow.instances[0]
    assert workflow.processor is marker_processor
    assert len(workflow.process_calls) == 1
    assert len(workflow.continue_calls) == 1
    assert workflow.continue_calls[0][1] == "detection"
    assert workflow.continue_calls[0][2] is False
    assert displayed["result"]["success"] is True
    assert displayed["result"]["project_name"] == "demo"


def test_display_ctds_result_shows_out_of_bounds_stats(
    interface_with_non_exe, monkeypatch
) -> None:
    printed: List[str] = []

    monkeypatch.setattr(
        "builtins.print",
        lambda *args, **_kwargs: printed.append(" ".join(str(arg) for arg in args)),
    )

    interface_with_non_exe._display_ctds_result(
        {
            "success": True,
            "output_path": "/tmp/output",
            "project_name": "demo",
            "statistics": {
                "total_processed": 4,
                "final_count": 1,
                "invalid_removed": 3,
                "out_of_bounds_labels": 1,
                "missing_images": 1,
                "missing_labels": 1,
            },
        }
    )

    assert any("标签越界数: 1" in line for line in printed)
    assert any("标签缺图数: 1" in line for line in printed)
    assert any("图片缺标数: 1" in line for line in printed)


def test_yolo_convert_to_ctds_uses_yolo_workflow_adapter(
    interface_with_non_exe, monkeypatch
) -> None:
    marker_processor = object()
    inputs = iter(["/tmp/ctds-out"])

    monkeypatch.setattr(
        "integrated_script.ui.interactive.YoloWorkflow",
        _RecordingYoloWorkflow,
    )
    monkeypatch.setattr(
        interface_with_non_exe,
        "_get_path_input",
        lambda _prompt, must_exist=True: "/tmp/yolo-dataset",
    )
    monkeypatch.setattr(
        interface_with_non_exe, "_get_processor", lambda _name: marker_processor
    )
    monkeypatch.setattr(interface_with_non_exe, "_pause", lambda: None)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    interface_with_non_exe._yolo_convert_to_ctds()

    assert len(_RecordingYoloWorkflow.instances) == 1
    workflow = _RecordingYoloWorkflow.instances[0]
    assert workflow.processor is marker_processor
    assert len(workflow.convert_calls) == 1
    assert workflow.convert_calls[0][0] == "/tmp/yolo-dataset"
    assert workflow.convert_calls[0][1] == "/tmp/ctds-out"


def test_yolo_convert_to_ctds_shows_failure_message_from_workflow(
    interface_with_non_exe, monkeypatch
) -> None:
    class _FailingWorkflow(_RecordingYoloWorkflow):
        def convert_yolo_to_ctds_dataset(
            self,
            dataset_path: str,
            output_path: Optional[str] = None,
        ) -> Dict[str, Any]:
            self.convert_calls.append((dataset_path, output_path))
            return {
                "success": False,
                "error": "内部处理失败",
                "error_code": "INTERNAL_ERROR",
            }

    marker_processor = object()
    inputs = iter([""])
    printed: List[str] = []

    monkeypatch.setattr(
        "integrated_script.ui.interactive.YoloWorkflow",
        _FailingWorkflow,
    )
    monkeypatch.setattr(
        interface_with_non_exe,
        "_get_path_input",
        lambda _prompt, must_exist=True: "/tmp/yolo-dataset",
    )
    monkeypatch.setattr(
        interface_with_non_exe, "_get_processor", lambda _name: marker_processor
    )
    monkeypatch.setattr(interface_with_non_exe, "_pause", lambda: None)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))
    monkeypatch.setattr(
        "builtins.print",
        lambda *args, **_kwargs: printed.append(" ".join(str(arg) for arg in args)),
    )

    interface_with_non_exe._yolo_convert_to_ctds()

    assert any("❌ 转换失败" in line for line in printed)
    assert any("错误信息: 内部处理失败" in line for line in printed)
    assert len(_FailingWorkflow.instances) == 1


def test_yolo_convert_to_xlabel_auto_uses_yolo_workflow_adapter(
    interface_with_non_exe, monkeypatch
) -> None:
    class _WorkflowForConvert:
        instances: List["_WorkflowForConvert"] = []

        def __init__(self, processor: Any) -> None:
            self.processor = processor
            self.detect_calls: List[str] = []
            self.convert_calls: List[Tuple[str, Optional[str]]] = []
            _WorkflowForConvert.instances.append(self)

        def detect_yolo_dataset_type(self, dataset_path: str) -> Dict[str, Any]:
            self.detect_calls.append(dataset_path)
            return {
                "detected_type": "detection",
                "confidence": 0.93,
                "statistics": {
                    "total_files": 8,
                    "detection_files": 8,
                    "segmentation_files": 0,
                },
            }

        def convert_yolo_to_xlabel(
            self, dataset_path: str, output_dir: Optional[str] = None
        ) -> Dict[str, Any]:
            self.convert_calls.append((dataset_path, output_dir))
            return {"success": True, "output_path": output_dir or "/tmp/xlabel"}

    marker_processor = object()
    displayed: Dict[str, Any] = {}

    monkeypatch.setattr(
        "integrated_script.ui.interactive.YoloWorkflow",
        _WorkflowForConvert,
    )
    monkeypatch.setattr(
        interface_with_non_exe,
        "_get_path_input",
        lambda _prompt, must_exist=True: "/tmp/yolo-dataset",
    )
    monkeypatch.setattr(
        interface_with_non_exe, "_get_processor", lambda _name: marker_processor
    )
    monkeypatch.setattr(interface_with_non_exe, "_get_input", lambda *_a, **_k: "")
    monkeypatch.setattr(
        interface_with_non_exe,
        "_get_user_confirmed_type",
        lambda _detected_type, _confidence: "detection",
    )
    monkeypatch.setattr(
        interface_with_non_exe,
        "_display_result",
        lambda result: displayed.setdefault("result", result),
    )
    monkeypatch.setattr(interface_with_non_exe, "_pause", lambda: None)

    interface_with_non_exe._yolo_convert_to_xlabel_auto()

    assert len(_WorkflowForConvert.instances) == 1
    workflow = _WorkflowForConvert.instances[0]
    assert workflow.processor is marker_processor
    assert workflow.detect_calls == ["/tmp/yolo-dataset"]
    assert workflow.convert_calls == [("/tmp/yolo-dataset", None)]
    assert displayed["result"]["success"] is True


def test_yolo_process_xlabel_auto_uses_yolo_workflow_adapter(
    interface_with_non_exe, monkeypatch
) -> None:
    class _WorkflowForXlabel:
        instances: List["_WorkflowForXlabel"] = []

        def __init__(self, processor: Any) -> None:
            self.processor = processor
            self.detect_calls: List[str] = []
            self.class_calls: List[str] = []
            self.convert_calls: List[Tuple[str, Optional[str], Tuple[str, ...]]] = []
            _WorkflowForXlabel.instances.append(self)

        def detect_xlabel_dataset_type(self, source_dir: str) -> Dict[str, Any]:
            self.detect_calls.append(source_dir)
            return {
                "detected_type": "segmentation",
                "confidence": 0.9,
                "statistics": {
                    "total_shapes": 12,
                    "detection_like": 0,
                    "segmentation_like": 12,
                },
            }

        def detect_xlabel_segmentation_classes(self, source_dir: str):
            self.class_calls.append(source_dir)
            return {"cat", "dog"}

        def convert_xlabel_to_yolo_segmentation(
            self,
            source_dir: str,
            output_dir: Optional[str] = None,
            class_order: Optional[List[str]] = None,
        ) -> Dict[str, Any]:
            self.convert_calls.append(
                (source_dir, output_dir, tuple(class_order or []))
            )
            return {"success": True, "output_path": output_dir or "/tmp/yolo-seg"}

    marker_processor = object()
    displayed: Dict[str, Any] = {}

    monkeypatch.setattr(
        "integrated_script.ui.interactive.YoloWorkflow",
        _WorkflowForXlabel,
    )
    monkeypatch.setattr(
        interface_with_non_exe,
        "_get_path_input",
        lambda _prompt, must_exist=True: "/tmp/xlabel-dataset",
    )
    monkeypatch.setattr(
        interface_with_non_exe, "_get_processor", lambda _name: marker_processor
    )
    monkeypatch.setattr(interface_with_non_exe, "_get_input", lambda *_a, **_k: "")
    monkeypatch.setattr(
        interface_with_non_exe,
        "_get_user_confirmed_type",
        lambda _detected_type, _confidence: "segmentation",
    )
    monkeypatch.setattr(
        interface_with_non_exe,
        "_get_class_order_from_user",
        lambda classes: ["cat", "dog"],
    )
    monkeypatch.setattr(
        interface_with_non_exe,
        "_display_result",
        lambda result: displayed.setdefault("result", result),
    )
    monkeypatch.setattr(interface_with_non_exe, "_pause", lambda: None)

    interface_with_non_exe._yolo_process_xlabel_auto()

    assert len(_WorkflowForXlabel.instances) == 1
    workflow = _WorkflowForXlabel.instances[0]
    assert workflow.processor is marker_processor
    assert workflow.detect_calls == ["/tmp/xlabel-dataset"]
    assert workflow.class_calls == ["/tmp/xlabel-dataset"]
    assert workflow.convert_calls == [("/tmp/xlabel-dataset", None, ("cat", "dog"))]
    assert displayed["result"]["success"] is True


def test_run_xlabel_conversion_uses_yolo_workflow_adapter(
    interface_with_non_exe, monkeypatch
) -> None:
    class _WorkflowForRun:
        instances: List["_WorkflowForRun"] = []

        def __init__(self, processor: Any) -> None:
            self.processor = processor
            self.class_calls: List[str] = []
            self.convert_calls: List[Tuple[str, Optional[str], Tuple[str, ...]]] = []
            _WorkflowForRun.instances.append(self)

        def detect_xlabel_classes(self, source_dir: str):
            self.class_calls.append(source_dir)
            return {"cat", "dog"}

        def convert_xlabel_to_yolo(
            self,
            source_dir: str,
            output_dir: Optional[str] = None,
            class_order: Optional[List[str]] = None,
        ) -> Dict[str, Any]:
            self.convert_calls.append(
                (source_dir, output_dir, tuple(class_order or []))
            )
            return {"success": True, "output_path": output_dir or "/tmp/yolo"}

    marker_processor = object()

    monkeypatch.setattr(
        "integrated_script.ui.interactive.YoloWorkflow",
        _WorkflowForRun,
    )
    monkeypatch.setattr(
        interface_with_non_exe, "_get_processor", lambda _name: marker_processor
    )
    monkeypatch.setattr(
        interface_with_non_exe,
        "_get_class_order_from_user",
        lambda classes: ["cat", "dog"],
    )

    result = interface_with_non_exe._run_xlabel_conversion(
        dataset_path="/tmp/xlabel-dataset",
        output_path=None,
        mode="detection",
    )

    assert len(_WorkflowForRun.instances) == 1
    workflow = _WorkflowForRun.instances[0]
    assert workflow.processor is marker_processor
    assert workflow.class_calls == ["/tmp/xlabel-dataset"]
    assert workflow.convert_calls == [("/tmp/xlabel-dataset", None, ("cat", "dog"))]
    assert result["success"] is True


def test_yolo_detection_statistics_uses_yolo_workflow_adapter(
    interface_with_non_exe, monkeypatch
) -> None:
    class _WorkflowForStats:
        instances: List["_WorkflowForStats"] = []

        def __init__(self, processor: Any) -> None:
            self.processor = processor
            self.calls: List[str] = []
            _WorkflowForStats.instances.append(self)

        def get_dataset_statistics(self, dataset_path: str) -> Dict[str, Any]:
            self.calls.append(dataset_path)
            return {
                "success": True,
                "statistics": {
                    "is_valid": True,
                    "orphaned_images": 0,
                    "orphaned_labels": 0,
                },
            }

    marker_processor = object()
    displayed: Dict[str, Any] = {}

    monkeypatch.setattr(
        "integrated_script.ui.interactive.YoloWorkflow",
        _WorkflowForStats,
    )
    monkeypatch.setattr(
        interface_with_non_exe,
        "_get_path_input",
        lambda _prompt, must_exist=True: "/tmp/yolo-dataset",
    )
    monkeypatch.setattr(
        interface_with_non_exe, "_get_processor", lambda _name: marker_processor
    )
    monkeypatch.setattr(
        interface_with_non_exe,
        "_display_result",
        lambda result: displayed.setdefault("result", result),
    )
    monkeypatch.setattr(interface_with_non_exe, "_pause", lambda: None)

    interface_with_non_exe._yolo_detection_statistics()

    assert len(_WorkflowForStats.instances) == 1
    workflow = _WorkflowForStats.instances[0]
    assert workflow.processor is marker_processor
    assert workflow.calls == ["/tmp/yolo-dataset"]
    assert displayed["result"]["success"] is True


def test_yolo_segmentation_statistics_uses_yolo_workflow_adapter(
    interface_with_non_exe, monkeypatch
) -> None:
    class _WorkflowForSegStats:
        instances: List["_WorkflowForSegStats"] = []

        def __init__(self, processor: Any) -> None:
            self.processor = processor
            self.calls: List[str] = []
            _WorkflowForSegStats.instances.append(self)

        def get_dataset_statistics(self, dataset_path: str) -> Dict[str, Any]:
            self.calls.append(dataset_path)
            return {
                "success": True,
                "statistics": {
                    "is_valid": True,
                    "orphaned_images": 0,
                    "orphaned_labels": 0,
                },
            }

    marker_processor = object()
    displayed: Dict[str, Any] = {}

    monkeypatch.setattr(
        "integrated_script.ui.interactive.YoloWorkflow",
        _WorkflowForSegStats,
    )
    monkeypatch.setattr(
        interface_with_non_exe,
        "_get_path_input",
        lambda _prompt, must_exist=True: "/tmp/yolo-dataset",
    )
    monkeypatch.setattr(
        interface_with_non_exe, "_get_processor", lambda _name: marker_processor
    )
    monkeypatch.setattr(
        interface_with_non_exe, "_validate_segmentation_format", lambda _path: []
    )
    monkeypatch.setattr(
        interface_with_non_exe,
        "_display_result",
        lambda result: displayed.setdefault("result", result),
    )
    monkeypatch.setattr(interface_with_non_exe, "_pause", lambda: None)

    interface_with_non_exe._yolo_segmentation_statistics()

    assert len(_WorkflowForSegStats.instances) == 1
    workflow = _WorkflowForSegStats.instances[0]
    assert workflow.processor is marker_processor
    assert workflow.calls == ["/tmp/yolo-dataset"]
    assert displayed["result"]["success"] is True


def test_yolo_clean_unmatched_uses_yolo_workflow_adapter(
    interface_with_non_exe, monkeypatch
) -> None:
    class _WorkflowForClean:
        instances: List["_WorkflowForClean"] = []

        def __init__(self, processor: Any) -> None:
            self.processor = processor
            self.calls: List[Tuple[str, bool]] = []
            _WorkflowForClean.instances.append(self)

        def clean_unmatched_files(
            self,
            dataset_path: str,
            dry_run: bool = False,
        ) -> Dict[str, Any]:
            self.calls.append((dataset_path, dry_run))
            return {
                "success": True,
                "deleted_files": {
                    "orphaned_images": [],
                    "orphaned_labels": [],
                    "invalid_labels": [],
                    "empty_labels": [],
                },
                "statistics": {
                    "total_deleted": 0,
                    "deleted_images": 0,
                    "deleted_labels": 0,
                },
            }

    marker_processor = object()
    inputs = iter(["y"])

    monkeypatch.setattr(
        "integrated_script.ui.interactive.YoloWorkflow",
        _WorkflowForClean,
    )
    monkeypatch.setattr(
        interface_with_non_exe,
        "_get_path_input",
        lambda _prompt, must_exist=True: "/tmp/yolo-dataset",
    )
    monkeypatch.setattr(
        interface_with_non_exe, "_get_processor", lambda _name: marker_processor
    )
    monkeypatch.setattr(interface_with_non_exe, "_pause", lambda: None)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    interface_with_non_exe._yolo_clean_unmatched()

    assert len(_WorkflowForClean.instances) == 1
    workflow = _WorkflowForClean.instances[0]
    assert workflow.processor is marker_processor
    assert workflow.calls == [("/tmp/yolo-dataset", True)]


def test_yolo_convert_to_xlabel_auto_displays_detection_failure(
    interface_with_non_exe, monkeypatch
) -> None:
    class _WorkflowDetectFail:
        def __init__(self, _processor: Any) -> None:
            pass

        def detect_yolo_dataset_type(self, _dataset_path: str) -> Dict[str, Any]:
            return {
                "success": False,
                "error": "内部处理失败",
                "error_code": "INTERNAL_ERROR",
            }

    displayed: Dict[str, Any] = {}
    printed: List[str] = []

    monkeypatch.setattr(
        "integrated_script.ui.interactive.YoloWorkflow", _WorkflowDetectFail
    )
    monkeypatch.setattr(
        interface_with_non_exe,
        "_get_path_input",
        lambda _prompt, must_exist=True: "/tmp/yolo-dataset",
    )
    monkeypatch.setattr(interface_with_non_exe, "_get_input", lambda *_a, **_k: "")
    monkeypatch.setattr(
        interface_with_non_exe, "_get_processor", lambda _name: object()
    )
    monkeypatch.setattr(
        interface_with_non_exe,
        "_display_result",
        lambda result: displayed.setdefault("result", result),
    )
    monkeypatch.setattr(interface_with_non_exe, "_pause", lambda: None)
    monkeypatch.setattr(
        "builtins.print",
        lambda *args, **_kwargs: printed.append(" ".join(str(arg) for arg in args)),
    )

    interface_with_non_exe._yolo_convert_to_xlabel_auto()

    assert displayed["result"]["success"] is False
    assert displayed["result"]["error"] == "内部处理失败"
    assert any("数据集类型检测失败" in line for line in printed)
    assert not any("未检测到有效标签" in line for line in printed)


def test_yolo_process_xlabel_auto_displays_detection_failure(
    interface_with_non_exe, monkeypatch
) -> None:
    class _WorkflowDetectFail:
        def __init__(self, _processor: Any) -> None:
            pass

        def detect_xlabel_dataset_type(self, _source_dir: str) -> Dict[str, Any]:
            return {
                "success": False,
                "error": "内部处理失败",
                "error_code": "INTERNAL_ERROR",
            }

    displayed: Dict[str, Any] = {}
    printed: List[str] = []

    monkeypatch.setattr(
        "integrated_script.ui.interactive.YoloWorkflow", _WorkflowDetectFail
    )
    monkeypatch.setattr(
        interface_with_non_exe,
        "_get_path_input",
        lambda _prompt, must_exist=True: "/tmp/xlabel-dataset",
    )
    monkeypatch.setattr(interface_with_non_exe, "_get_input", lambda *_a, **_k: "")
    monkeypatch.setattr(
        interface_with_non_exe, "_get_processor", lambda _name: object()
    )
    monkeypatch.setattr(
        interface_with_non_exe,
        "_display_result",
        lambda result: displayed.setdefault("result", result),
    )
    monkeypatch.setattr(interface_with_non_exe, "_pause", lambda: None)
    monkeypatch.setattr(
        "builtins.print",
        lambda *args, **_kwargs: printed.append(" ".join(str(arg) for arg in args)),
    )

    interface_with_non_exe._yolo_process_xlabel_auto()

    assert displayed["result"]["success"] is False
    assert displayed["result"]["error"] == "内部处理失败"
    assert any("数据集类型检测失败" in line for line in printed)
    assert not any("未检测到有效标注" in line for line in printed)


def test_display_result_delegates_to_presenter(
    interface_with_non_exe, monkeypatch
) -> None:
    captured: Dict[str, Any] = {}

    monkeypatch.setattr(
        "integrated_script.ui.interactive.render_result",
        lambda result: captured.setdefault("result", result),
    )

    payload = {"success": True, "output_path": "/tmp/out"}
    interface_with_non_exe._display_result(payload)

    assert captured["result"] == payload


def test_file_copy_uses_file_workflow_adapter(
    interface_with_non_exe, monkeypatch
) -> None:
    class _WorkflowForFileCopy:
        instances: List["_WorkflowForFileCopy"] = []

        def __init__(self, processor: Any) -> None:
            self.processor = processor
            self.calls: List[Tuple[str, str, bool]] = []
            _WorkflowForFileCopy.instances.append(self)

        def copy_files(
            self,
            source_dir: str,
            target_dir: str,
            file_patterns: Optional[List[str]] = None,
            recursive: bool = False,
            overwrite: bool = False,
            preserve_structure: bool = True,
        ) -> Dict[str, Any]:
            del file_patterns, overwrite, preserve_structure
            self.calls.append((source_dir, target_dir, recursive))
            return {"success": True, "copied_count": 1}

    marker_processor = object()

    monkeypatch.setattr(
        "integrated_script.ui.interactive.FileWorkflow", _WorkflowForFileCopy
    )
    monkeypatch.setattr(
        interface_with_non_exe, "_get_processor", lambda _name: marker_processor
    )
    monkeypatch.setattr(
        interface_with_non_exe,
        "_get_path_input",
        lambda _prompt, must_exist=True: (
            "/tmp/source.jpg" if "源路径" in _prompt else "/tmp/target"
        ),
    )
    monkeypatch.setattr(interface_with_non_exe, "_pause", lambda: None)

    interface_with_non_exe._file_copy()

    assert len(_WorkflowForFileCopy.instances) == 1
    workflow = _WorkflowForFileCopy.instances[0]
    assert workflow.processor is marker_processor
    assert workflow.calls == [("/tmp/source.jpg", "/tmp/target", False)]


def test_label_create_empty_uses_label_workflow_adapter(
    interface_with_non_exe, monkeypatch
) -> None:
    class _WorkflowForCreateEmpty:
        instances: List["_WorkflowForCreateEmpty"] = []

        def __init__(self, processor: Any) -> None:
            self.processor = processor
            self.calls: List[Tuple[str, str, bool]] = []
            _WorkflowForCreateEmpty.instances.append(self)

        def create_empty_labels(
            self,
            images_dir: str,
            labels_dir: Optional[str] = None,
            overwrite: bool = False,
        ) -> Dict[str, Any]:
            self.calls.append((images_dir, labels_dir or "", overwrite))
            return {"success": True, "created_count": 1}

    marker_processor = object()

    monkeypatch.setattr(
        "integrated_script.ui.interactive.LabelWorkflow", _WorkflowForCreateEmpty
    )
    monkeypatch.setattr(
        interface_with_non_exe, "_get_processor", lambda _name: marker_processor
    )
    monkeypatch.setattr(
        interface_with_non_exe,
        "_get_path_input",
        lambda _prompt, must_exist=True, must_be_dir=True: "/tmp/dataset/images",
    )
    monkeypatch.setattr(interface_with_non_exe, "_get_input", lambda *_a, **_k: "")
    monkeypatch.setattr(
        interface_with_non_exe, "_get_yes_no_input", lambda *_a, **_k: False
    )
    monkeypatch.setattr(interface_with_non_exe, "_pause", lambda: None)

    interface_with_non_exe._label_create_empty()

    assert len(_WorkflowForCreateEmpty.instances) == 1
    workflow = _WorkflowForCreateEmpty.instances[0]
    assert workflow.processor is marker_processor
    assert workflow.calls == [
        (
            "/tmp/dataset/images",
            str(Path("/tmp/dataset/images").parent / "labels"),
            False,
        )
    ]


def test_image_info_uses_image_workflow_adapter(
    interface_with_non_exe, monkeypatch
) -> None:
    class _WorkflowForImageInfo:
        instances: List["_WorkflowForImageInfo"] = []

        def __init__(self, processor: Any) -> None:
            self.processor = processor
            self.calls: List[Tuple[str, bool]] = []
            _WorkflowForImageInfo.instances.append(self)

        def get_image_info(
            self, image_path: str, recursive: bool = False
        ) -> Dict[str, Any]:
            self.calls.append((image_path, recursive))
            return {"success": True, "file_path": image_path}

    marker_processor = object()
    displayed: Dict[str, Any] = {}

    monkeypatch.setattr(
        "integrated_script.ui.interactive.ImageWorkflow", _WorkflowForImageInfo
    )
    monkeypatch.setattr(
        interface_with_non_exe, "_get_processor", lambda _name: marker_processor
    )
    monkeypatch.setattr(
        interface_with_non_exe,
        "_get_path_input",
        lambda _prompt, must_exist=True: "/tmp/img.jpg",
    )
    monkeypatch.setattr(
        interface_with_non_exe,
        "_display_enhanced_image_info",
        lambda result: displayed.setdefault("result", result),
    )
    monkeypatch.setattr(interface_with_non_exe, "_pause", lambda: None)

    interface_with_non_exe._image_info()

    assert len(_WorkflowForImageInfo.instances) == 1
    workflow = _WorkflowForImageInfo.instances[0]
    assert workflow.processor is marker_processor
    assert workflow.calls == [("/tmp/img.jpg", False)]
    assert displayed["result"]["success"] is True


def test_file_workflow_rename_sync_preserves_legacy_defaults() -> None:
    class _StubFileProcessor:
        def __init__(self) -> None:
            self.last_call: Optional[Tuple[str, str, str, int, bool]] = None

        def rename_images_labels_sync(
            self,
            images_dir: str,
            labels_dir: str,
            prefix: str,
            digits: int = 5,
            shuffle_order: bool = False,
        ) -> Dict[str, Any]:
            self.last_call = (images_dir, labels_dir, prefix, digits, shuffle_order)
            return {"success": True, "renamed_count": 1}

    processor = _StubFileProcessor()
    workflow = FileWorkflow(processor)

    result = workflow.rename_images_labels_sync("/tmp/images", "/tmp/labels", "demo")

    assert processor.last_call == ("/tmp/images", "/tmp/labels", "demo", 5, False)
    assert result["success"] is True


def test_yolo_merge_datasets_uses_yolo_workflow_adapter(
    interface_with_non_exe, monkeypatch, tmp_path
) -> None:
    class _WorkflowForMerge:
        def detect_name_conflicts(self, dataset_paths):
            return {"has_conflict": False, "conflict_count": 0, "examples": []}

        instances: List["_WorkflowForMerge"] = []

        def __init__(self, processor: Any) -> None:
            self.processor = processor
            self.validate_calls: List[List[Path]] = []
            self.generate_calls: List[Tuple[List[str], List[Path]]] = []
            self.merge_calls: List[
                Tuple[List[Path], str, Optional[str], Optional[str]]
            ] = []
            _WorkflowForMerge.instances.append(self)

        def validate_classes_consistency(
            self, dataset_paths: List[Path]
        ) -> Dict[str, Any]:
            self.validate_calls.append(dataset_paths)
            return {"consistent": True, "classes": ["cat", "dog"]}

        def generate_output_name(
            self, classes: List[str], dataset_paths: List[Path]
        ) -> str:
            self.generate_calls.append((classes, dataset_paths))
            return "merged-cat-dog"

        def merge_datasets(
            self,
            dataset_paths: List[Path],
            output_path: str,
            output_name: Optional[str] = None,
            image_prefix: Optional[str] = None,
        ) -> Dict[str, Any]:
            self.merge_calls.append(
                (dataset_paths, output_path, output_name, image_prefix)
            )
            return {
                "success": True,
                "output_path": "/tmp/merged",
                "total_images": 2,
                "total_labels": 2,
                "classes": ["cat", "dog"],
                "merged_datasets": 2,
            }

    d1 = tmp_path / "d1"
    d2 = tmp_path / "d2"
    d1.mkdir()
    d2.mkdir()

    marker_processor = object()
    inputs = iter([str(d1), str(d2), "", "", "", "y"])

    monkeypatch.setattr(
        "integrated_script.ui.interactive.YoloWorkflow", _WorkflowForMerge
    )
    monkeypatch.setattr(
        interface_with_non_exe, "_get_processor", lambda _name: marker_processor
    )
    monkeypatch.setattr(interface_with_non_exe, "_pause", lambda: None)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    interface_with_non_exe._yolo_merge_datasets()

    assert len(_WorkflowForMerge.instances) == 1
    workflow = _WorkflowForMerge.instances[0]
    assert workflow.processor is marker_processor
    assert len(workflow.validate_calls) == 1
    assert len(workflow.generate_calls) == 1
    assert len(workflow.merge_calls) == 1
    assert workflow.merge_calls[0][1] == "."


def test_yolo_merge_different_datasets_uses_yolo_workflow_adapter(
    interface_with_non_exe, monkeypatch, tmp_path
) -> None:
    class _WorkflowForDiffMerge:
        def detect_name_conflicts(self, dataset_paths):
            return {"has_conflict": False, "conflict_count": 0, "examples": []}

        instances: List["_WorkflowForDiffMerge"] = []

        def __init__(self, processor: Any) -> None:
            self.processor = processor
            self.collect_calls: List[List[Path]] = []
            self.mapping_calls: List[List[Dict[str, Any]]] = []
            self.generate_calls: List[Tuple[List[str], List[Path]]] = []
            self.merge_calls: List[
                Tuple[List[str], str, Optional[str], Optional[str], Optional[List[int]]]
            ] = []
            _WorkflowForDiffMerge.instances.append(self)

        def collect_all_classes_info(
            self, dataset_paths: List[Path]
        ) -> List[Dict[str, Any]]:
            self.collect_calls.append(dataset_paths)
            return [
                {"dataset_path": dataset_paths[0], "classes": ["cat"]},
                {"dataset_path": dataset_paths[1], "classes": ["dog"]},
            ]

        def create_unified_class_mapping(
            self, all_classes_info: List[Dict[str, Any]]
        ) -> Tuple[List[str], List[Dict[int, int]]]:
            self.mapping_calls.append(all_classes_info)
            return ["cat", "dog"], [{0: 0}, {0: 1}]

        def generate_different_output_name(
            self,
            unified_classes: List[str],
            dataset_paths: List[Path],
        ) -> str:
            self.generate_calls.append((unified_classes, dataset_paths))
            return "merged-diff"

        def merge_different_type_datasets(
            self,
            dataset_paths: List[str],
            output_path: str,
            output_name: Optional[str] = None,
            image_prefix: Optional[str] = None,
            dataset_order: Optional[List[int]] = None,
        ) -> Dict[str, Any]:
            self.merge_calls.append(
                (dataset_paths, output_path, output_name, image_prefix, dataset_order)
            )
            return {
                "success": True,
                "output_path": "/tmp/merged-diff",
                "total_images": 2,
                "total_labels": 2,
                "unified_classes": ["cat", "dog"],
                "merged_datasets": 2,
                "statistics": [],
            }

    d1 = tmp_path / "d1"
    d2 = tmp_path / "d2"
    d1.mkdir()
    d2.mkdir()

    marker_processor = object()
    inputs = iter([str(d1), str(d2), "", "n", "", "", "y"])

    monkeypatch.setattr(
        "integrated_script.ui.interactive.YoloWorkflow", _WorkflowForDiffMerge
    )
    monkeypatch.setattr(
        interface_with_non_exe, "_get_processor", lambda _name: marker_processor
    )
    monkeypatch.setattr(interface_with_non_exe, "_pause", lambda: None)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    interface_with_non_exe._yolo_merge_different_datasets()

    assert len(_WorkflowForDiffMerge.instances) == 1
    workflow = _WorkflowForDiffMerge.instances[0]
    assert workflow.processor is marker_processor
    assert len(workflow.collect_calls) == 1
    assert len(workflow.mapping_calls) == 1
    assert len(workflow.generate_calls) == 1
    assert len(workflow.merge_calls) == 1
    assert workflow.merge_calls[0][1] == "."


def test_yes_no_input_returns_true_on_empty_when_default_true(
    interface_with_non_exe, monkeypatch
) -> None:
    monkeypatch.setattr(interface_with_non_exe, "_get_input", lambda _prompt: "")

    result = interface_with_non_exe._get_yes_no_input("是否继续?", default=True)

    assert result is True


def test_yes_no_input_returns_false_on_empty_when_default_false(
    interface_with_non_exe, monkeypatch
) -> None:
    monkeypatch.setattr(interface_with_non_exe, "_get_input", lambda _prompt: "")

    result = interface_with_non_exe._get_yes_no_input("是否继续?", default=False)

    assert result is False


@pytest.mark.parametrize("raw", ["y", "yes", "是", "1", "true"])
def test_yes_no_input_accepts_true_values(
    interface_with_non_exe, monkeypatch, raw
) -> None:
    monkeypatch.setattr(interface_with_non_exe, "_get_input", lambda _prompt: raw)

    result = interface_with_non_exe._get_yes_no_input("是否继续?", default=False)

    assert result is True


@pytest.mark.parametrize("raw", ["n", "no", "否", "0", "false"])
def test_yes_no_input_accepts_false_values(
    interface_with_non_exe, monkeypatch, raw
) -> None:
    monkeypatch.setattr(interface_with_non_exe, "_get_input", lambda _prompt: raw)

    result = interface_with_non_exe._get_yes_no_input("是否继续?", default=True)

    assert result is False


def test_yes_no_input_retries_on_invalid_input(
    interface_with_non_exe, monkeypatch
) -> None:
    responses = iter(["???", "y"])
    printed: List[str] = []

    monkeypatch.setattr(
        interface_with_non_exe, "_get_input", lambda _prompt: next(responses)
    )
    monkeypatch.setattr(
        "builtins.print",
        lambda *args, **_kwargs: printed.append(" ".join(str(arg) for arg in args)),
    )

    result = interface_with_non_exe._get_yes_no_input("是否继续?", default=False)

    assert result is True
    assert any("请输入 y 或 n" in line for line in printed)


def test_yes_no_input_display_prompt_contains_default_marker(
    interface_with_non_exe, monkeypatch
) -> None:
    prompts: List[str] = []

    def _capture_prompt(prompt: str) -> str:
        prompts.append(prompt)
        return ""

    monkeypatch.setattr(interface_with_non_exe, "_get_input", _capture_prompt)

    interface_with_non_exe._get_yes_no_input("是否继续?", default=True)
    interface_with_non_exe._get_yes_no_input("是否继续?", default=False)

    assert "(y/n, 默认: y): " in prompts[0]
    assert "(y/n, 默认: n): " in prompts[1]


@pytest.mark.parametrize(
    "prompt",
    [
        "是否继续? (Y/n)",
        "是否继续? (y/N)",
        "是否继续? (y/n)",
        "是否继续? 默认: y",
    ],
)
def test_yes_no_input_rejects_legacy_prompt_markers(
    interface_with_non_exe, prompt
) -> None:
    with pytest.raises(ValueError):
        interface_with_non_exe._get_yes_no_input(prompt, default=True)


def test_yolo_clean_unmatched_uses_yes_no_helper_flow(
    interface_with_non_exe, monkeypatch
) -> None:
    class _WorkflowForCleanFlow:
        instances: List["_WorkflowForCleanFlow"] = []

        def __init__(self, processor: Any) -> None:
            self.processor = processor
            self.calls: List[Tuple[str, bool]] = []
            _WorkflowForCleanFlow.instances.append(self)

        def clean_unmatched_files(self, dataset_path: str, dry_run: bool = False):
            self.calls.append((dataset_path, dry_run))
            if dry_run:
                return {
                    "success": True,
                    "deleted_files": {
                        "orphaned_images": ["a.jpg"],
                        "orphaned_labels": [],
                        "invalid_labels": [],
                        "empty_labels": [],
                    },
                    "statistics": {
                        "total_deleted": 0,
                        "deleted_images": 0,
                        "deleted_labels": 0,
                    },
                }
            return {
                "success": True,
                "deleted_files": {
                    "orphaned_images": [],
                    "orphaned_labels": [],
                    "invalid_labels": [],
                    "empty_labels": [],
                },
                "statistics": {
                    "total_deleted": 1,
                    "deleted_images": 1,
                    "deleted_labels": 0,
                },
            }

    yes_no_calls: List[Tuple[str, bool]] = []
    yes_no_results = iter([True, False])

    def _fake_yes_no(prompt: str, default: bool) -> bool:
        yes_no_calls.append((prompt, default))
        return next(yes_no_results)

    monkeypatch.setattr(
        "integrated_script.ui.interactive.YoloWorkflow", _WorkflowForCleanFlow
    )
    monkeypatch.setattr(
        interface_with_non_exe,
        "_get_path_input",
        lambda _prompt, must_exist=True: "/tmp/yolo-dataset",
    )
    monkeypatch.setattr(
        interface_with_non_exe, "_get_processor", lambda _name: object()
    )
    monkeypatch.setattr(interface_with_non_exe, "_get_yes_no_input", _fake_yes_no)
    monkeypatch.setattr(
        interface_with_non_exe, "_display_clean_result", lambda _r: None
    )
    monkeypatch.setattr(interface_with_non_exe, "_pause", lambda: None)

    interface_with_non_exe._yolo_clean_unmatched()

    assert len(_WorkflowForCleanFlow.instances) == 1
    workflow = _WorkflowForCleanFlow.instances[0]
    assert workflow.calls == [("/tmp/yolo-dataset", True)]
    assert yes_no_calls == [
        ("\n是否先进行试运行（查看将要删除的文件但不实际删除）？", False),
        ("\n确认要删除这些文件吗？", False),
    ]


def test_yolo_detection_statistics_uses_yes_no_helper_with_expected_defaults(
    interface_with_non_exe, monkeypatch
) -> None:
    class _WorkflowForDetectionFlow:
        instances: List["_WorkflowForDetectionFlow"] = []

        def __init__(self, processor: Any) -> None:
            self.processor = processor
            self.calls: List[Tuple[str, bool]] = []
            _WorkflowForDetectionFlow.instances.append(self)

        def get_dataset_statistics(self, dataset_path: str):
            return {
                "success": True,
                "statistics": {
                    "is_valid": False,
                    "orphaned_images": 1,
                    "orphaned_labels": 0,
                },
            }

        def clean_unmatched_files(self, dataset_path: str, dry_run: bool = False):
            self.calls.append((dataset_path, dry_run))
            return {
                "success": True,
                "deleted_files": {
                    "orphaned_images": ["a.jpg"],
                    "orphaned_labels": [],
                    "invalid_labels": [],
                    "empty_labels": [],
                },
                "statistics": {
                    "total_deleted": 1,
                    "deleted_images": 1,
                    "deleted_labels": 0,
                },
            }

    yes_no_calls: List[Tuple[str, bool]] = []
    yes_no_results = iter([True, True])

    def _fake_yes_no(prompt: str, default: bool) -> bool:
        yes_no_calls.append((prompt, default))
        return next(yes_no_results)

    monkeypatch.setattr(
        "integrated_script.ui.interactive.YoloWorkflow", _WorkflowForDetectionFlow
    )
    monkeypatch.setattr(
        interface_with_non_exe,
        "_get_path_input",
        lambda _prompt, must_exist=True: "/tmp/yolo-dataset",
    )
    monkeypatch.setattr(
        interface_with_non_exe, "_get_processor", lambda _name: object()
    )
    monkeypatch.setattr(interface_with_non_exe, "_get_yes_no_input", _fake_yes_no)
    monkeypatch.setattr(interface_with_non_exe, "_display_result", lambda _r: None)
    monkeypatch.setattr(
        interface_with_non_exe, "_display_clean_result", lambda _r: None
    )
    monkeypatch.setattr(
        interface_with_non_exe, "_display_files_to_delete", lambda _r: None
    )
    monkeypatch.setattr(interface_with_non_exe, "_pause", lambda: None)

    interface_with_non_exe._yolo_detection_statistics()

    assert yes_no_calls == [
        ("是否立即进行自动清理？", True),
        ("\n确认删除这些文件？", True),
    ]


def test_yolo_segmentation_statistics_uses_yes_no_helper_with_expected_defaults(
    interface_with_non_exe, monkeypatch
) -> None:
    class _WorkflowForSegFlow:
        instances: List["_WorkflowForSegFlow"] = []

        def __init__(self, processor: Any) -> None:
            self.processor = processor
            self.calls: List[Tuple[str, bool]] = []
            _WorkflowForSegFlow.instances.append(self)

        def get_dataset_statistics(self, dataset_path: str):
            return {
                "success": True,
                "statistics": {
                    "is_valid": False,
                    "orphaned_images": 1,
                    "orphaned_labels": 0,
                },
            }

        def clean_unmatched_files(self, dataset_path: str, dry_run: bool = False):
            self.calls.append((dataset_path, dry_run))
            return {
                "success": True,
                "deleted_files": {
                    "orphaned_images": ["a.jpg"],
                    "orphaned_labels": [],
                    "invalid_labels": [],
                    "empty_labels": [],
                },
                "statistics": {
                    "total_deleted": 1,
                    "deleted_images": 1,
                    "deleted_labels": 0,
                },
            }

    yes_no_calls: List[Tuple[str, bool]] = []
    yes_no_results = iter([True, True, True])

    def _fake_yes_no(prompt: str, default: bool) -> bool:
        yes_no_calls.append((prompt, default))
        return next(yes_no_results)

    monkeypatch.setattr(
        "integrated_script.ui.interactive.YoloWorkflow", _WorkflowForSegFlow
    )
    monkeypatch.setattr(
        interface_with_non_exe,
        "_get_path_input",
        lambda _prompt, must_exist=True: "/tmp/yolo-dataset",
    )
    monkeypatch.setattr(
        interface_with_non_exe, "_get_processor", lambda _name: object()
    )
    monkeypatch.setattr(interface_with_non_exe, "_get_yes_no_input", _fake_yes_no)
    monkeypatch.setattr(
        interface_with_non_exe,
        "_validate_segmentation_format",
        lambda _path: [(Path("bad.txt"), "格式错误")],
    )
    monkeypatch.setattr(
        interface_with_non_exe,
        "_move_invalid_segmentation_files",
        lambda _path, _files: None,
    )
    monkeypatch.setattr(interface_with_non_exe, "_display_result", lambda _r: None)
    monkeypatch.setattr(
        interface_with_non_exe, "_display_clean_result", lambda _r: None
    )
    monkeypatch.setattr(
        interface_with_non_exe, "_display_files_to_delete", lambda _r: None
    )
    monkeypatch.setattr(interface_with_non_exe, "_pause", lambda: None)

    interface_with_non_exe._yolo_segmentation_statistics()

    assert yes_no_calls == [
        ("\n是否将无效文件移动到上级目录？", True),
        ("是否立即进行自动清理？", True),
        ("\n确认删除这些文件？", True),
    ]


def test_yolo_merge_datasets_uses_yes_no_helper_with_expected_defaults(
    interface_with_non_exe, monkeypatch, tmp_path
) -> None:
    class _WorkflowForMergeConfirm:
        def detect_name_conflicts(self, dataset_paths):
            return {"has_conflict": False, "conflict_count": 0, "examples": []}

        def __init__(self, _processor: Any) -> None:
            pass

        def validate_classes_consistency(self, _dataset_paths: List[Path]):
            return {"consistent": True, "classes": ["cat", "dog"]}

        def generate_output_name(self, classes: List[str], dataset_paths: List[Path]):
            return "merged-cat-dog"

        def merge_datasets(
            self,
            dataset_paths: List[Path],
            output_path: str,
            output_name: Optional[str] = None,
            image_prefix: Optional[str] = None,
        ):
            del dataset_paths, output_path, output_name, image_prefix
            return {
                "success": True,
                "output_path": "/tmp/merged",
                "total_images": 2,
                "total_labels": 2,
                "classes": ["cat", "dog"],
                "merged_datasets": 2,
            }

    d1 = tmp_path / "d1"
    d2 = tmp_path / "d2"
    d1.mkdir()
    d2.mkdir()

    yes_no_calls: List[Tuple[str, bool]] = []
    yes_no_results = iter([False])

    def _fake_yes_no(prompt: str, default: bool) -> bool:
        yes_no_calls.append((prompt, default))
        return next(yes_no_results)

    inputs = iter([str(d1), str(d2), "", "", "", "", ""])

    monkeypatch.setattr(
        "integrated_script.ui.interactive.YoloWorkflow", _WorkflowForMergeConfirm
    )
    monkeypatch.setattr(
        interface_with_non_exe, "_get_processor", lambda _name: object()
    )
    monkeypatch.setattr(interface_with_non_exe, "_get_yes_no_input", _fake_yes_no)
    monkeypatch.setattr(interface_with_non_exe, "_pause", lambda: None)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    interface_with_non_exe._yolo_merge_datasets()

    assert yes_no_calls[-1] == ("\n确认开始合并？", False)


def test_yolo_merge_different_datasets_uses_yes_no_helper_with_expected_defaults(
    interface_with_non_exe, monkeypatch, tmp_path
) -> None:
    class _WorkflowForDiffMergeConfirm:
        def detect_name_conflicts(self, dataset_paths):
            return {"has_conflict": False, "conflict_count": 0, "examples": []}

        def __init__(self, _processor: Any) -> None:
            pass

        def collect_all_classes_info(self, dataset_paths: List[Path]):
            return [
                {"dataset_path": dataset_paths[0], "classes": ["cat"]},
                {"dataset_path": dataset_paths[1], "classes": ["dog"]},
            ]

        def create_unified_class_mapping(self, all_classes_info: List[Dict[str, Any]]):
            del all_classes_info
            return ["cat", "dog"], [{0: 0}, {0: 1}]

        def generate_different_output_name(
            self, unified_classes: List[str], dataset_paths: List[Path]
        ):
            del unified_classes, dataset_paths
            return "merged-diff"

        def merge_different_type_datasets(
            self,
            dataset_paths: List[str],
            output_path: str,
            output_name: Optional[str] = None,
            image_prefix: Optional[str] = None,
            dataset_order: Optional[List[int]] = None,
        ):
            del dataset_paths, output_path, output_name, image_prefix, dataset_order
            return {
                "success": True,
                "output_path": "/tmp/merged-diff",
                "total_images": 2,
                "total_labels": 2,
                "unified_classes": ["cat", "dog"],
                "merged_datasets": 2,
                "statistics": [],
            }

    d1 = tmp_path / "d1"
    d2 = tmp_path / "d2"
    d1.mkdir()
    d2.mkdir()

    yes_no_calls: List[Tuple[str, bool]] = []
    yes_no_results = iter([False, False])

    def _fake_yes_no(prompt: str, default: bool) -> bool:
        yes_no_calls.append((prompt, default))
        return next(yes_no_results)

    inputs = iter([str(d1), str(d2), "", "", "", "", ""])

    monkeypatch.setattr(
        "integrated_script.ui.interactive.YoloWorkflow", _WorkflowForDiffMergeConfirm
    )
    monkeypatch.setattr(
        interface_with_non_exe, "_get_processor", lambda _name: object()
    )
    monkeypatch.setattr(interface_with_non_exe, "_get_yes_no_input", _fake_yes_no)
    monkeypatch.setattr(interface_with_non_exe, "_pause", lambda: None)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    interface_with_non_exe._yolo_merge_different_datasets()

    assert yes_no_calls[0] == ("是否需要调整数据集处理顺序？", False)
    assert yes_no_calls[-1] == ("\n确认开始合并？", False)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('"C:\\data\\set a"', "C:\\data\\set a"),
        ("  'C:/data/set'  ", "C:/data/set"),
        ("C:\\data\\set", "C:\\data\\set"),
        ('"C:\\data\\set', '"C:\\data\\set'),
        ('""', ""),
        ("", ""),
    ],
)
def test_strip_path_quotes(raw: str, expected: str) -> None:
    from integrated_script.ui.interactive import InteractiveInterface

    assert InteractiveInterface._strip_path_quotes(raw) == expected


@pytest.mark.parametrize(
    "method_name", ["_yolo_merge_datasets", "_yolo_merge_different_datasets"]
)
def test_yolo_merge_accepts_quoted_dataset_paths(
    interface_with_non_exe, monkeypatch, tmp_path, capsys, method_name: str
) -> None:
    d1 = tmp_path / "d 1"
    d2 = tmp_path / "d2"
    d1.mkdir()
    d2.mkdir()

    collected: List[List[str]] = []

    class _StopAfterCollect(Exception):
        pass

    class _Workflow:
        def __init__(self, _processor: Any) -> None:
            pass

        def validate_classes_consistency(self, dataset_paths: List[Path]) -> Any:
            collected.append([str(p) for p in dataset_paths])
            raise _StopAfterCollect()

        def collect_all_classes_info(self, dataset_paths: List[Path]) -> Any:
            collected.append([str(p) for p in dataset_paths])
            raise _StopAfterCollect()

    inputs = iter([f'"{d1}"', f"'{d2}'", "", "", "", ""])

    monkeypatch.setattr("integrated_script.ui.interactive.YoloWorkflow", _Workflow)
    monkeypatch.setattr(interface_with_non_exe, "_get_processor", lambda _n: None)
    monkeypatch.setattr(interface_with_non_exe, "_pause", lambda: None)
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))

    getattr(interface_with_non_exe, method_name)()

    assert "路径不存在" not in capsys.readouterr().out
    assert collected == [[str(d1), str(d2)]]
