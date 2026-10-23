"""Login lockout through the HTTP routes, across IPs and app instances (GH #530)."""

from __future__ import annotations

import httpx
from _users_app_builders import (
    ALICE,
    _build_users_app,
    _client,
    _login,
    _make_standard_user,
    user_row,
)
from users.auth_local.lockout import LOCKED_DETAIL

PASSWORD = "UserPass1!"


async def _token(app, ip: str, email: str, password: str) -> httpx.Response:
    async with _client(app, ip) as c:
        return await c.post("/api/users/auth/token", json={"email": email, "password": password})


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
        codes = [(await _login(app, ip, ALICE, "wrong")).status_code for app, ip in plan]
        assert codes == [400, 400, 400, 400, 429]  # the fifth trips the lock itself

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
    assert (await user_row(users_app, ALICE)).failed_login_count == 2


async def test_token_failures_count_too(users_app, alice) -> None:
    r = await _token(users_app, "1.1.1.1", ALICE, "wrong")
    assert (r.status_code, r.json()["detail"]) == (401, "Invalid credentials")
    assert (await user_row(users_app, ALICE)).failed_login_count == 1


async def test_success_resets_count(users_app, alice) -> None:
    for _ in range(2):
        await _login(users_app, "1.1.1.1", ALICE, "wrong")
    assert (await _login(users_app, "1.1.1.1", ALICE, PASSWORD)).status_code == 204
    row = await user_row(users_app, ALICE)
    assert (row.failed_login_count, row.last_failed_login_at) == (0, None)


async def test_token_success_resets_count(users_app, alice) -> None:
    await _token(users_app, "1.1.1.1", ALICE, "wrong")
    assert (await _token(users_app, "1.1.1.1", ALICE, PASSWORD)).status_code == 200
    assert (await user_row(users_app, ALICE)).failed_login_count == 0


async def test_correct_password_while_locked_does_not_unlock(users_app, alice) -> None:
    for i in range(10):
        await _login(users_app, f"10.0.0.{i}", ALICE, "wrong")
    locked = (await user_row(users_app, ALICE)).locked_until
    assert locked is not None
    assert (await _login(users_app, "9.9.9.9", ALICE, PASSWORD)).status_code == 429
    assert (await user_row(users_app, ALICE)).locked_until == locked


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


async def test_token_lookup_ignores_case_like_session_login(users_app, alice) -> None:
    for email in (ALICE, "Alice@Example.COM"):
        assert (await _token(users_app, "1.1.1.1", email, PASSWORD)).status_code == 200
        assert (await _login(users_app, "1.1.1.1", email, PASSWORD)).status_code == 204
    # A wrong password under either spelling counts against the one account.
    for email in (ALICE, "ALICE@example.com"):
        assert (await _token(users_app, "2.2.2.2", email, "wrong")).status_code == 401
    assert (await user_row(users_app, ALICE)).failed_login_count == 2


async def test_token_unknown_user_still_pays_for_a_hash(users_app, alice, monkeypatch) -> None:
    from fastapi_users.password import PasswordHelper

    calls: list[str] = []
    real = PasswordHelper.verify_and_update

    def verify(self, plain, hashed):
        calls.append(hashed)
        return real(self, plain, hashed)

    monkeypatch.setattr(PasswordHelper, "verify_and_update", verify)
    r = await _token(users_app, "1.1.1.1", "ghost@example.com", PASSWORD)
    assert r.status_code == 401
    assert len(calls) == 1  # the dummy-hash equaliser ran
