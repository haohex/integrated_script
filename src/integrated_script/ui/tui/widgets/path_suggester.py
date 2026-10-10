# -*- coding: utf-8 -*-
"""File and directory path completion suggester for Textual input controls."""

from __future__ import annotations

import os

from textual.suggester import Suggester


class PathSuggester(Suggester):
    """Filesystem path completion suggester for Textual Inputs."""

    def __init__(self) -> None:
        super().__init__(use_cache=False, case_sensitive=True)

    async def get_suggestion(self, value: str) -> str | None:
        if not value:
            return None
        try:
            raw_expanded = os.path.expanduser(value)
            if value.endswith(("/", "\\")):
                search_dir = raw_expanded
                prefix = ""
            else:
                search_dir = os.path.dirname(raw_expanded) or "."
                prefix = os.path.basename(raw_expanded)

            if not os.path.isdir(search_dir):
                return None

            for entry in os.scandir(search_dir):
                if entry.name.startswith(prefix) and entry.name != prefix:
                    remainder = entry.name[len(prefix) :]
                    if entry.is_dir():
                        remainder += "/"
                    return value + remainder
        except Exception:
            return None
        return None
