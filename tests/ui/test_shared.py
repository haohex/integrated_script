# -*- coding: utf-8 -*-
"""Unit tests for UI shared helpers and formatters."""

from __future__ import annotations

from pathlib import Path

from integrated_script.ui.shared.formatters import (
    build_payload_tree,
    extract_summary_items,
    extract_tables,
    format_payload_json,
)
from integrated_script.ui.shared.path_utils import (
    clean_path_input,
    normalize_user_path,
    parse_multiline_paths,
    truncate_path_for_display,
)
from integrated_script.ui.shared.theme import (
    THEME_DARK,
    THEME_LIGHT,
    get_palette,
    resolve_effective_theme,
)


def test_clean_path_input():
    assert clean_path_input('  "/my/dir/path"  ') == "/my/dir/path"
    assert clean_path_input("  '/home/user/file.txt'  ") == "/home/user/file.txt"
    assert clean_path_input("   raw_path_no_quotes   ") == "raw_path_no_quotes"


def test_normalize_user_path():
    home = Path.home()
    assert normalize_user_path("~/test.txt") == str(home / "test.txt")
    assert normalize_user_path("rel/path") == "rel/path"


def test_parse_multiline_paths():
    raw = """
    "path/one"
    /path/two

    '~/three'
    """
    parsed = parse_multiline_paths(raw)
    assert len(parsed) == 3
    assert parsed[0] == "path/one"
    assert parsed[1] == "/path/two"
    assert parsed[2] == "~/three"


def test_truncate_path_for_display():
    short = "C:/short/path.txt"
    assert truncate_path_for_display(short, 40) == short

    long_path = "/home/user/very/deep/nested/directory/structure/and/file/name/is/quite/long/image.png"
    truncated = truncate_path_for_display(long_path, 30)
    assert len(truncated) <= 30
    assert "..." in truncated


def test_theme_resolution():
    assert resolve_effective_theme(THEME_LIGHT) == "light"
    assert resolve_effective_theme(THEME_DARK) == "dark"
    # System theme should resolve to either light or dark
    sys_theme = resolve_effective_theme("system")
    assert sys_theme in ("light", "dark")


def test_palette_keys():
    dark_p = get_palette("dark")
    light_p = get_palette("light")
    for key in ("bg_canvas", "bg_surface", "text_primary", "accent"):
        assert key in dark_p
        assert key in light_p


def test_extract_summary_items():
    payload = {
        "processed_files": 120,
        "error_count": 0,
        "duration_sec": 4.5,
        "deep_obj": {"nested": "value"},
    }
    items = extract_summary_items(payload)
    labels = [i.label for i in items]
    assert "Processed Files" in labels
    assert "Error Count" in labels
    assert "Duration Sec" in labels


def test_extract_tables():
    payload = {
        "categories_table": [
            {"id": 0, "name": "person", "count": 50},
            {"id": 1, "name": "car", "count": 25},
        ]
    }
    tables = extract_tables(payload)
    assert len(tables) == 1
    assert tables[0].title == "Categories Table"
    assert len(tables[0].columns) == 3
    assert len(tables[0].rows) == 2


def test_build_payload_tree():
    payload = {
        "dataset": "VOC2007",
        "splits": ["train", "val"],
        "meta": {"version": 1},
    }
    root = build_payload_tree(payload, "root")
    assert root.key == "root"
    assert len(root.children) == 3


def test_format_payload_json():
    payload = {"key": "value"}
    json_out = format_payload_json(payload)
    assert '"key": "value"' in json_out
