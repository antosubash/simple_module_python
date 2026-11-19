"""Predicates for registered scopes, shared by Core traversal and ORM filtering."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from simple_module_db._builtin_scopes import tenant_scope
from simple_module_db._core_joins import _base_name
from simple_module_db.insert_guard import TENANT_COLUMN, statement_values
from simple_module_db.scopes import ResolvedScope, ScopeIsolationError
from simple_module_db.tenancy import TenantIsolationError


def scoped_names(scopes: list[ResolvedScope]) -> set[str]:
    return set().union(*(s.scope._table_names for s in scopes))


def orm_covered(scopes: list[ResolvedScope]) -> set[type]:
    """A join is ORM-covered only when every applicable scope has a context."""
    covered: set[type] = set()
    missing: set[type] = set()
    for resolved in scopes:
        (covered if resolved.value is not None else missing).update(resolved.scope._classes)
    return covered - missing


def subquery_predicates(scopes: list[ResolvedScope]) -> Callable[[Any], list[Any]]:
    def predicates_for(from_obj: Any) -> list[Any]:
        name = _base_name(from_obj)
        preds = []
        for resolved in scopes:
            if name not in resolved.scope._table_names:
                continue
            if resolved.required:
                raise resolved.scope.missing_error(name, "SELECT")
            if not resolved.active:
                continue
            preds.append(resolved.predicate(from_obj.c))
        return preds

    return predicates_for


def nested_dml_guard(scopes: list[ResolvedScope]) -> Callable[[Any], list[Any]]:
    """A nested DML never reaches do_orm_execute; guard its target here."""

    def check(stmt: Any) -> list[Any]:
        name = _base_name(stmt.table)
        op = stmt.__visit_name__.upper()
        preds = []
        for resolved in scopes:
            scope = resolved.scope
            if scope.reads_only or name not in scope._table_names:
                continue
            if not resolved.active and scope is not tenant_scope:
                continue
            if op == "INSERT":
                error = TenantIsolationError if scope is tenant_scope else ScopeIsolationError
                raise error(
                    f"INSERT into {scope.name}-scoped '{name}' inside another statement is not "
                    f"{scope.name}-scoped; run it as a statement of its own"
                )
            if resolved.required:
                raise scope.missing_error(name, op)
            if not resolved.active:
                continue
            column = TENANT_COLUMN if scope is tenant_scope else scope.column
            if op == "UPDATE" and column and column in statement_values(stmt):
                error = TenantIsolationError if scope is tenant_scope else ScopeIsolationError
                raise error(f"Cannot change {column} of existing rows")
            preds.append(resolved.predicate(stmt.table.c))
        return preds

    return check


__all__ = ["nested_dml_guard", "orm_covered", "scoped_names", "subquery_predicates"]
