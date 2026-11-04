"""``aliased(Model, <subquery or CTE>)`` entities in a statement (#816).

The ORM renders such an entity from the selectable it was built over, found
through its annotations — not from the statement's FROM list. So
``core_scope`` must not clone one: the clone would be rendered *next to* the
original, under the same name (``subqueryload()`` is built this way).

What the selectable reads is therefore never rewritten. It is either trusted
or refused:

* a relationship loader's statement (``subqueryload``) wraps the parent
  statement, which was scoped when it ran — trusted;
* a selectable that reads only the entity's own table, in its own ``FROM``,
  is covered by the entity's loader criteria (``include_aliases``) on the
  rows it returns — allowed;
* any other selectable that reads a tenant-scoped or soft-deletable table
  through Core (``select(Model.__table__)``, a nested ``select(t.c.x)``, a
  join) is refused with ``TenantIsolationError``. Built from ORM entities
  (``select(Model)``) it is scoped by the loader criteria and runs.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.sql import visitors
from sqlalchemy.sql.selectable import CompoundSelect, FromClause, Join, Select

from simple_module_db._core_joins import _base_name, _is_orm, is_scoped_leaf
from simple_module_db._core_walk import aliased_selectable, froms_read, references_plain
from simple_module_db.tenancy import TenantIsolationError

AliasedGuard = Callable[[Any, Any, set[str]], None]


class StatementParts:
    """One pass over a statement: its ORM options and its aliased-entity selectables."""

    def __init__(self, stmt: Any) -> None:
        self.options: list[Any] = []
        self.entities: dict[int, tuple[Any, Any]] = {}  # id(selectable) -> (insp, selectable)
        annotated: list[Any] = []
        for el in visitors.iterate(stmt):
            self.options.extend(getattr(el, "_with_options", ()))
            if _is_orm(el):
                selectable = aliased_selectable(el)
                if selectable is not None:
                    self.entities.setdefault(
                        id(selectable), (el._annotations["parententity"], selectable)
                    )
                if isinstance(el, FromClause):
                    annotated.append(el)
        # The annotated copies of an entity's selectable (``select_from(P)``)
        # are as much the entity's as the selectable itself.
        self.keep = [sel for _insp, sel in self.entities.values()] + [
            el for el in annotated if id(el._deannotate()) in self.entities
        ]

    @property
    def opaque(self) -> frozenset[int]:
        return frozenset(self.entities)


def check_entities(parts: StatementParts, names: set[str], guard: AliasedGuard | None) -> None:
    if guard is None:
        return
    for insp, selectable in parts.entities.values():
        if references_plain(selectable, names):
            guard(insp, selectable, names)


def refuse_aliased_core(insp: Any, selectable: Any, names: set[str]) -> None:
    """The guard for statements a caller wrote (not relationship loads)."""
    if _own_rows_only(insp, selectable, names):
        return
    tables = sorted({str(_base_name(el)) for el in _scoped_leaves(selectable, names)})
    raise TenantIsolationError(
        f"aliased({insp.mapper.class_.__name__}) over a selectable that reads "
        f"{', '.join(repr(t) for t in tables) or 'a scoped table'} through Core is not "
        "tenant-scoped; build the selectable from ORM entities (select(Model)) or run "
        "it under all_tenants() (with include_deleted=True for trashed rows)"
    )


def _scoped_leaves(selectable: Any, names: set[str]) -> list[Any]:
    return [el for el in visitors.iterate(selectable) if is_scoped_leaf(el, names)]


def _own_rows_only(insp: Any, selectable: Any, names: set[str]) -> bool:
    """``aliased(Doc, select(doc).where(doc.c.x == ...).subquery())``: one SELECT, own table.

    No join, no other scoped table, and no nested SELECT reading one — so
    every row it returns is a row of the entity's table, and the entity's
    loader criteria, applied to the alias, filter exactly those rows.
    """
    inner = selectable.element
    if not isinstance(inner, Select) or inner._setup_joins:
        return False
    if any(isinstance(f, Join) for f in inner._from_obj):
        return False
    own = insp.mapper.local_table
    if any(is_scoped_leaf(f, names) and f is not own for f in froms_read(inner)):
        return False
    return not any(
        el is not inner and isinstance(el, (Select, CompoundSelect)) and references_plain(el, names)
        for el in visitors.iterate(inner)
    )


__all__ = ["AliasedGuard", "StatementParts", "check_entities", "refuse_aliased_core"]
