"""`smpy new --git-module` writes git sources into the scaffolded host."""

from __future__ import annotations

from pathlib import Path

from simple_module_cli.cli import app
from typer.testing import CliRunner


def test_new_with_git_module_writes_source(tmp_path: Path, make_git_module_repo) -> None:
    repo = make_git_module_repo([("simple_module_blog", "0.2.0", None, False)], tags=["v0.2.0"])
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "new",
            "demoapp",
            "--dest",
            str(tmp_path / "demoapp"),
            "--preset",
            "minimal",
            "--yes",
            "--no-install",
            "--git-module",
            f"git+{repo.as_uri()}@v0.2.0",
        ],
    )
    assert result.exit_code == 0, result.output
    # Workspace mode: module deps live in the host member's pyproject.
    text = (tmp_path / "demoapp" / "host" / "pyproject.toml").read_text(encoding="utf-8")
    assert "simple_module_blog>=0.2.0,<1.0" in text
    assert 'tag = "v0.2.0"' in text


def test_create_host_with_git_module_writes_source(tmp_path: Path, make_git_module_repo) -> None:
    repo = make_git_module_repo([("simple_module_blog", "0.2.0", None, False)], tags=["v0.2.0"])
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "create-host",
            "demohost",
            "--dest",
            str(tmp_path / "demohost"),
            "--git-module",
            f"git+{repo.as_uri()}@v0.2.0",
        ],
    )
    assert result.exit_code == 0, result.output
    text = (tmp_path / "demohost" / "pyproject.toml").read_text(encoding="utf-8")
    assert "simple_module_blog>=0.2.0,<1.0" in text
    assert 'tag = "v0.2.0"' in text
