"""Redis outages respect lease deadlines and do not break cleanup (#787)."""

import asyncio
import time
from unittest.mock import AsyncMock

import pytest
from redis.exceptions import ConnectionError, TimeoutError
from simple_module_core.leases import _ATTEMPT_FLOOR, LeaseNotAcquiredError, lease, semaphore
from simple_module_hosting._lease_redis import _SOCKET_TIMEOUT, RedisLeaseBackend


@pytest.mark.parametrize("slots", [None, 2])
async def test_unresponsive_redis_respects_wait(slots, caplog) -> None:
    writers = []

    def accept(_reader, writer):
        writers.append(writer)

    try:
        server = await asyncio.start_server(accept, "127.0.0.1", 0)
    except OSError as exc:
        pytest.skip(f"Local TCP binding unavailable: {exc}")
    port = server.sockets[0].getsockname()[1]
    backend = RedisLeaseBackend(f"redis://127.0.0.1:{port}/0")
    held = (
        lease("silent", 10, wait=0.1, backend=backend)
        if slots is None
        else semaphore("silent", slots, 10, wait=0.1, backend=backend)
    )
    try:
        start = time.monotonic()
        assert await held.acquire() is False
        # One attempt is bounded by the per-attempt floor (1 s), not the socket retries.
        assert time.monotonic() - start < 3
        assert held.acquired is False
        assert "WARNING" in caplog.text
    finally:
        # Close the accepted sockets before ``wait_closed``: since 3.12 it waits
        # for every connection the server accepted, so the reverse order hangs.
        await backend._redis().aclose()
        for writer in writers:
            writer.close()
        server.close()
        await server.wait_closed()


@pytest.mark.parametrize("error", [TimeoutError, ConnectionError])
@pytest.mark.parametrize("slots", [None, 2])
async def test_redis_errors_fail_acquire_and_preserve_body_error(error, slots, caplog) -> None:
    client = AsyncMock()
    backend = RedisLeaseBackend("redis://unused", factory=lambda: client)
    held = (
        lease("outage", 10, backend=backend)
        if slots is None
        else semaphore("outage", slots, 10, backend=backend)
    )
    client.eval.side_effect = error("unavailable")
    assert await held.acquire() is False
    with pytest.raises(LeaseNotAcquiredError):
        async with held:
            pytest.fail("unconfirmed lease entered")
    client.eval.side_effect = None
    client.eval.return_value = 1
    with pytest.raises(ValueError, match="body failed"):
        async with held:
            client.eval.side_effect = error("unavailable")
            raise ValueError("body failed")
    assert held.acquired is False
    assert "WARNING" in caplog.text


async def test_redis_client_has_finite_timeouts_and_one_reconnect() -> None:
    backend = RedisLeaseBackend("redis://localhost")
    client = backend._redis()
    try:
        options = client.connection_pool.connection_kwargs
        assert options["socket_timeout"] == _SOCKET_TIMEOUT == 2.0
        assert options["socket_connect_timeout"] == _SOCKET_TIMEOUT
        assert options["retry"].get_retries() == 1
    finally:
        await client.aclose()


@pytest.mark.parametrize("slots", [None, 2])
async def test_stalled_backend_call_is_cancelled_at_deadline(slots, caplog) -> None:
    cancelled = asyncio.Event()

    async def stall(*args):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    client = AsyncMock()
    client.eval.side_effect = stall
    backend = RedisLeaseBackend("redis://unused", factory=lambda: client)
    held = (
        lease("stalled", 10, wait=0.05, backend=backend)
        if slots is None
        else semaphore("stalled", slots, 10, wait=0.05, backend=backend)
    )
    assert await asyncio.wait_for(held.acquire(), 3.0) is False
    assert cancelled.is_set()
    assert not held.acquired
    assert "WARNING" in caplog.text


@pytest.mark.parametrize("wait", [0, 0.1])
async def test_immediate_acquire_can_succeed_with_zero_wait(wait) -> None:
    client = AsyncMock()
    client.eval.return_value = 1
    held = lease(
        "ready", 10, wait=wait, backend=RedisLeaseBackend("redis://unused", factory=lambda: client)
    )
    assert await held.acquire()
    assert await held.release()


async def test_refresh_errors_and_cancellation_still_propagate() -> None:
    client = AsyncMock()
    held = lease("refresh", 10, backend=RedisLeaseBackend("redis://unused", factory=lambda: client))
    client.eval.side_effect = ConnectionError("unavailable")
    with pytest.raises(ConnectionError):
        await held.refresh()
    client.eval.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await held.acquire()


async def test_zero_wait_tolerates_a_slow_but_healthy_backend() -> None:
    """``wait=0`` means "do not queue", so a 200 ms reply still acquires."""

    async def slow(*_args):
        await asyncio.sleep(0.2)  # intentional-sleep: simulated slow backend reply
        return 1

    client = AsyncMock()
    client.eval.side_effect = slow
    held = lease(
        "slow", 10, wait=0, backend=RedisLeaseBackend("redis://unused", factory=lambda: client)
    )
    assert await held.acquire()


async def test_attempt_floor_is_one_second_at_zero_wait() -> None:
    """The floor is the documented 1 s: a 0.8 s reply acquires, a stall gives up at ~1 s."""
    assert _ATTEMPT_FLOOR == 1.0

    delay = 0.8

    async def reply(*_args):
        await asyncio.sleep(delay)  # intentional-sleep: simulated backend latency
        return 1

    client = AsyncMock()
    client.eval.side_effect = reply
    backend = RedisLeaseBackend("redis://unused", factory=lambda: client)
    assert await lease("floor-ok", 10, wait=0, backend=backend).acquire()
    delay = 30
    start = time.monotonic()
    assert await lease("floor-stall", 10, wait=0, backend=backend).acquire() is False
    assert 0.9 <= time.monotonic() - start < 2.5
