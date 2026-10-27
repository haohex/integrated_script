# Baseline evidence — 2026-09-30

- Existing working tree: modified .gitattributes; untracked .agents/, .codex/, .trellis/. No initial product edits.
- Created isolated .venv with uv-managed CPython 3.11.15. User explicitly authorized missing package installation.
- Installed editable project/dev plus PySide6 6.8.3, Textual 8.2.8, platformdirs 4.12.1, PyInstaller 6.22.3, pytest-qt and pytest-asyncio.
- `.venv/bin/python -m pytest -q`: exit 0, 278 collected, 271 passed, 7 skipped (missing preexisting .claude release documentation).
- `PATH="$PWD/.venv/bin:$PATH" make lint format-check type-check`: exit 0; flake8 passed, black73 files unchanged, isort passed; mypy43 source files passed but emitted legacy python_version=3.9 unsupported warning. Update to approved3.11 in backend ownership.
- Qt offscreen smoke: QApplication/label created successfully, Qt6.8.3, offscreen screen800x800; no native Windows/macOS test performed.

This is the pre-implementation baseline, not acceptance of new interfaces or packages.
