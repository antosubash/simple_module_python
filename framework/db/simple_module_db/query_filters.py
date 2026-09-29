"""Soft-delete and tenant filtering for SELECT statements.

The filters hang off the ``do_orm_execute`` event. The obvious implementation —
``with_loader_criteria`` per mapper in ``ORMExecuteState.all_mappers`` — only
sees entities the statement *names in its columns*, because ``all_mappers`` is
derived from ``column_descriptions``. Three common shapes name no entity there
and so went unfiltered (GH #332)::

    select(func.count()).select_from(Model)                    # annotated table
    select(func.count()).select_from(select(Model).subquery()) # nested select
    select(func.count()).select_from(Model.__table__)          # pure Core

On a single-tenant host that is a wrong count. On a multi-tenant host it is a
cross-tenant read. So we also walk the statement's FROM clause, and pick the
tool that is *correct for where the table was found* — the three shapes do not
accept the same fix:

* **Inside a JOIN**, a ``WHERE`` would silently turn a ``LEFT JOIN`` into an
  inner join, dropping rows the caller asked to keep. ``with_loader_criteria``
  renders into the ON clause instead, so joined entities always take that route.
* **Inside a subquery or CTE**, a ``WHERE`` on the *outer* statement references
  a table that is not one of its FROM elements, which produces a cartesian
  product (verified: SQLAlchemy emits ``SAWarning: cartesian product``).
  ``with_loader_criteria`` reaches the entity wherever it is compiled, so it is
  the only correct tool here.
* **A standalone top-level FROM** may carry no ORM identity at all
  (``Model.__table__``), and ``with_loader_criteria`` has no entity to attach
  to. Here a ``WHERE`` built from *that FROM element's own columns* is both
  correct and free of cartesian products.

Known limit: a mixin entity brought in only by ``select(A).join(B)`` — named
neither in the columns nor in an explicit ``select_from()`` — is still not
filtered, and neither is the nullable side of a Core ``OUTER`` join. Reaching
the first would mean resolving the statement's full FROM list on every query,
which measured ~270us against ~1100us for the query itself — a tax on every
query in the app to find nothing on all but a handful. Name the entity in the
columns, or filter the join explicitly.
"""

from __future__ import annotations

from sqlalchemy import Table
from sqlalchemy.orm import ORMExecuteState, with_loader_criteria
from sqlalchemy.sql.selectable import CTE, Alias, FromClause, Join, Select, Subquery
from sqlmodel import SQLModel

from simple_module_db.listeners import current_tenant_id
from simple_module_db.mixins import MultiTenantMixin, SoftDeleteMixin

# Depth cap for the FROM walk. Nesting deeper than this is vanishingly rare and
# the cap is what keeps a self-referential selectable from looping forever.
_MAX_FROM_DEPTH = 8

# ``(is_soft_delete, is_multi_tenant)`` per mapped class, so the hot path skips
# redundant ``issubclass`` work on every query.
_mixin_flags_cache: dict[type, tuple[bool, bool]] = {}

# ``Table.key`` -> mapped class, rebuilt only when the registry has grown.
_table_class_map: dict[str, type] = {}
_table_map_size = -1


def _mixin_flags(cls: type) -> tuple[bool, bool]:
    flags = _mixin_flags_cache.get(cls)
    if flags is None:
        flags = (issubclass(cls, SoftDeleteMixin), issubclass(cls, MultiTenantMixin))
        _mixin_flags_cache[cls] = flags
    return flags


def _class_for_table(table: Table) -> type | None:
    """Map a ``Table`` back to its mapped class, or ``None`` if unmapped.

    Only rebuilds the map on a miss, and only when the registry has actually
    grown — a module importing its models after the first query would otherwise
    stay invisible, while rebuilding on every miss would make an unmapped table
    (``alembic_version``) pay for a registry scan on every statement.
    """
    global _table_map_size
    cls = _table_class_map.get(table.key)
    if cls is not None:
        return cls
    mappers = SQLModel._sa_registry.mappers
    if len(mappers) == _table_map_size:
        return None
    for mapper in mappers:
        local = mapper.local_table
        if local is not None:
            _table_class_map.setdefault(local.key, mapper.class_)
    _table_map_size = len(mappers)
    return _table_class_map.get(table.key)


