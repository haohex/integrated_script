# -*- coding: utf-8 -*-
"""Textual-based Terminal User Interface (TUI) for integrated_script."""

from __future__ import annotations

import sys
from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    Footer,
    Input,
    Label,
    ProgressBar,
    RichLog,
    Tree,
)

from integrated_script.ui.shared.contract import (
    AppService,
    InteractionRequest,
    OperationSpec,
    TaskEvent,
)
from integrated_script.ui.tui.screens.interaction_modal import InteractionModalScreen
from integrated_script.ui.tui.styles import TUI_CSS
from integrated_script.ui.tui.widgets.form_builder import TuiFormBuilder
from integrated_script.ui.tui.widgets.result_panel import TuiResultPanel


class TuiApp(App[int]):
    """Integrated Script TUI Application."""

    CSS = TUI_CSS
    TITLE = "集成脚本工具"
    SUB_TITLE = "终端界面 (TUI)"

    BINDINGS = [
        Binding("ctrl+q", "safe_quit", "退出 (Ctrl+Q)"),
        Binding("ctrl+r", "run_operation", "执行当前操作"),
        Binding("ctrl+b", "toggle_nav", "切换导航 (Ctrl+B)"),
        Binding("ctrl+f", "focus_search", "搜索操作"),
    ]

    def __init__(self, service: AppService):
        super().__init__()
        self.service = service
        self.operations: tuple[OperationSpec, ...] = ()
        try:
            self.operations = self.service.list_operations()
        except Exception:
            self.operations = ()

        self.current_op: OperationSpec | None = None
        self.current_form: TuiFormBuilder | None = None
        self.active_task_id: str | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(id="top_bar"):
            yield Label("集成脚本工具 TUI", id="app_title")
            yield Button("☰ 导航", id="btn_toggle_nav", classes="toggle_nav_btn")
            yield Input(placeholder="搜索全部操作...", id="search_box")

        with Horizontal(id="main_container"):
            # Navigation Tree
            tree: Tree[OperationSpec | None] = Tree("功能目录", id="nav_tree")
            tree.root.expand()
            yield tree

            # Content Area (Scrollable to ensure 80x24 viewport adaptability)
            with VerticalScroll(id="content_area"):
                with Vertical(id="op_header"):
                    yield Label("请在左侧选择操作", id="op_title")
                    yield Label("", id="destructive_banner")
                    yield Label("", id="op_desc")

                with Vertical(id="form_container"):
                    yield Label("请选择操作以加载配置表单。")

                with Horizontal(id="actions_bar"):
                    yield Button("执行操作 (Ctrl+R)", variant="primary", id="btn_run")
                    yield Button("重置表单", variant="default", id="btn_reset")
                    yield Label("就绪", id="lbl_status")

                with Vertical(id="exec_panel"):
                    yield ProgressBar(total=100, id="progress_bar")
                    yield Label("", id="lbl_step")
                    yield RichLog(id="log_view", wrap=True, highlight=True, markup=True)

                yield TuiResultPanel(id="result_panel")

        yield Footer()

    def on_mount(self) -> None:
        self._populate_nav_tree()
        # Hide initial progress & banners
        self.query_one("#destructive_banner").styles.display = "none"
        self.query_one("#exec_panel").styles.display = "none"
        self.query_one("#result_panel").styles.display = "none"

        # Timer for polling events from backend service
        self.set_interval(0.1, self._poll_events)

    def _populate_nav_tree(self) -> None:
        tree = self.query_one("#nav_tree", Tree)
        tree.clear()

        categories: dict[str, list[OperationSpec]] = {}
        for op in self.operations:
            categories.setdefault(op.category or "其他", []).append(op)

        first_node = None
        for cat_name, ops in categories.items():
            cat_node = tree.root.add(f"[bold]{cat_name} ({len(ops)})[/bold]", data=None)
            for op in ops:
                label = f"[red]![/red] {op.label}" if op.destructive else op.label
                node = cat_node.add_leaf(label, data=op)
                if first_node is None:
                    first_node = node
            cat_node.expand()

        if first_node:
            tree.select_node(first_node)
            if first_node.data:
                self._load_operation_details(first_node.data)

    def on_tree_node_selected(
        self, event: Tree.NodeSelected[OperationSpec | None]
    ) -> None:
        op = event.node.data
        if op is not None:
            self._load_operation_details(op)

    def _load_operation_details(self, op: OperationSpec) -> None:
        self.current_op = op
        self.query_one("#op_title", Label).update(f"[bold]{op.label}[/bold]")
        self.query_one("#op_desc", Label).update(op.description or "")

        banner = self.query_one("#destructive_banner", Label)
        if op.destructive:
            banner.update(
                "[red]⚠ 注意：此功能为破坏性操作，可能删除、重构或覆盖文件。[/red]"
            )
            banner.styles.display = "block"
        else:
            banner.styles.display = "none"

        # Mount dynamic form builder
        form_container = self.query_one("#form_container", Vertical)
        form_container.remove_children()

        self.current_form = TuiFormBuilder(op.fields)
        form_container.mount(self.current_form)

        # Reset states
        self.query_one("#exec_panel").styles.display = "none"
        self.query_one("#result_panel").styles.display = "none"
        self.query_one("#lbl_status", Label).update("就绪")
        self.query_one("#btn_run", Button).disabled = self.service.busy

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search_box":
            query = event.value.strip().lower()
            tree = self.query_one("#nav_tree", Tree)
            tree.clear()

            categories: dict[str, list[OperationSpec]] = {}
            for op in self.operations:
                if not query or (query in op.label.lower()) or (query in op.id.lower()):
                    categories.setdefault(op.category or "其他", []).append(op)

            for cat_name, ops in categories.items():
                cat_node = tree.root.add(
                    f"[bold]{cat_name} ({len(ops)})[/bold]", data=None
                )
                for op in ops:
                    label = f"[red]![/red] {op.label}" if op.destructive else op.label
                    cat_node.add_leaf(label, data=op)
                cat_node.expand()

    def action_focus_search(self) -> None:
        self.query_one("#search_box", Input).focus()

    def action_toggle_nav(self) -> None:
        """Toggle navigation sidebar visibility."""
        tree = self.query_one("#nav_tree", Tree)
        tree.display = not tree.display
        if not tree.display:
            self.query_one("#content_area").focus()
        else:
            tree.focus()

    def action_run_operation(self) -> None:
        self._on_btn_run()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "btn_toggle_nav":
            self.action_toggle_nav()
        elif button_id == "btn_run":
            self._on_btn_run()
        elif button_id == "btn_reset":
            if self.current_form:
                self.current_form.reset_defaults()
            self.query_one("#lbl_status", Label).update("表单已重置")

    def _on_btn_run(self) -> None:
        if not self.current_op:
            self.notify("请先在左侧选择操作。", severity="warning")
            return

        if self.service.busy:
            self.notify("后台已有任务正在执行，请等待完成。", severity="warning")
            return

        values: dict[str, Any] = {}
        if self.current_form:
            errors = self.current_form.validate()
            if errors:
                self.notify("\n".join(errors), title="校验未通过", severity="error")
                return
            values = self.current_form.get_values()

        # Show execution panel
        self.query_one("#exec_panel").styles.display = "block"
        self.query_one("#result_panel").styles.display = "none"
        self.query_one("#lbl_status", Label).update("执行中...")
        self.query_one("#btn_run", Button).disabled = True

        log_view = self.query_one("#log_view", RichLog)
        log_view.clear()
        log_view.write(f"[dim]已提交操作任务: {self.current_op.id}[/dim]")

        pbar = self.query_one("#progress_bar", ProgressBar)
        pbar.update(progress=0, total=100)

        try:
            self.active_task_id = self.service.start(self.current_op.id, values)
        except Exception as e:
            self.query_one("#lbl_status", Label).update("启动失败")
            self.query_one("#btn_run", Button).disabled = False
            self.notify(f"启动失败: {e}", severity="error")

    def _poll_events(self) -> None:
        try:
            events: list[TaskEvent] = self.service.poll_events()
        except Exception:
            events = []

        for event in events:
            if event.kind == "started":
                self.query_one("#lbl_status", Label).update("执行中...")
                if event.message:
                    self.query_one("#lbl_step", Label).update(
                        f"[bold]{event.message}[/bold]"
                    )
                    self.query_one("#log_view", RichLog).write(
                        f"[blue][INFO][/blue] {event.message}"
                    )

            elif event.kind == "progress":
                if event.total and event.total > 0 and event.current is not None:
                    pct = int((event.current / event.total) * 100)
                    self.query_one("#progress_bar", ProgressBar).update(
                        progress=pct, total=100
                    )
                if event.message:
                    self.query_one("#lbl_step", Label).update(event.message)

            elif event.kind == "log":
                if event.message:
                    self.query_one("#log_view", RichLog).write(
                        f"[dim]{event.message}[/dim]"
                    )

            elif event.kind == "interaction":
                if event.interaction:
                    self._show_interaction_modal(event.task_id, event.interaction)

            elif event.kind == "completed":
                self.query_one("#btn_run", Button).disabled = False
                self.query_one("#exec_panel").styles.display = "none"

                result_panel = self.query_one("#result_panel", TuiResultPanel)
                result_panel.styles.display = "block"

                if event.result:
                    if event.result.success:
                        self.query_one("#lbl_status", Label).update(
                            "[green]执行成功[/green]"
                        )
                    else:
                        self.query_one("#lbl_status", Label).update(
                            "[red]执行失败[/red]"
                        )
                    result_panel.display_result(event.result)
                else:
                    self.query_one("#lbl_status", Label).update("执行结束")

    def _show_interaction_modal(self, task_id: str, req: InteractionRequest) -> None:
        def on_modal_result(result: dict[str, Any] | None) -> None:
            self.service.respond(task_id, req.id, result or {"_cancelled": True})

        self.push_screen(InteractionModalScreen(req), callback=on_modal_result)

    def action_safe_quit(self) -> None:
        if self.service.busy:
            self.notify(
                "当前有任务正在进行，禁止强制退出以防止数据损坏。请等待完成。",
                title="禁止退出",
                severity="error",
            )
            return

        try:
            self.service.close()
        except Exception:
            pass
        self.exit(0)


def run_tui(service: AppService | None = None) -> int:
    """Launch the Textual Terminal User Interface."""
    if service is None:
        try:
            from integrated_script.application import AppService as _RealService

            service = _RealService()
        except ImportError as e:
            raise RuntimeError(
                f"无法启动终端界面 (TUI)：后端应用服务 (integrated_script.application.AppService) 未就绪或导入失败: {e}"
            ) from e

    app = TuiApp(service=service)
    result = app.run()
    return result if isinstance(result, int) else 0


if __name__ == "__main__":
    sys.exit(run_tui())
