# -*- coding: utf-8 -*-
"""Structured payload formatters and inspectors for operation results."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SummaryItem:
    key: str
    label: str
    value: str


@dataclass
class TableData:
    title: str
    columns: list[str]
    rows: list[list[str]]


@dataclass
class TreeNode:
    key: str
    value: str
    children: list[TreeNode] = field(default_factory=list)


def format_number(val: int | float) -> str:
    """Format numbers with thousands separators."""
    if isinstance(val, int):
        return f"{val:,}"
    if isinstance(val, float):
        return f"{val:,.2f}"
    return str(val)


def format_bytes(num_bytes: int) -> str:
    """Format byte count to human-readable string."""
    size = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(size) < 1024.0:
            return f"{size:3.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def format_duration(seconds: float) -> str:
    """Format duration seconds to readable string."""
    if seconds < 1.0:
        return f"{seconds * 1000:.0f} ms"
    if seconds < 60.0:
        return f"{seconds:.2f} s"
    minutes = int(seconds // 60)
    rem_seconds = seconds % 60
    return f"{minutes}m {rem_seconds:.1f}s"


def extract_summary_items(payload: dict[str, Any]) -> list[SummaryItem]:
    """Extract top-level scalar values as quick summary metrics."""
    items: list[SummaryItem] = []
    for key, val in payload.items():
        if isinstance(val, (int, float, str, bool)) or val is None:
            label = key.replace("_", " ").title()
            val_str = "None" if val is None else str(val)
            if isinstance(val, bool):
                val_str = "Yes" if val else "No"
            elif isinstance(val, (int, float)):
                val_str = format_number(val)
            items.append(SummaryItem(key=key, label=label, value=val_str))
    return items


def extract_tables(payload: dict[str, Any]) -> list[TableData]:
    """Extract list-of-dicts or 2D data as structured tables."""
    tables: list[TableData] = []
    for key, val in payload.items():
        if isinstance(val, list) and val:
            if all(isinstance(row, dict) for row in val):
                # Columns from dict keys
                columns = list(val[0].keys())
                rows = [[str(row.get(col, "")) for col in columns] for row in val]
                tables.append(
                    TableData(
                        title=key.replace("_", " ").title(),
                        columns=columns,
                        rows=rows,
                    )
                )
            elif all(isinstance(item, (str, int, float)) for item in val):
                # Simple list of primitives
                tables.append(
                    TableData(
                        title=key.replace("_", " ").title(),
                        columns=["Index", "Value"],
                        rows=[[str(i + 1), str(item)] for i, item in enumerate(val)],
                    )
                )
    return tables


def build_payload_tree(data: Any, key_name: str = "root") -> TreeNode:
    """Convert arbitrary nested structure into a hierarchical tree without losing fields."""
    if isinstance(data, dict):
        node = TreeNode(key=key_name, value=f"{{ {len(data)} items }}")
        for sub_key, sub_val in data.items():
            node.children.append(build_payload_tree(sub_val, str(sub_key)))
        return node
    elif isinstance(data, (list, tuple)):
        node = TreeNode(key=key_name, value=f"[ {len(data)} items ]")
        for idx, item in enumerate(data):
            node.children.append(build_payload_tree(item, f"[{idx}]"))
        return node
    else:
        return TreeNode(key=key_name, value=str(data))


def format_payload_json(payload: dict[str, Any]) -> str:
    """Serialize payload to indented JSON with fallback for non-serializable objects."""
    try:
        return json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        return f"// Serialization error: {e}\\n{str(payload)}"
