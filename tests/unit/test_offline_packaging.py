# -*- coding: utf-8 -*-
"""离线交付与打包配置的单元测试。

覆盖范围（仅读取仓库文件与调用纯函数，不发起网络请求、不执行真实打包）：

* ``pyproject.toml`` 的 Python 版本、分类器、工具目标、入口脚本与资源清单；
* ``build_exe.py`` 的构建参数（模式、onedir、console/windowed、排除项）；
* 冻结入口的 ``multiprocessing.freeze_support()`` 调用时机；
* 产物校验函数确实能拒绝 Qt / 测试 / 截图泄漏；
* 锁定文件不含私有路径与平台专属 wheel。
"""

from __future__ import annotations

import ast
import re
import stat
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
BUILD_SCRIPT = REPO_ROOT / "build_exe.py"
PYPROJECT = REPO_ROOT / "pyproject.toml"
PACKAGE_SCRIPT = REPO_ROOT / "scripts" / "package_artifacts.py"
BUILD_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "build-artifacts.yml"

LOCK_FILES = (
    "requirements-runtime.txt",
    "requirements-build.txt",
    "requirements-dev.txt",
    "requirements-build-gui.txt",
)

# 允许出现在通用锁定中的环境 markers（uv --universal 会写入跨平台/Python marker）。
_ALLOWED_LOCK_MARKERS = (
    "sys_platform == 'win32'",
    "sys_platform == 'darwin'",
    "python_full_version < '3.12'",
    "python_full_version <= '3.11'",
    "python_full_version >= '3.12'",
    "platform_python_implementation != 'PyPy'",
)

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _toml() -> dict:
    import tomllib

    with PYPROJECT.open("rb") as handle:
        return tomllib.load(handle)


def _load_build_module():
    import importlib

    return importlib.import_module("build_exe")


# --------------------------------------------------------------------------- #
# pyproject.toml
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_requires_python_is_at_least_311() -> None:
    version = _toml()["project"]["requires-python"]
    assert version == ">=3.11"


@pytest.mark.unit
def test_classifiers_drop_unsupported_python_and_add_platforms() -> None:
    classifiers = _toml()["project"]["classifiers"]
    for removed in (
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ):
        assert removed not in classifiers
    assert "Programming Language :: Python :: 3.11" in classifiers
    assert "Operating System :: Microsoft :: Windows :: Windows 11" in classifiers
    assert "Operating System :: POSIX :: Linux" in classifiers
    assert "Operating System :: MacOS :: MacOS X" in classifiers


@pytest.mark.unit
def test_black_and_mypy_targets_match_python_311() -> None:
    data = _toml()
    assert data["tool"]["black"]["target-version"] == ["py311"]
    assert data["tool"]["mypy"]["python_version"] == "3.11"


@pytest.mark.unit
def test_runtime_dependencies_keep_business_semantics_and_add_tui() -> None:
    dependencies = _toml()["project"]["dependencies"]
    joined = " ".join(dependencies)
    # 原有业务依赖语义保留
    for expected in ("tqdm", "Pillow", "opencv-python-headless", "PyYAML", "requests"):
        assert expected.lower() in joined.lower()
    # 新增运行期依赖：TUI 与用户目录
    assert any(dep.startswith("textual") for dep in dependencies)
    assert any(dep.startswith("platformdirs") for dep in dependencies)
    # 运行期依赖不得强制 Qt（TUI 必须能脱离 Qt 运行）
    assert not any("PySide6" in dep for dep in dependencies)


@pytest.mark.unit
def test_gui_extra_exists_and_is_not_forced_on_tui() -> None:
    extras = _toml()["project"]["optional-dependencies"]
    assert any("PySide6" in dep for dep in extras["gui"])
    for required in ("dev-ui", "build"):
        assert required in extras
    assert any("pytest-qt" in dep for dep in extras["dev-ui"])
    assert any("pyinstaller" in dep.lower() for dep in extras["build"])


@pytest.mark.unit
def test_console_and_gui_script_entrypoints() -> None:
    data = _toml()
    assert (
        data["project"]["scripts"]["integrated-script"] == "integrated_script.main:main"
    )
    gui_scripts = data["project"]["gui-scripts"]
    assert gui_scripts["integrated-script-gui"] == "integrated_script.main:gui_main"


