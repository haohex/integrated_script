# 验证报告

当前发布验收日期：2026-10-09。v3.0.1 已进入开发分支云端验收：Linux x64 GUI/TUI 和 Linux ARM64 TUI 已实际构建并通过离线运行；Windows 高缩放布局修复正在复核。PR 尚未合并，Release 尚未发布。下文 2026-10-08 的包与哈希为历史基线，不作为本次新版本的发布包。macOS 包已按用户要求排除。

## v3.0.1 发布门禁

- 本地隔离锁定环境 Python 3.11.15、PySide6 6.8.3、Textual 8.2.8：Windows 高缩放布局和日志入口修复后，`make check-all` 退出码 0，438 passed、7 skipped（13.66 秒）。flake8、black（141 文件）、isort、mypy（85 源文件）通过。7 项跳过仍来自缺失的既有 `.claude` 发布文档。
- 新增小屏幕窗口框架完整包含、结果页日志访问和任务间日志隔离回归；完成/失败后隐藏进度面板，日志保留在结果页的“执行日志”选项卡并可复制。
- 新 PTY 控制器在历史 Ubuntu 22.04 构建包上真实验证空标签、PNG→JPEG、1,001 张 PNG 压缩，全部核对文件格式/尺寸/数量，三次正常退出码 0。此次控制器演练运行在 WSL 主机，未宣称断网；历史容器证据另列于下方。
- 原 GUI 冒烟脚本将截图/按键发送代替输出验证、将 SIGTERM -15 算作正常退出的结果已被拒绝。新脚本要求两个真实空标签、截图及界面关闭后的退出码 0，缺失输出或非交互环境必须失败。
- 冻结版本读取改为包内元数据，避免读取安装目录上层源码仓库的版本号。增加回归测试。
- Antigravity 负责界面、键盘/缩放修复与严格 GUI 验收；Pi 已完成共享后端。Pi 本阶段上游服务连续返回 400 后，主代理接管 CI、归档验证及 TUI 控制器。
- 用户已授权开发分支推送、通过云端门禁后的 PR 合并及 v3.0.1 自动发布。云端原生运行结果与发布下载链接将在完成后补录；配置工作流不等于运行成功。

## 开发分支实际云端证据

