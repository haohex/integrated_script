# -*- coding: utf-8 -*-
"""Main window for the desktop Qt application."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from integrated_script.ui.desktop.styles import generate_qss
from integrated_script.ui.desktop.widgets.form_builder import FormBuilder
from integrated_script.ui.desktop.widgets.icon_provider import (
    clear_icon_cache,
    get_icon,
)
from integrated_script.ui.desktop.widgets.interaction_dialog import (
    InteractionDialog,
)
from integrated_script.ui.desktop.widgets.result_view import ResultView
from integrated_script.ui.shared.contract import (
    AppService,
    InteractionRequest,
    OperationSpec,
    TaskEvent,
)
from integrated_script.ui.shared.theme import (
    THEME_DARK,
    THEME_LIGHT,
    THEME_SYSTEM,
    get_palette,
    load_theme_preference,
    resolve_effective_theme,
    save_theme_preference,
)


class MainWindow(QMainWindow):
    """Primary desktop GUI window for integrated_script."""

    def __init__(self, service: AppService, parent: QWidget | None = None):
        super().__init__(parent)
        self.service = service
        self.active_operation: OperationSpec | None = None
        self.active_task_id: str | None = None
        self._current_effective_theme: str = "light"
        self._style_hints_connected: bool = False

        self.setWindowTitle("集成脚本工具")
        self.setMinimumSize(720, 420)
        self._clamp_to_screen(1200, 780)

        # Global window close shortcut (Alt+F4 support even in WM-less environments)
        self._shortcut_close = QShortcut(QKeySequence("Alt+F4"), self)
        self._shortcut_close.activated.connect(self.close)

        # Retrieve operations list from contract service
        try:
            self.all_operations = self.service.list_operations()
        except Exception:
            self.all_operations = ()

        self._init_ui()
        self._load_operations()
        self._setup_system_theme_listener()
        self._apply_initial_theme()

        # Polling Timer for background service events
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(100)
        self.poll_timer.timeout.connect(self._poll_events)
        self.poll_timer.start()

    def _clamp_to_screen(self, target_width: int, target_height: int) -> None:
        """Clamp window size so it never exceeds screen.availableGeometry()."""
        screen = self.screen() or QApplication.primaryScreen()
        if screen:
            avail = screen.availableGeometry()
            max_w = max(self.minimumWidth(), avail.width())
            max_h = max(self.minimumHeight(), avail.height())
            w = min(target_width, max_w)
            h = min(target_height, max_h)
            self.resize(w, h)
        else:
            self.resize(target_width, target_height)

    def showEvent(self, event) -> None:
        """Ensure window fits available screen geometry upon display."""
        super().showEvent(event)
        self._clamp_to_screen(self.width(), self.height())

    def _setup_system_theme_listener(self) -> None:
        """Connect to Qt styleHints().colorSchemeChanged if available."""
        qapp = QApplication.instance()
        if qapp and hasattr(qapp, "styleHints"):
            try:
                hints = qapp.styleHints()
                if hasattr(hints, "colorSchemeChanged"):
                    hints.colorSchemeChanged.connect(
                        self._on_system_color_scheme_changed
                    )
                    self._style_hints_connected = True
            except Exception:
                pass

    def _on_system_color_scheme_changed(self, scheme: Any = None) -> None:
        """Handle system color scheme change event."""
        current_pref = load_theme_preference()
        if current_pref != THEME_SYSTEM:
            # Explicit user preference (light or dark) is preserved
            return
        hint = None
        if scheme is not None:
            scheme_name = getattr(scheme, "name", str(scheme)).lower()
            if "dark" in scheme_name:
                hint = THEME_DARK
            elif "light" in scheme_name:
                hint = THEME_LIGHT
        self._apply_theme_for_mode(THEME_SYSTEM, system_hint=hint)

    def _apply_initial_theme(self) -> None:
        pref = load_theme_preference()
        self._apply_theme_for_mode(pref)

    def _apply_theme_for_mode(self, mode: str, system_hint: str | None = None) -> None:
        """Resolve mode and apply stylesheet and icons."""
        effective = resolve_effective_theme(
            mode, system_hint=system_hint, system_app=QApplication.instance()
        )
        self._current_effective_theme = effective
        qss = generate_qss(effective)
        self.setStyleSheet(qss)
        clear_icon_cache()
        self._refresh_icons(effective)
        if hasattr(self, "result_view") and self.result_view is not None:
            self.result_view.update_theme(effective)

    def _init_ui(self) -> None:
        central_widget = QWidget(self)
        central_widget.setObjectName("central_widget")
        self.setCentralWidget(central_widget)
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        # 1. Top Bar
        top_bar = QFrame(self)
        top_bar.setObjectName("surface_panel")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(14, 8, 14, 8)
        top_layout.setSpacing(12)

        self.lbl_logo = QLabel(top_bar)
        self.lbl_logo.setPixmap(get_icon("app", size=24).pixmap(24, 24))
        top_layout.addWidget(self.lbl_logo)

        lbl_title = QLabel("集成脚本工具", top_bar)
        lbl_title.setObjectName("window_title")
        top_layout.addWidget(lbl_title)

        top_layout.addSpacing(16)

        # Search Bar
        self.search_input = QLineEdit(top_bar)
        self.search_input.setObjectName("search_input")
        self.search_input.setPlaceholderText("搜索全部操作与功能...")
        self.search_input.setMaximumWidth(320)
        self.search_input.textChanged.connect(self._filter_operations)
        top_layout.addWidget(self.search_input)

        top_layout.addStretch()

        # Compact layout toggle
        self.btn_compact = QPushButton("紧凑模式", top_bar)
        self.btn_compact.setCheckable(True)
        self.btn_compact.clicked.connect(self._toggle_compact)
        top_layout.addWidget(self.btn_compact)

        # Theme Selector
        self.theme_combo = QComboBox(top_bar)
        self.theme_combo.addItem("跟随系统", THEME_SYSTEM)
        self.theme_combo.addItem("浅色", THEME_LIGHT)
        self.theme_combo.addItem("深色", THEME_DARK)

        current_pref = load_theme_preference()
        for idx in range(self.theme_combo.count()):
            if self.theme_combo.itemData(idx) == current_pref:
                self.theme_combo.setCurrentIndex(idx)
                break
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        top_layout.addWidget(self.theme_combo)

        root_layout.addWidget(top_bar)

        # 2. Splitter Body (Nav + Content)
        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(4)

        # Left Panel (Navigation Tree)
        nav_panel = QFrame(self.splitter)
        nav_panel.setObjectName("nav_panel")
        nav_layout = QVBoxLayout(nav_panel)
        nav_layout.setContentsMargins(10, 12, 10, 12)
        nav_layout.setSpacing(10)

        lbl_nav_heading = QLabel("功能目录", nav_panel)
        lbl_nav_heading.setObjectName("section_heading")
        nav_layout.addWidget(lbl_nav_heading)

        self.nav_tree = QTreeWidget(nav_panel)
        self.nav_tree.setHeaderHidden(True)
        self.nav_tree.setAnimated(True)
        self.nav_tree.setIconSize(QSize(16, 16))
        self.nav_tree.itemClicked.connect(self._on_nav_item_clicked)
        self.nav_tree.itemActivated.connect(self._on_nav_item_activated)
        nav_layout.addWidget(self.nav_tree, 1)

        self.splitter.addWidget(nav_panel)

        # Right Panel (Operation Form & Output Area)
        content_panel = QFrame(self.splitter)
        content_panel.setObjectName("content_panel")
        content_layout = QVBoxLayout(content_panel)
        content_layout.setContentsMargins(14, 14, 14, 14)
        content_layout.setSpacing(12)

        # Operation Header
        self.op_header_widget = QWidget(content_panel)
        op_header_layout = QVBoxLayout(self.op_header_widget)
        op_header_layout.setContentsMargins(0, 0, 0, 0)
        op_header_layout.setSpacing(6)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self.lbl_op_title = QLabel("请在左侧选择操作", self.op_header_widget)
        self.lbl_op_title.setObjectName("op_title")
        title_row.addWidget(self.lbl_op_title)

        self.badge_category = QLabel("", self.op_header_widget)
        self.badge_category.setObjectName("badge_category")
        self.badge_category.setVisible(False)
        title_row.addWidget(self.badge_category)

        self.badge_destructive = QLabel("破坏性", self.op_header_widget)
        self.badge_destructive.setObjectName("badge_destructive")
        self.badge_destructive.setVisible(False)
        self.lbl_op_destructive = self.badge_destructive
        title_row.addWidget(self.badge_destructive)
        title_row.addStretch()

        op_header_layout.addLayout(title_row)

        self.lbl_op_desc = QLabel("", self.op_header_widget)
        self.lbl_op_desc.setObjectName("op_description")
        self.lbl_op_desc.setWordWrap(True)
        op_header_layout.addWidget(self.lbl_op_desc)

        # Destructive Banner
        self.destructive_banner = QFrame(self.op_header_widget)
        self.destructive_banner.setObjectName("destructive_banner")
        dest_banner_layout = QHBoxLayout(self.destructive_banner)
        dest_banner_layout.setContentsMargins(10, 8, 10, 8)
        dest_banner_layout.setSpacing(8)

        effective_theme = resolve_effective_theme(
            load_theme_preference(), system_app=QApplication.instance()
        )
        self.dest_icon = QLabel(self.destructive_banner)
        self.dest_icon.setPixmap(
            get_icon("alert", size=20, theme_name=effective_theme).pixmap(20, 20)
        )
        dest_banner_layout.addWidget(self.dest_icon)

        self.lbl_dest_text = QLabel(
            "注意：此功能为破坏性操作，可能直接删除、重构或覆盖文件，请谨慎运行。",
            self.destructive_banner,
        )
        self.lbl_dest_text.setObjectName("destructive_banner_text")
        dest_banner_layout.addWidget(self.lbl_dest_text, 1)
        self.destructive_banner.setVisible(False)
        op_header_layout.addWidget(self.destructive_banner)

        content_layout.addWidget(self.op_header_widget)

        # Dynamic Form Area (Wrapped in QScrollArea)
        self.form_scroll = QScrollArea(content_panel)
        self.form_scroll.setWidgetResizable(True)
        self.form_scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.current_form: FormBuilder | None = None
        empty_form_placeholder = QLabel(
            "请在左侧目录选择需要运行的操作以加载配置表单。",
            self.form_scroll,
        )
        empty_form_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.form_scroll.setWidget(empty_form_placeholder)

        content_layout.addWidget(self.form_scroll, 2)

        # Action Toolbar
        action_bar = QHBoxLayout()
        action_bar.setSpacing(10)

        palette = get_palette(effective_theme)
        self.btn_execute = QPushButton("开始执行", content_panel)
        self.btn_execute.setObjectName("primary_button")
        self.btn_execute.setShortcut("Ctrl+Return")
        self.btn_execute.setIcon(
            get_icon("play", color_hex=palette["text_on_accent"], size=18)
        )
        self.btn_execute.clicked.connect(self._on_execute_clicked)
        action_bar.addWidget(self.btn_execute)

        self.btn_reset = QPushButton("重置表单", content_panel)
        self.btn_reset.setIcon(get_icon("refresh"))
        self.btn_reset.clicked.connect(self._on_reset_clicked)
        action_bar.addWidget(self.btn_reset)

        self.lbl_status = QLabel("就绪", content_panel)
        self.lbl_status.setObjectName("lbl_status")
        action_bar.addWidget(self.lbl_status, 1)

        content_layout.addLayout(action_bar)

        # Execution Progress Panel (Collapsible/Hidden by default)
        self.exec_panel = QWidget(content_panel)
        exec_layout = QVBoxLayout(self.exec_panel)
        exec_layout.setContentsMargins(0, 4, 0, 0)
        exec_layout.setSpacing(6)

        self.progress_bar = QProgressBar(self.exec_panel)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        exec_layout.addWidget(self.progress_bar)

        self.lbl_step = QLabel("", self.exec_panel)
        self.lbl_step.setObjectName("lbl_step")
        exec_layout.addWidget(self.lbl_step)

        self.log_edit = QPlainTextEdit(self.exec_panel)
        self.log_edit.setReadOnly(True)
        self.log_edit.setMaximumHeight(140)
        self.log_console = self.log_edit
        exec_layout.addWidget(self.log_edit)

        self.exec_panel.setVisible(False)
        content_layout.addWidget(self.exec_panel)

        # Result View
        self.result_view = ResultView(content_panel)
        self.result_view.setVisible(False)
        content_layout.addWidget(self.result_view, 1)

        self.splitter.addWidget(content_panel)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([260, 940])

        root_layout.addWidget(self.splitter, 1)

    def _load_operations(self) -> None:
        self.nav_tree.clear()
        categories: dict[str, list[OperationSpec]] = {}
        for op in self.all_operations:
            categories.setdefault(op.category or "其他", []).append(op)

        effective_theme = resolve_effective_theme(
            load_theme_preference(), system_app=QApplication.instance()
        )

        for cat_name, ops in categories.items():
            cat_item = QTreeWidgetItem(self.nav_tree)
            cat_item.setText(0, f"{cat_name} ({len(ops)})")
            cat_item.setIcon(0, get_icon("folder", theme_name=effective_theme, size=16))
            cat_font = cat_item.font(0)
            cat_font.setBold(True)
            cat_item.setFont(0, cat_font)

            for op in ops:
                op_item = QTreeWidgetItem(cat_item)
                op_item.setText(0, op.label)
                op_item.setData(0, Qt.ItemDataRole.UserRole, op.id)

                op_icon_name = "alert" if op.destructive else "file"
                op_item.setIcon(
                    0,
                    get_icon(op_icon_name, theme_name=effective_theme, size=16),
                )

        self.nav_tree.expandAll()

        # Select first available operation by default
        if self.nav_tree.topLevelItemCount() > 0:
            first_cat = self.nav_tree.topLevelItem(0)
            if first_cat.childCount() > 0:
                first_op_item = first_cat.child(0)
                self.nav_tree.setCurrentItem(first_op_item)
                first_op_id = first_op_item.data(0, Qt.ItemDataRole.UserRole)
                first_op = next(
                    (o for o in self.all_operations if o.id == first_op_id),
                    None,
                )
                if first_op:
                    self._select_operation(first_op)

    def _filter_operations(self, text: str) -> None:
        query = text.strip().lower()
        first_match_item: QTreeWidgetItem | None = None
        for i in range(self.nav_tree.topLevelItemCount()):
            cat_item = self.nav_tree.topLevelItem(i)
            has_matching_child = False
            for j in range(cat_item.childCount()):
                child = cat_item.child(j)
                op_label = child.text(0).lower()
                op_id = str(child.data(0, Qt.ItemDataRole.UserRole) or "").lower()
                matches = (query in op_label) or (query in op_id)
                child.setHidden(not matches if query else False)
                if matches:
                    has_matching_child = True
                    if first_match_item is None:
                        first_match_item = child

            cat_item.setHidden(not has_matching_child if query else False)

        if query and first_match_item is not None:
            self.nav_tree.setCurrentItem(first_match_item)
            op_id = first_match_item.data(0, Qt.ItemDataRole.UserRole)
            if op_id and not getattr(self.service, "busy", False):
                self._select_operation_by_id(op_id)

    def _on_nav_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        if getattr(self.service, "busy", False):
            return
        op_id = item.data(0, Qt.ItemDataRole.UserRole)
        if op_id:
            op = next((o for o in self.all_operations if o.id == op_id), None)
            if op:
                self._select_operation(op)

    def _on_nav_item_activated(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle keyboard activation (Enter/Return) on tree item."""
        self._on_nav_item_clicked(item, column)

    def _select_operation_by_id(self, op_id: str) -> None:
        if getattr(self.service, "busy", False):
            return
        op = next((o for o in self.all_operations if o.id == op_id), None)
        if op:
            self._select_operation(op)

    def _select_operation(self, op: OperationSpec) -> None:
        self.active_operation = op
        self.lbl_op_title.setText(op.label)
        self.lbl_op_desc.setText(op.description)
        self.badge_category.setText(op.category or "其他")
        self.badge_category.setVisible(True)

        if op.destructive:
            self.badge_destructive.setVisible(True)
            self.destructive_banner.setVisible(True)
        else:
            self.badge_destructive.setVisible(False)
            self.destructive_banner.setVisible(False)

        # Build dynamic form
        self.current_form = FormBuilder(op.fields, self.form_scroll)
        self.form_scroll.setWidget(self.current_form)

        # Reset execution state views
        self.exec_panel.setVisible(False)
        self.result_view.setVisible(False)
        self.lbl_status.setText("就绪")
        self.btn_execute.setEnabled(not self.service.busy)

    def _on_reset_clicked(self) -> None:
        if self.current_form:
            self.current_form.reset_defaults()
            self.lbl_status.setText("表单已重置为默认值")

    def _on_execute_clicked(self) -> None:
        if not self.active_operation:
            return

        if self.service.busy:
            QMessageBox.warning(self, "任务正忙", "后台已有任务正在执行，请等待完成。")
            return

        # 1. Validate Form Inputs
        if self.current_form:
            errors = self.current_form.validate()
            if errors:
                QMessageBox.warning(self, "输入校验未通过", "\n".join(errors))
                return
            params = self.current_form.get_values()
        else:
            params = {}

        # 2. Destructive Double Confirmation
        if self.active_operation.destructive:
            warning_msg = (
                f"【{self.active_operation.label}】为破坏性操作！\n\n"
                f"{self.active_operation.description}\n\n"
                f"此操作可能会删除或覆盖现有文件。是否确认继续执行？"
            )
            reply = QMessageBox.warning(
                self,
                "破坏性操作确认",
                warning_msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # 3. Start Task via Contract
        try:
            self.exec_panel.setVisible(True)
            self.result_view.setVisible(False)
            self.progress_bar.setValue(0)
            self.lbl_step.setText("正在启动任务...")
            self.log_edit.clear()
            self.lbl_status.setText("正在执行...")
            self.btn_execute.setEnabled(False)

            self.active_task_id = self.service.start(self.active_operation.id, params)
        except Exception as ex:
            self.btn_execute.setEnabled(True)
            self.lbl_status.setText(f"启动失败: {ex}")
            QMessageBox.critical(self, "执行错误", f"无法启动操作:\n{ex}")

    def _poll_events(self) -> None:
        events = self.service.poll_events()
        for event in events:
            self._handle_event(event)

    def _handle_event(self, event: TaskEvent) -> None:
        kind = getattr(event, "kind", "")
        msg = getattr(event, "message", "")
        payload = getattr(event, "payload", {})

        if kind == "log":
            if msg:
                self.log_edit.appendPlainText(msg)

        elif kind == "progress":
            cur = getattr(event, "current", 0) or 0
            tot = getattr(event, "total", 100) or 100
            val = int((cur / tot) * 100) if tot > 0 else 0
            self.progress_bar.setValue(val)
            if msg:
                self.lbl_step.setText(msg)
                self.lbl_status.setText(f"执行中 ({val}%)...")

        elif kind == "interaction":
            req = getattr(event, "interaction", None)
            if not req and isinstance(payload, dict):
                req = InteractionRequest(
                    id=payload.get("id", ""),
                    title=payload.get("title", "操作确认"),
                    message=payload.get("message", ""),
                    kind=payload.get("kind", "confirm"),
                    fields=tuple(payload.get("fields", ())),
                    details=tuple(payload.get("details", ())),
                )
            if req:
                task_id = getattr(event, "task_id", self.active_task_id or "")
                self._handle_interaction(task_id, req)

        elif kind == "completed":
            self.progress_bar.setValue(100)
            self.btn_execute.setEnabled(True)
            res = getattr(event, "result", None)
            if res is not None:
                if res.success:
                    self.lbl_status.setText("执行成功")
                else:
                    self.lbl_status.setText("执行失败")
                self.result_view.show_result(res)
                self.result_view.setVisible(True)
            elif isinstance(payload, dict):
                self.lbl_status.setText("执行已完成")
                self.result_view.show_result(payload)
                self.result_view.setVisible(True)

        elif kind == "failed":
            self.lbl_status.setText("执行失败")
            self.btn_execute.setEnabled(True)
            res = getattr(event, "result", None)
            if res is not None:
                self.result_view.show_result(res)
            elif isinstance(payload, dict):
                err_data = dict(payload)
                err_data["success"] = False
                self.result_view.show_result(err_data)
            self.result_view.setVisible(True)

    def _handle_interaction(self, task_id: str, req: InteractionRequest) -> None:
        dlg = InteractionDialog(req, self)
        dlg.exec()
        response = dlg.get_response()
        self.service.respond(task_id, req.id, response)

    _show_interaction_dialog = _handle_interaction

    def _toggle_compact(self, checked: bool | None = None) -> None:
        if checked is None:
            checked = self.btn_compact.isChecked()
        if checked:
            self._clamp_to_screen(980, 600)
            self.splitter.setSizes([220, max(400, self.width() - 220)])
        else:
            self._clamp_to_screen(1200, 780)
            self.splitter.setSizes([260, max(500, self.width() - 260)])

    def _on_theme_changed(self, index: int) -> None:
        mode = self.theme_combo.itemData(index)
        save_theme_preference(mode)
        pref = load_theme_preference()
        self._apply_theme_for_mode(pref)

    def _refresh_icons(self, theme_name: str) -> None:
        palette = get_palette(theme_name)
        self.lbl_logo.setPixmap(
            get_icon("app", size=24, theme_name=theme_name).pixmap(24, 24)
        )
        self.btn_reset.setIcon(get_icon("refresh", theme_name=theme_name))
        self.btn_execute.setIcon(
            get_icon(
                "play",
                color_hex=palette["text_on_accent"],
                size=18,
                theme_name=theme_name,
            )
        )
        if hasattr(self, "dest_icon"):
            self.dest_icon.setPixmap(
                get_icon("alert", size=20, theme_name=theme_name).pixmap(20, 20)
            )

        # Refresh nav tree icons
        for i in range(self.nav_tree.topLevelItemCount()):
            cat_item = self.nav_tree.topLevelItem(i)
            cat_item.setIcon(0, get_icon("folder", theme_name=theme_name, size=16))
            for j in range(cat_item.childCount()):
                op_item = cat_item.child(j)
                op_id = op_item.data(0, Qt.ItemDataRole.UserRole)
                op = next((o for o in self.all_operations if o.id == op_id), None)
                icon_name = "alert" if (op and op.destructive) else "file"
                op_item.setIcon(0, get_icon(icon_name, theme_name=theme_name, size=16))

    def closeEvent(self, event) -> None:
        if getattr(self.service, "busy", False):
            event.ignore()
            if QApplication.platformName() != "offscreen":
                QMessageBox.warning(
                    self,
                    "任务正在运行",
                    "当前有正在执行的后台任务，无法直接退出。",
                )
            return

        if hasattr(self, "poll_timer") and self.poll_timer.isActive():
            self.poll_timer.stop()

        if self._style_hints_connected:
            qapp = QApplication.instance()
            if qapp and hasattr(qapp, "styleHints"):
                try:
                    hints = qapp.styleHints()
                    hints.colorSchemeChanged.disconnect(
                        self._on_system_color_scheme_changed
                    )
                except Exception:
                    pass
            self._style_hints_connected = False

        event.accept()
        qapp = QApplication.instance()
        if qapp:
            qapp.quit()
