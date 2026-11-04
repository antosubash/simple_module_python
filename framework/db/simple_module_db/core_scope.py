"""Tenant / soft-delete predicates for Core references, at every depth (#332, #506).

ORM entities are scoped by ``with_loader_criteria``. A plain ``Model.__table__``
(or ``table.alias()``) is not, wherever it sits: the top-level SELECT, a
join, a subquery, a CTE, a scalar or ``exists()`` subquery (also one inside
a join's ``ON``), a member of a UNION / INTERSECT / EXCEPT, the extra FROM
of an UPDATE / DELETE, or the SELECT feeding an ``INSERT ... FROM SELECT``.

One cheap walk (``_core_walk``) decides whether the statement holds any such reference; ORM
statements usually do not and are returned untouched. Otherwise the
statement is cloned once (``cloned_traverse``, a single clone map, so a
correlated subquery keeps pointing at the same outer FROM) and every SELECT
in it, innermost first, gets:

* its Core joins scoped (``_core_joins``: ``ON`` for nullable sides);
* ``WHERE`` predicates for every other plain table it reads — from its
  columns, its FROM list and its ``WHERE`` clause.

An UPDATE / DELETE gets ``WHERE`` predicates for the tables its ``WHERE``
and its ``SET`` values join in. The target of the statement itself is
scoped by the caller; the target of a DML *nested* in it (an
``update(...).cte()`` read by a SELECT) is handed to ``nested``, which
returns that DML's own predicates or refuses it. Under strict mode with no
tenant bound, ``predicates_for`` raises: every Core reference fails closed.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.sql import visitors

from simple_module_db._core_joins import Predicates, is_plain_leaf, same_from, scope_joins
from simple_module_db._core_walk import froms_read, references_plain
from simple_module_db._outer_joins import is_excluded, orm_outer_join_tables


def _executable_options(stmt: Any) -> list[Any]:
    """ORM options anywhere in ``stmt``: shared as they are, never cloned."""
    return [o for el in visitors.iterate(stmt) for o in getattr(el, "_with_options", ())]


def _add_where(stmt: Any, preds: list[Any]) -> None:
    if preds:  # ``stmt`` is this traversal's own clone: mutating it is safe
        stmt._where_criteria = (*stmt._where_criteria, *preds)


class _Visitor:
    def __init__(self, predicates_for: Predicates, orm_covered: Any) -> None:
        self.predicates_for = predicates_for
        self.orm_covered = orm_covered
        self.dml: list[Any] = []

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
        candidates = [f for f in froms_read(stmt) if not (outer and is_excluded(f, outer))]
        _add_where(stmt, [*joined.where, *self._preds(candidates, joined.covered)])

    def update_delete(self, stmt: Any) -> None:
        """The tables an UPDATE / DELETE joins in through its ``WHERE`` or ``SET``."""
        _add_where(stmt, self._preds(froms_read(stmt), []))
        self.dml.append(stmt)

    def insert(self, stmt: Any) -> None:
        self.dml.append(stmt)


def scope_core(
    stmt: Any,
    predicates_for: Predicates,
    names: set[str],
    orm_covered: Any = None,
    nested: Predicates | None = None,
) -> Any:
    """Return ``stmt`` with every plain scoped table filtered, or ``stmt`` itself.

    ``names`` are the scoped table names. ``orm_covered`` are the classes the
    caller gives loader criteria (for the #417 exclusion), or ``None``.
    ``nested`` gives the predicates for the target of a DML embedded in
    ``stmt`` (or raises); ``stmt``'s own target is the caller's.
    """
    if not names or not references_plain(stmt, names):
        return stmt
    visitor = _Visitor(predicates_for, orm_covered)
    out = visitors.cloned_traverse(
        stmt,
        {"stop_on": _executable_options(stmt)},
        {
            "select": visitor.select,
            "update": visitor.update_delete,
            "delete": visitor.update_delete,
            "insert": visitor.insert,
        },
    )
    if nested is not None:
        # The traversal is post-order: the root is reached last, so it is
        # only known now. The nested clones are this traversal's own.
        for dml in visitor.dml:
            if dml is not out:
                preds = nested(dml)
                if dml.__visit_name__ != "insert":
                    _add_where(dml, preds)
    return out


__all__ = ["scope_core"]
