"""UserManager — handles lifecycle hooks + custom verification-token helper."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, UUIDIDMixin, exceptions
from fastapi_users.jwt import generate_jwt

from users.constants import OAUTH_REGISTRATION_REQUEST_FLAG, SESSION_USER_ID_KEY
from users.contracts.events import UserRegistered
from users.db_adapter import UserDatabaseWithRoles, get_user_db
from users.exceptions import ExternalUserNoPasswordError
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

    # ── Auth (password-credential guards) ────────────────────

    async def authenticate(self, credentials):
        """Authenticate by email + password.

        Mirrors ``BaseUserManager.authenticate`` but rejects **external (SSO)
        users**: they have ``hashed_password is None``, so there is no local
        password to verify. We still run a dummy hash to keep timing uniform
        with the user-not-found and wrong-password paths.
        """
        try:
            user = await self.get_by_email(credentials.username)
        except exceptions.UserNotExists:
            self.password_helper.hash(credentials.password)
            return None

        if user.hashed_password is None:
            self.password_helper.hash(credentials.password)
            return None

        verified, updated_password_hash = self.password_helper.verify_and_update(
            credentials.password, user.hashed_password
        )
        if not verified:
            return None
        if updated_password_hash is not None:
            await self.user_db.update(user, {"hashed_password": updated_password_hash})
        return user

    async def forgot_password(self, user: User, request: Request | None = None) -> None:
        """Skip password reset for external (SSO) users — they have no password.

        Returning silently (rather than raising) preserves the public
        forgot-password endpoint's anti-enumeration behaviour: it always
        responds the same regardless of whether the account can reset.
        """
        if user.is_external:
            return
        await super().forgot_password(user, request)

    # ── Lifecycle hooks ──────────────────────────────────────

    async def on_after_register(self, user: User, request: Request | None = None) -> None:
        # A user provisioned via OAuth (flag set by the OAuth callback before
        # find-or-create) is external: drop the random password fastapi-users
        # assigned and mark the account SSO-only. Fires only for *new* users —
        # OAuth logins that link to an existing account don't reach here.
        if request is not None and getattr(request.state, OAUTH_REGISTRATION_REQUEST_FLAG, False):
            user.hashed_password = None
            user.is_external = True
            await self.user_db.update(user, {"hashed_password": None, "is_external": True})
        await self._publish_user_registered(user, request)
        if not user.is_verified:
            # Kicks off on_after_request_verify, which sends the email
            await self.request_verify(user, request)

    async def _publish_user_registered(self, user: User, request: Request | None) -> None:
        """Emit ``UserRegistered`` on the app-wide event bus.

        CLI bootstrap and unit tests instantiate the manager without a
        request, so there's no app context from which to reach the bus —
        publication is best-effort in those cases.
        """
        if request is None:
            return
        await request.app.state.sm.event_bus.publish(
            UserRegistered(user_id=user.id, email=user.email)
        )

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
        # Bridge to AuthMiddleware: it reads session["user_id"] (not the
        # fastapi-users cookie) to identify the request principal. Setting it
        # here covers OAuth callbacks too, where there's no wrapper to do it
        # explicitly. Password / accept-invite flows already set this in their
        # wrappers — re-assigning the same value here is a harmless no-op.
        if request is not None:
            request.session[SESSION_USER_ID_KEY] = str(user.id)

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
        if user.is_external or user.hashed_password is None:
            # No local password to fingerprint — hashing None would crash.
            raise ExternalUserNoPasswordError(user.id)
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
    users = request.app.state.users
    mailer = users.mailer
    settings = users.settings
    yield UserManager(user_db, mailer, settings)