def _walk_from(
    element: FromClause,
    depth: int,
    criteria_only: bool,
    direct: list[tuple[type, FromClause]],
    criteria: set[type],
) -> None:
    """Classify one FROM element into the WHERE-able or criteria-only bucket.

    ``criteria_only`` is sticky: once we are inside a JOIN, a subquery or a CTE,
    everything below is off-limits to a ``WHERE`` on the outer statement.
    """
    if depth > _MAX_FROM_DEPTH:
        return
    if isinstance(element, Join):
        # An INNER join keeps both sides WHERE-able: filtering either side in a
        # WHERE is equivalent to filtering it in the ON clause. An OUTER join
        # does not — a WHERE on the nullable side drops the very rows the outer
        # join was written to keep, so it falls back to loader criteria.
        nested = criteria_only or element.isouter
        _walk_from(element.left, depth + 1, nested, direct, criteria)
        _walk_from(element.right, depth + 1, nested, direct, criteria)
    elif isinstance(element, (Subquery, CTE)):
        inner = element.element
        if isinstance(inner, Select):
            for from_ in inner.get_final_froms():
                _walk_from(from_, depth + 1, True, direct, criteria)
    elif isinstance(element, Alias):
        inner = element.element
        if isinstance(inner, Table):
            cls = _class_for_table(inner)
            if cls is not None:
                # An alias keeps its own columns, so it stays WHERE-able when
                # it is a standalone top-level FROM.
                if criteria_only:
                    criteria.add(cls)
                else:
                    direct.append((cls, element))
        else:
            _walk_from(inner, depth + 1, criteria_only, direct, criteria)
    elif isinstance(element, Table):
        cls = _class_for_table(element)
        if cls is not None:
            if criteria_only:
                criteria.add(cls)
            else:
                direct.append((cls, element))


def apply_query_filters(execute_state: ORMExecuteState) -> None:
    """Attach soft-delete and tenant criteria to a SELECT before it executes.

    The criteria are built per *concrete* mapper because SQLModel mixins expose
    Pydantic ``FieldInfo`` (not SQLAlchemy ``InstrumentedAttribute``) at the
    mixin-class level, which breaks the lambda form of ``with_loader_criteria``
    that was used before the SQLModel migration.

    Soft-delete bypass: ``stmt.execution_options(include_deleted=True)``.
    """
    if not execute_state.is_select:
        return

    skip_soft_delete = bool(execute_state.execution_options.get("include_deleted", False))
    tenant_id = current_tenant_id.get()
    if skip_soft_delete and tenant_id is None:
        return

    statement = execute_state.statement
    options = []
    covered: set[type] = set()

    for mapper in execute_state.all_mappers:
        cls = mapper.class_
        covered.add(cls)
        options.extend(_loader_criteria(cls, skip_soft_delete, tenant_id))

    # ``_from_obj`` rather than ``get_final_froms()``: the latter resolves the
    # full FROM list and costs ~270us per call, which on the ordinary
    # entity-select path would be a ~40% tax on every query in the app to find
    # nothing. ``_from_obj`` is a plain tuple of the targets an explicit
    # ``select_from()`` recorded — 0.1us to read, empty for a normal
    # ``select(Model)``, and populated for exactly the shapes that are broken.
    # Private, so the three shape tests in ``test_query_filters.py`` are what
    # catch it going away.
    direct: list[tuple[type, FromClause]] = []
    criteria: set[type] = set()
    try:
        for from_ in getattr(statement, "_from_obj", ()):
            _walk_from(from_, 0, False, direct, criteria)
    except Exception:  # pragma: no cover - exotic selectables shouldn't break queries
        direct, criteria = [], set()

    for cls in criteria - covered:
        options.extend(_loader_criteria(cls, skip_soft_delete, tenant_id))

    for cls, from_element in direct:
        if cls in covered:
            continue
        # Built from the FROM element's own columns, never ``cls.__table__``:
        # an annotated table is not the same object, and referencing the
        # original would add a second FROM and cross-join the two.
        columns = from_element.c
        is_soft_delete, is_multi_tenant = _mixin_flags(cls)
        if is_soft_delete and not skip_soft_delete:
            statement = statement.where(columns.is_deleted.is_(False))
        if is_multi_tenant and tenant_id is not None:
            statement = statement.where(columns.tenant_id == tenant_id)

    if options:
        statement = statement.options(*options)
    if statement is not execute_state.statement:
        execute_state.statement = statement


def _loader_criteria(cls: type, skip_soft_delete: bool, tenant_id: str | None) -> list:
    is_soft_delete, is_multi_tenant = _mixin_flags(cls)
    out = []
    if is_soft_delete and not skip_soft_delete:
        out.append(with_loader_criteria(cls, cls.is_deleted.is_(False), include_aliases=True))
    if is_multi_tenant and tenant_id is not None:
        out.append(with_loader_criteria(cls, cls.tenant_id == tenant_id, include_aliases=True))
    return out
