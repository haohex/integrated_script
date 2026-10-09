# -*- coding: utf-8 -*-
"""Modal screen for handling InteractionRequest in Textual TUI."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label

from integrated_script.ui.shared.contract import InteractionRequest
from integrated_script.ui.tui.widgets.form_builder import TuiFormBuilder


class InteractionModalScreen(ModalScreen[dict[str, Any]]):
    """Interactive modal screen for confirmation and dynamic inputs."""

    def __init__(self, request: InteractionRequest):
        super().__init__()
        self.request = request
        self.form_builder: TuiFormBuilder | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="modal_dialog"):
            yield Label(self.request.title or "用户确认提示", id="modal_title")
            yield Label(self.request.message, id="modal_message")

            if self.request.details:
                with ScrollableContainer(id="modal_details"):
                    for detail in self.request.details:
                        yield Label(f"• {detail}")

            if self.request.kind == "input" and self.request.fields:
                self.form_builder = TuiFormBuilder(self.request.fields)
                yield self.form_builder

            with Horizontal(id="modal_buttons"):
                yield Button("取消", variant="default", id="btn_cancel")
                if self.request.kind == "confirm":
                    yield Button("确认执行", variant="primary", id="btn_confirm")
                else:
                    yield Button("提交", variant="primary", id="btn_submit")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "btn_confirm":
            self.dismiss({"confirmed": True})
        elif button_id == "btn_submit":
            if self.form_builder:
                errors = self.form_builder.validate()
                if errors:
                    # Notify validation error
                    self.notify(errors[0], severity="error")
                    return
                self.dismiss(self.form_builder.get_values())
            else:
                self.dismiss({})
        elif button_id == "btn_cancel":
            if self.request.kind == "confirm":
                self.dismiss({"confirmed": False})
            else:
                self.dismiss({"_cancelled": True})

    def action_cancel(self) -> None:
        if self.request.kind == "confirm":
            self.dismiss({"confirmed": False})
        else:
            self.dismiss({"_cancelled": True})
