#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_exe.py

PyInstaller build script

Used to package integrated_script project as Windows executable
"""

import importlib.util
import os
import platform
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


def build_exe():
    """Build the executable with inline PyInstaller configuration."""

    project_root = Path(__file__).parent
    main_script = project_root / "main.py"

    machine = platform.machine().lower()
    is_arm64 = machine in {"aarch64", "arm64"}
    print(f"Build machine: {machine} (arm64={is_arm64})")

    if not main_script.exists():
        print(f"Error: Main script not found {main_script}")
        return False

    build_dir = project_root / "build"
    if build_dir.exists():
        try:
            shutil.rmtree(build_dir)
        except PermissionError:
            print("Warning: Cannot delete build directory, continuing...")

    if importlib.util.find_spec("PyInstaller") is None:
        print(
            "Error: PyInstaller is not available in the current Python interpreter."
            " Install it in this environment (for example `python -m pip install pyinstaller`)."
        )
        return False

    data_separator = ";" if os.name == "nt" else ":"
    add_data = [
        f"{project_root / 'config'}{data_separator}config",
        f"{project_root / 'requirements.txt'}{data_separator}.",
        f"{project_root / 'pyproject.toml'}{data_separator}.",
    ]

    hidden_imports = [
        "integrated_script",
        "integrated_script.config",
        "integrated_script.core",
        "integrated_script.processors",
        "integrated_script.ui",
        "PIL",
        "cv2",
        "yaml",
        "tqdm",
        "logging.handlers",
        "logging.config",
    ]

    collect_args = [
        "--collect-submodules=integrated_script",
        "--collect-data=integrated_script",
    ]

    exclude_modules = ["tkinter", "PyQt5", "PyQt6"]

    upx_path = shutil.which("upx")
    upx_args = []
    if is_arm64:
        upx_args = ["--noupx"]
        if upx_path:
            print("Notice: ARM64 build disables UPX.")
        else:
            print("Notice: ARM64 build disables UPX (UPX not installed).")
    elif upx_path:
        upx_args = ["--upx-dir", str(Path(upx_path).resolve().parent)]
        print("Notice: UPX enabled.")
    else:
        print("Notice: UPX not found, build will omit binary compression.")

    clean_enabled = os.environ.get("PYINSTALLER_CLEAN", "1").strip().lower() not in {
        "0",
        "false",
        "no",
    }

    strip_enabled = os.name != "nt" and not is_arm64
    if os.name != "nt" and is_arm64:
        print("Notice: ARM64 build disables --strip.")
    if strip_enabled:
        print("Notice: --strip enabled.")

    cmd_parts = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--console",
        "--name=integrated_script",
        "--distpath",
        str(project_root / "dist"),
        "--workpath",
        str(project_root / "build"),
    ]
    cmd_parts = [part for part in cmd_parts if part]
    if strip_enabled:
        cmd_parts.append("--strip")
    if clean_enabled:
        cmd_parts.append("--clean")
    cmd_parts += upx_args

    cmd_parts += ["--paths", str(project_root / "src")]

    for data in add_data:
        cmd_parts += ["--add-data", data]

    for module in hidden_imports:
        cmd_parts += ["--hidden-import", module]

    cmd_parts += collect_args

    for module in exclude_modules:
        cmd_parts += ["--exclude-module", module]

    cmd_parts.append(str(main_script))

    try:
        command_display = shlex.join(cmd_parts)
    except AttributeError:
        command_display = " ".join(shlex.quote(part) for part in cmd_parts)
    print(f"Executing command: {command_display}")
    try:
        result = subprocess.run(cmd_parts)
    except FileNotFoundError:
        print("Build failed: Python executable disappeared from PATH.")
        return False

    if result.returncode == 0:
        exe_name = "integrated_script.exe" if os.name == "nt" else "integrated_script"
        exe_path = project_root / "dist" / exe_name
        if exe_path.exists():
            print("\nBuild successful!")
            print(f"Executable location: {exe_path}")
            print(f"File size: {exe_path.stat().st_size / 1024 / 1024:.1f} MB")
            return True
        else:
            print("Build failed: Generated exe file not found")
            print(f"Expected location: {exe_path}")
            return False
    else:
        print("Build failed: PyInstaller execution error")
        return False


if __name__ == "__main__":
    print("Building integrated_script project...")
    success = build_exe()
    if success:
        print("\nBuild completed successfully!")
    else:
        print("\nBuild failed!")
        sys.exit(1)
