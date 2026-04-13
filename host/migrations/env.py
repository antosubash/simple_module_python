"""Alembic environment — discovers module models via entry points."""

from __future__ import annotations

import importlib
import logging
from logging.config import fileConfig

from alembic import context
from simple_module_core.discovery import discover_modules
from simple_module_db.base import all_module_bases
from simple_module_hosting.settings import Settings
from sqlalchemy import MetaData, engine_from_config, pool

logger = logging.getLogger("alembic.env")

# Alembic Config object
config = context.config

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ── Discover module models ──────────────────────────────────────────
# discover_modules() loads module classes via entry points, but models
# are imported lazily. We import each module's ``models`` submodule
# explicitly so create_module_base() runs and all_module_bases populates.
modules = discover_modules()
for mod in modules:
    pkg = type(mod).__module__.split(".")[0]
    try:
        importlib.import_module(f"{pkg}.models")
    except ModuleNotFoundError:
        logger.debug("No models submodule for module '%s'", mod.meta.name)

# Combine all module metadata into a single MetaData for autogenerate
target_metadata = MetaData()
for base in all_module_bases:
    for table in base.metadata.tables.values():
        table.to_metadata(target_metadata)

# Allowlist: only manage tables declared by modules
MODULE_TABLES = {t.name for t in target_metadata.tables.values()}


def include_object(object, name, type_, reflected, compare_to):
    """Filter autogenerate to only module-declared tables."""
    if type_ == "table":
        return name in MODULE_TABLES
    if hasattr(object, "table"):
        return object.table.name in MODULE_TABLES
    return True


def _get_url() -> str:
    """Read database URL from settings, convert async to sync driver."""
    settings = Settings()
    url = settings.database_url
    url = url.replace("+aiosqlite", "")
    url = url.replace("+asyncpg", "+psycopg2")
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
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