@pytest.mark.unit
def test_package_data_ships_offline_assets() -> None:
    package_data = _toml()["tool"]["setuptools"]["package-data"]["integrated_script"]
    joined = " ".join(package_data)
    assert "assets/icons/*.svg" in package_data
    assert "assets/icons/LICENSE" in package_data
    assert "config/*.yaml" in package_data
    assert "assets" in joined


# --------------------------------------------------------------------------- #
# 锁定文件
# --------------------------------------------------------------------------- #


@pytest.mark.unit
@pytest.mark.parametrize("name", LOCK_FILES)
def test_lock_files_are_reproducible_and_path_free(name: str) -> None:
    path = REPO_ROOT / name
    assert path.is_file(), f"缺少锁定文件 {name}"

    content = _read(path)
    for forbidden in ("file://", "/home/", "C:\\"):
        assert forbidden not in content, f"{name} 含本机路径: {forbidden}"

    pinned = [
        line
        for line in content.splitlines()
        if line and not line.startswith(("#", " ")) and "==" in line
    ]
    assert pinned, f"{name} 未包含任何精确锁定版本"
    for line in pinned:
        requirement, _, marker = line.partition(";")
        requirement = requirement.strip()
        assert re.fullmatch(r"[A-Za-z0-9_.\-\[\]]+==[^\s;]+", requirement), line
        if marker:
            assert marker.strip() in _ALLOWED_LOCK_MARKERS, line


@pytest.mark.unit
def test_build_lock_contains_pyinstaller_and_runtime_deps() -> None:
    content = _read(REPO_ROOT / "requirements-build.txt").lower()
    assert "pyinstaller==" in content
    assert "opencv-python-headless==" in content
    assert "pyyaml==" in content


@pytest.mark.unit
def test_build_lock_covers_cross_platform_pyinstaller_deps() -> None:
    """通用锁定必须包含各平台 PyInstaller 依赖（否则对应 runner 装不上）。"""
    content = _read(REPO_ROOT / "requirements-build.txt").lower()
    assert "pefile==" in content and "sys_platform == 'win32'" in content
    assert "pywin32-ctypes==" in content and "sys_platform == 'win32'" in content
    assert "macholib==" in content and "sys_platform == 'darwin'" in content


@pytest.mark.unit
def test_build_lock_does_not_contain_gui_or_dev_tooling() -> None:
    content = _read(REPO_ROOT / "requirements-build.txt").lower()
    assert "pyside6==" not in content
    assert "shiboken6==" not in content
    assert "pytest==" not in content


@pytest.mark.unit
def test_gui_build_lock_pins_qt_and_pyinstaller() -> None:
    """GUI 构建使用独立锁：固定 PySide6 6.8.3，且不含开发工具。"""
    content = _read(REPO_ROOT / "requirements-build-gui.txt").lower()
    assert "pyside6==6.8.3" in content
    assert "shiboken6==6.8.3" in content
    assert "pyinstaller==" in content
    assert "pytest==" not in content


@pytest.mark.unit
def test_gui_build_lock_matches_pyproject_gui_extra_pin() -> None:
    """pyproject gui extra 与 GUI 构建锁必须锁定同一 Qt 版本。"""
    extras = _toml()["project"]["optional-dependencies"]
    assert "PySide6==6.8.3" in extras["gui"]


# --------------------------------------------------------------------------- #
# build_exe.py 参数
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_build_module_imports_without_pyinstaller() -> None:
    module = _load_build_module()
    assert callable(module.build_exe)
    assert callable(module.main)


@pytest.mark.unit
def test_modes_and_default_parser_value() -> None:
    module = _load_build_module()
    assert set(module.MODES) == {"tui", "gui", "all"}
    parser = module.create_argument_parser()
    assert parser.parse_args([]).mode == "tui"
    assert parser.parse_args(["--mode", "gui"]).mode == "gui"


@pytest.mark.unit
def test_unknown_mode_is_rejected() -> None:
    module = _load_build_module()
    with pytest.raises(ValueError):
        module.resolve_targets("nope")


@pytest.mark.unit
@pytest.mark.parametrize("mode", ["tui", "gui", "all"])
def test_resolve_targets_shape(mode: str) -> None:
    module = _load_build_module()
    targets = module.resolve_targets(mode)
    expected = {"tui": 1, "gui": 1, "all": 2}[mode]
    assert len(targets) == expected
    for target in targets:
        assert target.entry.name == f"launch_{target.mode}.py"
        assert target.output_dir.parent.name == "dist"


