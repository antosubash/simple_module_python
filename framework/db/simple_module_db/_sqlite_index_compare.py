"""Index comparisons SQLite cannot make faithfully (GH #869).

SQLite reflects ``CREATE INDEX ... (tenant_id, created_at DESC, id)`` as three
plain columns. A model that wrote the ordered column as ``sa.text("created_at
DESC")`` or ``sa.desc("created_at")`` holds an expression there, and Alembic
compares the two element by element: every autogenerate on SQLite then writes a
drop and re-create of a correct index, and ``alembic check`` fails on a correct
schema. Postgres reflects the ordering, so it compares these faithfully.

:func:`differs_only_in_sqlite_ordering` recognises exactly that pair, so
``make_include_object`` can skip it on SQLite. Anything else still reaches
Alembic: a different column list, a uniqueness change, or a real expression
such as ``lower(email)``.
"""

from __future__ import annotations

import re

from alembic import context
from sqlalchemy import Index
from sqlalchemy.schema import SchemaItem
from sqlalchemy.sql.elements import ColumnClause, TextClause, UnaryExpression

_ORDERING_MODIFIERS = frozenset({"asc_op", "desc_op", "nulls_first_op", "nulls_last_op"})

# One identifier, optionally double-quoted, then an optional ordering.
_ORDERED_COLUMN = re.compile(
    r'\s*(?:"([^"]+)"|([A-Za-z_][A-Za-z0-9_]*))'
    r"(?:\s+(?:ASC|DESC))?(?:\s+NULLS\s+(?:FIRST|LAST))?\s*",
    re.IGNORECASE,
)


def _on_sqlite() -> bool:
    """Whether the active Alembic migration context targets SQLite.

    Outside a migration (no context configured) the answer is no, so the
    caller never suppresses a comparison it cannot place.
    """
    try:
        return context.get_context().dialect.name == "sqlite"
    except Exception:
        return False


def _element_name(element: object) -> tuple[str | None, bool]:
    """``(column name, written as an expression)`` for one index element.

    The name is ``None`` for a real expression, which never matches.
    """
    while (
        isinstance(element, UnaryExpression)
        and getattr(element.modifier, "__name__", None) in _ORDERING_MODIFIERS
    ):
        element = element.element
    if isinstance(element, TextClause):
        match = _ORDERED_COLUMN.fullmatch(element.text)
        return (match[1] or match[2], True) if match else (None, True)
    if isinstance(element, ColumnClause) and not element.is_literal:
        return element.name, False
    # ``sa.desc("col")`` wraps a textual label reference holding the bare name.
    label = getattr(element, "element", None)
    if type(element).__name__ == "_textual_label_reference" and isinstance(label, str):
        return label, True
    return None, False


def differs_only_in_sqlite_ordering(left: SchemaItem, right: SchemaItem | None) -> bool:
    """True when two indexes are the same index as far as SQLite can tell.

    Requires an active SQLite migration context, equal uniqueness, the same
    column names in the same order, and at least one element written as an
    expression (otherwise Alembic's own comparison is already right).
    """
    if not isinstance(left, Index) or not isinstance(right, Index) or left.unique != right.unique:
        return False
    if not _on_sqlite():
        return False
    sides = [[_element_name(e) for e in index.expressions] for index in (left, right)]
    names = [[name for name, _ in side] for side in sides]
    written_as_expression = any(is_expr for side in sides for _, is_expr in side)
    return written_as_expression and None not in names[0] and names[0] == names[1]
