"""Tests for the `smpy new` scaffold layout and generated-app quality gates.

Split out of test_cli_new.py to keep both files under the 300-line cap. Covers
the generated app's layout (workspace vs flat), the dev-api reload watching
modules/, and the Makefile / root-pyproject quality-gate plumbing
(regressions #201, #202).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
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
    assert not (
        target / "modules/hello/hello/core/settings.py"
    ).exists()  # opt-in via --with-settings (#981)
    assert (target / "modules/hello/hello/web/endpoints/api.py").is_file()
    assert (target / "modules/hello/tests/web/crud/test_hello_crud.py").is_file()


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


def test_sm_new_dev_api_reloads_on_locale_edits(tmp_path: Path) -> None:
    """GH #930: the reloader watches only *.py by default, so a locale edit
    never reached a running `make dev`."""
    from simple_module_cli.app_project import create_app_project

    for flat in (False, True):
        target = tmp_path / ("flat" if flat else "ws")
        create_app_project(target, name="demo", db="sqlite", tenancy=False, selected=[], flat=flat)
        assert "--reload-include '*locales/*.json'" in (target / "Makefile").read_text()


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


def test_sm_new_makefile_cleanup_does_not_search_for_processes(tmp_path: Path) -> None:
    """Cleanup belongs to the supervisor, never a name/port process search."""
    from simple_module_cli.app_project import create_app_project

    target = tmp_path / "demo"
    create_app_project(target, name="demo", db="sqlite", tenancy=False, selected=[])
    makefile = (target / "Makefile").read_text()
    assert "pkill" not in makefile
    assert "lsof" not in makefile
    assert "Ctrl-C" in makefile
    assert "--port $(API_PORT)" in makefile
    assert "s/^SM_VITE_DEV_URL=" not in makefile


@pytest.mark.parametrize("flat", [False, True])
def test_sm_new_makefile_uses_unified_commands(tmp_path: Path, flat: bool) -> None:
    """Install/build prepare all artifacts; dev delegates to the process owner."""
    from simple_module_cli.app_project import create_app_project

    if shutil.which("make") is None:
        pytest.skip("make is not installed")
    target = tmp_path / "demo"
    create_app_project(target, name="demo", db="sqlite", tenancy=False, selected=[], flat=flat)
    actions = {
        "install": "uv run smpy gen",
        "build": "uv run smpy gen",
        "dev": "uv run smpy dev",
        "doctor": "uv run smpy doctor",
        "gen-pages": "uv run smpy host gen-pages",
        "gen-i18n": "uv run smpy host gen-i18n",
        "sync-js-deps" if flat else "sync-module-deps": "uv run smpy host sync-js-deps",
    }
    for action, command in actions.items():
        result = subprocess.run(["make", "-n", action], cwd=target, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert command in result.stdout
        if action == "dev":
            assert "uv run smpy dev" in result.stdout
            assert "uvicorn" not in result.stdout
        elif action in ("install", "build"):
            assert "uv run smpy gen" in result.stdout
            if action == "build":
                assert result.stdout.index("smpy gen") < result.stdout.index("npm run build")


def test_host_template_makefile_has_no_pkill() -> None:
    from simple_module_cli import app_project

    host_makefile = Path(app_project.__file__).parent / "templates" / "host" / "Makefile"
    assert "pkill" not in host_makefile.read_text()


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
    assert data["tool"]["ty"]["rules"]["missing-attribute"] == "ignore"
    assert data["tool"]["ty"]["rules"]["missing-union-attribute"] == "ignore"


@pytest.mark.parametrize("with_settings", [False, True])
def test_sm_new_generated_app_passes_its_own_lint(tmp_path: Path, with_settings: bool) -> None:
    """Regression #201: a freshly scaffolded app must pass its own `make lint`
    gate out of the box, including a new module with optional settings. Run
    the shipped Makefile against local framework/tools without a network install."""
    ruff = shutil.which("ruff")
    if ruff is None:
        pytest.skip("ruff not installed")

    runner = CliRunner()
    target = tmp_path / "demo"
    result = runner.invoke(
        app, ["new", "demo", "--yes", "--db", "sqlite", "--no-install", "--dest", str(target)]
    )
    assert result.exit_code == 0, result.output

    from simple_module_cli.scaffolding import create_module

    create_module(
        target / "modules" / "orders", "orders", standalone=False, with_settings=with_settings
    )
    # Use the already-installed checkout tools and framework, without resolving
    # another environment or downloading packages into the generated app.
    env = {
        **os.environ,
        "VIRTUAL_ENV": sys.prefix,
        "UV_PROJECT_ENVIRONMENT": sys.prefix,
        "UV_NO_SYNC": "1",
    }
    lint = subprocess.run(
        ["make", "lint"], cwd=target, env=env, capture_output=True, text=True, timeout=90
    )
    assert lint.returncode == 0, lint.stdout + lint.stderr

    fmt = subprocess.run(
        [ruff, "format", "--check", "."], cwd=target, capture_output=True, text=True
    )
    assert fmt.returncode == 0, f"`ruff format --check` failed:\n{fmt.stdout}\n{fmt.stderr}"
    check = subprocess.run([ruff, "check", "."], cwd=target, capture_output=True, text=True)
    assert check.returncode == 0, f"`ruff check` failed:\n{check.stdout}\n{check.stderr}"


def test_landing_page_next_steps_match_the_first_module_guide() -> None:
    """GH #898: `/setup` already creates the first admin, a module still has to
    be wired into the host, and "Read the docs" goes to the docs site."""
    from simple_module_cli import app_project

    landing = (
        Path(app_project.__file__).parent / "templates" / "host" / "client_app" / "pages"
    ) / "Landing.tsx"
    text = landing.read_text(encoding="utf-8")
    assert "create-admin" not in text
    assert "smpy add ../modules/orders --path host" in text
    assert "make migrate" in text
    assert "https://docs.py.simplemodule.dev/" in text
