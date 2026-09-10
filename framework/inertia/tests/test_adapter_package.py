"""The package is installed, versioned in lockstep, and attributed."""

from __future__ import annotations

import tomllib
from importlib.metadata import version
from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parents[1]


def test_package_is_importable_at_the_lockstep_version() -> None:
    import simple_module_inertia  # noqa: F401

    core = tomllib.loads((_PKG_DIR.parent / "core" / "pyproject.toml").read_text())
    assert version("simple_module_inertia") == core["project"]["version"]


def test_upstream_attribution_ships_with_the_package() -> None:
    notice = (_PKG_DIR / "NOTICE").read_text()
    assert "fastapi-inertia" in notice
    assert "MIT" in notice
    assert "Permission is hereby granted" in notice, "must reproduce the upstream MIT text"
