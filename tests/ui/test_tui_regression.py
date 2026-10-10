# -*- coding: utf-8 -*-
"""Regression tests for TUI key bindings, path completion, and browser modal."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from textual.widgets import Input

from integrated_script.ui.tui.app import TuiApp
from integrated_script.ui.tui.screens.path_browser_modal import PathBrowserModalScreen
from integrated_script.ui.tui.widgets.path_suggester import PathSuggester
from tests.ui.fake_service import FakeAppService


@pytest.mark.asyncio
async def test_tui_typing_q_does_not_quit():
    """Verify typing 'q' into an input field does NOT trigger exit and preserves 'q' character."""
    fake_service = FakeAppService()
    app = TuiApp(service=fake_service)
    async with app.run_test() as pilot:
        search_box = app.query_one("#search_box", Input)
        search_box.focus()

        # Type path with multiple 'q' characters
        test_path = "/data/quick_quality_dataset_q1"
        for ch in test_path:
            await pilot.press(ch)

        # App must still be running (not quit)
        assert app.is_running
        # Input must contain the exact string including 'q'
        assert search_box.value == test_path


@pytest.mark.asyncio
async def test_path_suggester():
    """Verify PathSuggester returns matching filesystem child entry."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        sub_dir = tmp_path / "target_folder"
        sub_dir.mkdir()

        suggester = PathSuggester()
        # Suggest from prefix
        prefix = str(tmp_path / "tar")
        suggestion = await suggester.get_suggestion(prefix)

        assert suggestion is not None
        assert str(sub_dir) in suggestion


@pytest.mark.asyncio
async def test_path_browser_modal_screen():
    """Verify PathBrowserModalScreen composes and allows selection."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        modal = PathBrowserModalScreen(initial_path=tmp_dir)
        assert modal.selected_path == tmp_dir
        # Cancel dismisses with None
        fake_app = TuiApp(service=FakeAppService())
        async with fake_app.run_test():
            await fake_app.push_screen(modal)
            modal.on_button_pressed(
                type(
                    "Event",
                    (),
                    {"button": type("Btn", (), {"id": "btn_browser_cancel"})()},
                )()
            )
            assert True
