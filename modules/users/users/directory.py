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
from simple_module_db.user_directory_sql import name_or_email_contains, to_directory_user
from sqlalchemy import String, cast, func, select

from users.models import Role, User, UserRole

# Columns only: loading ``User`` itself would also selectin-load its OAuth
# accounts, a second query per lookup that nothing here reads.
_COLUMNS = (User.id, User.email, User.full_name, User.is_active, User.disabled_at)


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
                user_roles = tuple(sorted(roles.get(row.id, ()))) if with_roles else None
                for key in parsed[row.id]:
                    found[key] = to_directory_user(
                        row,
                        key,
                        roles=user_roles,
                        is_active=bool(row.is_active) and row.disabled_at is None,
                    )
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
            stmt = stmt.where(name_or_email_contains(User.full_name, User.email, term.strip()))
        rows = (await db.execute(stmt)).all()
        return [
            to_directory_user(
                row, str(row.id), is_active=bool(row.is_active) and row.disabled_at is None
            )
            for row in rows
        ]

    def match_ids(self, term: str) -> Any | None:
        # ``CAST`` renders the canonical lowercase hyphenated form on both
        # dialects (Postgres from ``uuid``, SQLite from GUID's ``CHAR(36)``),
        # which is the form the audit trail and every other text id stores.
        return select(cast(User.id, String)).where(
            name_or_email_contains(User.full_name, User.email, term)
        )

    async def stats(self, db: Any, *, active_window: timedelta) -> DirectoryStats:
        now = datetime.now(UTC)
        # Calendar month, not a rolling 30 days: the tile reads "+6 this month".
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # One scan for all three figures rather than a query each.
        row = (
            await db.execute(
                select(
                    func.count(),
                    func.count().filter(User.last_login_at >= now - active_window),
                    func.count().filter(User.created_at >= month_start),
                ).select_from(User)
            )
        ).one()
        total, active, created = row
        return DirectoryStats(total=total, active_since=active, created_this_month=created)


__all__ = ["UsersDirectory"]
