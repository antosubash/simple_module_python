"""A session's lifetime is bounded per session, not per deployment.

Honouring "Keep me signed in for 30 days" meant widening the *signature*
window to 30 days, and the signer is one number for the whole process — so
every ordinary 14-day session became replayable for 30 days once its cookie
was lifted off disk. The window each sign-in actually asked for is recorded in
the session payload and enforced by the auth provider, which puts the ceiling
back where it belongs without narrowing the signer the checkbox needs.
"""

from __future__ import annotations

import json
import time
import uuid
from base64 import b64decode

import httpx
import pytest
from fastapi_users.password import PasswordHelper
from simple_module_hosting.session import SESSION_EXPIRES_AT_KEY
from simple_module_test import forge_session_cookie
from users.models import User

_pw = PasswordHelper()
_PROBE = "/dashboard/"


async def _make_user(session, email: str) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=_pw.hash("SecurePass1!"),
        is_active=True,
        is_verified=True,
        full_name="Test User",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


def _session_payload(resp) -> dict:
    """Decode the session cookie the response just wrote."""
    headers = [v for k, v in resp.headers.multi_items() if k.lower() == "set-cookie"]
    raw = next(h for h in headers if h.startswith("session="))
    signed = raw.split("=", 1)[1].split(";", 1)[0]
    return json.loads(b64decode(signed.split(".", 1)[0]))


async def _client_with_session(users_app, payload: dict) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=users_app),
        base_url="http://testserver",
        cookies={
            "session": forge_session_cookie(
                str(users_app.state.sm.settings.secret_key), payload
            )
        },
    )


class TestLoginRecordsAnAbsoluteDeadline:
    @pytest.mark.anyio
    async def test_a_plain_sign_in_is_bounded_at_the_cookie_window(
        self, anon_client, users_db, users_app
    ):
        await _make_user(users_db, "bounded@example.com")
        resp = await anon_client.post(
            "/api/users/auth/login",
            data={"username": "bounded@example.com", "password": "SecurePass1!"},
        )
        assert resp.status_code == 204, resp.text

        expected = time.time() + users_app.state.users.settings.cookie_max_age_seconds
        assert abs(_session_payload(resp)[SESSION_EXPIRES_AT_KEY] - expected) < 60

    @pytest.mark.anyio
    async def test_a_remembered_sign_in_gets_the_longer_bound(
        self, anon_client, users_db, users_app
    ):
        await _make_user(users_db, "remembered@example.com")
        resp = await anon_client.post(
            "/api/users/auth/login",
            data={
                "username": "remembered@example.com",
                "password": "SecurePass1!",
                "remember": "true",
            },
        )
        assert resp.status_code == 204, resp.text

        expected = time.time() + users_app.state.users.settings.remember_me_max_age_seconds
        assert abs(_session_payload(resp)[SESSION_EXPIRES_AT_KEY] - expected) < 60


class TestTheProviderEnforcesIt:
    """Both resolution paths: the cached context and the DB reload."""

    async def _user_id(self, users_app) -> str:
        from sqlalchemy import select

        async with users_app.state.sm.db.session_factory() as session:
            return str(
                (
                    await session.execute(select(User.id).where(User.email == "admin@example.com"))
                ).scalar_one()
            )

    @pytest.mark.anyio
    async def test_an_expired_session_is_signed_out(self, users_app):
        user_id = await self._user_id(users_app)
        payload = {
            "user_id": user_id,
            "session_version": 0,
            SESSION_EXPIRES_AT_KEY: int(time.time()) - 1,
        }
        async with await _client_with_session(users_app, payload) as client:
            resp = await client.get(_PROBE, follow_redirects=False)

        assert resp.status_code in (302, 401), resp.text

    @pytest.mark.anyio
    async def test_a_live_session_is_accepted(self, users_app):
        user_id = await self._user_id(users_app)
        payload = {
            "user_id": user_id,
            "session_version": 0,
            SESSION_EXPIRES_AT_KEY: int(time.time()) + 3600,
        }
        async with await _client_with_session(users_app, payload) as client:
            resp = await client.get(_PROBE, follow_redirects=False)

        assert resp.status_code == 200, resp.text

    @pytest.mark.anyio
    async def test_an_expired_session_is_refused_on_the_cached_path_too(self, users_app):
        """A cached ``user_ctx`` must not let an expired session through."""
        from auth.contracts.schemas import UserContext
        from sqlalchemy import select
        from sqlalchemy.orm import noload, selectinload

        async with users_app.state.sm.db.session_factory() as session:
            user = (
                await session.execute(
                    select(User)
                    .where(User.email == "admin@example.com")
                    .options(selectinload(User.roles), noload(User.oauth_accounts))
                )
            ).scalar_one()
            ctx = UserContext.from_user(user).to_session_dict()
            user_id = str(user.id)

        payload = {
            "user_id": user_id,
            "user_ctx": ctx,
            "session_version": 0,
            SESSION_EXPIRES_AT_KEY: int(time.time()) - 1,
        }
        async with await _client_with_session(users_app, payload) as client:
            resp = await client.get(_PROBE, follow_redirects=False)

        assert resp.status_code in (302, 401), resp.text

    @pytest.mark.anyio
    async def test_a_session_without_the_key_is_accepted_as_legacy(self, users_app):
        """Fail-open, deliberately and temporarily: every session minted before
        this change carries no deadline, and failing closed would sign the
        whole user base out on deploy."""
        user_id = await self._user_id(users_app)
        payload = {"user_id": user_id, "session_version": 0}
        async with await _client_with_session(users_app, payload) as client:
            resp = await client.get(_PROBE, follow_redirects=False)

        assert resp.status_code == 200, resp.text

    @pytest.mark.anyio
    async def test_an_unreadable_deadline_is_treated_as_absent(self, users_app):
        user_id = await self._user_id(users_app)
        payload = {"user_id": user_id, "session_version": 0, SESSION_EXPIRES_AT_KEY: "soon"}
        async with await _client_with_session(users_app, payload) as client:
            resp = await client.get(_PROBE, follow_redirects=False)

        assert resp.status_code == 200, resp.text
