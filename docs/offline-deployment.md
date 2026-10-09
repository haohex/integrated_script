# 离线交付与部署说明

本文档描述集成脚本工具（Integrated Script）的**离线可执行产物**：如何在联网的构建机
上构建、如何在无网络的目标机器上安装运行，以及各平台已知限制。

> 结论先行：构建机可以联网（用于安装依赖）；**产物在目标机器完全离线运行，不需要
> 安装 Python、不需要联网下载任何内容**。所有资源（配置模板、图标、许可证）都随产物
> 一起分发。

---

## 1. 支持平台

| 平台 | 架构 | TUI | GUI | 说明 |
| --- | --- | --- | --- | --- |
| Windows 10 / 11 | x64 | ✅ | ✅ | GUI 使用无控制台窗口入口 |
| Ubuntu 22.04 | x64 | ✅ | ✅ | 最低 glibc 基线（构建机固定 22.04） |
| Ubuntu 24.04 | x64 | ✅ | ✅ | 使用 22.04 基线产物，容器 TUI 实际操作已验证；GUI 原生验证待补 |
| Ubuntu 22.04+ | arm64 | ✅ | ❌ | 仅 TUI；使用云端 `ubuntu-22.04-arm` 原生构建 |

本次 `v3.0.1` 按用户要求仅发布 Linux、Windows 包，暂不提供 macOS 包。表格描述交付范围；实际运行证据见第 10 节。

Python 基线为 **3.11**。源码运行需要 Python 3.11+；离线产物自带 Python 运行时。

### 构建环境局限

- **Windows 产物**：使用原生 `windows-2022` 云端 runner 构建和实际运行；这不等同于 Windows 10/11 物理设备验收。当前运行状态见第 10 节。
- **Linux arm64**：使用 GitHub 托管 ARM64 runner，避免依赖仓库自托管机器。
- **Linux x64**：CI 固定 `ubuntu-22.04` 以取最低 glibc；在较新主机（如 Ubuntu 26.04 /
  glibc 2.43）上构建会把 glibc 下限抬高，**不保证在旧系统运行**。原因见下节。

### 较新 Linux 主机产物不保证旧系统

PyInstaller 的 `_internal/` 会随附构建主机的 `libstdc++.so.6`。例如在 Ubuntu 26.04
（glibc 2.43）构建的产物，其 `_internal/libstdc++.so.6` 可能要求 `GLIBC_2.38`，在
Ubuntu 22.04（glibc 2.35）上会因缺少符号而无法启动。因此**不要宣称在本机较新发行版
上构建的包满足 22.04**。

如需在较新主机上产出兼容 22.04 的包，请使用 CI 的 `ubuntu-22.04` runner，或在
隔离的 Ubuntu 22.04 容器/虚拟机内构建。先准备 `uv`、`binutils` 和第 7 节的图形运行库，
然后在该环境的源码副本中执行（不要复用较新主机的虚拟环境或系统动态库）：

```bash
uv python install 3.11.15
uv venv --python 3.11.15 .venv-build
uv pip install --python .venv-build/bin/python -r requirements-build-gui.txt
uv pip install --python .venv-build/bin/python --no-deps -e .
.venv-build/bin/python build_exe.py --mode all
.venv-build/bin/python scripts/verify_artifacts.py prepare --platform linux --arch x64 --tag v3.0.1
```

> 这些命令会创建虚拟环境、构建缓存、包元数据及 `dist/` 产物，建议使用专用构建目录。
> 安装包验证时再关闭网络；构建阶段本身允许下载依赖。

---

## 2. 启动入口

| 场景 | 命令 |
| --- | --- |
| 默认（终端界面 TUI） | `integrated-script` |
| Qt 桌面界面 | `integrated-script-gui` |
| 桌面界面（源码） | `python main.py --gui` |
| 旧交互式命令行（回退） | `integrated-script --legacy-cli` |
| 源码默认入口 | `python main.py` |

离线产物中：

- TUI：`dist/integrated_script/integrated_script`（Windows 为 `.exe`）
- GUI：`dist/integrated_script_gui/integrated_script_gui`（Windows 为 `.exe`，无控制台窗口）

TUI 入口**不包含 Qt**，可在没有 Qt 的机器上直接运行。GUI 为显式独立产物。

