"""A locked unknown username is indistinguishable from a locked account (GH #530)."""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from _users_app_builders import _build_users_app, _make_standard_user
from simple_module_core.rate_limit import InProcessWindowStore
from sqlalchemy import select
from users.auth_local import lockout
from users.manager import UserManager
from users.models import User

ALICE = "alice@example.com"
GHOST = "ghost@example.com"
T0 = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


class _Clock:
    """One clock for the DB tier (``_utcnow``) and the store tier."""

    def __init__(self) -> None:
        self.offset = 0.0

    def now(self) -> datetime:
        return T0 + timedelta(seconds=self.offset)

    def __call__(self) -> float:
        return self.now().timestamp()


@pytest.fixture
def clock(users_app, monkeypatch) -> _Clock:
    clock = _Clock()
    monkeypatch.setattr(lockout, "_utcnow", clock.now)
    store = InProcessWindowStore(clock=clock)
    users_app.state.sm = dataclasses.replace(users_app.state.sm, rate_limit_store=store)
    return clock


async def _login(app, ip: str, username: str, password: str = "wrong") -> httpx.Response:
    transport = httpx.ASGITransport(app=app, client=(ip, 1))
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        return await c.post(
            "/api/users/auth/login", data={"username": username, "password": password}
        )


def _shape(r: httpx.Response) -> tuple:
    return r.status_code, r.json()["detail"], r.headers.get("Retry-After")


async def test_same_count_same_answer_same_duration(users_app, clock) -> None:
    await _make_standard_user(users_app, ALICE)
    shapes: dict[str, list[tuple]] = {ALICE: [], GHOST: []}

    async def both(ip: str) -> None:
        for name in (ALICE, GHOST):
            shapes[name].append(_shape(await _login(users_app, ip, name)))

    # Spaced 250s apart — inside the 300s window of the previous failure, but
    # beyond a fixed window opened by the first. Both tiers must keep counting.
    for i in range(10):
        await both(f"10.0.0.{i}")
        clock.offset += 250 if i < 9 else 0
    clock.offset += 899  # one second before either lock lifts
    await both("10.0.1.1")
    clock.offset += 2
    await both("10.0.1.2")

    assert shapes[ALICE] == shapes[GHOST]
    trace = shapes[ALICE]
    assert [s[0] for s in trace] == [400] * 9 + [429, 429, 400]
    assert trace[9][2] == "900"  # the tripping attempt
    assert trace[10][2] == "1"  # same duration on both


async def test_known_and_unknown_take_the_same_password_path(users_app, monkeypatch) -> None:
    """Timing: an unknown username still pays for a password hash."""
    from fastapi_users.password import PasswordHelper

    await _make_standard_user(users_app, ALICE)
    calls: list[str] = []
    real_hash, real_verify = PasswordHelper.hash, PasswordHelper.verify_and_update

    def hash_(self, password):
        calls.append("hash")
        return real_hash(self, password)

    def verify(self, plain, hashed):
        calls.append("verify")
        return real_verify(self, plain, hashed)

    monkeypatch.setattr(PasswordHelper, "hash", hash_)
    monkeypatch.setattr(PasswordHelper, "verify_and_update", verify)
    await _login(users_app, "1.1.1.1", ALICE)
    known, calls[:] = list(calls), []
    await _login(users_app, "1.1.1.1", GHOST)
    assert known and calls  # each spends one hashing operation
    assert len(known) == len(calls) == 1


async def test_parallel_burst_gets_at_most_threshold_password_checks(monkeypatch, tmp_path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'burst.db'}"
    overrides = {"login_lockout_account_failures": ("5", "int")}
    app, ctx = await _build_users_app(
        monkeypatch, allow_signup=False, database_url=url, overrides=overrides
    )
    try:
        await _make_standard_user(app, ALICE)
        checks: list[str] = []
        real = UserManager.authenticate

        async def counting(self, credentials):
            checks.append(credentials.username)
            await asyncio.sleep(0)  # let the other requests interleave mid-check
            return await real(self, credentials)

        monkeypatch.setattr(UserManager, "authenticate", counting)
        responses = await asyncio.gather(*(_login(app, f"10.0.0.{i}", ALICE) for i in range(20)))
        codes = sorted(r.status_code for r in responses)
        assert len(checks) <= 5
        assert codes.count(400) == 4 and codes.count(429) == 16
        async with app.state.sm.db.session_factory() as session:
            row = (await session.execute(select(User).where(User.email == ALICE))).scalar_one()
        assert row.locked_until is not None
        # The burst neither reset nor overshot the count; the lock reset it to 0.
        assert row.failed_login_count == 0
    finally:
        await ctx.__aexit__(None, None, None)