@pytest.mark.unit
def test_tui_target_is_console_and_excludes_qt() -> None:
    module = _load_build_module()
    (tui,) = module.resolve_targets("tui")
    assert tui.console is True
    assert "PySide6" in tui.extra_excludes
    assert "integrated_script.ui.desktop" in tui.extra_excludes

    command = module.build_command(tui, REPO_ROOT)
    assert "--onedir" in command
    assert "--console" in command
    assert "--windowed" not in command
    assert command.count("--exclude-module") > 0
    excluded = {
        command[index + 1]
        for index, token in enumerate(command)
        if token == "--exclude-module"
    }
    assert "PySide6" in excluded
    assert "integrated_script.ui.desktop" in excluded
    assert "pytest" in excluded


@pytest.mark.unit
def test_gui_target_is_windowed_and_excludes_webengine() -> None:
    module = _load_build_module()
    (gui,) = module.resolve_targets("gui")
    assert gui.console is False

    command = module.build_command(gui, REPO_ROOT)
    assert "--onedir" in command
    assert "--windowed" in command
    assert "--console" not in command
    excluded = {
        command[index + 1]
        for index, token in enumerate(command)
        if token == "--exclude-module"
    }
    assert "PySide6.QtWebEngineCore" in excluded
    assert "pytest" in excluded
    # GUI 不得排除自身界面模块
    assert "integrated_script.ui.desktop" not in excluded


@pytest.mark.unit
def test_build_command_embeds_package_metadata() -> None:
    """冻结产物需带包元数据，否则 version.py 在解压目录中只能回退为 0.0.0。"""
    module = _load_build_module()
    for target in module.resolve_targets("all"):
        command = module.build_command(target, REPO_ROOT)
        assert "--copy-metadata=integrated-script" in command


@pytest.mark.unit
def test_build_command_never_excludes_numpy() -> None:
    """图像处理在模块顶层导入 numpy，排除会导致离线产物功能缺失。"""
    module = _load_build_module()
    for target in module.resolve_targets("all"):
        command = module.build_command(target, REPO_ROOT)
        excluded = {
            command[index + 1]
            for index, token in enumerate(command)
            if token == "--exclude-module"
        }
        assert "numpy" not in excluded
        assert "cv2" not in excluded


@pytest.mark.unit
def test_build_command_keeps_design_screenshots_out_of_bundle() -> None:
    """设计截图目录只存在于 docs/，不得作为 add-data 进入产物。"""
    module = _load_build_module()
    (tui,) = module.resolve_targets("tui")
    command = module.build_command(tui, REPO_ROOT)
    assert "docs/design" not in " ".join(command)
    for data in module.collect_add_data(REPO_ROOT):
        assert "design" not in data.lower()


@pytest.mark.unit
def test_build_command_ships_local_config_and_licenses() -> None:
    module = _load_build_module()
    add_data = module.collect_add_data(REPO_ROOT)
    joined = " ".join(add_data)
    assert "default_config" in joined or f"{REPO_ROOT / 'config'}" in joined
    assert any(
        entry.endswith(f"LICENSE{module._data_separator()}.") for entry in add_data
    )


# --------------------------------------------------------------------------- #
# --clean / --no-clean 透传到 PyInstaller 命令
# --------------------------------------------------------------------------- #


class _FakeCompletedProcess:
    returncode = 0


def _fake_build_target(module, tmp_path: Path, mode: str):
    """构造一个入口存在、产物目录位于 tmp_path 的假构建目标。"""
    entry = tmp_path / f"launch_{mode}.py"
    entry.write_text("print('stub')\n", encoding="utf-8")
    return module.BuildTarget(
        mode=mode,
        name=f"stub_{mode}",
        entry=entry,
        console=mode == "tui",
        output_dir=tmp_path / "dist" / f"stub_{mode}",
    )