开发分支提交 `32a34bc042d5b7220032746d23ee46bec039cf30` 的 [构建与运行记录](https://github.com/haohex/integrated_script/actions/runs/37931604487) 和 [独立质量门禁](https://github.com/haohex/integrated_script/actions/runs/37931604084) 已完成。以下是该提交的实际结果；后续界面修复必须重新通过门禁，不能沿用旧提交结果放行。

| 检查 | 实际结果 | 尚未验证范围 |
| --- | --- | --- |
| Linux / Windows 完整质量门禁 | 两个平台均通过 lint、格式、类型检查与单元/集成测试 | Windows 单元测试使用 offscreen；原生界面另验 |
| Ubuntu 22.04 x64 冻结 TUI | 归档重新解压后完成空标签、PNG→JPEG、1,001 张 PNG 压缩；全部核验实际输出并正常退出 0；子进程 PATH 无 Python，使用独立网络命名空间断网 | 代表操作，不是每项功能的大规模数据验收 |
| Ubuntu 22.04 x64 冻结 GUI | 原生 X11 自动操作产生 2 个真实空标签，截图及输出核验通过，用户窗口关闭后退出 0；使用同样的断网和子进程 PATH 隔离 | Xvfb 自动桌面，不是物理桌面人工验收 |
| Ubuntu 22.04 ARM64 冻结 TUI | 云端原生 ARM64 构建；三个操作及 1,001 个压缩输出通过；断网、子进程 PATH 无 Python、正常退出 0 | 未提供 ARM64 GUI |
| Windows Server 2022 原生 GUI | 100% / 125% 的真实空标签和 PNG→JPEG 操作通过；150% 窗口超出可用屏幕导致验收失败，修复尚须在原生 runner 重新验证 | 应用 `QT_SCALE_FACTOR` 缩放，不能宣称物理 Windows 10/11 设备 DPI 验收 |
| Windows 冻结 GUI/TUI | 原生布局门禁失败，构建及运行步骤未执行 | 尚无本次版本的 Windows 离线包运行证据 |
| Ubuntu 24.04 冻结运行 | 因 Windows 矩阵失败，本轮下游验收跳过 | 必须补齐真实运行结果 |

验收诊断和截图位于该运行的 `acceptance-linux-x64`、`acceptance-linux-arm64`、`acceptance-windows-x64` 制品；[PR #1](https://github.com/haohex/integrated_script/pull/1) 保持 draft。

## 环境与比较基线

- 仓库比较基线：`dede867`，包括本次新增未跟踪文件；保留会话前已有的 `.gitattributes`、`.agents/`、`.codex/`、`.trellis/` 改动。
- 源码验收环境：WSL2 Linux x64，Ubuntu 26.04 / glibc 2.43；隔离虚拟环境 Python 3.11.15、PySide6 6.8.3、Textual 8.2.8。
- Linux 离线构建基线：独立 Ubuntu 22.04 环境，Python 3.11.15，使用锁定依赖。主机 26.04 构建的旧包不能证明兼容 22.04。
- 分工：Antigravity 实现桌面/TUI、设计与截图；Pi 实现共享应用层、跨平台运行时和打包；主代理决定公共契约、整合并验收。

## 已有基线证据（2026-09-30）

| 检查 | 实际结果 | 限制 |
| --- | --- | --- |
| 原有回归基线 | 271 passed、7 skipped | 7 项跳过来自既有缺失 `.claude` 发布文档检查 |
| 新架构完整门禁 | 一轮 `make check-all`：388 passed、7 skipped，lint/format/mypy 通过 | 后续新增构建参数与系统主题修复后需要最后重跑 |
| 真实 AppService | 临时中文 CTDS 目录转换、数据验证、拒绝清理后孤儿图片保留 | 不是所有操作都做了大规模数据验收 |
| 后台压缩 | Qt 事件循环下 1,001 张 PNG、2 个工作进程、全部输出，1,003 条进度事件 | 此项为源码运行证据 |
| Ubuntu 22.04 冻结包 | 断网、只读根目录、无系统 Python 下 TUI/GUI 版本命令成功；GUI offscreen 保持事件循环 | 退出码 124 来自验收限时结束，不是正常 GUI 退出证据 |
| 冻结 TUI 真实操作 | 中文和空格路径中创建空标签、PNG 转 JPEG，退出码 0 | 最终新包尚须重新解压并验证 |

## 历史收尾验收（2026-10-08，v3.0.0）

| 检查 | 实际结果 |
| --- | --- |
| 主题与截图工具 | UI 套件 47 passed；系统 light/dark 信号、明确选择保护、Unknown 回退、结果状态保持、无 Qt 导入、正常/异常和冷启动临时目录隔离均有回归用例 |
| 稳定源码完整门禁 | 新 XDG 环境下 `make check-all` 退出码 0：420 passed、7 skipped（18.68 秒）；flake8 / black（134 文件）/ isort / mypy（85 源文件）均通过 |
| Ubuntu 22.04 构建 | GUI/TUI 构建与归档退出码 0；Python 3.11.15、glibc 2.35，123/123 源文件 SHA-256 与当前源码匹配 |
| 最终归档完整性 | 两个 tar.gz、BUILDINFO.json 和源码清单的 SHA256SUMS 独立核对全部通过；解压保留符号链接 |
| Ubuntu 22.04 TUI | 最终包解压后，中文空格路径中空标签与 PNG→JPEG，退出码 0；1,001 张 PNG 多进程压缩，数量/格式/尺寸/成功状态全部通过，退出码 0，耗时 136.2 秒 |
| Ubuntu 24.04 TUI | 同一最终包在容器中完成空标签与 PNG→JPEG，退出码 0，耗时 21.2 秒 |
| Ubuntu 22.04 GUI | 最终包 `--version` / `--help` 退出码 0；offscreen 保持事件循环，容器内 8 秒超时退出码 124，无 Traceback 或 Qt 插件错误；不等同于原生桌面交互或正常用户退出 |

上述容器使用 `--network none --read-only --tmpfs /tmp`，包挂载为只读，测试数据在临时可写目录，目标环境没有系统 Python。配置、缓存和日志通过 XDG 指向临时可写目录；生产使用需要可写用户目录。GUI 验收在容器内设置超时，避免只给 Docker 客户端发终止信号后留下 GUI 进程。

真实按键脚本现已验证焦点、搜索树重建和已选操作，解决之前自动化把路径填到 CTDS 默认表单的问题。压缩的第一轮外层 90 秒超时已被完整的 300 秒限时复核取代；136.2 秒记录确认任务真实成功并正常退出。仅清理本任务临时验收容器。

最终产物位于 `dist/artifacts/`：

| 文件 | 大小 | SHA-256 |
| --- | --- | --- |
| `integrated-script-v3.0.0-linux-x64-tui.tar.gz` | 102,782,056 字节 | `54ae6f4d9cb3978baec653953e0ee5519b7acaeab6071c155eb204930a48a66f` |
| `integrated-script-v3.0.0-linux-x64-gui.tar.gz` | 157,136,515 字节 | `ec07a930c025a43dd315db2a173ff5c397a08682b8207507e35a0aa4bd879634` |

构建信息与 123 个源文件哈希见 `dist/artifacts/BUILDINFO.json` 和 `source-manifest-final.json`。

最终门禁使用 `.venv`，将 `PATH` 指向 `.venv/bin`、`QT_QPA_PLATFORM=offscreen`，并将 XDG 配置、日志、缓存与数据目录指向新建临时根，再执行 `make check-all`。7 项跳过仅因既有 `.claude/commands/release.md` 和 `.claude/skills/release/SKILL.md` 不存在。真实界面测试已显式注入临时 `ConfigManager` 和工作目录，修复了首次全量验收等待旧配置导入弹窗的问题；正常应用的导入确认行为保留。

## 历史视觉证据与平台限制

[截图与设计验收](design/visual-acceptance.md)提供 Linux Qt offscreen PNG 和 Textual SVG。操作目录来自真实 AppService；运行进度、确认和成功/失败报告使用人工构造的展示状态，不代表截图中的 15,200 张图片已经实际处理。

| 平台 | 当前证据 |
| --- | --- |
| Ubuntu 22.04 x64 | 最终基线包真实隔离构建、无 Python 断网 TUI 实际操作和 GUI offscreen 启动通过；原生桌面文件对话框未实机检查 |
| Ubuntu 24.04 x64 | 最终包的容器 TUI 实际操作通过；GUI 原生桌面未验证 |
| Windows 10/11 x64 | 当时仅有 GUI windowed 入口、图标及构建配置；本次 Server 2022 云端证据见上方新版本记录 |
| macOS Intel / Apple Silicon | 早期设计曾包含 `.app`；当前发布范围按用户要求排除 macOS 包 |
| Linux ARM64 TUI | 当时尚未实际构建运行；本次已改用云端原生 ARM64 runner 并验收通过，见上方记录 |

## 已知验收副作用

前端代理在验证隔离时，曾将真实 `~/.config/integrated_script/theme_preference.json` 写为 `light`。主代理随后停止该任务并收紧验证边界。先前值未被可靠记录，因此没有猜测恢复或删除用户文件；后续验证必须使用临时目录中的模拟用户配置。

上方历史基线记录于提交、推送和发布之前。当前发布阶段见本文 v3.0.1 门禁记录；构建与部署方式见 [离线部署说明](offline-deployment.md)，设计取舍与官方参考见 [架构文档](architecture.md)。
