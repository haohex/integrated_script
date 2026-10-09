#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 ``build_exe.py`` 的 onedir 产物打成平台原生分发包。

用法::

    python scripts/package_artifacts.py --mode tui --platform linux \
        --tag v3.0.0 --arch x64 --outdir artifacts

产物命名（release 工作流依赖这些名字）::

    integrated-script-<tag>-<platform>-<arch>-<mode>.zip        # windows
    integrated-script-<tag>-<platform>-<arch>-<mode>.tar.gz     # linux / macos
    integrated-script-<tag>-macos-<arch>-gui.app.zip            # macOS GUI（.app 包）

只使用标准库，便于在任意构建机上运行。默认输出到 ``dist/artifacts/``（已被 gitignore）。
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import stat
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIST_ROOT = PROJECT_ROOT / "dist"
DEFAULT_OUTDIR = DIST_ROOT / "artifacts"

_TARGET_DIRS = {
    "tui": "integrated_script",
    "gui": "integrated_script_gui",
}

_VALID_PLATFORMS = ("windows", "linux", "macos")
_VALID_MODES = ("tui", "gui")


def normalize_arch(value: Optional[str] = None) -> str:
    machine = (value or platform.machine()).lower()
    if machine in {"x86_64", "amd64", "x64", "i386", "i686"}:
        return "x64"
    if machine in {"aarch64", "arm64"}:
        return "arm64"
    return machine or "unknown"


def artifact_name(
    tag: str, plat: str, arch: str, mode: str, *, is_app: bool = False
) -> str:
    if plat == "windows":
        extension = "zip"
    elif is_app:
        extension = "app.zip"
    else:
        extension = "tar.gz"
    stem = f"integrated-script-{tag}-{plat}-{arch}-{mode}"
    if is_app:
        stem = f"integrated-script-{tag}-{plat}-{arch}-gui"
    return f"{stem}.{extension}"


def _write_zip_symlink(archive: zipfile.ZipFile, path: Path, base_dir: Path) -> None:
    """把符号链接写成 ZIP 链接条目而不是复制/跟随目标。"""
    info = zipfile.ZipInfo(path.relative_to(base_dir).as_posix())
    info.create_system = 3  # Unix，解压端才能从 external_attr 读到 S_IFLNK
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    info.compress_type = zipfile.ZIP_STORED
    archive.writestr(info, os.readlink(path), zipfile.ZIP_STORED)


def _write_zip_directory(archive: zipfile.ZipFile, path: Path, base_dir: Path) -> None:
    """写入目录条目，保留空目录与目录 mode。"""
    archive.write(path, path.relative_to(base_dir).as_posix() + "/")


def _zip_directory(
    source_dir: Path, destination: Path, *, preserve_symlinks: bool = False
) -> None:
    """把目录写入 zip。

    默认（Windows 普通分发）与既有行为一致：只收录普通文件。macOS ``.app``
    分发（``preserve_symlinks=True``）额外保留符号链接条目：PyInstaller 6 冻结
    应用要求文件/目录符号链接不被跟随或复制（见
    https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#requirements-imposed-by-symbolic-links-in-frozen-application
    ）。两种模式都不改变 tar 输出。
    """
    if not preserve_symlinks:
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(source_dir.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(source_dir.parent))
        return

    base_dir = source_dir.parent
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        _write_zip_directory(archive, source_dir, base_dir)
        for dirpath, dirnames, filenames in os.walk(source_dir, followlinks=False):
            current = Path(dirpath)
            # 排序保证归档内容稳定；符号链接目录写入链接条目后从遍历中移除，
            # 避免重复收录目标内容；真实子目录递归时写目录条目保留空目录。
            dirnames.sort()
            filenames.sort()
            for name in dirnames:
                entry = current / name
                if entry.is_symlink():
                    _write_zip_symlink(archive, entry, base_dir)
                else:
                    _write_zip_directory(archive, entry, base_dir)
            dirnames[:] = [
                name for name in dirnames if not (current / name).is_symlink()
            ]
            for name in filenames:
                entry = current / name
                if entry.is_symlink():
                    _write_zip_symlink(archive, entry, base_dir)
                else:
                    archive.write(entry, entry.relative_to(base_dir).as_posix())


