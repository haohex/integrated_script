# -*- coding: utf-8 -*-
"""Modal screen for browsing filesystem directories and files in Textual TUI."""

from __future__ import annotations

import os
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DirectoryTree, Label


class PathBrowserModalScreen(ModalScreen[str | None]):
    """Modal screen for browsing and selecting local file or directory paths."""

    def __init__(self, initial_path: str = "", select_mode: str = "any"):
        super().__init__()
        self.select_mode = select_mode  # "dir", "file", "any"
        self._initial_dir = self._resolve_start_dir(initial_path)
        self.selected_path: str = str(self._initial_dir)

    def _resolve_start_dir(self, raw_path: str) -> Path:
        if raw_path:
            p = Path(os.path.expanduser(raw_path.strip()))
            if p.is_dir():
                return p
            if p.parent.is_dir():
                return p.parent
        return Path.cwd()

    def compose(self) -> ComposeResult:
        with Vertical(id="file_browser_dialog"):
            yield Label("选择文件或目录", id="file_browser_title")
            yield Label(f"当前选中: {self.selected_path}", id="lbl_browser_selected")

            tree = DirectoryTree(str(self._initial_dir), id="file_browser_tree")
            yield tree

            with Horizontal(id="file_browser_buttons"):
                yield Button("取消", variant="default", id="btn_browser_cancel")
                yield Button("选择当前项", variant="primary", id="btn_browser_confirm")

    def on_directory_tree_file_selected(
        self, event: DirectoryTree.FileSelected
    ) -> None:
        self.selected_path = str(event.path)
        self.query_one("#lbl_browser_selected", Label).update(
            f"当前选中: {self.selected_path}"
        )

    def on_directory_tree_directory_selected(
        self, event: DirectoryTree.DirectorySelected
    ) -> None:
        self.selected_path = str(event.path)
        self.query_one("#lbl_browser_selected", Label).update(
            f"当前选中: {self.selected_path}"
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_browser_confirm":
            self.dismiss(self.selected_path)
        elif event.button.id == "btn_browser_cancel":
            self.dismiss(None)
