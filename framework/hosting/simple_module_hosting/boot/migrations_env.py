"""Public Alembic environment runner shared by generated and in-tree hosts."""

from __future__ import annotations

import logging
from logging.config import fileConfig
from pathlib import Path

from simple_module_core.modules.discovery import discover_modules
from simple_module_db import (
    build_module_metadata,
    detect_provider,
    ensure_db_extensions,
    make_include_object,
    make_process_revision_directives,
    render_item,
)
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url

from simple_module_hosting.boot.migrations import ALEMBIC_DATABASE_URL_ATTRIBUTE

logger = logging.getLogger("alembic.env")


def run_migrations(context) -> None:
    """Run an Alembic environment with metadata from every installed module.

    Pass ``alembic.context`` from env.py. The setup wizard's locked URL wins
    over Settings; CLI settings resolve dotenv and anchor relative SQLite URLs.
    Both modes install the shared include/render/revision hooks. Online runs
    commit module extensions before revisions and dispose their sync engine.
    """
    from simple_module_hosting.config.settings import Settings

    config = context.config
    if config.config_file_name is not None:
        # The setup wizard runs in-process; keep existing app loggers enabled.
        fileConfig(config.config_file_name, disable_existing_loggers=False)

    target_metadata = build_module_metadata()
    include_object = make_include_object(target_metadata)
    # Preserve expression indexes, portable Boolean defaults and SQLite warnings.
    process_revision_directives = make_process_revision_directives(target_metadata)

    def _get_url() -> str:
        """Read database URL from settings, convert async to sync driver.

        The resolved URL is logged so the target is never a guess. ``.env``
        discovery walks up from the cwd and relative sqlite paths are anchored to
        the project root, so a wrong cwd no longer silently redirects the schema —
        but migrating the wrong database is quiet enough when it does happen
        (a stray app.db, nothing else) that printing the target, password masked,
        is worth the one line.
        """
        database_url = (
            config.attributes.get(ALEMBIC_DATABASE_URL_ATTRIBUTE) or Settings().database_url
        )
        detect_provider(database_url)
        url = database_url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg2")
        logger.info(
            "Migrating %s (cwd=%s)", make_url(url).render_as_string(hide_password=True), Path.cwd()
        )
        return url

    def run_migrations_offline() -> None:
        """Run migrations in 'offline' mode — generates SQL without a live DB."""
        url = _get_url()
        context.configure(
            url=url,
            target_metadata=target_metadata,
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
            include_object=include_object,
            render_item=render_item,
            process_revision_directives=process_revision_directives,
        )

        # Emit CREATE EXTENSION for what modules declare (ModuleBase.db_extensions).
        ensure_db_extensions(None, discover_modules())
        with context.begin_transaction():
            context.run_migrations()

    def run_migrations_online() -> None:
        """Run migrations against a live database."""
        configuration = config.get_section(config.config_ini_section, {})
        configuration["sqlalchemy.url"] = _get_url()

        connectable = engine_from_config(
            configuration,
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

        try:
            with connectable.connect() as connection:
                context.configure(
                    connection=connection,
                    target_metadata=target_metadata,
                    include_object=include_object,
                    render_item=render_item,
                    process_revision_directives=process_revision_directives,
                )

                # Extensions first, in their own committed transaction, so revisions
                # that use their types find them installed (ModuleBase.db_extensions).
                ensure_db_extensions(connection, discover_modules())
                connection.commit()

                with context.begin_transaction():
                    context.run_migrations()
        finally:
            connectable.dispose()

    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()
