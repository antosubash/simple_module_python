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

from sqlalchemy import and_, exc, or_
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
        onclause = and_(node.onclause, *_flatten(on)) if on else node.onclause  # ty: ignore[invalid-argument-type]
        return Join(left, right, onclause, isouter=node.isouter, full=node.full), owed


def _or_padded(owed: tuple) -> tuple:
    """``owed`` as ``pred OR <leaf padded>``: tagged with a third item so it is padded once."""
    if len(owed) == 3:
        return owed
    leaf, preds = owed
    padded = _padded(leaf)
    # No primary key to tell padding apart: keep the plain predicates, which
    # over-filter (drop the padded rows) but never leak.
    return (leaf, preds) if padded is None else (leaf, [or_(and_(*preds), padded)], True)


def _flatten(owed: list[tuple]) -> list[Any]:
    return [p for _leaf, preds, *_ in owed for p in preds]


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

    Once any ``.join()`` step is FULL, every ``WHERE`` predicate owed here
    takes the padded form ``pred OR <pk> IS NULL``. That is never a leak —
    a primary key is NULL only on a row an outer join padded, which carries
    nothing of that table — and it is what keeps the FULL join's left side
    from being filtered down to a RIGHT join.
    """
    scoper = _Scoper(predicates_for)
    owed: list[tuple] = []
    froms: list[Any] = []
    for from_obj in stmt._from_obj:
        if isinstance(from_obj, Join):
            from_obj, more = scoper.scope(from_obj)
            owed.extend(more)
        froms.append(from_obj)
    joins = [_scope_setup_join(stmt, i, scoper, owed) for i in range(len(stmt._setup_joins))]
    if any(entry[3].get("full") for entry in stmt._setup_joins):
        owed = [_or_padded(o) for o in owed]
    return JoinScope(tuple(froms), tuple(joins), _flatten(owed), scoper.covered)


def _scope_setup_join(stmt: Select, index: int, scoper: _Scoper, owed: list[tuple]) -> tuple:
    """One ``select(...).join(target, onclause)`` step over a Core target.

    The target is scoped like a ``Join``'s right side. A FULL step also
    preserves its left side — the FROM built so far — so that side's plain
    leaves get their (padded) predicates in this ``ON`` and owe the padded
    form to ``WHERE``. Without an explicit ``onclause`` the one SQLAlchemy
    infers is used; if it cannot be resolved, predicates fall back to plain
    ``WHERE`` (over-filters, never leaks).
    """
    entry = stmt._setup_joins[index]
    target, onclause, from_, flags = entry
    full = bool(flags.get("full"))
    outer = full or bool(flags.get("isouter"))
    target, target_owed = scoper.scope(target)
    resolved = None
    if full or (outer and onclause is None and target_owed):
        resolved = _resolved_join(stmt, index)
    left_owed = _left_owed(resolved.left, scoper, owed) if full and resolved is not None else []
    if not target_owed and not left_owed:
        return (target, onclause, from_, flags)
    if onclause is None and resolved is not None:
        onclause = resolved.onclause
    if not outer or onclause is None:
        owed.extend(target_owed)
        return (target, onclause, from_, flags)
    on = [*target_owed, *(_or_padded(o) for o in left_owed)]
    if full:
        owed.extend(target_owed)
    return (target, and_(onclause, *_flatten(on)), from_, flags)  # ty: ignore[invalid-argument-type]


def _resolved_join(stmt: Select, index: int) -> Join | None:
    """The ``Join`` SQLAlchemy builds for setup join ``index``: its left side and ``ON``."""
    target = stmt._setup_joins[index][0]
    probe = stmt._generate()
    probe._setup_joins = stmt._setup_joins[: index + 1]
    try:
        froms = probe.get_final_froms()
    except exc.SQLAlchemyError:
        return None
    stack = list(froms)
    while stack:
        node = stack.pop()
        if isinstance(node, FromGrouping):
            stack.append(node.element)
        elif isinstance(node, Join):
            if node.right is target or getattr(node.right, "element", None) is target:
                return node
            stack.extend((node.left, node.right))
    return None


def _left_owed(left: Any, scoper: _Scoper, owed: list[tuple]) -> list[tuple]:
    """What the plain leaves preserved on a FULL step's left side owe.

    A leaf already filtered in an earlier outer join's ``ON`` owes nothing;
    one already owing ``WHERE`` predicates is reported as is; one nobody has
    scoped yet (a columns-clause FROM) is scoped here and joins ``owed``.
    """
    found: list[tuple] = []
    stack = [left]
    while stack:
        node = stack.pop()
        if isinstance(node, FromGrouping):
            stack.append(node.element)
        elif isinstance(node, Join):
            stack.extend((node.left, node.right))
        elif is_plain_leaf(node):
            mine = [o for o in owed if same_from(o[0], node)]
            if mine:
                found.extend(mine)
            elif not any(same_from(node, c) for c in scoper.covered):
                preds = scoper.predicates_for(node)
                if preds:
                    scoper.covered.append(node)
                    owed.append((node, preds))
                    found.append((node, preds))
    return found


def same_from(a: Any, b: Any) -> bool:
    """One FROM occurrence: the same object, or clones of one (an alias the traversal
    copied while a column still points at the original — SQL renders them as one)."""
    return a is b or not a._cloned_set.isdisjoint(b._cloned_set)
