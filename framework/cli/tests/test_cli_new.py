"""Tests for the `sm new` / `simple-module new` CLI subcommand."""

from __future__ import annotations

import json
from pathlib import Path

from simple_module_cli.cli import app
from typer.testing import CliRunner


def test_sm_new_creates_app_directory(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "my-app"
    result = runner.invoke(
        app,
        ["new", "my-app", "--yes", "--db", "sqlite", "--no-install", "--dest", str(target)],
    )
    assert result.exit_code == 0, result.output
    assert target.is_dir()


def test_sm_new_generates_pyproject_with_expected_deps(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "my-app"
    runner.invoke(
        app,
        ["new", "my-app", "--yes", "--db", "sqlite", "--no-install", "--dest", str(target)],
    )
    pyproject_text = (target / "pyproject.toml").read_text()
    for required in (
        "simple_module_hosting",
        "simple_module_users",
        "simple_module_dashboard",
        "simple_module_permissions",
    ):
        assert required in pyproject_text, f"missing dep: {required}"


def test_sm_new_generates_package_json_with_npm_deps(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "my-app"
    runner.invoke(
        app,
        ["new", "my-app", "--yes", "--db", "sqlite", "--no-install", "--dest", str(target)],
    )
    data = json.loads((target / "package.json").read_text())
    assert "@simple-module-py/ui" in data.get("dependencies", {})
    assert "@simple-module-py/i18n" in data.get("dependencies", {})
    assert "@simple-module-py/tsconfig" in data.get("devDependencies", {})


def test_sm_new_writes_generated_secret_key(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "my-app"
    runner.invoke(
        app,
        ["new", "my-app", "--yes", "--db", "sqlite", "--no-install", "--dest", str(target)],
    )
    env_text = (target / ".env.example").read_text()
    assert "SM_SECRET_KEY=" in env_text
    assert "CHANGE-ME" not in env_text
    secret_line = next(ln for ln in env_text.splitlines() if ln.startswith("SM_SECRET_KEY="))
    assert len(secret_line.split("=", 1)[1]) >= 20


def test_create_app_project_with_selected_kwarg(tmp_path: Path) -> None:
    from simple_module_cli.app_project import create_app_project

    target = tmp_path / "demo"
    create_app_project(
        target,
        name="demo",
        db="sqlite",
        tenancy=False,
        selected=["users", "background_tasks"],
    )

    pyproject = (target / "pyproject.toml").read_text()
    assert "simple_module_background_tasks" in pyproject
    assert "simple_module_auth" in pyproject  # auto-added (users requires auth)
    assert "simple_module_dashboard" not in pyproject


def test_create_app_project_runs_recipe_for_background_tasks(tmp_path: Path) -> None:
    from simple_module_cli.app_project import create_app_project

    target = tmp_path / "demo"
    create_app_project(
        target,
        name="demo",
        db="sqlite",
        tenancy=False,
        selected=["background_tasks"],
    )

    assert (target / "scripts" / "run_worker.py").is_file()
    assert (target / "docker-compose.yml").is_file()
    assert (target / "docker" / "worker.Dockerfile").is_file()
    makefile_text = (target / "Makefile").read_text()
    assert "worker:" in makefile_text


def test_create_app_project_default_selected_keeps_back_compat(tmp_path: Path) -> None:
    from simple_module_cli.app_project import create_app_project

    target = tmp_path / "demo"
    create_app_project(target, name="demo", db="sqlite", tenancy=False)
    pyproject = (target / "pyproject.toml").read_text()
    for required in (
        "simple_module_users",
        "simple_module_dashboard",
        "simple_module_permissions",
    ):
        assert required in pyproject


def test_sm_new_with_preset_full_includes_background_tasks(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "demo"
    result = runner.invoke(
        app,
        ["new", "demo", "--yes", "--preset", "full", "--no-install", "--dest", str(target)],
    )
    assert result.exit_code == 0, result.output
    assert (target / "scripts" / "run_worker.py").is_file()
    assert (target / "docker-compose.yml").is_file()
    pyproject = (target / "pyproject.toml").read_text()
    assert "simple_module_background_tasks" in pyproject


def test_sm_new_with_explicit_with_flag(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "demo"
    result = runner.invoke(
        app,
        [
            "new",
            "demo",
            "--yes",
            "--preset",
            "minimal",
            "--with",
            "background_tasks",
            "--no-install",
            "--dest",
            str(target),
        ],
    )
    assert result.exit_code == 0, result.output
    pyproject = (target / "pyproject.toml").read_text()
    assert "simple_module_users" in pyproject
    assert "simple_module_background_tasks" in pyproject
    assert "simple_module_auth" in pyproject


def test_sm_new_unknown_with_module_errors(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "demo"
    result = runner.invoke(
        app,
        ["new", "demo", "--yes", "--with", "does_not_exist", "--no-install", "--dest", str(target)],
    )
    assert result.exit_code != 0
    assert "does_not_exist" in result.output
    assert "available" in result.output.lower()


def test_sm_new_yes_with_no_flags_uses_standard_preset(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "demo"
    result = runner.invoke(
        app,
        ["new", "demo", "--yes", "--no-install", "--dest", str(target)],
    )
    assert result.exit_code == 0, result.output
    pyproject = (target / "pyproject.toml").read_text()
    for required in (
        "simple_module_users",
        "simple_module_dashboard",
        "simple_module_permissions",
    ):
        assert required in pyproject
    assert "simple_module_background_tasks" not in pyproject


def test_sm_new_interactive_full_preset(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "demo"
    result = runner.invoke(
        app,
        ["new", "demo", "--no-install", "--dest", str(target)],
        input="\n".join(["", "", "3", ""]) + "\n",
    )
    assert result.exit_code == 0, result.output
    assert (target / "docker-compose.yml").is_file()


def test_sm_new_refuses_to_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "my-app"
    target.mkdir()
    (target / "existing.txt").write_text("x")

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["new", "my-app", "--yes", "--db", "sqlite", "--no-install", "--dest", str(target)],
    )
    assert result.exit_code != 0
    assert "exists" in result.output.lower() or "exists" in (result.stderr or "").lower()
