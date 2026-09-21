"""The endpoints actually broadcast — asserted through HTTP, not through the helper.

Every other revocation test calls ``publish_revocation`` directly, which means
deleting the ``db.on_commit(lambda: publish_revocation(...))`` line from both
endpoints would leave the whole suite green while the feature silently did
nothing in production. These tests close that: they drive the real routes and
assert on what reached the transport.

They also pin the *timing* half of the contract. The publish is hung on the
commit, not run inline, so a request that fails after bumping the counter must
not tell the other workers to forget anything — the row it was invalidating
never became durable.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import select
from users.session_revocation import CHANNEL

_REVOKE = "/api/users/me/sessions/revoke-all"
_PASSWORD = "/api/users/me/password"
_ADMIN_EMAIL = "admin@example.com"
_ADMIN_PASSWORD = "AdminPass1!"


class _RecordingTransport:
    """Stands in for the Redis transport and keeps the wire messages."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def publish(self, message: str) -> None:
        self.sent.append(message)

    @property
    def decoded(self) -> list[dict]:
        return [json.loads(m) for m in self.sent]


@pytest.fixture
async def broadcasts(users_app) -> AsyncGenerator[_RecordingTransport, None]:
    """Capture what this app would have broadcast to the other workers."""
    transport = _RecordingTransport()
    users_app.state.sm.invalidation.set_transport(transport)
    yield transport
    users_app.state.sm.invalidation.clear_transport()


async def _sign_in(client) -> None:
    resp = await client.post(
        "/api/users/auth/login",
        data={"username": _ADMIN_EMAIL, "password": _ADMIN_PASSWORD},
    )
    assert resp.status_code == 204, resp.text


async def _admin_id(app) -> uuid.UUID:
    from users.models import User

    async with app.state.sm.db.session_factory() as session:
        return (
            await session.execute(select(User.id).where(User.email == _ADMIN_EMAIL))
        ).scalar_one()


class TestRevokeAllBroadcasts:
    async def test_the_endpoint_tells_the_other_workers(self, users_app, anon_client, broadcasts):
        await _sign_in(anon_client)
        user_id = await _admin_id(users_app)

        resp = await anon_client.post(_REVOKE)
        assert resp.status_code == 204, resp.text

        assert len(broadcasts.sent) == 1, "sign out everywhere broadcast nothing"
        message = broadcasts.decoded[0]
        assert message["channel"] == CHANNEL
        assert message["key"] == str(user_id)

    async def test_the_broadcast_carries_this_worker_as_its_origin(
        self, users_app, anon_client, broadcasts
    ):
        """Without a real origin the receiving worker cannot tell it apart from
        its own echo, and would either ignore every message or act on its own."""
        await _sign_in(anon_client)
        await anon_client.post(_REVOKE)

        assert broadcasts.decoded[0]["origin"] == users_app.state.sm.invalidation.origin


class TestPasswordChangeBroadcasts:
    async def test_changing_a_password_tells_the_other_workers(
        self, users_app, anon_client, broadcasts
    ):
        """The case the issue was really about: a password changed because the
        account is believed compromised."""
        await _sign_in(anon_client)
        user_id = await _admin_id(users_app)

        resp = await anon_client.post(
            _PASSWORD,
            json={"current_password": _ADMIN_PASSWORD, "new_password": "NewAdminPass1!"},
        )
        assert resp.status_code == 204, resp.text

        assert len(broadcasts.sent) == 1, "the password change broadcast nothing"
        assert broadcasts.decoded[0]["key"] == str(user_id)

    async def test_a_rejected_password_broadcasts_nothing(self, anon_client, broadcasts):
        """The counter was never bumped, so nothing must be invalidated."""
        await _sign_in(anon_client)

        resp = await anon_client.post(
            _PASSWORD,
            json={"current_password": "wrong-password", "new_password": "NewAdminPass1!"},
        )
        assert resp.status_code in (400, 401, 403), resp.text
        assert broadcasts.sent == []


class TestRollbackDoesNotBroadcast:
    """A broadcast is a promise that the row changed. A rolled-back request made
    no such change, and telling every worker to forget a value that is still
    current would send them all back to the database for nothing — or, worse,
    make a revocation *look* like it happened."""

    async def test_a_failure_after_the_bump_broadcasts_nothing(
        self, anon_client, broadcasts, monkeypatch
    ):
        """Fail the endpoint *after* it has registered the on-commit callback.

        ``delete`` is called for the access-token rows, which happens after the
        bump and after ``db.on_commit(...)``. Making it raise reproduces "the
        transaction did not commit" without needing to break the database.
        """
        import users.auth_local.self_account as self_account

        await _sign_in(anon_client)

        def _explode(*args, **kwargs):
            raise RuntimeError("simulated failure after the session_version bump")

        monkeypatch.setattr(self_account, "delete", _explode)

        with pytest.raises(RuntimeError, match="simulated failure"):
            await anon_client.post(_REVOKE)

        assert broadcasts.sent == [], "a rolled-back revocation was broadcast anyway"


class TestNoTransportInstalled:
    async def test_revoking_still_works_with_no_transport(self, users_app, anon_client):
        """The default install: in-process only, and the endpoint still succeeds.

        Guards against the bus becoming load-bearing for the request rather than
        an accelerator over it.
        """
        assert users_app.state.sm.invalidation.has_transport is False
        await _sign_in(anon_client)

        resp = await anon_client.post(_REVOKE)

        assert resp.status_code == 204, resp.text
