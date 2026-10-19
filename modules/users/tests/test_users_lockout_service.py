"""``users.auth_local.lockout`` — both tiers, driven directly (GH #530)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from _users_app_builders import _make_standard_user
from simple_module_core.rate_limit import InProcessWindowStore
from sqlalchemy import select
from users.auth_local.lockout import (
    LoginAttempt,
    record_failure,
    record_success,
    refused_for,
)
from users.models import User
from users.settings import UsersSettings

T0 = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


@pytest.fixture
async def alice(users_app):
    return await _make_standard_user(users_app, "alice@example.com")


def _attempt(
    username: str,
    *,
    now: datetime = T0,
    ip: str = "1.1.1.1",
    store: InProcessWindowStore | None = None,
    account: int = 10,
) -> LoginAttempt:
    settings = UsersSettings(login_lockout_account_failures=account)
    return LoginAttempt.build(username, ip, store or InProcessWindowStore(), settings, now)


async def _row(users_db, user) -> User:
    stmt = select(User).where(User.id == user.id).execution_options(populate_existing=True)
    return (await users_db.execute(stmt)).scalar_one()


async def test_account_locks_at_threshold(users_db, alice) -> None:
    for i in range(3):
        # A different IP every time: the account lock does not care where from.
        await record_failure(users_db, _attempt("alice@example.com", ip=f"10.0.0.{i}", account=3))
    row = await _row(users_db, alice)
    assert row.locked_until == T0 + timedelta(seconds=900)
    assert row.failed_login_count == 0
    assert await refused_for(users_db, _attempt("alice@example.com", ip="9.9.9.9")) == 900


async def test_below_threshold_is_not_locked(users_db, alice) -> None:
    for i in range(2):
        await record_failure(users_db, _attempt("alice@example.com", ip=f"10.0.0.{i}", account=3))
    row = await _row(users_db, alice)
    assert (row.failed_login_count, row.locked_until) == (2, None)
    assert await refused_for(users_db, _attempt("alice@example.com", ip="9.9.9.9")) is None


async def test_expired_window_restarts_count(users_db, alice) -> None:
    await record_failure(users_db, _attempt("alice@example.com", now=T0))
    await record_failure(users_db, _attempt("alice@example.com", now=T0 + timedelta(seconds=10)))
    await record_failure(users_db, _attempt("alice@example.com", now=T0 + timedelta(seconds=400)))
    row = await _row(users_db, alice)
    assert row.failed_login_count == 1
    assert row.last_failed_login_at == T0 + timedelta(seconds=400)


async def test_expired_lock_allows_login(users_db, alice) -> None:
    for i in range(3):
        await record_failure(users_db, _attempt("alice@example.com", ip=f"10.0.0.{i}", account=3))
    later = T0 + timedelta(seconds=901)
    assert await refused_for(users_db, _attempt("alice@example.com", now=later)) is None


async def test_success_resets_count(users_db, alice) -> None:
    await record_failure(users_db, _attempt("alice@example.com"))
    await record_failure(users_db, _attempt("alice@example.com"))
    await record_success(users_db, alice.id)
    await users_db.commit()
    row = await _row(users_db, alice)
    assert (row.failed_login_count, row.last_failed_login_at) == (0, None)


async def test_failures_do_not_touch_updated_at(users_db, alice) -> None:
    before = (await _row(users_db, alice)).updated_at
    await record_failure(users_db, _attempt("alice@example.com"))
    assert (await _row(users_db, alice)).updated_at == before


async def test_ip_throttle_after_tier2_limit(users_db, alice) -> None:
    store = InProcessWindowStore()
    for _ in range(5):
        await record_failure(users_db, _attempt("alice@example.com", ip="1.1.1.1", store=store))
    wait = await refused_for(users_db, _attempt("alice@example.com", ip="1.1.1.1", store=store))
    assert wait is not None and wait > 0
    other_ip = _attempt("alice@example.com", ip="2.2.2.2", store=store)
    assert await refused_for(users_db, other_ip) is None


async def test_unknown_username_counts_against_account_threshold(users_db) -> None:
    store = InProcessWindowStore()
    for i in range(10):
        await record_failure(users_db, _attempt("ghost@example.com", ip=f"10.0.0.{i}", store=store))
    fresh_ip = _attempt("ghost@example.com", ip="9.9.9.9", store=store)
    assert await refused_for(users_db, fresh_ip) is not None


async def test_username_variants_share_one_counter(users_db, alice) -> None:
    store = InProcessWindowStore()
    await record_failure(users_db, _attempt(" Alice@Example.COM ", store=store))
    await record_failure(users_db, _attempt("alice@example.com", store=store))
    assert (await _row(users_db, alice)).failed_login_count == 2
    # ...and the per-IP key is the same one too.
    for _ in range(3):
        await record_failure(users_db, _attempt("ALICE@example.com", store=store))
    assert await refused_for(users_db, _attempt("alice@example.com", store=store)) is not None
