"""Scope what an INSERT reads: its SELECT source and the subqueries in its values.

``insert(...).from_select(..., select(...))`` reads like any SELECT, and so
does a subquery placed in ``.values()`` (single or multi-row) or in an
``ON CONFLICT DO UPDATE`` arm's ``set_`` / ``where``. Those subqueries are
scoped whatever the insert's target is — an untenanted table is no less a
place another tenant's data could be copied to.

The values of an insert sit outside the reach of loader criteria, so an ORM
subquery there is deannotated first and scoped as a Core one: every tenant /
soft-deletable table it reads gets its predicates (or, strict with no
tenant, raises).
"""

from __future__ import annotations

from collections.abc import Callable
from copy import copy
from typing import Any

from sqlalchemy.dialects.postgresql.dml import OnConflictDoUpdate as PgConflictUpdate
from sqlalchemy.dialects.sqlite.dml import OnConflictDoUpdate as SqliteConflictUpdate
from sqlalchemy.sql import visitors
from sqlalchemy.sql.annotation import _deep_deannotate
from sqlalchemy.sql.elements import BindParameter, ClauseElement
from sqlalchemy.util import immutabledict

Scope = Callable[[Any], Any]

_READS = frozenset({"select", "compound_select", "insert", "update", "delete"})


def _reads_rows(value: Any) -> bool:
    """``value`` holds a statement of its own (a scalar subquery, ``exists()``…)."""
    if not isinstance(value, ClauseElement) or isinstance(value, BindParameter):
        return False
    return any(el.__visit_name__ in _READS for el in visitors.iterate(value))


def _expr(value: Any, scope: Scope) -> Any:
    if not _reads_rows(value):
        return value
    plain = _deep_deannotate(value)
    scoped = scope(plain)
    return value if scoped is plain else scoped


def _row(row: Any, scope: Scope) -> Any:
    if isinstance(row, dict):
        return {k: _expr(v, scope) for k, v in row.items()}
    return type(row)(_expr(v, scope) for v in row)


def _arm(arm: Any, scope: Scope) -> Any:
    if not isinstance(arm, (PgConflictUpdate, SqliteConflictUpdate)):
        return arm
    values = [(k, _expr(v, scope)) for k, v in arm.update_values_to_set]
    where = arm.update_whereclause
    scoped_where = None if where is None else _expr(where, scope)
    unchanged = all(a[1] is b[1] for a, b in zip(values, arm.update_values_to_set, strict=True))
    if unchanged and scoped_where is where:
        return arm
    out = copy(arm)  # no generative setter for an existing conflict arm
    out.update_values_to_set = values
    out.update_whereclause = scoped_where
    return out


def scope_insert(stmt: Any, scope: Scope) -> Any:
    """``stmt`` with its SELECT source and its value subqueries scoped by ``scope``."""
    if getattr(stmt, "select", None) is not None:
        stmt = scope(stmt)
    values = stmt._values
    multi = stmt._multi_values
    arm = getattr(stmt, "_post_values_clause", None)
    new_values = {k: _expr(v, scope) for k, v in values.items()} if values else values
    new_multi = tuple([_row(r, scope) for r in group] for group in multi) if multi else multi
    new_arm = _arm(arm, scope)
    values_same = not values or all(new_values[k] is v for k, v in values.items())
    multi_same = not multi or all(
        _same_row(a, b)
        for ga, gb in zip(new_multi, multi, strict=True)
        for a, b in zip(ga, gb, strict=True)
    )
    if values_same and multi_same and new_arm is arm:
        return stmt
    out = stmt._generate()
    out._values = immutabledict(new_values) if new_values else new_values
    out._multi_values = new_multi
    if new_arm is not arm:
        out._post_values_clause = new_arm
    return out


def _same_row(a: Any, b: Any) -> bool:
    pairs = (
        zip(a.values(), b.values(), strict=True) if isinstance(a, dict) else zip(a, b, strict=True)
    )
    return all(x is y for x, y in pairs)


__all__ = ["scope_insert"]
