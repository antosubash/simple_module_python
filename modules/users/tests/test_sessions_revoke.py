"""Sign out everywhere, for real.

Browser auth is a signed cookie, not a server-side session store, so there is
no row to delete for the phone someone left on a train. The account instead
carries a ``session_version`` stamped into every session at login; bumping it
strands every cookie minted before the bump, wherever it is.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import httpx
import pytest
from simple_module_test import forge_session_cookie

_REVOKE = "/api/users/me/sessions/revoke-all"
_GUARDED = "/admin/users/"


def _other_browser(app, user_id: uuid.UUID, session_version: int) -> httpx.AsyncClient:
    """A second signed-in browser, holding a cookie this process never issued."""
    cookie = forge_session_cookie(
        str(app.state.sm.settings.secret_key),
        {"user_id": str(user_id), "session_version": session_version},
    )
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        cookies={"session": cookie},
    )


@pytest.fixture
async def signed_in_admin(users_app, anon_client) -> AsyncGenerator[uuid.UUID, None]:
    resp = await anon_client.post(
        "/api/users/auth/login",
        data={"username": "admin@example.com", "password": "AdminPass1!"},
    )
    assert resp.status_code == 204, resp.text
    from sqlalchemy import select
    from users.models import User

    async with users_app.state.sm.db.session_factory() as session:
        user_id = (
            await session.execute(select(User.id).where(User.email == "admin@example.com"))
        ).scalar_one()
    yield user_id


class TestRevokeAll:
    @pytest.mark.anyio
    async def test_bumps_the_session_version(self, users_app, anon_client, signed_in_admin):
        resp = await anon_client.post(_REVOKE)
        assert resp.status_code == 204, resp.text

        from sqlalchemy import select
        from users.models import User

        async with users_app.state.sm.db.session_factory() as session:
            version = (
                await session.execute(
                    select(User.session_version).where(User.id == signed_in_admin)
                )
            ).scalar_one()
        assert version == 1

    @pytest.mark.anyio
    async def test_an_older_cookie_stops_authenticating(
        self, users_app, anon_client, signed_in_admin
    ):
        async with _other_browser(users_app, signed_in_admin, 0) as other:
            before = await other.get(_GUARDED, follow_redirects=False)
            assert before.status_code == 200, before.text

            resp = await anon_client.post(_REVOKE)
            assert resp.status_code == 204, resp.text

            after = await other.get(_GUARDED, follow_redirects=False)
            assert after.status_code in (302, 401), after.text

    @pytest.mark.anyio
    async def test_a_cookie_minted_after_the_bump_still_works(
        self, users_app, anon_client, signed_in_admin
    ):
        await anon_client.post(_REVOKE)
        async with _other_browser(users_app, signed_in_admin, 1) as fresh:
            resp = await fresh.get(_GUARDED, follow_redirects=False)
            assert resp.status_code == 200, resp.text

    @pytest.mark.anyio
    async def test_the_calling_browser_is_signed_out_too(self, anon_client, signed_in_admin):
        await anon_client.post(_REVOKE)
        resp = await anon_client.get(_GUARDED, follow_redirects=False)
        assert resp.status_code in (302, 401), resp.text

    @pytest.mark.anyio
    async def test_refresh_tokens_are_revoked(self, users_app, anon_client, signed_in_admin):
        from datetime import UTC, datetime, timedelta

        from sqlalchemy import select
        from users.models import RefreshToken

        async with users_app.state.sm.db.session_factory() as session:
            token = RefreshToken(
                user_id=signed_in_admin,
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
            session.add(token)
            await session.commit()
            token_id = token.token

        assert (await anon_client.post(_REVOKE)).status_code == 204

        async with users_app.state.sm.db.session_factory() as session:
            revoked_at = (
                await session.execute(
                    select(RefreshToken.revoked_at).where(RefreshToken.token == token_id)
                )
            ).scalar_one()
        assert revoked_at is not None

    @pytest.mark.anyio
    async def test_bearer_tokens_stop_working(self, users_app, anon_client, signed_in_admin):
        """The sm_auth cookie is a row in users_access_token — it has to go too."""
        from sqlalchemy import func, select
        from users.models import UserAccessToken

        async with users_app.state.sm.db.session_factory() as session:
            live = (
                await session.execute(
                    select(func.count())
                    .select_from(UserAccessToken)
                    .where(UserAccessToken.user_id == signed_in_admin)
                )
            ).scalar_one()
        assert live >= 1

        assert (await anon_client.post(_REVOKE)).status_code == 204

        async with users_app.state.sm.db.session_factory() as session:
            left = (
                await session.execute(
                    select(func.count())
                    .select_from(UserAccessToken)
                    .where(UserAccessToken.user_id == signed_in_admin)
                )
            ).scalar_one()
        assert left == 0

    @pytest.mark.anyio
    async def test_requires_authentication(self, anon_client):
        resp = await anon_client.post(_REVOKE, follow_redirects=False)
        assert resp.status_code in (302, 401)


class TestLoginStampsTheVersion:
    @pytest.mark.anyio
    async def test_a_fresh_login_carries_the_current_version(
        self, users_app, anon_client, signed_in_admin
    ):
        """Otherwise a bump would strand the very session that ordered it."""
        await anon_client.post(_REVOKE)
        resp = await anon_client.post(
            "/api/users/auth/login",
            data={"username": "admin@example.com", "password": "AdminPass1!"},
        )
        assert resp.status_code == 204, resp.text
        page = await anon_client.get(_GUARDED, follow_redirects=False)
        assert page.status_code == 200, page.text
