"""Every lease backend honours the same contract (GH #539).

In-process, the ``sm_lease`` table (SQLite here; Postgres under
``make test-py-pg``) and Redis (``redis_server``: skipped locally without
``redis-server``, required on CI) run the same tests.
"""

from __future__ import annotations

import asyncio
import itertools
import uuid
from collections.abc import AsyncIterator

import pytest
from simple_module_core.leases import InProcessLeaseBackend, LeaseBackend, lease, semaphore
from simple_module_db.leases import DbLeaseBackend, LeaseRow
from simple_module_hosting._lease_redis import RedisLeaseBackend
from simple_module_test import wait_for

_SHORT_TTL = 0.3
_LONG_TTL = 30.0


@pytest.fixture(params=["inprocess", "db", "redis"])
async def backend(request: pytest.FixtureRequest, engine) -> AsyncIterator[LeaseBackend]:
    if request.param == "inprocess":
        yield InProcessLeaseBackend()
    elif request.param == "db":
        async with engine.begin() as conn:
            await conn.run_sync(LeaseRow.metadata.create_all)
        yield DbLeaseBackend(engine)
    else:
        url = request.getfixturevalue("redis_server")
        redis_backend = RedisLeaseBackend(url)
        yield redis_backend
        client = redis_backend._redis()
        # Only this process's names: CI's xdist workers share one Redis, and a
        # broader pattern deleted another worker's live semaphore mid-test.
        keys = [k async for k in client.scan_iter(match=f"sm:*:{_PREFIX}*")]
        if keys:
            await client.delete(*keys)
        await client.aclose()


_PREFIX = f"t-{uuid.uuid4().hex[:12]}-"


def _name() -> str:
    return f"{_PREFIX}{uuid.uuid4().hex}"


async def test_two_racing_acquirers_one_wins(backend: LeaseBackend) -> None:
    name = _name()
    handles = [lease(name, _LONG_TTL, blocking=False, backend=backend) for _ in range(2)]
    results = await asyncio.gather(*(h.acquire() for h in handles))
    assert sorted(results) == [False, True]


async def test_expired_owner_cannot_release_or_refresh(backend: LeaseBackend) -> None:
    name = _name()
    old = lease(name, _SHORT_TTL, blocking=False, backend=backend)
    assert await old.acquire()
    new = lease(name, _LONG_TTL, blocking=False, backend=backend)
    assert await wait_for(new.acquire, timeout=5)

    assert await old.refresh() is False
    assert await old.release() is False
    # The new owner still holds it: nobody else gets in.
    assert await lease(name, _LONG_TTL, blocking=False, backend=backend).acquire() is False
    assert await new.refresh() is True
    assert await new.release() is True


async def test_expired_owner_cannot_release_even_when_unclaimed(backend: LeaseBackend) -> None:
    held = lease(_name(), _SHORT_TTL, blocking=False, backend=backend)
    assert await held.acquire()
    # Probing with acquire() would claim it; the point is that nobody did.
    await asyncio.sleep(_SHORT_TTL * 2)  # intentional-sleep: let the TTL lapse unclaimed
    assert await held.release() is False


async def test_fence_strictly_increases(backend: LeaseBackend) -> None:
    name = _name()
    fences = []
    for _ in range(4):
        async with lease(name, _LONG_TTL, backend=backend) as held:
            fences.append(held.fence)
    assert all(a < b for a, b in itertools.pairwise(fences)), fences


async def test_released_lease_is_free_again(backend: LeaseBackend) -> None:
    name = _name()
    first = lease(name, _LONG_TTL, blocking=False, backend=backend)
    assert await first.acquire()
    assert await first.release() is True
    assert await first.release() is False
    assert await lease(name, _LONG_TTL, blocking=False, backend=backend).acquire()


async def test_semaphore_never_exceeds_its_slots(backend: LeaseBackend) -> None:
    name = _name()
    active = 0
    peak = 0

    async def worker() -> None:
        nonlocal active, peak
        async with semaphore(name, 4, _LONG_TTL, wait=10, backend=backend):
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.2)  # intentional-sleep: hold the slot so holders overlap
            active -= 1

    await asyncio.gather(*(worker() for _ in range(8)))
    assert peak == 4


async def test_semaphore_admits_n_then_refuses(backend: LeaseBackend) -> None:
    name = _name()
    holders = [semaphore(name, 4, _LONG_TTL, blocking=False, backend=backend) for _ in range(5)]
    results = await asyncio.gather(*(h.acquire() for h in holders))
    assert sorted(results) == [False, True, True, True, True]
    fences = [h.fence for h in holders if h.acquired]
    assert len(set(fences)) == 4

    winner = next(h for h in holders if h.acquired)
    assert await winner.refresh() is True
    assert await winner.release() is True
    loser = next(h for h in holders if not h.acquired)
    assert await loser.acquire() is True


async def test_semaphore_reclaims_expired_holders(backend: LeaseBackend) -> None:
    name = _name()
    stale = semaphore(name, 1, _SHORT_TTL, blocking=False, backend=backend)
    assert await stale.acquire()
    fresh = semaphore(name, 1, _LONG_TTL, blocking=False, backend=backend)
    assert await wait_for(fresh.acquire, timeout=5)
    assert await stale.refresh() is False
    assert await stale.release() is False
    assert await fresh.release() is True


@pytest.mark.postgres
async def test_postgres_lease_race_across_connections(engine) -> None:
    """Real parallel transactions on separate connections: exactly one winner."""
    async with engine.begin() as conn:
        await conn.run_sync(LeaseRow.metadata.create_all)
    backend = DbLeaseBackend(engine)
    name = _name()
    handles = [lease(name, _LONG_TTL, blocking=False, backend=backend) for _ in range(12)]
    results = await asyncio.gather(*(h.acquire() for h in handles))
    assert results.count(True) == 1

    sem = [semaphore(name + "s", 4, _LONG_TTL, blocking=False, backend=backend) for _ in range(12)]
    assert (await asyncio.gather(*(h.acquire() for h in sem))).count(True) == 4


async def test_names_that_look_like_internal_keys_do_not_collide(backend: LeaseBackend) -> None:
    base = _name()
    first = await backend.acquire(base, "a", _LONG_TTL)
    second = await backend.acquire(f"{base}:fence", "b", _LONG_TTL)
    assert first == 1
    assert second == 1  # its own holder and its own counter
    assert await backend.release(base, "a")
    third = await backend.acquire(base, "c", _LONG_TTL)
    assert third == 2
    sem = await backend.semaphore_acquire(f"{base}:sem:fence", "s", 1, _LONG_TTL)
    assert sem == 1
