"""Regression tests for ``smpy new`` scaffold bugs filed against released wheels.

Each test pins a specific issue's repro so the bug can't sneak back in
without a CI failure pointing at the fix.
"""

from __future__ import annotations

import json
from pathlib import Path

from simple_module_cli.cli import app
from typer.testing import CliRunner


def test_sm_new_flat_pins_inertia_react_to_v2(tmp_path: Path) -> None:
    """Issue #128: flat scaffold's root package.json must peer-match
    @simple-module-py/ui's ``@inertiajs/react: ^2.0.0`` peer dep."""
    runner = CliRunner()
    target = tmp_path / "demo"
    runner.invoke(
        app,
        ["new", "demo", "--yes", "--flat", "--no-install", "--dest", str(target)],
    )
    data = json.loads((target / "package.json").read_text())
    inertia = data.get("dependencies", {}).get("@inertiajs/react")
    assert inertia is not None
    assert inertia.startswith("^2."), f"expected ^2.x, got {inertia!r}"


def test_sm_new_sample_module_pins_match_framework_version(tmp_path: Path) -> None:
    """Issue #126/#119: sample hello module must pin framework deps to the
    actual published framework version, not the future ``>=1.0,<2.0`` range."""
    from importlib.metadata import version

    expected = version("simple_module_cli")
    runner = CliRunner()
    target = tmp_path / "demo"
    runner.invoke(
        app,
        ["new", "demo", "--yes", "--db", "sqlite", "--no-install", "--dest", str(target)],
    )
    text = (target / "modules" / "hello" / "pyproject.toml").read_text()
    for pkg in ("simple_module_core", "simple_module_db", "simple_module_hosting"):
        assert f"{pkg}=={expected}" in text, f"{pkg} should be pinned to =={expected}"
    # Dev pin: simple_module_test was the original >=0.1,<1.0 unsatisfiable case.
    assert f"simple_module_test=={expected}" in text


def test_sm_new_sample_module_seeds_static_dist_placeholder(tmp_path: Path) -> None:
    """Issue #127: hatch's force-include resolves at uv-sync time. A fresh
    scaffold must ship an empty ``static/dist/`` so the build doesn't fail
    before vite has had a chance to run."""
    runner = CliRunner()
    target = tmp_path / "demo"
    runner.invoke(
        app,
        ["new", "demo", "--yes", "--db", "sqlite", "--no-install", "--dest", str(target)],
    )
    static_dist = target / "modules" / "hello" / "hello" / "static" / "dist"
    assert static_dist.is_dir(), "static/dist/ must exist for hatch force-include"


def test_sm_new_sample_module_does_not_declare_view_prefix(tmp_path: Path) -> None:
    """Issue #138: fresh scaffold must not declare view_prefix so it boots
    without an SM019 warning (view routes registered but no menu entry or
    permissions)."""
    runner = CliRunner()
    target = tmp_path / "demo"
    runner.invoke(
        app,
        ["new", "demo", "--yes", "--db", "sqlite", "--no-install", "--dest", str(target)],
    )
    module_py = (target / "modules" / "hello" / "hello" / "module.py").read_text()
    assert "view_prefix" not in module_py
