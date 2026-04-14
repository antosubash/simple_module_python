"""SimpleModule CLI — `sm` console script.

Currently exposes:

* ``sm create-host <name>`` — scaffold a new host directory.
* ``sm gen-pages`` — regenerate the frontend pages manifest.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click


@click.group()
def main() -> None:
    """SimpleModule developer CLI."""


@main.command("create-host")
@click.argument("name")
@click.option(
    "--dest",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Destination directory. Defaults to ./<name>.",
)
@click.option(
    "--with",
    "modules",
    default="",
    help="Comma-separated module names to declare as deps (e.g. --with=Auth,Products).",
)
def create_host(name: str, dest: Path | None, modules: str) -> None:
    """Scaffold a new SimpleModule host project at ./<NAME>."""
    from simple_module_hosting.scaffolding import create_host as _create_host

    target = dest or Path.cwd() / name
    selected = [m.strip() for m in modules.split(",") if m.strip()]

    try:
        _create_host(target, name=name, modules=selected)
    except FileExistsError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)

    click.echo(f"Created host '{name}' at {target}")
    if selected:
        click.echo(f"Declared modules: {', '.join(selected)}")
    click.echo("\nNext steps:")
    click.echo(f"  cd {target}")
    click.echo("  uv sync")
    click.echo("  cp .env.example .env")
    click.echo('  alembic revision --autogenerate -m "initial schema"')
    click.echo("  alembic upgrade head")
    click.echo("  python main.py")


@main.command("create-module")
@click.argument("name")
@click.option(
    "--dest",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Destination directory. Defaults to ./simple-module-<slug>.",
)
def create_module_cmd(name: str, dest: Path | None) -> None:
    """Scaffold a publishable SimpleModule module package."""
    from simple_module_hosting.scaffolding import _to_kebab_case, create_module

    slug = _to_kebab_case(name)
    target = dest or Path.cwd() / f"simple-module-{slug}"

    try:
        create_module(target, name=name)
    except FileExistsError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)

    click.echo(f"Created module 'simple-module-{slug}' at {target}")
    click.echo("\nNext steps:")
    click.echo(f"  cd {target}")
    click.echo("  uv sync --extra dev")
    click.echo("  uv run pytest")


@main.command("gen-pages")
@click.option(
    "--host-dir",
    type=click.Path(file_okay=False, exists=True, path_type=Path),
    default=None,
    help="Path to the host's client_app directory. Defaults to ./client_app.",
)
def gen_pages(host_dir: Path | None) -> None:
    """Regenerate client_app/modules.{manifest.json,generated.ts}."""
    from simple_module_core import discover_modules

    from simple_module_hosting.scaffolding import write_module_pages_manifest

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    output = host_dir or Path.cwd() / "client_app"
    if not output.is_dir():
        click.echo(f"ERROR: client_app directory not found at {output}", err=True)
        sys.exit(1)

    modules = discover_modules()
    written = write_module_pages_manifest(modules, output)
    click.echo(f"Wrote {written['manifest'].name} and {written['generated'].name} to {output}")


if __name__ == "__main__":
    main()
