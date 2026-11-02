"""The lease handle and the in-process backend (GH #539), on a fake clock."""

from __future__ import annotations

import asyncio

import pytest
from simple_module_core.leases import (
    InProcessLeaseBackend,
    LeaseNotAcquiredError,
    configure_leases,
    get_leases,
    lease,
    semaphore,
)


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> _Clock:
    return _Clock()


@pytest.fixture
def backend(clock: _Clock) -> InProcessLeaseBackend:
    return InProcessLeaseBackend(clock=clock)


@pytest.fixture(autouse=True)
def _restore_default():
    yield
    configure_leases(None)


async def test_racing_acquirers_exactly_one_wins(backend: InProcessLeaseBackend) -> None:
    handles = [lease("import:42", 10, blocking=False, backend=backend) for _ in range(10)]
    results = await asyncio.gather(*(h.acquire() for h in handles))
    assert results.count(True) == 1


async def test_after_ttl_old_owner_cannot_release(
    backend: InProcessLeaseBackend, clock: _Clock
) -> None:
    old = lease("job", 10, blocking=False, backend=backend)
    assert await old.acquire()
    clock.now += 11
    new = lease("job", 10, blocking=False, backend=backend)
    assert await new.acquire()

    assert await old.release() is False
    assert await old.refresh() is False
    assert await lease("job", 10, blocking=False, backend=backend).acquire() is False
    assert await new.release() is True


async def test_refresh_extends_from_now(backend: InProcessLeaseBackend, clock: _Clock) -> None:
    held = lease("job", 10, blocking=False, backend=backend)
    assert await held.acquire()
    clock.now += 8
    assert await held.refresh()
    clock.now += 8  # 16 s after acquire, 8 s after refresh
    assert await lease("job", 10, blocking=False, backend=backend).acquire() is False


async def test_fence_strictly_increases_across_owners(
    backend: InProcessLeaseBackend, clock: _Clock
) -> None:
    fences = []
    for _ in range(3):
        held = lease("job", 1, blocking=False, backend=backend)
        assert await held.acquire()
        fences.append(held.fence)
        clock.now += 2  # let it lapse rather than release
    assert fences == sorted(set(fences)) and len(fences) == 3


async def test_semaphore_caps_concurrent_holders(backend: InProcessLeaseBackend) -> None:
    active = 0
    peak = 0

    async def worker() -> None:
        nonlocal active, peak
        async with semaphore("dl:example.org", 4, 30, backend=backend):
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)  # intentional-sleep: overlap the holders
            active -= 1

    await asyncio.gather(*(worker() for _ in range(8)))
    assert peak == 4


async def test_semaphore_expired_slot_is_reclaimed(
    backend: InProcessLeaseBackend, clock: _Clock
) -> None:
    holders = [semaphore("s", 2, 5, blocking=False, backend=backend) for _ in range(3)]
    assert [await h.acquire() for h in holders] == [True, True, False]
    clock.now += 6
    assert await holders[2].acquire()
    assert await holders[0].release() is False


async def test_context_manager_raises_when_wait_runs_out(backend: InProcessLeaseBackend) -> None:
    async with lease("busy", 30, backend=backend):
        with pytest.raises(LeaseNotAcquiredError):
            async with lease("busy", 30, wait=0.05, backend=backend):
                pass  # pragma: no cover


async def test_blocking_acquire_waits_for_release(backend: InProcessLeaseBackend) -> None:
    first = lease("q", 30, backend=backend)
    await first.acquire()

    async def release_soon() -> None:
        await asyncio.sleep(0.05)  # intentional-sleep: the holder finishes later
        await first.release()

    task = asyncio.create_task(release_soon())
    second = lease("q", 30, wait=5, backend=backend)
    assert await second.acquire()
    await task


async def test_non_blocking_handle_fails_fast(backend: InProcessLeaseBackend) -> None:
    async with lease("x", 30, backend=backend):
        with pytest.raises(LeaseNotAcquiredError):
            async with lease("x", 30, blocking=False, backend=backend):
                pass  # pragma: no cover


async def test_owner_names_the_token(backend: InProcessLeaseBackend) -> None:
    handle = lease("x", 30, owner="task-1", backend=backend)
    assert handle.token == "task-1"
    assert await handle.acquire()
    # The same owner from another handle (a retried task) re-acquires its own lease.
    again = lease("x", 30, owner="task-1", blocking=False, backend=backend)
    assert await again.acquire()
    assert again.fence > handle.fence


def test_validation() -> None:
    with pytest.raises(ValueError, match="ttl"):
        lease("x", 0)
    with pytest.raises(ValueError, match="slots"):
        semaphore("x", 0, 10)


async def test_configure_leases_sets_the_process_default(backend: InProcessLeaseBackend) -> None:
    configure_leases(backend)
    assert get_leases() is backend
    handle = lease("y", 30)
    assert await handle.acquire()
    assert await backend.release("y", handle.token) is True
    configure_leases(None)
    assert get_leases() is not backend
