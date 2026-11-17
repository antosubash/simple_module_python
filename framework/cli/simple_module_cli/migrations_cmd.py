"""Prepare frozen framework upgrades in a consuming host's own Alembic graph."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import typer

from simple_module_cli._migration_support import (
    NO_ALEMBIC_CONFIG,
    data_upgrade_entry_points,
    resolve_alembic_ini,
)

migrations_app = typer.Typer(help="Prepare host-owned framework upgrade revisions.")


@migrations_app.command("prepare")
def prepare(
    upgrade_id: Annotated[str, typer.Argument(help="Stable framework upgrade id.")],
    head: Annotated[str, typer.Option("--head", help="Explicit host head or label@head.")],
    config: Annotated[Path | None, typer.Option("--config", help="Host alembic.ini.")] = None,
) -> None:
    """Write a self-contained revision; never connect to or migrate the database."""
    entries = data_upgrade_entry_points()
    recipes = entries.select(name=upgrade_id)
    if not recipes:
        available = ", ".join(sorted(entries.names)) or "none"
        raise typer.BadParameter(f"Unknown upgrade {upgrade_id!r}. Available upgrades: {available}")
    if len(recipes) > 1:
        raise typer.BadParameter(f"Multiple installed recipes for upgrade {upgrade_id!r}")
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from alembic.util.exc import CommandError
    except ImportError as exc:
        raise typer.BadParameter(
            "Run this command in the host environment with Alembic installed"
        ) from exc

    ini = resolve_alembic_ini(override=config)
    if ini is None:
        raise typer.BadParameter(
            f"Alembic config not found: {config}" if config else NO_ALEMBIC_CONFIG
        )
    try:
        script = ScriptDirectory.from_config(Config(str(ini)))
        parent = script.get_revision(head)
        if parent is None or not parent.is_head:
            raise typer.BadParameter("--head must resolve to one existing host head")
        existing = {name for rev in script.walk_revisions() for name in rev.branch_labels}
    except CommandError as exc:
        raise typer.BadParameter(str(exc)) from exc

    # Frozen source is copied, so future package changes cannot change this revision.
    try:
        label, source = next(iter(recipes)).load()()
        if not label or not isinstance(label, str) or not isinstance(source, str):
            raise ValueError("expected a (branch label, Python source) pair")
    except Exception as exc:
        raise typer.BadParameter(f"Could not load recipe for {upgrade_id!r}: {exc}") from exc
    revision = uuid4().hex[:12]
    branch_labels = None if label in existing else (label,)
    identifiers = (
        f"\nrevision = {revision!r}\ndown_revision = {parent.revision!r}\n"
        f"branch_labels = {branch_labels!r}\ndepends_on = None\n"
    )
    slug = re.sub(r"[^\w-]", "_", upgrade_id)
    path = Path(parent.path).with_name(f"{revision}_{slug}.py")
    with path.open("x", encoding="utf-8") as output:
        output.write(source + identifiers)
    typer.echo(f"Prepared {upgrade_id}: {path}. Review it, then run alembic upgrade heads.")
