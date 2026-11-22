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
        ["make", "migration", "LABEL=orders", "msg=add field"],
        cwd=target,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.splitlines()[-2:] == ["--head", "orders@head"]
