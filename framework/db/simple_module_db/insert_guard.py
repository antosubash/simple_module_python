"""INSERT guard and statement-value helpers for the tenant query filter.

Explicit ``tenant_id`` values in an insert must match the bound tenant, and
missing ones are stamped with it (#357) — or, unbound on a non-strict
install, with the install's fallback tenant (#380); the same value readers let the
query filter refuse an UPDATE that assigns ``tenant_id`` (#356).
"""

from __future__ import annotations

from copy import copy
from typing import Any

from sqlalchemy import and_, literal, select
from sqlalchemy.dialects.postgresql.dml import OnConflictDoUpdate as PgConflictUpdate
from sqlalchemy.dialects.sqlite.dml import OnConflictDoUpdate as SqliteConflictUpdate
from sqlalchemy.orm import ORMExecuteState
from sqlalchemy.sql.elements import BindParameter, Label

from simple_module_db import model_registry as registry
from simple_module_db.tenancy import (
    ALL_TENANTS_OPTION,
    DEFAULT_TENANT_ID,
    TenantIsolationError,
    current_tenant_id,
    is_all_tenants,
    missing_tenant_error,
)

TENANT_COLUMN = "tenant_id"


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


def assigned_tenant_ids(execute_state: ORMExecuteState) -> list[Any]:
    found = []
    stmt_values = _statement_values(execute_state)
    if TENANT_COLUMN in stmt_values:
        found.append(stmt_values[TENANT_COLUMN])
    found.extend(row[TENANT_COLUMN] for row in _param_rows(execute_state) if TENANT_COLUMN in row)
    return found


def _foreign_insert(value: Any, tenant_id: str) -> TenantIsolationError:
    return TenantIsolationError(
        f"Cannot insert rows for tenant '{value}' in context of tenant '{tenant_id}'"
    )


def guard_insert(
    execute_state: ORMExecuteState, *, strict: bool, fallback: str = DEFAULT_TENANT_ID
) -> Any:
    mappers = [m.class_.__name__ for m in execute_state.all_mappers if registry.flags(m.class_)[1]]
    target = getattr(execute_state.statement, "table", None)
    if not mappers and getattr(target, "name", None) in registry.tenant_table_names:
        mappers = [target.name]  # Core insert(Model.__table__)
    if not mappers:
        return None
    bypass = execute_state.execution_options.get(ALL_TENANTS_OPTION, False) or is_all_tenants()
    if bypass and strict:
        return None
    # A non-strict bypass checks no explicit values; missing ones still get
    # the bound tenant, else the install's fallback (#380).
    bound = current_tenant_id.get()
    if not bypass:
        _guard_conflict_update(execute_state, bound)
    tenant_id = None if bypass else bound
    stamp = bound or fallback
    if tenant_id is None and strict:
        raise missing_tenant_error(mappers[0], "INSERT")
    if getattr(execute_state.statement, "select", None) is not None:
        return _guard_from_select(execute_state, tenant_id, stamp)
    if getattr(execute_state.statement, "_multi_values", None):
        return _guard_multi_values(execute_state, tenant_id, stamp)
    for value in assigned_tenant_ids(execute_state):
        if tenant_id is not None and value != tenant_id:
            raise _foreign_insert(value, tenant_id)

    rows = _param_rows(execute_state)
    stmt_has_tenant = TENANT_COLUMN in _statement_values(execute_state)
    missing = (
        [r for r in rows if TENANT_COLUMN not in r] if rows else ([] if stmt_has_tenant else [None])
    )
    if not missing:
        return None
    if rows:
        stamped = [{**r, TENANT_COLUMN: r.get(TENANT_COLUMN, stamp)} for r in rows]
        payload = stamped if isinstance(execute_state.parameters, list) else stamped[0]
        return execute_state.invoke_statement(params=payload)
    execute_state.statement = execute_state.statement.values(**{TENANT_COLUMN: stamp})
    return None


def _guard_from_select(execute_state: ORMExecuteState, tenant_id: str | None, stamp: str) -> None:
    stmt = execute_state.statement
    names = list(stmt._select_names)
    if TENANT_COLUMN in names:
        if tenant_id is None:
            return
        # SQL expressions cannot be validated as Python values; require a bound
        # literal, or an explicit all_tenants bypass for cross-tenant copies.
        params = _param_rows(execute_state)
        bind_names = stmt.compile().bind_names if params else {}
        sources = [stmt.select]
        while sources:
            source = sources.pop()
            if hasattr(source, "selects"):
                sources.extend(source.selects)
                continue
            value = list(source.selected_columns)[names.index(TENANT_COLUMN)]
            while isinstance(value, Label):
                value = value.element
            if not isinstance(value, BindParameter) or value.callable is not None:
                raise TenantIsolationError("INSERT ... SELECT tenant_id must be a bound literal")
            for row in params or [{}]:
                assigned = row.get(
                    value.key, row.get(bind_names.get(value, value.key), value.value)
                )
                if assigned != tenant_id:
                    raise _foreign_insert(assigned, tenant_id)
        return
    source = stmt.select.subquery()
    execute_state.statement = stmt.from_select(
        [*names, TENANT_COLUMN],
        select(*source.c, literal(stamp)),
        include_defaults=stmt.include_insert_from_select_defaults,
    )


def _guard_multi_values(execute_state: ORMExecuteState, tenant_id: str | None, stamp: str) -> Any:
    """``insert(M).values([{...}, {...}])``: check and stamp each row.

    ``.values(tenant_id=...)`` cannot be appended to a multi-VALUES insert
    (SQLAlchemy refuses to mix the two forms), so the rows are rewritten.
    """
    stmt = execute_state.statement
    columns = list(stmt.table.c)
    tenant_col = stmt.table.c[TENANT_COLUMN]
    groups, missing = [], False
    for group in stmt._multi_values:
        rows = []
        for row in group:
            mapping = dict(row) if isinstance(row, dict) else dict(zip(columns, row, strict=False))
            keys = {_column_name(k): k for k in mapping}
            if TENANT_COLUMN in keys:
                value = _bound_value(mapping[keys[TENANT_COLUMN]])
                if tenant_id is not None and value != tenant_id:
                    raise _foreign_insert(value, tenant_id)
            else:
                missing = True
                mapping[tenant_col] = stamp
            rows.append(mapping)
        groups.append(rows)
    if not missing:
        return None
    stamped = stmt._generate()
    stamped._multi_values = tuple(groups)
    execute_state.statement = stamped
    return None


def _guard_conflict_update(execute_state: ORMExecuteState, tenant_id: str | None) -> None:
    """Conflict updates are UPDATEs: preserve ownership and scope their target."""
    stmt = execute_state.statement
    arm = getattr(stmt, "_post_values_clause", None)
    if not isinstance(arm, (PgConflictUpdate, SqliteConflictUpdate)):
        return
    if any(_column_name(key) == TENANT_COLUMN for key, _ in arm.update_values_to_set):
        raise TenantIsolationError("Cannot change tenant_id of existing rows")
    if tenant_id is None:
        return
    # SQLAlchemy has no generative setter for an existing conflict arm.
    scoped = stmt._generate()
    scoped_arm = copy(arm)
    predicate = stmt.table.c[TENANT_COLUMN] == tenant_id
    scoped_arm.update_whereclause = (
        predicate if arm.update_whereclause is None else and_(arm.update_whereclause, predicate)
    )
    scoped._post_values_clause = scoped_arm
    execute_state.statement = scoped
