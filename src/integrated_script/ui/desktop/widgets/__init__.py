# -*- coding: utf-8 -*-
"""Desktop Qt Widgets components."""

from integrated_script.ui.desktop.widgets.form_builder import FormBuilder
from integrated_script.ui.desktop.widgets.icon_provider import get_icon
from integrated_script.ui.desktop.widgets.interaction_dialog import InteractionDialog
from integrated_script.ui.desktop.widgets.path_picker import PathPicker, PathsEditor
from integrated_script.ui.desktop.widgets.result_view import ResultView

__all__ = [
    "FormBuilder",
    "get_icon",
    "InteractionDialog",
    "PathPicker",
    "PathsEditor",
    "ResultView",
]
