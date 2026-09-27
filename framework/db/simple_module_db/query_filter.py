"""``do_orm_execute`` filter: soft-delete and tenant scoping on every ORM statement.

Scope (#332). Tenant and soft-delete criteria are attached for *every*
tenant-scoped / soft-deletable model, not only the entities a statement
names, so a table reached through a join target, an ORM ``exists()`` /
``in_()`` / scalar subquery or ``select(func.count()).select_from(Model)`` is
filtered too. A Core statement on ``Model.__table__`` at the top level
(select / update / delete) gets explicit predicates, and a bare Core
``exists().where(...)`` has its inner SELECT rewritten (``subquery_guard``).
"""

from __future__ import annotations

from typing import Any
from weakref import WeakKeyDictionary

from sqlalchemy.engine import Engine
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria

from simple_module_db import model_registry as registry
from simple_module_db.subquery_guard import scope_exists_subqueries
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
    named: list[type] = []
    for mapper in execute_state.all_mappers:
        if registry.flags(mapper.class_)[1]:
            named.append(mapper.class_)
    if not skip_soft_delete:
        options.extend(_soft_delete_criteria(execute_state))
    if not skip_tenant:
        options.extend(_tenant_criteria(execute_state, named, tenant_id, strict))
    if registry.tenant_classes or registry.soft_delete_classes:
        execute_state.statement = scope_exists_subqueries(
            execute_state.statement,
            _subquery_predicates(skip_soft_delete, skip_tenant, tenant_id, strict),
        )

    if options:
        execute_state.statement = execute_state.statement.options(*options)
    return None


def _soft_delete_criteria(execute_state: ORMExecuteState) -> list[Any]:
    for table in _plain_tables(execute_state, registry.soft_delete_table_names):
        execute_state.statement = execute_state.statement.where(table.c.is_deleted.is_(False))
    return [
        with_loader_criteria(c, c.is_deleted.is_(False), include_aliases=True)
        for c in registry.soft_delete_classes
    ]


def _subquery_predicates(
    skip_soft_delete: bool, skip_tenant: bool, tenant_id: str | None, strict: bool
):
    def predicates_for(from_obj: Any) -> list[Any]:
        name = getattr(from_obj, "name", None)
        preds = []
        if not skip_soft_delete and name in registry.soft_delete_table_names:
            preds.append(from_obj.c.is_deleted.is_(False))
        if not skip_tenant and name in registry.tenant_table_names:
            if tenant_id is not None:
                preds.append(from_obj.c.tenant_id == tenant_id)
            elif strict:
                raise missing_tenant_error(name, "SELECT")
        return preds

    return predicates_for


def _plain_tables(execute_state: ORMExecuteState, names: set[str]) -> list[Any]:
    """Tables a statement uses as plain Core tables (``Model.__table__``).

    Only the top level: the FROM list of a select, the target of an
    update/delete. ORM-annotated occurrences are covered by loader criteria.
    """
    stmt = execute_state.statement
    if execute_state.is_select:
        froms = [*getattr(stmt, "columns_clause_froms", ()), *getattr(stmt, "_from_obj", ())]
    else:
        froms = [getattr(stmt, "table", None)]
    return [f for f in froms if registry.is_plain_table(f, names)]


def _tenant_criteria(
    execute_state: ORMExecuteState, named: list[type], tenant_id: str | None, strict: bool
) -> list[Any]:
    core = _plain_tables(execute_state, registry.tenant_table_names)
    if execute_state.is_update and (named or core) and _assigned_tenant_ids(execute_state):
        raise TenantIsolationError("Cannot change tenant_id of existing rows")
    op = (
        "SELECT" if execute_state.is_select else ("UPDATE" if execute_state.is_update else "DELETE")
    )
    if tenant_id is None:
        if not strict:
            return []
        if named or core:
            raise missing_tenant_error(named[0].__name__ if named else core[0].name, op)
        # Indirect references (joins, subqueries) with no tenant bound match
        # nothing — tenant_id is NOT NULL — rather than every tenant.
        return [
            with_loader_criteria(c, c.tenant_id.is_(None), include_aliases=True)
            for c in registry.tenant_classes
        ]
    for table in core:
        execute_state.statement = execute_state.statement.where(table.c.tenant_id == tenant_id)
    return [
        with_loader_criteria(c, c.tenant_id == tenant_id, include_aliases=True)
        for c in registry.tenant_classes | set(named)
    ]


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
    mappers = [m.class_.__name__ for m in execute_state.all_mappers if registry.flags(m.class_)[1]]
    target = getattr(execute_state.statement, "table", None)
    if not mappers and getattr(target, "name", None) in registry.tenant_table_names:
        mappers = [target.name]  # Core insert(Model.__table__)
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
            raise missing_tenant_error(mappers[0], "INSERT")
        return None
    if rows:
        stamped = [{**r, TENANT_COLUMN: r.get(TENANT_COLUMN, tenant_id)} for r in rows]
        payload = stamped if isinstance(execute_state.parameters, list) else stamped[0]
        return execute_state.invoke_statement(params=payload)
    execute_state.statement = execute_state.statement.values(**{TENANT_COLUMN: tenant_id})
    return None
