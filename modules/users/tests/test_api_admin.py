"""Tests for /api/users/admin/* endpoints."""

from __future__ import annotations

import uuid

import pytest
from fastapi_users.password import PasswordHelper
from users.models import Role, User, UserRole

_pw = PasswordHelper()


async def _make_user(session, email, password="SecurePass1!", verified=True, role_names=None):
    from sqlalchemy import select

    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=_pw.hash(password),
        is_active=True,
        is_superuser=False,
        is_verified=verified,
    )
    session.add(user)
    await session.flush()

    if role_names:
        roles = (
            (await session.execute(select(Role).where(Role.name.in_(role_names)))).scalars().all()
        )
        for role in roles:
            session.add(UserRole(user_id=user.id, role_id=role.id))

    await session.commit()
    await session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Admin list
# ---------------------------------------------------------------------------


class TestAdminList:
    @pytest.mark.anyio
    async def test_list_without_auth_is_rejected(self, anon_client):
        resp = await anon_client.get("/api/users/admin", follow_redirects=False)
        # AuthMiddleware redirects unauthenticated non-public API paths to
        # /users/login. Preserving the 302 here so a regression to 401 or
        # pass-through is caught.
        assert resp.status_code == 302
        assert resp.headers["location"].endswith("/users/login")

    @pytest.mark.anyio
    async def test_list_as_admin_returns_200(self, admin_client, users_db):
        await _make_user(users_db, email="listed@example.com")
        resp = await admin_client.get("/api/users/admin")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        emails = [u["email"] for u in body]
        assert "listed@example.com" in emails

    @pytest.mark.anyio
    async def test_list_search_filters_results(self, admin_client, users_db):
        await _make_user(users_db, email="alpha@example.com")
        await _make_user(users_db, email="beta@example.com")
        resp = await admin_client.get("/api/users/admin?q=alpha")
        assert resp.status_code == 200
        emails = [u["email"] for u in resp.json()]
        assert "alpha@example.com" in emails
        assert "beta@example.com" not in emails

    @pytest.mark.anyio
    async def test_list_pagination(self, admin_client, users_db):
        for i in range(5):
            await _make_user(users_db, email=f"page{i}@example.com")
        resp = await admin_client.get("/api/users/admin?page=1&per_page=2")
        assert resp.status_code == 200
        assert len(resp.json()) <= 2


# ---------------------------------------------------------------------------
# Admin invite
# ---------------------------------------------------------------------------


class TestAdminInvite:
    @pytest.mark.anyio
    async def test_invite_creates_user(self, admin_client, users_app):
        resp = await admin_client.post(
            "/api/users/admin/invite",
            json={"email": "invited@example.com", "full_name": "Invited User"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == "invited@example.com"
        assert body["is_verified"] is False
        assert body["is_active"] is True

    @pytest.mark.anyio
    async def test_invite_calls_mailer(self, admin_client, users_app):
        from unittest.mock import AsyncMock

        # Replace the mailer with a mock
        original_mailer = users_app.state.mailer
        mock_mailer = AsyncMock()
        mock_mailer.send_invite = AsyncMock()
        users_app.state.mailer = mock_mailer

        try:
            resp = await admin_client.post(
                "/api/users/admin/invite",
                json={"email": "mailertest@example.com"},
            )
            assert resp.status_code == 201
            mock_mailer.send_invite.assert_awaited_once()
            call_args = mock_mailer.send_invite.call_args[0]
            assert call_args[0] == "mailertest@example.com"  # email
        finally:
            users_app.state.mailer = original_mailer

    @pytest.mark.anyio
    async def test_invite_without_auth_is_rejected(self, anon_client):
        resp = await anon_client.post(
            "/api/users/admin/invite",
            json={"email": "hacker@example.com"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert resp.headers["location"].endswith("/users/login")


# ---------------------------------------------------------------------------
# Admin disable / enable
# ---------------------------------------------------------------------------


class TestAdminDisableEnable:
    @pytest.mark.anyio
    async def test_disable_sets_is_active_false(self, admin_client, users_db):
        user = await _make_user(users_db, email="todisable@example.com")
        resp = await admin_client.patch(f"/api/users/admin/{user.id}/disable")
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_active"] is False
        assert body["disabled_at"] is not None

    @pytest.mark.anyio
    async def test_enable_sets_is_active_true(self, admin_client, users_db):
        user = await _make_user(users_db, email="toenable@example.com")
        # Disable first
        await admin_client.patch(f"/api/users/admin/{user.id}/disable")
        # Then enable
        resp = await admin_client.patch(f"/api/users/admin/{user.id}/enable")
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_active"] is True
        assert body["disabled_at"] is None

    @pytest.mark.anyio
    async def test_disable_nonexistent_returns_404(self, admin_client):
        resp = await admin_client.patch(f"/api/users/admin/{uuid.uuid4()}/disable")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Admin set roles
# ---------------------------------------------------------------------------


class TestAdminSetRoles:
    @pytest.mark.anyio
    async def test_set_roles_replaces_roles(self, admin_client, users_db):
        user = await _make_user(users_db, email="roletest@example.com", role_names=["admin"])
        resp = await admin_client.put(
            f"/api/users/admin/{user.id}/roles",
            json={"role_names": ["user"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["roles"] == ["user"]

    @pytest.mark.anyio
    async def test_set_empty_roles_clears_roles(self, admin_client, users_db):
        user = await _make_user(users_db, email="clearroles@example.com", role_names=["admin"])
        resp = await admin_client.put(
            f"/api/users/admin/{user.id}/roles",
            json={"role_names": []},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["roles"] == []

    @pytest.mark.anyio
    async def test_set_roles_without_auth_is_rejected(self, anon_client):
        resp = await anon_client.put(
            f"/api/users/admin/{uuid.uuid4()}/roles",
            json={"role_names": ["admin"]},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert resp.headers["location"].endswith("/users/login")
