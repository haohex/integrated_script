# integrated_script Makefile
# 简化常用开发、运行与离线打包任务的 Makefile
#
# 说明：本文件的清理/构建目标只作用于仓库内目录，不会删除用户配置或数据。

PYTHON ?= python
VENV_PYTHON ?= .venv/bin/python

.PHONY: help install install-dev install-gui install-build install-build-gui lock lock-gui test test-cov test-fast \
	lint format type-check format-check check-all check-ui clean \
	build build-tui build-gui build-all build-wheel \
	run run-tui run-gui run-legacy run-cli-help \
	docs serve-docs install-hooks setup-dev \
	update-deps install-deps init-project quickstart \
	clean-windows

# 默认目标
help:
	@echo "Available targets:"
	@echo "  --- 安装 ---"
	@echo "  install       - 安装运行期依赖（TUI + 核心，不含 Qt）"
	@echo "  install-dev   - 安装开发依赖（含 GUI/界面测试依赖）"
	@echo "  install-gui   - 安装 Qt 桌面界面依赖"
	@echo "  install-build - 安装离线打包依赖（PyInstaller）"
	@echo "  install-build-gui - 安装 GUI 离线打包依赖（PyInstaller + PySide6）"
	@echo "  lock          - 用 uv 重新生成 requirements-*.txt 锁定文件"
	@echo "  lock-gui      - 单独重新生成 GUI 构建锁 requirements-build-gui.txt"
	@echo "  --- 运行 ---"
	@echo "  run           - 运行默认 TUI 入口（python main.py）"
	@echo "  run-tui       - 运行终端界面（TUI）"
	@echo "  run-gui       - 运行 Qt 桌面界面（GUI）"
	@echo "  run-legacy    - 运行旧交互式命令行界面"
	@echo "  --- 检查 ---"
	@echo "  test          - Run tests"
	@echo "  test-cov      - Run tests with coverage"
	@echo "  lint          - Run linting (flake8)"
	@echo "  format        - Format code (black, isort)"
	@echo "  format-check  - Check formatting without writing"
	@echo "  type-check    - Run type checking (mypy)"
	@echo "  check-all     - Run all checks (lint, format-check, type-check, test)"
	@echo "  check-ui      - 无显示环境下运行界面测试"
	@echo "  --- 构建 ---"
	@echo "  build         - 构建 TUI 离线产物（兼容旧用法）"
	@echo "  build-tui     - 构建终端界面产物（console）"
	@echo "  build-gui     - 构建桌面界面产物（Windows 无控制台）"
	@echo "  build-all     - 依次构建 TUI 与 GUI 产物"
	@echo "  build-wheel   - 构建 sdist/wheel"
	@echo "  clean         - Clean build artifacts"

# 安装
install:
	$(PYTHON) -m pip install -e .

install-dev:
	$(PYTHON) -m pip install -e .[dev,gui,dev-ui]

install-gui:
	$(PYTHON) -m pip install -e .[gui]

install-build:
	$(PYTHON) -m pip install -r requirements-build.txt

install-build-gui:
	$(PYTHON) -m pip install -r requirements-build-gui.txt

# 锁定依赖（构建机需联网；产物运行不需要网络）
lock:
	uv pip compile pyproject.toml --universal --quiet \
		--custom-compile-command "make lock" -o requirements-runtime.txt
	uv pip compile pyproject.toml --universal --quiet --extra build \
		--custom-compile-command "make lock" -o requirements-build.txt
	uv pip compile pyproject.toml --universal --quiet --extra dev --extra dev-ui --extra gui \
		--custom-compile-command "make lock" -o requirements-dev.txt
	@echo "已更新 requirements-runtime.txt / requirements-build.txt / requirements-dev.txt"

