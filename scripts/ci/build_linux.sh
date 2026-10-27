#!/usr/bin/env bash
# 在 manylinux2014 容器（glibc 2.17）内构建 Linux 单文件可执行程序。
#
# 用法（在仓库根目录）：
#   docker run --rm -v "$PWD:/work" -w /work \
#     -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" \
#     quay.io/pypa/manylinux2014_x86_64 bash scripts/ci/build_linux.sh
#
# - manylinux 自带的 CPython 没有 libpython 共享库，PyInstaller 用不了，
#   所以用 uv 安装 python-build-standalone 的 Python。
# - 只装预编译 wheel：在 glibc 2.17 环境里会自动选出仍兼容的最新版本，不做源码编译。
set -euo pipefail

PYTHON_VERSION="${PYTHON_VERSION:-3.11}"

export UV_CACHE_DIR=/work/.cache/uv
export UV_PYTHON_INSTALL_DIR=/opt/uv-python
export UV_PYTHON_PREFERENCE=only-managed

/opt/python/cp311-cp311/bin/python -m pip install --quiet --root-user-action=ignore uv
UV=/opt/python/cp311-cp311/bin/uv

"$UV" venv --python "$PYTHON_VERSION" /opt/build-venv
"$UV" pip install --python /opt/build-venv/bin/python \
  --only-binary :all: -r requirements.txt pyinstaller
"$UV" pip list --python /opt/build-venv/bin/python

/opt/build-venv/bin/python build_exe.py

# 容器内以 root 运行，把产物和缓存交还给宿主用户，后续步骤才能改名和清理。
if [ -n "${HOST_UID:-}" ]; then
  chown -R "$HOST_UID:${HOST_GID:-$HOST_UID}" dist build .cache
fi
