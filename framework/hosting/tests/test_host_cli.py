"""Smoke tests for the simple_module_hosting host_cli Typer plugin."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
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


@pytest.mark.parametrize(
    "module_target",
    ["simple_module_hosting", "simple_module_hosting.host_cli"],
)
def test_python_dash_m_invocation_runs_cli(module_target: str) -> None:
    """Both ``python -m simple_module_hosting`` and ``...host_cli`` must invoke
    the Typer app — without ``__main__.py`` / a ``__name__ == "__main__"`` block
    these silently no-op'd, breaking the documented ``gen-pages`` workflow.
    """
    result = subprocess.run(
        [sys.executable, "-m", module_target, "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "gen-pages" in result.stdout
