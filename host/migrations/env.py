"""Alembic environment — discovers module models via entry points.

This file is the canonical template used by the host scaffold. All the logic
for discovering installed modules and aggregating their metadata lives in
``simple_module_db.migrations`` so new hosts get the behaviour for free.
"""

from __future__ import annotations

import logging
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from simple_module_db import (
    build_module_metadata,
    make_include_object,
    make_process_revision_directives,
    render_item,
)
from simple_module_hosting.settings import Settings
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url

logger = logging.getLogger("alembic.env")

# Alembic Config object
config = context.config

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Build target metadata by importing every installed module's models.
target_metadata = build_module_metadata()

# Autogenerate must only diff tables owned by installed modules — never the
# host's user-added tables or framework internals.
include_object = make_include_object(target_metadata)

# Re-emit expression-based indexes (e.g. ``lower(email)``) that autogenerate
# silently drops under SQLite — see make_process_revision_directives docstring.
process_revision_directives = make_process_revision_directives(target_metadata)


def _get_url() -> str:
    """Read database URL from settings, convert async to sync driver.

    The resolved URL is logged because ``Settings`` reads ``.env`` relative to
    the *current working directory*: run alembic from the wrong cwd and it
    silently falls back to the default SQLite file while the app talks to the
    configured database. Printing the target — password masked — turns that
    into something you notice on the first migration instead of a schema that
    lives in a database nobody reads.
    """
    settings = Settings()
    url = settings.database_url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg2")
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

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            render_item=render_item,
            process_revision_directives=process_revision_directives,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
