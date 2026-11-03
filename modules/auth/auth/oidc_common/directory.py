"""Directory for provider-owned UUID cache tables; roles remain at the IdP."""

from __future__ import annotations

from collections.abc import Collection
from datetime import UTC, datetime, timedelta
from typing import Any

from simple_module_core.user_directory import (
    DirectoryStats,
    DirectoryUser,
    chunked,
    parse_user_ids,
)
from simple_module_db.user_directory_sql import name_or_email_contains, to_directory_user
from sqlalchemy import String, func, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import FunctionElement


class _UuidText(FunctionElement):
    """A uuid column as the canonical hyphenated text every text id uses.

    The cache primary key is SQLAlchemy's ``Uuid``: native on Postgres,
    where a plain cast already renders hyphenated, but 32 bare hex characters
    on SQLite — which would never equal the ``str(uuid)`` an audit row stored.
    """

    type = String()
    inherit_cache = True


@compiles(_UuidText)
def _uuid_text_default(element: Any, compiler: Any, **kw: Any) -> str:
    return f"CAST({compiler.process(element.clauses, **kw)} AS VARCHAR)"


@compiles(_UuidText, "sqlite")
def _uuid_text_sqlite(element: Any, compiler: Any, **kw: Any) -> str:
    col = compiler.process(element.clauses, **kw)
    parts = [(1, 8), (9, 4), (13, 4), (17, 4), (21, 12)]
    return " || '-' || ".join(f"substr({col}, {start}, {length})" for start, length in parts)


class CacheDirectory:
    """Directory over the supplied provider cache model."""

    #: Cache rows are not an audited model with a screen of their own, so actor
    #: cells stay unlinked rather than pointing at a users page that is absent.
    entity_type: str | None = None

    def __init__(self, model: Any) -> None:
        self.model = model
        self._columns = (model.id, model.email, model.full_name)

    async def get_many(
        self, db: Any, ids: Collection[str], *, with_roles: bool = False
    ) -> dict[str, DirectoryUser]:
        parsed = parse_user_ids(ids)
        found: dict[str, DirectoryUser] = {}
        for chunk in chunked(list(parsed)):
            stmt = select(*self._columns).where(self.model.id.in_(chunk))
            for row in (await db.execute(stmt)).all():
                for key in parsed[row.id]:
                    found[key] = to_directory_user(row, key)
        return found

    async def search(self, db: Any, term: str | None, *, limit: int) -> list[DirectoryUser]:
        stmt = select(*self._columns).order_by(self.model.email).limit(limit)
        if term and term.strip():
            stmt = stmt.where(
                name_or_email_contains(self.model.full_name, self.model.email, term.strip())
            )
        return [to_directory_user(row, str(row.id)) for row in (await db.execute(stmt)).all()]

    def match_ids(self, term: str) -> Any | None:
        return select(_UuidText(self.model.id)).where(
            name_or_email_contains(self.model.full_name, self.model.email, term)
        )

    async def stats(self, db: Any, *, active_window: timedelta) -> DirectoryStats:
        cutoff = datetime.now(UTC) - active_window
        total, active = (
            await db.execute(
                select(
                    func.count(),
                    func.count().filter(self.model.last_login_at >= cutoff),
                ).select_from(self.model)
            )
        ).one()
        # The cache row is written at first sign-in, not account creation.
        return DirectoryStats(total=total, active_since=active, created_this_month=None)


__all__ = ["CacheDirectory"]
