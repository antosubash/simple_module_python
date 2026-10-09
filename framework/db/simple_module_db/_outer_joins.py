"""Tables an ORM entity LEFT-joins in, whose criteria already sit in ``ON`` (#417).

``select(Parent, func.count(Child.id)).outerjoin(Child, ...)``: the column
wrapped in ``func.count`` strips the ORM annotation, so ``columns_clause_froms``
lists a bare ``Table child``. ``_plain_tables`` took that for a Core
``Model.__table__`` reference and added ``WHERE child.tenant_id = :t``, which
is false for every row the outer join padded with NULLs — the LEFT JOIN became
an inner one and parents without children vanished.

Excluding such a table from the ``WHERE`` is only safe when something else
filters it. That holds for exactly one shape: the target of a LEFT outer join
is a plain ORM entity (``.outerjoin(Child, ...)``) whose class carries the
loader criteria, because ``with_loader_criteria`` renders them into the join's
``ON``, and an ``ON`` predicate fully filters a LEFT join's nullable side.
A relationship path (``.outerjoin(Parent.kids)``, ``.outerjoin(Parent.kids.
of_type(Kid))``) lands on the same ``ON`` and counts as that entity. So:

* a FULL outer join (``full=True``) is deliberately NOT exempted: it preserves
  its right side too, and an ``ON`` predicate never removes a preserved row —
  another tenant's (or a trashed) child that fails ``ON`` still comes back as
  an unmatched row. Only the ``WHERE`` predicate keeps it out (over-filters,
  never leaks);

* a relationship with ``secondary`` keeps the child's ``WHERE``: the child
  sits behind an association table, outside the outer join's own ``ON``;
* a raw ``Model.__table__`` target gets no loader criteria and keeps its
  ``WHERE`` predicate (over-filters, never leaks);
* an ``aliased(Model)`` target is left alone: its name never matches a table
  name, so it was never a ``WHERE`` candidate in the first place;
* a target whose mapper does not map exactly one table (joined inheritance)
  is left alone, conservatively;
* a target whose class is not in ``covered`` (the classes the caller attaches
  loader criteria for) is left alone — no criteria, no ``ON`` predicate.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Mapper, RelationshipProperty


def _plain(element: Any) -> Any:
    deannotate = getattr(element, "_deannotate", None)
    return deannotate() if deannotate is not None else element


def orm_outer_join_tables(stmt: Any, covered: set[type] | frozenset[type]) -> list[Any]:
    """Un-annotated tables of ORM entities ``stmt`` LEFT-outer-joins in (never FULL).

    Only entities whose class is in ``covered`` count: those are the ones the
    filter gives ``with_loader_criteria``, which is what puts their predicate
    in ``ON``. Compare the result by identity against FROM candidates.
    """
    tables: list[Any] = []
    for entry in getattr(stmt, "_setup_joins", ()):
        # SQLAlchemy 2.0: (target, onclause, from_, {"isouter": .., "full": ..})
        target, flags = entry[0], entry[-1]
        # LEFT only: ON cannot filter a FULL join's preserved right side.
        if not isinstance(flags, dict) or not flags.get("isouter") or flags.get("full"):
            continue
        prop = getattr(target, "property", None)
        if isinstance(prop, RelationshipProperty):
            mapper, table = _relationship_target(target, prop)
        else:
            mapper = getattr(target, "_annotations", {}).get("parententity")
            table = _plain(target)
        if not isinstance(mapper, Mapper) or mapper.class_ not in covered:
            continue
        if table is mapper.local_table and mapper.persist_selectable is mapper.local_table:
            tables.append(table)
    return tables


def _relationship_target(attr: Any, prop: RelationshipProperty) -> tuple[Any, Any]:
    """Mapper and table a ``.outerjoin(Parent.kids)`` path lands on, or ``(None, None)``.

    The child's loader criteria render into that join's ``ON`` exactly as for
    an entity target. Two shapes are refused: a ``secondary`` relationship
    (the child sits behind an association table, with no ``ON`` guarantee for
    the outer join itself) and an aliased ``of_type`` (aliases never matched a
    ``WHERE`` candidate anyway).
    """
    if prop.secondary is not None:
        return None, None
    of_type = getattr(attr, "_of_type", None)
    mapper = prop.mapper if of_type is None else of_type
    if not isinstance(mapper, Mapper):  # aliased(Child) is an AliasedInsp
        return None, None
    return mapper, mapper.local_table


def is_excluded(from_obj: Any, excluded: list[Any]) -> bool:
    # Table-object identity on purpose: matching by name would also drop the
    # WHERE on a raw duplicate occurrence (an alias, another FROM) of the table.
    plain = _plain(from_obj)
    return any(plain is t for t in excluded)
