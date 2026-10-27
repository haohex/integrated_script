# Execution and verification

User approved plan, implementation and package installs. Preserve preexisting .gitattributes/.agents/.codex/.trellis. On 2026-10-09 the user additionally authorized development-branch push, gated PR merge and a patch release; this supersedes the earlier no-commit/no-push constraint.

1. Main: task records, frozen contract, isolated .venv Python3.11, baseline tests.
2. Pi: public contract early; all open operation catalog/orchestration incl CTDS/class ordering/confirmations; path/config/progress; backend tests; entrypoints/deps/build/CI/README.
3. Antigravity concurrently: design doc/real Qt prototype against contract; complete GUI/TUI, interactions/themes/local icons, tests/screenshots. Fakes only in tests/prototype, never production backend fallback.
4. Main review actual files/tests/operation coverage and screenshots. Bounded followups to owning agents for gaps; workers not allowed to delegate/change global tasks/commit.
5. Run make check-all; UI offscreen tests; sample processing; Linux packaged smoke. Native Windows/macOS evidence must remain unverified until actually run.
6. Main updates executable spec/task evidence/journal without auto commits; incomplete platform validation remains visible.

## Recovery and current ownership
Initial Pi delegation stopped after repeated entrypoint-test hangs (legacy mocks entered actual TUI); its source edits are retained. Recovery is split without concurrent writes:
- Pi runtime repair (d8ef6b9e): application/core/main/legacy compatibility and existing backend tests; fixes review-notes.md. Must not touch packaging files or test_offline_packaging.py.
- Pi offline delivery (e55e4c6b): manifests/requirements/locks/Makefile/build_exe/scripts/CI/README/docs-offline and only tests/unit/test_offline_packaging.py. No src writes.
- Antigravity repair (c282d698): ui/desktop,tui,shared/assets/tests/ui/docs/design; production fake fallback removal, contrast, path UX and real service UI integration.
- Main: artifacts, integration review and final stable validation. No commits/pushes.

Commands: `.venv/bin/python -m pytest`; `PATH="$PWD/.venv/bin:$PATH" make check-all`; `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ui`; build_exe.py commands after implemented. Tests use temp data only.

Visual evidence: component states; six categories; CTDS confirmation, dangerous preview, errors, progress and real result; light/dark compact/full. Windows100/125/150/175/200% only when native platform available, never label Linux captures as Windows.

## Current release sequence (2026-10-09)

1. Pi implements Linux/Windows cloud validation, native builds and extracted TUI processing checks. Antigravity implements native GUI/DPI evidence and extracted GUI runtime checks; each owns disjoint files.
2. Main reviews actual files and runs the final local quality gate in isolated user directories. Commit only task product files; unrelated .gitattributes and local agent/bootstrap configuration remain outside the product commit.
3. Push `dev/offline-desktop-tui`, create a PR targeting `master`, and inspect checks for its exact head. Do not merge while tests, native builds, frozen runtime checks or Windows appearance review remain incomplete.
4. Review actual cloud GUI captures and reports; delegate any necessary fixes to the owning agent, repeat affected verification, and only then merge the accepted head.
5. Tag the accepted merge as `v3.0.1`; let the gated release workflow publish only Linux/Windows artifacts. Verify the release API, asset hashes and download contents before declaring completion.
6. Update the verification report, executable specifications and task/session records with actual URLs and results. No fabricated Windows 10/11 device evidence: hosted Windows runner testing and physical-device validation are distinguished.
