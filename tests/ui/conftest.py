# -*- coding: utf-8 -*-
"""Pytest fixtures for UI testing."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Ensure root directory is on sys.path for test package imports
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Ensure offscreen Qt platform for headless CI / CLI test execution
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from tests.ui.fake_service import FakeAppService  # noqa: E402


@pytest.fixture
def fake_service() -> FakeAppService:
    """Fixture providing a fresh FakeAppService instance for isolated tests."""
    return FakeAppService()
