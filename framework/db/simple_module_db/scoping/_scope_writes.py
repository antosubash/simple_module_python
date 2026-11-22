"""Insert hooks and ownership guards for module-defined scopes.

Tenant writes retain their established guards. Custom scalar scopes stamp direct
INSERTs too; arbitrary SQL expressions cannot be checked and are refused.
"""

from __future__ import annotations

from copy import copy
from typing import Any

from sqlalchemy import and_, inspect, literal, select
from sqlalchemy.orm import Session
from sqlalchemy.orm.evaluator import UnevaluatableError, _EvaluatorCompiler
from sqlalchemy.sql.elements import BindParameter, Label

from simple_module_db.scoping._builtin_scopes import tenant_scope
from simple_module_db.scoping._core_joins import _base_name
from simple_module_db.scoping.insert_guard import (
    _column_name,
    _param_rows,
    conflict_arm,
    raw_values,
    statement_values,
)
from simple_module_db.scoping.scopes import (
    ResolvedScope,
    ScopeFilter,
    ScopeIsolationError,
    resolve_scopes,
)


def refuse_scope_move(state: Any, scope: ScopeFilter) -> None:
    column = scope.column
    if column and (
        column in statement_values(state.statement)
        or any(column in row for row in _param_rows(state))
    ):
        raise ScopeIsolationError(f"Cannot change {column} of existing rows ({scope.name})")


def guard_scope_flush(session: Session) -> None:
    for resolved in resolve_scopes(session, {}, is_write=True):
        scope = resolved.scope
        if scope is tenant_scope:
            continue
        for obj in list(session.new) + list(session.dirty) + list(session.deleted):
            if type(obj) not in scope._classes:
                continue
            if resolved.required:
                raise scope.missing_error(type(obj).__name__, "FLUSH")
            if not resolved.active:
                continue
            state = inspect(obj)
            if obj in session.new:
                if scope.stamp:
                    scope.stamp(obj, resolved.value)
                try:
                    matches = _EvaluatorCompiler(type(obj)).process(resolved.predicate(type(obj)))(
                        obj
                    )
                except UnevaluatableError as exc:
                    raise ScopeIsolationError(
                        f"Cannot validate new object for scope '{scope.name}'"
                    ) from exc
                if not matches:
                    raise ScopeIsolationError(f"New object violates scope '{scope.name}'")
                continue
            if obj not in session.deleted and not session.is_modified(obj):
                continue
            if scope.column and state.attrs[scope.column].history.has_changes():
                raise ScopeIsolationError(f"Cannot change {scope.column} of an existing object")
            # Read persisted ownership even for detached/forged objects: the unit of
            # work itself writes by PK and cannot carry our predicate.
            mapper = state.mapper
            predicates = [
                col == value for col, value in zip(mapper.primary_key, state.identity, strict=True)
            ]
            probe = (
                select(literal(1))
                .select_from(mapper.local_table)
                .where(*predicates, resolved.predicate(mapper.local_table.c))
            )
            conn = session.connection(bind_arguments={"mapper": mapper})
            if conn.execute(probe).first() is None:
                raise ScopeIsolationError(f"Object is outside scope '{scope.name}'")


def _check_value(value: Any, resolved: ResolvedScope, params: list[dict], binds: dict) -> None:
    while isinstance(value, Label):
        value = value.element
    if isinstance(value, BindParameter):
        if value.callable is not None:
            raise ScopeIsolationError(f"Unverifiable INSERT for scope '{resolved.scope.name}'")
        values = [
            row.get(value.key, row.get(binds.get(value), value.value)) for row in params or [{}]
        ]
    elif hasattr(value, "__visit_name__"):
        raise ScopeIsolationError(f"Unverifiable INSERT for scope '{resolved.scope.name}'")
    else:
        values = [value]
    if any(value != resolved.value for value in values):
        raise ScopeIsolationError(f"INSERT violates scope '{resolved.scope.name}'")