def _capture_pyinstaller_commands(
    module, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, clean
) -> list:
    """跑完 build_exe 全链路，返回实际传给 subprocess 的命令列表。

    只 mock subprocess 与产物校验，resolve_targets / _run_target / build_command
    都走真实实现，从而验证 clean 是否真的穿到 PyInstaller 命令行。
    """
    fake_targets = [
        _fake_build_target(module, tmp_path, mode) for mode in ("tui", "gui")
    ]
    captured: list = []

    def fake_run(command, cwd=None, **_kwargs):
        captured.append([str(part) for part in command])
        return _FakeCompletedProcess()

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module, "_pyinstaller_available", lambda: True)
    monkeypatch.setattr(module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(module, "resolve_targets", lambda _mode: list(fake_targets))
    monkeypatch.setattr(module, "verify_dist", lambda _target: [])

    if clean is None:
        assert module.build_exe("all") is True
    else:
        assert module.build_exe("all", clean=clean) is True
    assert len(captured) == len(fake_targets)
    return captured


def _assert_pyinstaller_command(command: list, *, clean: bool) -> None:
    # 先确认这是真实的 PyInstaller 调用，而不是别的子进程
    assert command[1:3] == ["-m", "PyInstaller"]
    assert "--noconfirm" in command
    assert "--onedir" in command
    assert ("--clean" in command) is clean


@pytest.mark.unit
def test_build_exe_no_clean_flag_reaches_pyinstaller(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """--no-clean 必须一路透传，实际 PyInstaller 命令不含 --clean。"""
    module = _load_build_module()
    commands = _capture_pyinstaller_commands(module, monkeypatch, tmp_path, clean=False)
    for command in commands:
        _assert_pyinstaller_command(command, clean=False)


@pytest.mark.unit
def test_build_exe_clean_flag_reaches_pyinstaller(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """显式 clean=True 时，实际 PyInstaller 命令包含 --clean。"""
    module = _load_build_module()
    commands = _capture_pyinstaller_commands(module, monkeypatch, tmp_path, clean=True)
    for command in commands:
        _assert_pyinstaller_command(command, clean=True)


@pytest.mark.unit
def test_build_exe_clean_is_the_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """不传 clean 时保持旧行为：默认带 --clean。"""
    module = _load_build_module()
    commands = _capture_pyinstaller_commands(module, monkeypatch, tmp_path, clean=None)
    for command in commands:
        _assert_pyinstaller_command(command, clean=True)


@pytest.mark.unit
@pytest.mark.parametrize("clean", [True, False])
@pytest.mark.parametrize("pass_clean", [True, False], ids=["default", "explicit"])
def test_run_target_forwards_clean_to_build_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, clean: bool, pass_clean: bool
) -> None:
    """_run_target 必须把 clean 传给 build_command（历史缺陷点）。"""
    module = _load_build_module()
    target = _fake_build_target(module, tmp_path, "tui")
    captured: list = []

    def fake_run(command, cwd=None, **_kwargs):
        captured.append([str(part) for part in command])
        return _FakeCompletedProcess()

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module, "verify_dist", lambda _target: [])

    if pass_clean:
        assert module._run_target(target, tmp_path, clean=clean) is True
    else:
        # 省略 clean 时默认 True，与 build_command 的默认值一致
        assert module._run_target(target, tmp_path) is True
        clean = True

    (command,) = captured
    _assert_pyinstaller_command(command, clean=clean)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("argv", "expected_clean"),
    [(["--mode", "tui"], True), (["--mode", "gui", "--no-clean"], False)],
)
def test_main_forwards_no_clean_to_build_exe(
    monkeypatch: pytest.MonkeyPatch, argv: list, expected_clean: bool
) -> None:
    """CLI 解析结果必须转成 build_exe 的 clean 参数。"""
    module = _load_build_module()
    seen: dict = {}

    def fake_build_exe(mode="tui", *, clean=True):
        seen["mode"] = mode
        seen["clean"] = clean
        return True

    monkeypatch.setattr(module, "build_exe", fake_build_exe)
    assert module.main(list(argv)) == 0
    assert seen["mode"] == argv[argv.index("--mode") + 1]
    assert seen["clean"] is expected_clean


@pytest.mark.unit
def test_verify_dist_rejects_qt_in_tui(tmp_path: Path) -> None:
    module = _load_build_module()
    (tui,) = module.resolve_targets("tui")
    fake = tui.__class__(
        mode="tui",
        name=tui.name,
        entry=tui.entry,
        console=True,
        output_dir=tmp_path / "out",
        extra_excludes=tui.extra_excludes,
    )
    fake.output_dir.mkdir(parents=True)
    fake.executable_path.write_text("stub", encoding="utf-8")
    (fake.output_dir / "PySide6.QtCore.so").write_text("stub", encoding="utf-8")

    problems = module.verify_dist(fake)
    assert any("Qt" in problem for problem in problems)


