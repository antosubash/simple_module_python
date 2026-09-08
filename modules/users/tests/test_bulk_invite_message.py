"""A note from the person doing the inviting.

An invite from an unfamiliar address is indistinguishable from phishing. One
line of context — "you're joining the migration project" — is what makes it
answerable, so the batch form's optional message has to reach the mail itself
rather than stopping at the API boundary.
"""

from __future__ import annotations

import logging

import pytest

_URL = "/api/users/admin/invite/bulk"


class _SpyMailer:
    """Stands in for a mailer that actually delivers, and records the call.

    Implements the whole ``Mailer`` protocol, not just ``send_invite``:
    creating an unverified account fires ``on_after_register`` first, which
    sends a verification mail, and a spy missing that method turns every
    address into a failed row for a reason that has nothing to do with the
    thing under test.
    """

    delivers_email = True

    def __init__(self) -> None:
        self.invites: list[dict[str, object]] = []

    async def send_verification(self, email: str, token: str) -> None:
        pass

    async def send_password_reset(self, email: str, token: str) -> None:
        pass

    async def send_invite(
        self,
        email: str,
        token: str,
        invited_by_name: str,
        message: str | None = None,
    ) -> None:
        self.invites.append(
            {
                "email": email,
                "token": token,
                "invited_by_name": invited_by_name,
                "message": message,
            }
        )


@pytest.fixture
def spy_mailer(users_app):
    original = users_app.state.users.mailer
    spy = _SpyMailer()
    users_app.state.users.mailer = spy
    yield spy
    users_app.state.users.mailer = original


class TestBulkInviteMessage:
    @pytest.mark.anyio
    async def test_message_reaches_the_mailer(self, admin_client, spy_mailer):
        resp = await admin_client.post(
            _URL,
            json={
                "emails": ["noted@example.com"],
                "role_names": [],
                "message": "Joining us on the migration project.",
            },
        )
        assert resp.status_code == 200, resp.text
        assert [i["message"] for i in spy_mailer.invites] == [
            "Joining us on the migration project."
        ]

    @pytest.mark.anyio
    async def test_every_address_in_the_batch_gets_the_same_message(self, admin_client, spy_mailer):
        resp = await admin_client.post(
            _URL,
            json={
                "emails": ["one@example.com", "two@example.com"],
                "role_names": [],
                "message": "Welcome aboard.",
            },
        )
        assert resp.status_code == 200, resp.text
        assert {i["message"] for i in spy_mailer.invites} == {"Welcome aboard."}
        assert len(spy_mailer.invites) == 2

    @pytest.mark.anyio
    async def test_message_is_optional(self, admin_client, spy_mailer):
        resp = await admin_client.post(
            _URL, json={"emails": ["plain@example.com"], "role_names": []}
        )
        assert resp.status_code == 200, resp.text
        assert spy_mailer.invites[0]["message"] is None

    @pytest.mark.anyio
    async def test_bulk_invite_stamps_invited_at(self, admin_client, spy_mailer):
        """A bulk invite must land in the "invited" state, not "unverified"."""
        await admin_client.post(_URL, json={"emails": ["batch@example.com"], "role_names": []})
        resp = await admin_client.get(
            "/admin/users/", headers={"X-Inertia": "true", "Accept": "application/json"}
        )
        row = next(u for u in resp.json()["props"]["users"] if u["email"] == "batch@example.com")
        assert row["state"] == "invited"


class TestConsoleMailerMessage:
    @pytest.mark.anyio
    async def test_console_mailer_logs_the_message(self, users_app, caplog):
        mailer = users_app.state.users.mailer
        with caplog.at_level(logging.INFO, logger="users.mailer"):
            await mailer.send_invite("x@example.com", "tok", "Alex Doyle", "See you Monday.")
        record = next(r for r in caplog.records if r.getMessage() == "users.invite.email")
        assert record.message_body == "See you Monday."
