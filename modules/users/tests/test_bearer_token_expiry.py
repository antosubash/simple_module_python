"""A bearer credential lasts as long as it was issued for — not thirty days.

``_TOKEN_LIFETIME_SECONDS`` is one number for the whole process, because
``current_user`` resolves its strategy from the shared backend and cannot vary
it per request. It has to be the widest window any sign-in asks for, so every
other credential inherited it: an ordinary sign-in wrote an ``sm_auth`` cookie
whose ``Max-Age`` said fourteen days while the row behind it was accepted for
thirty, and ``/api/users/auth/token`` returned ``expires_in=900`` for a row good
for a month. ``Max-Age`` is browser-enforced only — a cookie lifted off disk is
replayed without one.

Each row now carries its own deadline and the ``session_version`` it was minted
under, and both bearer read paths enforce them: ``ExpiringDatabaseStrategy``
(which backs ``fastapi_users.current_user``) and ``UsersAuthProvider
._resolve_bearer`` (which backs ``AuthMiddleware``).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from users.models import User, UserAccessToken

_LOGIN = "/api/users/auth/login"
_TOKEN = "/api/users/auth/token"
_ME = "/api/users/me"
_CREDS = {"username": "admin@example.com", "password": "AdminPass1!"}


async def _tokens(app) -> list[UserAccessToken]:
    async with app.state.sm.db.session_factory() as session:
        return list((await session.execute(select(UserAccessToken))).scalars())


async def _only_token(app) -> UserAccessToken:
    rows = await _tokens(app)
    assert len(rows) == 1, f"expected exactly one access token, got {len(rows)}"
    return rows[0]


def _seconds_out(row: UserAccessToken) -> float:
    """How far ``expires_at`` sits from ``created_at``, in seconds."""
    created, expires = row.created_at, row.expires_at
    created = created.replace(tzinfo=UTC) if created.tzinfo is None else created
    expires = expires.replace(tzinfo=UTC) if expires.tzinfo is None else expires
    return (expires - created).total_seconds()


def _bearer(app, token: str) -> httpx.AsyncClient:
    """A client presenting the row as an ``Authorization: Bearer`` header.

    Read by ``UsersAuthProvider._resolve_bearer`` through ``AuthMiddleware``.
    """
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    )


async def _expire_all(app) -> None:
    """Push every row's deadline into the past, leaving ``created_at`` alone."""
    async with app.state.sm.db.session_factory() as session:
        for row in (await session.execute(select(UserAccessToken))).scalars():
            row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()


async def _expire(app, token: str) -> None:
    """Push a row's deadline into the past, leaving ``created_at`` alone.

    The point of the test: the row is well inside the thirty-day read ceiling
    and must still be refused, because the window it was *issued* for has run
    out.
    """
    async with app.state.sm.db.session_factory() as session:
        row = await session.get(UserAccessToken, token)
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()


class TestTheRowLastsWhatWasPromised:
    @pytest.mark.anyio
    async def test_an_ordinary_sign_in_gets_the_cookie_window(self, users_app, anon_client):
        """Not the thirty-day ceiling. This is the whole bug: the `Max-Age` said
        fourteen days and the row behind it was honoured for thirty."""
        assert (await anon_client.post(_LOGIN, data=_CREDS)).status_code == 204

        settings = users_app.state.users.settings
        assert _seconds_out(await _only_token(users_app)) == pytest.approx(
            settings.cookie_max_age_seconds, abs=5
        )

    @pytest.mark.anyio
    async def test_keep_me_signed_in_gets_the_longer_window(self, users_app, anon_client):
        """The checkbox still has to mean what it says."""
        assert (
            await anon_client.post(_LOGIN, data={**_CREDS, "remember": "true"})
        ).status_code == 204

        settings = users_app.state.users.settings
        assert _seconds_out(await _only_token(users_app)) == pytest.approx(
            settings.remember_me_max_age_seconds, abs=5
        )

    @pytest.mark.anyio
    async def test_the_token_endpoint_honours_its_own_expires_in(self, users_app, anon_client):
        """It advertised 15 minutes and minted a row good for a month, so a
        client that honoured `expires_in` re-authenticated every 15 minutes
        while the token it discarded stayed valid."""
        resp = await anon_client.post(
            _TOKEN, json={"email": "admin@example.com", "password": "AdminPass1!"}
        )
        assert resp.status_code == 200, resp.text
        advertised = resp.json()["expires_in"]

        settings = users_app.state.users.settings
        assert advertised == settings.bearer_token_lifetime_seconds
        assert _seconds_out(await _only_token(users_app)) == pytest.approx(advertised, abs=5)


