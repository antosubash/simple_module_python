"""Tests for the wizard's git-module step."""

from __future__ import annotations

import typer
from simple_module_cli.wizard import run_wizard
from typer.testing import CliRunner


def _drive(answers: list[str]) -> dict:
    captured: dict = {}
    wrapper_app = typer.Typer()

    @wrapper_app.command()
    def wrapper() -> None:
        db, _tenancy, selected, git_specs = run_wizard(default_db="sqlite", default_tenancy=False)
        captured.update(db=db, selected=selected, git_specs=git_specs)

    runner = CliRunner()
    result = runner.invoke(wrapper_app, [], input="\n".join(answers) + "\n")
    assert result.exit_code == 0, result.output
    return captured


def test_wizard_collects_git_specs() -> None:
    captured = _drive(["", "", "", "y", "git+https://github.com/x/repo@v1.0.0", "", ""])
    assert captured["git_specs"] == ["git+https://github.com/x/repo@v1.0.0"]


def test_wizard_git_step_default_is_skip() -> None:
    captured = _drive(["", "", "", "", ""])
    assert captured["git_specs"] == []


def test_wizard_rejects_non_git_spec_and_reprompts() -> None:
    captured = _drive(
        ["", "", "", "y", "https://github.com/x/repo", "git+https://github.com/x/r", "", ""]
    )
    assert captured["git_specs"] == ["git+https://github.com/x/r"]
