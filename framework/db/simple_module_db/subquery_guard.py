"""Scope a bare Core ``exists().where(...)`` — the one shape loader criteria miss.

``select(Model.id).where(...).exists()`` is ORM-compiled and gets the tenant
and soft-delete criteria like any other statement. ``exists().where(Model.x
== ...)`` is not: its inner SELECT has no entity in its columns, so SQLAlchemy
never applies loader criteria to it (#332).

The check is cheap and runs on every filtered statement: a walk of the WHERE,
column and HAVING clauses looking for an ``Exists``. Only when one is found is
the statement rewritten — every nested SELECT reading a tenant or soft-delete
table gains the matching predicates. Duplicates of loader criteria are
harmless.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.sql import visitors
from sqlalchemy.sql.selectable import Exists, Select

Predicates = Callable[[Any], list[Any]]


def _has_exists(stmt: Any) -> bool:
    roots = [
        *getattr(stmt, "_where_criteria", ()),
        *getattr(stmt, "_raw_columns", ()),
        *getattr(stmt, "_having_criteria", ()),
    ]
    return any(isinstance(el, Exists) for root in roots for el in visitors.iterate(root))


def scope_exists_subqueries(stmt: Any, predicates_for: Predicates) -> Any:
    """Return ``stmt`` with nested SELECTs scoped, or ``stmt`` unchanged."""
    if not _has_exists(stmt):
        return stmt

    def replace(element: Any) -> Any:
        if element is stmt or not isinstance(element, Select):
            return None
        preds = [p for from_obj in element.get_final_froms() for p in predicates_for(from_obj)]
        return element.where(*preds) if preds else None

    return visitors.replacement_traverse(stmt, {}, replace)


__all__ = ["scope_exists_subqueries"]
