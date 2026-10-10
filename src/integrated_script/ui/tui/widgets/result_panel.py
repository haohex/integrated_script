# -*- coding: utf-8 -*-
"""Result presentation panel for Textual TUI displaying nested payloads."""

from __future__ import annotations

from textual.containers import ScrollableContainer
from textual.widgets import DataTable, Label, TextArea

from integrated_script.contracts.results import OperationResult
from integrated_script.ui.shared.formatters import (
    extract_summary_items,
    extract_tables,
    format_payload_json,
)


class TuiResultPanel(ScrollableContainer):
    """Renders structured outcome, tables, and formatted JSON for completed operations."""

    def __init__(self, id: str | None = None):
        super().__init__(id=id)

    def display_result(self, result: OperationResult) -> None:
        self.remove_children()

        # Status Message
        if result.success:
            self.mount(
                Label(
                    f"✓ {result.message or '操作成功完成'}",
                    classes="result_success",
                )
            )
        else:
            err_line = f"✗ {result.message or '操作失败'}"
            if result.error_code:
                err_line += f" (错误码: {result.error_code})"
            self.mount(Label(err_line, classes="result_failure"))

        payload = result.payload or {}

        # Summary Metrics
        summary_items = extract_summary_items(payload)
        if summary_items:
            self.mount(Label("[bold]摘要指标:[/bold]"))
            for item in summary_items[:8]:
                self.mount(Label(f"  • {item.label}: [cyan]{item.value}[/cyan]"))

        # Structured Tables
        tables = extract_tables(payload)
        if tables:
            first_table = tables[0]
            self.mount(Label(f"[bold]数据表: {first_table.title}[/bold]"))
            dt: DataTable = DataTable()
            dt.styles.height = min(len(first_table.rows) + 3, 8)
            dt.add_columns(*first_table.columns)
            for row in first_table.rows:
                dt.add_row(*row)
            self.mount(dt)

        # Raw JSON section
        self.mount(Label("[bold]原始数据 (JSON):[/bold]"))
        json_area = TextArea(text=format_payload_json(payload), read_only=True)
        json_area.styles.height = 8
        self.mount(json_area)