@pytest.mark.unit
def test_verify_dist_rejects_test_artifacts(tmp_path: Path) -> None:
    module = _load_build_module()
    (tui,) = module.resolve_targets("tui")
    fake = tui.__class__(
        mode="tui",
        name=tui.name,
        entry=tui.entry,
        console=True,
        output_dir=tmp_path / "out",
        extra_excludes=tui.extra_excludes,
    )
    fake.output_dir.mkdir(parents=True)
    fake.executable_path.write_text("stub", encoding="utf-8")
    (fake.output_dir / "tests").mkdir()
    (fake.output_dir / "tests" / "fake_service.py").write_text("x", encoding="utf-8")

    problems = module.verify_dist(fake)
    assert any("测试" in problem for problem in problems)


# --------------------------------------------------------------------------- #
# freeze_support 时机
# --------------------------------------------------------------------------- #


def _function_def(tree: ast.AST, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"未找到函数 {name}")


def _call_lineno(node: ast.AST, dotted: str) -> int | None:
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        rendered = ""
        if isinstance(func, ast.Attribute):
            parts = []
            current = func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value  # type: ignore[assignment]
            if isinstance(current, ast.Name):
                parts.append(current.id)
            rendered = ".".join(reversed(parts))
        elif isinstance(func, ast.Name):
            rendered = func.id
        if rendered == dotted:
            return child.lineno
    return None


@pytest.mark.unit
def test_build_script_calls_freeze_support_before_parsing_args() -> None:
    tree = ast.parse(_read(BUILD_SCRIPT))
    main_func = _function_def(tree, "main")

    freeze_line = _call_lineno(main_func, "multiprocessing.freeze_support")
    assert (
        freeze_line is not None
    ), "build_exe.main 未调用 multiprocessing.freeze_support"

    parse_lines = [
        child.lineno
        for child in ast.walk(main_func)
        if isinstance(child, ast.Call)
        and isinstance(child.func, ast.Attribute)
        and child.func.attr == "parse_args"
    ]
    assert parse_lines, "build_exe.main 未解析参数"
    assert freeze_line < min(parse_lines)


@pytest.mark.unit
@pytest.mark.parametrize("mode", ["tui", "gui"])
def test_launchers_call_freeze_support_before_importing_app(mode: str) -> None:
    path = REPO_ROOT / "scripts" / f"launch_{mode}.py"
    assert path.is_file(), f"缺少启动器 {path}"
    source = _read(path)
    tree = ast.parse(source)
    main_func = _function_def(tree, "main")

    freeze_line = _call_lineno(main_func, "multiprocessing.freeze_support")
    assert freeze_line is not None, f"{path.name} 未调用 freeze_support"

    # 顶层不得导入 integrated_script（冻结子进程需先 freeze_support）
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = getattr(node, "module", None) or ""
            assert "integrated_script" not in module

    import_lines = [
        child.lineno
        for child in ast.walk(main_func)
        if isinstance(child, ast.ImportFrom)
        and "integrated_script.main" in (child.module or "")
    ]
    assert import_lines, f"{path.name} 未调用 integrated_script.main"
    assert freeze_line < min(import_lines), "freeze_support 必须先于应用导入"

    assert 'if __name__ == "__main__"' in source


@pytest.mark.unit
def test_launchers_use_agreed_main_functions() -> None:
    tui_source = _read(REPO_ROOT / "scripts" / "launch_tui.py")
    gui_source = _read(REPO_ROOT / "scripts" / "launch_gui.py")
    assert "from integrated_script.main import main as app_main" in tui_source
    assert "from integrated_script.main import gui_main" in gui_source


@pytest.mark.unit
def test_launcher_scripts_are_valid_python() -> None:
    for mode in ("tui", "gui"):
        path = REPO_ROOT / "scripts" / f"launch_{mode}.py"
        ast.parse(_read(path))


# --------------------------------------------------------------------------- #
# 产物打包脚本
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_package_script_imports_and_names_artifacts() -> None:
    import importlib

    module = importlib.import_module("scripts.package_artifacts")
    assert (
        module.artifact_name("v3.0.0", "windows", "x64", "tui")
        == "integrated-script-v3.0.0-windows-x64-tui.zip"
    )
    assert (
        module.artifact_name("v3.0.0", "linux", "x64", "gui")
        == "integrated-script-v3.0.0-linux-x64-gui.tar.gz"
    )
    assert (
        module.artifact_name("v3.0.0", "macos", "arm64", "gui", is_app=True)
        == "integrated-script-v3.0.0-macos-arm64-gui.app.zip"
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("machine", "expected"),
    [("x86_64", "x64"), ("AMD64", "x64"), ("arm64", "arm64"), ("aarch64", "arm64")],
)
def test_package_script_normalizes_arch(machine: str, expected: str) -> None:
    import importlib

    module = importlib.import_module("scripts.package_artifacts")
    assert module.normalize_arch(machine) == expected


