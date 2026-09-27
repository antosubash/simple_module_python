"""Every mapped tenant-scoped and soft-deletable model, known to the filters.

Filled as mappers configure (and topped up from any statement that names a
model), so criteria can be attached for models a statement does *not* name:
a join target, a subquery, a count (#332).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Mapper

from simple_module_db.mixins import MultiTenantMixin, SoftDeleteMixin

tenant_classes: set[type] = set()
soft_delete_classes: set[type] = set()
tenant_table_names: set[str] = set()
soft_delete_table_names: set[str] = set()

# ``(is_soft_delete, is_multi_tenant)`` per class, for the hot path.
_flags_cache: dict[type, tuple[bool, bool]] = {}


def flags(cls: type) -> tuple[bool, bool]:
    found = _flags_cache.get(cls)
    if found is None:
        found = (issubclass(cls, SoftDeleteMixin), issubclass(cls, MultiTenantMixin))
        _flags_cache[cls] = found
        register(cls)
    return found


def register(cls: type) -> None:
    table = getattr(cls, "__table__", None)
    if table is None:
        return
    if issubclass(cls, MultiTenantMixin) and cls not in tenant_classes:
        tenant_classes.add(cls)
        tenant_table_names.add(table.name)
    if issubclass(cls, SoftDeleteMixin) and cls not in soft_delete_classes:
        soft_delete_classes.add(cls)
        soft_delete_table_names.add(table.name)


@event.listens_for(Mapper, "mapper_configured")
def _on_mapper_configured(mapper: Mapper, cls: type) -> None:
    register(cls)


def is_plain_table(from_obj: Any, names: set[str]) -> bool:
    """A Core table (``Model.__table__``), not an ORM-annotated occurrence."""
    return getattr(from_obj, "name", None) in names and "parententity" not in getattr(
        from_obj, "_annotations", {}
    )