---

## 3. 依赖分层

`pyproject.toml` 是唯一依赖来源，`requirements-*.txt` 是 uv 生成的可复现锁定文件：

| 文件 | 用途 | 内容 |
| --- | --- | --- |
| `requirements.txt` | 人类阅读的宽松运行期约束 | 核心 + TUI，不含 Qt |
| `requirements-runtime.txt` | 运行期精确锁定 | 核心 + Textual + platformdirs |
| `requirements-build.txt` | 构建 TUI 离线产物（无 Qt） | 运行期 + PyInstaller（跨平台 markers） |
| `requirements-build-gui.txt` | 构建 GUI 离线产物（仅 modes 含 gui） | build + 固定 `PySide6==6.8.3` |
| `requirements-dev.txt` | 开发 / 界面测试 | dev + dev-ui + gui |
| `requirements-acceptance.txt` | 云端验收控制器 | PTY / ConPTY 和图像检查；不进入软件包 |

重新生成：`make lock`（生成前三个）与 `make lock-gui`（生成 GUI 构建锁），均需要 `uv`。
锁定文件使用 `uv pip compile --universal`，因此同时包含 Windows/macOS/Linux 的
PyInstaller 依赖（`pefile`、`pywin32-ctypes`、`macholib` 等平台 markers）；TUI 构建
只安装 `requirements-build.txt`，**不会引入 Qt**。GUI 构建锁固定 `PySide6==6.8.3`。
所有安装均为构建机联网阶段完成的静态锁定，产物运行期不联网。

源码开发用户按需安装：

```bash
pip install -e .          # 默认 TUI + 核心
pip install -e .[gui]     # 追加 Qt 桌面界面
```

> 默认安装**不会**强制 Qt：没有 Qt 时 TUI、核心处理与旧交互界面仍可正常工作。

---

## 4. 构建离线产物

```bash
# TUI 产物（不含 Qt）
pip install -r requirements-build.txt
python build_exe.py --mode tui

# GUI 产物（安装固定版本 PySide6==6.8.3）
pip install -r requirements-build-gui.txt
python build_exe.py --mode gui

python build_exe.py --mode all     # 依次构建两者（需先装 GUI 构建锁）
```

- 产物为 **onedir**（目录形式），便于携带资源与排查问题。
- 冻结入口在解析参数、启动 Qt 之前调用 `multiprocessing.freeze_support()`，
  以保证图片压缩的进程池在打包环境中正确工作。
- 构建脚本会校验产物：拒绝把 `tests/`、`fake_service`、设计截图或 Qt 组件打进 TUI。
- 构建脚本**不会**上传、发布或删除用户目录中的任何内容。

打包为分发包：

```bash
python scripts/package_artifacts.py --mode tui --platform linux \
    --arch x64 --tag v3.0.1                  # 默认输出 dist/artifacts/
```

CI 上传目录同为 `dist/artifacts/`（已在 `.gitignore` 中忽略）。

命名：

```
integrated-script-<tag>-windows-x64-tui.zip
integrated-script-<tag>-windows-x64-gui.zip
integrated-script-<tag>-linux-x64-tui.tar.gz
integrated-script-<tag>-linux-x64-gui.tar.gz
integrated-script-<tag>-linux-arm64-tui.tar.gz
```

---

## 5. 随产物分发的资源与许可证

| 资源 | 位置 | 说明 |
| --- | --- | --- |
| 默认配置模板 | `config/default_config.yaml` | 离线自带，不依赖网络 |
| 本地 SVG 图标 | `integrated_script/assets/icons/*.svg` | Fluent System Icons |
| 图标许可证 | `integrated_script/assets/icons/LICENSE` | MIT，Microsoft Corporation |
| 项目许可证 | `LICENSE` | MIT |

- 不包含任何设计截图、测试代码、fake 服务或开发工具。
- 不使用 Web 字体、Emoji 导航或在线主题。
- 图标为本地文件，运行期不发起网络请求。

---

## 6. 配置与用户数据

- 配置、日志、缓存写入 **用户目录**（由 `platformdirs` 解析），不再默认写入当前工作目录：
  - Windows：`%LOCALAPPDATA%\IntegratedScript\integrated_script`（当前 `platformdirs` 默认非 roaming 配置）
  - Linux：`~/.config/integrated_script` 等 XDG 目录
  - macOS：`~/Library/Application Support/integrated_script`
