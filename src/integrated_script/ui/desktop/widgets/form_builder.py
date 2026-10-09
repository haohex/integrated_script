# -*- coding: utf-8 -*-
"""Dynamic form builder generating typed Qt controls from ParameterSpec."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QDoubleValidator, QIntValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from integrated_script.ui.desktop.widgets.path_picker import PathPicker, PathsEditor
from integrated_script.ui.shared.contract import ParameterSpec


class NullableNumberEdit(QLineEdit):
    """Editable numeric control supporting None (leave empty) or explicit number."""

    def __init__(
        self,
        kind: str = "int",
        required: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.kind = kind
        self.required = required
        self.setPlaceholderText("必填数值..." if required else "保持原值 (留空不修改)")
        if kind == "int":
            self.setValidator(QIntValidator(-99999999, 99999999, self))
        else:
            validator = QDoubleValidator(-99999999.0, 99999999.0, 4, self)
            validator.setNotation(QDoubleValidator.Notation.StandardNotation)
            self.setValidator(validator)

    def value(self) -> int | float | None:
        text = self.text().strip()
        if not text:
            return None
        try:
            return int(text) if self.kind == "int" else float(text)
        except ValueError:
            return None

    def setValue(self, val: int | float | None) -> None:
        if val is None or val == "":
            self.setText("")
        else:
            self.setText(str(val))


class NullableBoolEdit(QComboBox):
    """Tri-state boolean dropdown for optional bool parameters."""

    def __init__(self, default: bool | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.addItem("保持原值 (不修改)", userData=None)
        self.addItem("是 (True / 开启)", userData=True)
        self.addItem("否 (False / 关闭)", userData=False)
        self.setValue(default)

    def value(self) -> bool | None:
        return self.currentData()

    def setValue(self, val: bool | None) -> None:
        if val is True:
            self.setCurrentIndex(1)
        elif val is False:
            self.setCurrentIndex(2)
        else:
            self.setCurrentIndex(0)

    def setChecked(self, checked: bool | None) -> None:
        self.setValue(checked)

    def isChecked(self) -> bool:
        return bool(self.value())


class FormBuilder(QWidget):
    """Dynamic form panel instantiated from a tuple of ParameterSpec."""

    def __init__(
        self, fields: tuple[ParameterSpec, ...], parent: QWidget | None = None
    ):
        super().__init__(parent)
        self.fields = fields
        self.widgets: dict[str, Any] = {}

        self.setObjectName("form_scroll_widget")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        for param in fields:
            field_container = QWidget(self)
            field_container.setObjectName("field_container")
            field_layout = QVBoxLayout(field_container)
            field_layout.setContentsMargins(0, 0, 0, 0)
            field_layout.setSpacing(4)

            kind = param.kind.lower()

            if kind == "bool" and param.default is not None:
                # For definite boolean switches (True/False default), use direct checkbox
                chk_text = (
                    f"{param.label or param.name} *"
                    if param.required
                    else (param.label or param.name)
                )
                chk = QCheckBox(chk_text, field_container)
                chk.setChecked(bool(param.default))
                self.widgets[param.name] = chk
                field_layout.addWidget(chk)
            else:
                # Label row (Label + Required indicator)
                label_row = QHBoxLayout()
                label_row.setContentsMargins(0, 0, 0, 0)
                label_row.setSpacing(4)

                label_text = param.label or param.name
                lbl = QLabel(label_text, field_container)
                lbl.setObjectName("field_label")
                label_row.addWidget(lbl)

                if param.required:
                    req_lbl = QLabel("*", field_container)
                    req_lbl.setStyleSheet("color: #FF7B72; font-weight: bold;")
                    label_row.addWidget(req_lbl)

                label_row.addStretch()
                field_layout.addLayout(label_row)

                # Widget creation based on kind
                widget = self._create_control(param, field_container)
                widget.setObjectName(f"field_{param.name}")
                if isinstance(widget, PathPicker):
                    widget.line_edit.setObjectName(param.name)
                elif hasattr(widget, "setObjectName"):
                    widget.setObjectName(param.name)
                self.widgets[param.name] = widget
                field_layout.addWidget(widget)

            # Optional Help / Description text
            if param.help:
                help_lbl = QLabel(param.help, field_container)
                help_lbl.setObjectName("field_help")
                help_lbl.setWordWrap(True)
                field_layout.addWidget(help_lbl)

            layout.addWidget(field_container)

        layout.addStretch()

    def _create_control(self, param: ParameterSpec, parent: QWidget) -> QWidget:
        kind = param.kind.lower()

        if kind == "str":
            edit = QLineEdit(parent)
            edit.setText(str(param.default or ""))
            return edit

        elif kind == "text":
            text_edit = QPlainTextEdit(parent)
            text_edit.setPlainText(str(param.default or ""))
            text_edit.setMaximumHeight(90)
            return text_edit

        elif kind == "path":
            picker = PathPicker(default=str(param.default or ""), parent=parent)
            return picker

        elif kind == "paths":
            editor = PathsEditor(default=str(param.default or ""), parent=parent)
            return editor

        elif kind == "int":
            if param.default is None:
                return NullableNumberEdit(
                    kind="int", required=param.required, parent=parent
                )
            spin = QSpinBox(parent)
            spin.setRange(-99999999, 99999999)
            val = param.default if isinstance(param.default, int) else 0
            spin.setValue(val)
            return spin

        elif kind == "float":
            if param.default is None:
                return NullableNumberEdit(
                    kind="float", required=param.required, parent=parent
                )
            dspin = QDoubleSpinBox(parent)
            dspin.setRange(-99999999.0, 99999999.0)
            dspin.setDecimals(
                4
                if isinstance(param.default, float)
                and len(str(param.default).split(".")[-1]) > 2
                else 2
            )
            dspin.setSingleStep(0.05)
            fval = float(param.default) if param.default is not None else 0.0
            dspin.setValue(fval)
            return dspin

        elif kind == "bool":
            if param.default is None:
                return NullableBoolEdit(default=None, parent=parent)
            chk = QCheckBox(param.label or param.name, parent)
            chk.setChecked(bool(param.default))
            return chk

        elif kind == "choice":
            combo = QComboBox(parent)
            for item in param.choices:
                if isinstance(item, (tuple, list)) and len(item) >= 2:
                    label, val = item[0], item[1]
                else:
                    label, val = str(item), item
                combo.addItem(str(label), userData=val)

            # Set default selection
            if param.default is not None:
                for idx in range(combo.count()):
                    if combo.itemData(idx) == param.default:
                        combo.setCurrentIndex(idx)
                        break
            return combo

        # Fallback to single-line string
        edit = QLineEdit(parent)
        edit.setText(str(param.default or ""))
        return edit

    def get_values(self) -> dict[str, Any]:
        """Collect current values from all controls with accurate Python types."""
        values: dict[str, Any] = {}
        for param in self.fields:
            name = param.name
            w = self.widgets.get(name)
            if w is None:
                continue

            kind = param.kind.lower()
            if kind == "str":
                values[name] = w.text().strip()
            elif kind == "text":
                values[name] = w.toPlainText().strip()
            elif kind == "path":
                values[name] = w.get_path()
            elif kind == "paths":
                # Return multiline string as expected by service
                values[name] = w.get_text()
            elif kind == "int":
                if isinstance(w, NullableNumberEdit):
                    values[name] = w.value()
                elif isinstance(w, QSpinBox):
                    values[name] = int(w.value())
                else:
                    txt = w.text().strip() if hasattr(w, "text") else ""
                    values[name] = int(txt) if txt else None
            elif kind == "float":
                if isinstance(w, NullableNumberEdit):
                    values[name] = w.value()
                elif isinstance(w, QDoubleSpinBox):
                    values[name] = float(w.value())
                else:
                    txt = w.text().strip() if hasattr(w, "text") else ""
                    values[name] = float(txt) if txt else None
            elif kind == "bool":
                if isinstance(w, NullableBoolEdit):
                    values[name] = w.value()
                elif isinstance(w, QCheckBox):
                    values[name] = bool(w.isChecked())
                elif hasattr(w, "value"):
                    values[name] = w.value()
                else:
                    values[name] = bool(getattr(w, "isChecked", lambda: False)())
            elif kind == "choice":
                values[name] = w.currentData()
            else:
                values[name] = w.text().strip() if hasattr(w, "text") else ""

        return values

    def validate(self) -> list[str]:
        """Check required fields and return list of validation error messages."""
        errors: list[str] = []
        values = self.get_values()
        for param in self.fields:
            if not param.required:
                continue
            val = values.get(param.name)
            if val is None or val == "":
                errors.append(
                    f"字段【{param.label or param.name}】为必填项，不能为空。"
                )
        return errors

    def reset_defaults(self) -> None:
        """Reset all controls to their spec defaults."""
        for param in self.fields:
            w = self.widgets.get(param.name)
            if w is None:
                continue
            kind = param.kind.lower()
            if kind == "str":
                w.setText(str(param.default or ""))
            elif kind == "text":
                w.setPlainText(str(param.default or ""))
            elif kind == "path":
                w.set_path(str(param.default or ""))
            elif kind == "paths":
                w.set_paths(str(param.default or ""))
            elif kind == "int":
                if isinstance(w, NullableNumberEdit):
                    w.setValue(param.default)
                elif isinstance(w, QSpinBox):
                    val = param.default if isinstance(param.default, int) else 0
                    w.setValue(val)
            elif kind == "float":
                if isinstance(w, NullableNumberEdit):
                    w.setValue(param.default)
                elif isinstance(w, QDoubleSpinBox):
                    fval = float(param.default) if param.default is not None else 0.0
                    w.setValue(fval)
            elif kind == "bool":
                if isinstance(w, NullableBoolEdit):
                    w.setValue(param.default)
                elif isinstance(w, QCheckBox):
                    w.setChecked(bool(param.default))
            elif kind == "choice":
                if param.default is not None:
                    for idx in range(w.count()):
                        if w.itemData(idx) == param.default:
                            w.setCurrentIndex(idx)
