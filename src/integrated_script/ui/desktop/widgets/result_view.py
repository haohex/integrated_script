# -*- coding: utf-8 -*-
"""Result view widget rendering complete OperationResult, logs, and nested payloads."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
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


def inject_word_breaks(text: str, max_chunk: int = 16) -> str:
    """Inject zero-width spaces into long unbroken tokens to permit natural QLabel wrapping."""
    if not text:
        return ""
    break_chars = set(r"\/_-.#?&=+:;")
    out: list[str] = []
    chunk_len = 0
    for ch in text:
        out.append(ch)
        if ch.isspace():
            chunk_len = 0
        elif ch in break_chars:
            out.append("\u200b")
            chunk_len = 0
        else:
            chunk_len += 1
            if chunk_len >= max_chunk:
                out.append("\u200b")
                chunk_len = 0
    return "".join(out)


class BreakableLabel(QLabel):
    """Word-wrapping QLabel with zero-width minimum size hint to avoid forcing parent layouts wide."""

    def __init__(
        self,
        text_or_parent: str | QWidget | None = None,
        parent: QWidget | None = None,
    ) -> None:
        self._raw_text: str = ""
        if isinstance(text_or_parent, QWidget):
            super().__init__(text_or_parent)
        elif isinstance(text_or_parent, str):
            self._raw_text = text_or_parent
            super().__init__(text_or_parent, parent)
        else:
            super().__init__(parent)
        self.setWordWrap(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        if self._raw_text:
            self.setText(self._raw_text)

    def setText(self, text: str) -> None:
        self._raw_text = text
        super().setText(inject_word_breaks(text))

    def text(self) -> str:
        return self._raw_text

    def minimumSizeHint(self) -> QSize:
        return QSize(0, super().minimumSizeHint().height())


class SummaryCard(QFrame):
    """Summary card displaying a key-value metric with responsive wrapping and copy capability."""

    def __init__(self, label: str, value: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._raw_value = value
        self.setObjectName("surface_panel")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        self.k_lbl = BreakableLabel(label, self)
        self.k_lbl.setObjectName("field_help")
        layout.addWidget(self.k_lbl)

        self.v_lbl = BreakableLabel(value, self)
        self.v_lbl.setObjectName("section_heading")
        self.v_lbl.setToolTip(value)
        self.v_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.v_lbl)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def minimumSizeHint(self) -> QSize:
        return QSize(0, super().minimumSizeHint().height())

    def _show_context_menu(self, pos: Any) -> None:
        menu = QMenu(self)
        copy_act = menu.addAction(get_icon("copy"), "复制完整内容")
        copy_act.triggered.connect(self._copy_value)
        menu.exec(self.mapToGlobal(pos))

    def _copy_value(self) -> None:
        cb = QApplication.clipboard()
        if cb:
            cb.setText(self._raw_value)


class ScrollContentWidget(QWidget):
    """Container widget that respects viewport width constraints and never forces horizontal expansion."""

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        return QSize(min(220, hint.width()), hint.height())


class LogViewerDialog(QDialog):
    """Standalone dialog for viewing and copying full execution logs."""

    def __init__(self, logs: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._avail_override: QRect | None = None
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

    def _clamp_to_screen(
        self,
        target_w: int = 680,
        target_h: int = 440,
        avail_override: QRect | None = None,
    ) -> None:
        """Clamp dialog size and frame within available screen geometry."""
        if avail_override is not None:
            self._avail_override = avail_override
        avail = self._avail_override
        if avail is None:
            screen = self.screen() or QApplication.primaryScreen()
            avail = screen.availableGeometry() if screen else None
        if not avail:
            self.resize(target_w, target_h)
            return

        offset_x = self.frameGeometry().left() - self.pos().x()
        offset_y = self.frameGeometry().top() - self.pos().y()
        fm_w = max(0, self.frameGeometry().width() - self.geometry().width())
        fm_h = max(0, self.frameGeometry().height() - self.geometry().height())

        max_c_w = max(320, avail.width() - fm_w)
        max_c_h = max(200, avail.height() - fm_h)
        min_w = min(320, max_c_w)
        min_h = min(200, max_c_h)
        self.setMinimumSize(min_w, min_h)

        w = max(min_w, min(target_w, max_c_w))
        h = max(min_h, min(target_h, max_c_h))
        self.resize(w, h)

        frame_w = w + fm_w
        frame_h = h + fm_h
        min_pos_x = avail.left() - offset_x
        max_pos_x = avail.right() - offset_x - frame_w + 1
        min_pos_y = avail.top() - offset_y
        max_pos_y = avail.bottom() - offset_y - frame_h + 1

        cur_pos = self.pos()
        clamped_x = max(min_pos_x, min(cur_pos.x(), max(min_pos_x, max_pos_x)))
        clamped_y = max(min_pos_y, min(cur_pos.y(), max(min_pos_y, max_pos_y)))
        self.move(clamped_x, clamped_y)

    def showEvent(self, event: Any) -> None:
        """Clamp dialog to available screen upon display."""
        super().showEvent(event)
        self._clamp_to_screen(self.width(), self.height())

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
        self._summary_cards: list[SummaryCard] = []
        self._current_summary_cols: int | None = None

        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(0)

        # Scroll area container for result content so it is scrollable and never clipped horizontally
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.scroll_content = ScrollContentWidget(self.scroll_area)
        self.main_layout = QVBoxLayout(self.scroll_content)
        self.main_layout.setContentsMargins(12, 12, 12, 12)
        self.main_layout.setSpacing(12)

        # 1. Status Banner
        self.banner = QFrame(self.scroll_content)
        self.banner_layout = QHBoxLayout(self.banner)
        self.banner_layout.setContentsMargins(12, 10, 12, 10)
        self.banner_layout.setSpacing(10)

        self.icon_label = QLabel(self.banner)
        self.banner_layout.addWidget(self.icon_label)

        self.banner_center = QVBoxLayout()
        self.banner_center.setContentsMargins(0, 0, 0, 0)
        self.banner_center.setSpacing(4)

        self.msg_label = BreakableLabel(parent=self.banner)
        self.banner_center.addWidget(self.msg_label)

        self.error_code_badge = BreakableLabel(parent=self.banner)
        self.error_code_badge.setObjectName("badge_destructive")
        self.error_code_badge.setVisible(False)
        self.banner_center.addWidget(self.error_code_badge)

        self.banner_layout.addLayout(self.banner_center, 1)

        self.btn_view_logs = QPushButton("查看日志", self.banner)
        self.btn_view_logs.setIcon(get_icon("terminal"))
        self.btn_view_logs.setToolTip("查看本次任务的完整执行日志")
        self.btn_view_logs.clicked.connect(self._focus_log_tab)
        self.banner_layout.addWidget(self.btn_view_logs)

        self.main_layout.addWidget(self.banner)

        # 2. Key Metrics Summary Cards Grid
        self.summary_container = QWidget(self.scroll_content)
        self.summary_grid = QGridLayout(self.summary_container)
        self.summary_grid.setContentsMargins(0, 0, 0, 0)
        self.summary_grid.setSpacing(8)
        self.main_layout.addWidget(self.summary_container)

        # 3. Tab Widget for Tables, Tree, Raw JSON, and Execution Logs
        self.tabs = QTabWidget(self.scroll_content)
        self.tabs.setMinimumHeight(140)

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

        self.scroll_area.setWidget(self.scroll_content)
        self.root_layout.addWidget(self.scroll_area, 1)

    def minimumSizeHint(self) -> QSize:
        """Return constrained responsive minimum size hint to prevent dialog/parent clipping."""
        return QSize(260, 80)

    def _relayout_summary_cards(self, target_width: int | None = None) -> None:
        """Rearrange summary cards into responsive grid columns based on available viewport width."""
        if not self._summary_cards:
            return
        w = (
            target_width
            if target_width is not None
            else self.scroll_area.viewport().width()
        )
        if w <= 0:
            w = self.width()

        n = len(self._summary_cards)
        if w < 480:
            cols = 1
        elif w < 850:
            cols = min(2, n)
        elif w < 1100:
            cols = min(3, n)
        else:
            cols = min(4, n)
        cols = max(1, cols)

        if getattr(self, "_current_summary_cols", None) == cols:
            return
        self._current_summary_cols = cols

        while self.summary_grid.count():
            self.summary_grid.takeAt(0)

        for idx, card in enumerate(self._summary_cards):
            r = idx // cols
            c = idx % cols
            self.summary_grid.addWidget(card, r, c)

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self._relayout_summary_cards(self.scroll_area.viewport().width())

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
            self.msg_label.setToolTip(op_result.message or "操作执行成功。")
            self.error_code_badge.setVisible(False)
        else:
            self.msg_label.setText(op_result.message or "操作执行失败。")
            self.msg_label.setToolTip(op_result.message or "操作执行失败。")
            if op_result.error_code:
                self.error_code_badge.setText(f"错误码: {op_result.error_code}")
                self.error_code_badge.setToolTip(f"错误码: {op_result.error_code}")
                self.error_code_badge.setVisible(True)
            else:
                self.error_code_badge.setVisible(False)

        # Clear existing summary cards
        while self.summary_grid.count():
            item = self.summary_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self._summary_cards = []
        self._current_summary_cols = None

        # Extract Summary Items
        summary_items = extract_summary_items(self.current_payload)
        for summary_entry in summary_items[:8]:  # show top 8
            card = SummaryCard(
                label=summary_entry.label,
                value=str(summary_entry.value),
                parent=self.summary_container,
            )
            self._summary_cards.append(card)

        self._relayout_summary_cards()

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
