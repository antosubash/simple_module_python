"""Tables an ORM entity outer-joins in, whose criteria already sit in ``ON`` (#417).

``select(Parent, func.count(Child.id)).outerjoin(Child, ...)``: the column
wrapped in ``func.count`` strips the ORM annotation, so ``columns_clause_froms``
lists a bare ``Table child``. ``_plain_tables`` took that for a Core
``Model.__table__`` reference and added ``WHERE child.tenant_id = :t``, which
is false for every row the outer join padded with NULLs — the LEFT JOIN became
an inner one and parents without children vanished.

Excluding such a table from the ``WHERE`` is only safe when something else
filters it. That holds for exactly one shape: the join target is a plain ORM
entity (``.outerjoin(Child, ...)``) whose class carries the loader criteria,
because ``with_loader_criteria`` renders them into the join's ``ON``. So:

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

from sqlalchemy.orm import Mapper


def _plain(element: Any) -> Any:
    deannotate = getattr(element, "_deannotate", None)
    return deannotate() if deannotate is not None else element


def orm_outer_join_tables(stmt: Any, covered: set[type] | frozenset[type]) -> list[Any]:
    """Un-annotated tables of ORM entities ``stmt`` outer- or full-joins in.

    Only entities whose class is in ``covered`` count: those are the ones the
    filter gives ``with_loader_criteria``, which is what puts their predicate
    in ``ON``. Compare the result by identity against FROM candidates.
    """
    tables: list[Any] = []
    for entry in getattr(stmt, "_setup_joins", ()):
        # SQLAlchemy 2.0: (target, onclause, from_, {"isouter": .., "full": ..})
        target, flags = entry[0], entry[-1]
        if not isinstance(flags, dict) or not (flags.get("isouter") or flags.get("full")):
            continue
        mapper = getattr(target, "_annotations", {}).get("parententity")
        if not isinstance(mapper, Mapper) or mapper.class_ not in covered:
            continue
        table = _plain(target)
        if table is mapper.local_table and mapper.persist_selectable is mapper.local_table:
            tables.append(table)
    return tables


def is_excluded(from_obj: Any, excluded: list[Any]) -> bool:
    plain = _plain(from_obj)
    return any(plain is t for t in excluded)
