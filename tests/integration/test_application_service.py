#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AppService 端到端集成测试：真实临时 CTDS 数据集、交互应答与事件。

使用临时 XDG 目录隔离用户配置/日志/缓存，测试不进入真实 TUI。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable, Dict, List, Sequence, Tuple

import pytest

from integrated_script.application import AppService
from integrated_script.config.settings import ConfigManager
from integrated_script.contracts.results import OperationResult


@pytest.fixture
def xdg_env(monkeypatch, tmp_path: Path):
    """把用户目录指向临时目录，避免污染真实环境。"""
    for var, sub in (
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_STATE_HOME", "state"),
        ("XDG_CACHE_HOME", "cache"),
        ("XDG_DATA_HOME", "data"),
    ):
        monkeypatch.setenv(var, str(tmp_path / var.lower()))
    return tmp_path


def _run_task(
    service: AppService,
    operation_id: str,
    values: Dict[str, object],
    responses: Sequence[Callable[[object], Dict[str, object]]] = (),
    timeout: float = 90.0,
) -> Tuple[OperationResult, List[str]]:
    """驱动一次任务直到完成，自动应答交互请求。"""
    result, log_lines, _ = _run_task_with_interactions(
        service, operation_id, values, responses, timeout
    )
    return result, log_lines


def _run_task_with_interactions(
    service: AppService,
    operation_id: str,
    values: Dict[str, object],
    responses: Sequence[Callable[[object], Dict[str, object]]] = (),
    timeout: float = 90.0,
) -> Tuple[OperationResult, List[str], List[object]]:
    """驱动一次任务直到完成，返回结果、日志和收到的交互请求列表。"""
    task_id = service.start(operation_id, values)
    log_lines: List[str] = []
    interactions: List[object] = []
    response_index = 0
    deadline = time.time() + timeout

    while time.time() < deadline:
        for event in service.poll_events():
            if event.kind == "log":
                log_lines.append(event.message)
            elif event.kind == "interaction":
                request = event.interaction
                assert request is not None
                interactions.append(request)
                if response_index < len(responses):
                    response = responses[response_index](request)
                else:
                    response = {"_cancelled": True}
                response_index += 1
                service.respond(task_id, request.id, response)
            elif event.kind == "completed":
                assert event.result is not None
                return event.result, log_lines, interactions
        time.sleep(0.02)

    raise AssertionError("任务在超时前未完成")


def _write_ctds_dataset(root: Path, names: str = "cat\ndog\n") -> Path:
    """创建真实的小型 CTDS 数据集（obj.names + obj_train_data）。"""
    from PIL import Image

    dataset = root / "ctds"
    train_data = dataset / "obj_train_data"
    train_data.mkdir(parents=True)
    (dataset / "obj.names").write_text(names, encoding="utf-8")

    for index in (1, 2):
        (train_data / f"{index}.txt").write_text(
            "0 0.5 0.5 0.2 0.2\n", encoding="utf-8"
        )
        Image.new("RGB", (24, 24), color=(index * 40, 10, 10)).save(
            train_data / f"{index}.jpg"
        )

    return dataset


def _build_service(working_directory: Path) -> AppService:
    return AppService(working_directory=working_directory)


def test_real_ctds_conversion_and_detection_validation_pass(
    xdg_env, tmp_path: Path
) -> None:
    """真实 CTDS 转换后，validate_detection(auto_clean=False) 必须成功。"""
    working = tmp_path / "work"
    working.mkdir()
    dataset = _write_ctds_dataset(working)

    service = _build_service(working)
    try:
        conversion, _ = _run_task(
            service,
            "yolo.ctds_to_yolo",
            {"dataset_path": str(dataset)},
            responses=(
                lambda _request: {"confirmed": True},
                lambda _request: {"dataset_type": "detection"},
            ),
        )
        assert conversion.success is True, conversion.to_legacy()
        output_path = conversion.payload["output_path"]
        assert Path(output_path, "images").is_dir()
        assert Path(output_path, "labels").is_dir()

        validation, log_lines = _run_task(
            service,
            "yolo.validate_detection",
            {"dataset_path": output_path, "auto_clean": False},
        )
    finally:
        service.close()

    assert validation.success is True, validation.to_legacy()
    assert validation.payload["statistics"]["is_valid"] is True
    assert validation.payload["statistics"]["orphaned_images"] == 0
    assert any(event.startswith("[INFO]") for event in log_lines)