- 显式 `--config <path>` 始终优先。
- **旧配置导入**：首次运行若当前目录存在旧 `config.json`，界面会询问是否导入；
  无论是否导入，**原文件都保留**，不会静默迁移或删除。
- 卸载产物只需删除解压目录；如需清理用户数据，请手动删除上述目录。
  构建脚本不会执行任何清理用户目录的操作。

---

## 7. Linux 图形依赖

TUI 只需要一个可用的终端。GUI（PySide6 / Qt）需要系统图形库，Ubuntu 基线：

```bash
sudo apt-get install -y libgl1 libegl1 libxkbcommon-x11-0 libxcb-cursor0 \
    libxcb-icccm4 libxcb-keysyms1 libxcb-shape0 libdbus-1-3 \
    libfontconfig1 libfreetype6 fonts-noto-cjk
```

- 无显示环境（CI / 服务器）下运行 GUI 测试需设置 `QT_QPA_PLATFORM=offscreen`。
- 中文界面建议安装 `fonts-noto-cjk`，否则可能出现方块字。
- 桌面集成示例见 `scripts/linux/*.desktop`。

---

## 8. 签名与真实性限制

- Windows 产物暂未配置 Authenticode 签名，系统可能显示未知发布者。
- 从本项目 GitHub Release 下载，使用随附 `SHA256SUMS.txt` 检查完整性。`BUILDINFO-*.json` 记录构建提交、版本和依赖；校验和不等同于代码签名。

---

## 9. 快速自检

```bash
# 冻结产物可用性（不进入界面）
./dist/integrated_script/integrated_script --version
./dist/integrated_script/integrated_script --help

# 旧界面回退
./dist/integrated_script/integrated_script --legacy-cli

# 打包相关单元测试
python -m pytest tests/unit/test_offline_packaging.py -q
```

离线验证要点：在**断网**机器上解压产物，直接运行上述命令；启动后执行一次
图片格式转换或图像信息统计，确认无需联网即可完成。

---

## 10. 平台验证状态

| 平台 | 构建 | 运行冒烟 | 状态 |
| --- | --- | --- | --- |
| Ubuntu 22.04 x64 | ✅ 隔离的 22.04 环境实际构建 | ✅ 最终压缩包解压后断网、无 Python、只读安装目录；TUI 创建标签、PNG→JPEG、1,001 张图片压缩并正常退出；GUI 离屏启动 | Linux 基线验收通过，见验证记录 |
| Ubuntu 24.04 x64 | 使用 22.04 基线产物 | ✅ 容器内断网 TUI 创建标签及 PNG→JPEG、正常退出 | TUI 容器验收通过；GUI 原生桌面待验证 |
| Windows x64 | CI 原生 runner | ❌ 未执行 | 未验证 |
| Linux arm64 | 云端 `ubuntu-22.04-arm` 原生 runner | ❌ 本阶段待执行 | 未验证 |

## 11. v3.0.1 发布门禁

先通过本地 `make check-all`，再推送开发分支。`Build Artifacts` 在开发分支执行 Linux/Windows 质量检查、原生 GUI 缩放验收、构建、归档校验、解压及真实 GUI/TUI 操作；Linux 通过隔离网络命名空间运行，Windows 为被测程序设置出站阻断规则。测试数据和用户状态全部位于临时目录。

只有开发分支检查和外观复核通过后才合并 PR。版本标签触发同一门禁，全部通过后自动发布五个软件包、校验和与构建信息。CI 的 `acceptance-*` 附件包含实际截图和运行 JSON；工作流配置本身不表示已经运行成功。

普通用户直接选择发布页的 `windows-x64-gui.zip` 或 `linux-x64-gui.tar.gz`，完整解压后运行其中的 `integrated_script_gui`；终端用户选择 `tui` 包。不要只移动单个可执行文件或删除 `_internal` 目录。

未列出的运行结果不得宣称已验证。GUI 的离屏启动不代替 Windows/macOS 的原生外观、
高 DPI、系统文件对话框和签名验证。具体命令、产物和限制见 [验证记录](verification-report.md)。
