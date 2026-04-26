"""``sm new`` Typer command — flag-driven or interactive scaffolder."""

from __future__ import annotations

import subprocess
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from simple_module.app_project import create_app_project
from simple_module.catalog import PRESETS, expand_deps
from simple_module.wizard import run_wizard

__all__ = ["new_project"]


class Db(StrEnum):
    sqlite = "sqlite"
    postgres = "postgres"


class Preset(StrEnum):
    minimal = "minimal"
    standard = "standard"
    full = "full"


def new_project(
    name: Annotated[str, typer.Argument(help="App name (used for directory + package).")],
    dest: Annotated[
        Path | None,
        typer.Option("--dest", help="Destination directory. Defaults to ./<name>."),
    ] = None,
    db: Annotated[
        Db,
        typer.Option("--db", help="Database backend to configure in .env.example."),
    ] = Db.sqlite,
    tenancy: Annotated[
        bool,
        typer.Option("--tenancy/--no-tenancy", help="Enable the multi-tenant middleware."),
    ] = False,
    preset: Annotated[
        Preset | None,
        typer.Option("--preset", help="Module preset. Combine with --with."),
    ] = None,
    extra: Annotated[
        str,
        typer.Option(
            "--with",
            help="Comma-separated extra modules (e.g. background_tasks,file_storage).",
        ),
    ] = "",
    yes: Annotated[
        bool,
        typer.Option("--yes", "-y", help="Skip interactive prompts; accept defaults."),
    ] = False,
    no_install: Annotated[
        bool,
        typer.Option(
            "--no-install",
            help="Skip 'uv sync' / 'npm install' / 'alembic upgrade head' after scaffolding.",
        ),
    ] = False,
) -> None:
    """Scaffold a new SimpleModule app, optionally with background jobs."""
    target = dest or Path.cwd() / name
    extra_list = [m.strip() for m in extra.split(",") if m.strip()]
    flag_driven = preset is not None or bool(extra_list)

    if yes or flag_driven:
        chosen = list(PRESETS[(preset or Preset.standard).value]) + extra_list
        try:
            resolved, added = expand_deps(chosen)
        except KeyError as exc:
            typer.echo(f"ERROR: {exc}", err=True)
            raise typer.Exit(code=1) from exc
        for added_name, required_by in added:
            typer.echo(f"Added {added_name} (required by {required_by})")
        db_final, tenancy_final = db.value, tenancy
    else:
        try:
            db_final, tenancy_final, resolved = run_wizard(
                default_db=db.value, default_tenancy=tenancy
            )
        except typer.Abort:
            typer.echo("Aborted.", err=True)
            raise typer.Exit(code=1) from None

    try:
        create_app_project(target, name=name, db=db_final, tenancy=tenancy_final, selected=resolved)
    except FileExistsError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Created app '{name}' at {target}")
    typer.echo(f"Modules: {', '.join(resolved)}")
    typer.echo("\nNext steps:")
    typer.echo(f"  cd {target}")
    if no_install:
        typer.echo("  uv sync")
        typer.echo("  npm install")
        typer.echo("  alembic upgrade head")
        typer.echo("  make dev")
        if "background_tasks" in resolved:
            typer.echo("  docker compose up -d redis worker beat   # background jobs")
        return

    typer.echo("Installing dependencies...")
    for cmd in (["uv", "sync"], ["npm", "install"]):
        result = subprocess.run(cmd, cwd=target, check=False)
        if result.returncode != 0:
            typer.echo(
                f"WARNING: {' '.join(cmd)} failed (exit {result.returncode}); "
                "finish setup manually.",
                err=True,
            )
            return

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], cwd=target, check=False)
    typer.echo("\nSetup complete. Run `make dev` in the new directory.")
    if "background_tasks" in resolved:
        typer.echo("For background jobs, also run: docker compose up -d redis worker beat")
