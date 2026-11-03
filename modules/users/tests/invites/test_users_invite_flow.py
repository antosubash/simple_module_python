"""End-to-end invite flow tests.

Admin invites → token captured from ConsoleMailer log → accept-invite
with that token + password → new user can log in.
"""

from __future__ import annotations

import re

import pytest
from fastapi_users.jwt import generate_jwt
from sqlalchemy import select
from users.manager import UserManager
from users.models import User


class TestInviteFlow:
    @pytest.mark.anyio
    async def test_full_invite_flow(self, admin_client, anon_client, captured_mail):
        """Admin invites user → token from logs → accept-invite → login."""
        # Step 1: Admin sends invite
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

        # Step 2: Extract token from the captured invite mail
        sent = [m for m in captured_mail.to("newbie@example.com") if "invited you" in m.subject]
        assert len(sent) == 1, f"Expected 1 invite mail, got {captured_mail.messages}"
        # Link format: http://testserver/users/invite/accept?token=<token>
        token = re.search(r"token=(\S+)", sent[0].text).group(1)
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
        self, admin_client, anon_client, captured_mail, users_app
    ):
        """Rejected passwords leave the durable invitation usable for a retry (#763)."""
        await admin_client.post(
            "/api/users/admin/invite",
            json={"email": "weakpw@example.com"},
        )

        token = re.search(
            r"token=(\S+)",
            next(
                m for m in captured_mail.to("weakpw@example.com") if "invited you" in m.subject
            ).text,
        ).group(1)

        async with users_app.state.sm.db.session_factory() as db:
            user = await db.scalar(select(User).where(User.email == "weakpw@example.com"))
            original_password = user.hashed_password
            user_id = user.id

        resp = await anon_client.post(
            "/api/users/auth/accept-invite",
            json={"token": token, "password": "short"},
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert detail.startswith("INVALID_PASSWORD:")

        async with users_app.state.sm.db.session_factory() as db:
            user = await db.get(User, user_id)
            assert user.is_verified is False
            assert user.hashed_password == original_password

        resp = await anon_client.post(
            "/api/users/auth/accept-invite",
            json={"token": token, "password": "FreshSecure1!"},
        )
        assert resp.status_code == 204, resp.text

        async with users_app.state.sm.db.session_factory() as db:
            user = await db.get(User, user_id)
            assert user.is_verified is True
            assert user.hashed_password != original_password

    @pytest.mark.anyio
    async def test_invited_user_cannot_login_before_accepting(self, admin_client, anon_client):
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

    @pytest.mark.anyio
    async def test_accept_invite_hooks_see_password_and_verification_together(
        self, admin_client, anon_client, captured_mail, users_app, monkeypatch
    ):
        """Both hooks run in order, after the complete acceptance is durable."""
        await admin_client.post("/api/users/admin/invite", json={"email": "hooks@example.com"})
        token = re.search(r"token=(\S+)", captured_mail.to("hooks@example.com")[-1].text).group(1)
        seen = []

        async def after_verify(manager, user, request):
            async with users_app.state.sm.db.session_factory() as db:
                durable = await db.get(User, user.id)
                assert durable.is_verified is True
                assert manager.password_helper.verify_and_update(
                    "FreshSecure1!", durable.hashed_password
                )[0]
            seen.append("verify")

        async def after_update(manager, user, changes, request):
            assert changes == {"password": "FreshSecure1!", "full_name": "Invitee"}
            seen.append("update")

        monkeypatch.setattr(UserManager, "on_after_verify", after_verify)
        monkeypatch.setattr(UserManager, "on_after_update", after_update)
        resp = await anon_client.post(
            "/api/users/auth/accept-invite",
            json={"token": token, "password": "FreshSecure1!", "full_name": " Invitee "},
        )
        assert resp.status_code == 204, resp.text
        assert seen == ["verify", "update"]

    @pytest.mark.anyio
    @pytest.mark.parametrize(
        "claims, lifetime",
        [
            ({}, -1),
            ({"aud": "fastapi-users:reset"}, 3600),
            ({"sub": "not-a-uuid"}, 3600),
            ({"sub": "00000000-0000-0000-0000-000000000000"}, 3600),
            ({"email": "missing@example.com"}, 3600),
            ({"email": None}, 3600),
            ({"sub": None}, 3600),
        ],
    )
    async def test_accept_invite_rejects_invalid_claims(
        self, admin_client, anon_client, captured_mail, users_app, claims, lifetime
    ):
        """Only a current verify token matching both account ID and email can write."""
        resp = await admin_client.post(
            "/api/users/admin/invite", json={"email": "claims@example.com"}
        )
        token = generate_jwt(
            {
                "sub": resp.json()["id"],
                "email": "claims@example.com",
                "aud": UserManager.verification_token_audience,
                **claims,
            },
            users_app.state.users.settings.verification_token_secret,
            lifetime,
        )
        resp = await anon_client.post(
            "/api/users/auth/accept-invite", json={"token": token, "password": "FreshSecure1!"}
        )
        assert resp.status_code == 400, resp.text
        assert resp.json()["detail"] == "INVITE_BAD_TOKEN"

    @pytest.mark.anyio
    async def test_accept_invite_token_is_single_use(
        self, admin_client, anon_client, captured_mail
    ):
        """A second acceptance with the same token is refused, not re-applied."""
        await admin_client.post("/api/users/admin/invite", json={"email": "once@example.com"})
        token = re.search(r"token=(\S+)", captured_mail.to("once@example.com")[-1].text).group(1)
        body = {"token": token, "password": "FreshSecure1!"}
        assert (
            await anon_client.post("/api/users/auth/accept-invite", json=body)
        ).status_code == 204
        again = await anon_client.post(
            "/api/users/auth/accept-invite", json={**body, "password": "Another-Secure2!"}
        )
        assert again.status_code == 400
        assert again.json()["detail"] == "INVITE_BAD_TOKEN"

    @pytest.mark.anyio
    async def test_rejected_password_fires_no_hooks(
        self, admin_client, anon_client, captured_mail, monkeypatch
    ):
        """Neither lifecycle hook runs for an acceptance that writes nothing."""
        await admin_client.post("/api/users/admin/invite", json={"email": "nohooks@example.com"})
        token = re.search(r"token=(\S+)", captured_mail.to("nohooks@example.com")[-1].text).group(1)
        seen = []

        async def record(*args, **kwargs):
            seen.append(args)

        monkeypatch.setattr(UserManager, "on_after_verify", record)
        monkeypatch.setattr(UserManager, "on_after_update", record)
        resp = await anon_client.post(
            "/api/users/auth/accept-invite", json={"token": token, "password": "short"}
        )
        assert resp.status_code == 400
        assert seen == []
