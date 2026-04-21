"""SimpleModule CLI — `sm` console script.

Currently exposes:

* ``sm create-host <name>`` — scaffold a new host directory.
* ``sm create-module <name>`` — scaffold a new module package.
* ``sm gen-pages`` — regenerate the frontend pages manifest + Tailwind CSS.
* ``sm sync-js-deps`` — install JS deps declared by installed modules.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path

import click
from simple_module_core import discover_modules

from simple_module_hosting.scaffolding import (
    _to_kebab_case,
    collect_module_js_deps,
    create_module,
    repo_root_from_client_app,
    write_module_pages_manifest,
)
from simple_module_hosting.scaffolding import (
    create_host as _create_host,
)


@click.group()
def main() -> None:
    """SimpleModule developer CLI."""


@main.command("new")
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
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Skip interactive prompts; accept all defaults.",
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
    yes: bool,
    no_install: bool,
) -> None:
    """Scaffold a new SimpleModule app — pre-wired with users, dashboard, permissions."""
    target = dest or Path.cwd() / name
    if not yes:
        db = click.prompt(
            "Database backend",
            default=db,
            type=click.Choice(["sqlite", "postgres"]),
        )
        tenancy = click.confirm("Enable multi-tenancy?", default=tenancy)

    from simple_module_hosting.scaffolding import create_app_project

    try:
        create_app_project(target, name=name, db=db, tenancy=tenancy)
    except FileExistsError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)

    click.echo(f"Created app '{name}' at {target}")
    click.echo("\nPre-wired modules: users, dashboard, permissions")
    click.echo("\nNext steps:")
    click.echo(f"  cd {target}")
    if no_install:
        click.echo("  uv sync")
        click.echo("  npm install")
        click.echo("  alembic upgrade head")
        click.echo("  make dev")
        return

    click.echo("Installing dependencies...")
    for cmd in (["uv", "sync"], ["npm", "install"]):
        result = subprocess.run(cmd, cwd=target, check=False)
        if result.returncode != 0:
            click.echo(
                f"WARNING: {' '.join(cmd)} failed (exit {result.returncode}); "
                f"finish setup manually.",
                err=True,
            )
            return

    subprocess.run(["uv", "run", "alembic", "upgrade", "head"], cwd=target, check=False)
    click.echo("\nSetup complete. Run `make dev` in the new directory.")


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
    help="Destination directory. Defaults to ./simple_module_<package>.",
)
def create_module_cmd(name: str, dest: Path | None) -> None:
    """Scaffold a publishable SimpleModule module package."""
    slug = _to_kebab_case(name)
    package = slug.replace("-", "_")
    target = dest or Path.cwd() / f"simple_module_{package}"

    try:
        create_module(target, name=name)
    except FileExistsError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(1)

    click.echo(f"Created module 'simple_module_{package}' at {target}")
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
    """Regenerate client_app/modules.{manifest.json,generated.ts,generated.css}."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    output = host_dir or Path.cwd() / "client_app"
    if not output.is_dir():
        click.echo(f"ERROR: client_app directory not found at {output}", err=True)
        sys.exit(1)

    modules = discover_modules()
    written = write_module_pages_manifest(modules, output)
    click.echo(
        f"Wrote {written['manifest'].name}, {written['generated'].name}, "
        f"{written['css'].name} to {output}"
    )


@main.command("sync-js-deps")
@click.option(
    "--host-client-app",
    type=click.Path(file_okay=False, exists=True, path_type=Path),
    default=None,
    help="Path to host/client_app. Defaults to ./client_app.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print the npm install command without running it.",
)
def sync_js_deps(host_client_app: Path | None, dry_run: bool) -> None:
    """Install JS deps declared by installed modules into host's node_modules.

    Walks every discovered module, reads its package.json, and runs a single
    ``npm install --workspace host/client_app --save=false <specs>``. Use
    this after ``pip install``-ing a module wheel that declares JS deps;
    in-repo modules already flow through npm workspaces and need nothing.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    output = host_client_app or Path.cwd() / "client_app"
    if not output.is_dir():
        click.echo(f"ERROR: client_app directory not found at {output}", err=True)
        sys.exit(1)

    modules = discover_modules()
    by_module = collect_module_js_deps(modules)
    if not by_module:
        click.echo("No module JS dependencies declared.")
        return

    # Flatten into a single spec list. npm's own resolver handles conflicts.
    specs: list[str] = []
    for mod_name in sorted(by_module):
        for dep, rng in sorted(by_module[mod_name].items()):
            specs.append(f"{dep}@{rng}")
    # Dedupe while preserving first-seen order.
    deduped: list[str] = []
    seen: set[str] = set()
    for spec in specs:
        if spec not in seen:
            seen.add(spec)
            deduped.append(spec)

    npm = shutil.which("npm")
    if npm is None:
        click.echo("ERROR: npm not found on PATH.", err=True)
        sys.exit(1)

    # Workspace path is relative to the repo root — derive it from output.
    repo_root = repo_root_from_client_app(output)
    try:
        workspace = str(output.resolve().relative_to(repo_root))
    except ValueError:
        workspace = str(output.resolve())

    cmd = [
        npm,
        "install",
        "--workspace",
        workspace,
        "--save=false",
        "--no-audit",
        "--no-fund",
        *deduped,
    ]
    click.echo("Installing module JS deps:")
    for spec in deduped:
        click.echo(f"  {spec}")
    if dry_run:
        click.echo("(dry-run) " + " ".join(cmd))
        return
    result = subprocess.run(cmd, cwd=repo_root, check=False)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
