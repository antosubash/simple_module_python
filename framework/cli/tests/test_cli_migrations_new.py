"""Module migrations choose a branch in flat and workspace hosts (#984)."""

from os import pathsep
from pathlib import Path
from shutil import copyfile

import alembic
import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from simple_module_cli import migrations_cmd
from simple_module_cli.cli import app
from typer.testing import CliRunner


@pytest.mark.parametrize("label", [None, "orders"])
def test_new_selects_existing_label_or_creates_labelled_root(alembic_host, monkeypatch, label):
    host, versions = alembic_host
    if label:
        (versions / "local.py").write_text(
            "revision = 'local'\ndown_revision = None\nbranch_labels = ('orders',)\n"
        )
    calls = []
    monkeypatch.setattr(
        migrations_cmd,
        "_default_exec_runner",
        lambda cmd, cwd: calls.append((cmd, cwd)) or 0,
        raising=False,
    )
    result = CliRunner().invoke(app, ["migrations", "new", "orders", "-m", "init"])
    assert result.exit_code == 0, result.output
    assert calls == [
        (
            [
                "uv",
                "run",
                "alembic",
                "-c",
                str(host / "alembic.ini"),
                "revision",
                "--autogenerate",
                "-m",
                "init",
                *(
                    ["--head", "orders@head"]
                    if label
                    else [
                        "--head",
                        "base",
                        "--branch-label",
                        "orders",
                        "--version-path",
                        str(versions),
                    ]
                ),
            ],
            host,
        )
    ]


def test_new_workspace_keeps_app_root_as_cwd(alembic_host, monkeypatch):
    root, _ = alembic_host
    host = root / "host"
    host.mkdir()
    (root / "migrations").rename(host / "migrations")
    (root / "alembic.ini").rename(host / "alembic.ini")
    calls = []
    monkeypatch.setattr(
        migrations_cmd,
        "_default_exec_runner",
        lambda cmd, cwd: calls.append((cmd, cwd)) or 0,
        raising=False,
    )
    result = CliRunner().invoke(app, ["migrations", "new", "orders", "-m", "init"])
    assert result.exit_code == 0, result.output
    assert calls[0][0][:6] == ["uv", "run", "--project", str(host), "alembic", "-c"]
    assert calls[0][1] == root


def test_new_propagates_alembic_failure(alembic_host, monkeypatch):
    monkeypatch.setattr(migrations_cmd, "_default_exec_runner", lambda *a: 1, raising=False)
    result = CliRunner().invoke(app, ["migrations", "new", "orders", "-m", "init"])
    assert result.exit_code == 1


def test_first_root_with_multiple_version_locations_is_created_in_configured_directory(
    alembic_host, monkeypatch
):
    host, versions = alembic_host
    destination = host / "custom_versions"
    destination.mkdir()
    ini = host / "alembic.ini"
    with ini.open("a") as output:
        output.write(f"path_separator = os\nversion_locations = {destination}{pathsep}{versions}\n")
    copyfile(
        Path(alembic.__file__).parent / "templates/generic/script.py.mako",
        host / "migrations/script.py.mako",
    )

    def execute(cmd, cwd):
        # Exercise Alembic's revision placement without database autogeneration.
        command.revision(
            Config(str(ini)),
            message="init",
            head=cmd[cmd.index("--head") + 1],
            branch_label=cmd[cmd.index("--branch-label") + 1],
            version_path=cmd[cmd.index("--version-path") + 1] if "--version-path" in cmd else None,
        )
        return 0

    monkeypatch.setattr(migrations_cmd, "_default_exec_runner", execute)
    result = CliRunner().invoke(app, ["migrations", "new", "orders", "-m", "init"])
    assert result.exit_code == 0, result.output
    revision = ScriptDirectory.from_config(Config(str(ini))).get_revision("orders@head")
    assert revision.down_revision is None
    assert Path(revision.path).parent == destination
    assert [path.name for path in versions.glob("*.py")] == ["local.py"]
