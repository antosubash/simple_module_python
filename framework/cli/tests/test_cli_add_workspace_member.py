"""`smpy add` of a local module inside the host's uv workspace (GH #442)."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
import typer
from simple_module_cli.add_cmd import run_add
from simple_module_cli.uv_workspace import is_workspace_member

HOST = '[project]\nname = "myhost"\nversion = "0.1.0"\ndependencies = []\n'
WORKSPACE = '[tool.uv.workspace]\nmembers = ["host", "modules/*"]\nexclude = ["modules/skipped"]\n'
DIST = "simple_module_forest_plots"
DEP = "simple-module-forest-plots"


def _noop(cmd: list[str], cwd: Path) -> int:
    return 0


def _write_module(root: Path) -> None:
    (root / DIST).mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "{DIST.replace("_", "-")}"\nversion = "0.1.0"\n'
        f'[project.entry-points.simple_module]\n{DIST} = "{DIST}.module:M"\n',
        encoding="utf-8",
    )


def _host_data(workspace: Path) -> dict:
    return tomllib.loads((workspace / "host" / "pyproject.toml").read_text(encoding="utf-8"))


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text(WORKSPACE, encoding="utf-8")
    (tmp_path / "host").mkdir()
    (tmp_path / "host" / "pyproject.toml").write_text(HOST, encoding="utf-8")
    return tmp_path


def test_workspace_member_gets_workspace_source_and_unpinned_dep(workspace: Path) -> None:
    _write_module(workspace / "modules" / "forest_plots")
    run_add(
        "../modules/forest_plots",
        pyproject=workspace / "host" / "pyproject.toml",
        no_sync=True,
        exec_runner=_noop,
    )
    data = _host_data(workspace)
    assert data["project"]["dependencies"] == [DEP]
    assert data["tool"]["uv"]["sources"][DEP] == {"workspace": True}


def test_excluded_workspace_dir_keeps_path_source(workspace: Path) -> None:
    _write_module(workspace / "modules" / "skipped")
    run_add(
        "../modules/skipped",
        pyproject=workspace / "host" / "pyproject.toml",
        no_sync=True,
        exec_runner=_noop,
    )
    data = _host_data(workspace)
    assert data["tool"]["uv"]["sources"][DEP] == {"path": "../modules/skipped", "editable": True}
    assert data["project"]["dependencies"] == [f"{DEP}>=0.1.0,<1.0"]


def test_no_enclosing_workspace_is_not_a_member(tmp_path: Path) -> None:
    (tmp_path / "host").mkdir()
    (tmp_path / "mod").mkdir()
    assert not is_workspace_member(tmp_path / "host", tmp_path / "mod")


def test_cwd_relative_path_falls_back_and_is_rewritten(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_module(workspace / "modules" / "forest_plots")
    monkeypatch.chdir(workspace)
    run_add(
        "./modules/forest_plots",
        pyproject=workspace / "host" / "pyproject.toml",
        no_sync=True,
        exec_runner=_noop,
    )
    assert _host_data(workspace)["tool"]["uv"]["sources"][DEP] == {"workspace": True}


def test_missing_path_error_names_the_resolution_base(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(typer.Exit):
        run_add(
            "./nope",
            pyproject=workspace / "host" / "pyproject.toml",
            no_sync=True,
            exec_runner=_noop,
        )
    assert "--path project" in capsys.readouterr().err
