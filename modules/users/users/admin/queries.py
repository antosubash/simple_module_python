"""Read/query helpers for the admin UserService (split from service.py)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from fastapi import FastAPI
from simple_module_db import LIKE_ESCAPE_CHAR, like_contains_pattern
from simple_module_db.pagination import PageParams
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from users.admin.user_state import STATUS_CONDITIONS, user_state
from users.contracts.schemas import RoleListItem, UserListItem
from users.exceptions import UserNotFoundError
from users.manager import UserManager
from users.models import Role, User, UserRole
from users.session_revocation import bump_session_version, publish_revocation
from users.session_version_cache import forget_session_version


def _live_lock(locked_until: datetime | None) -> datetime | None:
    """*locked_until* while the lock holds, else ``None``.

    An expired lock stays on the row until the next failure or an unlock; it
    refuses nothing any more, so the admin screens must not show it.
    """
    if locked_until is not None and locked_until > datetime.now(UTC):
        return locked_until
    return None


class _UserServiceBase:
    def __init__(
        self,
        db: AsyncSession,
        user_manager: UserManager,
        app: FastAPI | None = None,
    ) -> None:
        self._db = db
        self._manager = user_manager
        self._app = app

    async def _revoke_sessions(self, user: User) -> None:
        """Persist the counter with the write; evict only after it commits."""
        await bump_session_version(self._db, user)
        user_id = user.id
        app = self._app
        if app is None:
            self._db.on_commit(lambda: forget_session_version(user_id))
        else:
            self._db.on_commit(lambda: publish_revocation(app, user_id))

    # ── Helpers ─────────────────────────────────────────────────

    async def _resolve_roles(self, role_names: list[str]) -> list[Role]:
        """Return Role ORM objects matching the given names."""
        if not role_names:
            return []
        result = await self._db.execute(select(Role).where(Role.name.in_(role_names)))
        return list(result.scalars().all())

    @property
    def _invite_lifetime(self) -> timedelta:
        """How long an invite link stays usable.

        Read off the manager rather than the settings object because that is
        the value the token is actually minted with — an expiry the table
        prints has to come from the same place as the one the token enforces.
        """
        return timedelta(seconds=self._manager.verification_token_lifetime_seconds)

    def _invite_expiry(self, invited_at: datetime | None) -> datetime | None:
        return None if invited_at is None else invited_at + self._invite_lifetime

    def to_list_item(self, user: User) -> UserListItem:
        """Build the DTO from a User with roles already eager-loaded."""
        return UserListItem(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            is_verified=user.is_verified,
            is_external=user.is_external,
            disabled_at=user.disabled_at,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
            invited_at=user.invited_at,
            invite_expires_at=self._invite_expiry(user.invited_at),
            state=user_state(user.is_active, user.is_verified, user.invited_at),
            locked_until=_live_lock(user.locked_until),
            roles=[r.name for r in user.roles],
        )

    async def list_roles(self) -> list[RoleListItem]:
        stmt = (
            select(Role, func.count(UserRole.user_id))  # ty: ignore[invalid-argument-type]
            .outerjoin(UserRole, UserRole.role_id == Role.id)  # ty: ignore[invalid-argument-type]
            .group_by(Role.id)  # ty: ignore[invalid-argument-type]
            .order_by(Role.name)
        )
        result = await self._db.execute(stmt)
        return [
            RoleListItem(
                id=role.id,
                name=role.name,
                description=role.description,
                user_count=user_count,
            )
            for role, user_count in result.all()
        ]

    async def _get_user_with_roles(self, user_id: uuid.UUID) -> User | None:
        result = await self._db.execute(
            select(User).where(User.id == user_id).options(selectinload(User.roles))  # ty: ignore[invalid-argument-type]
        )
        return result.scalar_one_or_none()

    async def _require_user(self, user_id: uuid.UUID) -> User:
        """Fetch a user with roles eager-loaded, or raise UserNotFoundError."""
        user = await self._get_user_with_roles(user_id)
        if user is None:
            raise UserNotFoundError(user_id)
        return user

    # ── Queries ──────────────────────────────────────────────────

    async def list_users(
        self,
        *,
        page: int = 1,
        per_page: int = 20,
        search: str | None = None,
        status: str | None = None,
        role_name: str | None = None,
        verified: str | None = None,
        sort: str = "email",
        order: str = "asc",
    ) -> tuple[list[UserListItem], int]:
        """Returns (items, total_count). last_login_at sort always uses NULLS LAST.

        Selects only the columns ``UserListItem`` needs (plain rows, not ORM
        entities) + one batched roles query — avoids hydrating full User+Role
        ORM graphs, which dominated this endpoint's CPU under load.
        """
        # Clamp here, not in the endpoints: the admin view takes these params
        # raw, and a page<=0 would reach SQL as a negative OFFSET.
        params = PageParams(page=page, per_page=per_page)
        stmt = select(
            User.id,  # ty: ignore[invalid-argument-type]
            User.email,  # ty: ignore[invalid-argument-type]
            User.full_name,  # ty: ignore[invalid-argument-type]
            User.is_active,  # ty: ignore[invalid-argument-type]
            User.is_verified,  # ty: ignore[invalid-argument-type]
            User.is_external,  # ty: ignore[invalid-argument-type]
            User.disabled_at,  # ty: ignore[invalid-argument-type]
            User.last_login_at,  # ty: ignore[invalid-argument-type]
            User.created_at,
            User.invited_at,  # ty: ignore[invalid-argument-type]
            User.locked_until,  # ty: ignore[invalid-argument-type]
        )
        count_stmt = select(func.count()).select_from(User)

        conditions = []

        if search:
            pattern = like_contains_pattern(search)
            conditions.append(
                or_(
                    User.email.ilike(pattern, escape=LIKE_ESCAPE_CHAR),
                    User.full_name.ilike(pattern, escape=LIKE_ESCAPE_CHAR),
                )
            )

        status_condition = STATUS_CONDITIONS.get(status or "")
        if status_condition is not None:
            conditions.append(status_condition())

        if verified == "yes":
            conditions.append(User.is_verified.is_(True))
        elif verified == "no":
            conditions.append(User.is_verified.is_(False))

        if role_name is not None:
            subq = (
                select(UserRole.user_id)
                .join(Role, Role.id == UserRole.role_id)
                .where(Role.name == role_name)
            )
            conditions.append(User.id.in_(subq))

        for cond in conditions:
            stmt = stmt.where(cond)
            count_stmt = count_stmt.where(cond)

        total = (await self._db.execute(count_stmt)).scalar_one()

        sort_col_map = {
            "email": User.email,
            "last_login_at": User.last_login_at,
            "created_at": User.created_at,
        }
        sort_col = sort_col_map.get(sort, User.email)

        if sort == "last_login_at":
            order_clause = (
                sort_col.desc().nulls_last() if order == "desc" else sort_col.asc().nulls_last()
            )
        else:
            order_clause = sort_col.desc() if order == "desc" else sort_col.asc()

        stmt = stmt.order_by(order_clause).offset(params.offset).limit(params.per_page)
        rows = (await self._db.execute(stmt)).all()

        # One batched roles query, grouped in Python — DB-agnostic (no
        # array_agg/group_concat) and builds no Role ORM objects.
        user_ids = [r.id for r in rows]
        roles_by_user: dict[uuid.UUID, list[str]] = {}
        if user_ids:
            role_rows = await self._db.execute(
                select(UserRole.user_id, Role.name)
                .join(Role, Role.id == UserRole.role_id)
                .where(UserRole.user_id.in_(user_ids))
                .order_by(UserRole.user_id, Role.name)
            )
            for uid, role_name_ in role_rows:
                roles_by_user.setdefault(uid, []).append(role_name_)

        # Selected columns == UserListItem fields (minus the derived ones and
        # roles): unpack directly.
        items = [
            UserListItem(
                **cast(
                    "dict[str, Any]", {**r._mapping, "locked_until": _live_lock(r.locked_until)}
                ),
                invite_expires_at=self._invite_expiry(r.invited_at),
                state=user_state(r.is_active, r.is_verified, r.invited_at),
                roles=roles_by_user.get(r.id, []),
            )
            for r in rows
        ]
        return items, total

    async def count_user_states(self) -> dict[str, int]:
        """Workspace-wide counts unaffected by list filters/pagination —
        feeds the stat row on /admin/users so it doesn't reflect
        the current page slice.

        ``invited`` and ``unverified`` are counted apart because the card the
        deck labels "Pending invites" means outstanding *invitations*: a
        self-registered account that never clicked its verification mail is
        nobody's to chase.

        One scan with ``COUNT(*) FILTER (WHERE …)`` per state rather than a
        round-trip each (Postgres and SQLite >= 3.30 both support it).
        """
        keys = ("active", "unverified", "invited")
        stmt = select(*(func.count().filter(STATUS_CONDITIONS[k]()) for k in keys)).select_from(
            User
        )
        row = (await self._db.execute(stmt)).one()
        return {key: int(value) for key, value in zip(keys, row, strict=True)}

    async def get_with_roles(self, user_id: uuid.UUID) -> User | None:
        return await self._get_user_with_roles(user_id)

    async def get_list_item(self, user_id: uuid.UUID) -> UserListItem:
        user = await self._require_user(user_id)
        return self.to_list_item(user)
