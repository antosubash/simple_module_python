"""Published app scaffolds work with static assets and tenant discovery (#1087)."""

import os
import subprocess
import tomllib
from importlib.metadata import version

import pytest
from simple_module_cli.app_project import create_app_project
from simple_module_cli.catalog import CATALOG, expand_deps
from simple_module_cli.cli import app
from typer.testing import CliRunner


def test_tenants_catalog_declares_auth_dependency():
    assert CATALOG["tenants"].package == "simple_module_tenants"
    resolved, _ = expand_deps(["tenants"])
    assert resolved == ["auth", "tenants"]


@pytest.mark.parametrize("flat", [False, True])
def test_tenancy_installs_pinned_provider(tmp_path, flat):
    target = tmp_path / "app"
    args = ["new", "app", "--yes", "--tenancy", "--no-install", "--dest", str(target)]
    if flat:
        args.append("--flat")
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    host = target if flat else target / "host"
    deps = tomllib.loads((host / "pyproject.toml").read_text())["project"]["dependencies"]
    assert f"simple_module_tenants=={version('simple_module_cli')}" in deps


@pytest.mark.parametrize("flat", [False, True])
def test_scaffold_static_base_and_labelled_migration(tmp_path, flat):
    target = tmp_path / "app"
    host, _ = create_app_project(target, name="app", selected=[], flat=flat)
    config = (host / "client_app/vite.config.ts").read_text()
    assert "base: command === 'build' ? '/static/dist/' : '/'" in config
    # Execute the recipe with a fake uv; verify argv rather than Makefile text.
    uv = tmp_path / "bin/uv"
    uv.parent.mkdir()
    uv.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    uv.chmod(0o755)
    env = {**os.environ, "PATH": f"{uv.parent}:{os.environ['PATH']}"}
    missing = subprocess.run(
        ["make", "migration", "msg=add field"], cwd=target, env=env, capture_output=True, text=True
    )
    assert missing.returncode != 0
    assert "LABEL" in missing.stdout + missing.stderr
    result = subprocess.run(
        ["make", "-s", "migration", "LABEL=orders", "msg=add field"],
        cwd=target,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.splitlines() == [
        "run",
        "smpy",
        "migrations",
        "new",
        "orders",
        "-m",
        "add field",
    ]


@pytest.mark.parametrize("flat", [False, True])
def test_bootstrap_initial_branch_supports_make_migration_labels(tmp_path, monkeypatch, flat):
    from alembic import command
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from simple_module_cli import migrations_cmd
    from simple_module_cli import new as new_mod

    target = tmp_path / "app"
    host, _ = create_app_project(target, name="app", selected=[], flat=flat)
    ini = host / "alembic.ini"
    versions = host / "migrations/versions"

    # Real alembic graph: first capture the exact args `_bootstrap_initial_migration` builds,
    # then generate the initial revision with real Alembic outside the subprocess stub.
    bootstrap_calls: list[list[str]] = []

    def capture_bootstrap(cmd, *, cwd, check, capture_output=False, text=False, errors=None):
        del check, capture_output, text, errors
        assert cwd == target
        bootstrap_calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    with monkeypatch.context() as m:
        m.setattr(new_mod.subprocess, "run", capture_bootstrap)
        argv = new_mod._alembic_argv(target, host)
        assert new_mod._bootstrap_initial_migration(target, host, argv) is True

    cmd = bootstrap_calls[0]
    assert cmd[-2:] == ["--branch-label", "initial"]
    command.revision(
        Config(str(target / cmd[cmd.index("-c") + 1])),
        message="initial schema",
        branch_label=cmd[cmd.index("--branch-label") + 1],
        autogenerate=False,
    )

    script = ScriptDirectory.from_config(Config(str(ini)))
    assert script.get_revision("initial@head") is not None

    monkeypatch.chdir(target)
    monkeypatch.delenv("SM_PROJECT_ROOT", raising=False)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        migrations_cmd,
        "_default_exec_runner",
        lambda cmd, cwd: calls.append(cmd) or 0,
        raising=False,
    )
    assert CliRunner().invoke(app, ["migrations", "new", "initial", "-m", "update"]).exit_code == 0
    assert calls[-1][-2:] == ["--head", "initial@head"]

    assert (
        CliRunner().invoke(app, ["migrations", "new", "orders", "-m", "add orders"]).exit_code == 0
    )
    assert calls[-1][-6:] == [
        "--head",
        "base",
        "--branch-label",
        "orders",
        "--version-path",
        str(versions.resolve()),
    ]
