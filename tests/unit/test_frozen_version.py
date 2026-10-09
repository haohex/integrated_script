"""A downloaded executable reports its own build, not its installation folder."""

import sys

from integrated_script import version


def test_frozen_version_does_not_search_parent_checkout(monkeypatch):
    version.get_version.cache_clear()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(version, "package_version", lambda name: "3.0.0")

    def forbidden_search(path):
        raise AssertionError("Frozen version must not read parent project metadata")

    monkeypatch.setattr(version, "_find_pyproject", forbidden_search)
    try:
        assert version.get_version() == "3.0.0"
    finally:
        version.get_version.cache_clear()
