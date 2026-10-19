"""Login lockout through the HTTP routes, across IPs and app instances (GH #530)."""

from __future__ import annotations

import httpx
import pytest
from _users_app_builders import _build_users_app, _make_standard_user
from sqlalchemy import select
from users.auth_local.lockout import LOCKED_DETAIL
from users.models import User

ALICE = "alice@example.com"
PASSWORD = "UserPass1!"


def _client(app, ip: str) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, client=(ip, 1))
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


async def _login(app, ip: str, username: str, password: str) -> httpx.Response:
    async with _client(app, ip) as c:
        return await c.post(
            "/api/users/auth/login", data={"username": username, "password": password}
        )


async def _token(app, ip: str, email: str, password: str) -> httpx.Response:
    async with _client(app, ip) as c:
        return await c.post("/api/users/auth/token", json={"email": email, "password": password})


async def _alice_row(app) -> User:
    async with app.state.sm.db.session_factory() as session:
        return (await session.execute(select(User).where(User.email == ALICE))).scalar_one()


@pytest.fixture
async def alice(users_app):
    return await _make_standard_user(users_app, ALICE)


async def test_acceptance_three_ips_two_apps_survives_restart(monkeypatch, tmp_path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'lockout.db'}"
    overrides = {"login_lockout_account_failures": ("5", "int")}
    contexts = []

    async def build():
        app, ctx = await _build_users_app(
            monkeypatch, allow_signup=False, database_url=url, overrides=overrides
        )
        contexts.append(ctx)
        return app

    try:
        app_a, app_b = await build(), await build()
        await _make_standard_user(app_a, ALICE)
        plan = [
            (app_a, "1.1.1.1"),
            (app_b, "2.2.2.2"),
            (app_a, "3.3.3.3"),
            (app_b, "1.1.1.1"),
            (app_a, "2.2.2.2"),
        ]
        for app, ip in plan:
            assert (await _login(app, ip, ALICE, "wrong")).status_code == 400

        r = await _login(app_b, "9.9.9.9", ALICE, PASSWORD)
        assert r.status_code == 429
        assert r.json()["detail"] == LOCKED_DETAIL
        assert 0 < int(r.headers["Retry-After"]) <= 900

        app_c = await build()  # a restart: fresh process memory, same database
        assert (await _login(app_c, "8.8.8.8", ALICE, PASSWORD)).status_code == 429
        assert (await _token(app_c, "8.8.8.8", ALICE, PASSWORD)).status_code == 429
    finally:
        for ctx in reversed(contexts):
            await ctx.__aexit__(None, None, None)


async def test_failures_persist_across_requests(users_app, alice) -> None:
    for _ in range(2):
        assert (await _login(users_app, "1.1.1.1", ALICE, "wrong")).status_code == 400
    assert (await _alice_row(users_app)).failed_login_count == 2


async def test_token_failures_count_too(users_app, alice) -> None:
    r = await _token(users_app, "1.1.1.1", ALICE, "wrong")
    assert (r.status_code, r.json()["detail"]) == (401, "Invalid credentials")
    assert (await _alice_row(users_app)).failed_login_count == 1


async def test_success_resets_count(users_app, alice) -> None:
    for _ in range(2):
        await _login(users_app, "1.1.1.1", ALICE, "wrong")
    assert (await _login(users_app, "1.1.1.1", ALICE, PASSWORD)).status_code == 204
    row = await _alice_row(users_app)
    assert (row.failed_login_count, row.last_failed_login_at) == (0, None)


async def test_token_success_resets_count(users_app, alice) -> None:
    await _token(users_app, "1.1.1.1", ALICE, "wrong")
    assert (await _token(users_app, "1.1.1.1", ALICE, PASSWORD)).status_code == 200
    assert (await _alice_row(users_app)).failed_login_count == 0


async def test_correct_password_while_locked_does_not_unlock(users_app, alice) -> None:
    for i in range(10):
        await _login(users_app, f"10.0.0.{i}", ALICE, "wrong")
    locked = (await _alice_row(users_app)).locked_until
    assert locked is not None
    assert (await _login(users_app, "9.9.9.9", ALICE, PASSWORD)).status_code == 429
    assert (await _alice_row(users_app)).locked_until == locked


async def test_unknown_and_locked_look_the_same(users_app, alice) -> None:
    for i in range(10):
        await _login(users_app, f"10.0.0.{i}", ALICE, "wrong")
        await _login(users_app, f"10.0.0.{i}", "ghost@example.com", "wrong")
    locked = await _login(users_app, "9.9.9.9", ALICE, PASSWORD)
    unknown = await _login(users_app, "9.9.9.9", "ghost@example.com", "whatever")
    assert locked.status_code == unknown.status_code == 429
    assert locked.json()["detail"] == unknown.json()["detail"] == LOCKED_DETAIL


async def test_tier2_throttles_ip_not_account(users_app, alice) -> None:
    for _ in range(5):
        assert (await _login(users_app, "1.1.1.1", ALICE, "wrong")).status_code == 400
    assert (await _login(users_app, "1.1.1.1", ALICE, PASSWORD)).status_code == 429
    assert (await _token(users_app, "1.1.1.1", ALICE, PASSWORD)).status_code == 429
    assert (await _login(users_app, "2.2.2.2", ALICE, "wrong")).status_code == 400
    assert (await _login(users_app, "2.2.2.2", ALICE, PASSWORD)).status_code == 204


async def test_auth_inner_login_is_gone(users_app, alice) -> None:
    r = await _login(users_app, "1.1.1.1", ALICE, PASSWORD)
    assert r.status_code == 204  # the wrapper still works...
    async with _client(users_app, "1.1.1.1") as c:
        inner = await c.post(
            "/api/users/auth-inner/login", data={"username": ALICE, "password": PASSWORD}
        )
    assert inner.status_code in (404, 405)  # ...the unthrottled stock route does not
