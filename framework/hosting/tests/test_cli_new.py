"""Tests for the `sm new` / `simple-module new` CLI subcommand."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner
from simple_module_hosting.cli import main


def test_sm_new_creates_app_directory(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "my-app"
    result = runner.invoke(
        main,
        ["new", "my-app", "--yes", "--db", "sqlite", "--no-install", "--dest", str(target)],
    )
    assert result.exit_code == 0, result.output
    assert target.is_dir()


def test_sm_new_generates_pyproject_with_expected_deps(tmp_path: Path) -> None:
    runner = CliRunner()
    target = tmp_path / "my-app"
    runner.invoke(
        main,
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
        main,
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
        main,
        ["new", "my-app", "--yes", "--db", "sqlite", "--no-install", "--dest", str(target)],
    )
    env_text = (target / ".env.example").read_text()
    assert "SM_SECRET_KEY=" in env_text
    assert "CHANGE-ME" not in env_text
    secret_line = next(ln for ln in env_text.splitlines() if ln.startswith("SM_SECRET_KEY="))
    assert len(secret_line.split("=", 1)[1]) >= 20


def test_sm_new_refuses_to_overwrite(tmp_path: Path) -> None:
    target = tmp_path / "my-app"
    target.mkdir()
    (target / "existing.txt").write_text("x")

    runner = CliRunner()
    result = runner.invoke(
        main,
        ["new", "my-app", "--yes", "--db", "sqlite", "--no-install", "--dest", str(target)],
    )
    assert result.exit_code != 0
    assert "exists" in result.output.lower() or "exists" in (result.stderr or "").lower()
