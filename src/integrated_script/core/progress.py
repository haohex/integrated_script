#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
progress.py

进度管理模块

提供进度条显示、进度跟踪和上下文管理功能。
"""

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
        self.progress_bar = None
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
