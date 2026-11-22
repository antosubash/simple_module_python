"""CLI command tests for ``smpy openapi gen-types`` (#504)."""

from __future__ import annotations

from pathlib import Path

from simple_module_cli.cli import app
from typer.testing import CliRunner


def test_cli_refuses_a_module_outside_the_project(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "templates").mkdir()
    monkeypatch.setenv("SM_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'x.db'}")
    monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
    result = CliRunner().invoke(app, ["openapi", "gen-types", "--module", "feature_flags"])
    assert result.exit_code == 1
    assert "outside" in result.output


def test_cli_without_opted_in_modules_says_so(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "templates").mkdir()
    monkeypatch.setenv("SM_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'x.db'}")
    monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
    result = CliRunner().invoke(app, ["openapi", "gen-types"])
    assert result.exit_code == 0, result.output
    assert "pass --module" in result.output
