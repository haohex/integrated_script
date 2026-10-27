<!-- TRELLIS:START -->
# mini-trellis

This project uses mini-trellis as a memory layer. Working knowledge lives under `.trellis/`:

- `.trellis/spec/` — durable contracts (short markdown; read `index.md` first)
- `.trellis/research/` — topic inbox (`<topic>.md`; `README.md` is not a topic)
- `.trellis/workspace/` — per-developer journals

Record a session with `/mini-trellis:remember` (Claude/OpenCode), `/mini-trellis-remember` (Pi), or `$mini-trellis-remember` (Codex). When earlier decisions or relevant project rules are needed, use `mini-trellis mem recall "<topic or path>"`; expand evidence with `mini-trellis mem read "<ref>"`. No search is required for unrelated work. Promote lasting boundaries into spec with `mini-trellis-update-spec`.

Record only confirmed decisions, reusable research findings, or the session/compact handoff. Skip ordinary turns and unconfirmed guesses. New installs write notes without an automatic git commit; use `mini-trellis doctor` to check host wiring and `mini-trellis refresh --dry-run` before refreshing assets.

Keep confirmed rules short and faithful. Unconfirmed scope, exceptions, and implementation choices stay open or are labeled as inference, not added to the contract.

For a confirmed update, follow this short order: read the existing topic; edit that file; read it back and check the new rule, limits, and negations; run `python3 ./.trellis/scripts/add_session.py --title "..." --summary "..." --topic <actual-topic-path>`; read the journal and check its topic link. Journal-only success is not topic success; report partial writes accurately. New notes follow the requested or discussion language; updates preserve the document language.

When recall excerpts already answer the question with source and qualifiers, cite them and stop. Expand only missing context; do not repeat a lookup or fall back to dialogue-only `search` merely to reconfirm sufficient evidence.

mini-trellis does not create or drive tasks.

Managed by mini-trellis. Edits outside this block are preserved.
<!-- TRELLIS:END -->

<!-- dispatch:begin -->
## Dispatch

主会话可以是 Claude 或 Codex，worker 通过 Herdr 派发（dispatch skill）。角色和模型以 dispatch skill 为准，这里只写本项目的特有部分。

**默认派发**：在本项目中，涉及 Python 业务逻辑或终端交互代码的实现任务，包括 plan 模式批准后的执行阶段，主会话都默认使用 dispatch skill 派发给 worker，不需要用户另外说明。规划方案时，按 be（实现和单元测试）、bt（只读评审、集成测试和完整验收）拆分；本项目无独立前端，不启动 fe。

以下情况由主会话自己完成，不派发：

- 用户说"你自己做"或"不要派发"
- 小改动，写任务卡比直接修改还费事
- 安全、鉴权、支付、数据迁移、删除数据、CI 或部署相关的任务
- 当前不在 Herdr 中（`HERDR_ENV` 不等于 1）

项目配置：

- 后端目录：`src/integrated_script/`（含 `ui/` 终端交互层）、根入口 `main.py`；单元测试 `tests/unit/` → be。本项目是本地 Python CLI 工具，无后端服务。
- 前端目录：无（没有 Web 或独立图形前端；终端交互层随 Python 代码交给 be）。
- 集成测试：`tests/integration/`（处理器集成）、`tests/cli/`（CLI 冒烟） → bt
- 共享契约：`src/integrated_script/contracts/`（`results.py` 结果模型、`errors.py` 错误归一化）、`src/integrated_script/config/exceptions.py`（异常定义）、`README.md`（功能与输入输出约定）；无 OpenAPI/proto（不提供网络服务接口）。契约只由主会话修改。
- 后端验收：在项目根目录使用已有 `.venv`，逐条执行以下命令（对应 CI `make check-all` 的检查项，不同步或安装依赖；缺少环境或工具时报告无法运行）：
  - `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m flake8 --max-line-length=120 --extend-ignore=E203,W503 src/integrated_script tests/`
  - `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m black --target-version py310 --check src tests main.py build_exe.py`
  - `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m isort --check-only src tests main.py build_exe.py`
  - `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m mypy --cache-dir=/dev/null src/integrated_script`
  - `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m pytest -p no:cacheprovider tests/`
- 前端验收：无（无独立前端；终端交互单元测试及 CLI 冒烟测试包含在上述 pytest 完整套件中）。
- 禁区：`.github/`、`.env*`
- 隔离：默认共用工作区；前后端会改同一批文件时使用 herdr worktree
- 任务卡：`.dispatch/tasks/`（已加入 .gitignore）
<!-- dispatch:end -->