def test_real_ctds_conversion_denied_cleanup_preserves_orphan(
    xdg_env, tmp_path: Path
) -> None:
    """拒绝清理时保留孤立文件，且验证结果仍报告问题。"""
    working = tmp_path / "work"
    working.mkdir()
    dataset = _write_ctds_dataset(working)

    service = _build_service(working)
    try:
        conversion, _ = _run_task(
            service,
            "yolo.ctds_to_yolo",
            {"dataset_path": str(dataset)},
            responses=(
                lambda _request: {"confirmed": True},
                lambda _request: {"dataset_type": "detection"},
            ),
        )
        output_path = Path(conversion.payload["output_path"])

        orphan = output_path / "images" / "orphan-99999.jpg"
        orphan.write_bytes((output_path / "images" / "cat-dog-00001.jpg").read_bytes())

        validation, _ = _run_task(
            service,
            "yolo.validate_detection",
            {"dataset_path": str(output_path), "auto_clean": True},
            responses=(lambda _request: {"confirmed": False},),
        )
    finally:
        service.close()

    assert validation.success is False
    assert validation.payload["statistics"]["orphaned_images"] == 1
    assert validation.payload["clean_result"]["cancelled"] is True
    assert orphan.exists(), "拒绝清理后孤立文件必须保留"


def test_real_segmentation_validation_succeeds(xdg_env, tmp_path: Path) -> None:
    """真实分割数据集（>=7 列标签）验证成功。"""
    working = tmp_path / "work"
    dataset = working / "seg"
    (dataset / "images").mkdir(parents=True)
    (dataset / "labels").mkdir(parents=True)
    (dataset / "classes.txt").write_text("cat\n", encoding="utf-8")

    from PIL import Image

    for name in ("a", "b"):
        Image.new("RGB", (16, 16)).save(dataset / "images" / f"{name}.jpg")
        (dataset / "labels" / f"{name}.txt").write_text(
            "0 0.1 0.1 0.9 0.1 0.9 0.9 0.1 0.9\n", encoding="utf-8"
        )

    service = _build_service(working)
    try:
        result, _ = _run_task(
            service,
            "yolo.validate_segmentation",
            {
                "dataset_path": str(dataset),
                "move_invalid": False,
                "auto_clean": False,
            },
        )
    finally:
        service.close()

    assert result.success is True, result.to_legacy()
    assert result.payload["statistics"]["is_valid"] is True
    assert result.payload["invalid_segmentation_files"] == []


def test_real_segmentation_validation_flags_bad_label(xdg_env, tmp_path: Path) -> None:
    """真实分割数据集中列数不足的标签被标记，不移动时保留原文件。"""
    working = tmp_path / "work"
    dataset = working / "seg"
    (dataset / "images").mkdir(parents=True)
    (dataset / "labels").mkdir(parents=True)
    (dataset / "classes.txt").write_text("cat\n", encoding="utf-8")

    from PIL import Image

    Image.new("RGB", (16, 16)).save(dataset / "images" / "a.jpg")
    Image.new("RGB", (16, 16)).save(dataset / "images" / "b.jpg")
    (dataset / "labels" / "a.txt").write_text(
        "0 0.1 0.1 0.9 0.1 0.9 0.9 0.1 0.9\n", encoding="utf-8"
    )
    bad_label = dataset / "labels" / "b.txt"
    bad_label.write_text("0 0.1 0.1 0.9\n", encoding="utf-8")

    service = _build_service(working)
    try:
        result, _ = _run_task(
            service,
            "yolo.validate_segmentation",
            {
                "dataset_path": str(dataset),
                "move_invalid": False,
                "auto_clean": False,
            },
        )
    finally:
        service.close()

    assert result.payload["invalid_segmentation_files"]
    assert any(
        "b.txt" in item["file"] for item in result.payload["invalid_segmentation_files"]
    )
    assert bad_label.exists(), "未确认移动时无效标签必须保留"


