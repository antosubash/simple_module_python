"""Mapped models and cached membership in each registered scope.

Filled as mappers are constructed (and topped up from any statement that names a
model), so criteria can be attached for models a statement does *not* name:
a join target, a subquery, a count (#332).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Mapper

from simple_module_db import scopes
from simple_module_db._builtin_scopes import soft_delete_scope, tenant_scope
from simple_module_db.mixins import MultiTenantMixin, SoftDeleteMixin

tenant_classes = tenant_scope._classes
soft_delete_classes = soft_delete_scope._classes
tenant_table_names = tenant_scope._table_names
soft_delete_table_names = soft_delete_scope._table_names
# Mapped class per ``Table`` — resolves a Core DML target (``Model.__table__``)
# back to its model, for bulk-write auditing (#557).
classes_by_table: dict[Any, type] = {}
# Several inheritance mappers can share a table; registration must see each.
mapped_classes: set[type] = set()

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
    mapped_classes.add(cls)
    classes_by_table.setdefault(table, cls)
    for scope in scopes._scopes.values():
        if cls not in scope._classes:
            scope.register_model(cls)


@event.listens_for(Mapper, "mapper_configured")
def _on_mapper_configured(mapper: Mapper, cls: type) -> None:
    register(cls)


@event.listens_for(Mapper, "after_mapper_constructed")
def _on_mapper_constructed(mapper: Mapper, cls: type) -> None:
    # Registered as soon as the class is mapped, not when mappers configure:
    # a Core statement over ``Model.__table__`` run before any ORM use would
    # otherwise find the table unknown, and unscoped.
    register(cls)


scopes.register_scope(soft_delete_scope)
scopes.register_scope(tenant_scope)
