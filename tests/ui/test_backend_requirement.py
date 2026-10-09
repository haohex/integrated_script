# -*- coding: utf-8 -*-
"""Regression tests verifying backend requirement and strict failure on missing backend."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from integrated_script.ui.desktop.app import run_gui
from integrated_script.ui.tui.app import run_tui


def test_missing_backend_gui_raises_runtime_error():
    """Verify GUI explicitly fails with RuntimeError if AppService is unavailable, never falling back to fake."""
    with patch.dict("sys.modules", {"integrated_script.application": None}):
        with pytest.raises(RuntimeError, match="无法启动桌面界面"):
            run_gui(service=None)


def test_missing_backend_tui_raises_runtime_error():
    """Verify TUI explicitly fails with RuntimeError if AppService is unavailable, never falling back to fake."""
    with patch.dict("sys.modules", {"integrated_script.application": None}):
        with pytest.raises(RuntimeError, match="无法启动终端界面"):
            run_tui(service=None)


def test_no_fake_service_in_production_package():
    """Verify FakeAppService is absent from production ui.shared package."""
    import integrated_script.ui.shared as shared

    assert not hasattr(shared, "FakeAppService")
    with pytest.raises(ImportError):
        import integrated_script.ui.shared.fake_service  # type: ignore # noqa: F401
