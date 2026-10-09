# -*- coding: utf-8 -*-
"""Qt Stylesheet (QSS) generator for desktop GUI themes."""

from __future__ import annotations

from integrated_script.ui.shared.theme import get_palette


def generate_qss(theme_name: str) -> str:
    """Generate complete QSS stylesheet for given theme ('light' or 'dark')."""
    p = get_palette(theme_name)

    return f"""
/* Root Window Canvas */
QMainWindow, QWidget#central_widget {{
    background-color: {p['bg_canvas']};
}}

/* Base Styling */
QWidget {{
    color: {p['text_primary']};
    font-size: 13px;
    selection-background-color: {p['accent']};
    selection-color: #FFFFFF;
}}

/* Surface Panels */
QFrame#surface_panel, QFrame#nav_panel, QFrame#content_panel {{
    background-color: {p['bg_surface']};
    border: 1px solid {p['border_subtle']};
    border-radius: 6px;
}}

/* All labels are transparent by default to prevent jarring background blocks */
QLabel {{
    background-color: transparent;
    color: {p['text_primary']};
}}

/* Typography */
QLabel#window_title {{
    font-size: 17px;
    font-weight: 600;
    color: {p['text_primary']};
}}

QLabel#section_heading {{
    font-size: 14px;
    font-weight: 600;
    color: {p['text_primary']};
}}

QLabel#op_title {{
    font-size: 18px;
    font-weight: 600;
    color: {p['text_primary']};
}}

QLabel#op_description {{
    font-size: 13px;
    color: {p['text_secondary']};
    line-height: 1.4;
}}

QLabel#field_label {{
    font-size: 13px;
    font-weight: 500;
    color: {p['text_primary']};
}}

QLabel#field_help {{
    font-size: 12px;
    color: {p['text_secondary']};
}}

QLabel#lbl_status {{
    color: {p['text_secondary']};
    font-size: 13px;
}}

QLabel#lbl_step {{
    color: {p['text_secondary']};
    font-size: 12px;
}}

/* Destructive & Caution Banner */
QFrame#destructive_banner {{
    background-color: {p['status_danger_bg']};
    border: 1px solid {p['status_danger']};
    border-radius: 6px;
    padding: 8px 12px;
}}

QLabel#destructive_banner_text {{
    background-color: transparent;
    color: {p['status_danger']};
    font-weight: 600;
    font-size: 13px;
}}

/* Scroll Area and Forms */
QScrollArea, QScrollArea > QWidget > QWidget {{
    background-color: transparent;
    border: none;
}}

QWidget#form_scroll_widget, QWidget#field_container {{
    background-color: transparent;
}}

/* Checkboxes */
QCheckBox {{
    background-color: transparent;
    color: {p['text_primary']};
    font-size: 13px;
    spacing: 6px;
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 3px;
    border: 1px solid {p['border_control']};
    background-color: {p['bg_surface']};
}}

QCheckBox::indicator:hover {{
    border-color: {p['accent']};
}}

QCheckBox::indicator:checked {{
    background-color: {p['accent']};
    border-color: {p['accent']};
    image: none;
}}

/* Standard Input Controls */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
    background-color: {p['bg_surface']};
    color: {p['text_primary']};
    border: 1px solid {p['border_control']};
    border-radius: 4px;
    padding: 5px 8px;
    min-height: 22px;
}}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border: 2px solid {p['border_focus']};
    padding: 4px 7px;
}}

QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
    background-color: {p['bg_hover']};
    color: {p['text_disabled']};
    border-color: {p['border_subtle']};
}}

/* Buttons */
QPushButton {{
    background-color: {p['bg_surface']};
    color: {p['text_primary']};
    border: 1px solid {p['border_control']};
    border-radius: 4px;
    padding: 6px 14px;
    font-weight: 500;
    min-height: 20px;
}}

QPushButton:hover {{
    background-color: {p['bg_hover']};
    border-color: {p['border_control']};
}}

QPushButton:pressed {{
    background-color: {p['bg_active']};
}}

QPushButton:disabled {{
    background-color: {p['bg_canvas']};
    color: {p['text_disabled']};
    border-color: {p['border_subtle']};
}}

/* Primary Accent Button */
QPushButton#primary_button {{
    background-color: {p['accent']};
    color: {p['text_on_accent']};
    border: 1px solid {p['accent']};
    font-weight: 600;
}}

QPushButton#primary_button:hover {{
    background-color: {p['accent_hover']};
    border-color: {p['accent_hover']};
}}

QPushButton#primary_button:pressed {{
    background-color: {p['accent_pressed']};
    border-color: {p['accent_pressed']};
}}

QPushButton#primary_button:disabled {{
    background-color: {p['text_disabled']};
    border-color: {p['text_disabled']};
    color: #E0E0E0;
}}

/* Danger Button */
QPushButton#danger_button {{
    background-color: {p['status_danger']};
    color: #FFFFFF;
    border: 1px solid {p['status_danger']};
    font-weight: 600;
}}

QPushButton#danger_button:hover {{
    background-color: {p['danger_hover']};
    border-color: {p['danger_hover']};
}}

/* Tool Buttons */
QToolButton {{
    background-color: {p['bg_surface']};
    color: {p['text_primary']};
    border: 1px solid {p['border_control']};
    border-radius: 4px;
    padding: 4px 10px;
    min-height: 20px;
}}

QToolButton:hover {{
    background-color: {p['bg_hover']};
    border-color: {p['border_control']};
}}

QToolButton:pressed {{
    background-color: {p['bg_active']};
}}

QToolButton::menu-indicator {{
    image: none;
    width: 0px;
    height: 0px;
}}

QToolButton::menu-button {{
    image: none;
    width: 0px;
    border: none;
}}

QToolButton::menu-arrow {{
    image: none;
    width: 0px;
    height: 0px;
    border: none;
}}

/* Navigation Tree and Lists */
QTreeWidget {{
    background-color: {p['bg_surface']};
    color: {p['text_primary']};
    border: 1px solid {p['border_subtle']};
    border-radius: 4px;
    outline: none;
    show-decoration-selected: 1;
}}

QTreeWidget:focus {{
    border: 1px solid {p['border_focus']};
}}

QTreeWidget::branch {{
    background: transparent;
}}

QTreeWidget::branch:hover {{
    background-color: {p['bg_hover']};
}}

QTreeWidget::branch:selected {{
    background-color: {p['accent_subtle']};
}}

QTreeWidget::branch:selected:hover {{
    background-color: {p['accent_subtle']};
}}

QTreeWidget::item {{
    height: 28px;
    padding: 2px 6px;
    border-radius: 0px;
    margin: 0px;
}}

QTreeWidget::item:hover {{
    background-color: {p['bg_hover']};
}}

QTreeWidget::item:selected {{
    background-color: {p['accent_subtle']};
    color: {p['accent']};
    font-weight: 600;
}}

QTreeWidget::item:focus {{
    border: none;
    outline: none;
}}

QTreeWidget::item:selected:focus {{
    background-color: {p['accent_subtle']};
    border: none;
    outline: none;
}}

QListWidget, QTableWidget {{
    background-color: {p['bg_surface']};
    color: {p['text_primary']};
    border: 1px solid {p['border_subtle']};
    border-radius: 4px;
    outline: none;
}}

QListWidget::item {{
    padding: 6px 10px;
    border-radius: 4px;
    margin: 1px 4px;
}}

QListWidget::item:hover {{
    background-color: {p['bg_hover']};
}}

QListWidget::item:selected {{
    background-color: {p['accent_subtle']};
    color: {p['accent']};
    font-weight: 600;
}}

QHeaderView::section {{
    background-color: {p['bg_surface_alt']};
    color: {p['text_secondary']};
    font-weight: 600;
    padding: 6px 8px;
    border: none;
    border-bottom: 1px solid {p['border_subtle']};
}}

/* Progress Bar */
QProgressBar {{
    background-color: {p['bg_hover']};
    border: 1px solid {p['border_subtle']};
    border-radius: 4px;
    text-align: center;
    color: {p['text_primary']};
    font-weight: 600;
    min-height: 18px;
    max-height: 18px;
}}

QProgressBar::chunk {{
    background-color: {p['accent']};
    border-radius: 3px;
}}

/* Scrollbars */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0px;
}}

QScrollBar::handle:vertical {{
    background: {p['border_control']};
    min-height: 24px;
    border-radius: 5px;
}}

QScrollBar::handle:vertical:hover {{
    background: {p['text_secondary']};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0px;
}}

QScrollBar::handle:horizontal {{
    background: {p['border_control']};
    min-width: 24px;
    border-radius: 5px;
}}

/* Tab Widget */
QTabWidget::pane {{
    border: 1px solid {p['border_subtle']};
    border-radius: 4px;
    background-color: {p['bg_surface']};
}}

QTabBar::tab {{
    background-color: {p['bg_canvas']};
    color: {p['text_secondary']};
    padding: 6px 14px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}}

QTabBar::tab:selected {{
    background-color: {p['bg_surface']};
    color: {p['accent']};
    font-weight: 600;
    border: 1px solid {p['border_subtle']};
    border-bottom-color: {p['bg_surface']};
}}

/* Badges */
QLabel#badge_category {{
    background-color: {p['badge_bg']};
    color: {p['text_secondary']};
    border-radius: 3px;
    padding: 2px 6px;
    font-size: 11px;
    font-weight: 600;
}}

QLabel#badge_destructive {{
    background-color: {p['status_danger_bg']};
    color: {p['status_danger']};
    border: 1px solid {p['status_danger']};
    border-radius: 3px;
    padding: 2px 6px;
    font-size: 11px;
    font-weight: 600;
}}
"""
