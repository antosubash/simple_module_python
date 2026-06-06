"""Alembic environment for a SimpleModule host.

Discovery + metadata aggregation lives in `simple_module_db.migrations` so
this file stays small and identical across all hosts. Don't add module-
specific imports here — install the module package and re-run autogenerate.
"""

from __future__ import annotations

import logging
from logging.config import fileConfig

from alembic import context
from simple_module_db import (
    build_module_metadata,
    make_include_object,
    make_process_revision_directives,
    render_item,
)
from simple_module_hosting.settings import Settings
from sqlalchemy import engine_from_config, pool

logger = logging.getLogger("alembic.env")

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = build_module_metadata()
include_object = make_include_object(target_metadata)
# Re-emit expression-based indexes (e.g. ``lower(email)``) that autogenerate
# silently drops under SQLite. See ``make_process_revision_directives`` docstring.
process_revision_directives = make_process_revision_directives(target_metadata)


def _get_url() -> str:
    """Read database URL from settings, convert async to sync driver."""
    settings = Settings()
    return settings.database_url.replace("+aiosqlite", "").replace("+asyncpg", "+psycopg2")


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