@pytest.mark.unit
def test_package_script_builds_zip_and_tarball(tmp_path: Path) -> None:
    import importlib

    module = importlib.import_module("scripts.package_artifacts")

    dist_root = tmp_path / "dist"
    for name in ("integrated_script", "integrated_script_gui"):
        target = dist_root / name
        target.mkdir(parents=True)
        (target / ("x.exe" if name.endswith("gui") else "x")).write_text(
            "bin", encoding="utf-8"
        )
        (target / "config").mkdir()
        (target / "config" / "default_config.yaml").write_text("a: 1", encoding="utf-8")

    zip_path = module.package(
        "tui", "windows", "v1.0.0", "x64", outdir=tmp_path / "out", dist_root=dist_root
    )
    assert zip_path.exists() and zipfile.is_zipfile(zip_path)

    tar_path = module.package(
        "gui", "linux", "v1.0.0", "x64", outdir=tmp_path / "out", dist_root=dist_root
    )
    assert tar_path.exists() and tarfile.is_tarfile(tar_path)


@pytest.mark.unit
def test_package_script_finds_sibling_macos_app_bundle(tmp_path: Path) -> None:
    """macOS onedir+windowed 下 PyInstaller 把 .app 放在 onedir 同级。

    release.yml 期望的 .app.zip 不能因为只 glob onedir 内部而缺失。
    """
    import importlib

    module = importlib.import_module("scripts.package_artifacts")

    dist_root = tmp_path / "dist"
    target = dist_root / "integrated_script_gui"
    target.mkdir(parents=True)
    (target / "integrated_script_gui").write_text("bin", encoding="utf-8")

    # 同级 .app（PyInstaller BUNDLE 真实布局），不在 onedir 内部。
    app_bundle = dist_root / "integrated_script_gui.app"
    (app_bundle / "Contents" / "MacOS").mkdir(parents=True)
    (app_bundle / "Contents" / "MacOS" / "integrated_script_gui").write_text(
        "bin", encoding="utf-8"
    )
    (app_bundle / "Contents" / "Info.plist").write_text("plist", encoding="utf-8")

    path = module.package(
        "gui",
        "macos",
        "v1.0.0",
        "arm64",
        outdir=tmp_path / "out",
        dist_root=dist_root,
    )

    assert path.name == "integrated-script-v1.0.0-macos-arm64-gui.app.zip"
    assert zipfile.is_zipfile(path)
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
    assert any(
        "integrated_script_gui.app/Contents/Info.plist" in name for name in names
    ), names


@pytest.mark.unit
def test_package_script_preserves_app_symlinks(tmp_path: Path) -> None:
    """macOS .app zip 必须保留文件/目录符号链接条目（PyInstaller 6 要求）。

    这不是 macOS 原生验收，只验证归档层的链接/mode/内容契约。
    """
    import importlib

    module = importlib.import_module("scripts.package_artifacts")

    dist_root = tmp_path / "dist"
    target = dist_root / "integrated_script_gui"
    target.mkdir(parents=True)
    (target / "integrated_script_gui").write_text("bin", encoding="utf-8")

    app_bundle = dist_root / "integrated_script_gui.app"
    frameworks = app_bundle / "Contents" / "Frameworks"
    macos = app_bundle / "Contents" / "MacOS"
    frameworks.mkdir(parents=True)
    macos.mkdir(parents=True)
    executable = macos / "integrated_script_gui"
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    executable.chmod(0o755)
    (app_bundle / "Contents" / "Info.plist").write_text("plist", encoding="utf-8")
    empty_dir = app_bundle / "Contents" / "Resources" / "empty"
    empty_dir.mkdir(parents=True)

    dylib = frameworks / "libpython3.11.dylib"
    dylib.write_text("dylib", encoding="utf-8")
    try:
        (frameworks / "libpython3.11.dylib.link").symlink_to("libpython3.11.dylib")
        (app_bundle / "Contents" / "FrameworksLink").symlink_to("Frameworks")
    except (OSError, NotImplementedError):  # pragma: no cover - 无权限的平台
        pytest.skip("当前环境不允许创建符号链接")

    path = module.package(
        "gui",
        "macos",
        "v1.0.0",
        "arm64",
        outdir=tmp_path / "out",
        dist_root=dist_root,
    )

    with zipfile.ZipFile(path) as archive:
        infos = {info.filename: info for info in archive.infolist()}
        prefix = "integrated_script_gui.app/Contents/"

        file_link = infos[prefix + "Frameworks/libpython3.11.dylib.link"]
        assert file_link.create_system == 3
        assert stat.S_ISLNK(file_link.external_attr >> 16)
        assert archive.read(file_link.filename) == b"libpython3.11.dylib"

        dir_link = infos[prefix + "FrameworksLink"]
        assert dir_link.create_system == 3
        assert stat.S_ISLNK(dir_link.external_attr >> 16)
        assert archive.read(dir_link.filename) == b"Frameworks"
        # 目录链接不得被跟随：目标内容只应出现一次。
        assert (
            sum(
                1
                for name in infos
                if name.endswith("libpython3.11.dylib") and not name.endswith(".link")
            )
            == 1
        )

        real_file = infos[prefix + "MacOS/integrated_script_gui"]
        assert stat.S_IMODE(real_file.external_attr >> 16) == 0o755
        assert archive.read(real_file.filename) == b"#!/bin/sh\n"

        assert prefix + "Resources/empty/" in infos


