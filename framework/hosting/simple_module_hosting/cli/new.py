"""The upgraded ``sm new`` command.

Combines flag-driven non-interactive use (``--preset`` / ``--with``) with
the interactive wizard. All paths converge on
:func:`simple_module_hosting.scaffolding.create_app_project` with a
resolved module list.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import click

from simple_module_hosting.scaffolding import create_app_project

from .catalog import PRESETS, expand_deps
from .wizard import run_wizard

__all__ = ["new_project"]


@click.command("new")
@click.argument("name")
@click.option(
    "--dest",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Destination directory. Defaults to ./<name>.",
)
@click.option(
    "--db",
    type=click.Choice(["sqlite", "postgres"]),
    default="sqlite",
    show_default=True,
    help="Database backend to configure in .env.example.",
)
@click.option(
    "--tenancy/--no-tenancy",
    default=False,
    show_default=True,
    help="Enable the multi-tenant middleware by default.",
)
@click.option(
    "--preset",
    type=click.Choice(["minimal", "standard", "full"]),
    default=None,
    help="Module preset. Combine with --with to add modules on top.",
)
@click.option(
    "--with",
    "extra",
    default="",
    help="Comma-separated extra module names (e.g. background_tasks,file_storage).",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Skip interactive prompts; accept defaults.",
)
@click.option(
    "--no-install",
    is_flag=True,
    default=False,
    help="Skip 'uv sync' / 'npm install' / 'alembic upgrade head' after scaffolding.",
)
def new_project(
    name: str,
    dest: Path | None,
    db: str,
    tenancy: bool,
    preset: str | None,
    extra: str,
    yes: bool,
    no_install: bool,
) -> None:
    """Scaffold a new SimpleModule app, optionally with background jobs."""
    target = dest or Path.cwd() / name

    extra_list = [m.strip() for m in extra.split(",") if m.strip()]
    flag_driven = preset is not None or bool(extra_list)

    if yes or flag_driven:
        chosen = list(PRESETS[preset or "standard"]) + extra_list
        try:
            resolved, added = expand_deps(chosen)
        except KeyError as exc:
            click.echo(f"ERROR: {exc}", err=True)
            sys.exit(1)
        for added_name, required_by in added:
            click.echo(f"Added {added_name} (required by {required_by})")
    else:
        try:
            db, tenancy, resolved = run_wizard(default_db=db, default_tenancy=tenancy)
        except click.Abort:
            click.echo("Aborted.", err=True)
            sys.exit(1)

    try:
        create_app_project(target, name=name, db=db, tenancy=tenancy, selected=resolved)
    except FileExistsError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)

    click.echo(f"Created app '{name}' at {target}")
    click.echo(f"Modules: {', '.join(resolved)}")
    click.echo("\nNext steps:")
    click.echo(f"  cd {target}")
    if no_install:
        click.echo("  uv sync")
        click.echo("  npm install")
        click.echo("  alembic upgrade head")
        click.echo("  make dev")
        if "background_tasks" in resolved:
            click.echo("  docker compose up -d redis worker beat   # background jobs")
        return

    click.echo("Installing dependencies...")
    for cmd in (["uv", "sync"], ["npm", "install"]):
        result = subprocess.run(cmd, cwd=target, check=False)
        if result.returncode != 0:
            click.echo(
                f"WARNING: {' '.join(cmd)} failed (exit {result.returncode}); "
                "finish setup manually.",
                err=True,
            )
            return

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], cwd=target, check=False)
    click.echo("\nSetup complete. Run `make dev` in the new directory.")
    if "background_tasks" in resolved:
        click.echo("For background jobs, also run: docker compose up -d redis worker beat")
