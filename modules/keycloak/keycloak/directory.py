"""The keycloak module's :class:`~simple_module_core.user_directory.UserDirectory`.

Keycloak owns the accounts; this app only learns about a user when they sign
in, and caches the stable id it hands out in ``keycloak_user_cache``. So the
directory knows **users who have signed in at least once**, and nothing about
their roles (those live in the IdP and arrive as token claims, never stored)
or when the IdP account was created.
"""

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
from simple_module_db import LIKE_ESCAPE_CHAR, like_contains_pattern
from sqlalchemy import String, func, or_, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import FunctionElement

from keycloak.models import KeycloakUserCache


class _UuidText(FunctionElement):
    """A uuid column as the canonical hyphenated text every text id uses.

    ``keycloak_user_cache.id`` is SQLAlchemy's ``Uuid``: native on Postgres,
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


_COLUMNS = (KeycloakUserCache.id, KeycloakUserCache.email, KeycloakUserCache.full_name)


def _to_directory_user(row: Any, key: str) -> DirectoryUser:
    # ``roles`` stays ``None``: unknown, which callers must not read as "none".
    return DirectoryUser(id=key, email=row.email, full_name=row.full_name)


def _name_or_email_contains(term: str) -> Any:
    pattern = like_contains_pattern(term)
    return or_(
        KeycloakUserCache.full_name.ilike(pattern, escape=LIKE_ESCAPE_CHAR),
        KeycloakUserCache.email.ilike(pattern, escape=LIKE_ESCAPE_CHAR),
    )


class KeycloakDirectory:
    """Directory over ``keycloak_user_cache``."""

    #: Cache rows are not an audited model with a screen of their own, so actor
    #: cells stay unlinked rather than pointing at a users page that is absent.
    entity_type: str | None = None

    async def get_many(
        self, db: Any, ids: Collection[str], *, with_roles: bool = False
    ) -> dict[str, DirectoryUser]:
        parsed = parse_user_ids(ids)
        found: dict[str, DirectoryUser] = {}
        for chunk in chunked(list(parsed)):
            stmt = select(*_COLUMNS).where(KeycloakUserCache.id.in_(chunk))
            for row in (await db.execute(stmt)).all():
                for key in parsed[row.id]:
                    found[key] = _to_directory_user(row, key)
        return found

    async def search(self, db: Any, term: str | None, *, limit: int) -> list[DirectoryUser]:
        stmt = select(*_COLUMNS).order_by(KeycloakUserCache.email).limit(limit)
        if term and term.strip():
            stmt = stmt.where(_name_or_email_contains(term.strip()))
        return [_to_directory_user(row, str(row.id)) for row in (await db.execute(stmt)).all()]

    def match_ids(self, term: str) -> Any | None:
        return select(_UuidText(KeycloakUserCache.id)).where(_name_or_email_contains(term))

    async def stats(self, db: Any, *, active_window: timedelta) -> DirectoryStats:
        count = select(func.count()).select_from(KeycloakUserCache)
        total = (await db.execute(count)).scalar_one()
        cutoff = datetime.now(UTC) - active_window
        active = (
            await db.execute(count.where(KeycloakUserCache.last_login_at >= cutoff))
        ).scalar_one()
        # The cache row is written at first sign-in, not account creation.
        return DirectoryStats(total=total, active_since=active, created_this_month=None)


__all__ = ["KeycloakDirectory"]
