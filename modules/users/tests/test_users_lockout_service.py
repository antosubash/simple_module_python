"""``users.auth_local.lockout`` — both tiers, driven directly (GH #530)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from _users_app_builders import ALICE
from fastapi import HTTPException
from simple_module_core.rate_limit import InProcessWindowStore
from sqlalchemy import select
from users.auth_local import lockout
from users.auth_local.lockout import (
    Admission,
    LoginAttempt,
    admit,
    record_failure,
    record_success,
)
from users.models import User
from users.settings import UsersSettings

T0 = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)


def _attempt(
    username: str = ALICE,
    *,
    now: datetime = T0,
    ip: str = "1.1.1.1",
    store: InProcessWindowStore | None = None,
    account: int = 10,
) -> LoginAttempt:
    settings = UsersSettings(login_lockout_account_failures=account)
    return LoginAttempt.build(username, ip, store or InProcessWindowStore(), settings, now)


async def _fail(session, attempt: LoginAttempt) -> int:
    """One wrong password: admit, then settle. Returns the status it would answer."""
    try:
        admission = await admit(session, attempt)
    except HTTPException as exc:
        return exc.status_code
    locked = await record_failure(session, attempt, admission)
    return locked.status_code if locked else 400


async def _admit_or_status(session, attempt: LoginAttempt) -> Admission | int:
    try:
        return await admit(session, attempt)
    except HTTPException as exc:
        return exc.status_code


async def _row(users_db, user) -> User:
    stmt = select(User).where(User.id == user.id).execution_options(populate_existing=True)
    return (await users_db.execute(stmt)).scalar_one()


async def test_account_locks_on_the_attempt_that_reaches_the_threshold(users_db, alice) -> None:
    # A different IP every time: the account lock does not care where from.
    codes = [await _fail(users_db, _attempt(ip=f"10.0.0.{i}", account=3)) for i in range(4)]
    assert codes == [400, 400, 429, 429]
    row = await _row(users_db, alice)
    assert row.locked_until == T0 + timedelta(seconds=900)
    assert row.failed_login_count == 0


async def test_expired_window_restarts_count(users_db, alice) -> None:
    await _fail(users_db, _attempt(now=T0))
    await _fail(users_db, _attempt(now=T0 + timedelta(seconds=10)))
    await _fail(users_db, _attempt(now=T0 + timedelta(seconds=400)))
    row = await _row(users_db, alice)
    assert row.failed_login_count == 1
    assert row.last_failed_login_at == T0 + timedelta(seconds=400)


async def test_expired_lock_allows_login(users_db, alice) -> None:
    for i in range(3):
        await _fail(users_db, _attempt(ip=f"10.0.0.{i}", account=3))
    later = T0 + timedelta(seconds=901)
    assert isinstance(
        await _admit_or_status(users_db, _attempt(now=later, ip="9.9.9.9")), Admission
    )


async def test_success_resets_count_and_source(users_db, alice) -> None:
    store = InProcessWindowStore()
    for _ in range(4):
        await _fail(users_db, _attempt(store=store))
    attempt = _attempt(store=store)
    await record_success(users_db, attempt, await admit(users_db, attempt))
    await users_db.commit()
    row = await _row(users_db, alice)
    assert (row.failed_login_count, row.last_failed_login_at) == (0, None)
    assert (await store.peek(attempt.ip_key, attempt.ip_spec)).count == 0


async def test_failures_do_not_touch_updated_at(users_db, alice) -> None:
    before = (await _row(users_db, alice)).updated_at
    await _fail(users_db, _attempt())
    assert (await _row(users_db, alice)).updated_at == before


async def test_ip_throttle_after_tier2_limit(users_db, alice) -> None:
    store = InProcessWindowStore()
    codes = [await _fail(users_db, _attempt(ip="1.1.1.1", store=store)) for _ in range(6)]
    assert codes == [400] * 5 + [429]
    assert (await _row(users_db, alice)).failed_login_count == 5  # the 6th never counted
    assert await _fail(users_db, _attempt(ip="2.2.2.2", store=store)) == 400


async def test_username_variants_share_one_counter(users_db, alice) -> None:
    store = InProcessWindowStore()
    await _fail(users_db, _attempt(" Alice@Example.COM ", store=store))
    await _fail(users_db, _attempt(ALICE, store=store))
    assert (await _row(users_db, alice)).failed_login_count == 2
    for _ in range(3):  # ...and the per-IP key is the same one too
        await _fail(users_db, _attempt("ALICE@example.com", store=store))
    assert await _fail(users_db, _attempt(ALICE, store=store)) == 429


# ── Concurrency: a slot is taken before the password is checked ─────────────


async def test_burst_gets_at_most_threshold_password_tries(users_db, alice) -> None:
    """Admissions taken concurrently (none settled yet) stop at the threshold."""
    store = InProcessWindowStore()
    results = [
        await _admit_or_status(users_db, _attempt(ip=f"10.0.0.{i}", store=store, account=3))
        for i in range(8)
    ]
    admitted = [r for r in results if isinstance(r, Admission)]
    assert [a.count for a in admitted] == [1, 2, 3]
    assert results[3:] == [429] * 5
    assert (await _row(users_db, alice)).failed_login_count == 3  # refused ones never counted


async def test_unknown_burst_matches_known_burst(users_db, alice) -> None:
    def statuses(results):
        return [r.count if isinstance(r, Admission) else r for r in results]

    store = InProcessWindowStore()
    known = [
        await _admit_or_status(users_db, _attempt(ALICE, ip=f"10.0.0.{i}", store=store, account=3))
        for i in range(6)
    ]
    ghost = [
        await _admit_or_status(
            users_db, _attempt("ghost@example.com", ip=f"10.0.0.{i}", store=store, account=3)
        )
        for i in range(6)
    ]
    assert statuses(known) == statuses(ghost) == [1, 2, 3, 429, 429, 429]


async def test_success_mid_burst_does_not_lift_a_lock(users_db, alice) -> None:
    store = InProcessWindowStore()
    await _fail(users_db, _attempt(ip="10.0.0.1", store=store, account=3))
    owner = _attempt(ip="10.0.0.2", store=store, account=3)
    owner_slot = await admit(users_db, owner)  # admitted before the lock
    attacker = _attempt(ip="10.0.0.3", store=store, account=3)
    locked = await record_failure(users_db, attacker, await admit(users_db, attacker))
    assert locked is not None and locked.status_code == 429

    await record_success(users_db, owner, owner_slot)  # the owner's password lands last
    await users_db.commit()
    assert (await _row(users_db, alice)).locked_until == T0 + timedelta(seconds=900)
    assert await _admit_or_status(users_db, _attempt(ip="9.9.9.9", store=store)) == 429


async def test_lock_write_survives_concurrent_counting(users_db, users_app, alice) -> None:
    """A counting UPDATE from another worker between the lock's read and write cannot undo it."""
    store = InProcessWindowStore()
    for i in range(2):
        await _fail(users_db, _attempt(ip=f"10.0.0.{i}", store=store, account=3))
    last = _attempt(ip="10.0.0.9", store=store, account=3)
    slot = await admit(users_db, last)
    async with users_app.state.sm.db.session_factory() as other:  # another worker
        assert await _admit_or_status(other, _attempt(ip="10.0.0.8", store=store, account=3)) == 429
    await record_failure(users_db, last, slot)
    assert (await _row(users_db, alice)).locked_until is not None


async def test_lock_landing_after_the_read_reports_the_time_left(users_db, alice) -> None:
    """The conditional UPDATE misses on a lock another worker wrote after the read."""
    for i in range(3):
        await _fail(users_db, _attempt(ip=f"10.0.0.{i}", account=3))  # locked until T0+900
    mid = _attempt(now=T0 + timedelta(seconds=300), ip="9.9.9.9", account=3)
    try:
        await lockout._admit_account(users_db, mid, [None])  # read before the lock landed
    except HTTPException as exc:
        assert (exc.status_code, exc.headers) == (429, {"Retry-After": "600"})
    else:
        raise AssertionError("a locked row was admitted")


def test_overlong_username_is_hashed_in_store_keys() -> None:
    long_name = _attempt("a" * 300 + "@example.com")
    assert len(long_name.key_name) == 64
    assert "a" * 100 not in long_name.ip_key + long_name.account_key + long_name.lock_key
    assert _attempt("b" * 300).key_name != long_name.key_name
    assert _attempt(ALICE).key_name == ALICE  # an address-length name is kept as-is
