"""Tests for /api/users/auth/* endpoints.

Covers: login wrapper, accept-invite, register gating, rate-limit integration.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi_users.password import PasswordHelper
from users.models import User

_pw = PasswordHelper()


def _hash(plain: str) -> str:
    return _pw.hash(plain)


async def _make_user(session, email, password, verified=True, full_name=None):

    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=_hash(password),
        is_active=True,
        is_superuser=False,
        is_verified=verified,
        full_name=full_name,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Login wrapper
# ---------------------------------------------------------------------------


class TestLogin:
    @pytest.mark.anyio
    async def test_bad_credentials_returns_400(self, anon_client, users_db):
        await _make_user(users_db, email="ok@example.com", password="SecurePass1!")
        resp = await anon_client.post(
            "/api/users/auth/login",
            data={"username": "ok@example.com", "password": "WRONG_PASSWORD"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "LOGIN_BAD_CREDENTIALS"

    @pytest.mark.anyio
    async def test_nonexistent_user_returns_400(self, anon_client):
        resp = await anon_client.post(
            "/api/users/auth/login",
            data={"username": "nobody@example.com", "password": "SecurePass1!"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "LOGIN_BAD_CREDENTIALS"

    @pytest.mark.anyio
    async def test_unverified_user_returns_400(self, anon_client, users_db):
        await _make_user(
            users_db, email="unverified@example.com", password="SecurePass1!", verified=False
        )
        resp = await anon_client.post(
            "/api/users/auth/login",
            data={"username": "unverified@example.com", "password": "SecurePass1!"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "LOGIN_USER_NOT_VERIFIED"

    @pytest.mark.anyio
    async def test_valid_login_sets_cookie(self, anon_client, users_db):
        await _make_user(users_db, email="valid@example.com", password="SecurePass1!")
        resp = await anon_client.post(
            "/api/users/auth/login",
            data={"username": "valid@example.com", "password": "SecurePass1!"},
        )
        assert resp.status_code == 204
        assert "sm_auth" in resp.cookies

    @pytest.mark.anyio
    async def test_valid_login_writes_session_user_id(self, anon_client, users_db):
        """Login must write session['user_id'] for future AuthMiddleware use."""
        import json
        from base64 import b64decode

        from itsdangerous import TimestampSigner

        user = await _make_user(users_db, email="session@example.com", password="SecurePass1!")
        resp = await anon_client.post(
            "/api/users/auth/login",
            data={"username": "session@example.com", "password": "SecurePass1!"},
        )
        assert resp.status_code == 204

        # Verify session cookie contains user_id
        raw = resp.cookies.get("session")
        assert raw is not None
        # The itsdangerous signer uses base64url — strip the sig suffix
        signer = TimestampSigner("test-secret-key")
        unsigned = signer.unsign(raw).decode()
        payload = json.loads(b64decode(unsigned).decode())
        assert "user_id" in payload
        assert payload["user_id"] == str(user.id)


# ---------------------------------------------------------------------------
# Accept-invite
# ---------------------------------------------------------------------------


class TestAcceptInvite:
    @pytest.mark.anyio
    async def test_bad_token_returns_400(self, anon_client):
        resp = await anon_client.post(
            "/api/users/auth/accept-invite",
            json={"token": "bad.token.here", "password": "NewSecurePass1!"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "INVITE_BAD_TOKEN"

    @pytest.mark.anyio
    async def test_valid_invite_verifies_and_logs_in(self, anon_client, users_db, users_app):
        """Full flow: create unverified user, mint token, accept-invite, get cookie."""
        from unittest.mock import AsyncMock, MagicMock

        from users.db_adapter import UserDatabaseWithRoles
        from users.manager import UserManager
        from users.models import User

        # Create unverified user
        await _make_user(
            users_db, email="invited@example.com", password="OldUnusable1!", verified=False
        )

        # Mint a verify token using the manager
        settings = users_app.state.users.settings
        fake_mailer = MagicMock()
        fake_mailer.send_invite = AsyncMock()
        fake_mailer.send_verification = AsyncMock()
        fake_mailer.send_password_reset = AsyncMock()

        user_db = UserDatabaseWithRoles(users_db, User)
        manager = UserManager(user_db, fake_mailer, settings)
        # Reload the user with the manager to get a proper User object
        fetched = await user_db.get_by_email("invited@example.com")
        token = manager.mint_invite_token(fetched)

        resp = await anon_client.post(
            "/api/users/auth/accept-invite",
            json={"token": token, "password": "NewSecurePass1!"},
        )
        assert resp.status_code == 204
        assert "sm_auth" in resp.cookies


# ---------------------------------------------------------------------------
# Register gating
# ---------------------------------------------------------------------------


class TestRegisterGating:
    @pytest.mark.anyio
    async def test_register_not_mounted_when_signup_disabled(self, anon_client):
        """POST /api/users/auth/register should 404 when allow_signup=False."""
        resp = await anon_client.post(
            "/api/users/auth/register",
            json={"email": "new@example.com", "password": "SecurePass1!"},
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_register_mounted_when_signup_enabled(self, anon_client_signup):
        """POST /api/users/auth/register should 201 when allow_signup=True."""
        resp = await anon_client_signup.post(
            "/api/users/auth/register",
            json={"email": "newuser@example.com", "password": "SecurePass1!"},
        )
        # 201 Created from fastapi-users register router
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == "newuser@example.com"
        assert body["is_verified"] is False


# ---------------------------------------------------------------------------
# Throughput limit on shared auth side-effect endpoints
# ---------------------------------------------------------------------------


class TestAuthThroughputLimit:
    @pytest.mark.anyio
    async def test_forgot_password_rate_limited_after_threshold(
        self, anon_client, users_app, users_db
    ):
        """After the configured attempt budget, /forgot-password returns 429."""
        from users.auth_local.rate_limit import ThroughputLimiter

        # Tighten the limit for the test so we don't need to hit 10 real endpoints
        users_app.state.users.auth_throughput_limiter = ThroughputLimiter(
            max_attempts=2, window_seconds=60
        )

        # Use a real email so the first few attempts exercise the real code path
        await _make_user(users_db, email="throttle@example.com", password="SecurePass1!")

        payload = {"email": "throttle@example.com"}
        # 2 within budget
        r1 = await anon_client.post("/api/users/auth/forgot-password", json=payload)
        r2 = await anon_client.post("/api/users/auth/forgot-password", json=payload)
        assert r1.status_code in (200, 202)
        assert r2.status_code in (200, 202)

        # 3rd is throttled
        r3 = await anon_client.post("/api/users/auth/forgot-password", json=payload)
        assert r3.status_code == 429
