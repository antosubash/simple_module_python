"""A session minted before deadlines existed gets one on first sight.

``SESSION_EXPIRES_AT_KEY`` holds each session's own absolute deadline, which is
what holds an ordinary sign-in to the fourteen days it asked for while the
signature window stays at thirty for everyone (that is what "keep me signed in"
needs). Sessions minted before the key existed carry none, and
``session_has_expired`` accepted them — a fail-open with nothing tracking when
it could safely be closed.

Stamping on first sight closes it without a deploy-time mass sign-out. It can
only ever tighten: the signer independently enforces the signature window from
the session's original mint time, so a stamp written now cannot outlast the
ceiling the session already had.
"""

from __future__ import annotations

import time

import httpx
import pytest
from simple_module_hosting.session import (
    SESSION_EXPIRES_AT_KEY,
    SESSION_REMEMBER_KEY,
    SESSION_SIGNATURE_MAX_AGE,
    ensure_session_expiry,
    session_has_expired,
    stamp_session_expiry,
)
from simple_module_test import forge_session_cookie
from sqlalchemy import select
from users.models import User

# Probed with a page route rather than ``/api/users/me``: that one also depends
# on ``current_user``, which reads the ``sm_auth`` cookie, and a forged session
# cookie carries no such row. This route is gated by ``AuthMiddleware`` alone —
# which is the code path under test.
_GUARDED = "/admin/users/"
_DAY = 24 * 60 * 60


class TestSessionHasExpiredFailsClosed:
    """Absence used to mean "accept"; the only caller stamps first, so absence
    now means the session never went through that path."""

    def test_a_session_with_no_deadline_is_expired(self):
        assert session_has_expired({}) is True

    def test_a_non_mapping_is_expired(self):
        assert session_has_expired(None) is True

    def test_an_unreadable_deadline_is_expired(self):
        assert session_has_expired({SESSION_EXPIRES_AT_KEY: "soon"}) is True
        # ``bool`` is an ``int``: True must not read as epoch second 1.
        assert session_has_expired({SESSION_EXPIRES_AT_KEY: True}) is True

    def test_a_future_deadline_is_live(self):
        assert session_has_expired({SESSION_EXPIRES_AT_KEY: time.time() + 60}) is False

    def test_a_past_deadline_is_expired(self):
        assert session_has_expired({SESSION_EXPIRES_AT_KEY: time.time() - 1}) is True


class TestEnsureSessionExpiry:
    def test_it_stamps_a_session_that_has_none(self):
        session: dict = {}
        deadline = ensure_session_expiry(session, 14 * _DAY)

        assert session[SESSION_EXPIRES_AT_KEY] == deadline
        assert deadline == pytest.approx(time.time() + 14 * _DAY, abs=5)
        assert session_has_expired(session) is False

    def test_it_never_widens_an_existing_deadline(self):
        """Otherwise every request would slide the window forward and the
        session would never expire."""
        session: dict = {}
        first = stamp_session_expiry(session, 60)
        again = ensure_session_expiry(session, SESSION_SIGNATURE_MAX_AGE)

        assert again == first
        assert session[SESSION_EXPIRES_AT_KEY] == first

    def test_it_leaves_an_already_expired_deadline_alone(self):
        """Re-stamping here would resurrect a session the caller is about to
        reject."""
        session = {SESSION_EXPIRES_AT_KEY: int(time.time()) - 1}
        ensure_session_expiry(session, 14 * _DAY)

        assert session_has_expired(session) is True


class TestALegacySessionKeepsWorking:
    """The deploy-time behaviour: nobody is signed out, and from the first
    request on the session carries the same bound as one minted today."""

    @staticmethod
    def _legacy_client(app, user_id, session_version: int, **extra) -> httpx.AsyncClient:
        """A browser holding a cookie minted before deadlines existed."""
        payload = {"user_id": str(user_id), "session_version": session_version, **extra}
        assert SESSION_EXPIRES_AT_KEY not in payload
        cookie = forge_session_cookie(str(app.state.sm.settings.secret_key), payload)
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            cookies={"session": cookie},
        )

    @staticmethod
    async def _admin(app):
        async with app.state.sm.db.session_factory() as session:
            return (
                await session.execute(select(User).where(User.email == "admin@example.com"))
            ).scalar_one()

    @pytest.mark.anyio
    async def test_it_is_not_signed_out(self, users_app):
        admin = await self._admin(users_app)
        async with self._legacy_client(users_app, admin.id, admin.session_version) as client:
            assert (await client.get(_GUARDED)).status_code == 200

    @pytest.mark.anyio
    async def test_the_ordinary_window_is_stamped_onto_it(self, users_app):
        admin = await self._admin(users_app)
        async with self._legacy_client(users_app, admin.id, admin.session_version) as client:
            resp = await client.get(_GUARDED)
        assert resp.status_code == 200

        session = _read_session(users_app, resp)
        assert session[SESSION_EXPIRES_AT_KEY] == pytest.approx(
            time.time() + users_app.state.users.settings.cookie_max_age_seconds, abs=30
        )

    @pytest.mark.anyio
    async def test_a_remembered_legacy_session_is_not_demoted(self, users_app):
        """It recorded the longer window; stamping must read that back rather
        than quietly cutting it to the ordinary one."""
        admin = await self._admin(users_app)
        async with self._legacy_client(
            users_app, admin.id, admin.session_version, **{SESSION_REMEMBER_KEY: 30 * _DAY}
        ) as client:
            resp = await client.get(_GUARDED)
        assert resp.status_code == 200

        session = _read_session(users_app, resp)
        assert session[SESSION_EXPIRES_AT_KEY] == pytest.approx(time.time() + 30 * _DAY, abs=30)


def _read_session(app, response: httpx.Response) -> dict:
    """Decode the session cookie this response wrote."""
    import itsdangerous
    from starlette.datastructures import Secret

    raw = response.cookies.get("session")
    assert raw is not None, "expected the stamping request to rewrite the session cookie"
    signer = itsdangerous.TimestampSigner(str(Secret(str(app.state.sm.settings.secret_key))))
    import base64
    import json

    return json.loads(base64.b64decode(signer.unsign(raw, max_age=SESSION_SIGNATURE_MAX_AGE)))
