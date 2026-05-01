"""Per-module SQLModel base with schema isolation."""

from __future__ import annotations

import os

from simple_module_core.dotenv import env_bool
from sqlalchemy import MetaData
from sqlmodel import SQLModel

from simple_module_db.provider import DatabaseProvider, detect_provider

# Convention-based naming for constraints (helps Alembic)
_naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Cache created bases to avoid recreating for the same module
_base_cache: dict[str, type[SQLModel]] = {}

# Track all module bases for Alembic discovery. Module-level *mutable* list
# so callers that imported it before every module registered (e.g. conftest,
# migrations/env.py) still observe new entries. Deduped at append time —
# see ``_register_base`` below.
all_module_bases: list[type[SQLModel]] = []


def _register_base(base: type[SQLModel]) -> None:
    """Append ``base`` to ``all_module_bases`` iff not already present.

    Guards against the list growing under repeated imports (test suites,
    reloaders, plugin discovery) without changing the public type.
    """
    if base not in all_module_bases:
        all_module_bases.append(base)


def _default_schema_policy() -> DatabaseProvider:
    """Resolve the schema layout to register module tables under.

    The :class:`DatabaseProvider` enum doubles as a *schema-layout*
    selector here — ``POSTGRESQL`` means "give every module its own
    schema (``orders.<table>``)", ``SQLITE`` means "shared public schema,
    name-prefixed tables (``orders_<table>``)". The conflation is
    deliberate so existing call sites keep working, but conceptually this
    is "schema policy", not "what DB are we connecting to": you can run
    Postgres with ``SM_SCHEMA_PER_MODULE=false`` to keep a flat layout.

    Resolution order:
      1. ``SM_SCHEMA_PER_MODULE`` (authoritative when set, decoupled from URL).
      2. ``SM_DATABASE_URL`` (legacy fallback so deployments that haven't
         migrated to the explicit knob keep working).
      3. ``SQLITE`` (shared schema, the safe default).
    """
    explicit = os.environ.get("SM_SCHEMA_PER_MODULE")
    if explicit is not None:
        return (
            DatabaseProvider.POSTGRESQL
            if env_bool("SM_SCHEMA_PER_MODULE")
            else DatabaseProvider.SQLITE
        )

    url = os.environ.get("SM_DATABASE_URL", "")
    if url:
        return detect_provider(url)
    return DatabaseProvider.SQLITE


# Back-compat alias for the previous private name. Internal callers should
# prefer the new spelling; the alias keeps any monkeypatch-based test fixtures
# working through the rename.
_default_provider = _default_schema_policy


def create_module_base(
    module_name: str,
    provider: DatabaseProvider | None = None,
) -> type[SQLModel]:
    """Create a SQLModel abstract base with schema isolation for a module.

    - PostgreSQL: uses a dedicated schema (e.g., ``products``)
    - SQLite: single schema; modules are expected to prefix ``__tablename__``
      with the module name to avoid collisions (e.g., ``products_product``)

    The provider defaults to whatever ``SM_DATABASE_URL`` indicates, so
    module models work in both dev (SQLite) and prod (PostgreSQL) without
    code changes. Pass ``provider=`` explicitly in tests that need to pin it.

    Returns a cached base if already created for this module+provider. The
    returned class is a ``SQLModel`` subclass with a per-module ``MetaData``;
    concrete table classes declare ``table=True`` and inherit from it.
    """
    if provider is None:
        provider = _default_schema_policy()

    cache_key = f"{module_name}:{provider}"
    if cache_key in _base_cache:
        return _base_cache[cache_key]

    schema_name = module_name.lower()

    if provider == DatabaseProvider.POSTGRESQL:
        mod_metadata = MetaData(schema=schema_name, naming_convention=_naming_convention)
    else:
        mod_metadata = MetaData(naming_convention=_naming_convention)

    # Use type() to create the class, avoiding class body scoping issues
    ModuleBase = type(  # noqa: N806
        f"{module_name.title()}Base",
        (SQLModel,),
        {
            "__abstract__": True,
            "metadata": mod_metadata,
        },
    )

    # Store module name for reference
    ModuleBase.__module_name__ = schema_name  # type: ignore[attr-defined]

    _base_cache[cache_key] = ModuleBase
    _register_base(ModuleBase)
    return ModuleBase
