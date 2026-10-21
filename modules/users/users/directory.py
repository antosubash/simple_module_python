"""The users module's :class:`~simple_module_core.user_directory.UserDirectory`.

Other modules read user records through ``get_user_directory(app)`` rather than
importing ``users.models`` (GH #501), so the same audit log, dashboard and
permissions screens work whether ``users`` or ``keycloak`` holds the accounts.
This is the implementation over ``users_user``; it is installed in
``UsersModule.register_settings``.
"""

from __future__ import annotations

import uuid
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
from sqlalchemy import String, cast, func, or_, select

from users.models import Role, User, UserRole

# Columns only: loading ``User`` itself would also selectin-load its OAuth
# accounts, a second query per lookup that nothing here reads.
_COLUMNS = (User.id, User.email, User.full_name, User.is_active, User.disabled_at)


def _to_directory_user(row: Any, roles: tuple[str, ...] | None, key: str) -> DirectoryUser:
    return DirectoryUser(
        id=key,
        email=row.email,
        full_name=row.full_name,
        # A disabled account is still ``is_active`` in fastapi-users' sense;
        # to every other module it is simply not usable.
        is_active=bool(row.is_active) and row.disabled_at is None,
        roles=roles,
    )


def _name_or_email_contains(term: str) -> Any:
    pattern = like_contains_pattern(term)
    return or_(
        User.full_name.ilike(pattern, escape=LIKE_ESCAPE_CHAR),
        User.email.ilike(pattern, escape=LIKE_ESCAPE_CHAR),
    )


class UsersDirectory:
    """Directory over the local ``users_user`` table."""

    #: Audit entries record ``type(obj).__name__``; the users module registers
    #: its audit link under the same class name.
    entity_type: str | None = User.__name__

    async def get_many(
        self, db: Any, ids: Collection[str], *, with_roles: bool = False
    ) -> dict[str, DirectoryUser]:
        parsed = parse_user_ids(ids)
        found: dict[str, DirectoryUser] = {}
        for chunk in chunked(list(parsed)):
            rows = (await db.execute(select(*_COLUMNS).where(User.id.in_(chunk)))).all()
            roles = await self._roles_for(db, chunk) if with_roles else {}
            for row in rows:
                key = parsed[row.id]
                user_roles = tuple(sorted(roles.get(row.id, ()))) if with_roles else None
                found[key] = _to_directory_user(row, user_roles, key)
        return found

    async def _roles_for(
        self, db: Any, user_ids: Collection[uuid.UUID]
    ) -> dict[uuid.UUID, list[str]]:
        rows = await db.execute(
            select(UserRole.user_id, Role.name)
            .join(Role, Role.id == UserRole.role_id)
            .where(UserRole.user_id.in_(list(user_ids)))
        )
        roles: dict[uuid.UUID, list[str]] = {}
        for user_id, name in rows.all():
            roles.setdefault(user_id, []).append(name)
        return roles

    async def search(self, db: Any, term: str | None, *, limit: int) -> list[DirectoryUser]:
        stmt = select(*_COLUMNS).order_by(User.email).limit(limit)
        if term and term.strip():
            stmt = stmt.where(_name_or_email_contains(term.strip()))
        rows = (await db.execute(stmt)).all()
        return [_to_directory_user(row, None, str(row.id)) for row in rows]

    def match_ids(self, term: str) -> Any | None:
        # ``CAST`` renders the canonical lowercase hyphenated form on both
        # dialects (Postgres from ``uuid``, SQLite from GUID's ``CHAR(36)``),
        # which is the form the audit trail and every other text id stores.
        return select(cast(User.id, String)).where(_name_or_email_contains(term))

    async def stats(self, db: Any, *, active_window: timedelta) -> DirectoryStats:
        now = datetime.now(UTC)
        # Calendar month, not a rolling 30 days: the tile reads "+6 this month".
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        count = select(func.count()).select_from(User)
        total = (await db.execute(count)).scalar_one()
        active = (
            await db.execute(count.where(User.last_login_at >= now - active_window))
        ).scalar_one()
        created = (await db.execute(count.where(User.created_at >= month_start))).scalar_one()
        return DirectoryStats(total=total, active_since=active, created_this_month=created)


__all__ = ["UsersDirectory"]
