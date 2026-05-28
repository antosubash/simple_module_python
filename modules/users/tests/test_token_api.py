"""Tests for bearer token endpoints: /api/users/auth/token*.

Covers: login via email+password, refresh rotation, revoke, and error paths.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi_users.password import PasswordHelper
from users.models import User

_pw = PasswordHelper()


def _hash(plain: str) -> str:
    return _pw.hash(plain)


async def _seed_user(session, email="api@example.com", password="SecurePass1!"):
    """Create a verified, active user for token tests."""
    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=_hash(password),
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# POST /api/users/auth/token — login
# ---------------------------------------------------------------------------


class TestTokenLogin:
    @pytest.mark.anyio
    async def test_invalid_email_returns_401(self, anon_client):
        resp = await anon_client.post(
            "/api/users/auth/token",
            json={"email": "nobody@example.com", "password": "whatever"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid credentials"

    @pytest.mark.anyio
    async def test_wrong_password_returns_401(self, anon_client, users_db):
        await _seed_user(users_db)
        resp = await anon_client.post(
            "/api/users/auth/token",
            json={"email": "api@example.com", "password": "WRONG"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid credentials"

    @pytest.mark.anyio
    async def test_inactive_user_returns_401(self, anon_client, users_db):
        user = await _seed_user(users_db, email="inactive@example.com")
        user.is_active = False
        await users_db.commit()

        resp = await anon_client.post(
            "/api/users/auth/token",
            json={"email": "inactive@example.com", "password": "SecurePass1!"},
        )
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_valid_credentials_returns_token_pair(self, anon_client, users_db):
        await _seed_user(users_db)
        resp = await anon_client.post(
            "/api/users/auth/token",
            json={"email": "api@example.com", "password": "SecurePass1!"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"]
        assert body["refresh_token"]
        assert body["expires_in"] > 0


# ---------------------------------------------------------------------------
# POST /api/users/auth/token/refresh
# ---------------------------------------------------------------------------


class TestTokenRefresh:
    @pytest.mark.anyio
    async def test_invalid_uuid_returns_401(self, anon_client):
        resp = await anon_client.post(
            "/api/users/auth/token/refresh",
            json={"refresh_token": "not-a-uuid"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid refresh token"

    @pytest.mark.anyio
    async def test_nonexistent_token_returns_401(self, anon_client):
        resp = await anon_client.post(
            "/api/users/auth/token/refresh",
            json={"refresh_token": str(uuid.uuid4())},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid or expired refresh token"

    @pytest.mark.anyio
    async def test_valid_refresh_rotates_tokens(self, anon_client, users_db):
        """Login, then refresh — old refresh revoked, new pair returned."""
        await _seed_user(users_db)
        login = await anon_client.post(
            "/api/users/auth/token",
            json={"email": "api@example.com", "password": "SecurePass1!"},
        )
        assert login.status_code == 200
        old_refresh = login.json()["refresh_token"]

        refresh_resp = await anon_client.post(
            "/api/users/auth/token/refresh",
            json={"refresh_token": old_refresh},
        )
        assert refresh_resp.status_code == 200
        new_body = refresh_resp.json()
        assert new_body["access_token"]
        assert new_body["refresh_token"] != old_refresh

        # Old refresh token should now be revoked
        reuse = await anon_client.post(
            "/api/users/auth/token/refresh",
            json={"refresh_token": old_refresh},
        )
        assert reuse.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/users/auth/token — revoke
# ---------------------------------------------------------------------------


class TestTokenRevoke:
    @pytest.mark.anyio
    async def test_invalid_format_returns_400(self, anon_client):
        resp = await anon_client.request(
            "DELETE",
            "/api/users/auth/token",
            json={"refresh_token": "garbage"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid token format"

    @pytest.mark.anyio
    async def test_nonexistent_token_returns_ok(self, anon_client):
        """Revoking a non-existent token is idempotent — still returns ok."""
        resp = await anon_client.request(
            "DELETE",
            "/api/users/auth/token",
            json={"refresh_token": str(uuid.uuid4())},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    @pytest.mark.anyio
    async def test_revoke_makes_refresh_unusable(self, anon_client, users_db):
        """After revoking, the refresh token can no longer be used."""
        await _seed_user(users_db)
        login = await anon_client.post(
            "/api/users/auth/token",
            json={"email": "api@example.com", "password": "SecurePass1!"},
        )
        rt = login.json()["refresh_token"]

        # Revoke
        revoke_resp = await anon_client.request(
            "DELETE",
            "/api/users/auth/token",
            json={"refresh_token": rt},
        )
        assert revoke_resp.status_code == 200

        # Attempt refresh — should fail
        refresh_resp = await anon_client.post(
            "/api/users/auth/token/refresh",
            json={"refresh_token": rt},
        )
        assert refresh_resp.status_code == 401
