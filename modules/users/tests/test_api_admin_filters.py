"""Tests for /api/users/admin/* list filtering and verify endpoints."""

from __future__ import annotations

import uuid

import pytest
from test_api_admin import _make_user

# ---------------------------------------------------------------------------
# Admin list filters
# ---------------------------------------------------------------------------


class TestAdminListFilters:
    @pytest.mark.anyio
    async def test_status_filter(self, admin_client, users_db):
        from datetime import UTC, datetime

        await _make_user(users_db, email="on@x.com")
        u = await _make_user(users_db, email="off@x.com")
        u.is_active = False
        u.disabled_at = datetime.now(UTC)
        await users_db.commit()

        resp = await admin_client.get("/api/users/admin?status=disabled")
        assert resp.status_code == 200
        emails = [u["email"] for u in resp.json()]
        assert "off@x.com" in emails
        assert "on@x.com" not in emails

    @pytest.mark.anyio
    async def test_unknown_status_returns_200_unfiltered(self, admin_client, users_db):
        await _make_user(users_db, email="any@x.com")
        resp = await admin_client.get("/api/users/admin?status=bogus")
        assert resp.status_code == 200
        emails = [u["email"] for u in resp.json()]
        assert "any@x.com" in emails

    @pytest.mark.anyio
    async def test_sort_last_login_desc(self, admin_client, users_db):
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        a = await _make_user(users_db, email="alpha@x.com")
        b = await _make_user(users_db, email="beta@x.com")
        a.last_login_at = now - timedelta(days=1)
        b.last_login_at = now
        await users_db.commit()

        resp = await admin_client.get("/api/users/admin?sort=last_login_at&order=desc&per_page=50")
        assert resp.status_code == 200
        emails = [u["email"] for u in resp.json()]
        assert emails.index("beta@x.com") < emails.index("alpha@x.com")


# ---------------------------------------------------------------------------
# Admin verify
# ---------------------------------------------------------------------------


class TestAdminVerify:
    @pytest.mark.anyio
    async def test_verify_sets_flag(self, admin_client, users_db):
        user = await _make_user(users_db, email="toverify@x.com", verified=False)
        resp = await admin_client.patch(f"/api/users/admin/{user.id}/verify")
        assert resp.status_code == 200
        assert resp.json()["is_verified"] is True

    @pytest.mark.anyio
    async def test_verify_idempotent(self, admin_client, users_db):
        user = await _make_user(users_db, email="alreadyverified@x.com", verified=True)
        resp = await admin_client.patch(f"/api/users/admin/{user.id}/verify")
        assert resp.status_code == 200
        assert resp.json()["is_verified"] is True

    @pytest.mark.anyio
    async def test_verify_unknown_returns_404(self, admin_client):
        resp = await admin_client.patch(f"/api/users/admin/{uuid.uuid4()}/verify")
        assert resp.status_code == 404
