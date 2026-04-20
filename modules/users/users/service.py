"""UserService — admin operations delegating to the DB and UserManager."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from users.contracts.schemas import RoleListItem, UserCreate, UserListItem
from users.manager import UserManager
from users.models import Role, User, UserRole


class UserService:
    def __init__(
        self,
        db: AsyncSession,
        user_manager: UserManager,
    ) -> None:
        self._db = db
        self._manager = user_manager

    # ── Helpers ─────────────────────────────────────────────────

    async def _resolve_roles(self, role_names: list[str]) -> list[Role]:
        """Return Role ORM objects matching the given names."""
        if not role_names:
            return []
        result = await self._db.execute(select(Role).where(Role.name.in_(role_names)))
        return list(result.scalars().all())

    async def to_list_item(self, user: User) -> UserListItem:
        """Build the DTO from a User with roles already eager-loaded."""
        return UserListItem(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            is_verified=user.is_verified,
            disabled_at=user.disabled_at,
            last_login_at=user.last_login_at,
            roles=[r.name for r in user.roles],
        )

    async def list_roles(self) -> list[RoleListItem]:
        stmt = (
            select(Role, func.count(UserRole.user_id))
            .outerjoin(UserRole, UserRole.role_id == Role.id)
            .group_by(Role.id)
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
            select(User).where(User.id == user_id).options(selectinload(User.roles))
        )
        return result.scalar_one_or_none()

    # ── Public API ───────────────────────────────────────────────

    async def list_users(
        self,
        *,
        page: int = 1,
        per_page: int = 20,
        search: str | None = None,
    ) -> tuple[list[UserListItem], int]:
        """Returns (items, total_count). Filters on email/full_name LIKE search."""
        stmt = select(User).options(selectinload(User.roles))
        count_stmt = select(func.count()).select_from(User)

        if search:
            pattern = f"%{search}%"
            condition = or_(
                User.email.ilike(pattern),
                User.full_name.ilike(pattern),
            )
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        total = (await self._db.execute(count_stmt)).scalar_one()

        stmt = stmt.order_by(User.email).offset((page - 1) * per_page).limit(per_page)
        rows = (await self._db.execute(stmt)).scalars().all()

        items = [await self.to_list_item(u) for u in rows]
        return items, total

    async def invite(
        self,
        email: str,
        full_name: str | None,
        role_names: list[str],
        *,
        invited_by: User | None = None,
    ) -> tuple[User, str]:
        """Creates unverified user + random unusable password, assigns roles,
        mints a verification token. Returns (user, token)."""
        password = secrets.token_urlsafe(32)
        user_create = UserCreate(
            email=email,
            password=password,
            full_name=full_name,
            is_active=True,
            is_verified=False,
        )
        user = await self._manager.create(user_create, safe=False)

        # Assign roles
        roles = await self._resolve_roles(role_names)
        invited_by_str = str(invited_by.id) if invited_by else None
        for role in roles:
            self._db.add(
                UserRole(
                    user_id=user.id,
                    role_id=role.id,
                    assigned_by=invited_by_str,
                )
            )
        if roles:
            await self._db.commit()

        token = await self._manager.generate_verification_token(user)
        return user, token

    async def disable(self, user_id: uuid.UUID) -> User:
        user = await self._get_user_with_roles(user_id)
        if user is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="User not found")
        user.disabled_at = datetime.now(UTC)
        user.is_active = False
        await self._db.commit()
        self._db.expire_all()
        refreshed = await self._get_user_with_roles(user_id)
        assert refreshed is not None  # we just committed a change to this user
        return refreshed

    async def enable(self, user_id: uuid.UUID) -> User:
        user = await self._get_user_with_roles(user_id)
        if user is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="User not found")
        user.disabled_at = None
        user.is_active = True
        await self._db.commit()
        self._db.expire_all()
        refreshed = await self._get_user_with_roles(user_id)
        assert refreshed is not None  # we just committed a change to this user
        return refreshed

    async def set_roles(
        self,
        user_id: uuid.UUID,
        role_names: list[str],
        *,
        assigned_by: str | None = None,
    ) -> User:
        user = await self._get_user_with_roles(user_id)
        if user is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="User not found")

        # Delete all existing role assignments for this user
        await self._db.execute(delete(UserRole).where(UserRole.user_id == user_id))

        # Insert new role assignments
        roles = await self._resolve_roles(role_names)
        for role in roles:
            self._db.add(
                UserRole(
                    user_id=user_id,
                    role_id=role.id,
                    assigned_by=assigned_by,
                )
            )

        await self._db.commit()
        # Expire the session so the next query sees DB-committed data.
        self._db.expire_all()

        # Re-fetch with roles loaded
        refreshed = await self._get_user_with_roles(user_id)
        assert refreshed is not None  # we just committed role changes to this user
        return refreshed

    async def generate_reset_link(self, user_id: uuid.UUID, base_url: str) -> str:
        """Build an admin-copyable password-reset URL. No email side-effect."""
        user = await self._get_user_with_roles(user_id)
        if user is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="User not found")

        token = await self._manager.generate_reset_password_token(user)
        return f"{base_url.rstrip('/')}/users/reset-password?token={token}"

    async def get_with_roles(self, user_id: uuid.UUID) -> User | None:
        return await self._get_user_with_roles(user_id)

    async def get_list_item(self, user_id: uuid.UUID) -> UserListItem:
        user = await self._get_user_with_roles(user_id)
        if user is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="User not found")
        return await self.to_list_item(user)
