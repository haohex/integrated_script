# Journal - luohao (Part 1)

> AI development session journal
> Started: 2026-09-30

---



## Session 1: 离线 GUI/TUI 架构实施与最终验收
<!-- trellis-session: v=2 fp=9bb15eabe019aca2 -->

**Date**: 2026-10-08
**Task**: 离线 GUI/TUI 架构实施与最终验收
**Branch**: `master`

### Summary

Antigravity 完成 GUI/TUI 与主题和隔离；Pi 完成共享运行时、路径与离线打包。Linux 最终包真实断网操作通过，完整门禁 420 passed/7 skipped。

### Main Changes

- 共享 AppService 驱动 GUI/TUI，保留原处理器行为和旧 CLI 回退
- Qt 桌面主题、表单、结构化结果与 Textual 导航；所有前端由 Antigravity 实现
- Pi 完成 Ubuntu22 基线离线 GUI/TUI 包、资源、锁与原生 CI 配置

### Git Commits

(No commits - planning session)

### Testing

- [OK] 新 XDG 环境 make check-all exit0：420 passed,7 既有发布文档 skip；lint/format/mypy 通过
- [OK] 最终解压包 Ubuntu22 TUI 两操作及1001 PNG压缩正常退出；GUI offscreen 启动通过
- [OK] 最终包 Ubuntu24 容器 TUI 两操作正常退出；123源文件hash和分发SHA256SUMS核对通过

### Status

[OK] **Completed**

### Next Steps

- Windows/macOS/ARM 原生构建、GUI 外观/DPI 和最低系统版本仍待验证
- 用户未授权提交或发布，保留工作区与任务记录，不自动归档


## Session 2: 离线桌面与 TUI 重构完成并发布 v3.0.1
<!-- trellis-session: v=2 fp=a559a3c1e43f03b7 -->

**Date**: 2026-10-10
**Task**: 离线桌面与 TUI 重构完成并发布 v3.0.1
**Branch**: `dev/offline-desktop-tui`

### Summary

完成共享应用架构、原生路径、GUI/TUI与离线分发；开发分支验收后合并PR1并自动发布v3.0.1，全部正式下载资产已核验。

### Main Changes

- Antigravity实现界面；Pi实现共享后端；Pi持续upstream400后主代理接管CI/编码收尾及最终验收。
- 原算法、默认值、输出格式与旧CLI回退保留；发布Windows/Linux x64 GUI/TUI及Linux ARM64 TUI共5包，不提供macOS包。

### Git Commits

| Hash | Message |
|------|---------|
| `01315aa542d7beb4b47baa18530b9bb96b91bcff` | test: 等待真实后台任务完成并校验空标签输出 |
| `72f8d43819c6341c93e1285a9050c54140fb7716` | Merge pull request #1 from haohex/dev/offline-desktop-tui |

### Testing

- [OK] 隔离make check-all：465passed7skipped，lint/black144/isort/mypy85全部通过；Windows云端464passed8skipped0failures。
- [OK] 开发运行38014994017和Release38015844945全部成功；实际Windows截图及五档应用缩放通过，7份正式运行报告输出/正常退出全部核验。
- [OK] 实际下载12个Release资产，5个归档、4个原始SHA256清单、3个BUILDINFO与合并SHA72f8d43全部匹配；PE GUI2/TUI3和内置Python资源正确。

### Status

[OK] **Completed**


## Session 3: 标注 offline-desktop-tui 归档已回退
<!-- trellis-session: v=2 fp=d571e5447ce43915 -->

**Date**: 2026-10-27
**Task**: 标注 offline-desktop-tui 归档已回退
**Branch**: `master`

### Summary

PR #2 回退了共享 GUI/TUI 与跨平台离线发布架构，代码恢复到 dede867。在 offline-desktop-tui 主设计和 3 个子任务归档的 design.md 中加入已回退标注及重新引入的方法（先 revert f8d6876）。
Topics: [.trellis/research/archive/2026-10/09-30-offline-desktop-tui/design.md](../../research/archive/2026-10/09-30-offline-desktop-tui/design.md)

### Git Commits

(No commits - planning session)

### Status

[OK] **Completed**


## Session 4: 合并数据集：引号路径与文件名冲突前缀规则
<!-- trellis-session: v=2 fp=be67f61ea27e2535 -->

**Date**: 2026-10-27
**Task**: 合并数据集：引号路径与文件名冲突前缀规则
**Branch**: `fix/merge-dataset-input`

### Summary

在 .worktrees/merge-fixes 分支 fix/merge-dataset-input 完成两项（未合入 master）：选项8/9路径输入去成对引号；收集路径后先检查兼容性和文件名冲突（stem 不区分大小写），无冲突保留原名，有冲突强制前缀、留空取消，统一 前缀_00001。处理器 image_prefix=None 表示保留原名，无前缀且冲突时拒绝。README §6.1.7 已同步。

### Git Commits

| Hash | Message |
|------|---------|
| `475fcbe` | fix: 合并数据集时识别带引号的路径 |
| `019d4dc` | feat: 合并数据集按文件名冲突决定是否强制图片前缀 |

### Testing

- [OK] flake8/black/isort/mypy 通过；pytest 301 passed 7 skipped；/tmp 端到端冒烟通过

### Status

[OK] **Completed**

### Next Steps

- 用户确认后把 fix/merge-dataset-input 合入 master 并清理 worktree；bt 建议#2（交互流程多一轮图片扫描）按决定未做