def test_real_ctds_to_yolo_conversion_is_rejected_by_default(
    xdg_env, tmp_path: Path
) -> None:
    """默认应答（无响应）应视为取消，不执行写入。"""
    working = tmp_path / "work"
    working.mkdir()
    dataset = _write_ctds_dataset(working)

    service = _build_service(working)
    try:
        result, _ = _run_task(
            service,
            "yolo.ctds_to_yolo",
            {"dataset_path": str(dataset)},
        )
    finally:
        service.close()

    assert result.success is True
    assert result.payload.get("cancelled") is True
    assert not (working / "cat-dog-00002").exists()


def _write_extensionless_dir(root: Path, names: str = ("alpha", "beta")) -> Path:
    work = root / "work"
    work.mkdir(parents=True, exist_ok=True)
    for name in names:
        (work / name).write_text("x", encoding="utf-8")
    return work


def test_rename_single_dir_no_suffix_prompts_and_renames(
    xdg_env, tmp_path: Path
) -> None:
    """通过公共 start/poll/respond：无后缀→询问→输入后缀→确认→重命名。"""
    work = _write_extensionless_dir(tmp_path)
    service = _build_service(work)
    try:
        result, _, interactions = _run_task_with_interactions(
            service,
            "file.rename_single_dir",
            {
                "source_dir": str(work),
                "prefix": "",
                "digits": 2,
                "suffix": "",
                "shuffle_order": False,
            },
            responses=(
                lambda _request: {"suffix": ".dat"},
                lambda _request: {"confirmed": True},
            ),
        )
    finally:
        service.close()

    kinds = [request.kind for request in interactions]
    assert kinds == ["input", "confirm"], interactions
    input_request = interactions[0]
    assert input_request.fields[0].name == "suffix"
    assert input_request.fields[0].required is True
    assert result.success is True, result.to_legacy()
    assert sorted(path.name for path in work.iterdir()) == ["01.dat", "02.dat"]


def test_rename_single_dir_no_suffix_dismissed_writes_nothing(
    xdg_env, tmp_path: Path
) -> None:
    """用户关闭后缀输入（_cancelled）时取消操作，不改动任何文件。"""
    work = _write_extensionless_dir(tmp_path)
    service = _build_service(work)
    try:
        result, _, interactions = _run_task_with_interactions(
            service,
            "file.rename_single_dir",
            {
                "source_dir": str(work),
                "prefix": "",
                "digits": 2,
                "suffix": "",
                "shuffle_order": False,
            },
            responses=(lambda _request: {"_cancelled": True},),
        )
    finally:
        service.close()

    assert [request.kind for request in interactions] == ["input"]
    assert result.success is True, result.to_legacy()
    assert result.payload.get("cancelled") is True
    assert sorted(path.name for path in work.iterdir()) == ["alpha", "beta"]


def test_rename_single_dir_existing_suffixes_skip_prompt(
    xdg_env, tmp_path: Path
) -> None:
    """混合已存在后缀时沿用旧字典序选择，不下发后缀输入交互。"""
    work = tmp_path / "work"
    work.mkdir()
    for name in ("a.png", "b.jpg"):
        (work / name).write_text("x", encoding="utf-8")

    service = _build_service(work)
    try:
        result, _, interactions = _run_task_with_interactions(
            service,
            "file.rename_single_dir",
            {
                "source_dir": str(work),
                "prefix": "",
                "digits": 2,
                "suffix": "",
                "shuffle_order": False,
            },
            responses=(lambda _request: {"confirmed": True},),
        )
    finally:
        service.close()

    assert [request.kind for request in interactions] == ["confirm"], interactions
    assert result.success is True, result.to_legacy()
    assert sorted(path.name for path in work.iterdir()) == ["01.jpg", "02.jpg"]


