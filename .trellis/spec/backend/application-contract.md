# Shared Desktop / TUI Application Contract

## 1. Scope / Trigger
Use this contract when changing operations, parameters, interactive decisions, execution events, runtime paths or GUI/TUI entrypoints. The desktop and terminal are adapters of the same application service. They must not import processors or own business confirmation rules.

## 2. Signatures
Public imports are from `integrated_script.application`:
- `AppService(config=None, *, working_directory=None)`
- `list_operations() -> tuple[OperationSpec, ...]`
- `start(operation_id, values) -> str` (task ID, background execution)
- `poll_events() -> list[TaskEvent]` (drains pending events)
- `respond(task_id, request_id, values) -> None`
- `busy: bool`; `close() -> None`

Presentation entrypoints: `ui.desktop.app.run_gui(service=None) -> int`, `ui.tui.app.run_tui(service=None) -> int`. `integrated-script` defaults to TUI; `integrated-script-gui` launches desktop; `--legacy-cli` selects the compatibility UI. Imports are lazy at these boundaries; the TUI installation and bundle must not depend on Qt.

## 3. Contracts
- `ParameterSpec`: name, label, kind, default, required, choices, help. Kinds: str/text/path/paths/int/float/bool/choice. Choice pairs are (label, actual value).
- `OperationSpec`: id, category, label, description, fields, destructive.
- `InteractionRequest`: id, title, message, fields, kind (input/confirm), details.
- `TaskEvent`: task_id, kind (started/progress/log/interaction/completed), message, current, total, interaction, result.
- `OperationResult` remains the existing typed result. Preserve all legacy payload fields for complete results, statistics and error details.
- Optional defaults of `None` are meaningful: do not convert them to 0, False or the first choice. Configuration editing uses None to retain the current value. Explicit 0 and False must survive round trips.
- Confirmations submit `{'confirmed': bool}`; input dialogs submit field mappings; dismissal submits `{'_cancelled': True}`. All decisions use the same event/respond path in both frontends, including legacy-config import.
- Catalog availability is shared. Packaged applications hide source-environment maintenance; source mode preserves it. Presentation must not maintain a separate list of operation IDs.
- User config/log/cache locations come from platform directories. Explicit config wins. Import-time logging must not create cwd/logs; loading modules and requesting --version must work from a read-only directory with writable user directories.
- Preserve raw path input at the UI boundary; the application owns home/quote/relative-path interpretation. Relative paths use the captured working directory. Never infer a Windows-to-POSIX mount mapping.
- All UI assets are local. Production cannot fall back to a fake service on ImportError. Test services live under tests only.
- Desktop system-theme resolution belongs to the Qt adapter; shared presentation helpers must remain importable without Qt. Explicit light/dark choices are stable across system-color changes; an unavailable system-color hint uses a documented light fallback rather than a fabricated dark preference.
- Screenshot and acceptance tools must isolate configuration, theme, logs, cache and working data before application imports can write state. Test sentinels belong under temporary roots, never in the actual user's home directory; restore environment and overrides after both success and failure.
- Frozen version resolution uses bundled package metadata, never a parent checkout's pyproject.toml. Build and release manifests identify one commit and product version; actual runtime checks operate on extracted archives.

## 4. Validation & Error Matrix
| Condition | Required behavior |
| --- | --- |
| Another task is running | start raises ValueError; no second worker |
| Unknown operation | ValueError; no processor invocation |
| Invalid field/path | completed failure with VALIDATION_ERROR and readable message |
| Wrong task/request response | ValueError; cannot confirm a later operation |
| User declines/dismisses confirmation | No subsequent operation writes; expose cancellation, not fabricated success statistics |
| Missing backend/dependency | Visible startup failure, never demo results |
| Old result has valid/statistics.is_valid but no success | Normalize at application adapter, preserve processor dictionary contract |
| Unknown progress total | Indeterminate display, no invented percentage |
| Application closes during processing | Do not abandon a writing worker or force-cancel it |

## 5. Good / Base / Bad Cases
- Base: config.view runs in the worker, emits logs and completed result, both clients render its payload.
- Good: CTDS preflight requests type confirmation; approving produces existing processor output; declining prevents conversion. Cleaning an orphan image must preserve the image after a declined prompt.
- Good: no user config + old cwd config offers import through the common interaction channel; explicit config and an existing user config bypass migration. Refusal preserves the old file and defaults.
- Bad: a valid dataset shows failure because its legacy dictionary lacks success; converting None to False changes a saved preference without user input; rendering fake statistics masks a missing backend.

## 6. Required Tests
- Existing processor/workflow regressions plus real temporary CTDS, validation and rejected-cleanup fixtures.
- Public start/poll_events/respond tests for confirmation, stale IDs and legacy-config import; direct helper tests alone cannot prove the UI can reach migration.
- Frontend tests for nullable numbers/booleans, required blank values, choice actual values, nested payloads, raw paths and close protection.
- Subprocess cold start from an unwritable cwd; writable XDG directories; no cwd config/log writes.
- Source/frozen catalog parity except documented environment-maintenance exclusion.
- Offline bundle startup and representative work, tested on the minimum Linux baseline. Host Ubuntu26 output does not prove Ubuntu22 compatibility; a workflow definition does not prove Windows/macOS execution.
- Theme tests cover system light/dark transitions, explicit-choice protection and unknown hints. Screenshot tests exercise normal and exceptional cleanup while preserving a simulated existing user configuration.
- Non-migration UI integration fixtures inject an explicit temporary ConfigManager and working directory. A default AppService against repository cwd can correctly request legacy-config import in a fresh XDG environment, blocking an unattended modal test. Keep migration coverage separate through public start/poll/respond; do not disable production import prompts to make tests pass.
- Asynchronous UI integration tests use a bounded monotonic deadline, drain service/Qt events and yield time to the worker. Assert both terminal service state and visible results, then verify actual output files. Fixed-count tight polling is not a completion guarantee; cleanup waits for a writing worker before calling close.

## 7. Wrong vs Correct
Wrong: catch ImportError and launch FakeAppService; duplicate dataclasses in a UI fallback; call a processor directly from a button; convert optional bool default=None with bool(default).

Correct: import the shared contract, fail clearly if its implementation is absent, call AppService, render its typed events, and preserve None independently of explicit False/0.

Wrong: globally redirect stdout to obtain progress or logs, or import the application layer from core logging to resolve its default directory.

Correct: use progress/log event sinks and a lower-level platform directory dependency; retain legacy console behavior outside application tasks.
