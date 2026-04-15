"""End-to-end invite flow tests.

Admin invites → token captured from ConsoleMailer log → accept-invite
with that token + password → new user can log in.
"""

from __future__ import annotations

import logging

import pytest


class TestInviteFlow:
    @pytest.mark.anyio
    async def test_full_invite_flow(self, admin_client, anon_client, caplog):
        """Admin invites user → token from logs → accept-invite → login."""
        # Step 1: Admin sends invite
        with caplog.at_level(logging.INFO, logger="users.mailer"):
            resp = await admin_client.post(
                "/api/users/admin/invite",
                json={
                    "email": "newbie@example.com",
                    "full_name": "New User",
                    "role_names": ["user"],
                },
            )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["email"] == "newbie@example.com"
        assert body["is_verified"] is False

        # Step 2: Extract token from ConsoleMailer log record
        invite_records = [
            r for r in caplog.records if r.getMessage() == "users.invite.email"
        ]
        assert len(invite_records) == 1, (
            f"Expected 1 invite log record, got {len(invite_records)}: {caplog.records}"
        )
        link = invite_records[0].link  # type: ignore[attr-defined]
        # Link format: http://testserver/users/invite/accept?token=<token>
        token = link.split("token=", 1)[1]
        assert len(token) > 20

        # Step 3: Accept invite with the token and a new password
        resp = await anon_client.post(
            "/api/users/auth/accept-invite",
            json={"token": token, "password": "FreshSecure1!"},
        )
        assert resp.status_code == 204, resp.text
        assert "sm_auth" in resp.cookies

        # Step 4: New user can log in with the new password
        resp = await anon_client.post(
            "/api/users/auth/login",
            data={"username": "newbie@example.com", "password": "FreshSecure1!"},
        )
        assert resp.status_code == 204, resp.text
        assert "sm_auth" in resp.cookies

    @pytest.mark.anyio
    async def test_accept_invite_with_stale_token_fails(self, anon_client):
        """A completely invalid token should return 400 INVITE_BAD_TOKEN."""
        resp = await anon_client.post(
            "/api/users/auth/accept-invite",
            json={"token": "not.a.real.token", "password": "FreshSecure1!"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "INVITE_BAD_TOKEN"

    @pytest.mark.anyio
    async def test_accept_invite_weak_password_fails(
        self, admin_client, anon_client, caplog
    ):
        """Weak password during accept-invite should return 400."""
        with caplog.at_level(logging.INFO, logger="users.mailer"):
            await admin_client.post(
                "/api/users/admin/invite",
                json={"email": "weakpw@example.com"},
            )

        invite_records = [
            r for r in caplog.records if r.getMessage() == "users.invite.email"
        ]
        token = invite_records[0].link.split("token=", 1)[1]  # type: ignore[attr-defined]

        resp = await anon_client.post(
            "/api/users/auth/accept-invite",
            json={"token": token, "password": "short"},
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert "INVALID_PASSWORD" in detail or "password" in detail.lower()

    @pytest.mark.anyio
    async def test_invited_user_cannot_login_before_accepting(
        self, admin_client, anon_client
    ):
        """Unverified invited user cannot log in before accepting invite."""
        await admin_client.post(
            "/api/users/admin/invite",
            json={"email": "waiting@example.com"},
        )
        # Try to log in with the unusable password (we don't know it) — just
        # confirm that any attempt fails, not that it's specifically 400 vs 401.
        resp = await anon_client.post(
            "/api/users/auth/login",
            data={"username": "waiting@example.com", "password": "anything"},
        )
        assert resp.status_code in (400,)