class TestAnExpiredRowStopsAuthenticating:
    @pytest.mark.anyio
    async def test_the_cookie_strategy_path_refuses_it(self, users_app, anon_client):
        """`fastapi_users.current_user`, via ExpiringDatabaseStrategy.

        ``/api/users/me`` is the probe because it depends on ``current_user``,
        which is what reads the ``sm_auth`` row. The row stays well inside the
        thirty-day read ceiling — only the deadline it was issued for has passed.
        """
        assert (await anon_client.post(_LOGIN, data=_CREDS)).status_code == 204
        assert (await anon_client.get(_ME)).status_code == 200

        await _expire_all(users_app)
        assert (await anon_client.get(_ME)).status_code == 401

    @pytest.mark.anyio
    async def test_the_provider_path_refuses_it(self, users_app, anon_client):
        """`UsersAuthProvider._resolve_bearer`, via AuthMiddleware."""
        from users.provider import UsersAuthProvider

        resp = await anon_client.post(
            _TOKEN, json={"email": "admin@example.com", "password": "AdminPass1!"}
        )
        token = resp.json()["access_token"]
        scope = {"app": users_app}

        provider = UsersAuthProvider()
        assert await provider._resolve_bearer(scope, token) is not None
        await _expire(users_app, token)
        assert await provider._resolve_bearer(scope, token) is None


class TestAPasswordChangeStrandsBearerTokens:
    """`change_my_password` bumped `session_version` and stranded every session,
    while every bearer token minted before it kept working — including any an
    attacker who knew the old password had already collected."""

    @pytest.mark.anyio
    async def test_a_version_bump_strands_a_token_on_both_paths(self, users_app, anon_client):
        from users.provider import UsersAuthProvider, forget_session_version

        # One row per path: the sign-in writes the `sm_auth` row `current_user`
        # reads, and `/auth/token` mints the one the Bearer header carries.
        assert (await anon_client.post(_LOGIN, data=_CREDS)).status_code == 204
        minted = await anon_client.post(
            _TOKEN, json={"email": "admin@example.com", "password": "AdminPass1!"}
        )
        token = minted.json()["access_token"]
        provider = UsersAuthProvider()
        scope = {"app": users_app}

        assert (await anon_client.get(_ME)).status_code == 200
        assert await provider._resolve_bearer(scope, token) is not None

        async with users_app.state.sm.db.session_factory() as session:
            user = (
                await session.execute(select(User).where(User.email == "admin@example.com"))
            ).scalar_one()
            user.session_version = int(user.session_version or 0) + 1
            await session.commit()
            forget_session_version(user.id)

        assert (await anon_client.get(_ME)).status_code == 401
        assert await provider._resolve_bearer(scope, token) is None

    @pytest.mark.anyio
    async def test_changing_the_password_deletes_the_rows(self, users_app, anon_client):
        """The stamped counter already strands them; deleting is what stops a
        stolen token resolving a row at all, and stops the refresh tokens
        minting fresh ones behind it."""
        assert (await anon_client.post(_LOGIN, data=_CREDS)).status_code == 204
        assert await _tokens(users_app)

        resp = await anon_client.post(
            "/api/users/me/password",
            json={"current_password": "AdminPass1!", "new_password": "NewAdminPass1!"},
        )
        assert resp.status_code == 204, resp.text
        assert await _tokens(users_app) == []


class TestTheMintedCounterIsCurrent:
    @pytest.mark.anyio
    async def test_a_refresh_carries_the_accounts_counter(self, users_app, anon_client):
        """A refresh token outlives the access tokens it mints, so the account
        is re-read rather than trusted from the row."""
        resp = await anon_client.post(
            _TOKEN, json={"email": "admin@example.com", "password": "AdminPass1!"}
        )
        refresh = resp.json()["refresh_token"]

        async with users_app.state.sm.db.session_factory() as session:
            user = (
                await session.execute(select(User).where(User.email == "admin@example.com"))
            ).scalar_one()
            user.session_version = 42
            await session.commit()

        rotated = await anon_client.post(
            "/api/users/auth/token/refresh", json={"refresh_token": refresh}
        )
        assert rotated.status_code == 200, rotated.text

        async with users_app.state.sm.db.session_factory() as session:
            row = (
                await session.execute(
                    select(UserAccessToken).where(
                        UserAccessToken.token == rotated.json()["access_token"]
                    )
                )
            ).scalar_one()
            assert row.session_version == 42

    @pytest.mark.anyio
    async def test_a_refresh_for_a_deactivated_account_is_refused(self, users_app, anon_client):
        resp = await anon_client.post(
            _TOKEN, json={"email": "admin@example.com", "password": "AdminPass1!"}
        )
        refresh = resp.json()["refresh_token"]

        async with users_app.state.sm.db.session_factory() as session:
            user = (
                await session.execute(select(User).where(User.email == "admin@example.com"))
            ).scalar_one()
            user.is_active = False
            await session.commit()

        rotated = await anon_client.post(
            "/api/users/auth/token/refresh", json={"refresh_token": refresh}
        )
        assert rotated.status_code == 401


class TestTheModelDefault:
    def test_a_row_built_directly_still_gets_a_deadline(self):
        """The mint paths always stamp one; the default keeps a caller that
        builds the model by hand from minting a credential that never expires."""
        row = UserAccessToken(token="t", user_id=uuid.uuid4())
        assert row.expires_at is not None
        assert _seconds_out(row) == pytest.approx(30 * 24 * 60 * 60, abs=5)
