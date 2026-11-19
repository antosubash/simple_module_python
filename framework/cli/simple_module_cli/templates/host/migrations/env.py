"""Alembic environment; metadata and migration hooks are framework-owned."""

from alembic import context
from simple_module_hosting.migrations_env import run_migrations

run_migrations(context)
