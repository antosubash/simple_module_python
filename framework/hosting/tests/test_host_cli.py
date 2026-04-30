"""Smoke tests for the simple_module_hosting host_cli Typer plugin."""

from __future__ import annotations

from pathlib import Path

import typer
from simple_module_hosting.host_cli import app
from typer.testing import CliRunner


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
    result = runner.invoke(app, ["gen-pages", "--host-dir", str(tmp_path / "does-not-exist")])
    assert result.exit_code != 0
    assert "not found" in result.output.lower() or "not found" in (result.stderr or "").lower()


def test_module_entrypoint_runs_cli() -> None:
    """``python -m simple_module_hosting`` must invoke the Typer app, not silently no-op."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "simple_module_hosting", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "gen-pages" in result.stdout
    assert "sync-js-deps" in result.stdout


def test_host_cli_module_dunder_main_runs_cli() -> None:
    """``python -m simple_module_hosting.host_cli`` must also invoke the Typer app."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m", "simple_module_hosting.host_cli", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "gen-pages" in result.stdout
