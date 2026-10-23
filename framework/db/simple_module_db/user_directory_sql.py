"""SQL-backed user directory helpers shared by account providers."""

from __future__ import annotations

from typing import Any

from simple_module_core.user_directory import DirectoryUser
from sqlalchemy import or_
from sqlalchemy.sql.elements import ColumnElement

from simple_module_db.search import LIKE_ESCAPE_CHAR, like_contains_pattern


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
    )
