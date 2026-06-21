"""Admin REST CRUD tests: create / update / delete."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from test_api_admin import _make_user
from users.models import User

# ---------------------------------------------------------------------------
# Admin create
# ---------------------------------------------------------------------------


class TestAdminCreate:
    @pytest.mark.anyio
    async def test_create_returns_201(self, admin_client):
        resp = await admin_client.post(
            "/api/users/admin",
            json={
                "email": "newuser@example.com",
                "password": "SecurePass1!",
                "full_name": "New User",
                "role_names": ["user"],
            },
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["email"] == "newuser@example.com"
        assert body["is_active"] is True
        assert body["is_verified"] is True
        assert body["roles"] == ["user"]

    @pytest.mark.anyio
    async def test_create_duplicate_returns_409(self, admin_client, users_db):
        await _make_user(users_db, email="taken@example.com")
        resp = await admin_client.post(
            "/api/users/admin",
            json={"email": "taken@example.com", "password": "SecurePass1!"},
        )
        assert resp.status_code == 409

    @pytest.mark.anyio
    async def test_create_weak_password_returns_400(self, admin_client):
        resp = await admin_client.post(
            "/api/users/admin",
            json={"email": "weakpw@example.com", "password": "short"},
        )
        assert resp.status_code == 400
        assert "8 characters" in resp.json()["detail"]

    @pytest.mark.anyio
    async def test_create_without_auth_is_rejected(self, anon_client):
        resp = await anon_client.post(
            "/api/users/admin",
            json={"email": "hacker@example.com", "password": "SecurePass1!"},
            follow_redirects=False,
        )
        assert resp.status_code == 401
        assert resp.json() == {"detail": "Not authenticated"}


# ---------------------------------------------------------------------------
# Admin update details
# ---------------------------------------------------------------------------


class TestAdminUpdate:
    @pytest.mark.anyio
    async def test_update_changes_email_and_name(self, admin_client, users_db):
        user = await _make_user(users_db, email="before@example.com")
        resp = await admin_client.patch(
            f"/api/users/admin/{user.id}",
            json={"email": "after@example.com", "full_name": "After Name"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["email"] == "after@example.com"
        assert body["full_name"] == "After Name"

    @pytest.mark.anyio
    async def test_update_duplicate_email_returns_409(self, admin_client, users_db):
        await _make_user(users_db, email="exists@example.com")
        target = await _make_user(users_db, email="target@example.com")
        resp = await admin_client.patch(
            f"/api/users/admin/{target.id}",
            json={"email": "exists@example.com"},
        )
        assert resp.status_code == 409

    @pytest.mark.anyio
    async def test_update_nonexistent_returns_404(self, admin_client):
        resp = await admin_client.patch(
            f"/api/users/admin/{uuid.uuid4()}",
            json={"email": "ghost@example.com"},
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_update_without_auth_is_rejected(self, anon_client):
        resp = await anon_client.patch(
            f"/api/users/admin/{uuid.uuid4()}",
            json={"email": "x@example.com"},
            follow_redirects=False,
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Admin delete
# ---------------------------------------------------------------------------


class TestAdminDelete:
    @pytest.mark.anyio
    async def test_delete_returns_204(self, admin_client, users_db):
        user = await _make_user(users_db, email="deleteme@example.com")
        resp = await admin_client.delete(f"/api/users/admin/{user.id}")
        assert resp.status_code == 204

    @pytest.mark.anyio
    async def test_delete_nonexistent_returns_404(self, admin_client):
        resp = await admin_client.delete(f"/api/users/admin/{uuid.uuid4()}")
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_delete_self_returns_400(self, admin_client, users_app):
        async with users_app.state.sm.db.session_factory() as session:
            admin = (
                await session.execute(
                    select(User).where(User.email == "admin@example.com")
                )
            ).scalar_one()
        resp = await admin_client.delete(f"/api/users/admin/{admin.id}")
        assert resp.status_code == 400

    @pytest.mark.anyio
    async def test_delete_without_auth_is_rejected(self, anon_client):
        resp = await anon_client.delete(
            f"/api/users/admin/{uuid.uuid4()}",
            follow_redirects=False,
        )
        assert resp.status_code == 401
