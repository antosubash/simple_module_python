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


def test_gen_pages_reports_manifest_error_without_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*_args: object, **_kwargs: object) -> None:
        raise ValueError("duplicate page 'X'")

    monkeypatch.setattr("simple_module_hosting.host_cli.write_module_pages_manifest", _boom)
    result = CliRunner().invoke(app, ["gen-pages", "--host-dir", str(tmp_path)])
    assert result.exit_code == 1
    assert "ERROR: duplicate page 'X'" in result.output
    assert not isinstance(result.exception, ValueError)


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


@pytest.mark.parametrize("skip", [False, True])
def test_gen_i18n_missing_package(tmp_path, monkeypatch, skip):
    monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
    args = ["gen-i18n", "--skip-if-missing"] if skip else ["gen-i18n"]
    result = CliRunner().invoke(app, args)

    assert result.exit_code == (0 if skip else 1), result.output
    assert "@simple-module-py/i18n" in result.output
    if skip:
        assert result.output.splitlines() == [
            "Skipping gen-i18n: @simple-module-py/i18n not found."
        ]


@pytest.mark.parametrize("workspace_root", [True, False], ids=["workspace", "flat"])
def test_sync_js_deps_targets_the_workspace_only_when_one_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, workspace_root: bool
) -> None:
    client_app = tmp_path / "client_app"
    client_app.mkdir()
    (client_app / "package.json").write_text("{}", encoding="utf-8")
    if workspace_root:
        (tmp_path / "package.json").write_text('{"workspaces": ["client_app"]}', encoding="utf-8")
    monkeypatch.setattr("simple_module_hosting.host_cli.discover_modules", list)
    monkeypatch.setattr("simple_module_hosting.host_cli.select_auth_provider", lambda m, _p: m)
    monkeypatch.setattr(
        "simple_module_hosting.host_cli.collect_module_js_deps", lambda _m: {"x": {"dep": "^1"}}
    )
    monkeypatch.setattr("simple_module_hosting.host_cli.shutil.which", lambda _n: "npm")

    result = CliRunner().invoke(
        app, ["sync-js-deps", "--host-client-app", str(client_app), "--dry-run"]
    )

    assert result.exit_code == 0, result.output
    assert ("--workspace client_app" in result.output) is workspace_root
