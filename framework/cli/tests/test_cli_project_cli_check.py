"""`smpy` says when it is not the CLI of the app it runs in (GH #929)."""

from __future__ import annotations

import builtins
import tomllib
from pathlib import Path

import pytest
from simple_module_cli import cli as cli_mod
from simple_module_cli._project_cli_check import app_framework_pin, warn_if_not_the_apps_cli
from simple_module_cli.app_project import create_app_project
from simple_module_cli.cli import app
from simple_module_cli.pins import resolve_framework_version
from typer.testing import CliRunner

_APP = '[project]\nname = "demo"\nversion = "0.1.0"\ndependencies = []\n'


def _app(root: Path, *, root_dev: list[str] | None = None, host: list[str] | None = None) -> Path:
    root.mkdir(parents=True)
    groups = f"\n[dependency-groups]\ndev = {root_dev!r}\n".replace("'", '"') if root_dev else ""
    (root / "pyproject.toml").write_text(_APP + groups, encoding="utf-8")
    if host is not None:
        (root / "host").mkdir()
        deps = repr(host).replace("'", '"')
        (root / "host" / "pyproject.toml").write_text(
            f'[project]\nname = "demo-host"\nversion = "0.1.0"\ndependencies = {deps}\n',
            encoding="utf-8",
        )
    return root


def test_the_workspace_root_keeps_the_cli_in_its_dev_group(tmp_path: Path) -> None:
    target = tmp_path / "demo"
    create_app_project(target, name="demo", db="sqlite", tenancy=False, selected=[])
    root = tomllib.loads((target / "pyproject.toml").read_text(encoding="utf-8"))
    version = resolve_framework_version()
    assert f"simple_module_cli=={version}" in root["dependency-groups"]["dev"]


def test_the_pin_is_found_from_a_module_subdirectory(tmp_path: Path) -> None:
    root = _app(tmp_path / "demo", host=["simple_module_core==0.0.46"])
    nested = root / "modules" / "notes"
    nested.mkdir(parents=True)
    assert app_framework_pin(nested) == (root.resolve(), "0.0.46")


def test_ranges_are_not_pins(tmp_path: Path) -> None:
    _app(tmp_path / "demo", root_dev=["simple_module_test>=0.0.40"])
    assert app_framework_pin(tmp_path / "demo") is None


@pytest.mark.parametrize("command", [None, "create-module", "doctor"])
def test_a_mismatch_warns_once(tmp_path: Path, capsys, command) -> None:
    root = _app(tmp_path / "demo", root_dev=["simple_module_cli==0.0.46"])
    warn_if_not_the_apps_cli(command, "0.0.45", root)
    err = capsys.readouterr().err
    assert err.count("WARNING") == 1
    assert "0.0.46" in err
    assert "0.0.45" in err
    assert "uv run smpy" in err


@pytest.mark.parametrize("command", ["new", "update", "package-update"])
def test_version_changing_commands_do_not_warn(tmp_path: Path, capsys, command) -> None:
    root = _app(tmp_path / "demo", root_dev=["simple_module_cli==0.0.46"])
    warn_if_not_the_apps_cli(command, "0.0.45", root)
    assert capsys.readouterr().err == ""


def test_a_matching_version_and_no_app_stay_silent(tmp_path: Path, capsys) -> None:
    root = _app(tmp_path / "demo", root_dev=["simple_module_cli==0.0.46"])
    warn_if_not_the_apps_cli("doctor", "0.0.46", root)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    warn_if_not_the_apps_cli("doctor", "0.0.45", outside)
    assert capsys.readouterr().err == ""


def _without_core(monkeypatch) -> None:
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("simple_module_core"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(cli_mod, "resolve_framework_version", lambda: "0.0.46")


def test_doctor_inside_an_app_names_the_wrong_smpy(tmp_path: Path, monkeypatch) -> None:
    root = _app(tmp_path / "demo", host=["simple_module_core==0.0.46"])
    monkeypatch.chdir(root)
    _without_core(monkeypatch)
    result = CliRunner().invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "not installed in this project's venv" in result.output
    assert "run it inside a project" not in result.output


def test_doctor_outside_a_project_keeps_the_plain_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _without_core(monkeypatch)
    result = CliRunner().invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "run it inside a project" in result.output
