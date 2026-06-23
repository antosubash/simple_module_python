"""Tests for the `smpy new` scaffold layout and generated-app quality gates.

Split out of test_cli_new.py to keep both files under the 300-line cap. Covers
the generated app's layout (workspace vs flat), the dev-api reload watching
modules/, and the Makefile / root-pyproject quality-gate plumbing
(regressions #201, #202).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest
from simple_module_cli.cli import app
from typer.testing import CliRunner


def test_sm_new_default_scaffolds_sample_hello_module(tmp_path: Path) -> None:
    """Default (workspace) mode lays down modules/hello/ as an authoring template."""
    runner = CliRunner()
    target = tmp_path / "demo"
    result = runner.invoke(
        app,
        ["new", "demo", "--yes", "--db", "sqlite", "--no-install", "--dest", str(target)],
    )
    assert result.exit_code == 0, result.output
    assert (target / "modules" / "hello" / "pyproject.toml").is_file()
    assert (target / "modules" / "hello" / "hello" / "module.py").is_file()


def test_sm_new_default_lays_down_workspace_layout(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "demo"
    runner.invoke(
        app,
        ["new", "demo", "--yes", "--db", "sqlite", "--no-install", "--dest", str(target)],
    )
    for relpath in ("pyproject.toml", "package.json", "Makefile", ".env.example"):
        assert (target / relpath).is_file(), f"missing workspace root file: {relpath}"
    for relpath in (
        "main.py",
        "alembic.ini",
        "pyproject.toml",
        "client_app/package.json",
        "client_app/vite.config.ts",
    ):
        assert (target / "host" / relpath).is_file(), f"missing host file: {relpath}"
    for relpath in (".env.example", "README.md", ".gitignore", "Makefile"):
        assert not (target / "host" / relpath).exists()
    assert not (target / "modules" / "hello" / ".github").exists()


def test_sm_new_default_wires_workspace_in_pyproject(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "demo"
    runner.invoke(
        app,
        ["new", "demo", "--yes", "--db", "sqlite", "--no-install", "--dest", str(target)],
    )
    workspace_pyproject = (target / "pyproject.toml").read_text()
    assert "[tool.uv.workspace]" in workspace_pyproject
    assert 'members = ["host", "modules/*"]' in workspace_pyproject

    host_pyproject = (target / "host" / "pyproject.toml").read_text()
    assert "simple_module_hello" in host_pyproject
    # Sample module is resolved from the workspace, not PyPI.
    assert "[tool.uv.sources" in host_pyproject
    assert "workspace = true" in host_pyproject


def test_sm_new_default_adds_npm_workspaces_field(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "demo"
    runner.invoke(
        app,
        ["new", "demo", "--yes", "--db", "sqlite", "--no-install", "--dest", str(target)],
    )
    data = json.loads((target / "package.json").read_text())
    assert data.get("workspaces") == ["host/client_app", "modules/*"]


def test_sm_new_flat_skips_modules_dir(tmp_path: Path) -> None:
    """``--flat`` keeps the legacy single-host layout: no modules/ tree, no sample."""
    runner = CliRunner()
    target = tmp_path / "demo"
    result = runner.invoke(
        app,
        ["new", "demo", "--yes", "--flat", "--no-install", "--dest", str(target)],
    )
    assert result.exit_code == 0, result.output
    assert not (target / "modules").exists()
    pyproject_text = (target / "pyproject.toml").read_text()
    assert "simple_module_hello" not in pyproject_text
    # No workspace plumbing pointing at a non-existent modules/ tree.
    assert "[tool.uv.workspace]" not in pyproject_text
    data = json.loads((target / "package.json").read_text())
    assert "workspaces" not in data


def test_sm_new_dev_api_watches_modules_dir(tmp_path: Path) -> None:
    """Regression #202: the dev-api reloader must watch modules/* so edits to
    in-repo module packages (routes/endpoints/locales) hot-reload — uvicorn
    otherwise only watches the launch cwd (host/)."""
    from simple_module_cli.app_project import create_app_project

    target = tmp_path / "demo"
    create_app_project(target, name="demo", db="sqlite", tenancy=False, selected=[])
    makefile = (target / "Makefile").read_text()
    assert "--reload-dir" in makefile
    assert "../modules" in makefile


def test_sm_new_makefile_has_quality_gate_targets(tmp_path: Path) -> None:
    """Regression #201: the scaffold Makefile must emit test/lint/doctor targets
    and use `alembic upgrade heads` (plural) for per-module branch heads."""
    from simple_module_cli.app_project import create_app_project

    target = tmp_path / "demo"
    create_app_project(target, name="demo", db="sqlite", tenancy=False, selected=[])
    makefile = (target / "Makefile").read_text()
    for tgt in ("test:", "test-py:", "test-js:", "lint:", "doctor:"):
        assert tgt in makefile, f"missing Makefile target {tgt}"
    assert "upgrade heads" in makefile
    assert "upgrade head\n" not in makefile  # the buggy singular form is gone


def test_sm_new_root_pyproject_has_dev_tooling_and_config(tmp_path: Path) -> None:
    """Regression #201: the workspace root must ship the dev tooling + pytest /
    ruff / ty config so `make test` and `make lint` work out of the box."""
    from simple_module_cli.app_project import create_app_project

    target = tmp_path / "demo"
    create_app_project(target, name="demo", db="sqlite", tenancy=False, selected=[])
    data = tomllib.loads((target / "pyproject.toml").read_text())

    dev = data["dependency-groups"]["dev"]
    joined = " ".join(dev)
    assert "ruff" in joined and "ty" in joined and "pytest" in joined
    # simple_module_test is pinned to the framework version, not the broken range.
    assert any(d.startswith("simple_module_test==") for d in dev)
    assert data["tool"]["pytest"]["ini_options"]["asyncio_mode"] == "auto"
    assert data["tool"]["ruff"]["line-length"] == 100
    assert "unresolved-attribute" in data["tool"]["ty"]["rules"]


def test_sm_new_generated_app_passes_its_own_ruff(tmp_path: Path) -> None:
    """Regression #201: a freshly scaffolded app must pass its own `make lint`
    ruff gate out of the box. Templates are excluded from the framework's own
    ruff, so violations in generated code only surface against the scaffold's
    shipped ruff config — this test runs it end to end."""
    ruff = shutil.which("ruff")
    if ruff is None:
        pytest.skip("ruff not installed")

    runner = CliRunner()
    target = tmp_path / "demo"
    result = runner.invoke(
        app, ["new", "demo", "--yes", "--db", "sqlite", "--no-install", "--dest", str(target)]
    )
    assert result.exit_code == 0, result.output

    fmt = subprocess.run(
        [ruff, "format", "--check", "."], cwd=target, capture_output=True, text=True
    )
    assert fmt.returncode == 0, f"`ruff format --check` failed:\n{fmt.stdout}\n{fmt.stderr}"
    check = subprocess.run([ruff, "check", "."], cwd=target, capture_output=True, text=True)
    assert check.returncode == 0, f"`ruff check` failed:\n{check.stdout}\n{check.stderr}"
