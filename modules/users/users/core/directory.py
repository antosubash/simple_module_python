"""The users module's :class:`~simple_module_core.access.user_directory.UserDirectory`.

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

from simple_module_core.access.role_directory import DirectoryRole
from simple_module_core.access.user_directory import (
    DirectoryStats,
    DirectoryUser,
    EmailLookupUserDirectory,
    chunked,
    parse_user_ids,
)
from simple_module_db.queries.user_directory_sql import (
    name_or_email_contains,
    search_rows,
    to_directory_user,
)
from sqlalchemy import String, cast, func, select

from users.models import Role, User, UserRole

# Columns only: loading ``User`` itself would also selectin-load its OAuth
# accounts, a second query per lookup that nothing here reads.
_COLUMNS = (
    User.id,
    User.email,
    User.full_name,
    User.is_active,
    User.disabled_at,
    User.is_verified,
)


def _is_usable(row: Any) -> bool:
    # A disabled account is still ``is_active`` in fastapi-users' sense;
    # to every other module it is simply not usable.
    return bool(row.is_active) and row.disabled_at is None


class UsersDirectory(EmailLookupUserDirectory):
    """Directory over the local ``users_user`` table."""

    editable = True

    async def list_roles(self, db: Any) -> list[DirectoryRole]:
        rows = (await db.execute(select(Role).order_by(Role.name))).scalars().all()
        return [DirectoryRole(r.name, r.name, r.description, r.id) for r in rows]

    async def user_roles(self, db: Any, user_id: str) -> tuple[str, ...] | None:
        found = await self.get_many(db, [user_id], with_roles=True)
        user = found.get(user_id)
        return user.roles if user is not None else None

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
                        is_active=_is_usable(row),
                        email_verified=bool(row.is_verified),
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

    async def search(
        self,
        db: Any,
        term: str | None,
        *,
        limit: int,
        include_ids: Collection[str] | None = None,
        exclude_ids: Collection[str] = (),
        active_only: bool = False,
        exact_email: bool = False,
        match_email: bool = True,
    ) -> list[DirectoryUser]:
        stmt = select(*_COLUMNS).order_by(User.email)
        if exclude_ids:
            stmt = stmt.where(User.id.not_in(list(parse_user_ids(exclude_ids))))
        if active_only:
            stmt = stmt.where(User.is_active.is_(True), User.disabled_at.is_(None))
        if exact_email:
            stmt = stmt.where(func.lower(User.email) == (term or "").strip().lower())
        elif term and term.strip():
            stmt = stmt.where(
                name_or_email_contains(
                    User.full_name, User.email, term.strip(), match_email=match_email
                )
            )
        rows = await search_rows(db, stmt, User.id, include_ids=include_ids, limit=limit)
        return [to_directory_user(row, str(row.id), is_active=_is_usable(row)) for row in rows]

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
