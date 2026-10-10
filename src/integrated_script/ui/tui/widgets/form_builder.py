# -*- coding: utf-8 -*-
"""Dynamic Textual form builder generating typed input controls for ParameterSpec."""

from __future__ import annotations

from typing import Any

from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Label, Select, Switch, TextArea

from integrated_script.ui.shared.contract import ParameterSpec
from integrated_script.ui.shared.path_utils import clean_path_input
from integrated_script.ui.tui.screens.path_browser_modal import (
    PathBrowserModalScreen,
)
from integrated_script.ui.tui.widgets.path_suggester import PathSuggester


class TuiFormBuilder(Vertical):
    """Dynamic form container mapping ParameterSpec to Textual widgets."""

    def __init__(self, fields: tuple[ParameterSpec, ...], id: str | None = None):
        super().__init__(id=id)
        self.fields = fields
        self._controls: dict[str, Any] = {}

    def compose(self):
        for param in self.fields:
            label_text = f"• {param.label or param.name}"
            if param.required:
                label_text += " [red]*[/red]"

            yield Label(label_text, classes="field_label")

            kind = param.kind.lower()
            ctrl_id = f"field_{param.name}"

            if kind == "str":
                ctrl = Input(
                    value=str(param.default or ""),
                    placeholder="请输入文本...",
                    id=ctrl_id,
                )
                self._controls[param.name] = ctrl
                yield ctrl

            elif kind == "text":
                ctrl = TextArea(text=str(param.default or ""), id=ctrl_id)
                ctrl.styles.height = 4
                self._controls[param.name] = ctrl
                yield ctrl

            elif kind == "path":
                with Horizontal(classes="path_row"):
                    ctrl = Input(
                        value=str(param.default or ""),
                        placeholder="输入或粘贴路径...",
                        suggester=PathSuggester(),
                        id=ctrl_id,
                        classes="path_input",
                    )
                    self._controls[param.name] = ctrl
                    yield ctrl
                    yield Button(
                        "浏览...",
                        id=f"btn_browse_{param.name}",
                        classes="btn_browse",
                    )

            elif kind == "paths":
                ctrl = TextArea(text=str(param.default or ""), id=ctrl_id)
                ctrl.styles.height = 4
                self._controls[param.name] = ctrl
                yield ctrl

            elif kind == "int":
                if param.default is None:
                    placeholder = (
                        "必填数值..." if param.required else "保持原值 (留空不修改)"
                    )
                    ctrl = Input(
                        value="",
                        placeholder=placeholder,
                        type="integer",
                        id=ctrl_id,
                    )
                else:
                    ctrl = Input(value=str(param.default), type="integer", id=ctrl_id)
                self._controls[param.name] = ctrl
                yield ctrl

            elif kind == "float":
                if param.default is None:
                    placeholder = (
                        "必填数值..." if param.required else "保持原值 (留空不修改)"
                    )
                    ctrl = Input(
                        value="",
                        placeholder=placeholder,
                        type="number",
                        id=ctrl_id,
                    )
                else:
                    ctrl = Input(value=str(param.default), type="number", id=ctrl_id)
                self._controls[param.name] = ctrl
                yield ctrl

            elif kind == "bool":
                if param.default is None:
                    options = [
                        ("保持原值 (不修改)", "__none__"),
                        ("是 (True / 开启)", "true"),
                        ("否 (False / 关闭)", "false"),
                    ]
                    ctrl = Select(
                        options=options,
                        value="__none__",
                        allow_blank=False,
                        id=ctrl_id,
                    )
                    self._controls[param.name] = ctrl
                    yield ctrl
                else:
                    ctrl = Switch(value=bool(param.default), id=ctrl_id)
                    self._controls[param.name] = ctrl
                    yield ctrl

            elif kind == "choice":
                options = []
                for item in param.choices:
                    if isinstance(item, (tuple, list)) and len(item) >= 2:
                        options.append((str(item[0]), item[1]))
                    else:
                        options.append((str(item), item))

                def_val = (
                    param.default
                    if param.default is not None
                    else (options[0][1] if options else None)
                )
                ctrl = Select(options=options, value=def_val, id=ctrl_id)
                self._controls[param.name] = ctrl
                yield ctrl

            else:
                ctrl = Input(value=str(param.default or ""), id=ctrl_id)
                self._controls[param.name] = ctrl
                yield ctrl

            if param.help:
                yield Label(f"  ({param.help})", classes="field_help")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if button_id.startswith("btn_browse_"):
            param_name = button_id.replace("btn_browse_", "")
            ctrl = self._controls.get(param_name)
            current_val = getattr(ctrl, "value", "") if ctrl else ""

            def _on_path_picked(picked: str | None) -> None:
                if picked and ctrl and hasattr(ctrl, "value"):
                    ctrl.value = picked

            self.app.push_screen(
                PathBrowserModalScreen(initial_path=current_val),
                callback=_on_path_picked,
            )

    def get_values(self) -> dict[str, Any]:
        """Collect and coerce values into accurate Python types."""
        values: dict[str, Any] = {}
        for param in self.fields:
            name = param.name
            ctrl = self._controls.get(name)
            if ctrl is None:
                # Default fallback when form has not been mounted in DOM
                values[name] = param.default
                continue

            kind = param.kind.lower()
            if kind == "str":
                values[name] = getattr(ctrl, "value", "").strip()
            elif kind == "text":
                values[name] = getattr(ctrl, "text", "").strip()
            elif kind == "path":
                values[name] = clean_path_input(getattr(ctrl, "value", ""))
            elif kind == "paths":
                values[name] = getattr(ctrl, "text", "").strip()
            elif kind == "int":
                raw = getattr(ctrl, "value", "").strip()
                if not raw:
                    values[name] = None
                else:
                    try:
                        values[name] = int(raw)
                    except ValueError:
                        values[name] = None
            elif kind == "float":
                raw = getattr(ctrl, "value", "").strip()
                if not raw:
                    values[name] = None
                else:
                    try:
                        values[name] = float(raw)
                    except ValueError:
                        values[name] = None
            elif kind == "bool":
                if isinstance(ctrl, Switch):
                    values[name] = bool(getattr(ctrl, "value", False))
                else:
                    sel_val = getattr(ctrl, "value", "__none__")
                    if sel_val in ("true", True):
                        values[name] = True
                    elif sel_val in ("false", False):
                        values[name] = False
                    else:
                        values[name] = None
            elif kind == "choice":
                values[name] = getattr(ctrl, "value", None)
            else:
                values[name] = getattr(ctrl, "value", "")

        return values

    def validate(self) -> list[str]:
        """Validate required fields."""
        errors: list[str] = []
        vals = self.get_values()
        for param in self.fields:
            if not param.required:
                continue
            val = vals.get(param.name)
            if val is None or val == "":
                errors.append(f"字段【{param.label or param.name}】为必填项。")
        return errors

    def reset_defaults(self) -> None:
        """Reset inputs to default values."""
        for param in self.fields:
            name = param.name
            ctrl = self._controls.get(name)
            if ctrl is None:
                continue
            kind = param.kind.lower()
            if kind == "str":
                ctrl.value = str(param.default or "")
            elif kind == "text":
                ctrl.text = str(param.default or "")
            elif kind == "path":
                ctrl.value = str(param.default or "")
            elif kind == "paths":
                ctrl.text = str(param.default or "")
            elif kind == "int":
                ctrl.value = str(param.default) if param.default is not None else ""
            elif kind == "float":
                ctrl.value = str(param.default) if param.default is not None else ""
            elif kind == "bool":
                if isinstance(ctrl, Switch):
                    ctrl.value = bool(param.default)
                else:
                    if param.default is True:
                        ctrl.value = "true"
                    elif param.default is False:
                        ctrl.value = "false"
                    else:
                        ctrl.value = "__none__"
            elif kind == "choice":
                ctrl.value = param.default
