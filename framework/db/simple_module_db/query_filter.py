"""``do_orm_execute`` filter: soft-delete and tenant scoping on every ORM statement.

Scope — what this filter can and cannot see. It works on the ORM entities a
statement names (``execute_state.all_mappers``): ``select(Model)``,
``update(Model)``, ``delete(Model)``, ``insert(Model)``, relationship loads.
A tenant-scoped table reached only through a join target, an ``exists()`` /
``in_()`` subquery, ``select(func.count()).select_from(Model)`` or a Core
statement on ``Model.__table__`` is NOT scoped (#332) — module code must name
the entity or add the ``tenant_id`` predicate itself.
"""

from __future__ import annotations

from typing import Any
from weakref import WeakKeyDictionary

from sqlalchemy.engine import Engine
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria

from simple_module_db.mixins import MultiTenantMixin, SoftDeleteMixin
from simple_module_db.tenancy import (
    ALL_TENANTS_OPTION,
    TenantIsolationError,
    current_tenant_id,
    is_all_tenants,
    missing_tenant_error,
)

TENANT_COLUMN = "tenant_id"

# Per-engine tenancy policy. Keyed by engine rather than held in a module
# global so two ``DatabaseState``s in one process (tests, a CLI next to an
# app) cannot switch each other's strict mode off. Values expose
# ``tenant_strict`` — a ``DatabaseState``, or an ``EngineTenancy`` for a bare
# sync engine such as the Celery worker's.
_engine_policy: WeakKeyDictionary[Engine, Any] = WeakKeyDictionary()


class EngineTenancy:
    """Tenancy policy for an engine that has no ``DatabaseState``."""

    def __init__(self, *, tenant_strict: bool) -> None:
        self.tenant_strict = tenant_strict


def bind_engine_policy(engine: Engine, policy: Any) -> None:
    """Attach a policy (anything with ``tenant_strict``) to a sync engine."""
    _engine_policy[engine] = policy


def _strict_configured(session: Session) -> bool:
    bind = session.bind
    policy = _engine_policy.get(bind) if isinstance(bind, Engine) else None
    return bool(policy is not None and policy.tenant_strict)


def is_strict(session: Session) -> bool:
    """Strict isolation is on for this session's engine and not waived."""
    return _strict_configured(session) and not is_all_tenants()


# Cache ``(is_soft_delete, is_multi_tenant)`` flags per mapper class so the
# ``do_orm_execute`` hot path skips redundant ``issubclass`` work on every query.
_mixin_flags_cache: dict[type, tuple[bool, bool]] = {}


def _flags(cls: type) -> tuple[bool, bool]:
    flags = _mixin_flags_cache.get(cls)
    if flags is None:
        flags = (issubclass(cls, SoftDeleteMixin), issubclass(cls, MultiTenantMixin))
        _mixin_flags_cache[cls] = flags
    return flags


def filter_statements(execute_state: ORMExecuteState) -> Any:
    """Scope ORM statements by soft-delete and tenant.

    * SELECT: soft-delete + tenant loader criteria.
    * UPDATE / DELETE: tenant criteria, and an UPDATE may not assign
      ``tenant_id`` (the bulk sibling of the unit-of-work rule).
    * INSERT: explicit ``tenant_id`` values must match the bound tenant;
      missing ones are stamped with it (#357).

    Without a tenant, strict mode raises instead of leaving the statement
    unscoped. Bypass: ``execution_options(all_tenants=True)`` or
    ``all_tenants()``; soft-delete bypass: ``include_deleted=True``.
    """
    if execute_state.is_insert:
        return _guard_insert(execute_state)
    is_select = execute_state.is_select
    if not (is_select or execute_state.is_update or execute_state.is_delete):
        return None

    options_in = execute_state.execution_options
    skip_soft_delete = not is_select or options_in.get("include_deleted", False)
    tenant_id = current_tenant_id.get()
    skip_tenant = options_in.get(ALL_TENANTS_OPTION, False) or is_all_tenants()
    strict = _strict_configured(execute_state.session)
    if skip_soft_delete and (skip_tenant or (tenant_id is None and not strict)):
        return None

    options = []
    for mapper in execute_state.all_mappers:
        cls = mapper.class_
        is_soft_delete, is_multi_tenant = _flags(cls)
        if is_soft_delete and not skip_soft_delete:
            options.append(
                with_loader_criteria(cls, cls.is_deleted.is_(False), include_aliases=True)
            )
        if not is_multi_tenant or skip_tenant:
            continue
        if execute_state.is_update and _assigned_tenant_ids(execute_state):
            raise TenantIsolationError("Cannot change tenant_id of existing rows")
        if tenant_id is not None:
            options.append(
                with_loader_criteria(cls, cls.tenant_id == tenant_id, include_aliases=True)
            )
        elif strict:
            op = "SELECT" if is_select else ("UPDATE" if execute_state.is_update else "DELETE")
            raise missing_tenant_error(cls.__name__, op)

    if options:
        execute_state.statement = execute_state.statement.options(*options)
    return None


def _bound_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _column_name(key: Any) -> str:
    return getattr(key, "key", None) or getattr(key, "name", None) or str(key)


def _statement_values(execute_state: ORMExecuteState) -> dict[str, Any]:
    raw = getattr(execute_state.statement, "_values", None) or {}
    return {_column_name(k): _bound_value(v) for k, v in raw.items()}


def _param_rows(execute_state: ORMExecuteState) -> list[dict[str, Any]]:
    params = execute_state.parameters
    if isinstance(params, dict):
        return [params] if params else []
    return [p for p in (params or []) if isinstance(p, dict)]


def _assigned_tenant_ids(execute_state: ORMExecuteState) -> list[Any]:
    found = []
    stmt_values = _statement_values(execute_state)
    if TENANT_COLUMN in stmt_values:
        found.append(stmt_values[TENANT_COLUMN])
    found.extend(row[TENANT_COLUMN] for row in _param_rows(execute_state) if TENANT_COLUMN in row)
    return found


def _guard_insert(execute_state: ORMExecuteState) -> Any:
    mappers = [m.class_ for m in execute_state.all_mappers if _flags(m.class_)[1]]
    if not mappers or execute_state.execution_options.get(ALL_TENANTS_OPTION, False):
        return None
    if is_all_tenants():
        return None
    tenant_id = current_tenant_id.get()
    for value in _assigned_tenant_ids(execute_state):
        if tenant_id is not None and value != tenant_id:
            raise TenantIsolationError(
                f"Cannot insert rows for tenant '{value}' in context of tenant '{tenant_id}'"
            )

    rows = _param_rows(execute_state)
    stmt_has_tenant = TENANT_COLUMN in _statement_values(execute_state)
    missing = (
        [r for r in rows if TENANT_COLUMN not in r] if rows else ([] if stmt_has_tenant else [None])
    )
    if not missing:
        return None
    if tenant_id is None:
        if _strict_configured(execute_state.session):
            raise missing_tenant_error(mappers[0].__name__, "INSERT")
        return None
    if rows:
        stamped = [{**r, TENANT_COLUMN: r.get(TENANT_COLUMN, tenant_id)} for r in rows]
        payload = stamped if isinstance(execute_state.parameters, list) else stamped[0]
        return execute_state.invoke_statement(params=payload)
    execute_state.statement = execute_state.statement.values(**{TENANT_COLUMN: tenant_id})
    return None
