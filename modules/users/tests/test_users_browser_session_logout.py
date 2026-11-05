"""Logout ends one browser session, including an earlier copy of its cookie."""

import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from _users_app_builders import user_row
from auth.constants import SESSION_ID_KEY
from simple_module_core.invalidation import InvalidationBus
from sqlalchemy import select
from users.auth_local.browser_sessions import revoke_browser_session
from users.constants import SESSION_USER_ID_KEY
from users.models import RevokedSession
from users.session_revocation import CHANNEL, subscribe
from users.session_version_cache import (
    clear_session_version_cache,
    read_session_version,
    store_session_version,
)

CREDENTIALS = {"username": "admin@example.com", "password": "AdminPass1!"}


@pytest.mark.parametrize("path", ["/users/logout", "/api/users/auth/logout"])
@pytest.mark.parametrize("remember", [False, True])
async def test_logout_revokes_only_this_session(users_app, anon_client, path, remember):
    transport = httpx.ASGITransport(app=users_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as other:
        for client in [anon_client, other]:
            response = await client.post(
                "/api/users/auth/login", data={**CREDENTIALS, "remember": str(remember).lower()}
            )
            assert response.status_code == 204
        initial = anon_client.cookies.get("session")
        # Cache both the principal in the signed cookie and the server's counter.
        assert (await anon_client.get("/api/users/me")).status_code == 200
        copied = anon_client.cookies.get("session")
        assert (await anon_client.post(path)).status_code in {204, 303}
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver", cookies={"session": copied}
        ) as replay:
            assert (await replay.get("/api/users/me")).status_code == 401
            # The same copy again with a cold counter cache, then the first cookie.
            for cookie, cold in [(copied, True), (initial, False)]:
                if cold:
                    clear_session_version_cache()
                replay.cookies.clear()
                replay.cookies.set("session", cookie)
                assert (await replay.get("/api/users/me")).status_code == 401
        assert (await other.get("/api/users/me")).status_code == 200


async def test_legacy_cookie_without_id_remains_accepted(users_app, admin_client):
    assert (await admin_client.get("/api/users/me")).status_code == 200
    # The fixture deliberately forges the pre-upgrade shape without an id.
    copied = admin_client.cookies.get("session", domain="testserver.local")
    await admin_client.post("/api/users/auth/logout")
    admin_client.cookies.clear()
    admin_client.cookies.set("session", copied)
    assert (await admin_client.get("/api/users/me")).status_code == 200


async def test_logout_cleans_expired_records_and_retains_deadline(users_app, anon_client):
    user = await user_row(users_app, "admin@example.com")
    async with users_app.state.sm.db.session_factory() as db:
        db.add(
            RevokedSession(
                session_id="expired",
                user_id=user.id,
                expires_at=datetime.now(UTC) - timedelta(days=1),
            )
        )
        await db.commit()
    assert (await anon_client.post("/api/users/auth/login", data=CREDENTIALS)).status_code == 204
    before = datetime.now(UTC)
    assert (await anon_client.post("/api/users/auth/logout")).status_code == 204
    async with users_app.state.sm.db.session_factory() as db:
        rows = list((await db.execute(select(RevokedSession))).scalars())
        assert len(rows) == 1
        assert rows[0].session_id != "expired"
        remaining = rows[0].expires_at - before
        assert timedelta(days=13) < remaining <= timedelta(days=14)


async def test_second_logout_of_same_session_is_a_noop(users_app, anon_client):
    assert (await anon_client.post("/api/users/auth/login", data=CREDENTIALS)).status_code == 204
    copied = anon_client.cookies.get("session")
    assert (await anon_client.post("/api/users/auth/logout")).status_code == 204
    async with users_app.state.sm.db.session_factory() as db:
        first = list((await db.execute(select(RevokedSession))).scalars())
    assert len(first) == 1
    transport = httpx.ASGITransport(app=users_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver", cookies={"session": copied}
    ) as again:
        assert (await again.post("/api/users/auth/logout")).status_code in {204, 401, 403}
    async with users_app.state.sm.db.session_factory() as db:
        rows = list((await db.execute(select(RevokedSession))).scalars())
    assert [(r.session_id, r.expires_at) for r in rows] == [
        (r.session_id, r.expires_at) for r in first
    ]


async def test_revoke_browser_session_twice_in_one_transaction(users_app):
    user = await user_row(users_app, "admin@example.com")
    session = {SESSION_ID_KEY: "dup", SESSION_USER_ID_KEY: str(user.id)}
    request = SimpleNamespace(session=session, app=users_app)
    async with users_app.state.sm.db.session_factory() as db:
        await revoke_browser_session(request, db)
        await revoke_browser_session(request, db)
        await db.commit()
    async with users_app.state.sm.db.session_factory() as db:
        rows = list((await db.execute(select(RevokedSession))).scalars())
    assert [r.session_id for r in rows] == ["dup"]


async def test_remote_invalidation_drops_cached_retirements():
    user_id = uuid.uuid4()
    bus = InvalidationBus()
    subscribe(bus)
    store_session_version(user_id, 0, frozenset({"retired"}))
    assert read_session_version(user_id, "retired") == (True, None)
    assert read_session_version(user_id, "other-device") == (True, 0)
    await bus.deliver(
        f'{{"v": 1, "channel": "{CHANNEL}", "key": "{user_id}", "origin": "other-worker"}}'
    )
    assert read_session_version(user_id, "retired") == (False, None)


async def test_logout_broadcasts_after_record_is_durable(users_app, anon_client):
    messages = []

    class Transport:
        async def publish(self, message):
            payload = json.loads(message)
            if payload["channel"] == CHANNEL:
                async with users_app.state.sm.db.session_factory() as db:
                    records = list((await db.execute(select(RevokedSession))).scalars())
                    assert len(records) == 1
                    assert str(records[0].user_id) == payload["key"]
                messages.append(payload)

    users_app.state.sm.invalidation.set_transport(Transport())
    assert (await anon_client.post("/api/users/auth/login", data=CREDENTIALS)).status_code == 204
    assert (await anon_client.post("/api/users/auth/logout")).status_code == 204
    assert len(messages) == 1