# GUI 构建锁：在 build 基础上叠加固定版本 Qt，仅 modes 含 gui 的构建安装。
lock-gui:
	uv pip compile pyproject.toml --universal --quiet \
		--extra build --extra gui --custom-compile-command "make lock-gui" \
		-o requirements-build-gui.txt
	@echo "已更新 requirements-build-gui.txt（build + pinned PySide6）"

# 测试
test:
	$(PYTHON) -m pytest tests/ -v

test-cov:
	$(PYTHON) -m pytest tests/ --cov=src/integrated_script --cov-report=term-missing

test-fast:
	$(PYTHON) -m pytest tests/ -x -v

# 界面测试（无头环境）
check-ui:
	QT_QPA_PLATFORM=offscreen $(PYTHON) -m pytest tests/ui

# 代码质量
PYTHON_PATHS=src/integrated_script tests scripts main.py build_exe.py

lint:
	flake8 --max-line-length=120 --extend-ignore=E203,W503 src/integrated_script tests/ scripts/ main.py build_exe.py

format:
	$(PYTHON) -m black --target-version py311 src tests scripts main.py build_exe.py
	$(PYTHON) -m isort src tests scripts main.py build_exe.py

format-check:
	$(PYTHON) -m black --target-version py311 --check src tests scripts main.py build_exe.py
	$(PYTHON) -m isort --check-only src tests scripts main.py build_exe.py

type-check:
	mypy src/integrated_script

# 综合检查
check-all: lint format-check type-check test

# 清理（仅仓库内构建产物，不触碰用户目录）
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf .mypy_cache/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

# 离线可执行文件构建（本机原生平台；跨平台产物由 CI 原生 runner 构建）
build: build-tui

build-tui:
	$(PYTHON) build_exe.py --mode tui

build-gui:
	$(PYTHON) build_exe.py --mode gui

build-all:
	$(PYTHON) build_exe.py --mode all

# 分发包（wheel/sdist），非离线可执行文件
build-wheel: clean
	$(PYTHON) -m build

# 运行入口
run:
	$(PYTHON) main.py

run-tui:
	$(PYTHON) -m integrated_script.main

run-gui:
	$(PYTHON) -c "from integrated_script.main import gui_main; raise SystemExit(gui_main())"

run-legacy:
	$(PYTHON) main.py --legacy-cli

run-cli-help:
	$(PYTHON) main.py --help

# 文档
docs:
	@echo "Documentation generation not implemented yet"
	@echo "Please refer to docs/README.md for manual documentation"

serve-docs:
	@echo "Documentation server not implemented yet"
	@echo "Please refer to docs/README.md for manual documentation"

# 开发环境设置
setup-dev: install-dev install-hooks

install-hooks:
	@hook_path="$$(git rev-parse --git-path hooks/pre-push)"; \
	cp .githooks/pre-push "$$hook_path"; \
	chmod +x "$$hook_path"

# 依赖管理（编辑 pyproject.toml 后使用 make lock 重新锁定）
update-deps: lock

install-deps:
	$(PYTHON) -m pip install -r requirements-runtime.txt

# 项目初始化
init-project:
	@echo "Initializing project..."
	mkdir -p logs
	mkdir -p output
	mkdir -p temp
	@echo "Project initialized!"

# 快速开始
quickstart: install-dev init-project
	@echo "Quick start setup complete!"
	@echo "Run 'make run-tui' for the terminal interface, 'make run-gui' for the desktop interface."

# Windows 兼容性（如果在 Windows 上使用 make）
ifeq ($(OS),Windows_NT)
    RM = del /Q
    RMDIR = rmdir /S /Q
else
    RM = rm -f
    RMDIR = rm -rf
endif

# 清理 Windows 特定文件
clean-windows:
	$(RM) *.pyc
	$(RMDIR) __pycache__
	$(RMDIR) .pytest_cache
	$(RMDIR) htmlcov
	$(RMDIR) .mypy_cache
	$(RMDIR) build
	$(RMDIR) dist
	$(RMDIR) *.egg-info
