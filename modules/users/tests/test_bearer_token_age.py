"""A bearer token expires, and the provider is the one that has to say so.

``UsersAuthProvider._resolve_bearer`` looked a token up by value and stopped
there — no age check anywhere — so a row minted for 30 days authenticated
forever. fastapi-users' own strategy compares ``created_at`` against its
lifetime; the provider bypasses the strategy entirely, so it needs the same
clause or the two disagree about what "expired" means.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select, update
from users.backend import _TOKEN_LIFETIME_SECONDS
from users.models import User, UserAccessToken

_GUARDED = "/admin/users/"


async def _mint(users_app) -> str:
    """A real access-token row for the seeded admin."""
    async with users_app.state.sm.db.session_factory() as session:
        user_id = (
            await session.execute(select(User.id).where(User.email == "admin@example.com"))
        ).scalar_one()
        token = UserAccessToken(token=uuid.uuid4().hex, user_id=user_id)
        session.add(token)
        await session.commit()
        return token.token


async def _backdate(users_app, token: str, *, seconds: int) -> None:
    async with users_app.state.sm.db.session_factory() as session:
        await session.execute(
            update(UserAccessToken)
            .where(UserAccessToken.token == token)
            .values(created_at=datetime.now(UTC) - timedelta(seconds=seconds))
        )
        await session.commit()


def _bearer(users_app, token: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=users_app),
        base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    )


class TestBearerTokenAge:
    @pytest.mark.anyio
    async def test_a_fresh_token_authenticates(self, users_app):
        token = await _mint(users_app)
        async with _bearer(users_app, token) as client:
            resp = await client.get(_GUARDED, follow_redirects=False)
        assert resp.status_code == 200, resp.text

    @pytest.mark.anyio
    async def test_a_token_inside_the_window_still_authenticates(self, users_app):
        token = await _mint(users_app)
        await _backdate(users_app, token, seconds=_TOKEN_LIFETIME_SECONDS - 3600)
        async with _bearer(users_app, token) as client:
            resp = await client.get(_GUARDED, follow_redirects=False)
        assert resp.status_code == 200, resp.text

    @pytest.mark.anyio
    async def test_a_token_past_the_window_does_not(self, users_app):
        token = await _mint(users_app)
        await _backdate(users_app, token, seconds=_TOKEN_LIFETIME_SECONDS + 3600)
        async with _bearer(users_app, token) as client:
            resp = await client.get(_GUARDED, follow_redirects=False)
        assert resp.status_code in (302, 401), resp.text