@pytest.mark.unit
def test_package_script_fails_when_dist_missing(tmp_path: Path) -> None:
    import importlib

    module = importlib.import_module("scripts.package_artifacts")
    with pytest.raises(FileNotFoundError):
        module.package(
            "tui",
            "linux",
            "v1.0.0",
            "x64",
            outdir=tmp_path / "out",
            dist_root=tmp_path / "missing",
        )


# --------------------------------------------------------------------------- #
# 冻结目录契约（application/catalog.py）
# --------------------------------------------------------------------------- #


@pytest.mark.unit
def test_catalog_keeps_all_operations_in_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """源码运行必须保留全部操作，包括「环境检查与配置」。"""
    monkeypatch.delattr(sys, "frozen", raising=False)
    from integrated_script.application import catalog

    operations = catalog.build_operations()
    env_ids = [op.spec.id for op in operations if op.spec.category == "环境检查与配置"]
    assert "env.install_dependencies" in env_ids
    assert "env.check_dependencies" in env_ids


@pytest.mark.unit
def test_catalog_hides_env_category_when_frozen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """冻结产物隐藏环境维护入口，其余类别保持完整。"""
    from integrated_script.application import catalog

    monkeypatch.delattr(sys, "frozen", raising=False)
    source_ops = catalog.build_operations()
    source_categories = {op.spec.category for op in source_ops}
    assert "环境检查与配置" in source_categories

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    frozen_ops = catalog.build_operations()
    frozen_categories = {op.spec.category for op in frozen_ops}
    assert "环境检查与配置" not in frozen_categories

    # 除环境类外，冻结目录与源码目录完全一致（顺序与内容都不变）
    assert [op.spec.id for op in frozen_ops] == [
        op.spec.id for op in source_ops if op.spec.category != "环境检查与配置"
    ]


@pytest.mark.unit
def test_catalog_marks_rename_operations_destructive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """三个 rename 操作是危险展示 metadata（真正确认仍在 handler）。"""
    from integrated_script.application import catalog

    monkeypatch.delattr(sys, "frozen", raising=False)
    specs = {op.spec.id: op.spec for op in catalog.build_operations()}
    for operation_id in (
        "file.rename_single_dir",
        "file.rename_images_labels",
        "file.rename_images_labels_legacy",
    ):
        assert specs[operation_id].destructive is True, operation_id

    suffix_field = next(
        field
        for field in specs["file.rename_single_dir"].fields
        if field.name == "suffix"
    )
    assert "自动检测" in suffix_field.help


@pytest.mark.unit
def test_catalog_category_order_is_stable(monkeypatch: pytest.MonkeyPatch) -> None:
    from integrated_script.application import catalog

    order = catalog.category_order()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert catalog.category_order() == order


# --------------------------------------------------------------------------- #
# CI 构建矩阵静态检查
# --------------------------------------------------------------------------- #


