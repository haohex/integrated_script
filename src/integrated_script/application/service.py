#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""应用服务：单任务后台执行、事件轮询与交互应答。

设计要点（与冻结契约一致）：
- ``start`` 立即返回任务 ID，不阻塞界面；
- 单任务模型，重复 ``start`` 抛出 ``ValueError``；
- 工作线程负责校验、预检与处理，错误转换为 ``OperationResult.failure``；
- 交互（确认/输入）通过 ``InteractionRequest`` 下发，前端轮询后 ``respond``；
- 不支持强杀取消：``close`` 在写入任务运行时会拒绝并保持任务存活。
"""

from __future__ import annotations

import logging
import shutil
import threading
import traceback
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from ..config.settings import ConfigManager
from ..contracts.errors import normalize_exception
from ..contracts.results import OperationResult
from ..core import progress as progress_module
from .catalog import build_operations
from .contracts import (
    InteractionRequest,
    OperationSpec,
    ParameterSpec,
    TaskEvent,
)
from .operations import Operation, TaskContext
from .paths import AppPaths
from .results import normalize_legacy_result
from .values import ValueCoercionError, coerce_values

_TERMINAL_KINDS = {"completed"}


class TaskClosedError(RuntimeError):
    """任务正在写入时被要求关闭。"""


class _WorkerContext(TaskContext):
    """后台线程内的 TaskContext 实现。"""

    def __init__(
        self,
        service: "AppService",
        config: ConfigManager,
        working_directory: Path,
        task_id: str,
        emit,
        wait_for_response,
    ) -> None:
        super().__init__(config, working_directory)
        self._service = service
        self._task_id = task_id
        self._emit = emit
        self._wait_for_response = wait_for_response

    # ---- 日志 / 进度 ---------------------------------------------------
    def log(self, message: str) -> None:
        if message:
            self._emit(TaskEvent(task_id=self._task_id, kind="log", message=message))

    def progress(self, current: int, total: Optional[int], message: str = "") -> None:
        self._emit(
            TaskEvent(
                task_id=self._task_id,
                kind="progress",
                message=message or "",
                current=current,
                total=total,
            )
        )

    # ---- 交互 -----------------------------------------------------------
    def _request(self, request: InteractionRequest) -> Optional[Dict[str, Any]]:
        response, cancelled = self._service._register_and_wait(
            self._task_id, request, self._emit
        )
        if cancelled:
            return None
        return response

    def confirm(
        self,
        title: str,
        message: str,
        *,
        details: Sequence[str] = (),
        default: bool = False,
    ) -> bool:
        request = InteractionRequest(
            id=uuid.uuid4().hex,
            title=title,
            message=message,
            fields=(),
            kind="confirm",
            details=tuple(details),
        )
        response = self._request(request)
        if response is None:
            return False
        return bool(response.get("confirmed", False))

    def ask(
        self,
        title: str,
        message: str,
        fields: Sequence[ParameterSpec],
        *,
        kind: str = "input",
    ) -> Optional[Dict[str, Any]]:
        request = InteractionRequest(
            id=uuid.uuid4().hex,
            title=title,
            message=message,
            fields=tuple(fields),
            kind=kind,
            details=(),
        )
        response = self._request(request)
        if response is None:
            return None
        try:
            return coerce_values(
                request.fields, response, base_dir=self.working_directory
            )
        except ValueCoercionError as exc:
            self.log(f"输入无效: {exc}")
            return None


class _SessionCancelled(Exception):
    """内部信号：本次会话中旧配置导入未被接受，当前操作应安全结束。"""


class _LegacyImportError(Exception):
    """内部信号：旧配置文件存在但无法导入，需要向用户报告可读错误。"""


class AppService:
    """统一应用服务。"""

    def __init__(
        self,
        config: Optional[ConfigManager] = None,
        *,
        working_directory: Optional[Path] = None,
    ):
        self._working_directory = Path(working_directory or Path.cwd())
        self._app_paths = AppPaths.resolve(working_directory=self._working_directory)

        self._legacy_config = self._app_paths.legacy_config_file
        self._legacy_config_pending = False
        self._import_config_path: Optional[Path] = None
        self._session_legacy_prompted = False

        default_config_built = config is None
        if config is None:
            # ConfigManager 构造函数会创建配置目录，因此必须先判断新用户配置是否
            # 已存在。新配置缺失但发现旧配置时，不立刻写入新配置、也不预载旧值，
            # 保持默认值并等待前端确认；load_on_init=False 只建目录不写文件。
            if not self._app_paths.config_file.exists() and (
                self._legacy_config is not None and self._legacy_config.is_file()
            ):
                self._import_config_path = self._legacy_config
                self._legacy_config_pending = True
                config = ConfigManager(
                    config_file=self._app_paths.config_file,
                    auto_save=True,
                    load_on_init=False,
                )
            else:
                config = ConfigManager(
                    config_file=self._app_paths.config_file,
                    auto_save=True,
                )
        self._config = config

        if default_config_built:
            # 默认 AppService 也必须给处理器注入用户 temp/log 路径，不能只在 CLI
            # 引导层注入；否则处理器会在 cwd/安装目录创建 temp/logs。
            self._inject_runtime_paths()

        self._operations: Dict[str, Operation] = {
            operation.id: operation for operation in build_operations()
        }

        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._events: List[TaskEvent] = []
        self._task_id: Optional[str] = None
        self._thread: Optional[threading.Thread] = None

        # 当前待应答交互
        self._pending_request_id: Optional[str] = None
        self._pending_response: Optional[Dict[str, Any]] = None
        self._pending_cancelled = False
        self._waiting_for_response = False

        self._closing = False
        self._writing = False

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------
    def list_operations(self) -> Tuple[OperationSpec, ...]:
        """返回所有可执行操作的公开描述。"""
        return tuple(operation.spec for operation in self._operations.values())

    def start(self, operation_id: str, values: Dict[str, Any]) -> str:
        """启动操作，立即返回任务 ID。"""
        with self._lock:
            if self.busy:
                raise ValueError("已有任务正在运行，无法并发启动新任务")
            operation = self._operations.get(operation_id)
            if operation is None:
                raise ValueError(f"未知操作: {operation_id}")

            task_id = uuid.uuid4().hex
            self._task_id = task_id
            self._events = []
            self._pending_request_id = None
            self._pending_response = None
            self._pending_cancelled = False
            self._waiting_for_response = False
            self._closing = False
            self._writing = False

            thread = threading.Thread(
                target=self._run_task,
                args=(task_id, operation, dict(values or {})),
                name=f"integrated-script-{operation_id}",
                daemon=True,
            )
            self._thread = thread
            self._events.append(
                TaskEvent(
                    task_id=task_id,
                    kind="started",
                    message=operation.spec.label,
                )
            )
            thread.start()
            return task_id

    def poll_events(self) -> List[TaskEvent]:
        """取出并清空当前累积的事件。"""
        with self._lock:
            events = list(self._events)
            self._events.clear()
            return events

    def respond(self, task_id: str, request_id: str, values: Dict[str, Any]) -> None:
        """应答当前交互请求；过期或未知请求会被拒绝。"""
        with self._lock:
            if self._task_id != task_id:
                raise ValueError("应答的任务与当前任务不匹配")
            if self._pending_request_id is None:
                raise ValueError("当前没有等待应答的交互请求")
            if request_id != self._pending_request_id:
                raise ValueError("交互请求已过期或不存在")

            response = dict(values or {})
            self._pending_cancelled = bool(response.get("_cancelled", False))
            self._pending_response = response
            self._pending_request_id = None
            self._waiting_for_response = False
            self._condition.notify_all()

    @property
    def busy(self) -> bool:
        """是否有任务尚未结束。"""
        with self._lock:
            thread = self._thread
            return thread is not None and thread.is_alive()

    @property
    def app_paths(self) -> AppPaths:
        """当前解析出的用户目录与配置文件路径。"""
        return self._app_paths

    def _inject_runtime_paths(self) -> None:
        """把用户可写的 temp/log 目录注入配置（仅当仍是默认相对值时）。

        只在内存中生效，不主动改写用户配置文件；显式绝对路径保持不变。
        """
        paths = self._app_paths
        previous_auto_save = self._config.auto_save
        self._config.auto_save = False
        try:
            if self._config.get("paths.temp_dir") in (None, "", "temp"):
                self._config.set("paths.temp_dir", str(paths.cache_dir / "temp"))
            if self._config.get("paths.log_dir") in (None, "", "logs"):
                self._config.set("paths.log_dir", str(paths.log_dir))
        finally:
            self._config.auto_save = previous_auto_save

    def legacy_config_info(self) -> Optional[Path]:
        """返回可导入的旧配置文件路径，无则返回 None。"""
        if self._legacy_config_pending and self._legacy_config is not None:
            return self._legacy_config
        return None

    def import_legacy_config(self) -> bool:
        """用户确认后把旧配置导入到当前用户配置路径，旧文件保持不变。

        解析失败时抛出可读异常且不写入用户配置；成功则用导入后的值刷新
        当前配置对象，再注入用户可写的 temp/log 路径。
        """
        if not self._legacy_config_pending or self._import_config_path is None:
            return False

        source = self._import_config_path
        self._app_paths.config_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._config.load_from_file(source)
        except Exception as exc:  # noqa: BLE001 - 转为可读错误，不覆盖用户配置
            raise ValueError(f"旧配置文件无法导入: {source} ({exc})") from exc

        shutil.copy2(source, self._app_paths.config_file)
        self._legacy_config_pending = False
        self._import_config_path = None
        self._session_legacy_prompted = True
        self._inject_runtime_paths()
        return True

    def legacy_config_request(self) -> Optional[InteractionRequest]:
        """构造旧配置导入确认请求（不存在则返回 None）。

        兼容保留：前端不再需要预先调用，正常流程由第一次 ``start`` 通过
        worker 的 ``TaskContext.confirm`` 在任务内发起。
        旧文件始终保持不变。
        """
        legacy = self.legacy_config_info()
        if legacy is None:
            return None
        return InteractionRequest(
            id="import-legacy-config",
            title="导入旧配置",
            message=(
                f"检测到已存在的旧配置文件:\n{legacy}\n"
                f"是否导入到用户配置目录 {self._app_paths.config_file}？"
                "原文件不会被修改。"
            ),
            kind="confirm",
        )

    def _maybe_handle_legacy_config(self, context: "_WorkerContext") -> None:
        """首次任务开始时询问是否导入旧配置。

        仅通过现有 worker 交互通道（``confirm``）发起；用户拒绝或关闭时抛出
        ``_SessionCancelled`` 让当前操作安全结束，且不再重复询问。旧文件始终
        不修改；``--config`` 与已存在的用户配置不会进入此分支。
        """
        if not self._legacy_config_pending or self._session_legacy_prompted:
            return

        self._session_legacy_prompted = True
        request = self.legacy_config_request()
        if request is None:
            return

        confirmed = context.confirm(
            request.title,
            request.message,
            details=request.details,
            default=False,
        )
        if not confirmed:
            self._legacy_config_pending = False
            self._import_config_path = None
            raise _SessionCancelled()

        try:
            self.import_legacy_config()
        except ValueError as exc:
            self._legacy_config_pending = False
            self._import_config_path = None
            raise _LegacyImportError(str(exc)) from exc

    @property
    def waiting_for_response(self) -> bool:
        """工作线程是否正在等待交互应答。"""
        with self._lock:
            return self._waiting_for_response

    def close(self) -> None:
        """请求关闭服务。

        如果没有任务在运行，立即返回；如果任务正在等待交互，则取消该交互让
        处理安全结束；如果任务正在执行写入，拒绝关闭以避免留下半成品。
        """
        with self._lock:
            thread = self._thread
            if thread is None or not thread.is_alive():
                self._closing = True
                return

            if self._waiting_for_response:
                self._closing = True
                self._pending_cancelled = True
                self._pending_response = {"_cancelled": True}
                self._pending_request_id = None
                self._waiting_for_response = False
                self._condition.notify_all()
                return

            if self._writing:
                raise TaskClosedError("任务正在写入，无法关闭；请等待处理完成")

            self._closing = True
            self._pending_cancelled = True
            self._condition.notify_all()

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------
    def _emit_event(self, event: TaskEvent) -> None:
        with self._lock:
            self._events.append(event)

    def _wait_for_response(
        self, request_id: str
    ) -> Tuple[Optional[Dict[str, Any]], bool]:
        with self._condition:
            self._pending_request_id = request_id
            self._pending_response = None
            self._pending_cancelled = False
            self._waiting_for_response = True
            self._condition.notify_all()

            while self._pending_response is None:
                if self._closing:
                    self._waiting_for_response = False
                    return None, True
                self._condition.wait(timeout=0.2)

            response = self._pending_response
            self._pending_response = None
            self._waiting_for_response = False
            return response, self._pending_cancelled

    def _register_and_wait(
        self,
        task_id: str,
        request: InteractionRequest,
        emit,
    ) -> Tuple[Optional[Dict[str, Any]], bool]:
        """先登记待应答请求再发事件，避免前端应答竞态。"""
        with self._condition:
            self._pending_request_id = request.id
            self._pending_response = None
            self._pending_cancelled = False
            self._waiting_for_response = True

        emit(
            TaskEvent(
                task_id=task_id,
                kind="interaction",
                message=request.message,
                interaction=request,
            )
        )

        with self._condition:
            while self._pending_response is None:
                if self._closing:
                    self._waiting_for_response = False
                    return None, True
                self._condition.wait(timeout=0.2)

            response = self._pending_response
            self._pending_response = None
            self._waiting_for_response = False
            return response, self._pending_cancelled

    def _run_task(
        self, task_id: str, operation: Operation, raw_values: Dict[str, Any]
    ) -> None:
        sink_token = _SinkToken()
        log_handler = _EventLogHandler()
        result: Optional[OperationResult] = None

        with (
            progress_module.progress_sink(sink_token),
            _route_logs_to_events(log_handler),
        ):
            try:
                values = coerce_values(
                    operation.fields, raw_values, base_dir=self._working_directory
                )
                context = _WorkerContext(
                    self,
                    self._config,
                    self._working_directory,
                    task_id,
                    self._emit_event,
                    self._wait_for_response,
                )
                sink_token.bind(context)
                log_handler.bind(context)

                self._maybe_handle_legacy_config(context)

                with self._lock:
                    self._writing = True
                legacy = operation.handler(context, values)
                if isinstance(legacy, OperationResult):
                    result = legacy
                else:
                    result = OperationResult.from_legacy(
                        normalize_legacy_result(legacy)
                    )
            except _SessionCancelled:
                result = OperationResult.from_legacy(
                    normalize_legacy_result(
                        {
                            "success": True,
                            "cancelled": True,
                            "stage": "cancelled",
                            "message": (
                                "已跳过旧配置导入，本次操作已取消；"
                                "后续将使用默认配置。原配置文件未被修改。"
                            ),
                        }
                    )
                )
            except _LegacyImportError as exc:
                result = OperationResult.failure(
                    message=str(exc),
                    error_code="LEGACY_CONFIG_INVALID",
                    payload={"reason": "legacy_config"},
                )
            except ValueCoercionError as exc:
                result = OperationResult.failure(
                    str(exc), error_code="VALIDATION_ERROR"
                )
            except Exception as exc:  # noqa: BLE001
                normalized = normalize_exception(exc)
                result = OperationResult.failure(
                    message=normalized.message,
                    error_code=normalized.code,
                    payload={
                        "error_details": normalized.details,
                        "traceback": traceback.format_exc(),
                    },
                )
            finally:
                with self._lock:
                    self._writing = False

        with self._lock:
            self._events.append(
                TaskEvent(task_id=task_id, kind="completed", result=result)
            )
            self._condition.notify_all()


class _EventLogHandler(logging.Handler):
    """把处理器日志转发为 ``TaskEvent(kind='log')`` 的日志处理器。

    工作线程启动后、上下文就绪前的日志会被丢弃（与进度一样属于增量信息）。
    """

    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        self._context: Optional[_WorkerContext] = None
        self._lock = threading.Lock()

    def bind(self, context: _WorkerContext) -> None:
        with self._lock:
            self._context = context

    def emit(self, record: logging.LogRecord) -> None:
        with self._lock:
            context = self._context
        if context is None:
            return
        try:
            message = record.getMessage()
            if record.exc_info:
                message = f"{message}\n{self.format(record)}"
            context.log(f"[{record.levelname}] {message}")
        except Exception:  # noqa: BLE001 - 日志失败不能影响处理
            pass


@contextmanager
def _route_logs_to_events(handler: _EventLogHandler) -> Iterator[None]:
    """任务执行期间将 root logger 日志接入事件，并静音控制台输出。

    只临时调整 root logger 上的控制台 StreamHandler 级别，文件处理器与
    legacy 控制台（非 AppService 路径）不受影响；不替换 ``sys.stdout``。
    """
    root_logger = logging.getLogger()
    muted: List[Tuple[logging.Handler, int]] = []
    for h in list(root_logger.handlers):
        if isinstance(h, logging.StreamHandler) and not isinstance(
            h, logging.FileHandler
        ):
            muted.append((h, h.level))
            h.setLevel(logging.CRITICAL + 1)
    root_logger.addHandler(handler)
    try:
        yield
    finally:
        root_logger.removeHandler(handler)
        for h, level in muted:
            h.setLevel(level)


class _SinkToken:
    """可延迟绑定上下文的进度接收器令牌。

    工作线程创建后、上下文就绪前可能已有进度事件，这里先缓冲再转发。
    简单起见，绑定前的事件直接丢弃（进度是增量信息，不影响结果）。
    """

    def __init__(self) -> None:
        self._context: Optional[_WorkerContext] = None
        self._lock = threading.Lock()

    def bind(self, context: _WorkerContext) -> None:
        with self._lock:
            self._context = context

    def progress_started(self, description: str, total: int, unit: str) -> None:
        self._forward("progress_started", description, total, unit)

    def progress_updated(self, current: int, total: int, description: str = "") -> None:
        self._forward("progress_updated", current, total, description)

    def progress_closed(self, current: int, total: int) -> None:
        self._forward("progress_closed", current, total)

    def progress_postfix(self, values: Dict[str, Any]) -> None:
        self._forward("progress_postfix", values)

    def _forward(self, method: str, *args: Any) -> None:
        with self._lock:
            context = self._context
        if context is None:
            return
        handler = getattr(context, method, None)
        if handler is None:
            return
        try:
            handler(*args)
        except Exception:  # noqa: BLE001 - 进度失败不能影响处理
            pass


__all__ = ["AppService", "TaskClosedError"]
