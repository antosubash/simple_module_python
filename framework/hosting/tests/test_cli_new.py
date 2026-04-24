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


def test_sm_version_flag() -> None:
    result = CliRunner().invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "sm" in result.output


def test_sm_list_modules_prints_header() -> None:
    result = CliRunner().invoke(main, ["list-modules"])
    assert result.exit_code == 0, result.output
    # Either we see the column header (modules discovered) or the empty-state message.
    assert "PACKAGE" in result.output or "No modules discovered" in result.output


def test_sm_gen_pages_missing_dir_has_hint(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["gen-pages", "--host-dir", str(tmp_path / "nope")])
    assert result.exit_code != 0
    # Click .exists=True on --host-dir rejects missing path; no hint expected in that branch.
    # Exercise the default-path branch by running without --host-dir from a cwd w/o client_app.
    with runner.isolated_filesystem(temp_dir=str(tmp_path)):
        result = runner.invoke(main, ["gen-pages"])
    assert result.exit_code != 0
    combined = result.output + (result.stderr or "")
    assert "hint:" in combined
