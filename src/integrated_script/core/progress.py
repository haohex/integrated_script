#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
progress.py

进度管理模块

提供进度条显示、进度跟踪和上下文管理功能。
"""

import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator, List, Optional

from .logging_config import get_logger

try:
    from tqdm import tqdm as _tqdm

    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

    # 简单的进度显示替代
    class _FallbackTqdm:
        def __init__(self, iterable=None, total=None, desc=None, **kwargs):
            self.iterable = iterable
            self.total = total or (len(iterable) if iterable else 0)
            self.desc = desc or ""
            self.current = 0
            self.start_time = time.time()

        def __iter__(self):
            if self.iterable:
                for item in self.iterable:
                    yield item
                    self.update(1)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

        def update(self, n=1):
            self.current += n
            if self.total > 0:
                percent = (self.current / self.total) * 100
                elapsed = time.time() - self.start_time
                if self.current > 0:
                    eta = (elapsed / self.current) * (self.total - self.current)
                    print(
                        f"\r{self.desc}: {percent:.1f}% ({self.current}/{self.total}) ETA: {eta:.1f}s",
                        end="",
                    )

        def set_description(self, desc):
            self.desc = desc

        def close(self):
            if self.total > 0:
                print(f"\r{self.desc}: 100% ({self.total}/{self.total}) 完成")
            else:
                print(f"\r{self.desc}: 完成 ({self.current} 项)")

    _tqdm = _FallbackTqdm

# 兼容测试中 monkeypatch("integrated_script.core.progress.tqdm", ...)
tqdm = _tqdm

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 进度事件接收器（progress sink）
#
# 应用层（GUI/TUI）在后台线程执行操作时注册 sink，core 层的进度不再写入终端，
# 而是转换为结构化事件；未注册 sink 时保持原有终端 tqdm 行为完全不变。
# 这里不做全局 stdout 重定向，只提供显式注册点。
# ---------------------------------------------------------------------------

_sink_lock = threading.RLock()
_active_sink: Optional[Any] = None


def set_progress_sink(sink: Optional[Any]) -> None:
    """注册当前活动进度接收器（None 表示恢复终端进度）。"""
    global _active_sink
    with _sink_lock:
        _active_sink = sink


def get_progress_sink() -> Optional[Any]:
    """返回当前活动进度接收器，未注册时返回 None。"""
    with _sink_lock:
        return _active_sink


@contextmanager
def progress_sink(sink: Optional[Any]) -> Iterator[Optional[Any]]:
    """在上下文中临时注册进度接收器，退出时恢复之前的接收器。"""
    global _active_sink
    with _sink_lock:
        previous = _active_sink
        _active_sink = sink
    try:
        yield sink
    finally:
        with _sink_lock:
            _active_sink = previous


def _notify_sink(sink: Optional[Any], method: str, *args: Any) -> None:
    """安全地向 sink 派发事件，接收器异常不得影响处理流程。"""
    if sink is None:
        return
    handler = getattr(sink, method, None)
    if handler is None:
        return
    try:
        handler(*args)
    except Exception as exc:  # pragma: no cover - 接收器问题不应中断处理
        logger.debug("进度接收器 %s 调用失败: %s", method, exc)


class _SinkBar:
    """将 tqdm 风格进度条调用转发给 sink 的轻量对象。"""

    def __init__(
        self,
        sink: Any,
        total: Optional[int] = None,
        description: str = "",
        unit: str = "item",
    ) -> None:
        self._sink = sink
        self.total = total or 0
        self.n = 0
        self.description = description
        self.unit = unit
        _notify_sink(sink, "progress_started", description, self.total, unit)

    def update(self, n: int = 1) -> None:
        self.n += n
        _notify_sink(
            self._sink, "progress_updated", self.n, self.total, self.description
        )

    def set_description(self, description: Optional[str] = None, refresh: bool = True):
        _ = refresh
        self.description = description or ""
        _notify_sink(
            self._sink, "progress_updated", self.n, self.total, self.description
        )

    def set_postfix(
        self, ordered_dict: Optional[dict] = None, refresh: bool = True, **kwargs: Any
    ) -> None:
        _ = refresh
        values = dict(ordered_dict or {})
        values.update(kwargs)
        _notify_sink(self._sink, "progress_postfix", values)

    def close(self) -> None:
        _notify_sink(self._sink, "progress_closed", self.n, self.total)

    def __enter__(self) -> "_SinkBar":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class _SinkIterable:
    """将可迭代对象的逐项进度转发给 sink，替代直接实例化 tqdm 的场景。"""

    def __init__(
        self,
        sink: Any,
        iterable: Any,
        total: Optional[int] = None,
        description: str = "",
        unit: str = "item",
    ) -> None:
        self._sink = sink
        self._iterable = iterable
        self.total = total if total is not None else _safe_len(iterable)
        self.n = 0
        self.description = description
        self.unit = unit

    def __iter__(self) -> Iterator[Any]:
        _notify_sink(
            self._sink, "progress_started", self.description, self.total, self.unit
        )
        for item in self._iterable:
            yield item
            self.n += 1
            _notify_sink(
                self._sink, "progress_updated", self.n, self.total, self.description
            )
        _notify_sink(self._sink, "progress_closed", self.n, self.total)

    def update(self, n: int = 1) -> None:
        self.n += n
        _notify_sink(
            self._sink, "progress_updated", self.n, self.total, self.description
        )

    def set_description(self, description: Optional[str] = None, refresh: bool = True):
        _ = refresh
        self.description = description or ""

    def set_postfix(
        self, ordered_dict: Optional[dict] = None, refresh: bool = True, **kwargs: Any
    ) -> None:
        _ = refresh
        values = dict(ordered_dict or {})
        values.update(kwargs)
        _notify_sink(self._sink, "progress_postfix", values)

    def close(self) -> None:
        _notify_sink(self._sink, "progress_closed", self.n, self.total)


class _FallbackIterable:
    """tqdm 不可用且没有 sink 时的降级包装：仅保留原有 print 行为标记。"""

    def __init__(self, iterable: Any) -> None:
        self._iterable = iterable

    def __iter__(self) -> Iterator[Any]:
        return iter(self._iterable)


def _safe_len(iterable: Any) -> int:
    try:
        return len(iterable)  # type: ignore[arg-type]
    except TypeError:
        return 0


def create_progress_bar(
    total: Optional[int] = None,
    description: str = "",
    unit: str = "item",
    **kwargs: Any,
) -> Any:
    """创建进度条：有 sink 时返回事件转发对象，否则返回真实 tqdm。"""
    sink = get_progress_sink()
    if sink is not None:
        return _SinkBar(sink, total, description, unit)
    return tqdm(total=total, desc=description, unit=unit, **kwargs)


def iterate_with_progress(
    iterable: Any,
    total: Optional[int] = None,
    description: str = "",
    unit: str = "item",
) -> Any:
    """带进度的迭代：sink 优先，其次 tqdm，最后原样返回。"""
    sink = get_progress_sink()
    if sink is not None:
        return _SinkIterable(sink, iterable, total, description, unit)
    if TQDM_AVAILABLE:
        return tqdm(iterable, desc=description, unit=unit, total=total)
    return _FallbackIterable(iterable)


class ProgressManager:
    """进度管理器

    提供统一的进度跟踪和显示功能。

    Attributes:
        show_progress (bool): 是否显示进度条
        progress_bar: 当前进度条实例
    """

    def __init__(self, show_progress: bool = True):
        """初始化进度管理器

        Args:
            show_progress: 是否显示进度条
        """
        self.show_progress = show_progress
        self.progress_bar: Optional[Any] = None
        self._start_time: Optional[float] = None
        self._total_items = 0
        self._processed_items = 0

    def create_progress_bar(
        self, total: int, description: str = "", unit: str = "item", **kwargs
    ) -> Optional[_tqdm]:
        """创建进度条

        Args:
            total: 总项目数
            description: 描述文本
            unit: 单位
            **kwargs: 其他tqdm参数

        Returns:
            进度条实例或None
        """
        if not self.show_progress:
            return None

        self._total_items = total
        self._processed_items = 0
        self._start_time = time.time()

        sink = get_progress_sink()
        if sink is not None:
            self.progress_bar = _SinkBar(sink, total, description, unit)
            logger.debug(f"创建进度接收器: {description} (总计: {total})")
            return self.progress_bar

        try:
            self.progress_bar = tqdm(
                total=total, desc=description, unit=unit, ncols=80, **kwargs
            )
            logger.debug(f"创建进度条: {description} (总计: {total})")
            return self.progress_bar
        except Exception as e:
            logger.warning(f"创建进度条失败: {str(e)}")
            return None

    def update_progress(self, n: int = 1, description: Optional[str] = None) -> None:
        """更新进度

        Args:
            n: 增加的项目数
            description: 新的描述文本
        """
        self._processed_items += n

        if self.progress_bar:
            try:
                self.progress_bar.update(n)
                if description:
                    self.progress_bar.set_description(description)
            except Exception as e:
                logger.warning(f"更新进度条失败: {str(e)}")
        elif self.show_progress:
            # 简单的文本进度显示
            if self._total_items > 0:
                percent = (self._processed_items / self._total_items) * 100
                print(
                    f"\r进度: {percent:.1f}% ({self._processed_items}/{self._total_items})",
                    end="",
                )

    def close_progress_bar(self) -> None:
        """关闭进度条"""
        if self.progress_bar:
            try:
                self.progress_bar.close()
                elapsed = time.time() - self._start_time if self._start_time else 0
                logger.debug(f"进度条关闭，耗时: {elapsed:.2f}秒")
            except Exception as e:
                logger.warning(f"关闭进度条失败: {str(e)}")
            finally:
                self.progress_bar = None
        elif self.show_progress and self._total_items > 0:
            print("\n完成")

    def __enter__(self):
        """上下文管理器入口"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        _ = (exc_type, exc_val, exc_tb)
        self.close_progress_bar()
        return False