def _build_matrix() -> list[dict]:
    import yaml

    data = yaml.safe_load(_read(BUILD_WORKFLOW))
    jobs = data["jobs"]
    build = jobs["build"]
    return build["strategy"]["matrix"]["include"]


@pytest.mark.unit
def test_current_release_builds_only_linux_and_windows_in_the_cloud() -> None:
    import yaml

    data = yaml.safe_load(_read(BUILD_WORKFLOW))
    jobs_yaml = yaml.safe_dump(data["jobs"], allow_unicode=True)

    runners = {str(entry["runner"]) for entry in _build_matrix()}
    assert runners == {"windows-2022", "ubuntu-22.04", "ubuntu-22.04-arm"}
    assert "macos" not in jobs_yaml
    assert "self-hosted" not in jobs_yaml


@pytest.mark.unit
def test_build_workflow_matrix_uses_current_runners_with_matching_arch() -> None:
    by_name = {entry["name"]: entry for entry in _build_matrix()}
    assert by_name["linux-arm64"]["runner"] == "ubuntu-22.04-arm"
    assert by_name["linux-arm64"]["arch"] == "arm64"
    assert by_name["windows-x64"]["arch"] == "x64"
    assert by_name["linux-x64"]["arch"] == "x64"
    for entry in by_name.values():
        assert entry["arch"] in entry["name"], entry
    assert "architecture: ${{ matrix.arch }}" in _read(BUILD_WORKFLOW)


@pytest.mark.unit
def test_build_workflow_gates_on_quality_and_tests_extracted_bundles() -> None:
    import yaml

    content = _read(BUILD_WORKFLOW)
    jobs = yaml.safe_load(content)["jobs"]
    assert jobs["build"]["needs"] == "quality"
    assert jobs["linux-24-runtime"]["needs"] == "build"
    assert jobs["linux-24-runtime"]["runs-on"] == "ubuntu-24.04"
    assert "verify_artifacts.py extract" in content
    assert "frozen_tui_smoke.py --executable extracted/" in content
    assert "frozen_gui_smoke.py --executable extracted/" in content
    assert "unshare --net" in content
    assert "New-NetFirewallRule" in content


@pytest.mark.unit
def test_build_workflow_installs_gui_lock_only_when_gui_requested() -> None:
    content = _read(BUILD_WORKFLOW)
    assert "requirements-build-gui.txt" in content
    # ARM TUI-only 不得引入 Qt；x64 两个平台均提供桌面产物。
    by_name = {entry["name"]: entry for entry in _build_matrix()}
    assert by_name["linux-arm64"]["gui"] is False
    assert by_name["linux-x64"]["gui"] is True
    assert by_name["windows-x64"]["gui"] is True
    assert "if [ '${{ matrix.gui }}' = 'true' ]; then" in content
    # TUI 安装步骤只装无 Qt 的构建锁
    assert "requirements-build.txt" in content


@pytest.mark.unit
def test_build_workflow_uploads_the_packaged_artifact_dir() -> None:
    """上传路径必须与 package_artifacts 默认输出目录一致（dist/artifacts）。"""
    import importlib

    module = importlib.import_module("scripts.package_artifacts")
    assert module.DEFAULT_OUTDIR == REPO_ROOT / "dist" / "artifacts"

    content = _read(BUILD_WORKFLOW)
    assert "dist/artifacts/*" in content
    # 不应残留旧路径（仓库根 artifacts/）
    assert "\n          path: artifacts/*" not in content


@pytest.mark.unit
def test_build_script_error_hint_points_to_gui_lock() -> None:
    content = _read(BUILD_SCRIPT)
    assert "requirements-build-gui.txt" in content
    assert "requirements-build.txt" in content


@pytest.mark.unit
def test_release_consumes_matrix_artifact_names() -> None:
    """release.yml 的下载/发布路径必须与 build-artifacts 的 matrix 名称一致。"""
    import yaml

    build = yaml.safe_load(_read(BUILD_WORKFLOW))
    names = {
        entry["name"]
        for entry in build["jobs"]["build"]["strategy"]["matrix"]["include"]
    }
    from scripts.verify_artifacts import RELEASE_TARGETS

    assert names == set(RELEASE_TARGETS)
    release = _read(REPO_ROOT / ".github" / "workflows" / "release.yml")
    assert "pattern: offline-*" in release
    assert "merge-multiple: true" in release
    assert "verify_artifacts.py release --directory release-assets" in release
    assert "fail_on_unmatched_files: true" in release
