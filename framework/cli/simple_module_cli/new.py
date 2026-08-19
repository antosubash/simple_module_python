"""``smpy new`` Typer command — flag-driven or interactive scaffolder."""

from __future__ import annotations

import shutil
import subprocess
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from simple_module_cli.add_cmd import run_add
from simple_module_cli.app_project import create_app_project
from simple_module_cli.case import InvalidScaffoldNameError, to_kebab_case, validate_scaffold_name
from simple_module_cli.catalog import PRESETS, expand_deps
from simple_module_cli.wizard import run_wizard

__all__ = ["new_project"]

_ALEMBIC = ("uv", "run", "alembic")


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
            help=("Skip 'uv sync' / 'npm install' / initial alembic migration after scaffolding."),
        ),
    ] = False,
    flat: Annotated[
        bool,
        typer.Option(
            "--flat",
            help=(
                "Skip the modules/ directory and sample module. Use when the host "
                "will only consume published modules and never author its own."
            ),
        ),
    ] = False,
    git_module: Annotated[
        list[str] | None,
        typer.Option(
            "--git-module",
            help="git+URL[@ref][#subdirectory=dir] module source; repeatable.",
        ),
    ] = None,
) -> None:
    """Scaffold a new SimpleModule app, optionally with background jobs."""
    try:
        validate_scaffold_name(name)
    except InvalidScaffoldNameError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    pypi_name = to_kebab_case(name)
    if pypi_name != name:
        typer.echo(f"Normalizing PyPI name to {pypi_name!r}.")
    target = dest or Path.cwd() / name
    extra_list = [m.strip() for m in extra.split(",") if m.strip()]
    flag_driven = preset is not None or bool(extra_list)

    wizard_git: list[str] = []
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
            db_final, tenancy_final, resolved, wizard_git = run_wizard(
                default_db=db.value, default_tenancy=tenancy
            )
        except typer.Abort:
            typer.echo("Aborted.", err=True)
            raise typer.Exit(code=1) from None

    try:
        host_dir, preserved = create_app_project(
            target,
            name=name,
            db=db_final,
            tenancy=tenancy_final,
            selected=resolved,
            flat=flat,
        )
    except FileExistsError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    # Git-sourced modules land in the host pyproject before the install
    # phase below, so its single `uv sync` covers them too.
    for spec in [*(git_module or []), *wizard_git]:
        run_add(
            spec,
            pyproject=host_dir / "pyproject.toml",
            no_sync=True,
            assume_yes=yes,
        )

    typer.echo(f"Created app '{name}' at {target}")
    typer.echo(f"Modules: {', '.join(resolved)}")
    if preserved:
        typer.echo(
            "\nPreserved existing files (scaffold's versions were skipped — "
            "merge by hand if you want their contents):"
        )
        for path in preserved:
            rel = path.relative_to(target) if path.is_relative_to(target) else path
            typer.echo(f"  {rel}")
    typer.echo("\nNext steps:")
    typer.echo(f"  cd {target}")
    if no_install:
        typer.echo("  uv sync")
        typer.echo("  npm install")
        typer.echo('  make migration msg="initial schema"')
        typer.echo("  make migrate")
        typer.echo("  make dev")
        typer.echo("  make docker-up   # or run the full stack in containers")
        if "background_tasks" in resolved:
            typer.echo("  docker compose up -d redis worker beat   # background jobs")
        return

    typer.echo("Installing dependencies...")
    for cmd in (["uv", "sync"], ["npm", "install"]):
        if shutil.which(cmd[0]) is None:
            typer.echo(
                f"WARNING: '{cmd[0]}' not found on PATH; skipping `{' '.join(cmd)}`. "
                "Install it and finish setup manually.",
                err=True,
            )
            return
        result = subprocess.run(cmd, cwd=target, check=False)
        if result.returncode != 0:
            typer.echo(
                f"WARNING: {' '.join(cmd)} failed (exit {result.returncode}); "
                "finish setup manually.",
                err=True,
            )
            return

    _bootstrap_initial_migration(host_dir)
    # `heads` (plural) applies every per-module branch head; `head` (singular)
    # errors once a second module ships its own migration branch label.
    subprocess.run([*_ALEMBIC, "upgrade", "heads"], cwd=host_dir, check=False)
    typer.echo("\nSetup complete. Run `make dev` in the new directory.")
    typer.echo("To run the full stack in containers instead: make docker-up")
    if "background_tasks" in resolved:
        typer.echo("For background jobs, also run: docker compose up -d redis worker beat")


def _bootstrap_initial_migration(host_dir: Path) -> None:
    """Autogenerate the baseline migration if the scaffold ships none.

    Without a real revision, ``alembic upgrade head`` is a silent no-op
    against an empty schema — the bundled modules' tables never exist.
    """
    versions_dir = host_dir / "migrations" / "versions"
    if any(p.name != "__init__.py" for p in versions_dir.glob("*.py")):
        return
    subprocess.run(
        [*_ALEMBIC, "revision", "--autogenerate", "-m", "initial schema"],
        cwd=host_dir,
        check=False,
    )
