# -*- coding: utf-8 -*-
"""Icon provider for desktop GUI using local SVG assets with theme-aware recoloring."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from integrated_script.ui.shared.theme import (
    load_theme_preference,
    resolve_effective_theme,
)

ASSETS_ICONS_DIR = Path(__file__).resolve().parents[3] / "assets" / "icons"

_ICON_CACHE: dict[tuple[str, str, int], QIcon] = {}


def clear_icon_cache() -> None:
    """Clear cached icons (e.g. after theme switch)."""
    _ICON_CACHE.clear()


def get_icon(
    name: str,
    color_hex: str | None = None,
    size: int = 20,
    theme_name: str | None = None,
) -> QIcon:
    """Load local SVG icon and tint it according to theme or explicit color."""
    effective_theme = (
        resolve_effective_theme(theme_name)
        if theme_name
        else resolve_effective_theme(load_theme_preference())
    )

    if not color_hex:
        if effective_theme == "dark":
            if name in ("alert", "error"):
                color_hex = "#FF7B72"
            elif name == "folder":
                color_hex = "#79C0FF"
            elif name == "check":
                color_hex = "#56D364"
            else:
                color_hex = "#D4D4D4"
        else:
            if name in ("alert", "error"):
                color_hex = "#CF222E"
            elif name == "folder":
                color_hex = "#0067C0"
            elif name == "check":
                color_hex = "#0F7B0F"
            else:
                color_hex = "#333333"

    cache_key = (name, color_hex or "", size)
    if cache_key in _ICON_CACHE:
        return _ICON_CACHE[cache_key]

    svg_name = name if name.endswith(".svg") else f"{name}.svg"
    svg_path = ASSETS_ICONS_DIR / svg_name

    if not svg_path.is_file():
        svg_path = ASSETS_ICONS_DIR / "app.svg"
        if not svg_path.is_file():
            return QIcon()

    try:
        svg_data = svg_path.read_text(encoding="utf-8")
        if color_hex and name != "app":
            svg_data = svg_data.replace('fill="currentColor"', f'fill="{color_hex}"')
            svg_data = svg_data.replace('fill="#000000"', f'fill="{color_hex}"')
            svg_data = svg_data.replace(
                'stroke="currentColor"', f'stroke="{color_hex}"'
            )

        renderer = QSvgRenderer(svg_data.encode("utf-8"))
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()

        icon = QIcon(pixmap)
        _ICON_CACHE[cache_key] = icon
        return icon
    except Exception:
        return QIcon(str(svg_path))
