# Approved implementation design

> **已回退（2026-10-27）**：本设计对应的实现经 PR #1 合并（`72f8d43`，即 v3.0.1），
> 随后由 PR #2（`f8d6876` / 合并 `01be19a`）整体回退，master 代码恢复到 `dede867`。
> 当前 master 中不存在 `application/`、`ui/desktop/`、`ui/tui/` 等本文描述的代码；本文仅作历史记录。
> 如需重新引入，须先 revert `f8d6876`，直接重新合并 `dev/offline-desktop-tui` 不会生效。

## Layers and ownership
`ui/desktop` and `ui/tui` -> `application` (operations, orchestration, runner) -> existing workflows/processors -> core path/progress/config adapters. No frontend imports of processors/business rules. Existing contracts.results.OperationResult preserved. Core never imports Qt/Textual. Legacy interactive UI remains regression fallback.

- Pi owns application/, new contracts, core/, config/, processors/ progress hooks, workflows/, main.py entrypoints, pyproject/requirements/locks, Makefile/build scripts/CI, backend tests, README offline instructions. May edit legacy ui/interactive.py for compatibility, not new display design.
- Antigravity owns ui/desktop/, ui/tui/, ui/shared/ (presentation only), assets/, tests/ui/, docs/design/, screenshot scripts/artifacts. No backend/contracts/manifests changes.
- Main owns task artifacts, interface decisions/review; no concurrent worker-file edits.

## Frozen integration contract
Public exports in `integrated_script.application` (implement exactly; private helpers free):

```python
@dataclass(frozen=True)
class ParameterSpec:
    name: str
    label: str
    kind: str = 'str'  # str, text, path, paths, int, float, bool, choice
    default: Any = None
    required: bool = False
    choices: tuple[tuple[str, Any], ...] = ()  # (display label, value)
    help: str = ''

@dataclass(frozen=True)
class OperationSpec:
    id: str
    category: str  # Chinese label; original order
    label: str
    description: str
    fields: tuple[ParameterSpec, ...] = ()
    destructive: bool = False

@dataclass(frozen=True)
class InteractionRequest:
    id: str
    title: str
    message: str
    fields: tuple[ParameterSpec, ...] = ()
    kind: str = 'input'  # input, confirm
    details: tuple[str, ...] = ()

@dataclass(frozen=True)
class TaskEvent:
    task_id: str
    kind: str  # started, progress, log, interaction, completed
    message: str = ''
    current: int | None = None
    total: int | None = None
    interaction: InteractionRequest | None = None
    result: OperationResult | None = None

class AppService:
    def __init__(self, config: ConfigManager | None = None, *, working_directory: Path | None = None): ...
    def list_operations(self) -> tuple[OperationSpec, ...]: ...
    def start(self, operation_id: str, values: dict[str, Any]) -> str: ...
    def poll_events(self) -> list[TaskEvent]: ...
    def respond(self, task_id: str, request_id: str, values: dict[str, Any]) -> None: ...
    @property
    def busy(self) -> bool: ...
    def close(self) -> None: ...
```

start returns immediately, rejects concurrent start with ValueError. Worker owns validation, preflight and processing; errors become completed OperationResult.failure. payload preserves all real legacy result fields, UI renders nested data rather than dropping it. paths/list-like text accept newline strings, service owns splitting/coercion. bool/choice widgets return actual Python values.

Worker posts InteractionRequest then waits on per-task condition/queue. Frontends poll on timer and respond; confirm uses {'confirmed': bool}, input uses field mapping; dismissal {'_cancelled': True}. False/dismissal prevents subsequent writes. Responses match task/request; reject stale responses. Editing initial params requires fresh operation/confirmation. No forced cancel; UI refuses close during execution, allows dismissal of waiting input. close must not abandon writing task.

Antigravity implements `ui.desktop.app.run_gui(service: AppService | None = None) -> int` and `ui.tui.app.run_tui(service: AppService | None = None) -> int`. Pi wires main/gui_main with lazy imports. TUI never imports Qt. --legacy-cli fallback, default TUI, existing flags maintained.

## Paths/config/progress
AppPaths uses platformdirs user config/log/cache; --config overrides. Keep legacy ConfigManager default API if tests rely on it, application bootstrap explicitly uses user path. New config absent + old cwd config present: shared import confirmation, original preserved. Relative paths against captured cwd; paired outer quotes/home expansion; preserve valid POSIX backslash filenames and symlink semantics. Foreign drive/UNC on POSIX produces actionable error, no guessed mapping. No unrelated filename algorithms changes.

Progress covers core wrappers AND direct image tqdm/mp channels; route to active worker, preserve legacy terminal sink otherwise. No global stdout monkeypatch. Events carry task_id; don't print into TUI. Config missing bundled YAML must not silently change existing effective defaults.

## Visual contract
Native title bar; restrained blue/gray. Light bg #F3F3F3/surface #FFFFFF/text #1B1B1B/accent #0067C0; dark bg #202020/surface #2C2C2C/text #F3F3F3/accent #4CC2FF. System fonts with Chinese fallback (Qt APIs, not CSS stacks). 4/8/12/16/24 spacing, body ~14 logical pixels/captions >=12/headings ~20, controls ~32 growing with font, 4-6 radius, visible focus. Local Fluent System Icons with license, no emoji/web-fonts/dashboards. Navigation categories + operations + structured form + progress/result. Only actual result counts, unknown total indeterminate. Long paths accessible/copyable. Native file dialogs, working Qt fallback on Linux. Theme system/light/dark saved separately from business config. Default1200x780, compact980x600, clamp to smaller screen and scroll. TUI supports80x24 with compact navigation, scrolling/shortcuts. Esc never force-cancels writes. Windows GUI windowed, TUI console.

## Packaging
Python3.11 build baseline; PySide6 6.8 series/Textual/platformdirs locked with existing business deps. GUI onedir; TUI excludes Qt. Native OS/arch builds; Windows zip, macOS app+terminal archives, Linux directory tar+desktop entry. Assets/licenses included, frozen never pip; source explicit maintenance preserved. No signing credentials assumed. Linux standard Ubuntu desktop baseline. Existing Linux ARM pipeline must not silently break, new GUI ARM Linux not required.
