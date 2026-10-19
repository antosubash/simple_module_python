"""Tenant / soft-delete predicates for Core references, at every depth (#332, #506).

ORM entities are scoped by ``with_loader_criteria``. A plain ``Model.__table__``
(or ``table.alias()``) is not, wherever it sits: the top-level SELECT, a
join, a subquery, a CTE, a scalar or ``exists()`` subquery (also one inside
a join's ``ON``), a member of a UNION / INTERSECT / EXCEPT, the extra FROM
of an UPDATE / DELETE, or the SELECT feeding an ``INSERT ... FROM SELECT``.

One cheap walk decides whether the statement holds any such reference; ORM
statements usually do not and are returned untouched. Otherwise the
statement is cloned once (``cloned_traverse``, a single clone map, so a
correlated subquery keeps pointing at the same outer FROM) and every SELECT
in it, innermost first, gets:

* its Core joins scoped (``_core_joins``: ``ON`` for nullable sides);
* ``WHERE`` predicates for every other plain table it reads — from its
  columns, its FROM list and its ``WHERE`` clause.

An UPDATE / DELETE gets ``WHERE`` predicates for the tables its ``WHERE``
joins in; its target is scoped by the caller. Under strict mode with no
tenant bound, ``predicates_for`` raises: every Core reference fails closed.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.sql import visitors
from sqlalchemy.sql.selectable import Alias, Join, Select, TableClause
from sqlalchemy.sql.visitors import HasTraverseInternals

from simple_module_db._core_joins import (
    Predicates,
    _base_name,
    _is_orm,
    is_plain_leaf,
    same_from,
    scope_joins,
)
from simple_module_db._outer_joins import is_excluded, orm_outer_join_tables


def _orm_less(stmt: Any) -> bool:
    """A SELECT naming no ORM entity in its columns, FROM list or joins.

    Loader criteria have nothing to attach to there — ``exists().where(
    Doc.x == ...)`` — so the tables its ``WHERE`` reads must be scoped like
    Core ones. In an ORM select those tables are the entities' own.
    """
    targets = [entry[0] for entry in stmt._setup_joins]
    return not any(_is_orm(el) for el in (*stmt._raw_columns, *stmt._from_obj, *targets))


def _froms_read(stmt: Any) -> list[Any]:
    """The FROMs a SELECT reads besides its joins, and the extra FROMs of a DML."""
    if not isinstance(stmt, Select):
        target = stmt.table._deannotate()
        return [f for f in _where_froms(stmt) if f is not target]
    froms = [*stmt.columns_clause_froms, *(f for f in stmt._from_obj if not isinstance(f, Join))]
    return [*froms, *_where_froms(stmt)] if _orm_less(stmt) else froms


def _references_plain(stmt: Any, names: set[str]) -> bool:
    """Whether ``stmt`` reads a scoped table outside the ORM's annotations.

    ORM-annotated elements are not descended into: their tables are the
    loader criteria's business, and every ORM column leads to a plain table.
    """
    stack = [stmt]
    while stack:
        el = stack.pop()
        if _is_orm(el):
            continue
        target = el if isinstance(el, (TableClause, Alias)) else getattr(el, "table", None)
        if (
            isinstance(target, (TableClause, Alias))
            and is_plain_leaf(target)
            and _base_name(target) in names
        ):
            return True
        stack.extend(_children(el))
    return False


def _children(el: Any) -> list[Any]:
    # ``Select.get_children`` adds every FROM it derives from the columns and
    # WHERE, deannotated, so every ORM statement would look Core. Its declared
    # internals plus the FROMs ``_froms_read`` would scope are what counts.
    if isinstance(el, Select):
        omit = ("_correlate", "_correlate_except")
        return [*HasTraverseInternals.get_children(el, omit_attrs=omit), *_froms_read(el)]
    if el.__visit_name__ in ("update", "delete"):
        return [*el.get_children(), *_froms_read(el)]
    return list(el.get_children())


def _executable_options(stmt: Any) -> list[Any]:
    """ORM options anywhere in ``stmt``: shared as they are, never cloned."""
    return [o for el in visitors.iterate(stmt) for o in getattr(el, "_with_options", ())]


def _where_froms(stmt: Any) -> list[Any]:
    return [f for crit in stmt._where_criteria for f in crit._from_objects]


def _add_where(stmt: Any, preds: list[Any]) -> None:
    if preds:  # ``stmt`` is this traversal's own clone: mutating it is safe
        stmt._where_criteria = (*stmt._where_criteria, *preds)


class _Visitor:
    def __init__(self, predicates_for: Predicates, orm_covered: Any) -> None:
        self.predicates_for = predicates_for
        self.orm_covered = orm_covered

    def _preds(self, candidates: list[Any], skip: list[Any]) -> list[Any]:
        preds: list[Any] = []
        seen: list[Any] = list(skip)
        for from_obj in candidates:
            if not is_plain_leaf(from_obj) or any(same_from(from_obj, s) for s in seen):
                continue
            seen.append(from_obj)
            preds.extend(self.predicates_for(from_obj))
        return preds

    def select(self, stmt: Any) -> None:
        joined = scope_joins(stmt, self.predicates_for)
        if joined.covered:
            stmt._from_obj, stmt._setup_joins = joined.from_obj, joined.setup_joins
        # A bare table an ORM entity LEFT-joins in is filtered by that
        # join's ON; a WHERE on it would make the join inner (#417).
        outer = orm_outer_join_tables(stmt, self.orm_covered) if self.orm_covered else []
        candidates = [f for f in _froms_read(stmt) if not (outer and is_excluded(f, outer))]
        _add_where(stmt, [*joined.where, *self._preds(candidates, joined.covered)])

    def dml(self, stmt: Any) -> None:
        """The tables an UPDATE / DELETE joins in through its ``WHERE``."""
        _add_where(stmt, self._preds(_froms_read(stmt), []))


def scope_core(
    stmt: Any, predicates_for: Predicates, names: set[str], orm_covered: Any = None
) -> Any:
    """Return ``stmt`` with every plain scoped table filtered, or ``stmt`` itself.

    ``names`` are the scoped table names. ``orm_covered`` are the classes the
    caller gives loader criteria (for the #417 exclusion), or ``None``.
    """
    if not names or not _references_plain(stmt, names):
        return stmt
    visitor = _Visitor(predicates_for, orm_covered)
    return visitors.cloned_traverse(
        stmt,
        {"stop_on": _executable_options(stmt)},
        {"select": visitor.select, "update": visitor.dml, "delete": visitor.dml},
    )


__all__ = ["scope_core"]
