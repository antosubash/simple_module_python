"""Tests for entry-point-based plugin discovery."""

from __future__ import annotations

import textwrap
from importlib.metadata import EntryPoint

import pytest
import typer
from simple_module.plugins import discover_and_mount
from typer.testing import CliRunner


def _make_entry(name: str, module_attr: str) -> EntryPoint:
    return EntryPoint(name=name, value=module_attr, group="simple_module.cli_plugins")


@pytest.fixture
def fake_plugin_module(tmp_path, monkeypatch):
    """Create a tiny package on sys.path that exports a Typer ``app``."""
    import sys

    pkg_dir = tmp_path / "fake_sm_plugin"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(
        textwrap.dedent(
            """
            import typer
            app = typer.Typer(help="Fake plugin.")

            @app.command("ping")
            def ping():
                typer.echo("pong-from-fake")
            """
        )
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    yield "fake_sm_plugin:app"
    sys.modules.pop("fake_sm_plugin", None)


def test_discover_mounts_valid_plugin(monkeypatch, fake_plugin_module) -> None:
    monkeypatch.setattr(
        "simple_module.plugins._iter_plugin_entries",
        lambda: [_make_entry("fake", fake_plugin_module)],
    )
    root = typer.Typer()
    discover_and_mount(root)

    runner = CliRunner()
    result = runner.invoke(root, ["fake", "ping"])
    assert result.exit_code == 0, result.output
    assert "pong-from-fake" in result.output


def _root_with_builtin() -> typer.Typer:
    """Typer requires at least one command before --help works."""
    root = typer.Typer()

    @root.command("noop")
    def _noop() -> None:
        pass

    return root


def test_discover_skips_broken_plugin(monkeypatch, capsys) -> None:
    bad = _make_entry("broken", "nonexistent_module:app")
    monkeypatch.setattr("simple_module.plugins._iter_plugin_entries", lambda: [bad])
    root = _root_with_builtin()
    discover_and_mount(root)  # should not raise

    captured = capsys.readouterr()
    assert "failed to load plugin 'broken'" in captured.err

    runner = CliRunner()
    result = runner.invoke(root, ["broken"])
    assert result.exit_code != 0


def test_discover_warns_on_duplicate_subgroup(monkeypatch, fake_plugin_module, capsys) -> None:
    a = _make_entry("dup", fake_plugin_module)
    b = _make_entry("dup", fake_plugin_module)
    monkeypatch.setattr("simple_module.plugins._iter_plugin_entries", lambda: [a, b])
    root = typer.Typer()
    discover_and_mount(root)
    captured = capsys.readouterr()
    assert "duplicate" in captured.err.lower() or "already" in captured.err.lower()


def test_discover_with_no_plugins_is_noop(monkeypatch) -> None:
    monkeypatch.setattr("simple_module.plugins._iter_plugin_entries", list)
    root = _root_with_builtin()
    discover_and_mount(root)
    runner = CliRunner()
    result = runner.invoke(root, ["--help"])
    assert result.exit_code == 0
