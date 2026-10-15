"""Postgres extensions a module needs (``ModuleBase.db_extensions``).

``ensure_db_extensions`` runs from the host ``env.py`` before the migrations
do, so a revision that creates an ``ltree`` column finds the extension already
installed. It is idempotent (``CREATE EXTENSION IF NOT EXISTS``), so it costs
nothing on an up-to-date database.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from typing import Any

from simple_module_core import ModuleBase
from sqlalchemy import text

from simple_module_db.types import LTree, TSVector

logger = logging.getLogger(__name__)

EXTENSION_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_-]*$")


class UnsupportedDatabaseError(RuntimeError):
    """A module needs a database feature the configured database lacks."""


def declared_extensions(modules: Iterable[ModuleBase]) -> dict[str, list[str]]:
    """``{extension: [module names that declare it]}``, validated, in module order."""
    wanted: dict[str, list[str]] = {}
    for mod in modules:
        for name in mod.db_extensions():
            if not EXTENSION_NAME_PATTERN.fullmatch(name):
                raise ValueError(
                    f"Module {mod.meta.name!r} declares invalid database extension "
                    f"{name!r} (must match {EXTENSION_NAME_PATTERN.pattern})"
                )
            owners = wanted.setdefault(name, [])
            if mod.meta.name not in owners:
                owners.append(mod.meta.name)
    return wanted


def ensure_db_extensions(connection: Any, modules: Iterable[ModuleBase]) -> list[str]:
    """Install every extension the modules declare; return the extension names.

    * Postgres: ``CREATE EXTENSION IF NOT EXISTS "<name>"``.
    * SQLite: raises :class:`UnsupportedDatabaseError` naming the module(s) and
      extension(s) — SQLite has none, and carrying on would fail later with a
      less helpful message.
    * ``connection=None`` is Alembic offline mode: the statements are emitted
      into the generated SQL script through ``context.execute``.
    """
    wanted = declared_extensions(modules)
    if not wanted:
        return []

    offline = connection is None
    if offline:
        from alembic import context

        dialect = context.get_context().dialect.name
    else:
        dialect = connection.dialect.name

    if dialect != "postgresql":
        detail = "; ".join(f"{', '.join(owners)} needs {name!r}" for name, owners in wanted.items())
        raise UnsupportedDatabaseError(
            f"Database extensions require PostgreSQL, but the database is {dialect}: {detail}. "
            "Point SM_DATABASE_URL at Postgres or uninstall the module."
        )

    for name in wanted:
        statement = f'CREATE EXTENSION IF NOT EXISTS "{name}"'
        if offline:
            context.execute(statement)
        else:
            logger.info("Ensuring Postgres extension %r", name)
            connection.execute(text(statement))
    return list(wanted)


def render_extension_type(obj: Any, imports: set[str] | None) -> str | None:
    """Alembic render for ``LTree`` / ``TSVector``, or ``None`` for other types.

    Rendered through our own classes (not ``postgresql.TSVECTOR``) so the same
    revision also upgrades on SQLite, where they are ``TEXT``.
    """
    if isinstance(obj, (LTree, TSVector)):
        if imports is not None:
            imports.add("import simple_module_db.types")
        return f"simple_module_db.types.{type(obj).__name__}()"
    return None


__all__ = [
    "UnsupportedDatabaseError",
    "declared_extensions",
    "ensure_db_extensions",
    "render_extension_type",
]
