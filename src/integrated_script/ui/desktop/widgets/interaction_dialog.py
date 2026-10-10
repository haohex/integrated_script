# -*- coding: utf-8 -*-
"""Modal dialog for InteractionRequest handling confirmations and inputs."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from integrated_script.ui.desktop.widgets.form_builder import FormBuilder
from integrated_script.ui.desktop.widgets.icon_provider import get_icon
from integrated_script.ui.shared.contract import InteractionRequest


class InteractionDialog(QDialog):
    """Modal dialog for interactive user confirmations and inputs."""

    def __init__(self, request: InteractionRequest, parent: QWidget | None = None):
        super().__init__(parent)
        self.request = request
        self.response_data: dict[str, Any] = {"_cancelled": True}

        self.setWindowTitle(request.title or "需要用户确认")
        self.setMinimumWidth(520)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Header with icon and title
        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        icon_name = "alert" if request.kind == "confirm" else "settings"
        icon_label = QLabel(self)
        icon_label.setPixmap(get_icon(icon_name, size=28).pixmap(28, 28))
        header_layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignTop)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(4)
        lbl_title = QLabel(request.title or "操作交互确认", self)
        lbl_title.setObjectName("section_heading")
        title_layout.addWidget(lbl_title)

        lbl_msg = QLabel(request.message, self)
        lbl_msg.setWordWrap(True)
        lbl_msg.setObjectName("op_description")
        title_layout.addWidget(lbl_msg)

        header_layout.addLayout(title_layout, 1)
        layout.addLayout(header_layout)

        # Details list if provided (e.g. CTDS details or dangerous deletion list)
        if request.details:
            details_frame = QFrame(self)
            details_frame.setObjectName("surface_panel")
            details_layout = QVBoxLayout(details_frame)
            details_layout.setContentsMargins(8, 8, 8, 8)
            details_layout.setSpacing(4)

            list_widget = QListWidget(details_frame)
            list_widget.setMaximumHeight(140)
            for item in request.details:
                list_widget.addItem(f"• {item}")
            details_layout.addWidget(list_widget)
            layout.addWidget(details_frame)

        # Dynamic Form for input kind
        self.form_builder: FormBuilder | None = None
        if request.kind == "input" and request.fields:
            scroll = QScrollArea(self)
            scroll.setWidgetResizable(True)
            scroll.setMaximumHeight(260)
            self.form_builder = FormBuilder(request.fields, scroll)
            scroll.setWidget(self.form_builder)
            layout.addWidget(scroll)

        # Action Buttons
        button_row = QHBoxLayout()
        button_row.addStretch()

        self.btn_cancel = QPushButton("取消", self)
        self.btn_cancel.clicked.connect(self._on_cancel)
        button_row.addWidget(self.btn_cancel)

        if request.kind == "confirm":
            self.btn_action = QPushButton("确认执行", self)
            self.btn_action.setObjectName("primary_button")
            self.btn_action.clicked.connect(self._on_confirm)
            button_row.addWidget(self.btn_action)
        else:
            self.btn_action = QPushButton("提交", self)
            self.btn_action.setObjectName("primary_button")
            self.btn_action.clicked.connect(self._on_submit_input)
            button_row.addWidget(self.btn_action)

        layout.addLayout(button_row)

    def _on_confirm(self) -> None:
        self.response_data = {"confirmed": True}
        self.accept()

    def _on_cancel(self) -> None:
        if self.request.kind == "confirm":
            self.response_data = {"confirmed": False}
        else:
            self.response_data = {"_cancelled": True}
        self.reject()

    def _on_submit_input(self) -> None:
        if self.form_builder:
            errors = self.form_builder.validate()
            if errors:
                # validation failed, keep open
                return
            self.response_data = self.form_builder.get_values()
        else:
            self.response_data = {}
        self.accept()

    def get_response(self) -> dict[str, Any]:
        """Return the interaction response data collected from user action."""
        return getattr(self, "response_data", {})

    def closeEvent(self, event) -> None:
        # Default close / Esc sends cancellation
        if self.request.kind == "confirm":
            self.response_data = {"confirmed": False}
        else:
            self.response_data = {"_cancelled": True}
        super().closeEvent(event)

    @classmethod
    def ask(
        cls, request: InteractionRequest, parent: QWidget | None = None
    ) -> dict[str, Any]:
        dlg = cls(request, parent)
        dlg.exec()
        return dlg.response_data
