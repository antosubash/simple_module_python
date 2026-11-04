"""Tenant / soft-delete criteria for a relationship's ``secondary`` table.

``relationship(secondary=Link.__table__)`` joins a plain table that loader
criteria never see: ``joinedload``, ``selectinload``, ``subqueryload`` and a
``join(Parent.links)`` build that join at compile time, from the
relationship itself. (A lazy load names the table in its ``WHERE``, where
``core_scope`` finds it.) So once a mapper is configured, every relationship
whose ``secondary`` is a tenant-scoped or soft-deletable table gets its
``secondaryjoin`` extended with

* ``:all_tenants OR secondary.tenant_id = :tenant``, and
* ``:include_deleted OR secondary.is_deleted IS false``.

The values are bound per execution, not per statement: the parameters are
``callable_`` binds, read when the statement's parameters are built, from
the scope ``record_execution_scope`` records just before — from the statement's
execution options (``all_tenants`` / ``include_deleted``), the bound tenant
and the engine's strict mode. Strict mode with no tenant matches no link row.
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
_scoped: list[Any] = []  # the relationships extended so far


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
    _scoped.append(prop)


@event.listens_for(Mapper, "mapper_configured")
def _on_mapper_configured(mapper: Mapper, cls: type) -> None:
    for prop in mapper.relationships:
        if prop.parent is mapper:
            scope_relationship(prop)


def record_execution_scope(
    conn: Any, clause: Any, multiparams: Any, params: Any, options: Any
) -> None:
    """``before_execute``: record the scope the criteria above read for this execution."""
    if not _scoped:
        return
    policy = policy_of(conn)
    strict = bool(policy is not None and policy.tenant_strict)
    tenant_id = current_tenant_id.get()
    skip_tenant = (
        bool(options.get(ALL_TENANTS_OPTION))
        or is_all_tenants()
        or (tenant_id is None and not strict)
    )
    _scope.set(_Scope(skip_tenant, tenant_id, bool(options.get(INCLUDE_DELETED_OPTION))))


def install_execution_scope(engine: Any) -> None:
    if isinstance(engine, Engine) and not event.contains(
        engine, "before_execute", record_execution_scope
    ):
        event.listen(engine, "before_execute", record_execution_scope)


__all__ = ["install_execution_scope", "scope_relationship", "secondary_criteria"]
