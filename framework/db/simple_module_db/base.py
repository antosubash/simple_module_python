"""Per-module SQLModel base.

Every module owns its own :class:`sqlalchemy.MetaData` so Alembic autogenerate
can attribute tables to a module, but all tables live in the host's single
``public`` schema. Modules prefix ``__tablename__`` with the module name to
avoid collisions (e.g. ``users_user``).
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlmodel import SQLModel

# Convention-based naming for constraints (helps Alembic)
_naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

_base_cache: dict[str, type[SQLModel]] = {}

# Track all module bases for Alembic discovery. Module-level *mutable* list
# so callers that imported it before every module registered (e.g. conftest,
# migrations/env.py) still observe new entries. Deduped at append time —
# see ``_register_base`` below.
all_module_bases: list[type[SQLModel]] = []


def _register_base(base: type[SQLModel]) -> None:
    """Append ``base`` to ``all_module_bases`` iff not already present."""
    if base not in all_module_bases:
        all_module_bases.append(base)


def create_module_base(module_name: str) -> type[SQLModel]:
    """Create a SQLModel abstract base with its own ``MetaData`` for a module.

    All modules share the host's single schema. Concrete tables should prefix
    ``__tablename__`` with ``module_name`` (e.g. ``users_user``) so names don't
    collide. The per-module ``MetaData`` is what lets Alembic autogenerate
    attribute each table to its module and what makes ``build_module_metadata``
    able to assemble the combined target metadata.

    Returns a cached base on repeat calls for the same module name.
    """
    module_name = module_name.lower()
    if module_name in _base_cache:
        return _base_cache[module_name]

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

    ModuleBase.__module_name__ = module_name  # type: ignore[attr-defined]

    _base_cache[module_name] = ModuleBase
    _register_base(ModuleBase)
    return ModuleBase
