# -*- coding: utf-8 -*-
"""Path handling utilities for desktop and TUI."""

from __future__ import annotations

from pathlib import Path


def clean_path_input(raw: str) -> str:
    """Strip surrounding whitespace and paired outer quotes from path input."""
    cleaned = raw.strip()
    if len(cleaned) >= 2:
        if (cleaned.startswith('"') and cleaned.endswith('"')) or (
            cleaned.startswith("'") and cleaned.endswith("'")
        ):
            cleaned = cleaned[1:-1].strip()
    return cleaned


def normalize_user_path(raw: str) -> str:
    """Helper for internal path expansion where explicitly requested by display layer."""
    cleaned = clean_path_input(raw)
    if not cleaned:
        return ""
    if cleaned.startswith("~"):
        try:
            return str(Path(cleaned).expanduser())
        except Exception:
            return cleaned
    return cleaned


def parse_multiline_paths(raw: str) -> list[str]:
    """Parse multiline string into a list of clean, non-empty raw user paths.

    Preserves relative paths and user formatting without premature absolute normalization.
    """
    lines = raw.splitlines()
    paths: list[str] = []
    for line in lines:
        cleaned = clean_path_input(line)
        if cleaned:
            paths.append(cleaned)
    return paths


def truncate_path_for_display(path_str: str, max_chars: int = 48) -> str:
    """Truncate long path with middle ellipsis for UI display."""
    if len(path_str) <= max_chars:
        return path_str

    half = (max_chars - 3) // 2
    return f"{path_str[:half]}...{path_str[-half:]}"
