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
# - PyInstaller 从源码包安装并重新编译启动器，打上 pyinstaller-noexec-tmpdir.patch：
#   解压目录会跳过 noexec 挂载的 /tmp 等目录，最后回退到 $HOME/.cache。
set -euo pipefail

PYTHON_VERSION="${PYTHON_VERSION:-3.11}"
PYINSTALLER_VERSION="$(sed -n 's/^pyinstaller==//p' scripts/ci/build-requirements.txt)"
PYINSTALLER_SHA256=05eb2f5615503e72939a7224d68b4aff572c6b0438ee4a17d0a4b481f399362d

export UV_CACHE_DIR=/work/.cache/uv
export UV_PYTHON_INSTALL_DIR=/opt/uv-python
export UV_PYTHON_PREFERENCE=only-managed

/opt/python/cp311-cp311/bin/python -m pip install --quiet --root-user-action=ignore uv
UV=/opt/python/cp311-cp311/bin/uv

"$UV" venv --python "$PYTHON_VERSION" /opt/build-venv
"$UV" pip install --python /opt/build-venv/bin/python \
  --only-binary :all: -r requirements.txt

# 下载 PyInstaller 源码包，校验后打补丁，安装时编译启动器。
src_root=/opt/pyinstaller-src
mkdir -p "$src_root"
sdist_url="$(/opt/build-venv/bin/python - "$PYINSTALLER_VERSION" <<'PY'
import json
import sys
import urllib.request

version = sys.argv[1]
with urllib.request.urlopen(f"https://pypi.org/pypi/pyinstaller/{version}/json") as resp:
    data = json.load(resp)
print(next(u["url"] for u in data["urls"] if u["packagetype"] == "sdist"))
PY
)"
curl -fsSL "$sdist_url" -o "$src_root/pyinstaller.tar.gz"
echo "$PYINSTALLER_SHA256  $src_root/pyinstaller.tar.gz" | sha256sum -c -
tar -xzf "$src_root/pyinstaller.tar.gz" -C "$src_root"
src_dir="$src_root/pyinstaller-$PYINSTALLER_VERSION"
patch -d "$src_dir" -p1 --forward < scripts/ci/pyinstaller-noexec-tmpdir.patch
PYINSTALLER_COMPILE_BOOTLOADER=1 "$UV" pip install --python /opt/build-venv/bin/python \
  --no-cache "$src_dir"

# 确认启动器是从补丁源码编译的：调试版启动器 run_d 中应包含补丁新增的调试字符串
# （正式版 run 不含调试输出，由 smoke_test.sh 的 noexec 场景实际验证）。
/opt/build-venv/bin/python - <<'PY'
import pathlib
import PyInstaller

bootloaders = list(pathlib.Path(PyInstaller.__file__).parent.glob("bootloader/Linux-*/run_d"))
assert bootloaders, "未找到 Linux 调试版启动器"
for path in bootloaders:
    assert b"noexec file system" in path.read_bytes(), f"启动器未包含 noexec 补丁: {path}"
    print(f"补丁启动器: {path.parent}")
PY

"$UV" pip list --python /opt/build-venv/bin/python

/opt/build-venv/bin/python build_exe.py

# 容器内以 root 运行，把产物和缓存交还给宿主用户，后续步骤才能改名和清理。
if [ -n "${HOST_UID:-}" ]; then
  chown -R "$HOST_UID:${HOST_GID:-$HOST_UID}" dist build .cache
fi
