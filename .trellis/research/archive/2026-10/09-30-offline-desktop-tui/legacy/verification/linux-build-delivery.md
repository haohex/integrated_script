# Pi 最终 Ubuntu22 离线构建交付 (stage 1–4)

生成时间: 2026-10-08 15:40 CST
构建主机: host Ubuntu 26.04 / glibc 2.43 (仅作为 Docker 宿主，**未**用于构建/执行产物)
构建容器: `integrated-script-verify:ubuntu22`
`sha256:666bf0a0d221acbacbcc331df09163e5b73e2edd56e633a8ec28ba0e99f6b3d4`
Ubuntu 22.04.5 LTS / glibc 2.35，Python 3.11.15（`/work/python/cpython-3.11.15-linux-x86_64-gnu`，非系统 Python）

## 1. 源码快照与一致性
- 最新稳定源码同步到 `/tmp/integrated-build22-CyKgKo/project`（替换旧快照，保留预装 `.venv`/python）。
- 复制 123 个文件：顶层打包文件、`config/`、`scripts/`、`src/`、LICENSE/README/requirements 锁；含新增 PNG/ICO/SVG/icons/LICENSE。
- 过滤 `__pycache__`/`.pytest_cache`/`.mypy_cache`/`*.pyc`/`*.egg-info`；未复制 tests/docs/design 截图/fakes/.venv/.git/userdatasets。
- `source-manifest-final.json`（相对 repo 路径 + sha256，123 条，含 python/锁/image id）。
- 构建前后 source 一致性：123/123 sha256 匹配，0 mismatch（构建不修改 runtime 源文件）。
- 锁哈希：build-gui e3be27fc…、build f8c35f44…、dev 0c34bf1f…、runtime 76813a08…。

## 2. 构建 (exit 0)
```
docker run --rm --user 1001:1001 \
  -e XDG_CONFIG_HOME=/work/config -e XDG_CACHE_HOME=/work/cache -e XDG_STATE_HOME=/work/state \
  -e QT_QPA_PLATFORM=offscreen -v /tmp/integrated-build22-CyKgKo:/work -w /work/project \
  integrated-script-verify:ubuntu22 /work/.venv/bin/python build_exe.py --mode all --no-clean
EXIT=0
```
日志: `/tmp/integrated-final-build22/logs/build-all-20261008-153300.log`

打包（各 exit 0）：
```
/work/.venv/bin/python scripts/package_artifacts.py --mode tui --platform linux --arch x64 --tag v3.0.0
/work/.venv/bin/python scripts/package_artifacts.py --mode gui --platform linux --arch x64 --tag v3.0.0
```
日志: `logs/package-20261008-153459.log`

## 3. 解压验收根 (tarfile filter='data', symlink 保留)
- `/tmp/integrated-final-build22/extract/integrated_script`  (files=458, symlinks=36)
- `/tmp/integrated-final-build22/extract/integrated_script_gui` (files=452, symlinks=61)
- 无绝对路径符号链接，无 broken symlink。

离线测试（TUI 在 stock `ubuntu:22.04`；GUI 在 Qt 系统库镜像），
`--network none --read-only --tmpfs /tmp`，包 ro mount，XDG 均 /tmp，不安装 Python：
- `command -v python/python3` → not found ✅
- TUI `--version` exit 0 / `--help` exit 0 ✅
- GUI `--version` exit 0 / `--help` exit 0 ✅
- GUI offscreen 进入 Qt eventloop，`timeout 8` → exit 124，无 Traceback / Qt 插件错误 ✅
  （仅证明限时终止，**不**代表正常用户退出或 native GUI 交互）
- root 与 uid 1001 均通过。
日志: `logs/offline-*-*.log`，脚本 `logs/offline_check.sh`

## 4. 回写 repo/dist
- `dist/integrated_script/`、`dist/integrated_script_gui/`（copytree symlinks=True，替换旧 host 产物）
- `dist/artifacts/integrated-script-v3.0.0-linux-x64-{tui,gui}.tar.gz`
- `dist/artifacts/SHA256SUMS`、`BUILDINFO.json`、`source-manifest-final.json`
- SHA256SUMS `sha256sum -c` 全部 OK。未删除其它 dist 内容。

tar.gz sha256：
- tui 54ae6f4d9cb3978baec653953e0ee5519b7acaeab6071c155eb204930a48a66f (102782056)
- gui ec07a930c025a43dd315db2a173ff5c397a08682b8207507e35a0aa4bd879634 (157136515)

## 未验证限制（保留）
- Windows / macOS / ARM native 运行时未在原生硬件验证。
- GUI 正常用户退出与真实 native GUI 未演示。
- macOS-13 hosted runner 已退役，native 最低 OS 未验证。

## 未做（按契约）
- 未改产品源码/锁/测试；未 commit/push；未改 Trellis 全局状态。
- 未修改 `/tmp/integrated_tui_smoke.py`、`/tmp/integrated_frozen_compress_smoke.py`（94 代理独占）。
- TUI/GUI frozen interactive smoke 未执行，留主代理在 `/tmp/integrated-final-build22/extract/*` 上跑真实 UI 回归。
