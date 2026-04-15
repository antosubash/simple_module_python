"""Tests for UserManager."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi_users import exceptions
from fastapi_users.jwt import decode_jwt

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_settings():
    from users.settings import UsersSettings

    return UsersSettings(
        verification_token_secret="test-verify-secret-at-least-32-bytes-long",
        reset_password_token_secret="test-reset-secret-at-least-32-bytes-long",
        verification_token_lifetime_seconds=3600,
        reset_password_token_lifetime_seconds=1800,
    )


@pytest.fixture
def fake_mailer():
    mailer = MagicMock()
    mailer.send_password_reset = AsyncMock()
    mailer.send_verification = AsyncMock()
    mailer.send_invite = AsyncMock()
    return mailer


@pytest.fixture
def fake_user():
    """Minimal user-like object for manager tests."""
    user = MagicMock()
    user.id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    user.email = "test@example.com"
    user.is_verified = False
    user.last_login_at = None
    return user


@pytest.fixture
def fake_user_db():
    db = MagicMock()
    db.update = AsyncMock(return_value=None)
    return db


@pytest.fixture
def manager(fake_settings, fake_mailer, fake_user_db):
    from users.manager import UserManager

    return UserManager(fake_user_db, fake_mailer, fake_settings)


# ---------------------------------------------------------------------------
# validate_password
# ---------------------------------------------------------------------------


class TestValidatePassword:
    @pytest.mark.anyio
    async def test_rejects_too_short(self, manager, fake_user):
        with pytest.raises(exceptions.InvalidPasswordException) as exc_info:
            await manager.validate_password("short", fake_user)
        assert "8 characters" in exc_info.value.reason

    @pytest.mark.anyio
    async def test_rejects_exactly_7_chars(self, manager, fake_user):
        with pytest.raises(exceptions.InvalidPasswordException):
            await manager.validate_password("1234567", fake_user)

    @pytest.mark.anyio
    async def test_accepts_exactly_8_chars(self, manager, fake_user):
        # Should not raise — fake_user.email is "test@example.com"
        await manager.validate_password("abcde123", fake_user)

    @pytest.mark.anyio
    async def test_rejects_all_digits(self, manager, fake_user):
        with pytest.raises(exceptions.InvalidPasswordException) as exc_info:
            await manager.validate_password("12345678", fake_user)
        assert "all numbers" in exc_info.value.reason

    @pytest.mark.anyio
    async def test_rejects_password_containing_email(self, manager, fake_user):
        # fake_user.email = "test@example.com"; password contains the email
        with pytest.raises(exceptions.InvalidPasswordException) as exc_info:
            await manager.validate_password("test@example.com", fake_user)
        assert "email" in exc_info.value.reason

    @pytest.mark.anyio
    async def test_rejects_password_containing_email_case_insensitive(self, manager, fake_user):
        with pytest.raises(exceptions.InvalidPasswordException) as exc_info:
            await manager.validate_password("TEST@EXAMPLE.COM", fake_user)
        assert "email" in exc_info.value.reason

    @pytest.mark.anyio
    async def test_accepts_valid_password(self, manager, fake_user):
        await manager.validate_password("SecurePass1!", fake_user)


# ---------------------------------------------------------------------------
# Lifecycle hooks
# ---------------------------------------------------------------------------


class TestOnAfterForgotPassword:
    @pytest.mark.anyio
    async def test_calls_mailer_send_password_reset(self, manager, fake_mailer, fake_user):
        await manager.on_after_forgot_password(fake_user, "reset-token")
        fake_mailer.send_password_reset.assert_awaited_once_with(fake_user.email, "reset-token")


class TestOnAfterRequestVerify:
    @pytest.mark.anyio
    async def test_calls_mailer_send_verification(self, manager, fake_mailer, fake_user):
        await manager.on_after_request_verify(fake_user, "verify-token")
        fake_mailer.send_verification.assert_awaited_once_with(fake_user.email, "verify-token")


class TestOnAfterLogin:
    @pytest.mark.anyio
    async def test_updates_last_login_at(self, manager, fake_user_db, fake_user):
        before = datetime.now(UTC)
        await manager.on_after_login(fake_user)
        after = datetime.now(UTC)

        # last_login_at should have been set on the user object
        assert fake_user.last_login_at is not None
        assert before <= fake_user.last_login_at <= after

    @pytest.mark.anyio
    async def test_calls_user_db_update_with_dict(self, manager, fake_user_db, fake_user):
        await manager.on_after_login(fake_user)

        fake_user_db.update.assert_awaited_once()
        call_args = fake_user_db.update.call_args
        # Second positional arg must be a dict with last_login_at
        update_dict = call_args[0][1]
        assert "last_login_at" in update_dict


# ---------------------------------------------------------------------------
# generate_verification_token
# ---------------------------------------------------------------------------


class TestGenerateVerificationToken:
    @pytest.mark.anyio
    async def test_returns_decodable_jwt(self, manager, fake_settings, fake_user):
        token = await manager.generate_verification_token(fake_user)

        assert isinstance(token, str)
        assert len(token) > 20  # basic sanity

    @pytest.mark.anyio
    async def test_jwt_has_correct_audience(self, manager, fake_settings, fake_user):
        token = await manager.generate_verification_token(fake_user)

        data = decode_jwt(
            token,
            fake_settings.verification_token_secret,
            [manager.verification_token_audience],
        )
        assert data["aud"] == manager.verification_token_audience

    @pytest.mark.anyio
    async def test_jwt_has_correct_subject(self, manager, fake_settings, fake_user):
        token = await manager.generate_verification_token(fake_user)

        data = decode_jwt(
            token,
            fake_settings.verification_token_secret,
            [manager.verification_token_audience],
        )
        assert data["sub"] == str(fake_user.id)

    @pytest.mark.anyio
    async def test_jwt_has_email(self, manager, fake_settings, fake_user):
        token = await manager.generate_verification_token(fake_user)

        data = decode_jwt(
            token,
            fake_settings.verification_token_secret,
            [manager.verification_token_audience],
        )
        assert data["email"] == fake_user.email

    @pytest.mark.anyio
    async def test_jwt_audience_matches_verify_audience(self, manager, fake_user):
        """Token audience must match what fastapi-users POST /verify expects."""
        assert manager.verification_token_audience == "fastapi-users:verify"
        token = await manager.generate_verification_token(fake_user)
        # Decodable with the verify audience — no exception means it passes
        decode_jwt(
            token,
            manager.verification_token_secret,
            ["fastapi-users:verify"],
        )