def test_legacy_config_prompts_import_without_creating_user_config(
    xdg_env, tmp_path: Path, monkeypatch
) -> None:
    """新用户配置缺失 + cwd 旧配置存在：必须在创建新配置前提示导入。"""
    working = tmp_path / "cwd"
    working.mkdir()
    legacy_data = {"version": "1.0.0", "processing": {"batch_size": 42}}
    legacy_file = working / "config.json"
    legacy_file.write_text(json.dumps(legacy_data), encoding="utf-8")

    service = AppService(working_directory=working)
    try:
        assert service.legacy_config_info() == legacy_file
        request = service.legacy_config_request()
        assert request is not None
        assert request.kind == "confirm"
        assert str(legacy_file) in request.message

        assert not service.app_paths.config_file.exists()

        assert service.import_legacy_config() is True
        assert service.app_paths.config_file.exists()
        assert service._config.get("processing.batch_size") == 42
        assert legacy_file.read_text(encoding="utf-8") == json.dumps(legacy_data)
        # 导入后仍需把用户 temp/log 路径注入配置
        assert Path(str(service._config.get("paths.temp_dir"))).is_absolute()
        assert Path(str(service._config.get("paths.log_dir"))).is_absolute()
    finally:
        service.close()


def test_legacy_config_rejection_keeps_defaults_without_writing(
    xdg_env, tmp_path: Path
) -> None:
    working = tmp_path / "cwd"
    working.mkdir()
    (working / "config.json").write_text(
        json.dumps({"version": "1.0.0", "processing": {"batch_size": 7}}),
        encoding="utf-8",
    )

    service = AppService(working_directory=working)
    try:
        assert service.legacy_config_info() is not None
        # 用户拒绝导入：前端不调用 import_legacy_config；新文件不写，旧文件不改。
        assert not service.app_paths.config_file.exists()
        assert (working / "config.json").exists()
        # 未导入时使用默认值，而不是旧配置的 batch_size=7
        assert service._config.get("processing.batch_size") == 100
    finally:
        service.close()


def test_legacy_import_prompted_via_public_start_and_imports(
    xdg_env, tmp_path: Path
) -> None:
    """冻结前端只调用 start/poll_events/respond 也能看到导入提示并完成导入。"""
    working = tmp_path / "cwd"
    working.mkdir()
    legacy_data = {"version": "1.0.0", "processing": {"batch_size": 42}}
    legacy_file = working / "config.json"
    legacy_file.write_text(json.dumps(legacy_data), encoding="utf-8")

    service = AppService(working_directory=working)
    try:
        assert not service.app_paths.config_file.exists()

        result, _, interactions = _run_task_with_interactions(
            service,
            "config.view",
            {},
            responses=(lambda _request: {"confirmed": True},),
        )

        # 任务内必须先下发一次导入确认交互，且不依赖 legacy_config_request。
        assert len(interactions) == 1
        request = interactions[0]
        assert request.kind == "confirm"
        assert str(legacy_file) in request.message

        assert result.success is True, result.to_legacy()
        assert service.app_paths.config_file.exists()
        assert service._config.get("processing.batch_size") == 42
        assert result.payload["config"]["processing"]["batch_size"] == 42
        assert legacy_file.read_text(encoding="utf-8") == json.dumps(legacy_data)

        # 已导入后再次执行不再重复询问。
        second, _, second_interactions = _run_task_with_interactions(
            service, "config.view", {}, responses=()
        )
        assert second_interactions == []
        assert second.success is True
    finally:
        service.close()


