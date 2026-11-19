"""Registered scopes for mapped relationship secondary tables.

Loader criteria cannot see a plain secondary Table built at compile time. Add
parameterized join predicates once, then bind each scope and bypass per execution.
Unmapped association tables remain unscoped, regardless of their column names.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from sqlalchemy import Boolean, and_, bindparam, event, or_
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Mapper

from simple_module_db import scopes
from simple_module_db._core_joins import _base_name
from simple_module_db.scopes import ScopeFilter

_SCOPED_MARK = "_sm_secondary_scoped"
_scope: ContextVar[dict[str, tuple[bool, Any]] | None] = ContextVar(
    "sm_secondary_scope", default=None
)
_any_scoped = False


def _current(scope: ScopeFilter) -> tuple[bool, Any]:
    found = _scope.get()
    if found is not None:
        return found.get(scope.name, (True, None))
    value = scope.value()
    return scope.bypassed({}) or value is None, value


def secondary_criteria(table: Any, added: set[str]) -> list[Any]:
    name = _base_name(table)
    criteria = []
    for scope in scopes._scopes.values():
        if name not in scope._table_names or scope.name in added:
            continue
        skip = bindparam(
            f"sm_secondary_skip_{scope.name}",
            type_=Boolean(),
            callable_=lambda s=scope: _current(s)[0],
        )
        value = bindparam(
            f"sm_secondary_value_{scope.name}",
            type_=table.c[scope.column].type if scope.column else None,
            callable_=lambda s=scope: _current(s)[1],
        )
        present = bindparam(
            f"sm_secondary_present_{scope.name}",
            type_=Boolean(),
            callable_=lambda s=scope: _current(s)[1] is not None,
        )
        criteria.append(or_(skip, and_(present, scope.criteria(table.c, value))))
        added.add(scope.name)
    return criteria


def scope_relationship(prop: Any) -> None:
    """Extend a relationship with any not-yet-installed registered scopes."""
    if prop.secondary is None:
        return
    added = getattr(prop, _SCOPED_MARK, set())
    criteria = secondary_criteria(prop.secondary, added)
    if not criteria:
        return
    join_condition = prop._join_condition
    join_condition.secondaryjoin = and_(join_condition.secondaryjoin, *criteria)
    prop.secondaryjoin = join_condition.secondaryjoin
    setattr(prop, _SCOPED_MARK, added)
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
    if not _any_scoped:
        return
    is_write = bool(getattr(clause, "is_update", False) or getattr(clause, "is_delete", False))
    values = {}
    for scope in scopes._scopes.values():
        value = scope.value()
        skip = (
            (is_write and scope.reads_only)
            or scope.bypassed(options)
            or (value is None and not scope.requires_context(conn))
        )
        # Keep the bound value even during a bypass: cached relationship SQL
        # still binds it, as the built-in tenant policy has always done.
        values[scope.name] = (skip, value)
    _scope.set(values)


def clear_execution_scope(*_args: Any) -> None:
    if _scope.get() is not None:
        _scope.set(None)


# Every engine records options, including unbound engines. Clear after failure too,
# so a subsequent execution (or child task) cannot inherit a previous bypass.
event.listen(Engine, "before_execute", record_execution_scope)
event.listen(Engine, "after_execute", clear_execution_scope)
event.listen(Engine, "handle_error", clear_execution_scope)

__all__: list[str] = []
