"""Post-install steps and shared helpers for ``smpy add``."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from pathlib import Path

import typer

from simple_module_cli.package_update_deps import workspace_member_dirs
from simple_module_cli.package_update_npm import install_roots, load_manifests
from simple_module_cli.pyproject_edit import load_pyproject
from simple_module_cli.uv_workspace import find_workspace_root, is_workspace_member

ExecRunner = Callable[[list[str], Path], int]

_DIST_PREFIX = re.compile(r"^simple[-_]module[-_]", re.IGNORECASE)
_SKIP_IF_MISSING = "--skip-if-missing"
#: Click's exit code for an unknown option.
_USAGE_ERROR = 2


_ENTRYPOINT_CHECK = (
    "import sys\n"
    "from importlib.metadata import distributions\n"
    "target = sys.argv[1].replace('-', '_').lower()\n"
    "for dist in distributions():\n"
    "    if any(ep.group == 'simple_module' for ep in dist.entry_points):\n"
    "        name = (dist.metadata['Name'] or '').replace('-', '_').lower()\n"
    "        if name == target:\n"
    "            sys.exit(0)\n"
    "sys.exit(1)\n"
)


def _default_exec_runner(cmd: list[str], cwd: Path) -> int:
    return subprocess.run(cmd, cwd=cwd, check=False).returncode


def _sync_command(project_dir: Path) -> tuple[list[str], Path]:
    """How to sync after editing ``project_dir``'s pyproject.

    A host inside an app workspace shares one venv with the root's dev tools
    and every module member. ``uv sync`` from ``host/`` would sync the host
    alone and uninstall the rest (GH #916), so sync the workspace from its
    root, as ``make install`` does.
    """
    root = find_workspace_root(project_dir)
    if root is not None and (
        root == project_dir.resolve() or is_workspace_member(project_dir, project_dir)
    ):
        return ["uv", "sync", "--all-packages"], root
    return ["uv", "sync"], project_dir


def sync_project(
    project_dir: Path, exec_runner: ExecRunner, *, upgrade: list[str] | None = None
) -> None:
    """Finish manifest changes using the app's installation and generation flow."""
    sync_cmd, root = _sync_command(project_dir)
    for name in upgrade or []:
        sync_cmd.extend(["--upgrade-package", name])
    commands = [(sync_cmd, root)]
    client = next((p for p in (root / "host/client_app", root / "client_app") if p.is_dir()), None)
    if client is not None:
        pyproject = root / "pyproject.toml"
        files = [pyproject, *workspace_member_dirs(pyproject, load_pyproject(pyproject))]
        manifests = load_manifests([file.parent for file in files])
        commands.extend((["npm", "install"], directory) for directory in install_roots(manifests))
        commands.append((["uv", "run", "smpy", "gen"], root))
    for cmd, cwd in commands:
        if exec_runner(cmd, cwd) != 0:
            raise _fail(
                f"`{' '.join(cmd)}` failed — manifests are already updated. "
                f"Fix the error, then run `make install` from {root} to finish installation."
            )


def _fail(message: str) -> typer.Exit:
    typer.echo(f"ERROR: {message}", err=True)
    return typer.Exit(code=1)


def post_install(
    project_dir: Path,
    dists: list[str],
    models_dists: list[str],
    exec_runner: ExecRunner,
) -> None:
    """Sync dependencies, regenerate frontend files, and check entry points."""
    sync_cmd, sync_dir = _sync_command(project_dir)
    has_frontend = (project_dir / "client_app").is_dir()
    commands = [(sync_cmd, sync_dir)]
    if has_frontend:
        commands.extend(
            (["uv", "run", "smpy", "host", *step], project_dir)
            for step in (("gen-pages",), ("sync-js-deps",), ("gen-i18n", _SKIP_IF_MISSING))
        )
    for cmd, cwd in commands:
        code = exec_runner(cmd, cwd)
        if code == _USAGE_ERROR and _SKIP_IF_MISSING in cmd:
            # A hosting plugin older than the global smpy has no --skip-if-missing.
            code = exec_runner([part for part in cmd if part != _SKIP_IF_MISSING], cwd)
        if code != 0:
            raise _fail(
                f"`{' '.join(cmd)}` failed — dependencies are already recorded in pyproject.toml. "
                "Fix the error, then rerun the original `smpy add` command."
            )
    for dist in dists:
        code = exec_runner(["uv", "run", "python", "-c", _ENTRYPOINT_CHECK, dist], project_dir)
        if code != 0:
            raise _fail(
                f"{dist} installed but exposes no [project.entry-points.simple_module] "
                "entry point — it is not a SimpleModule module."
            )
    for dist in models_dists:
        # The same message `smpy create-module`'s next steps suggest (GH #931).
        slug = _DIST_PREFIX.sub("", dist)
        typer.echo(
            f"{dist} ships database models — generate and apply the migration:\n"
            f'  make migration msg="add {slug}"\n  make migrate'
        )
    # Only `pyproject.toml` changed, which the dev reloader does not watch; and a
    # reload still logs the new module as not importable in that process (GH #915,
    # #931), so only a restart serves it.
    if has_frontend:
        typer.echo("Run `make install` from the app root to link pages and generate i18n keys.")
    typer.echo("If `make dev` is running, restart it to discover the installed modules.")
