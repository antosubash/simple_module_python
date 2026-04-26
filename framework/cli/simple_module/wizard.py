"""Interactive prompt sequence for ``sm new``.

Returns the user's choices as ``(db, tenancy, selected)`` where
``selected`` is the topologically resolved module list (already includes
transitive requires). All prompts use ``click`` — no extra TUI dep.
"""

from __future__ import annotations

import click

from .catalog import CATALOG, PRESETS, expand_deps

__all__ = ["run_wizard"]


_PRESET_CHOICES = ("minimal", "standard", "full", "custom")


def run_wizard(*, default_db: str, default_tenancy: bool) -> tuple[str, bool, list[str]]:
    db = click.prompt(
        "Database backend",
        default=default_db,
        type=click.Choice(["sqlite", "postgres"]),
    )
    tenancy = click.confirm("Enable multi-tenancy?", default=default_tenancy)

    click.echo("\nPreset:")
    click.echo("  [1] minimal  — users only")
    click.echo("  [2] standard — users, dashboard, permissions  (default)")
    click.echo("  [3] full     — every module")
    click.echo("  [4] custom   — pick modules one by one")
    choice = click.prompt(
        "Choose",
        default="2",
        type=click.Choice(["1", "2", "3", "4"]),
        show_choices=False,
    )
    preset_name = _PRESET_CHOICES[int(choice) - 1]

    if preset_name == "custom":
        picked = [
            name
            for name in CATALOG
            if click.confirm(f"Include {CATALOG[name].display}?", default=False)
        ]
    else:
        picked = list(PRESETS[preset_name])

    resolved, added = expand_deps(picked)
    for name, required_by in added:
        click.echo(f"Added {name} (required by {required_by})")
    click.echo(f"Selected modules: {', '.join(resolved)}")

    if not click.confirm("Proceed?", default=True):
        raise click.Abort()
    return db, tenancy, resolved
