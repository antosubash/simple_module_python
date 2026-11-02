"""Post-install steps and shared helpers for ``smpy add``."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import typer

ExecRunner = Callable[[list[str], Path], int]


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


def _fail(message: str) -> typer.Exit:
    typer.echo(f"ERROR: {message}", err=True)
    return typer.Exit(code=1)


def post_install(
    project_dir: Path,
    dists: list[str],
    models_dists: list[str],
    exec_runner: ExecRunner,
) -> None:
    """uv sync → gen-pages → sync-js-deps → entry-point check → reminders."""
    if exec_runner(["uv", "sync"], project_dir) != 0:
        raise _fail("`uv sync` failed — pyproject was written; fix and re-run `uv sync`.")
    if (project_dir / "client_app").is_dir():
        exec_runner(["uv", "run", "smpy", "host", "gen-pages"], project_dir)
        exec_runner(["uv", "run", "smpy", "host", "sync-js-deps"], project_dir)
    for dist in dists:
        code = exec_runner(["uv", "run", "python", "-c", _ENTRYPOINT_CHECK, dist], project_dir)
        if code != 0:
            raise _fail(
                f"{dist} installed but exposes no [project.entry-points.simple_module] "
                "entry point — it is not a SimpleModule module."
            )
    for dist in models_dists:
        typer.echo(
            f"{dist} ships database models — generate and apply the migration:\n"
            f'  make migration msg="add {dist}"\n  make migrate'
        )
