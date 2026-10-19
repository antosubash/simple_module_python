"""Tenant / soft-delete criteria for Core joins over ``Model.__table__`` (#506).

ORM joins get their criteria from ``with_loader_criteria``, which renders into
each join's ``ON``. A Core join — ``tag.outerjoin(link, ...)`` in
``select_from``, or ``select(...).outerjoin(link, ...)`` on a raw table — has
no loader criteria, and a ``WHERE`` on its nullable side would turn the outer
join into an inner one. So this module rewrites the joins themselves:

* a LEFT join's nullable (right) side gets its predicates in ``ON``, which
  filters it exactly;
* a FULL join preserves both sides, and ``ON`` never removes a preserved row,
  so both sides' predicates go in ``ON`` *and* each side owes
  ``pred OR <side padded>`` (its primary key ``IS NULL``) to whatever encloses
  the join — that drops another tenant's (or a trashed) row coming back
  unmatched while keeping the NULL padding the join adds;
* an INNER join's sides, and a LEFT join's preserved side, owe their
  predicates to the enclosing join's ``ON`` — or, at the top, to ``WHERE``.

The FULL-join form is exact, not merely safe: a row survives only if every
side that is present passed its own predicates, which is what pre-filtering
both inputs would give, without wrapping the tables in subqueries (which
would break every column reference to them).

Every plain leaf inside a join is reported back, so the caller does not also
``WHERE``-filter it through the columns clause. ORM-annotated leaves are left
to their loader criteria. ``core_scope`` calls this for each SELECT in a
statement, nested ones included.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.sql.selectable import Alias, FromGrouping, Join, Select, TableClause

Predicates = Callable[[Any], list[Any]]


def _base_name(from_obj: Any) -> str | None:
    while isinstance(from_obj, Alias):  # ``table.alias().alias()`` nests
        from_obj = from_obj.element
    return getattr(from_obj, "name", None)


def _is_orm(el: Any) -> bool:
    return "parententity" in getattr(el, "_annotations", {})


def is_plain_leaf(node: Any) -> bool:
    """A Core table or alias of one — not an ORM-annotated occurrence."""
    if _is_orm(node):
        return False
    base = node
    while isinstance(base, Alias):
        base = base.element
    return isinstance(base, TableClause)


def _padded(leaf: Any) -> Any | None:
    """``leaf``'s row is the NULL padding of an outer join: its primary key is NULL."""
    pk = list(leaf.primary_key)
    return and_(*(c.is_(None) for c in pk)) if pk else None


class _Scoper:
    def __init__(self, predicates_for: Predicates) -> None:
        self.predicates_for = predicates_for
        self.covered: list[Any] = []

    def scope(self, node: Any) -> tuple[Any, list[Any]]:
        """``node`` with its joins scoped, and the predicates its rows still owe."""
        if isinstance(node, Join):
            return self._join(node)
        if isinstance(node, FromGrouping):  # a join nested as another join's side
            inner, owed = self.scope(node.element)
            return (node if inner is node.element else FromGrouping(inner)), owed
        if not is_plain_leaf(node):
            return node, []
        preds = self.predicates_for(node)
        if preds:
            self.covered.append(node)
        return node, [(node, preds)] if preds else []

    def _join(self, node: Join) -> tuple[Any, list[Any]]:
        left, owed_left = self.scope(node.left)
        right, owed_right = self.scope(node.right)
        if not node.isouter:
            on, owed = [], owed_left + owed_right
        elif node.full:
            on, owed = owed_left + owed_right, [_or_padded(o) for o in owed_left + owed_right]
        else:
            on, owed = owed_right, owed_left
        if not on and left is node.left and right is node.right:
            return node, owed
        onclause = and_(node.onclause, *_flatten(on)) if on else node.onclause
        return Join(left, right, onclause, isouter=node.isouter, full=node.full), owed


def _or_padded(owed: tuple[Any, list[Any]]) -> tuple[Any, list[Any]]:
    leaf, preds = owed
    padded = _padded(leaf)
    # No primary key to tell padding apart: keep the plain predicates, which
    # over-filter (drop the padded rows) but never leak.
    return (leaf, preds) if padded is None else (leaf, [or_(and_(*preds), padded)])


def _flatten(owed: list[tuple[Any, list[Any]]]) -> list[Any]:
    return [p for _leaf, preds in owed for p in preds]


class JoinScope:
    """What scoping one SELECT's joins produced, for the caller to install."""

    def __init__(self, from_obj: tuple, setup_joins: tuple, where: list, covered: list) -> None:
        self.from_obj = from_obj
        self.setup_joins = setup_joins
        self.where = where
        self.covered = covered


def scope_joins(stmt: Select, predicates_for: Predicates) -> JoinScope:
    """Scope ``stmt``'s Core joins: its ``FROM`` joins and ``.join()`` steps.

    ``covered`` lists every plain leaf filtered here — in ``ON`` or through
    ``where`` — which must not get another ``WHERE`` predicate from the
    caller: on a nullable side it would make the outer join inner.
    ``predicates_for`` raises under strict mode with no tenant bound, so a
    Core join fails closed like everything else.
    """
    scoper = _Scoper(predicates_for)
    where: list[Any] = []
    froms: list[Any] = []
    for from_obj in stmt._from_obj:
        if isinstance(from_obj, Join):
            from_obj, owed = scoper.scope(from_obj)
            where.extend(_flatten(owed))
        froms.append(from_obj)
    joins = [_scope_setup_join(entry, scoper, where) for entry in stmt._setup_joins]
    return JoinScope(tuple(froms), tuple(joins), where, scoper.covered)


def _scope_setup_join(entry: tuple, scoper: _Scoper, where: list[Any]) -> tuple:
    """One ``select(...).join(target, onclause)`` step over a Core target.

    The left side is the FROM built so far, already filtered by its own
    predicates; only the target is scoped here. Without an explicit
    ``onclause`` there is no ``ON`` to extend, so an outer target's
    predicates fall back to ``WHERE`` (over-filters, never leaks).
    """
    target, onclause, from_, flags = entry
    target, owed = scoper.scope(target)
    outer = bool(flags.get("isouter")) or bool(flags.get("full"))
    if not owed:
        return (target, onclause, from_, flags)
    if not outer or onclause is None:
        where.extend(_flatten(owed))
        return (target, onclause, from_, flags)
    onclause = and_(onclause, *_flatten(owed))
    if flags.get("full"):
        where.extend(_flatten([_or_padded(o) for o in owed]))
    return (target, onclause, from_, flags)
