"""Reject invalid recipes and destinations before writing migration source."""

import py_compile
from importlib.metadata import EntryPoint, EntryPoints

import pytest
from simple_module_cli.cli import app
from simple_module_cli.commands import migrations_cmd
from typer.testing import CliRunner

_UPGRADE = "mail.settings_namespace_v1"


def test_prepare_walks_past_workspace_package_to_the_project_root(alembic_host, monkeypatch):
    host, versions = alembic_host
    workspace = host / "workspace"
    workspace.mkdir()
    (workspace / "pyproject.toml").touch()
    monkeypatch.delenv("SM_PROJECT_ROOT", raising=False)
    monkeypatch.chdir(workspace)
    args = ["migrations", "prepare", _UPGRADE, "--head", "local"]

    explicit = CliRunner().invoke(app, [*args, "--config", "alembic.ini"])
    assert explicit.exit_code == 2
    assert list(versions.glob("*.py")) == [versions / "local.py"]

    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output


def test_prepare_names_both_colliding_recipes_without_importing_them(alembic_host, monkeypatch):
    entries = EntryPoints(
        EntryPoint(name=_UPGRADE, group="simple_module.data_upgrades", value=value)
        for value in ("first:recipe", "second:recipe")
    )
    loads = []
    monkeypatch.setattr(migrations_cmd, "data_upgrade_entry_points", lambda: entries)
    monkeypatch.setattr(EntryPoint, "load", lambda entry: loads.append(entry.value))

    result = CliRunner().invoke(app, ["migrations", "prepare", _UPGRADE, "--head", "local"])

    assert not loads
    assert result.exit_code == 2
    assert "first:recipe" in result.output
    assert "second:recipe" in result.output


@pytest.mark.parametrize(
    "recipe",
    [
        ["label", "def upgrade(): pass\ndef downgrade(): pass\n"],
        ("label", "def upgrade(): pass\n"),
        ("label", "def upgrade(context): pass\ndef downgrade(): pass\n"),
        ("label", "if True:\n"),
        ("label", "def upgrade():\n    break\ndef downgrade(): pass\n"),
    ],
    ids=["wrong-shape", "missing-downgrade", "required-argument", "syntax-error", "compile-error"],
)
def test_prepare_rejects_invalid_recipe_output(alembic_host, monkeypatch, recipe):
    _, versions = alembic_host
    monkeypatch.setattr(EntryPoint, "load", lambda entry: lambda: recipe)
    result = CliRunner().invoke(app, ["migrations", "prepare", _UPGRADE, "--head", "local"])

    assert result.exit_code == 2, result.output
    assert list(versions.glob("*.py")) == [versions / "local.py"]


@pytest.mark.parametrize("kind", ["symlink", "sourceless"])
def test_prepare_rejects_a_head_without_a_scanned_source_file(alembic_host, kind):
    host, versions = alembic_host
    source = versions / "local.py"
    if kind == "symlink":
        target = host / "external.py"
        source.rename(target)
        source.symlink_to(target)
    else:
        py_compile.compile(str(source), doraise=True)
        source.unlink()
        with (host / "alembic.ini").open("a") as output:
            output.write("sourceless = true\n")

    before = set(host.rglob("*.py"))
    result = CliRunner().invoke(app, ["migrations", "prepare", _UPGRADE, "--head", "local"])

    assert result.exit_code == 2, result.output
    assert set(host.rglob("*.py")) == before
