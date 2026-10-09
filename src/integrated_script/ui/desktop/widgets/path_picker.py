# -*- coding: utf-8 -*-
"""Path picker and multiline paths widgets with native and fallback dialog support."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from integrated_script.ui.desktop.widgets.icon_provider import get_icon
from integrated_script.ui.shared.path_utils import (
    clean_path_input,
    parse_multiline_paths,
)


class PathPicker(QWidget):
    """Single path input with browse button and Linux fallback."""

    path_changed = Signal(str)

    def __init__(
        self,
        default: str = "",
        choose_mode: str = "directory",  # "directory", "file", or "save"
        file_filter: str = "All Files (*.*)",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.choose_mode = choose_mode
        self.file_filter = file_filter

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.line_edit = QLineEdit(self)
        self.line_edit.setText(default)
        self.line_edit.setPlaceholderText("选择或输入路径...")
        self.line_edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.line_edit, 1)

        self.browse_button = QToolButton(self)
        self.browse_button.setIcon(
            get_icon("folder" if choose_mode == "directory" else "file")
        )
        self.browse_button.setText("浏览… ▾")
        self.browse_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.browse_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        menu = QMenu(self.browse_button)
        act_dir = menu.addAction("选择目录/文件夹...")
        act_file = menu.addAction("选择已有文件...")
        act_save = menu.addAction("指定/保存文件路径...")
        act_dir.setIcon(get_icon("folder"))
        act_file.setIcon(get_icon("file"))
        act_save.setIcon(get_icon("copy"))
        act_dir.triggered.connect(self._browse_directory)
        act_file.triggered.connect(self._browse_file)
        act_save.triggered.connect(self._browse_save_file)
        self.browse_button.setMenu(menu)

        layout.addWidget(self.browse_button)

    def _on_text_changed(self, text: str) -> None:
        self.path_changed.emit(clean_path_input(text))

    def _get_start_dir(self) -> str:
        current_text = clean_path_input(self.line_edit.text())
        if current_text and os.path.exists(current_text):
            return (
                current_text
                if os.path.isdir(current_text)
                else os.path.dirname(current_text)
            )
        return str(Path.cwd())

    def _browse_directory(self) -> None:
        start_dir = self._get_start_dir()
        selected = ""
        try:
            selected = QFileDialog.getExistingDirectory(self, "选择目录", start_dir)
        except Exception:
            try:
                selected = QFileDialog.getExistingDirectory(
                    self, "选择目录", start_dir, QFileDialog.Option.DontUseNativeDialog
                )
            except Exception:
                selected = ""
        if selected:
            self.line_edit.setText(selected)
            self.path_changed.emit(selected)

    def _browse_file(self) -> None:
        start_dir = self._get_start_dir()
        selected = ""
        try:
            selected, _ = QFileDialog.getOpenFileName(
                self, "选择文件", start_dir, self.file_filter
            )
        except Exception:
            try:
                selected, _ = QFileDialog.getOpenFileName(
                    self,
                    "选择文件",
                    start_dir,
                    self.file_filter,
                    options=QFileDialog.Option.DontUseNativeDialog,
                )
            except Exception:
                selected = ""
        if selected:
            self.line_edit.setText(selected)
            self.path_changed.emit(selected)

    def _browse_save_file(self) -> None:
        start_dir = self._get_start_dir()
        selected = ""
        try:
            selected, _ = QFileDialog.getSaveFileName(
                self, "指定/保存文件", start_dir, self.file_filter
            )
        except Exception:
            try:
                selected, _ = QFileDialog.getSaveFileName(
                    self,
                    "指定/保存文件",
                    start_dir,
                    self.file_filter,
                    options=QFileDialog.Option.DontUseNativeDialog,
                )
            except Exception:
                selected = ""
        if selected:
            self.line_edit.setText(selected)
            self.path_changed.emit(selected)

    def _on_browse_clicked(self) -> None:
        if self.choose_mode == "file":
            self._browse_file()
        elif self.choose_mode == "save":
            self._browse_save_file()
        else:
            self._browse_directory()

    def get_path(self) -> str:
        return clean_path_input(self.line_edit.text())

    def set_path(self, path: str) -> None:
        self.line_edit.setText(path)


class PathsEditor(QWidget):
    """Multi-path editor supporting multiple paths, file dialogs, and clear action."""

    paths_changed = Signal(list)

    def __init__(self, default: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.text_edit = QPlainTextEdit(self)
        self.text_edit.setPlaceholderText("每行输入一个路径，或使用下方按钮添加...")
        self.text_edit.setPlainText(default)
        self.text_edit.setMaximumHeight(120)
        self.text_edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.text_edit)

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(6)

        self.btn_add_dir = QPushButton("添加目录...", self)
        self.btn_add_dir.setIcon(get_icon("folder"))
        self.btn_add_dir.clicked.connect(self._add_directory)
        btn_layout.addWidget(self.btn_add_dir)

        self.btn_add_files = QPushButton("添加文件...", self)
        self.btn_add_files.setIcon(get_icon("file"))
        self.btn_add_files.clicked.connect(self._add_files)
        btn_layout.addWidget(self.btn_add_files)

        btn_layout.addStretch()

        self.btn_clear = QPushButton("清空", self)
        self.btn_clear.clicked.connect(self.text_edit.clear)
        btn_layout.addWidget(self.btn_clear)

        layout.addLayout(btn_layout)

    def _on_text_changed(self) -> None:
        self.paths_changed.emit(self.get_path_list())

    def _add_directory(self) -> None:
        try:
            d = QFileDialog.getExistingDirectory(self, "选择目录", str(Path.cwd()))
        except Exception:
            d = QFileDialog.getExistingDirectory(
                self,
                "选择目录",
                str(Path.cwd()),
                QFileDialog.Option.DontUseNativeDialog,
            )
        if d:
            current = self.text_edit.toPlainText().strip()
            self.text_edit.setPlainText(f"{current}\n{d}".strip() if current else d)

    def _add_files(self) -> None:
        try:
            files, _ = QFileDialog.getOpenFileNames(
                self, "选择文件", str(Path.cwd()), "All Files (*.*)"
            )
        except Exception:
            files, _ = QFileDialog.getOpenFileNames(
                self,
                "选择文件",
                str(Path.cwd()),
                "All Files (*.*)",
                options=QFileDialog.Option.DontUseNativeDialog,
            )
        if files:
            current = self.text_edit.toPlainText().strip()
            new_lines = "\n".join(files)
            self.text_edit.setPlainText(
                f"{current}\n{new_lines}".strip() if current else new_lines
            )

    def get_path_list(self) -> list[str]:
        return parse_multiline_paths(self.text_edit.toPlainText())

    def get_text(self) -> str:
        return self.text_edit.toPlainText().strip()
