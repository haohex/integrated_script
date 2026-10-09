# -*- coding: utf-8 -*-
"""Result view widget rendering complete OperationResult, logs, and nested payloads."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from integrated_script.contracts.results import OperationResult
from integrated_script.ui.desktop.widgets.icon_provider import get_icon
from integrated_script.ui.shared.formatters import (
    TreeNode,
    build_payload_tree,
    extract_summary_items,
    extract_tables,
    format_payload_json,
)
from integrated_script.ui.shared.theme import (
    get_palette,
    load_theme_preference,
    resolve_effective_theme,
)


class LogViewerDialog(QDialog):
    """Standalone dialog for viewing and copying full execution logs."""

    def __init__(self, logs: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("执行日志详情")
        self.resize(680, 440)
        self.setMinimumSize(320, 200)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        toolbar = QHBoxLayout()
        lbl_hint = QLabel("任务完整执行日志输出：", self)
        toolbar.addWidget(lbl_hint)
        toolbar.addStretch()

        self.btn_copy = QPushButton("复制日志", self)
        self.btn_copy.setIcon(get_icon("copy"))
        self.btn_copy.clicked.connect(self._copy_to_clipboard)
        toolbar.addWidget(self.btn_copy)

        layout.addLayout(toolbar)

        self.log_view = QPlainTextEdit(self)
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("font-family: monospace; font-size: 12px;")
        self.log_view.setPlainText(logs)
        layout.addWidget(self.log_view, 1)

        btn_box = QHBoxLayout()
        btn_box.addStretch()
        btn_close = QPushButton("关闭", self)
        btn_close.clicked.connect(self.accept)
        btn_box.addWidget(btn_close)
        layout.addLayout(btn_box)

    def _copy_to_clipboard(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self.log_view.toPlainText())


class ResultView(QWidget):
    """Renders operation outcome, status banners, tables, execution logs, and nested payloads."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.current_payload: dict[str, Any] = {}
        self._last_result: OperationResult | None = None

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(12, 12, 12, 12)
        self.main_layout.setSpacing(12)

        # 1. Status Banner
        self.banner = QFrame(self)
        self.banner_layout = QHBoxLayout(self.banner)
        self.banner_layout.setContentsMargins(12, 10, 12, 10)
        self.banner_layout.setSpacing(10)

        self.icon_label = QLabel(self.banner)
        self.banner_layout.addWidget(self.icon_label)

        self.msg_label = QLabel(self.banner)
        self.msg_label.setWordWrap(True)
        self.banner_layout.addWidget(self.msg_label, 1)

        self.error_code_badge = QLabel(self.banner)
        self.error_code_badge.setObjectName("badge_destructive")
        self.error_code_badge.setVisible(False)
        self.banner_layout.addWidget(self.error_code_badge)

        self.btn_view_logs = QPushButton("查看日志", self.banner)
        self.btn_view_logs.setIcon(get_icon("terminal"))
        self.btn_view_logs.setToolTip("查看本次任务的完整执行日志")
        self.btn_view_logs.clicked.connect(self._focus_log_tab)
        self.banner_layout.addWidget(self.btn_view_logs)

        self.main_layout.addWidget(self.banner)

        # 2. Key Metrics Summary Cards Grid
        self.summary_container = QWidget(self)
        self.summary_grid = QGridLayout(self.summary_container)
        self.summary_grid.setContentsMargins(0, 0, 0, 0)
        self.summary_grid.setSpacing(8)
        self.main_layout.addWidget(self.summary_container)

        # 3. Tab Widget for Tables, Tree, Raw JSON, and Execution Logs
        self.tabs = QTabWidget(self)

        # Tab: Data Tables
        self.table_container = QWidget(self.tabs)
        self.table_layout = QVBoxLayout(self.table_container)
        self.table_layout.setContentsMargins(8, 8, 8, 8)
        self.table_widget = QTableWidget(self.table_container)
        self.table_widget.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table_layout.addWidget(self.table_widget)
        self.tabs.addTab(self.table_container, "结构化表格")

        # Tab: Tree View for Hierarchical Objects
        self.tree_container = QWidget(self.tabs)
        tree_layout = QVBoxLayout(self.tree_container)
        tree_layout.setContentsMargins(8, 8, 8, 8)
        self.tree_widget = QTreeWidget(self.tree_container)
        self.tree_widget.setHeaderLabels(["属性 / 键", "数值 / 内容"])
        self.tree_widget.header().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.tree_widget.header().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        tree_layout.addWidget(self.tree_widget)
        self.tabs.addTab(self.tree_container, "层级数据")

        # Tab: Raw JSON Output with Copy Button
        self.json_container = QWidget(self.tabs)
        json_layout = QVBoxLayout(self.json_container)
        json_layout.setContentsMargins(8, 8, 8, 8)
        json_toolbar = QHBoxLayout()
        json_toolbar.addStretch()
        self.btn_copy_json = QPushButton("复制 JSON", self.json_container)
        self.btn_copy_json.setIcon(get_icon("copy"))
        self.btn_copy_json.clicked.connect(self._copy_json_to_clipboard)
        json_toolbar.addWidget(self.btn_copy_json)
        json_layout.addLayout(json_toolbar)

        self.json_view = QPlainTextEdit(self.json_container)
        self.json_view.setReadOnly(True)
        self.json_view.setStyleSheet("font-family: monospace; font-size: 12px;")
        json_layout.addWidget(self.json_view)

        self.tabs.addTab(self.json_container, "原始 JSON")

        # Tab: Execution Logs with Copy and Popout Dialog
        self.log_container = QWidget(self.tabs)
        log_layout = QVBoxLayout(self.log_container)
        log_layout.setContentsMargins(8, 8, 8, 8)
        log_toolbar = QHBoxLayout()
        log_toolbar.addStretch()

        self.btn_copy_log = QPushButton("复制日志", self.log_container)
        self.btn_copy_log.setIcon(get_icon("copy"))
        self.btn_copy_log.clicked.connect(self._copy_log_to_clipboard)
        log_toolbar.addWidget(self.btn_copy_log)

        self.btn_popout_log = QPushButton("弹窗查看", self.log_container)
        self.btn_popout_log.setIcon(get_icon("terminal"))
        self.btn_popout_log.clicked.connect(self._open_log_dialog)
        log_toolbar.addWidget(self.btn_popout_log)

        log_layout.addLayout(log_toolbar)

        self.log_view = QPlainTextEdit(self.log_container)
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("font-family: monospace; font-size: 12px;")
        log_layout.addWidget(self.log_view)

        self.tabs.addTab(self.log_container, "执行日志")

        self.main_layout.addWidget(self.tabs, 1)

    def minimumSizeHint(self) -> QSize:
        """Return constrained responsive minimum size hint to prevent dialog/parent clipping."""
        return QSize(260, 80)

    def update_theme(self, theme_name: str | None = None) -> None:
        """Update banner colors and icons according to theme without modifying payload or tab state."""
        eff_theme = theme_name or resolve_effective_theme(load_theme_preference())
        palette = get_palette(eff_theme)
        self.btn_copy_json.setIcon(get_icon("copy", theme_name=eff_theme))
        self.btn_copy_log.setIcon(get_icon("copy", theme_name=eff_theme))
        self.btn_popout_log.setIcon(get_icon("terminal", theme_name=eff_theme))
        self.btn_view_logs.setIcon(get_icon("terminal", theme_name=eff_theme))

        if self._last_result is not None:
            if self._last_result.success:
                succ_bg = palette["status_success_bg"]
                succ_fg = palette["status_success"]
                self.banner.setStyleSheet(
                    f"QFrame {{ background-color: {succ_bg}; border: 1px solid {succ_fg}; border-radius: 6px; }}"
                )
                self.icon_label.setPixmap(
                    get_icon(
                        "check", color_hex=succ_fg, size=24, theme_name=eff_theme
                    ).pixmap(24, 24)
                )
                self.msg_label.setStyleSheet(
                    f"color: {succ_fg}; font-size: 14px; font-weight: 600;"
                )
            else:
                danger_bg = palette["status_danger_bg"]
                danger_fg = palette["status_danger"]
                self.banner.setStyleSheet(
                    f"QFrame {{ background-color: {danger_bg}; border: 1px solid {danger_fg}; border-radius: 6px; }}"
                )
                self.icon_label.setPixmap(
                    get_icon(
                        "error", color_hex=danger_fg, size=24, theme_name=eff_theme
                    ).pixmap(24, 24)
                )
                self.msg_label.setStyleSheet(
                    f"color: {danger_fg}; font-size: 14px; font-weight: 600;"
                )

    def set_logs(self, logs: str | None) -> None:
        """Set execution logs displayed in ResultView."""
        self.log_view.setPlainText(logs or "")

    def clear_logs(self) -> None:
        """Clear execution logs in ResultView."""
        self.log_view.clear()

    def get_logs(self) -> str:
        """Get currently stored execution logs."""
        return self.log_view.toPlainText()

    def _focus_log_tab(self) -> None:
        """Switch active tab to execution logs."""
        self.tabs.setCurrentWidget(self.log_container)

    def _open_log_dialog(self) -> None:
        """Open standalone log viewer dialog."""
        dlg = LogViewerDialog(self.log_view.toPlainText(), parent=self)
        dlg.exec()

    def set_result(
        self,
        result: OperationResult | dict[str, Any],
        logs: str | None = None,
    ) -> None:
        """Populate result view with OperationResult content and optional execution logs."""
        if logs is not None:
            self.set_logs(logs)

        if isinstance(result, dict):
            raw_payload = result.get("payload")
            payload = raw_payload if isinstance(raw_payload, dict) else result
            op_result = OperationResult(
                success=bool(result.get("success", True)),
                message=str(result.get("message", "")),
                error_code=result.get("error_code"),
                payload=payload,
            )
        else:
            op_result = result

        self._last_result = op_result
        self.current_payload = dict(op_result.payload or {})

        eff_theme = resolve_effective_theme(load_theme_preference())
        self.update_theme(eff_theme)

        # Status message and error code badge
        if op_result.success:
            self.msg_label.setText(op_result.message or "操作执行成功。")
            self.error_code_badge.setVisible(False)
        else:
            self.msg_label.setText(op_result.message or "操作执行失败。")
            if op_result.error_code:
                self.error_code_badge.setText(f"错误码: {op_result.error_code}")
                self.error_code_badge.setVisible(True)
            else:
                self.error_code_badge.setVisible(False)

        # Clear existing summary cards
        while self.summary_grid.count():
            item = self.summary_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        # Extract Summary Items
        summary_items = extract_summary_items(self.current_payload)
        max_cols = 4
        for idx, summary_entry in enumerate(summary_items[:8]):  # show top 8
            card = QFrame(self.summary_container)
            card.setObjectName("surface_panel")
            card.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(10, 8, 10, 8)
            card_layout.setSpacing(2)

            k_lbl = QLabel(summary_entry.label, card)
            k_lbl.setObjectName("field_help")
            k_lbl.setWordWrap(True)
            card_layout.addWidget(k_lbl)

            v_lbl = QLabel(str(summary_entry.value), card)
            v_lbl.setObjectName("section_heading")
            v_lbl.setWordWrap(True)
            v_lbl.setToolTip(str(summary_entry.value))
            card_layout.addWidget(v_lbl)

            r = idx // max_cols
            c = idx % max_cols
            self.summary_grid.addWidget(card, r, c)

        # Extract Tables
        tables = extract_tables(self.current_payload)
        if tables:
            first_table = tables[0]
            cols = getattr(
                first_table,
                "columns",
                getattr(first_table, "headers", []),
            )
            self.table_widget.setColumnCount(len(cols))
            self.table_widget.setHorizontalHeaderLabels(cols)
            self.table_widget.setRowCount(len(first_table.rows))
            for r_idx, row in enumerate(first_table.rows):
                for c_idx, val in enumerate(row):
                    self.table_widget.setItem(r_idx, c_idx, QTableWidgetItem(str(val)))
            self.tabs.setTabEnabled(0, True)
        else:
            self.table_widget.setRowCount(0)
            self.table_widget.setColumnCount(0)
            self.tabs.setTabEnabled(0, False)

        # Extract Tree
        self.tree_widget.clear()
        root_node = build_payload_tree(self.current_payload)
        for child in root_node.children:
            self._populate_tree_widget(child, self.tree_widget)
        self.tree_widget.expandAll()

        # Raw JSON view
        self.json_view.setPlainText(format_payload_json(self.current_payload))

        # Select appropriate initial tab
        if not op_result.success:
            self.tabs.setCurrentWidget(self.log_container)
        elif tables:
            self.tabs.setCurrentIndex(0)

    def show_result(
        self,
        result: OperationResult | dict[str, Any],
        logs: str | None = None,
    ) -> None:
        """Alias for set_result."""
        self.set_result(result, logs=logs)

    def _populate_tree_widget(
        self, node: TreeNode, parent_item: QTreeWidget | QTreeWidgetItem
    ) -> None:
        if isinstance(parent_item, QTreeWidget):
            item = QTreeWidgetItem(parent_item, [node.key, node.value])
        else:
            item = QTreeWidgetItem(parent_item, [node.key, node.value])

        for child in node.children:
            self._populate_tree_widget(child, item)

    def _copy_json_to_clipboard(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self.json_view.toPlainText())

    def _copy_log_to_clipboard(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self.log_view.toPlainText())
