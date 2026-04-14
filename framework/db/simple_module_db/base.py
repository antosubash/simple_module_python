"""Per-module declarative base with schema isolation."""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

from simple_module_db.provider import DatabaseProvider

# Convention-based naming for constraints (helps Alembic)
_naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Cache created bases to avoid recreating for the same module
_base_cache: dict[str, type[DeclarativeBase]] = {}

# Track all module bases for Alembic discovery
all_module_bases: list[type[DeclarativeBase]] = []


def create_module_base(
    module_name: str,
    provider: DatabaseProvider = DatabaseProvider.SQLITE,
) -> type[DeclarativeBase]:
    """Create a SQLAlchemy DeclarativeBase with schema isolation for a module.

    - PostgreSQL: uses a dedicated schema (e.g., ``products``)
    - SQLite: prefixes table names (e.g., ``products_product``)

    Returns a cached base if already created for this module+provider.
    """
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
        (DeclarativeBase,),
        {
            "__abstract__": True,
            "metadata": mod_metadata,
        },
    )

    # Store module name for reference
    ModuleBase.__module_name__ = schema_name  # type: ignore[attr-defined]  # ty: ignore[unresolved-attribute]

    _base_cache[cache_key] = ModuleBase
    all_module_bases.append(ModuleBase)
    return ModuleBase
