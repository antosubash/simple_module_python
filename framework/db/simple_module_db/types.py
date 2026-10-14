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

from sqlalchemy.engine.interfaces import Dialect
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