@contextmanager
def progress_context(
    total: int, description: str = "", show_progress: bool = True, **kwargs
) -> Iterator[ProgressManager]:
    """进度上下文管理器

    Args:
        total: 总项目数
        description: 描述文本
        show_progress: 是否显示进度条
        **kwargs: 其他参数

    Yields:
        ProgressManager: 进度管理器实例

    Example:
        >>> with progress_context(100, "处理文件") as progress:
        ...     for i in range(100):
        ...         # 处理逻辑
        ...         progress.update_progress(1)
    """
    manager = ProgressManager(show_progress=show_progress)

    try:
        manager.create_progress_bar(total, description, **kwargs)
        yield manager
    finally:
        manager.close_progress_bar()


def process_with_progress(
    items: List[Any],
    processor: Callable[[Any], Any],
    description: str = "处理中",
    show_progress: bool = True,
    error_handler: Optional[Callable[[Exception, Any], Any]] = None,
) -> List[Any]:
    """带进度显示的批量处理

    Args:
        items: 要处理的项目列表
        processor: 处理函数
        description: 进度描述
        show_progress: 是否显示进度条
        error_handler: 错误处理函数

    Returns:
        List[Any]: 处理结果列表

    Example:
        >>> def process_item(item):
        ...     return item * 2
        >>>
        >>> results = process_with_progress(
        ...     [1, 2, 3, 4, 5],
        ...     process_item,
        ...     "处理数字"
        ... )
    """
    results = []
    errors = []

    with progress_context(len(items), description, show_progress) as progress:
        for i, item in enumerate(items):
            try:
                result = processor(item)
                results.append(result)
            except Exception as e:
                logger.error(f"处理项目 {i} 时出错: {str(e)}")
                if error_handler:
                    try:
                        handled_result = error_handler(e, item)
                        results.append(handled_result)
                    except Exception as handle_error:
                        logger.error(f"错误处理器失败: {str(handle_error)}")
                        errors.append((i, item, e))
                        results.append(None)
                else:
                    errors.append((i, item, e))
                    results.append(None)

            progress.update_progress(1)

    if errors:
        logger.warning(f"处理完成，但有 {len(errors)} 个错误")
        for i, item, error in errors[:5]:  # 只显示前5个错误
            logger.warning(f"  项目 {i}: {str(error)}")
        if len(errors) > 5:
            logger.warning(f"  ... 还有 {len(errors) - 5} 个错误")

    return results
