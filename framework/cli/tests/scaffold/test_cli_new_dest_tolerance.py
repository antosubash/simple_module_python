"""Regression tests for ``smpy new`` against a non-empty destination.

Issue #148: scaffolding into a directory that already contains a fresh
``git init`` (or ``gh repo create``) layout — ``.git/``, ``.gitignore``,
``README.md``, ``LICENSE`` — has to succeed without clobbering the user's
files. Arbitrary pre-existing entries must still hard-fail so we don't
overwrite real work.
"""

from __future__ import annotations

from pathlib import Path

from simple_module_cli.cli import app
from typer.testing import CliRunner


def test_sm_new_tolerates_git_init_leftovers_in_dest(tmp_path: Path) -> None:
    """``smpy new --dest .`` after ``git init`` / ``gh repo create`` must succeed,
    even with ``.git/``, ``.gitignore``, ``README.md``, ``LICENSE`` pre-existing —
    the scaffold preserves them and writes everything else."""
    runner = CliRunner()
    target = tmp_path / "demo"
    target.mkdir()
    (target / ".git").mkdir()
    user_gitignore = "*.pyc\n"
    (target / ".gitignore").write_text(user_gitignore)
    user_readme = "# demo (user-authored)\n"
    (target / "README.md").write_text(user_readme)
    (target / "LICENSE").write_text("MIT\n")

    result = runner.invoke(
        app,
        ["new", "demo", "--yes", "--db", "sqlite", "--no-install", "--dest", str(target)],
    )

    assert result.exit_code == 0, result.output
    assert (target / ".git").is_dir()
    assert (target / ".gitignore").read_text() == user_gitignore
    assert (target / "README.md").read_text() == user_readme
    assert (target / "LICENSE").read_text() == "MIT\n"
    assert (target / "host" / "pyproject.toml").is_file()
    assert (target / "modules" / "hello").is_dir()
    assert "Preserved existing files" in result.output
    assert ".gitignore" in result.output
    assert "README.md" in result.output


def test_sm_new_flat_tolerates_git_init_leftovers(tmp_path: Path) -> None:
    """Flat mode (host-at-target) must also tolerate the safe allowlist,
    since `smpy new --flat --dest .` is the same flow against a fresh
    `git init`."""
    runner = CliRunner()
    target = tmp_path / "demo"
    target.mkdir()
    (target / ".git").mkdir()
    (target / ".gitignore").write_text("# user\n")

    result = runner.invoke(
        app,
        [
            "new",
            "demo",
            "--yes",
            "--flat",
            "--db",
            "sqlite",
            "--no-install",
            "--dest",
            str(target),
        ],
    )

    assert result.exit_code == 0, result.output
    assert (target / ".gitignore").read_text() == "# user\n"
    assert (target / "pyproject.toml").is_file()


def test_sm_new_still_refuses_unrelated_files_in_dest(tmp_path: Path) -> None:
    """Tolerance is *narrow* — arbitrary pre-existing files (anything not in
    the safe allowlist) must still be a hard error so users don't accidentally
    scaffold over real work."""
    runner = CliRunner()
    target = tmp_path / "demo"
    target.mkdir()
    (target / "my_notes.md").write_text("don't clobber me")

    result = runner.invoke(
        app,
        ["new", "demo", "--yes", "--db", "sqlite", "--no-install", "--dest", str(target)],
    )

    assert result.exit_code != 0
    output = result.output + (result.stderr or "")
    assert "my_notes.md" in output
    assert (target / "my_notes.md").read_text() == "don't clobber me"
