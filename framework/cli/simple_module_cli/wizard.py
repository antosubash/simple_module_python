"""Interactive prompt sequence for ``smpy new``."""

from __future__ import annotations

import typer

from simple_module_cli.catalog import CATALOG, PRESETS, expand_deps

__all__ = ["run_wizard"]

_PRESET_CHOICES = ("minimal", "standard", "full", "custom")


def run_wizard(*, default_db: str, default_tenancy: bool) -> tuple[str, bool, list[str], list[str]]:
    db = typer.prompt("Database backend", default=default_db, type=str)
    if db not in ("sqlite", "postgres"):
        typer.echo(f"Invalid database: {db!r}; expected sqlite or postgres", err=True)
        raise typer.Abort()
    tenancy = typer.confirm("Enable multi-tenancy?", default=default_tenancy)

    typer.echo("\nPreset:")
    typer.echo("  [1] minimal  — users only")
    typer.echo("  [2] standard — users, dashboard, permissions  (default)")
    typer.echo("  [3] full     — every module")
    typer.echo("  [4] custom   — pick modules one by one")
    choice = typer.prompt("Choose", default="2", type=str)
    if choice not in {"1", "2", "3", "4"}:
        typer.echo(f"Invalid choice: {choice!r}", err=True)
        raise typer.Abort()
    preset_name = _PRESET_CHOICES[int(choice) - 1]

    if preset_name == "custom":
        picked = [
            name
            for name in CATALOG
            if typer.confirm(f"Include {CATALOG[name].display}?", default=False)
        ]
    else:
        picked = list(PRESETS[preset_name])

    resolved, added = expand_deps(picked)
    for name, required_by in added:
        typer.echo(f"Added {name} (required by {required_by})")
    typer.echo(f"Selected modules: {', '.join(resolved)}")

    git_specs: list[str] = []
    if typer.confirm("Add modules from a git URL?", default=False):
        while True:
            url = typer.prompt("git+URL (blank to finish)", default="", show_default=False).strip()
            if not url:
                break
            if not url.startswith("git+"):
                typer.echo("Spec must start with git+ (e.g. git+https://github.com/x/repo)")
                continue
            git_specs.append(url)

    if not typer.confirm("Proceed?", default=True):
        raise typer.Abort()
    return db, tenancy, resolved, git_specs
