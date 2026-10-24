"""Real cache transactions keep Keycloak identities stable across requests (#618)."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from keycloak.directory import KeycloakDirectory
from keycloak.models import KeycloakUserCache
from keycloak.provider import KeycloakAuthProvider
from simple_module_db import independent_session
from sqlalchemy import event, select
from starlette.requests import Request

CLAIMS = {"sub": "kc-stable", "email": "old@example.com", "preferred_username": "Old"}


@pytest.fixture
def cache_request(db_state, db_session):
    app = SimpleNamespace(state=SimpleNamespace(sm=SimpleNamespace(db=db_state)))
    return Request({"type": "http", "app": app, "headers": []})


async def test_keycloak_cache_commits_and_keeps_id_across_logins(cache_request, db_state):
    provider = KeycloakAuthProvider()
    first = await provider._upsert_user_cache(cache_request, CLAIMS)
    async with db_state.session_factory() as db:
        users = await KeycloakDirectory().get_many(db, [first])
        assert users[first].email == "old@example.com"

    second = await provider._upsert_user_cache(cache_request, CLAIMS)
    assert second == first
    changed = {**CLAIMS, "email": "new@example.com", "preferred_username": "New"}
    assert await provider._upsert_user_cache(cache_request, changed) == first
    async with db_state.session_factory() as db:
        row = (await db.execute(select(KeycloakUserCache))).scalar_one()
        assert str(row.id) == first
        assert (row.email, row.full_name) == ("new@example.com", "New")
        assert row.last_login_at is not None


@pytest.mark.parametrize("age", [None, 30, 600])
async def test_keycloak_bearer_throttles_timestamp_writes(cache_request, db_state, age):
    now = datetime.now(UTC)
    previous = None if age is None else now - timedelta(seconds=age)
    async with independent_session(cache_request.app) as db:
        row = KeycloakUserCache(
            keycloak_sub=CLAIMS["sub"],
            email=CLAIMS["email"],
            full_name=CLAIMS["preferred_username"],
            last_login_at=previous,
        )
        db.add(row)
        user_id = str(row.id)

    updates = []

    def record_update(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("UPDATE KEYCLOAK_USER_CACHE"):
            updates.append(statement)

    event.listen(db_state.engine.sync_engine, "before_cursor_execute", record_update)
    try:
        provider = KeycloakAuthProvider()

        class Jwks:
            async def validate_jwt(self, token):
                return CLAIMS

        provider.jwks_cache = Jwks()
        for _ in range(2):
            ctx = await provider._resolve_bearer(cache_request, "jwt")
            assert ctx.id == user_id
        assert len(updates) == (0 if age == 30 else 1)

        # A browser login always records the login, even inside the interval.
        await provider._upsert_user_cache(cache_request, CLAIMS)
        assert len(updates) == (1 if age == 30 else 2)
    finally:
        event.remove(db_state.engine.sync_engine, "before_cursor_execute", record_update)

    async with db_state.session_factory() as db:
        row = (await db.execute(select(KeycloakUserCache))).scalar_one()
        assert row.last_login_at >= now


async def test_keycloak_bearer_saves_profile_inside_touch_interval(cache_request, db_state):
    provider = KeycloakAuthProvider()
    user_id = await provider._upsert_user_cache(cache_request, CLAIMS)
    async with db_state.session_factory() as db:
        previous = (await db.execute(select(KeycloakUserCache.last_login_at))).scalar_one()

    changed = {**CLAIMS, "email": "new@example.com", "preferred_username": "New"}
    assert await provider._upsert_user_cache(cache_request, changed, throttle_login=True) == user_id
    async with db_state.session_factory() as db:
        row = (await db.execute(select(KeycloakUserCache))).scalar_one()
        assert (row.email, row.full_name) == ("new@example.com", "New")
        assert row.last_login_at == previous


async def test_keycloak_cache_recovers_unique_insert_race(cache_request, db_state, monkeypatch):
    async with independent_session(cache_request.app) as db:
        winner = KeycloakUserCache(keycloak_sub=CLAIMS["sub"], email="winner@example.com")
        db.add(winner)
        winner_id = str(winner.id)

    session_class = db_state.session_factory.class_
    execute = session_class.execute
    hide_winner = True

    async def stale_first_read(self, statement, *args, **kwargs):
        nonlocal hide_winner
        if hide_winner:
            hide_winner = False
            # Simulate the initial SELECT finishing before the competing insert
            # commits. The subsequent INSERT hits the real unique constraint.
            return await execute(self, select(KeycloakUserCache).where(False))
        return await execute(self, statement, *args, **kwargs)

    monkeypatch.setattr(session_class, "execute", stale_first_read)
    result = await KeycloakAuthProvider()._upsert_user_cache(cache_request, CLAIMS)
    assert result == winner_id
    async with db_state.session_factory() as db:
        row = (await db.execute(select(KeycloakUserCache))).scalar_one()
        assert str(row.id) == winner_id
        assert (row.email, row.full_name) == ("old@example.com", "Old")
