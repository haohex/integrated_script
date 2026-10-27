#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
version.py

统一版本读取入口。
优先从仓库 pyproject.toml 读取，回退到已安装包元数据。
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Callable, Optional, Tuple

PackageVersionFunc = Callable[[str], str]


def _resolve_metadata_api() -> Tuple[type[Exception], Optional[PackageVersionFunc]]:
    try:
        import importlib.metadata as metadata

        return metadata.PackageNotFoundError, metadata.version
    except ImportError:  # pragma: no cover
        try:
            import importlib_metadata as metadata_backport  # type: ignore[import-not-found]

            return (
                metadata_backport.PackageNotFoundError,
                metadata_backport.version,
            )
        except ImportError:  # pragma: no cover
            return Exception, None


PackageNotFound, package_version = _resolve_metadata_api()


_DEFAULT_VERSION = "0.0.0"
_PACKAGE_NAME = "integrated-script"


def _find_pyproject(start_file: Path) -> Optional[Path]:
    """从给定文件路径向上查找 pyproject.toml。"""
    current = start_file.resolve().parent
    for directory in [current, *current.parents]:
        candidate = directory / "pyproject.toml"
        if candidate.exists():
            return candidate
    return None


@lru_cache(maxsize=1)
def get_version() -> str:
    """获取应用版本号。"""
    pyproject_file = _find_pyproject(Path(__file__))
    if pyproject_file is not None:
        content = pyproject_file.read_text(encoding="utf-8")
        in_project_section = False

        for line in content.splitlines():
            stripped = line.strip()

            if stripped == "[project]":
                in_project_section = True
                continue

            if (
                in_project_section
                and stripped.startswith("[")
                and stripped != "[project]"
            ):
                break

            if in_project_section:
                match = re.match(r"^\s*version\s*=\s*['\"]([^'\"]+)['\"]", line)
                if match:
                    return match.group(1)

    if package_version is not None:
        try:
            return package_version(_PACKAGE_NAME)
        except PackageNotFound:
            pass

    return _DEFAULT_VERSION
