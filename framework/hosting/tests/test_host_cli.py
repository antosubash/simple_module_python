"""Smoke tests for the simple_module_hosting host_cli Typer plugin."""

from __future__ import annotations

from pathlib import Path

import typer
from typer.testing import CliRunner

from simple_module_hosting.host_cli import app


def test_app_is_typer_instance() -> None:
    assert isinstance(app, typer.Typer)


def test_help_lists_gen_pages_and_sync_js_deps() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "gen-pages" in result.output
    assert "sync-js-deps" in result.output


def test_gen_pages_errors_on_missing_client_app(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app, ["gen-pages", "--host-dir", str(tmp_path / "does-not-exist")]
    )
    assert result.exit_code != 0
    assert "not found" in result.output.lower() or "not found" in (result.stderr or "").lower()