def test_legacy_import_rejection_cancels_operation_safely(
    xdg_env, tmp_path: Path
) -> None:
    """拒绝导入：当前操作安全取消、使用默认配置、原文件不变、不再重复询问。"""
    working = tmp_path / "cwd"
    working.mkdir()
    legacy_file = working / "config.json"
    legacy_file.write_text(
        json.dumps({"version": "1.0.0", "processing": {"batch_size": 7}}),
        encoding="utf-8",
    )

    service = AppService(working_directory=working)
    try:
        result, _, interactions = _run_task_with_interactions(
            service,
            "config.view",
            {},
            responses=(lambda _request: {"confirmed": False},),
        )

        assert len(interactions) == 1
        assert result.success is True, result.to_legacy()
        assert result.payload.get("cancelled") is True
        assert result.message, "取消必须带可读说明"
        assert not service.app_paths.config_file.exists()
        assert service._config.get("processing.batch_size") == 100
        assert legacy_file.exists()

        # 同一会话内再次执行：不重复询问，直接使用默认配置执行。
        second, _, second_interactions = _run_task_with_interactions(
            service, "config.view", {}, responses=()
        )
        assert second_interactions == []
        assert second.success is True
        assert second.payload.get("cancelled") is not True
    finally:
        service.close()


def test_legacy_import_close_response_cancels_operation(
    xdg_env, tmp_path: Path
) -> None:
    """关闭对话框（_cancelled）等同于拒绝，安全结束且不写用户配置。"""
    working = tmp_path / "cwd"
    working.mkdir()
    (working / "config.json").write_text(
        json.dumps({"version": "1.0.0", "processing": {"batch_size": 9}}),
        encoding="utf-8",
    )

    service = AppService(working_directory=working)
    try:
        result, _, interactions = _run_task_with_interactions(
            service, "config.view", {}, responses=()
        )
        assert len(interactions) == 1
        assert result.success is True
        assert result.payload.get("cancelled") is True
        assert not service.app_paths.config_file.exists()
    finally:
        service.close()


def test_legacy_import_invalid_file_reports_readable_error(
    xdg_env, tmp_path: Path
) -> None:
    """确认导入但旧文件无效：报可读错误，不覆盖用户配置，也不静默成功。"""
    working = tmp_path / "cwd"
    working.mkdir()
    legacy_file = working / "config.json"
    legacy_file.write_text("{ this is not valid json", encoding="utf-8")

    service = AppService(working_directory=working)
    try:
        result, _, interactions = _run_task_with_interactions(
            service,
            "config.view",
            {},
            responses=(lambda _request: {"confirmed": True},),
        )

        assert len(interactions) == 1
        assert result.success is False, result.to_legacy()
        assert result.error_code == "LEGACY_CONFIG_INVALID"
        assert str(legacy_file) in result.message
        assert not service.app_paths.config_file.exists()
        assert legacy_file.read_text(encoding="utf-8") == "{ this is not valid json"

        # 无效旧配置已清除待处理状态：后续不再询问，使用默认配置。
        second, _, second_interactions = _run_task_with_interactions(
            service, "config.view", {}, responses=()
        )
        assert second_interactions == []
        assert second.success is True
    finally:
        service.close()


def test_explicit_config_does_not_trigger_legacy_import(
    xdg_env, tmp_path: Path
) -> None:
    working = tmp_path / "cwd"
    working.mkdir()
    (working / "config.json").write_text("{}", encoding="utf-8")
    explicit = tmp_path / "explicit.json"
    explicit.write_text(json.dumps({"version": "1.0.0"}), encoding="utf-8")

    from integrated_script.application.paths import AppPaths

    paths = AppPaths.resolve(explicit_config=explicit, working_directory=working)
    assert paths.legacy_config_file is None
    assert paths.has_legacy_config is False

    config = ConfigManager(config_file=explicit, auto_save=False)
    service = AppService(config=config, working_directory=working)
    try:
        assert service.legacy_config_info() is None
        assert service.legacy_config_request() is None
    finally:
        service.close()


