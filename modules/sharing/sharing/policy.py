"""Plug shares into a module's ``OwnedResourcePolicy`` (GH #526).

::

    from sharing.policy import share_exists_for

    NOTE_POLICY = OwnedResourcePolicy(
        Note.owner_id,
        bypass_perm=PERM_NOTES_MANAGE,
        share_exists=share_exists_for(NOTE_TYPE, Note.id),
    )
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from simple_module_core.resources import ResourcePrincipal
from sqlalchemy import String, cast, func, inspect, or_
from sqlmodel import exists, select

from sharing.constants import ROLE_IMPLIES, SUBJECT_USER
from sharing.models import ResourceShare


def resolve_roles(roles: Mapping[str, tuple[str, ...]] | None) -> Mapping[str, tuple[str, ...]]:
    """*roles* as declared on a resource type; ``None`` means the default view/edit roles."""
    return ROLE_IMPLIES if roles is None else roles


def roles_granting(
    action: str, *, roles: Mapping[str, tuple[str, ...]] | None = None
) -> tuple[str, ...]:
    """Every share role that implies *action*."""
    return tuple(role for role, implied in resolve_roles(roles).items() if action in implied)


def _is_uuid(column: Any) -> bool:
    try:
        return column.type.python_type is uuid.UUID
    except (AttributeError, NotImplementedError):
        return False


def id_text(column: Any) -> Any:
    """*column* rendered as the canonical text :func:`canonical_id` stores.

    UUIDs become 32 lowercase hex digits on every dialect (Postgres casts with
    hyphens, SQLite stores without), everything else its plain text.
    """
    text = cast(column, String)
    if _is_uuid(column):
        return func.replace(func.lower(text), "-", "")
    return text


def canonical_id(value: Any) -> str:
    """The stored ``resource_id`` for a key value (matches :func:`id_text`)."""
    if isinstance(value, uuid.UUID):
        return value.hex
    return str(value)


def row_id(obj: Any) -> str:
    """The canonical id of a loaded single-key row."""
    identity = inspect(obj).identity
    if not identity or len(identity) != 1:
        raise ValueError("shared resources need a single-column primary key")
    return canonical_id(identity[0])


def active_share_clause(now: datetime | None = None) -> Any:
    """Shares that have not expired, as of *now* (a bound value, not ``NOW()``)."""
    moment = now or datetime.now(UTC)
    return or_(ResourceShare.expires_at.is_(None), ResourceShare.expires_at > moment)


def share_exists_for(
    resource_type: str, id_col: Any, *, roles: Mapping[str, tuple[str, ...]] | None = None
) -> Callable[[ResourcePrincipal, str], Any | None]:
    """A ``share_exists`` factory for ``OwnedResourcePolicy``.

    Correlated on *id_col*; tenant scoping comes from the share table's
    ``MultiTenantMixin`` filter, and expired shares never match.
    """
    key = id_text(id_col)

    def share_exists(principal: ResourcePrincipal, action: str) -> Any | None:
        granting_roles = roles_granting(action, roles=roles)
        if not granting_roles or principal.user_id is None:
            return None
        return exists(
            select(ResourceShare.id).where(
                ResourceShare.resource_type == resource_type,
                ResourceShare.resource_id == key,
                ResourceShare.subject_type == SUBJECT_USER,
                ResourceShare.subject_id == principal.user_id,
                ResourceShare.role.in_(granting_roles),
                active_share_clause(),
            )
        )

    return share_exists


__all__ = [
    "active_share_clause",
    "canonical_id",
    "id_text",
    "resolve_roles",
    "roles_granting",
    "row_id",
    "share_exists_for",
]
