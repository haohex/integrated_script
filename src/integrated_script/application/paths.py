#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用户目录与运行路径解析。

应用运行时的可写状态（配置、日志、缓存）统一放在 ``platformdirs`` 提供的
用户目录下，而不是当前工作目录。显式 ``--config`` 仍然优先。

这里只负责路径解析，不做任何配置迁移；旧 cwd 配置的导入由应用层显式确认。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:  # pragma: no cover - platformdirs 为运行时依赖
    from platformdirs import PlatformDirs
except ImportError:  # pragma: no cover - 回退保证 core 不依赖第三方
    PlatformDirs = None  # type: ignore[assignment,misc]

APP_NAME = "integrated_script"
APP_AUTHOR = "IntegratedScript"


def _fallback_base() -> Path:
    """platformdirs 不可用时的保守回退目录。"""
    if os.name == "nt":  # pragma: no cover - 仅在 Windows 回退
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return Path(base) / APP_NAME
    xdg_config = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config:
        return Path(xdg_config) / APP_NAME
    return Path(os.path.expanduser("~")) / ".config" / APP_NAME


@dataclass(frozen=True)
class AppPaths:
    """应用运行目录集合。

    Attributes:
        config_dir: 用户配置目录。
        log_dir: 日志目录。
        cache_dir: 缓存目录。
        config_file: 默认配置文件路径（可被显式 --config 覆盖）。
        legacy_config_file: 旧版 cwd 配置文件路径（仅用于提示导入）。
    """

    config_dir: Path
    log_dir: Path
    cache_dir: Path
    config_file: Path
    legacy_config_file: Optional[Path] = None

    @classmethod
    def resolve(
        cls,
        *,
        explicit_config: Optional[os.PathLike | str] = None,
        working_directory: Optional[os.PathLike | str] = None,
        prefer_user_dirs: bool = True,
    ) -> "AppPaths":
        """解析应用目录。

        Args:
            explicit_config: 显式指定的配置文件路径，优先级最高。
            working_directory: 相对路径与旧配置探测所基于的目录。
            prefer_user_dirs: 是否使用 platformdirs 用户目录（应用启动为 True）。
        """
        cwd = Path(working_directory) if working_directory else Path.cwd()

        if prefer_user_dirs and PlatformDirs is not None:
            dirs = PlatformDirs(appname=APP_NAME, appauthor=APP_AUTHOR)
            config_dir = Path(dirs.user_config_dir)
            log_dir = Path(dirs.user_log_dir)
            cache_dir = Path(dirs.user_cache_dir)
        else:
            base = _fallback_base()
            config_dir = base / "config"
            log_dir = base / "logs"
            cache_dir = base / "cache"

        default_config = config_dir / "config.json"

        if explicit_config is not None:
            resolved_config = Path(explicit_config).expanduser()
            if not resolved_config.is_absolute():
                resolved_config = (cwd / resolved_config).resolve()
            config_file = resolved_config
            # 显式 --config 由用户明确指定，不触发旧配置导入提示。
            legacy_config = None
        else:
            config_file = default_config
            # 候选旧配置：cwd/config.json 优先，其次用户配置目录下的
            # config.json（保证「新配置不存在才提示导入」两个方向都成立）。
            candidates = (cwd / "config.json", default_config)
            legacy_config = None
            for candidate in candidates:
                if candidate == config_file:
                    continue
                if candidate.is_file():
                    legacy_config = candidate
                    break

        return cls(
            config_dir=config_dir,
            log_dir=log_dir,
            cache_dir=cache_dir,
            config_file=config_file,
            legacy_config_file=legacy_config,
        )

    def ensure_directories(self) -> None:
        """创建配置/日志/缓存目录。"""
        for directory in (self.config_dir, self.log_dir, self.cache_dir):
            directory.mkdir(parents=True, exist_ok=True)

    @property
    def has_legacy_config(self) -> bool:
        """是否有可提示导入的旧配置。

        仅当当前生效的 ``config_file`` 尚不存在，且发现其它候选旧配置时返回
        True；不会因为读取旧配置而创建新文件，也不把 ``--config`` 认定的文件
        当作旧配置重复导入。
        """
        if self.legacy_config_file is None:
            return False
        if self.legacy_config_file == self.config_file:
            return False
        return self.legacy_config_file.is_file() and not self.config_file.exists()


__all__ = ["AppPaths", "APP_NAME", "APP_AUTHOR"]
