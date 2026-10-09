# -*- coding: utf-8 -*-
"""Unit tests for Terminal User Interface (TUI)."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Button, Input, Select, Tree

from integrated_script.ui.shared.contract import ParameterSpec
from integrated_script.ui.tui.app import TuiApp
from integrated_script.ui.tui.widgets.form_builder import TuiFormBuilder


@pytest.mark.asyncio
async def test_tui_app_mount_and_catalog(fake_service):
    app = TuiApp(service=fake_service)
    async with app.run_test():
        tree = app.query_one("#nav_tree", Tree)
        assert tree is not None
        assert tree.root.children is not None

        # Check top-bar widgets exist
        assert app.query_one("#search_box", Input) is not None
        assert app.query_one("#btn_run", Button) is not None
        assert app.query_one("#btn_toggle_nav", Button) is not None


@pytest.mark.asyncio
async def test_tui_app_destructive_banner(fake_service):
    app = TuiApp(service=fake_service)
    async with app.run_test():
        # Select destructive op
        clean_op = next(o for o in fake_service.list_operations() if o.destructive)
        app._load_operation_details(clean_op)

        banner = app.query_one("#destructive_banner")
        assert banner.styles.display != "none"


@pytest.mark.asyncio
async def test_tui_form_builder_nullable_preservation():
    """Verify that TuiFormBuilder preserves None defaults and accepts explicit 0 / False."""
    fields = (
        ParameterSpec("n", "保持原值", "int", None),
        ParameterSpec("b", "保持原值", "bool", None),
    )
    fb = TuiFormBuilder(fields)

    # Unmounted fallback
    assert fb.get_values() == {"n": None, "b": None}

    # Test in real mounted context
    class TestApp(App):
        def compose(self) -> ComposeResult:
            yield fb

    app = TestApp()
    async with app.run_test():
        # Initial mounted values should be None
        vals = fb.get_values()
        assert vals == {"n": None, "b": None}

        # Explicit '0' input must produce 0
        input_n = fb.query_one("#field_n", Input)
        input_n.value = "0"

        # Explicit False selection must produce False
        select_b = fb.query_one("#field_b", Select)
        select_b.value = "false"

        updated_vals = fb.get_values()
        assert updated_vals["n"] == 0
        assert updated_vals["b"] is False


@pytest.mark.asyncio
async def test_tui_app_nav_toggle(fake_service):
    """Test 80x24 navigation toggle collapse/expand via action_toggle_nav."""
    app = TuiApp(service=fake_service)
    async with app.run_test():
        tree = app.query_one("#nav_tree", Tree)
        assert tree.display is True

        # Toggle collapse
        app.action_toggle_nav()
        assert tree.display is False

        # Toggle expand
        app.action_toggle_nav()
        assert tree.display is True
