"""Resending an invite from the users table.

An invite that never arrived is the most common reason a row sits in the
"invited" state forever, and until now the only cure was deleting the account
and inviting again. Resending has to mint a *fresh* token and move
``invited_at`` forward, or the row would keep advertising the expiry of the
message nobody received.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import pytest

_INVITE = "/api/users/admin/invite"


async def _invite(client, email: str) -> str:
    resp = await client.post(_INVITE, json={"email": email, "role_names": []})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _set_invited_at(users_db, user_id: str, when: datetime) -> None:
    import uuid

    from sqlalchemy import update
    from users.models import User

    await users_db.execute(
        update(User).where(User.id == uuid.UUID(user_id)).values(invited_at=when)
    )
    await users_db.commit()


class _SpyMailer:
    """A mailer that reports itself as delivering, and records the send.

    Implements the whole protocol: creating and re-inviting go through
    ``on_after_register``/verification paths that call the other two methods.
    """

    delivers_email = True

    def __init__(self) -> None:
        self.invites: list[tuple[str, str]] = []

    async def send_verification(self, email: str, token: str) -> None:
        pass

    async def send_password_reset(self, email: str, token: str) -> None:
        pass

    async def send_invite(
        self, email: str, token: str, invited_by_name: str, message: str | None = None
    ) -> None:
        self.invites.append((email, token))


@pytest.fixture
def spy_mailer(users_app):
    original = users_app.state.users.mailer
    spy = _SpyMailer()
    users_app.state.users.mailer = spy
    yield spy
    users_app.state.users.mailer = original


class TestResendInvite:
    @pytest.mark.anyio
    async def test_resend_accepts_and_mails_again(self, admin_client, spy_mailer):
        user_id = await _invite(admin_client, "again@example.com")

        resp = await admin_client.post(f"/api/users/admin/{user_id}/resend-invite")

        assert resp.status_code == 202, resp.text
        assert resp.json()["status"] == "sent"
        assert [email for email, _ in spy_mailer.invites] == [
            "again@example.com",
            "again@example.com",
        ]
        assert spy_mailer.invites[-1][1]

    @pytest.mark.anyio
    async def test_resend_refreshes_invited_at(self, admin_client, users_db):
        user_id = await _invite(admin_client, "stale@example.com")
        old = datetime.now(UTC) - timedelta(days=6)
        await _set_invited_at(users_db, user_id, old)

        resp = await admin_client.post(f"/api/users/admin/{user_id}/resend-invite")
        assert resp.status_code == 202, resp.text

        rows = await admin_client.get(
            "/admin/users/", headers={"X-Inertia": "true", "Accept": "application/json"}
        )
        row = next(u for u in rows.json()["props"]["users"] if u["email"] == "stale@example.com")
        # SQLite hands back naive datetimes for a tz-aware column, Postgres
        # aware ones — compare on the wall clock either way.
        refreshed = datetime.fromisoformat(row["invited_at"]).replace(tzinfo=None)
        assert refreshed > old.replace(tzinfo=None)

    @pytest.mark.anyio
    async def test_resend_hands_back_a_link_when_mail_cannot_be_delivered(self, admin_client):
        """The console mailer delivers nothing, so the admin needs the URL."""
        user_id = await _invite(admin_client, "console@example.com")
        resp = await admin_client.post(f"/api/users/admin/{user_id}/resend-invite")
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["status"] == "link"
        assert "/users/invite/accept?token=" in (body["link"] or "")

    @pytest.mark.anyio
    async def test_resend_refuses_for_an_already_verified_account(self, admin_client, users_db):
        from test_api_admin import _make_user

        user = await _make_user(users_db, email="settled@example.com", verified=True)
        resp = await admin_client.post(f"/api/users/admin/{user.id}/resend-invite")
        assert resp.status_code == 409, resp.text

    @pytest.mark.anyio
    async def test_resend_404s_for_an_unknown_user(self, admin_client):
        resp = await admin_client.post(
            "/api/users/admin/00000000-0000-0000-0000-0000000000ff/resend-invite"
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_resend_requires_the_manage_permission(self, user_client):
        resp = await user_client.post(
            "/api/users/admin/00000000-0000-0000-0000-0000000000ff/resend-invite"
        )
        assert resp.status_code == 403


class TestInviteTokenClaims:
    @pytest.mark.anyio
    async def test_invite_token_names_the_inviter(self, admin_client, users_app, caplog):
        """The accept-invite card says who invited you; the claim carries it."""
        import jwt

        with caplog.at_level(logging.INFO, logger="users.mailer"):
            await _invite(admin_client, "whosent@example.com")
        link = next(r for r in caplog.records if r.getMessage() == "users.invite.email").link
        token = link.split("token=", 1)[1]

        payload = jwt.decode(
            token,
            users_app.state.users.settings.verification_token_secret,
            algorithms=["HS256"],
            audience="fastapi-users:verify",
        )
        assert payload["invited_by"] == "Test Admin"
        assert "exp" in payload
