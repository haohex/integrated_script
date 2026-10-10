#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""离线可执行文件打包脚本。

用法::

    python build_exe.py                 # 默认构建 TUI（兼容旧 main.py --build）
    python build_exe.py --mode tui      # 仅终端界面（console，不含 Qt）
    python build_exe.py --mode gui      # 仅桌面界面（Windows 下无控制台窗口）
    python build_exe.py --mode all      # 依次构建 TUI 与 GUI

设计要点：

* 构建机允许联网安装依赖；产物为自包含 onedir，目标机器离线运行。
* GUI 与 TUI 使用各自独立的 launcher 入口，二者都调用 ``integrated_script.main``
  中已经约定的 ``main`` / ``gui_main``。
* TUI 明确排除 Qt / PySide6 / 桌面界面模块；GUI 排除 TUI 与 WebEngine 等未使用组件。
* 设计截图、测试代码与 fake 服务不得进入产物；构建后通过 :func:`verify_dist` 断言。
"""

from __future__ import annotations

import argparse
import importlib.util
import multiprocessing
import os
import platform
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent

MODES: Tuple[str, ...] = ("tui", "gui", "all")

# 任何平台都不需要打进产物、且不属于产品运行路径的模块。
_COMMON_EXCLUDES: Tuple[str, ...] = (
    "tkinter",
    "PyQt5",
    "PyQt6",
    "PySide2",
    "pytest",
    "_pytest",
    "pytest_qt",
    "pytest_asyncio",
    "black",
    "isort",
    "flake8",
    "mypy",
    "IPython",
    "notebook",
    "tests",
)

# 桌面界面用不到的 Qt 子模块，减小体积。
_GUI_QT_EXCLUDES: Tuple[str, ...] = (
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel",
    "PySide6.QtWebSockets",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickWidgets",
    "PySide6.QtQuick3D",
    "PySide6.Qt3DCore",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtBluetooth",
    "PySide6.QtNfc",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtRemoteObjects",
    "PySide6.QtSerialPort",
    "PySide6.QtSpatialAudio",
    "PySide6.QtSvgWidgets",
    "PySide6.QtUiTools",
    "PySide6.QtVirtualKeyboard",
    "PySide6.QtNetworkAuth",
    "PySide6.QtPositioning",
)

# TUI 明确排除 Qt 与桌面界面。
_TUI_EXCLUDES: Tuple[str, ...] = (
    "PySide6",
    "shiboken6",
    "integrated_script.ui.desktop",
)


@dataclass(frozen=True)
class BuildTarget:
    """单个打包目标的不可变描述。"""

    mode: str
    name: str
    entry: Path
    console: bool
    output_dir: Path
    extra_excludes: Tuple[str, ...] = field(default=())
    collect_all: Tuple[str, ...] = field(default=())

    @property
    def executable_name(self) -> str:
        suffix = ".exe" if os.name == "nt" else ""
        return f"{self.name}{suffix}"

    @property
    def executable_path(self) -> Path:
        return self.output_dir / self.executable_name


def project_root() -> Path:
    return PROJECT_ROOT


def _launcher_script(mode: str) -> Path:
    return PROJECT_ROOT / "scripts" / f"launch_{mode}.py"


def resolve_targets(mode: str) -> List[BuildTarget]:
    """把 ``--mode`` 解析为具体构建目标列表。"""
    if mode not in MODES:
        raise ValueError(f"未知构建模式: {mode!r}（可选：{', '.join(MODES)}）")

    tui = BuildTarget(
        mode="tui",
        name="integrated_script",
        entry=_launcher_script("tui"),
        console=True,
        output_dir=PROJECT_ROOT / "dist" / "integrated_script",
        extra_excludes=_TUI_EXCLUDES,
        collect_all=("textual",),
    )
    gui = BuildTarget(
        mode="gui",
        name="integrated_script_gui",
        entry=_launcher_script("gui"),
        console=False,
        output_dir=PROJECT_ROOT / "dist" / "integrated_script_gui",
        extra_excludes=_GUI_QT_EXCLUDES,
        # 不用 --collect-all=PySide6：那会把整个 Qt（含 WebEngine/3D/Charts）都拉进来
        # （实测 934MB）。PyInstaller 自带的 PySide6 hook + 显式 hidden-import 只收集
        # 实际使用的 QtCore/QtGui/QtWidgets/QtSvg。
    )

    if mode == "tui":
        return [tui]
    if mode == "gui":
        return [gui]
    return [tui, gui]


def _data_separator() -> str:
    return ";" if os.name == "nt" else ":"


def collect_add_data(root: Path) -> List[str]:
    """需要随产物分发的本地资源（配置模板 / 图标 / 许可证）。"""
    sep = _data_separator()
    candidates = [
        (root / "config", "config"),
        (root / "LICENSE", "."),
    ]
    pairs: List[str] = []
    for source, destination in candidates:
        if source.exists():
            pairs.append(f"{source}{sep}{destination}")

    # 本地图标（含 icons/LICENSE）由 --collect-data=integrated_script 从包内
    # package-data 一并收集，见 pyproject.toml [tool.setuptools.package-data]。
    return pairs


def collect_hidden_imports(target: BuildTarget) -> List[str]:
    common = [
        "integrated_script",
        "integrated_script.main",
        "integrated_script.application",
        "integrated_script.config",
        "integrated_script.core",
        "integrated_script.processors",
        "integrated_script.ui",
        "PIL",
        "cv2",
        "yaml",
        "tqdm",
        "platformdirs",
        "logging.handlers",
        "logging.config",
        "multiprocessing",
        "multiprocessing.spawn",
        "concurrent.futures",
    ]
    if target.mode == "tui":
        common += [
            "integrated_script.ui.tui",
            "integrated_script.ui.shared",
            "textual",
        ]
    else:
        common += [
            "integrated_script.ui.desktop",
            "integrated_script.ui.shared",
            "PySide6",
            "PySide6.QtCore",
            "PySide6.QtGui",
            "PySide6.QtWidgets",
            "PySide6.QtSvg",
        ]
    return common


def build_command(target: BuildTarget, root: Path, *, clean: bool = True) -> List[str]:
    """构造调用 PyInstaller 的完整命令（可测试、无副作用）。"""
    # PyInstaller 在 --distpath 下以 --name 建目录；dist/<name> 即产物目录。
    target.output_dir.mkdir(parents=True, exist_ok=True)
    work_dir = root / "build" / target.mode
    work_dir.mkdir(parents=True, exist_ok=True)

    command: List[str] = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--console" if target.console else "--windowed",
        f"--name={target.name}",
        "--distpath",
        str(target.output_dir.parent),
        "--workpath",
        str(work_dir),
        "--specpath",
        str(work_dir),
        "--paths",
        str(root / "src"),
    ]
    if clean:
        command.append("--clean")

    if platform.machine().lower() in {"aarch64", "arm64"}:
        command.append("--noupx")

    excludes = list(_COMMON_EXCLUDES) + list(target.extra_excludes)
    # 注意：不排除 numpy —— 图像处理（processors/image/core.py）在模块顶层导入它，
    # 排除会导致图像处理功能在离线产物中静默失效。
    for module in excludes:
        command += ["--exclude-module", module]

    for module in collect_hidden_imports(target):
        command += ["--hidden-import", module]

    command.append("--collect-submodules=integrated_script")
    command.append("--collect-data=integrated_script")
    # 携带包元数据，使冻结产物无论放在哪都能通过 importlib.metadata 读到真实版本号
    # （否则 version.py 回退为 0.0.0）。
    command.append("--copy-metadata=integrated-script")
    for package in target.collect_all:
        command.append(f"--collect-all={package}")

    for data in collect_add_data(root):
        command += ["--add-data", data]

    icon = root / "src" / "integrated_script" / "assets" / "app.ico"
    if icon.exists():
        command += ["--icon", str(icon)]

    command.append(str(target.entry))
    return command


def _pyinstaller_available() -> bool:
    return importlib.util.find_spec("PyInstaller") is not None


_FORBIDDEN_ARTIFACT_PARTS = (
    "tests",
    "fake_service",
    "generate_screenshots",
    "design",
)


def verify_dist(target: BuildTarget) -> List[str]:
    """检查产物目录，返回问题列表（空表示通过）。"""
    problems: List[str] = []
    if not target.output_dir.is_dir():
        return [f"产物目录不存在: {target.output_dir}"]
    if not target.executable_path.exists():
        problems.append(f"未找到可执行文件: {target.executable_path}")

    text_suffixes = {".py", ".pyi"}
    image_suffixes = {".png", ".jpg", ".jpeg"}
    bundled = [
        path
        for path in target.output_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in text_suffixes | image_suffixes
    ]
    for path in bundled:
        relative = path.relative_to(target.output_dir)
        lowered = str(relative).lower()
        parts = {part.lower() for part in relative.parts}
        if "tests" in parts:
            problems.append(f"测试代码被打入产物: {relative}")
        for forbidden in _FORBIDDEN_ARTIFACT_PARTS:
            if forbidden in lowered and forbidden not in {"tests", "design"}:
                problems.append(f"测试/截图脚本被打入产物: {relative}")
        if "design" in parts and path.suffix.lower() in image_suffixes:
            problems.append(f"设计截图被打入产物: {relative}")

    if target.mode == "tui":
        for qt_marker in ("PySide6", "shiboken6", "Qt6Core", "Qt6Widgets"):
            match = next(
                (
                    path
                    for path in target.output_dir.rglob(f"*{qt_marker}*")
                    if path.is_file()
                ),
                None,
            )
            if match is not None:
                problems.append(
                    f"TUI 产物包含 Qt 组件: {match.relative_to(target.output_dir)}"
                )
    return problems


def _run_target(target: BuildTarget, root: Path, *, clean: bool = True) -> bool:
    if not target.entry.exists():
        print(f"错误: 找不到启动器入口 {target.entry}")
        return False

    command = build_command(target, root, clean=clean)
    try:
        display = shlex.join(command)
    except AttributeError:  # pragma: no cover - 旧 Python
        display = " ".join(shlex.quote(part) for part in command)
    print(f"[{target.mode}] 执行: {display}")

    try:
        result = subprocess.run(command, cwd=str(root))
    except FileNotFoundError:
        print("构建失败: 当前解释器不可用。")
        return False

    if result.returncode != 0:
        print(f"[{target.mode}] PyInstaller 执行失败，退出码 {result.returncode}")
        return False

    problems = verify_dist(target)
    if problems:
        print(f"[{target.mode}] 产物校验失败：")
        for problem in problems:
            print(f"  - {problem}")
        return False

    size_mb = (
        sum(
            path.stat().st_size
            for path in target.output_dir.rglob("*")
            if path.is_file()
        )
        / 1024
        / 1024
    )
    print(
        f"[{target.mode}] 构建成功: {target.executable_path} "
        f"(目录 {size_mb:.1f} MB, console={target.console})"
    )
    return True


def create_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build_exe.py",
        description="构建离线自包含产物（TUI / GUI / 全部）",
    )
    parser.add_argument(
        "--mode",
        choices=MODES,
        default="tui",
        help="构建目标：tui（默认）、gui 或 all",
    )
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="复用 PyInstaller 缓存（默认 --clean）",
    )
    return parser


def build_exe(mode: str = "tui", *, clean: bool = True) -> bool:
    """按模式执行构建，返回是否全部成功。"""
    root = PROJECT_ROOT
    if not _pyinstaller_available():
        lock_hint = (
            "requirements-build-gui.txt"
            if mode in {"gui", "all"}
            else "requirements-build.txt"
        )
        print(
            "错误: 当前解释器未安装 PyInstaller。\n"
            f"      请安装构建依赖：pip install -r {lock_hint}"
        )
        return False

    targets = resolve_targets(mode)
    print(
        f"构建机器: {platform.machine()} | Python {platform.python_version()} | 模式 {mode}"
    )
    results: Dict[str, bool] = {}
    for target in targets:
        if target.output_dir.exists():
            try:
                shutil.rmtree(target.output_dir)
            except PermissionError:
                print(f"[{target.mode}] 警告: 无法删除旧产物目录，继续构建。")
        results[target.mode] = _run_target(target, root, clean=clean)

    return all(results.values())


def main(argv: Sequence[str] | None = None) -> int:
    # 冻结后的多进程（图片压缩使用 ProcessPoolExecutor）必须有这一步，
    # 且必须在解析参数/启动 Qt 之前执行，否则子进程会重复启动整个界面。
    multiprocessing.freeze_support()

    parser = create_argument_parser()
    args = parser.parse_args(argv)
    success = build_exe(args.mode, clean=not args.no_clean)
    if success:
        print("\n构建完成。")
        return 0
    print("\n构建失败。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
