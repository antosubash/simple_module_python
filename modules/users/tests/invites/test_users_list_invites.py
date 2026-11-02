"""An invited account and a self-signup are not the same thing.

Both sit in the table as ``is_active and not is_verified``, so the list used to
label them identically. They call for opposite actions — one is waiting on an
email that may never have arrived (resend it), the other on a person who
already has one (nothing to do) — which is why ``invited_at`` exists and why
``state`` is computed rather than derived on the client.
"""

from __future__ import annotations

import pytest

_VIEW = "/admin/users/"
_INERTIA = {"X-Inertia": "true", "Accept": "application/json"}


async def _rows_by_email(client, query: str = "") -> dict[str, dict]:
    resp = await client.get(f"{_VIEW}{query}", headers=_INERTIA)
    assert resp.status_code == 200, resp.text
    return {row["email"]: row for row in resp.json()["props"]["users"]}


class TestUserState:
    @pytest.mark.anyio
    async def test_invited_and_unverified_are_distinct(self, admin_client, users_db):
        from test_api_admin import _make_user

        await _make_user(users_db, email="selfsignup@example.com", verified=False)
        invited = await admin_client.post(
            "/api/users/admin/invite",
            json={"email": "invited@example.com", "role_names": []},
        )
        assert invited.status_code == 201, invited.text

        rows = await _rows_by_email(admin_client)
        assert rows["invited@example.com"]["state"] == "invited"
        assert rows["selfsignup@example.com"]["state"] == "unverified"
        assert rows["admin@example.com"]["state"] == "active"

    @pytest.mark.anyio
    async def test_disabled_beats_every_other_state(self, admin_client, users_db):
        from test_api_admin import _make_user

        user = await _make_user(users_db, email="gone@example.com", verified=False)
        resp = await admin_client.patch(f"/api/users/admin/{user.id}/disable")
        assert resp.status_code == 200, resp.text

        rows = await _rows_by_email(admin_client)
        assert rows["gone@example.com"]["state"] == "disabled"

    @pytest.mark.anyio
    async def test_invited_row_carries_both_timestamps(self, admin_client):
        """The row has to say "invited 2d ago · expires in 5d" on its own."""
        await admin_client.post(
            "/api/users/admin/invite",
            json={"email": "pending@example.com", "role_names": []},
        )
        row = (await _rows_by_email(admin_client))["pending@example.com"]
        assert row["invited_at"] is not None
        assert row["invite_expires_at"] is not None
        assert row["invite_expires_at"] > row["invited_at"]

    @pytest.mark.anyio
    async def test_self_signup_has_no_invite_timestamps(self, admin_client, users_db):
        from test_api_admin import _make_user

        await _make_user(users_db, email="walkin@example.com", verified=False)
        row = (await _rows_by_email(admin_client))["walkin@example.com"]
        assert row["invited_at"] is None
        assert row["invite_expires_at"] is None


class TestStatusFilter:
    """Verified folded into Status: all / active / unverified / invited / disabled."""

    @pytest.mark.anyio
    async def test_invited_filter_excludes_self_signups(self, admin_client, users_db):
        from test_api_admin import _make_user

        await _make_user(users_db, email="walkin2@example.com", verified=False)
        await admin_client.post(
            "/api/users/admin/invite",
            json={"email": "asked@example.com", "role_names": []},
        )
        rows = await _rows_by_email(admin_client, "?status=invited")
        assert set(rows) == {"asked@example.com"}

    @pytest.mark.anyio
    async def test_unverified_filter_excludes_invitees(self, admin_client, users_db):
        from test_api_admin import _make_user

        await _make_user(users_db, email="walkin3@example.com", verified=False)
        await admin_client.post(
            "/api/users/admin/invite",
            json={"email": "asked2@example.com", "role_names": []},
        )
        rows = await _rows_by_email(admin_client, "?status=unverified")
        assert set(rows) == {"walkin3@example.com"}

    @pytest.mark.anyio
    async def test_active_means_active_and_verified(self, admin_client, users_db):
        from test_api_admin import _make_user

        await _make_user(users_db, email="walkin4@example.com", verified=False)
        rows = await _rows_by_email(admin_client, "?status=active")
        assert "walkin4@example.com" not in rows
        assert "admin@example.com" in rows


class TestPendingInvitesAggregate:
    @pytest.mark.anyio
    async def test_pending_counts_invites_not_self_signups(self, admin_client, users_db):
        from test_api_admin import _make_user

        await _make_user(users_db, email="walkin5@example.com", verified=False)
        await admin_client.post(
            "/api/users/admin/invite",
            json={"email": "asked3@example.com", "role_names": []},
        )
        resp = await admin_client.get(_VIEW, headers=_INERTIA)
        aggregates = resp.json()["props"]["aggregates"]
        assert aggregates["invited"] == 1
        assert aggregates["unverified"] == 1
