"""Tests for the `smpy new` interactive wizard."""

from __future__ import annotations

import typer
from simple_module_cli.wizard import run_wizard
from typer.testing import CliRunner


def _drive(answers: list[str]) -> tuple[str, bool, list[str], str]:
    """Run the wizard with stdin pre-fed; return (db, tenancy, selected, output)."""
    captured: dict = {}
    wrapper_app = typer.Typer()

    @wrapper_app.command()
    def wrapper() -> None:
        db, tenancy, selected = run_wizard(default_db="sqlite", default_tenancy=False)
        captured["db"] = db
        captured["tenancy"] = tenancy
        captured["selected"] = selected

    runner = CliRunner()
    result = runner.invoke(wrapper_app, [], input="\n".join(answers) + "\n")
    assert result.exit_code == 0, result.output
    return captured["db"], captured["tenancy"], captured["selected"], result.output


def test_wizard_standard_preset_default_path() -> None:
    db, tenancy, selected, out = _drive(["", "", "", ""])
    assert db == "sqlite"
    assert tenancy is False
    assert "users" in selected and "dashboard" in selected and "permissions" in selected
    assert "auth" in selected
    assert "Added auth (required by" in out


def test_wizard_postgres_with_tenancy() -> None:
    db, tenancy, _selected, _out = _drive(["postgres", "y", "", ""])
    assert db == "postgres"
    assert tenancy is True


def test_wizard_minimal_preset() -> None:
    _, _, selected, _ = _drive(["", "", "1", ""])
    assert set(selected) == {"users", "auth"}


def test_wizard_full_preset_includes_background_tasks() -> None:
    _, _, selected, _ = _drive(["", "", "3", ""])
    assert "background_tasks" in selected
    assert len(selected) >= 7


def test_wizard_custom_picks_only_yes_answers() -> None:
    answers = ["", "", "4"] + ["n"] * 7 + ["y", ""]
    _, _, selected, out = _drive(answers)
    assert set(selected) == {"background_tasks", "users", "auth"}
    assert "Added users (required by background_tasks)" in out
    assert "Added auth (required by users)" in out


def test_wizard_aborts_on_confirm_no() -> None:
    captured: dict = {}
    wrapper_app = typer.Typer()

    @wrapper_app.command()
    def wrapper() -> None:
        try:
            run_wizard(default_db="sqlite", default_tenancy=False)
        except typer.Abort:
            captured["aborted"] = True
            raise

    runner = CliRunner()
    result = runner.invoke(wrapper_app, [], input="\n".join(["", "", "", "n"]) + "\n")
    assert result.exit_code != 0
    assert captured.get("aborted") is True
