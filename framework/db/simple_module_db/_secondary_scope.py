"""Tenant / soft-delete criteria for a relationship's ``secondary`` table.

``relationship(secondary=Link.__table__)`` joins a plain table that loader
criteria never see: ``joinedload``, ``selectinload``, ``subqueryload`` and a
``join(Parent.links)`` build that join at compile time, from the
relationship itself. (A lazy load names the table in its ``WHERE``, where
``core_scope`` finds it.) So once a mapper is configured, every relationship
whose ``secondary`` is the table of a ``MultiTenantMixin`` /
``SoftDeleteMixin`` model gets its ``secondaryjoin`` extended with

* ``:all_tenants OR secondary.tenant_id = :tenant``, and
* ``:include_deleted OR secondary.is_deleted IS false``.

The values are bound per execution, not per statement: the parameters are
``callable_`` binds, read when the statement's parameters are built, from
the scope ``record_execution_scope`` records just before — from the statement's
execution options (``all_tenants`` / ``include_deleted``), the bound tenant
and the engine's strict mode. Strict mode with no tenant matches no link row.
Like the main filter, an UPDATE / DELETE skips the soft-delete criterion: writes
may touch trashed rows. The scope is cleared after each execution.

A bare association ``Table`` that no mapped mixin class owns is not scoped,
``tenant_id`` column or not, like every other unmapped table.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any, NamedTuple

from sqlalchemy import Boolean, String, and_, bindparam, event, or_
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Mapper

from simple_module_db import model_registry as registry
from simple_module_db._core_joins import _base_name
from simple_module_db._engine_policies import policy_of
from simple_module_db.tenancy import ALL_TENANTS_OPTION, current_tenant_id, is_all_tenants

INCLUDE_DELETED_OPTION = "include_deleted"
_SCOPED_MARK = "_sm_secondary_scoped"


class _Scope(NamedTuple):
    skip_tenant: bool
    tenant_id: str | None
    skip_deleted: bool


_scope: ContextVar[_Scope | None] = ContextVar("sm_secondary_scope", default=None)
_any_scoped = False  # whether any relationship has been extended yet


def _current() -> _Scope:
    found = _scope.get()
    if found is not None:
        return found
    tenant_id = current_tenant_id.get()
    return _Scope(is_all_tenants() or tenant_id is None, tenant_id, False)


def secondary_criteria(table: Any) -> list[Any]:
    name = _base_name(table)
    criteria: list[Any] = []
    if name in registry.tenant_table_names:
        skip = bindparam("sm_secondary_all_tenants", type_=Boolean(), callable_=_skip_tenant)
        tenant = bindparam("sm_secondary_tenant_id", type_=String(), callable_=_tenant_id)
        criteria.append(or_(skip, table.c.tenant_id == tenant))
    if name in registry.soft_delete_table_names:
        skip = bindparam("sm_secondary_include_deleted", type_=Boolean(), callable_=_skip_deleted)
        criteria.append(or_(skip, table.c.is_deleted.is_(False)))
    return criteria


def _skip_tenant() -> bool:
    return _current().skip_tenant


def _tenant_id() -> str | None:
    return _current().tenant_id


def _skip_deleted() -> bool:
    return _current().skip_deleted


def scope_relationship(prop: Any) -> None:
    """Extend ``prop``'s ``secondaryjoin`` with its secondary table's criteria; idempotent."""
    if prop.secondary is None or getattr(prop, _SCOPED_MARK, False):
        return
    criteria = secondary_criteria(prop.secondary)
    if not criteria:
        return
    join_condition = prop._join_condition
    join_condition.secondaryjoin = and_(join_condition.secondaryjoin, *criteria)
    prop.secondaryjoin = join_condition.secondaryjoin
    setattr(prop, _SCOPED_MARK, True)
    global _any_scoped
    _any_scoped = True


@event.listens_for(Mapper, "mapper_configured")
def _on_mapper_configured(mapper: Mapper, cls: type) -> None:
    for prop in mapper.relationships:
        if prop.parent is mapper:
            scope_relationship(prop)


def record_execution_scope(
    conn: Any, clause: Any, multiparams: Any, params: Any, options: Any
) -> None:
    """``before_execute``: record the scope the criteria above read for this execution."""
    if not _any_scoped:
        return
    policy = policy_of(conn)
    strict = bool(policy is not None and policy.tenant_strict)
    tenant_id = current_tenant_id.get()
    skip_tenant = (
        bool(options.get(ALL_TENANTS_OPTION))
        or is_all_tenants()
        or (tenant_id is None and not strict)
    )
    is_write = bool(getattr(clause, "is_update", False) or getattr(clause, "is_delete", False))
    skip_deleted = is_write or bool(options.get(INCLUDE_DELETED_OPTION))
    _scope.set(_Scope(skip_tenant, tenant_id, skip_deleted))


def clear_execution_scope(*_args: Any) -> None:
    """``after_execute``: forget the scope, so nothing outside an execution reads it."""
    if _scope.get() is not None:
        _scope.set(None)


# On the ``Engine`` class, so every engine records the scope — bound to a policy or
# not. A per-engine listener left an unbound engine reading the previous
# execution's scope and ignoring its options. Each execution sets the scope
# before its parameters are built and clears it afterwards; an execution that
# fails leaves a value the next execution overwrites before reading.
event.listen(Engine, "before_execute", record_execution_scope)
event.listen(Engine, "after_execute", clear_execution_scope)

__all__: list[str] = []
