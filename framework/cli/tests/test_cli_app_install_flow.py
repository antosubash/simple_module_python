"""A ``smpy new`` app stays installed under plain uv commands (GH #916).

The workspace root used to have no dependencies, so ``uv sync`` at the root,
or the ``uv sync --extra dev`` that ``create-module`` printed, uninstalled the
app's own modules from the shared venv.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from simple_module_cli.cli import app
from typer.testing import CliRunner


def _new_app(tmp_path: Path) -> tuple[Path, str]:
    target = tmp_path / "demo"
    result = CliRunner().invoke(
        app, ["new", "demo", "--yes", "--db", "sqlite", "--no-install", "--dest", str(target)]
    )
    assert result.exit_code == 0, result.output
    return target, result.output


def test_root_project_installs_the_host_through_a_workspace_source(tmp_path) -> None:
    target, _ = _new_app(tmp_path)
    root = tomllib.loads((target / "pyproject.toml").read_text(encoding="utf-8"))
    host = tomllib.loads((target / "host" / "pyproject.toml").read_text(encoding="utf-8"))
    host_name = host["project"]["name"]

    assert root["project"]["dependencies"] == [host_name]
    assert root["tool"]["uv"]["sources"][host_name] == {"workspace": True}


def test_no_install_next_steps_use_make_install(tmp_path) -> None:
    _, output = _new_app(tmp_path)
    steps = output.split("Next steps:", 1)[1]
    assert "  make install\n" in steps
    assert "  uv sync\n" not in steps
    assert "  npm install\n" not in steps  # make install runs it


def test_create_module_inside_an_app_wires_and_syncs(tmp_path, monkeypatch) -> None:
    target, _ = _new_app(tmp_path)
    monkeypatch.chdir(target)
    calls = []
    monkeypatch.setattr(
        "simple_module_cli._add_install._default_exec_runner",
        lambda cmd, cwd: calls.append((cmd, cwd)) or 0,
    )
    result = CliRunner().invoke(app, ["create-module", "notes", "--dest", "modules/notes"])

    assert result.exit_code == 0, result.output
    steps = result.output.split("Next step", 1)[1]
    host = tomllib.loads((target / "host/pyproject.toml").read_text())
    assert "simple_module_notes" in host["project"]["dependencies"]
    assert host["tool"]["uv"]["sources"]["simple_module_notes"] == {"workspace": True}
    assert [call[0] for call in calls] == [
        ["uv", "sync", "--all-packages"],
        ["npm", "install"],
        ["uv", "run", "smpy", "gen"],
    ]
    assert all(cwd == target for _, cwd in calls)
    assert 'uv run smpy migrations new notes -m "init"' in steps
    assert "make migrate" in steps
    assert "smpy add" not in steps
    assert "make install" not in result.output
    assert "restart `make dev`" in steps
    assert "uv sync --extra dev" not in result.output


def test_create_module_outside_an_app_keeps_the_package_flow(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["create-module", "notes", "--dest", "notes"])

    assert result.exit_code == 0, result.output
    assert "uv sync --extra dev" in result.output
    assert "uv run smpy module verify" in result.output
    assert "npm install" not in result.output
    assert "npm run typecheck" not in result.output
