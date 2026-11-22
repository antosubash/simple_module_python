"""SQL-backed user directory helpers shared by account providers."""

from __future__ import annotations

from collections.abc import Collection
from typing import Any

from simple_module_core.access.user_directory import DirectoryUser, chunked, parse_user_ids
from sqlalchemy import or_
from sqlalchemy.sql.elements import ColumnElement

from simple_module_db.queries.search import LIKE_ESCAPE_CHAR, like_contains_pattern


async def search_rows(
    db: Any,
    stmt: Any,
    id_column: Any,
    *,
    include_ids: Collection[str] | None,
    limit: int,
) -> list[Any]:
    """Bound allowed-id parameters and merge email-ordered search results."""
    if include_ids is None:
        return list((await db.execute(stmt.limit(limit))).all())
    rows = []
    for chunk in chunked(list(parse_user_ids(include_ids))):
        # SQL merges the best previous rows with this chunk using the database collation.
        wanted = [*chunk, *(row.id for row in rows)]
        rows = list((await db.execute(stmt.where(id_column.in_(wanted)).limit(limit))).all())
    return rows


def name_or_email_contains(full_name: Any, email: Any, term: str) -> ColumnElement[bool]:
    """Match a literal substring in either provider column, ignoring case."""
    pattern = like_contains_pattern(term)
    return or_(
        full_name.ilike(pattern, escape=LIKE_ESCAPE_CHAR),
        email.ilike(pattern, escape=LIKE_ESCAPE_CHAR),
    )


def to_directory_user(
    row: Any,
    key: str,
    *,
    roles: tuple[str, ...] | None = None,
    is_active: bool = True,
    email_verified: bool | None = None,
) -> DirectoryUser:
    """Convert identity columns, preserving unknown versus empty roles.

    Providers supply account availability and roles when known. ``None`` means
    unknown roles; an empty tuple means no assigned roles.
    """
    return DirectoryUser(
        id=key,
        email=row.email,
        full_name=row.full_name,
        is_active=is_active,
        roles=roles,
        email_verified=email_verified,
    )
