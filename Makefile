# integrated_script Makefile
# 简化常用开发任务的 Makefile

.PHONY: help install install-dev test test-cov lint format type-check clean build upload docs serve-docs install-hooks

# 默认目标
help:
	@echo "Available targets:"
	@echo "  install      - Install the package"
	@echo "  install-dev  - Install development dependencies"
	@echo "  test         - Run tests"
	@echo "  test-cov     - Run tests with coverage"
	@echo "  lint         - Run linting (flake8)"
	@echo "  format       - Format code (black, isort)"
	@echo "  type-check   - Run type checking (mypy)"
	@echo "  check-all    - Run all checks (lint, format, type-check)"
	@echo "  clean        - Clean build artifacts"
	@echo "  build        - Build the package"
	@echo "  upload       - Upload to PyPI"
	@echo "  docs         - Generate documentation"
	@echo "  serve-docs   - Serve documentation locally"
	@echo "  run-example  - Run basic usage example"
	@echo "  run-cli      - Run CLI in interactive mode"

# 安装
install:
	pip install -e .

install-dev:
	pip install -e .[dev,docs]

# 测试
test:
	python -m pytest tests/ -v

test-cov:
	python -m pytest tests/ --cov=src/integrated_script --cov-report=term-missing

test-fast:
	python -m pytest tests/ -x -v

# 代码质量
PYTHON_PATHS=src/integrated_script tests

lint:
	flake8 --max-line-length=120 --extend-ignore=E203,W503 src/integrated_script tests/

format:
	python -m black --target-version py310 src tests main.py build_exe.py
	python -m isort src tests main.py build_exe.py

format-check:
	python -m black --target-version py310 --check src tests main.py build_exe.py
	python -m isort --check-only src tests main.py build_exe.py

format-all:
	python -m black --target-version py310 src tests main.py build_exe.py
	python -m isort src tests main.py build_exe.py

type-check:
	mypy src/integrated_script

# 综合检查
check-all: lint format-check type-check test

# 清理
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

# 构建和发布
build: clean
	python -m build

upload: build
	twine upload dist/*

upload-test: build
	twine upload --repository testpypi dist/*

# 文档
docs:
	@echo "Documentation generation not implemented yet"
	@echo "Please refer to docs/README.md for manual documentation"

serve-docs:
	@echo "Documentation server not implemented yet"
	@echo "Please refer to docs/README.md for manual documentation"

# 运行示例
run-example:
	python examples/basic_usage.py

run-cli:
	python main.py --interactive

run-cli-help:
	python main.py --help

# 开发环境设置
setup-dev: install-dev install-hooks

install-hooks:
	@hook_path="$$(git rev-parse --git-path hooks/pre-push)"; \
	cp .githooks/pre-push "$$hook_path"; \
	chmod +x "$$hook_path"

# 版本管理
bump-patch:
	bump2version patch

bump-minor:
	bump2version minor

bump-major:
	bump2version major

# 安全检查
security-check:
	bandit -r src/integrated_script/
	safety check

# 性能测试
profile:
	python -m cProfile -o profile.stats examples/basic_usage.py
	python -c "import pstats; pstats.Stats('profile.stats').sort_stats('cumulative').print_stats(20)"

# 依赖管理
update-deps:
	pip-compile requirements.in
	pip-compile requirements-dev.in

install-deps:
	pip-sync requirements.txt requirements-dev.txt

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
	@echo "Run 'make run-cli' to start the interactive interface"
	@echo "Run 'make run-example' to see usage examples"

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
