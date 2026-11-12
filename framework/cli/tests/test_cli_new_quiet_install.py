"""`smpy new` keeps tool chatter out of a successful run (GH #917).

A first run printed ~150 lines (uv's package list, alembic's INFO lines) and
"Next steps: cd <app>" before the install had even started.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from simple_module_cli import new as new_mod
from simple_module_cli.cli import app
from typer.testing import CliRunner


def _invoke(tmp_path: Path, monkeypatch, *, fail: str | None = None):
    calls: list[list[str]] = []

    def fake_run(cmd, *, cwd, check, capture_output=False, text=False, errors=None):
        del cwd, check, errors
        calls.append(list(cmd))
        assert capture_output and text, f"{cmd} must not stream to the terminal"
        failed = fail is not None and fail in cmd
        return subprocess.CompletedProcess(
            cmd,
            1 if failed else 0,
            stdout=f"chatter from {cmd[0]}\n",
            stderr="boom\n" if failed else "",
        )

    monkeypatch.setattr(new_mod.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(new_mod.subprocess, "run", fake_run)
    result = CliRunner().invoke(
        app, ["new", "demo", "--yes", "--db", "sqlite", "--dest", str(tmp_path / "demo")]
    )
    return result, calls


def test_successful_install_is_quiet_and_ends_with_next_steps(tmp_path, monkeypatch) -> None:
    result, calls = _invoke(tmp_path, monkeypatch)

    assert result.exit_code == 0, result.output
    assert any("upgrade" in c for c in calls)
    assert "chatter from" not in result.output
    assert result.output.count("Next steps") == 1
    assert result.output.index("Next steps") > result.output.index("Setup complete")
    assert "make dev" in result.output.split("Next steps", 1)[1]


def test_a_failing_step_shows_its_output(tmp_path, monkeypatch) -> None:
    result, _ = _invoke(tmp_path, monkeypatch, fail="npm")

    assert "chatter from npm" in result.output
    assert "boom" in result.output
    assert "failed" in result.output


def test_a_failed_initial_migration_stops_and_prints_the_manual_steps(
    tmp_path, monkeypatch
) -> None:
    result, calls = _invoke(tmp_path, monkeypatch, fail="--autogenerate")

    assert not any("upgrade" in c for c in calls)
    steps = result.output.split("Next steps", 1)[1]
    assert "make migration" in steps
    assert "make migrate" in steps
    assert "Setup complete" not in result.output
