"""Column types shared by every module.

``AwareDateTime`` is the explicit-column counterpart of the ``UTCDateTime``
SQLModel picks for a bare ``datetime`` field. Declaring
``sa_type=DateTime(timezone=True)`` bypasses that type, and on SQLite (which
stores no offset) such a column reads back *naive*: pydantic then serializes
``2026-10-14T10:40:52`` with no offset and a browser parses UTC as local time
(GH #468). Use ``sa_type=AwareDateTime()`` wherever a field needs an explicit
column type.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import TypeDecorator, UserDefinedType
from sqlmodel.sql.sqltypes import UTCDateTime


class AwareDateTime(UTCDateTime):
    """``DateTime(timezone=True)`` that always reads back an aware UTC value.

    Unlike SQLModel's ``UTCDateTime`` a naive value is accepted on write and
    taken to be UTC — the semantics a plain ``DateTime(timezone=True)`` column
    had on SQLite — so existing callers that bind naive UTC keep working.
    Migrations render it as ``sa.DateTime(timezone=True)`` (see
    :func:`simple_module_db.migrations.render_item`), so adopting it needs no
    schema change.
    """

    cache_ok = True

    def __repr__(self) -> str:
        return "AwareDateTime()"

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            value = value.replace(tzinfo=UTC)
        return super().process_bind_param(value, dialect)


class _PgLTree(UserDefinedType):
    cache_ok = True

    def get_col_spec(self, **kw: object) -> str:
        return "LTREE"


class LTree(TypeDecorator):
    """Postgres ``ltree`` (label tree paths); ``TEXT`` on SQLite.

    The ``ltree`` extension must be declared by the owning module through
    :meth:`~simple_module_core.ModuleBase.db_extensions` (``["ltree"]``).
    Values are plain dotted-path strings (``"top.science.physics"``). Query
    operators (``<@``, ``@>``, ``~``) are Postgres-only: use ``column.op("<@")``.
    """

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(_PgLTree())
        return dialect.type_descriptor(Text())

    def __repr__(self) -> str:
        return "LTree()"


# Let Postgres reflection (autogenerate, ``alembic check``) return ``LTree``
# instead of warning "Did not recognize type 'ltree'" and falling back to NullType.
postgresql.base.ischema_names["ltree"] = LTree


class TSVector(TypeDecorator):
    """Postgres ``tsvector`` (full-text search); ``TEXT`` on SQLite.

    Built in to Postgres, so no extension is needed. Pair with a GIN index and
    ``func.to_tsvector`` / ``column.op("@@")(func.plainto_tsquery(...))``.
    """

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(postgresql.TSVECTOR())
        return dialect.type_descriptor(Text())

    def __repr__(self) -> str:
        return "TSVector()"
