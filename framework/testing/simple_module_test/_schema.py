"""Schema construction for the plugin's app fixtures.

Split out of :mod:`simple_module_test.fixtures` so that module declares
fixtures and this one holds the machinery underneath them: importing every
installed module's models, resolving the migration heads, creating the tables
and stamping ``alembic_version`` so the boot-time migration check passes.
"""

from __future__ import annotations

import contextlib
import importlib
from functools import lru_cache

from simple_module_core.discovery import discover_modules
from simple_module_db.base import all_module_bases


@lru_cache(maxsize=1)
def _ensure_models_imported() -> list:
    """Import all module models so all_module_bases is populated (cached)."""
    for mod in discover_modules():
        pkg = type(mod).__module__.split(".")[0]
        with contextlib.suppress(ModuleNotFoundError):
            importlib.import_module(f"{pkg}.models")
    return list(all_module_bases)


@lru_cache(maxsize=1)
def _alembic_heads() -> tuple[str, ...]:
    """Cached head revisions — cannot change within a pytest run.

    Plural: each module's first migration sets its own ``branch_labels``, so
    the history has one head per module and a real upgraded database carries
    an ``alembic_version`` row for each. Stamping only one leaves the rest
    looking un-applied, which now reads as a behind-head schema and puts every
    test app behind the setup gate.
    """
    from simple_module_hosting.migrations import resolve_head_revisions

    return resolve_head_revisions()


async def _create_all_tables(engine) -> None:
    """Create all module tables in a single connection.

    Also stamps the alembic_version table at heads so the app's startup
    migration check (``check_migrations``) treats the test DB as current.
    Without the stamp the check would raise because ``create_all`` doesn't
    touch alembic_version.
    """
    from sqlalchemy import text

    bases = _ensure_models_imported()
    heads = _alembic_heads()

    async with engine.begin() as conn:

        def _sync_create_all(sync_conn):
            for base in bases:
                base.metadata.create_all(sync_conn)

        await conn.run_sync(_sync_create_all)

        if heads:
            await conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS alembic_version "
                    "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
                )
            )
            await conn.execute(text("DELETE FROM alembic_version"))
            for head in heads:
                await conn.execute(
                    text("INSERT INTO alembic_version (version_num) VALUES (:v)"),
                    {"v": head},
                )
