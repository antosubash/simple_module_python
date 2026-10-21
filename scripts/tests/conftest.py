"""Shared fixtures for the release-scripts test suite (check_metadata, check_readmes)."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def tmp_pkg_dir(tmp_path: Path) -> Path:
    """A temp directory set up like a simple-module package root."""
    return tmp_path


def _write(path: Path, content: str) -> Path:
    """Write text to a path, creating parents as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def writer():
    return _write
