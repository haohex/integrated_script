# Offline desktop and TUI redesign

Approved by user on 2026-09-30, including task creation, implementation and installing missing packages. Delivery scope and publication authorization updated by the user on 2026-10-09 (see below).

## Goal
Polished offline desktop and terminal interfaces for all existing open operations without changing processing algorithms, defaults, output formats or destructive-operation semantics. Windows appearance is a first-class acceptance requirement.

## Requirements
- Python >=3.11; PySide6 Qt Widgets and Textual share operations, validation, interaction state, progress and results.
- Windows 10/11 x64, Ubuntu 22.04/24.04 x64, and Linux ARM64 TUI; packages include Python/resources. Build may use internet; target installation/use do not. macOS packages are excluded from the current release at the user's request.
- Native local Unicode, quoted, relative, drive/UNC paths. No cross-platform drive mapping or unnecessary symlink dereferencing.
- Preserve all open YOLO/image/file/label/environment/configuration capabilities and safety decisions; unopened capabilities remain unopened.
- Default command is TUI; separate GUI launcher without Windows console; explicit legacy fallback.
- Writable state uses user directories; explicit --config wins; offer import of old cwd config without silent migration.
- Professional native-title-bar GUI, consistent forms/tables, local icons, accessible focus, system/light/dark themes and real states. No decorative dashboards, fake metrics, marketing prose, emoji navigation or cloud.
- Antigravity owns all frontend design/implementation; Pi backend/packaging; main architecture/integration/acceptance. Delegation through codeg-mcp.

## Acceptance
- All open operations accessible in GUI/TUI, including CTDS confirmation and class ordering.
- Existing processor/workflow regressions and new path/service/UI tests pass with make check-all.
- Real Qt screenshots for forms, confirmation, progress, results, themes; compact layout, long Chinese paths, focus and errors checked.
- Offline packaged smoke processing without installed Python; untested platforms explicitly marked unverified.
- Preserve preexisting and unrelated changes. The user now authorizes task commits, development-branch push, PR merge after development-branch tests/builds pass, and a patch release. This supersedes the earlier no-commit/no-push/no-publication restriction.
- Local CI must pass before the development branch is pushed. The development branch must complete cloud tests, native Linux/Windows builds, extracted-bundle runtime checks, and GUI appearance review before PR merge. Publish v3.0.1 only from the accepted merged revision, with downloadable offline packages and checksums on GitHub Releases.

## Exclusions
No new algorithms, training/inference, cloud, mount mapping, persistent queue, forced cancellation, global rollback, WebView/QML, paid themes or store distribution.
