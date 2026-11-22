"""One source-aware manifest update followed by the app's installation flow."""

from pathlib import Path
from typing import Annotated

import typer

from simple_module_cli.sources._add_install import (
    ExecRunner,
    _default_exec_runner,
    _fail,
    sync_project,
)
from simple_module_cli.sources.pypi import Fetcher
from simple_module_cli.sources.uv_workspace import find_workspace_root, is_workspace_member
from simple_module_cli.updates.package_update import run_update as update_manifests


def run_update(
    path: Path,
    *,
    only: str | None = None,
    dry_run: bool = False,
    include_pre: bool = False,
    loosen: bool = False,
    fetcher: Fetcher | None = None,
    git_runner=None,
    exec_runner: ExecRunner | None = None,
) -> None:
    project = (path.parent if path.name == "pyproject.toml" else path).resolve()
    if not (project / "pyproject.toml").is_file():
        raise _fail(f"{project / 'pyproject.toml'} not found")
    root = find_workspace_root(project)
    if root is not None and (root == project or is_workspace_member(project, project)):
        project = root
    relock = update_manifests(
        project,
        only=only,
        dry_run=dry_run,
        include_pre=include_pre,
        loosen=loosen,
        fetcher=fetcher,
        git_runner=git_runner,
    )
    if not dry_run:
        sync_project(project, exec_runner or _default_exec_runner, upgrade=relock)


def update_modules(
    name: Annotated[
        str | None,
        typer.Argument(help="Dependency dist name. Omit to update all framework/module pins."),
    ] = None,
    path: Annotated[
        Path,
        typer.Option("--path", help="Project root or pyproject.toml. Defaults to cwd."),
    ] = Path(),
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Preview without writing or installing.")
    ] = False,
    include_pre: Annotated[
        bool, typer.Option("--include-pre", help="Include PyPI pre-releases.")
    ] = False,
    loosen: Annotated[
        bool, typer.Option("--loosen", help="Rewrite PyPI constraints to >=<latest>.")
    ] = False,
) -> None:
    """Update PyPI and git pins, sync lockfiles, and generate the frontend."""
    run_update(path, only=name, dry_run=dry_run, include_pre=include_pre, loosen=loosen)
