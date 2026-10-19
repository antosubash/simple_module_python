"""The cheap walk ``core_scope`` runs on every statement (#506, #559).

``references_plain`` answers one question — does this statement read a
scoped table outside the ORM's annotations? — and ORM statements usually
answer no, so this runs on nearly every query while tenancy is on. It is a
reachability search over the clause tree, pruned at ORM-annotated elements;
everything here is about expanding fewer nodes, or expanding them more
cheaply, without changing which elements are reachable (#559):

* each element is expanded once, however many parents name it;
* a bound parameter has no clause children and is not expanded;
* a SELECT's declared children skip its empty collections, and the FROMs
  ``froms_read`` would add are added only when its internals do not
  already hold them (or they are ORM-annotated, which the walk prunes);
* ``table`` is looked up without the costly ``AttributeError`` that a
  column expression's ``__getattr__`` raises for it.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.sql.elements import ColumnClause, ColumnElement
from sqlalchemy.sql.selectable import Alias, Join, Select, TableClause
from sqlalchemy.sql.traversals import _get_children

from simple_module_db._core_joins import _base_name, _is_orm, is_plain_leaf


def orm_less(stmt: Any) -> bool:
    """A SELECT naming no ORM entity in its columns, FROM list or joins.

    Loader criteria have nothing to attach to there — ``exists().where(
    Doc.x == ...)`` — so the tables its ``WHERE`` reads must be scoped like
    Core ones. In an ORM select those tables are the entities' own.
    """
    targets = [entry[0] for entry in stmt._setup_joins]
    return not any(_is_orm(el) for el in (*stmt._raw_columns, *stmt._from_obj, *targets))


def where_froms(stmt: Any) -> list[Any]:
    return [f for crit in stmt._where_criteria for f in crit._from_objects]


def froms_read(stmt: Any) -> list[Any]:
    """The FROMs a SELECT reads besides its joins, and the extra FROMs of a DML."""
    if not isinstance(stmt, Select):
        target = stmt.table._deannotate()
        return [f for f in where_froms(stmt) if f is not target]
    froms = [*stmt.columns_clause_froms, *(f for f in stmt._from_obj if not isinstance(f, Join))]
    return [*froms, *(where_froms(stmt) if orm_less(stmt) else core_where_froms(stmt))]


def core_where_froms(stmt: Select) -> list[Any]:
    """The FROMs a SELECT's ``WHERE`` pulls in through plain (non-ORM) columns.

    ``select(Tag.name).where(link.c.tag_id == Tag.id)`` reads ``link`` only
    through its ``WHERE``. ``where_froms`` cannot be used for an ORM select:
    an entity column's ``_from_objects`` is its bare table too, and an
    ``aliased()`` entity's would gain a stray cartesian FROM. So the criteria
    are walked down to their columns, pruning ORM-annotated elements and
    anything that adds no FROM to this SELECT (a nested select's own
    references are scoped where that select is visited).
    """
    found: list[Any] = []
    stack = list(stmt._where_criteria)
    while stack:
        el = stack.pop()
        if _is_orm(el) or not el._from_objects:
            continue
        if isinstance(el, ColumnClause):
            found.extend(el._from_objects)
        else:
            stack.extend(el.get_children())
    return found


def references_plain(stmt: Any, names: set[str]) -> bool:
    """Whether ``stmt`` reads a scoped table outside the ORM's annotations.

    ORM-annotated elements are not descended into: their tables are the
    loader criteria's business, and every ORM column leads to a plain table.
    The answer depends only on *which* elements are reachable, so an element
    met twice is expanded once. ``seen`` keeps the objects, not just their
    ids, so a temporary child list cannot free one and recycle its id.
    """
    stack = [stmt]
    seen: dict[int, Any] = {}
    while stack:
        el = stack.pop()
        if id(el) in seen or _is_orm(el):
            continue
        seen[id(el)] = el
        target = el if isinstance(el, (TableClause, Alias)) else _table_of(el)
        if (
            isinstance(target, (TableClause, Alias))
            and is_plain_leaf(target)
            and _base_name(target) in names
        ):
            return True
        if el.__visit_name__ != "bindparam":  # a bound value: no clause children
            stack.extend(_children(el))
    return False


_SELECT_OMIT = ("_correlate", "_correlate_except")
_EMPTYABLE = (tuple, list)


def _children(el: Any) -> list[Any]:
    # ``Select.get_children`` adds every FROM it derives from the columns and
    # WHERE, deannotated, so every ORM statement would look Core. Its declared
    # internals plus the FROMs ``froms_read`` would scope are what counts —
    # less what the internals already hold: the FROM list itself, and the
    # columns-clause FROMs of an all-entity ORM columns clause (#559).
    if isinstance(el, Select):
        kids = _declared_children(el)
        if not _orm_columns_only(el):
            kids.extend(el.columns_clause_froms)
        if orm_less(el):
            kids.extend(where_froms(el))
        return kids
    if el.__visit_name__ in ("update", "delete"):
        return [*el.get_children(), *froms_read(el)]
    return list(el.get_children())


def _declared_children(stmt: Select) -> list[Any]:
    """``HasTraverseInternals.get_children(stmt, omit_attrs=_SELECT_OMIT)``, as a list.

    The same generated dispatch, minus the call per empty collection: most
    of a SELECT's ~30 declared attributes are ``()`` on any given statement.
    """
    kids: list[Any] = []
    dispatch = _get_children.run_generated_dispatch(
        stmt, stmt._traverse_internals, "_generated_get_children_traversal"
    )
    for attrname, obj, meth in dispatch:
        if obj is None or (obj.__class__ in _EMPTYABLE and not obj) or attrname in _SELECT_OMIT:
            continue
        kids.extend(meth(obj))
    return kids


def _orm_columns_only(stmt: Select) -> bool:
    """Every ``columns_clause_froms`` entry is ORM-annotated, so the walk prunes it.

    Under the ORM compile plugin an annotated column's FROM is its entity's
    ``__clause_element__()`` — a ``Mapper``'s or ``AliasedInsp``'s selectable,
    annotated with ``parententity`` itself. The Core plugin would give the
    column's own ``_from_objects`` instead, which may be a plain table.
    """
    return stmt._propagate_attrs.get("compile_state_plugin") == "orm" and all(
        _is_orm(c) for c in stmt._raw_columns
    )


# Per class: does attribute lookup of ``table`` end in ``ColumnElement.__getattr__``?
_COMPARATOR_LOOKUP: dict[type, bool] = {}


def _table_of(el: Any) -> Any:
    """``getattr(el, "table", None)``, exactly — minus the ``AttributeError`` it costs.

    When no class in the MRO defines ``table``, Python tries the instance
    ``__dict__`` and then ``__getattr__``; for a ``ColumnElement`` that is
    ``getattr(self.comparator, "table")``, which this calls directly instead
    of letting ``__getattr__`` format an error message to be thrown away.
    Any other class (one that defines ``table``, has no ``__dict__`` or its
    own ``__getattr__``) takes the plain ``getattr``.
    """
    cls = el.__class__
    via_comparator = _COMPARATOR_LOOKUP.get(cls)
    if via_comparator is None:
        via_comparator = _COMPARATOR_LOOKUP[cls] = (
            cls.__getattr__ is ColumnElement.__getattr__
            if issubclass(cls, ColumnElement)
            and cls.__dictoffset__ != 0
            and not any("table" in vars(k) for k in cls.__mro__)
            else False
        )
    if not via_comparator:
        return getattr(el, "table", None)
    found = el.__dict__.get("table", _MISSING)
    return getattr(el.comparator, "table", None) if found is _MISSING else found


_MISSING = object()
