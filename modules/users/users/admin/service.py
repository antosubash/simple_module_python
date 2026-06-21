"""UserService — admin write operations (reads live in queries.py)."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete

from users.admin.queries import _UserServiceBase
from users.contracts.schemas import UserCreate
from users.models import User, UserRole


class UserService(_UserServiceBase):
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
            await self._db.flush()
            await self._db.refresh(user, attribute_names=["roles"])

        token = await self._manager.generate_verification_token(user)
        return user, token

    async def disable(self, user_id: uuid.UUID) -> User:
        user = await self._require_user(user_id)
        user.disabled_at = datetime.now(UTC)
        user.is_active = False
        await self._db.flush()
        return user

    async def enable(self, user_id: uuid.UUID) -> User:
        user = await self._require_user(user_id)
        user.disabled_at = None
        user.is_active = True
        await self._db.flush()
        return user

    async def mark_verified(self, user_id: uuid.UUID) -> User:
        user = await self._require_user(user_id)
        if not user.is_verified:
            user.is_verified = True
            await self._db.flush()
        return user

    async def set_roles(
        self,
        user_id: uuid.UUID,
        role_names: list[str],
        *,
        assigned_by: str | None = None,
    ) -> User:
        user = await self._require_user(user_id)

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

        await self._db.flush()
        await self._db.refresh(user, attribute_names=["roles"])
        return user

    async def generate_reset_link(self, user_id: uuid.UUID, base_url: str) -> str:
        """Build an admin-copyable password-reset URL. No email side-effect."""
        user = await self._require_user(user_id)

        token = await self._manager.generate_reset_password_token(user)
        return f"{base_url.rstrip('/')}/users/reset-password?token={token}"