def test_default_service_injects_user_runtime_paths(xdg_env, tmp_path: Path) -> None:
    working = tmp_path / "cwd"
    working.mkdir()

    service = AppService(working_directory=working)
    try:
        temp_dir = str(service._config.get("paths.temp_dir"))
        log_dir = str(service._config.get("paths.log_dir"))
        assert Path(temp_dir).is_absolute()
        assert Path(log_dir).is_absolute()
        assert str(tmp_path / "xdg_cache_home") in temp_dir
        assert str(tmp_path / "xdg_state_home") in log_dir
    finally:
        service.close()


def test_processor_logger_output_becomes_log_events_not_stdout(
    xdg_env, tmp_path: Path, capsys
) -> None:
    """主代理观察到 processor INFO 泄漏到 stdout；应转为 log 事件。"""
    working = tmp_path / "work"
    working.mkdir()
    dataset = working / "dataset"
    (dataset / "images").mkdir(parents=True)
    (dataset / "labels").mkdir(parents=True)
    (dataset / "images" / "a.jpg").write_bytes(b"img")
    (dataset / "labels" / "a.txt").write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")

    service = _build_service(working)
    try:
        result, log_lines = _run_task(
            service,
            "yolo.validate_detection",
            {"dataset_path": str(dataset), "auto_clean": False},
        )
    finally:
        service.close()

    captured = capsys.readouterr()
    assert result.success is True
    # 事件里必须包含处理器日志
    assert any("YOLO" in line or "统计" in line for line in log_lines)
    # stdout 中不得出现处理器 logger 的时间戳格式
    assert " - INFO - " not in captured.out


def _cold_start_env(tmp_path: Path) -> Dict[str, str]:
    """构造指向可写用户目录、无 cwd 写入的冷启动环境变量。"""
    import os

    base = tmp_path / "cold"
    env = dict(os.environ)
    env.update(
        {
            "HOME": str(base / "home"),
            "XDG_CONFIG_HOME": str(base / "config"),
            "XDG_STATE_HOME": str(base / "state"),
            "XDG_CACHE_HOME": str(base / "cache"),
            "XDG_DATA_HOME": str(base / "data"),
            "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src"),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    for sub in ("home", "config", "state", "cache", "data"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    return env


def test_cold_start_import_and_version_without_cwd_write(tmp_path: Path) -> None:
    """新解释器 + 只读 cwd：import 与 --version 不得在 cwd 创建 logs。"""
    import os
    import subprocess
    import sys

    readonly_cwd = Path("/proc")
    if not readonly_cwd.is_dir() or os.access(readonly_cwd, os.W_OK):
        pytest.skip("需要一个不可写的 cwd（本机 /proc 可写或不存在）")

    env = _cold_start_env(tmp_path)
    src_root = Path(__file__).resolve().parents[2] / "src"

    def run(args: Sequence[str]) -> str:
        completed = subprocess.run(
            [sys.executable, *args],
            cwd=str(readonly_cwd),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert completed.returncode == 0, completed.stderr
        return completed.stdout

    import_out = run(
        ["-c", "import integrated_script; print(integrated_script.__version__)"]
    )
    assert import_out.strip(), "import 未输出内容"

    version_out = run(["-m", "integrated_script.main", "--version"])
    assert import_out.strip() in version_out, version_out

    # 只读 cwd 下若代码试图写 cwd/logs 会直接报错；另外确认日志落在用户目录。
    assert not (readonly_cwd / "logs").exists()
    state_logs = Path(env["XDG_STATE_HOME"]) / "integrated_script" / "log"
    assert state_logs.is_dir(), "日志应写入用户可写目录"
    assert list(state_logs.glob("*.log")), "用户日志目录应出现日志文件"
    assert not (src_root / "logs").exists(), "不得在源码/cwd 创建 logs"
