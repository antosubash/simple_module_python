"""Module migrations choose a branch in flat and workspace hosts (#984)."""

import pytest
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
                    else ["--head", "base", "--branch-label", "orders"]
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
