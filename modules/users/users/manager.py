"""UserManager — handles lifecycle hooks + custom verification-token helper."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, UUIDIDMixin, exceptions
from fastapi_users.jwt import generate_jwt

from users.db_adapter import UserDatabaseWithRoles, get_user_db
from users.mailer import Mailer
from users.models import User

if TYPE_CHECKING:
    from users.settings import UsersSettings


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    """Customizes password validation, token secrets, and lifecycle emails."""

    # Secrets and lifetimes pulled from settings at construction time so
    # subclasses of UserManager work in tests without full app startup.
    def __init__(
        self,
        user_db: UserDatabaseWithRoles,
        mailer: Mailer,
        settings: UsersSettings,
    ) -> None:
        super().__init__(user_db)
        self.mailer = mailer
        self.reset_password_token_secret = settings.reset_password_token_secret
        self.verification_token_secret = settings.verification_token_secret
        self.reset_password_token_lifetime_seconds = (
            settings.reset_password_token_lifetime_seconds
        )
        self.verification_token_lifetime_seconds = (
            settings.verification_token_lifetime_seconds
        )

    # ── Password policy ──────────────────────────────────────

    async def validate_password(self, password: str, user) -> None:
        if len(password) < 8:
            raise exceptions.InvalidPasswordException(
                reason="Password must be at least 8 characters"
            )
        if password.lower() in user.email.lower():
            raise exceptions.InvalidPasswordException(
                reason="Password cannot contain your email"
            )
        if password.isdigit():
            raise exceptions.InvalidPasswordException(
                reason="Password cannot be all numbers"
            )

    # ── Lifecycle hooks ──────────────────────────────────────

    async def on_after_register(self, user: User, request: Request | None = None) -> None:
        if not user.is_verified:
            # Kicks off on_after_request_verify, which sends the email
            await self.request_verify(user, request)

    async def on_after_forgot_password(
        self, user: User, token: str, request: Request | None = None
    ) -> None:
        await self.mailer.send_password_reset(user.email, token)

    async def on_after_request_verify(
        self, user: User, token: str, request: Request | None = None
    ) -> None:
        await self.mailer.send_verification(user.email, token)

    async def on_after_login(
        self, user: User, request: Request | None = None, response=None
    ) -> None:
        user.last_login_at = datetime.now(UTC)
        await self.user_db.update(user, {"last_login_at": user.last_login_at})

    # ── Invite token helper (no email side-effect) ──────────

    async def generate_verification_token(self, user: User) -> str:
        """Mint a verify-audience JWT without firing on_after_request_verify.

        Used by the admin-invite endpoint — it must produce the exact token
        shape fastapi-users' POST /verify expects, but send a different email
        template (invite instead of verify). The public request_verify()
        couples token generation with email send; we decouple them here.

        Verified: BaseUserManager.verification_token_audience == "fastapi-users:verify"
        Verified: generate_jwt(data, secret, lifetime_seconds, algorithm)
        """
        token_data = {
            "sub": str(user.id),
            "email": user.email,
            "aud": self.verification_token_audience,
        }
        return generate_jwt(
            token_data,
            self.verification_token_secret,
            self.verification_token_lifetime_seconds,
        )


async def get_user_manager(
    request: Request,
    user_db: UserDatabaseWithRoles = Depends(get_user_db),
):
    """FastAPI dependency — pulls mailer and settings off app.state."""
    mailer = request.app.state.mailer
    settings = request.app.state.users_settings
    yield UserManager(user_db, mailer, settings)
