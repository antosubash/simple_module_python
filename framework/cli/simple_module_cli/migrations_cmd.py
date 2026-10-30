"""Prepare frozen framework upgrades in a consuming host's own Alembic graph."""

from __future__ import annotations

import os
from importlib.resources import files
from pathlib import Path
from typing import Annotated
from uuid import uuid4

import typer

migrations_app = typer.Typer(help="Prepare host-owned framework upgrade revisions.")
_RECIPES = {
    "mail.settings_namespace_v1": ("mail", "mail_settings.py"),
    "users.hashed_bearer_tokens_v1": ("users", "users_tokens.py"),
}


@migrations_app.command("prepare")
def prepare(
    upgrade_id: Annotated[str, typer.Argument(help="Stable framework upgrade id.")],
    head: Annotated[str, typer.Option("--head", help="Explicit host head or label@head.")],
    config: Annotated[Path | None, typer.Option("--config", help="Host alembic.ini.")] = None,
) -> None:
    """Write a self-contained revision; never connect to or migrate the database."""
    if upgrade_id not in _RECIPES:
        raise typer.BadParameter(f"Unknown upgrade {upgrade_id!r}; choose {', '.join(_RECIPES)}")
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from alembic.util.exc import CommandError
    except ImportError as exc:
        raise typer.BadParameter(
            "Run this command in the host environment with Alembic installed"
        ) from exc

    root = Path(os.environ.get("SM_PROJECT_ROOT", Path.cwd()))
    if config is None:
        config = root / "alembic.ini"
        if not config.is_file():
            config = root / "host/alembic.ini"
    if not config.is_file():
        raise typer.BadParameter(f"Host Alembic config not found: {config}")
    try:
        script = ScriptDirectory.from_config(Config(str(config)))
        parent = script.get_revision(head)
        if parent is None or not parent.is_head:
            raise typer.BadParameter("--head must resolve to one existing host head")
        label, recipe = _RECIPES[upgrade_id]
        labels = {label for rev in script.walk_revisions() for label in rev.branch_labels}
    except CommandError as exc:
        raise typer.BadParameter(str(exc)) from exc

    # Frozen source is copied, so future package changes cannot change this revision.
    source = files("simple_module_cli").joinpath("migration_recipes", recipe).read_text()
    revision = uuid4().hex[:12]
    branch_labels = None if label in labels else (label,)
    identifiers = (
        f"\nrevision = {revision!r}\ndown_revision = {parent.revision!r}\n"
        f"branch_labels = {branch_labels!r}\ndepends_on = None\n"
    )
    path = Path(script.versions) / f"{revision}_{upgrade_id.replace('.', '_')}.py"
    with path.open("x") as output:
        output.write(source + identifiers)
    typer.echo(f"Prepared {upgrade_id}: {path}. Review it, then run alembic upgrade heads.")