def _tar_directory(source_dir: Path, destination: Path) -> None:
    with tarfile.open(destination, "w:gz") as archive:
        archive.add(source_dir, arcname=source_dir.name, recursive=True)


def _linux_desktop_entries() -> List[Path]:
    directory = PROJECT_ROOT / "scripts" / "linux"
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.desktop"))


def package(
    mode: str,
    plat: str,
    tag: str,
    arch: Optional[str] = None,
    outdir: Optional[Path] = None,
    dist_root: Optional[Path] = None,
) -> Path:
    """打包单个目标，返回生成的压缩包路径。"""
    if mode not in _VALID_MODES:
        raise ValueError(f"未知模式: {mode!r}")
    if plat not in _VALID_PLATFORMS:
        raise ValueError(f"未知平台: {plat!r}")

    root = dist_root or DIST_ROOT
    normalized_arch = normalize_arch(arch)
    target_dir = root / _TARGET_DIRS[mode]
    if not target_dir.is_dir():
        raise FileNotFoundError(
            f"未找到 {mode} 产物目录 {target_dir}，请先运行 `python build_exe.py --mode {mode}`"
        )

    output_dir = outdir or DEFAULT_OUTDIR
    output_dir.mkdir(parents=True, exist_ok=True)

    if plat == "linux":
        desktop_dir = target_dir / "share" / "applications"
        desktop_dir.mkdir(parents=True, exist_ok=True)
        for entry in _linux_desktop_entries():
            shutil.copy2(entry, desktop_dir / entry.name)

    # macOS GUI：PyInstaller 在 onedir+windowed 下会把 BUNDLE 放在 onedir
    # 同级（dist/<name>.app），而不是 onedir 内部（见 PyInstaller BUNDLE 行为）。
    # 这里同时兼容同级与内部两种布局，避免 release.yml 期望的 .app.zip 缺失。
    app_bundle = next(target_dir.glob("*.app"), None)
    if app_bundle is None:
        sibling = target_dir.parent / f"{target_dir.name}.app"
        if sibling.is_dir():
            app_bundle = sibling
    is_app = plat == "macos" and mode == "gui" and app_bundle is not None

    destination = output_dir / artifact_name(
        tag, plat, normalized_arch, mode, is_app=is_app
    )
    if destination.exists():
        destination.unlink()

    if is_app:
        _zip_directory(app_bundle, destination, preserve_symlinks=True)  # type: ignore[arg-type]
    elif destination.suffix == ".zip":
        _zip_directory(target_dir, destination)
    else:
        _tar_directory(target_dir, destination)
    return destination


def create_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="打包离线产物")
    parser.add_argument("--mode", required=True, choices=_VALID_MODES)
    parser.add_argument("--platform", required=True, choices=_VALID_PLATFORMS)
    parser.add_argument("--tag", required=True, help="发布标签，如 v3.0.0")
    parser.add_argument("--arch", default=None, help="x64 / arm64（默认取当前机器）")
    parser.add_argument(
        "--outdir", default=None, help="输出目录（默认 dist/artifacts/）"
    )
    parser.add_argument("--dist-root", default=None, help="PyInstaller dist 根目录")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = create_argument_parser().parse_args(argv)
    try:
        path = package(
            args.mode,
            args.platform,
            args.tag,
            args.arch,
            Path(args.outdir) if args.outdir else None,
            Path(args.dist_root) if args.dist_root else None,
        )
    except (FileNotFoundError, ValueError) as error:
        print(f"打包失败: {error}")
        return 1
    size_mb = path.stat().st_size / 1024 / 1024
    print(f"已生成 {path} ({size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
