"""UserManager — handles lifecycle hooks + custom verification-token helper."""

from __future__ import annotations

import asyncio
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
        self.reset_password_token_lifetime_seconds = settings.reset_password_token_lifetime_seconds
        self.verification_token_lifetime_seconds = settings.verification_token_lifetime_seconds

    # ── Password policy ──────────────────────────────────────

    async def validate_password(self, password: str, user) -> None:
        if len(password) < 8:
            raise exceptions.InvalidPasswordException(
                reason="Password must be at least 8 characters"
            )
        if password.lower() in user.email.lower():
            raise exceptions.InvalidPasswordException(reason="Password cannot contain your email")
        if password.isdigit():
            raise exceptions.InvalidPasswordException(reason="Password cannot be all numbers")

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

    # ── Token helpers (no email side-effect) ─────────────────

    async def generate_verification_token(self, user: User) -> str:
        """Mint a verify-audience JWT without firing on_after_request_verify.

        Used by the admin-invite flow: the verify-token primitive is reused
        for invites, but the email template differs. request_verify() couples
        token generation with email send — this decouples them.
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

    async def generate_reset_password_token(self, user: User) -> str:
        """Mint a reset-audience JWT without firing on_after_forgot_password.

        Shape matches ``BaseUserManager.forgot_password``: the payload includes
        ``password_fgpt`` (a bcrypt of the current hashed_password) so the token
        invalidates when the password changes. Used by the admin
        reset-password-link endpoint, where the admin copies the link instead
        of triggering an email.

        The fingerprint must be bcrypt-style because the stock
        ``reset_password`` path in fastapi-users verifies it with
        ``password_helper.verify_and_update``. Bcrypt is CPU-bound (~100ms at
        default rounds) so we offload it to a worker thread — otherwise a
        single admin action would stall the event loop for other requests.
        """
        fingerprint = await asyncio.to_thread(self.password_helper.hash, user.hashed_password)
        token_data = {
            "sub": str(user.id),
            "password_fgpt": fingerprint,
            "aud": self.reset_password_token_audience,
        }
        return generate_jwt(
            token_data,
            self.reset_password_token_secret,
            self.reset_password_token_lifetime_seconds,
        )


async def get_user_manager(
    request: Request,
    user_db: UserDatabaseWithRoles = Depends(get_user_db),
):
    """FastAPI dependency — pulls mailer and settings off app.state."""
    mailer = request.app.state.mailer
    settings = request.app.state.users_settings
    yield UserManager(user_db, mailer, settings)
