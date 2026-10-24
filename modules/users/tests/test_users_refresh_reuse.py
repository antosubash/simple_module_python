"""Refresh rotation must consume a token once and detect reuse (#625)."""

import asyncio

from _users_app_builders import _build_users_app, _client, _make_standard_user
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select
from users.models.refresh_token import RefreshToken


async def _login(client):
    response = await client.post(
        "/api/users/auth/token",
        json={"email": "user@example.com", "password": "UserPass1!"},
    )
    assert response.status_code == 200
    return response.json()["refresh_token"]


async def _refresh(client, token):
    return await client.post("/api/users/auth/token/refresh", json={"refresh_token": token})


async def test_users_refresh_reuse_revokes_descendants_only(anon_client, users_app):
    await _make_standard_user(users_app)
    original = await _login(anon_client)
    separate_login = await _login(anon_client)
    child = await _refresh(anon_client, original)
    assert child.status_code == 200
    grandchild = await _refresh(anon_client, child.json()["refresh_token"])
    assert grandchild.status_code == 200

    assert (await _refresh(anon_client, original)).status_code == 401
    assert (await _refresh(anon_client, grandchild.json()["refresh_token"])).status_code == 401
    assert (await _refresh(anon_client, separate_login)).status_code == 200


async def test_users_concurrent_refresh_has_one_winner(monkeypatch, tmp_path):
    # Separate connections: an in-memory SQLite StaticPool shares a transaction.
    app, lifespan = await _build_users_app(
        monkeypatch,
        allow_signup=False,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'refresh.db'}",
    )
    try:
        await _make_standard_user(app)
        async with _client(app, "127.0.0.1") as client:
            token = await _login(client)
            execute = AsyncSession.execute
            readers = asyncio.Barrier(2)

            async def synchronized_read(session, statement, *args, **kwargs):
                result = await execute(session, statement, *args, **kwargs)
                if isinstance(statement, Select) and any(
                    desc.get("entity") is RefreshToken for desc in statement.column_descriptions
                ):
                    frozen = result.freeze()
                    row = frozen().scalar_one_or_none()
                    if row is not None and row.revoked_at is None:
                        # Force both stale reads before either request can burn the token.
                        await readers.wait()
                    return frozen()
                return result

            monkeypatch.setattr(AsyncSession, "execute", synchronized_read)
            responses = await asyncio.wait_for(
                asyncio.gather(_refresh(client, token), _refresh(client, token)),
                timeout=15,
            )
            assert sorted(response.status_code for response in responses) == [200, 401]
            winner = next(response for response in responses if response.status_code == 200)
            assert (await _refresh(client, winner.json()["refresh_token"])).status_code == 401
    finally:
        await lifespan.__aexit__(None, None, None)
