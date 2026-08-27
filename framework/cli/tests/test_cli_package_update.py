"""Tests for `smpy package-update`."""

from __future__ import annotations

from pathlib import Path

import click
import pytest
from simple_module_cli import package_update as pu
from simple_module_cli.cli import app
from typer.testing import CliRunner


def test_updates_simple_module_deps(tmp_path: Path, fake_pypi) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "x"\nversion = "0.1.0"\n'
        "dependencies = [\n"
        '    "simple_module_core>=0.1",\n'
        '    "simple_module_db>=0.1,<3.0",\n'
        '    "fastapi>=0.110",\n'
        "]\n",
        encoding="utf-8",
    )

    pu.run_update(
        path=pyproject,
        dry_run=False,
        include_pre=False,
        fetcher=fake_pypi({"simple_module_core": "1.2.3", "simple_module_db": "2.0.0"}),
    )

    out = pyproject.read_text(encoding="utf-8")
    assert "simple_module_core>=1.2.3" in out
    assert "simple_module_db>=2.0.0,<3.0" in out  # upper bound preserved
    assert "fastapi>=0.110" in out  # untouched


def test_walks_workspace_members(tmp_path: Path, fake_pypi) -> None:
    root = tmp_path / "pyproject.toml"
    root.write_text(
        '[project]\nname = "root"\nversion = "0"\ndependencies = ["simple_module_core>=0.1"]\n'
        '\n[tool.uv.workspace]\nmembers = ["pkgs/*"]\n',
        encoding="utf-8",
    )
    member = tmp_path / "pkgs" / "alpha"
    member.mkdir(parents=True)
    (member / "pyproject.toml").write_text(
        '[project]\nname = "alpha"\nversion = "0"\ndependencies = ["simple_module_db>=0.1"]\n',
        encoding="utf-8",
    )

    pu.run_update(
        path=tmp_path,
        dry_run=False,
        include_pre=False,
        fetcher=fake_pypi({"simple_module_core": "1.0.0", "simple_module_db": "2.0.0"}),
    )

    assert "simple_module_core>=1.0.0" in root.read_text(encoding="utf-8")
    assert "simple_module_db>=2.0.0" in (member / "pyproject.toml").read_text(encoding="utf-8")


def test_skips_workspace_source_deps(tmp_path: Path, fake_pypi) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "x"\nversion = "0"\n'
        'dependencies = ["simple_module_core", "simple_module_db>=0.1"]\n'
        "\n[tool.uv.sources]\n"
        "simple_module_core = { workspace = true }\n",
        encoding="utf-8",
    )

    pu.run_update(
        path=pyproject,
        dry_run=False,
        include_pre=False,
        fetcher=fake_pypi({"simple_module_core": "9.9.9", "simple_module_db": "2.0.0"}),
    )

    out = pyproject.read_text(encoding="utf-8")
    assert '"simple_module_core"' in out  # untouched — workspace source
    assert "9.9.9" not in out
    assert "simple_module_db>=2.0.0" in out


def test_dry_run_does_not_write(tmp_path: Path, fake_pypi) -> None:
    pyproject = tmp_path / "pyproject.toml"
    original = '[project]\nname = "x"\nversion = "0"\ndependencies = ["simple_module_core>=0.1"]\n'
    pyproject.write_text(original, encoding="utf-8")

    pu.run_update(
        path=pyproject,
        dry_run=True,
        include_pre=False,
        fetcher=fake_pypi({"simple_module_core": "1.0.0"}),
    )

    assert pyproject.read_text(encoding="utf-8") == original


def test_skips_unknown_pypi_package(tmp_path: Path, fake_pypi) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "x"\nversion = "0"\ndependencies = ["simple_module_unknown>=0.1"]\n',
        encoding="utf-8",
    )

    pu.run_update(
        path=pyproject,
        dry_run=False,
        include_pre=False,
        fetcher=fake_pypi({}),
    )

    assert "simple_module_unknown>=0.1" in pyproject.read_text(encoding="utf-8")


def test_excludes_prereleases_by_default(tmp_path: Path) -> None:
    def fetcher(url: str) -> dict:
        return {
            "info": {"version": "2.0.0rc1"},
            "releases": {
                "1.5.0": [{"yanked": False}],
                "2.0.0rc1": [{"yanked": False}],
            },
        }

    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\nname = "x"\nversion = "0"\ndependencies = ["simple_module_core>=0.1"]\n',
        encoding="utf-8",
    )

    pu.run_update(path=pyproject, dry_run=False, include_pre=False, fetcher=fetcher)
    assert "simple_module_core>=1.5.0" in pyproject.read_text(encoding="utf-8")

    pu.run_update(path=pyproject, dry_run=False, include_pre=True, fetcher=fetcher)
    assert "simple_module_core>=2.0.0rc1" in pyproject.read_text(encoding="utf-8")


def test_missing_pyproject_exits_nonzero(tmp_path: Path, fake_pypi) -> None:
    # typer >= 0.26 vendors click as ``typer._click``; the raised ``Exit``
    # no longer inherits from ``click.exceptions.Exit``.  Catch both.
    _exit_types: tuple[type[BaseException], ...] = (click.exceptions.Exit,)
    try:
        from typer._click.exceptions import Exit as _TyExit

        _exit_types = (*_exit_types, _TyExit)
    except ImportError:
        pass
    with pytest.raises(_exit_types) as exc:
        pu.run_update(
            path=tmp_path,
            dry_run=False,
            include_pre=False,
            fetcher=fake_pypi({}),
        )
    assert getattr(exc.value, "exit_code", getattr(exc.value, "code", None)) == 1


def test_cli_command_registered() -> None:
    result = CliRunner().invoke(app, ["package-update", "--help"])
    assert result.exit_code == 0
    assert "package-update" in result.output or "Update all simple_module" in result.output
