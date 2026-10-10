# -*- coding: utf-8 -*-
"""Theme tokens, palettes, and preference persistence for desktop and TUI."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

THEME_SYSTEM = "system"
THEME_LIGHT = "light"
THEME_DARK = "dark"

LIGHT_PALETTE = {
    "bg_canvas": "#F3F3F3",
    "bg_surface": "#FFFFFF",
    "bg_surface_alt": "#F9F9F9",
    "bg_hover": "#EDEDED",
    "bg_active": "#E5E5E5",
    "border_subtle": "#E5E5E5",
    "border_control": "#D1D1D1",
    "border_focus": "#0067C0",
    "text_primary": "#1B1B1B",
    "text_secondary": "#5D5D5D",
    "text_disabled": "#A6A6A6",
    "accent": "#0067C0",
    "accent_hover": "#1979C9",
    "accent_pressed": "#005FB8",
    "accent_subtle": "#E8F3FF",
    "text_on_accent": "#FFFFFF",
    "status_success": "#0F7B0F",
    "status_success_bg": "#EBF6EB",
    "status_warning": "#9D5D00",
    "status_warning_bg": "#FFF8E6",
    "status_danger": "#CF222E",
    "status_danger_bg": "#FFEBE9",
    "danger_hover": "#A40E26",
    "badge_bg": "#EAEAEA",
}

DARK_PALETTE = {
    "bg_canvas": "#202020",
    "bg_surface": "#2C2C2C",
    "bg_surface_alt": "#333333",
    "bg_hover": "#383838",
    "bg_active": "#404040",
    "border_subtle": "#333333",
    "border_control": "#444444",
    "border_focus": "#4CC2FF",
    "text_primary": "#F3F3F3",
    "text_secondary": "#A0A0A0",
    "text_disabled": "#666666",
    "accent": "#4CC2FF",
    "accent_hover": "#6BD5FF",
    "accent_pressed": "#38ACFF",
    "accent_subtle": "#1B3B54",
    "text_on_accent": "#001E36",
    "status_success": "#56D364",
    "status_success_bg": "#122A17",
    "status_warning": "#F2CC60",
    "status_warning_bg": "#3B2D00",
    "status_danger": "#FF7B72",
    "status_danger_bg": "#3D1418",
    "danger_hover": "#FF9492",
    "badge_bg": "#383838",
}

_APP_NAME = "integrated_script"
_APP_AUTHOR = "IntegratedScript"

_custom_theme_config_path: Path | None = None


def set_theme_config_path_override(path: Path | None) -> None:
    """Override the path to the theme preference file (e.g. for testing / screenshot isolation)."""
    global _custom_theme_config_path
    _custom_theme_config_path = path


def get_theme_config_path_override() -> Path | None:
    """Return the active custom theme preference path override, if any."""
    return _custom_theme_config_path


def get_theme_config_path() -> Path:
    """Return path to theme settings JSON file in standard user config dir."""
    if _custom_theme_config_path is not None:
        return _custom_theme_config_path

    try:
        from platformdirs import PlatformDirs

        dirs = PlatformDirs(appname=_APP_NAME, appauthor=_APP_AUTHOR)
        return Path(dirs.user_config_dir) / "theme_preference.json"
    except Exception:
        # Fallback consistent with AppPaths._fallback_base()
        if os.name == "nt":
            base = os.environ.get("APPDATA") or os.path.expanduser("~")
            return Path(base) / _APP_NAME / "theme_preference.json"
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        if xdg_config:
            return Path(xdg_config) / _APP_NAME / "theme_preference.json"
        return Path.home() / ".config" / _APP_NAME / "theme_preference.json"


def load_theme_preference() -> str:
    """Load user theme preference ('system', 'light', 'dark'). Default 'system'."""
    try:
        path = get_theme_config_path()
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            theme = data.get("theme", THEME_SYSTEM)
            if theme in (THEME_SYSTEM, THEME_LIGHT, THEME_DARK):
                return theme
    except Exception:
        pass
    return THEME_SYSTEM


def save_theme_preference(mode: str) -> None:
    """Save theme preference persistently."""
    if mode not in (THEME_SYSTEM, THEME_LIGHT, THEME_DARK):
        mode = THEME_SYSTEM
    try:
        path = get_theme_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"theme": mode}, indent=2), encoding="utf-8")
    except Exception:
        pass


def resolve_effective_theme(
    preference: str | None = None,
    system_detector: Callable[[], str | None] | None = None,
    system_hint: str | None = None,
    system_app: Any | None = None,
) -> str:
    """Resolve preference ('system', 'light', 'dark') to concrete 'light' or 'dark'.

    When preference is 'system', resolution priority is:
    1. Explicit system_hint if provided ('light' or 'dark').
    2. system_detector() callable if provided (returns 'light', 'dark', or None).
    3. Inspection of system_app (or active QApplication if present in runtime),
       checking styleHints().colorScheme().
    4. Fallback to 'light'.
    """
    mode = preference or load_theme_preference()
    if mode in (THEME_LIGHT, THEME_DARK):
        return mode

    if mode == THEME_SYSTEM:
        if system_hint in (THEME_LIGHT, THEME_DARK):
            return system_hint

        if system_detector is not None:
            try:
                detected = system_detector()
                if detected in (THEME_LIGHT, THEME_DARK):
                    return detected
            except Exception:
                pass

        app = system_app
        if app is None:
            try:
                import sys

                if "PySide6.QtWidgets" in sys.modules:
                    from PySide6.QtWidgets import QApplication

                    app = QApplication.instance()
            except Exception:
                app = None

        if app is not None:
            detected_qt = _detect_qt_theme(app)
            if detected_qt in (THEME_LIGHT, THEME_DARK):
                return detected_qt

        return THEME_LIGHT

    return THEME_LIGHT


def _detect_qt_theme(qapp: Any) -> str | None:
    """Inspect a Qt application object for color scheme.

    Uses styleHints().colorScheme() only. Does not inspect qapp.palette()
    to prevent pollution by application QSS stylesheets.
    """
    try:
        if hasattr(qapp, "styleHints"):
            hints = qapp.styleHints()
            if hasattr(hints, "colorScheme"):
                scheme = hints.colorScheme()
                scheme_name = getattr(scheme, "name", str(scheme)).lower()
                if "dark" in scheme_name:
                    return THEME_DARK
                if "light" in scheme_name:
                    return THEME_LIGHT
                # Qt.ColorScheme.Unknown falls back explicitly to light
                return THEME_LIGHT
    except Exception:
        pass
    return None


def get_palette(theme_name: str) -> dict[str, str]:
    """Return palette dictionary for concrete theme name ('light' or 'dark')."""
    return DARK_PALETTE if theme_name == THEME_DARK else LIGHT_PALETTE
