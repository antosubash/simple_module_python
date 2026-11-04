"""``aliased(Model, <subquery, CTE, join or text>)`` entities in a statement (#816).

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
  rows it returns — allowed; so is a ``Join`` of the entity's own table with
  tables that are not scoped;
* any other selectable that reads a tenant-scoped or soft-deletable table
  through Core (``select(Model.__table__)``, a nested ``select(t.c.x)``, a
  join) is refused with ``TenantIsolationError``. Built from ORM entities
  (``select(Model)``) it is scoped by the loader criteria and runs;
* SQL text (``text().columns()``, bare or as a subquery / CTE) under an
  entity of a scoped table is refused: no filter can read what it selects.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.sql import visitors
from sqlalchemy.sql.elements import FunctionFilter, Over, WithinGroup
from sqlalchemy.sql.functions import FunctionElement
from sqlalchemy.sql.selectable import (
    Alias,
    CompoundSelect,
    FromClause,
    FromGrouping,
    Join,
    Select,
)

from simple_module_db._core_joins import _base_name, _is_orm, is_plain_leaf, is_scoped_leaf
from simple_module_db._core_walk import (
    aliased_selectable,
    froms_read,
    is_textual,
    reads_text_as_scoped,
    references_plain,
)
from simple_module_db.tenancy import TenantIsolationError

AliasedGuard = Callable[[Any, Any, set[str]], None]

# Aggregates combine rows even without a GROUP BY: ``max(id)`` over every tenant's
# rows next to ``min(tenant_id)``. Names, since ``func.<name>`` builds a plain
# ``Function`` for any name SQLAlchemy has no class for.
_AGGREGATES = frozenset(
    {
        "aggregate_strings", "array_agg", "avg", "bit_and", "bit_or", "bool_and",
        "bool_or", "count", "every", "group_concat", "json_agg", "json_group_array",
        "json_group_object", "json_object_agg", "jsonb_agg", "jsonb_object_agg",
        "max", "min", "mode", "percentile_cont", "percentile_disc", "stddev",
        "stddev_pop", "stddev_samp", "string_agg", "sum", "total", "var_pop",
        "var_samp", "variance", "xmlagg",
    }
)  # fmt: skip


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
        self.keep = [sel for _insp, sel in self.entities.values()]
        if self.entities:
            self.keep += [el for el in annotated if id(el._deannotate()) in self.entities]
        self.opaque = frozenset(self.entities)


def check_entities(parts: StatementParts, names: set[str], guard: AliasedGuard | None) -> None:
    if guard is None:
        return
    for insp, selectable in parts.entities.values():
        if references_plain(selectable, names) or reads_text_as_scoped(insp, selectable, names):
            guard(insp, selectable, names)


def refuse_aliased_core(insp: Any, selectable: Any, names: set[str]) -> None:
    """The guard for statements a caller wrote (not relationship loads)."""
    entity = insp.mapper.class_.__name__
    if is_textual(selectable):
        raise TenantIsolationError(
            f"aliased({entity}) over SQL text is not tenant-scoped: the filter cannot read "
            "what the text selects; build the selectable from ORM entities (select(Model)) "
            "or run it under all_tenants() (with include_deleted=True for trashed rows)"
        )
    if _own_rows_only(insp, selectable, names):
        return
    leaves = (el for el in visitors.iterate(selectable) if is_scoped_leaf(el, names))
    tables = sorted({str(_base_name(el)) for el in leaves})
    raise TenantIsolationError(
        f"aliased({entity}) over a selectable that reads "
        f"{', '.join(repr(t) for t in tables) or 'a scoped table'} through Core is not "
        "tenant-scoped; build the selectable from ORM entities (select(Model)) or run "
        "it under all_tenants() (with include_deleted=True for trashed rows)"
    )


def _own_rows_only(insp: Any, selectable: Any, names: set[str]) -> bool:
    """``aliased(Doc, select(doc).where(doc.c.x == ...).subquery())``: one SELECT, own table.

    No join, no grouping, aggregate or window function, no other scoped
    table, and no nested SELECT reading one — so every row it returns is a
    row of the entity's table, and the entity's loader criteria, applied to
    the alias, filter exactly those rows.
    """
    if isinstance(selectable, Join):
        return _own_join_only(insp, selectable, names)
    inner = selectable.element
    if not isinstance(inner, Select) or inner._setup_joins:
        return False
    if any(isinstance(f, Join) for f in inner._from_obj):
        return False
    # Grouping, aggregates and window functions combine rows *before* the entity's
    # criteria filter the result, so a row of this tenant could carry other tenants' data.
    if inner._group_by_clauses or inner._having_criteria or _combines_rows(inner):
        return False
    own = insp.mapper.local_table
    if any(is_scoped_leaf(f, names) and f is not own for f in froms_read(inner)):
        return False
    return not any(
        el is not inner and isinstance(el, (Select, CompoundSelect)) and references_plain(el, names)
        for el in visitors.iterate(inner)
    )


def _own_join_only(insp: Any, join: Join, names: set[str]) -> bool:
    """``aliased(Doc, doc.join(tag))``: the entity's own table(s) joined to unscoped tables.

    Every row carries one row of the entity's tables, which its loader
    criteria filter. The entity's tables are those of its mapper (and of a
    ``with_polymorphic`` entity's mappers), so the flat alias the ORM builds
    for joined inheritance counts too. Each may appear once: a second copy of
    one, any other scoped table, a subquery or text on a side, or an ``ON``
    clause with a nested SELECT reading a scoped table through Core is not
    covered.
    """
    own = {t for m in (insp.mapper, *insp.with_polymorphic_mappers) for t in m.tables}
    met: set[Any] = set()
    stack: list[Any] = [join]
    while stack:
        node = stack.pop()
        if isinstance(node, FromGrouping):
            stack.append(node.element)
        elif isinstance(node, Join):
            stack.extend((node.left, node.right))
            nested = (
                el
                for el in visitors.iterate(node.onclause)
                if isinstance(el, (Select, CompoundSelect))
            )
            if any(references_plain(el, names) for el in nested):
                return False
        elif not is_plain_leaf(node):
            return False
        elif is_scoped_leaf(node, names):
            base = _table_of_leaf(node)
            if base not in own or base in met:
                return False
            met.add(base)
    return True


def _table_of_leaf(node: Any) -> Any:
    while isinstance(node, Alias):
        node = node.element
    return node


def _combines_rows(inner: Select) -> bool:
    """An aggregate or window function in ``inner`` itself (a nested SELECT is its own)."""
    stack = list(inner.get_children())
    while stack:
        el = stack.pop()
        if isinstance(el, (Select, CompoundSelect)):
            continue
        if isinstance(el, (Over, WithinGroup, FunctionFilter)):
            return True
        if isinstance(el, FunctionElement) and str(getattr(el, "name", "")).lower() in _AGGREGATES:
            return True
        stack.extend(el.get_children())
    return False


__all__ = ["AliasedGuard", "StatementParts", "check_entities", "refuse_aliased_core"]
