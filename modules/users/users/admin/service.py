"""UserService — admin write operations (reads live in queries.py)."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import noload

from users.admin.queries import _UserServiceBase
from users.contracts.schemas import UserCreate
from users.exceptions import (
    EmailAlreadyExistsError,
    ExternalUserNoPasswordError,
    UserNotFoundError,
)
from users.models import OAuthAccount, RefreshToken, User, UserAccessToken, UserRole


class UserService(_UserServiceBase):
    async def create_user(
        self,
        email: str,
        password: str,
        full_name: str | None,
        role_names: list[str],
        *,
        created_by: str | None,
    ) -> User:
        """Create an active+verified user with an admin-set password.

        Reuses ``manager.create`` for the password policy + email-uniqueness
        check. ``is_verified=True`` means ``on_after_register`` does not fire a
        verification email (and with no request, no event is published here —
        the endpoint publishes ``UserCreated``)."""
        user_create = UserCreate(
            email=email,
            password=password,
            full_name=full_name,
            is_active=True,
            is_verified=True,
            is_superuser=False,
        )
        user = await self._manager.create(user_create, safe=False)

        roles = await self._resolve_roles(role_names)
        for role in roles:
            self._db.add(
                UserRole(
                    user_id=user.id,
                    role_id=role.id,
                    assigned_by=created_by,
                )
            )
        if roles:
            await self._db.flush()
            # User.roles is lazy="noload": selectinload only populates a fresh
            # fetch, not an identity-map hit. Expunge first to force a reload.
            user_id = user.id
            self._db.expunge(user)
            loaded = await self._get_user_with_roles(user_id)
            if loaded is None:  # impossible: row was just flushed in this txn
                raise RuntimeError(f"User {user_id} vanished immediately after create")
            return loaded
        return user

    async def update_details(
        self,
        user_id: uuid.UUID,
        email: str,
        full_name: str | None,
    ) -> User:
        """Update a user's email + full name. Raises UserNotFoundError if the
        user is missing, EmailAlreadyExistsError if the new email is taken by
        another user."""
        user = await self._require_user(user_id)
        if email.lower() != user.email.lower():
            clash = await self._db.execute(
                select(User.id).where(
                    func.lower(User.email) == email.lower(),
                    User.id != user_id,
                )
            )
            if clash.scalar_one_or_none() is not None:
                raise EmailAlreadyExistsError(email)
        user.email = email
        user.full_name = full_name
        await self._db.flush()
        return user

    async def delete_user(self, user_id: uuid.UUID) -> None:
        """Hard-delete a user and all of its dependent rows.

        Every child table is cleared with an explicit bulk ``DELETE`` so the
        result is deterministic and identical on Postgres and SQLite (SQLite
        only honours FK cascade with a per-connection pragma we don't set, and
        ``RefreshToken`` has no DB cascade at all).

        The user is loaded with ``roles`` and ``oauth_accounts`` forced to
        ``noload``. ``noload`` returns an empty collection *without* emitting a
        query, which matters twice: (1) the unit of work isn't tracking the
        ``users_user_role`` / ``oauth_account`` rows, so our bulk deletes don't
        race the ORM and trigger ``StaleDataError`` on flush (the original bug —
        it only bit a real request session deleting a user that actually had a
        role); (2) ``session.delete(user)`` won't trigger an implicit async
        lazy-load of the ``delete-orphan`` ``oauth_accounts`` collection
        mid-flush. ``session.delete(user)`` is what flags the session as
        written so ``get_db`` commits — a bulk ``DELETE`` of the user alone
        would be rolled back as a read-only request."""
        result = await self._db.execute(
            select(User)
            .where(User.id == user_id)
            .options(noload(User.roles), noload(User.oauth_accounts))
        )
        user = result.scalar_one_or_none()
        if user is None:
            raise UserNotFoundError(user_id)
        for model in (UserRole, UserAccessToken, OAuthAccount, RefreshToken):
            await self._db.execute(delete(model).where(model.user_id == user_id))
        await self._db.delete(user)
        await self._db.flush()

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
        """Build an admin-copyable password-reset URL. No email side-effect.

        Raises ``ExternalUserNoPasswordError`` for SSO users — they have no
        local password, so a reset link is meaningless (and would crash on the
        null-hash fingerprint).
        """
        user = await self._require_user(user_id)
        if user.is_external:
            raise ExternalUserNoPasswordError(user_id)

        token = await self._manager.generate_reset_password_token(user)
        return f"{base_url.rstrip('/')}/users/reset-password?token={token}"