def guard_scope_insert(state: Any, scopes: list[ResolvedScope]) -> None:
    for resolved in scopes:
        scope = resolved.scope
        stmt = state.statement
        if (
            scope is tenant_scope
            or scope.reads_only
            or _base_name(stmt.table) not in scope._table_names
        ):
            continue
        if resolved.required:
            raise scope.missing_error(stmt.table.name, "INSERT")
        if not resolved.active:
            continue
        if scope.column is None:
            raise ScopeIsolationError(f"INSERT needs a scalar column for scope '{scope.name}'")
        for prefix, _dialect in getattr(stmt, "_prefixes", ()):
            if "REPLACE" in str(prefix).upper():
                raise ScopeIsolationError(f"INSERT OR REPLACE is not scoped ({scope.name})")
        _guard_upsert(state, resolved)
        _stamp_insert(state, resolved)


def _stamp_insert(state: Any, resolved: ResolvedScope) -> None:
    scope, stmt = resolved.scope, state.statement
    column = scope.column
    assert column is not None
    rows = _param_rows(state)
    binds = {
        v: _column_name(k) for k, v in raw_values(stmt).items() if isinstance(v, BindParameter)
    }
    source = getattr(stmt, "select", None)
    if source is not None:
        names = list(stmt._select_names)
        if column in names:
            binds = stmt.compile().bind_names if rows else {}
            sources = [source]
            while sources:
                part = sources.pop()
                if hasattr(part, "selects"):
                    sources.extend(part.selects)
                else:
                    _check_value(
                        list(part.selected_columns)[names.index(column)], resolved, rows, binds
                    )
        elif scope.stamp:
            source = source.subquery()
            state.statement = stmt.from_select(
                [*names, column],
                select(*source.c, literal(resolved.value)),
                include_defaults=stmt.include_insert_from_select_defaults,
            )
        else:
            raise ScopeIsolationError(f"INSERT missing '{column}'")
        return
    if stmt._multi_values:
        groups = []
        for group in stmt._multi_values:
            stamped = []
            for row in group:
                mapping = (
                    dict(row)
                    if isinstance(row, dict)
                    else dict(zip(stmt.table.c, row, strict=False))
                )
                keys = {_column_name(k): k for k in mapping}
                if column in keys:
                    _check_value(mapping[keys[column]], resolved, rows, binds)
                elif scope.stamp:
                    mapping[stmt.table.c[column]] = resolved.value
                else:
                    raise ScopeIsolationError(f"INSERT missing '{column}'")
                stamped.append(mapping)
            groups.append(stamped)
        stmt = stmt._generate()
        stmt._multi_values = tuple(groups)
        state.statement = stmt
        return
    values = {_column_name(k): v for k, v in raw_values(stmt).items()}
    if column in values:
        _check_value(values[column], resolved, rows, binds)
    for row in rows:
        if column in row:
            _check_value(row[column], resolved, [], {})
    if rows:
        stamped = []
        for row in rows:
            if column not in row and column not in values:
                if not scope.stamp:
                    raise ScopeIsolationError(f"INSERT missing '{column}'")
                row = {**row, column: resolved.value}
            stamped.append(row)
        # Keep later tenant stamping/audit in the same execution pipeline.
        state.parameters = stamped if isinstance(state.parameters, list) else stamped[0]
    elif column not in values:
        if not scope.stamp:
            raise ScopeIsolationError(f"INSERT missing '{column}'")
        state.statement = stmt.values(**{column: resolved.value})


def _guard_upsert(state: Any, resolved: ResolvedScope) -> None:
    stmt = state.statement
    arm = conflict_arm(stmt)
    if arm is None:
        return
    if any(_column_name(k) == resolved.scope.column for k, _ in arm.update_values_to_set):
        raise ScopeIsolationError(f"Cannot change {resolved.scope.column} in conflict update")
    out, arm = stmt._generate(), copy(arm)
    pred = resolved.predicate(stmt.table.c)
    arm.update_whereclause = (
        pred if arm.update_whereclause is None else and_(arm.update_whereclause, pred)
    )
    out._post_values_clause = arm
    state.statement = out
