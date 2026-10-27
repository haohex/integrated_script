#!/usr/bin/env bash
# 冒烟测试打包好的单文件程序：能启动，且 Pillow / OpenCV 在打包后真实可用。
#
# 用法：bash scripts/ci/smoke_test.sh <可执行文件路径>
# Linux 产物在 CI 中放进 centos:7 容器（glibc 2.17）里运行本脚本，验证最低兼容版本。
set -euo pipefail

exe="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/img"
cp "$script_dir/smoke.jpg" "$work/img/smoke.jpg"
cd "$work"

check() {
  local name="$1" pattern="$2" output="$3"
  if grep -q -- "$pattern" <<<"$output"; then
    echo "PASS: $name"
  else
    echo "FAIL: $name (未找到: $pattern)"
    echo "----- 输出 -----"
    echo "$output"
    exit 1
  fi
}

out="$("$exe" --version 2>&1)"
check "--version" "integrated_script" "$out"

# 主菜单 2 图像处理 -> 5 获取图像信息（Pillow）
out="$(printf '2\n5\nimg/smoke.jpg\n\n0\n0\n0\n' | "$exe" 2>&1 || true)"
check "Pillow 读取图像信息" "8 x 8" "$out"

# 主菜单 2 图像处理 -> 4 修复 OpenCV 读取错误的图像（OpenCV），不递归
out="$(printf '2\n4\nimg\nn\n\n0\n0\n0\n' | "$exe" 2>&1 || true)"
check "OpenCV 读取图像" "OpenCV 成功加载 1 张" "$out"

echo "冒烟测试通过: $exe"
