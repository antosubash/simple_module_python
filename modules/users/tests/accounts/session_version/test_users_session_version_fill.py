"""Cache fills: one read per account, and never a read that a revocation raced.

A read that started before "sign out everywhere" can finish after the forget.
Storing it would put the old counter back and re-admit every revoked session
in this worker until the TTL ran out.
"""

from __future__ import annotations

import asyncio

import pytest
from users.accounts.session_version_cache import (
    SESSION_VERSION_TTL_SECONDS,
    clear_session_version_cache,
    configure_session_version_cache,
    fill_session_version,
    forget_session_version,
    peek_session_version,
)

_USER = "dana"


@pytest.fixture(autouse=True)
def _cold_cache():
    clear_session_version_cache()
    yield
    configure_session_version_cache(SESSION_VERSION_TTL_SECONDS)
    clear_session_version_cache()


class TestARacedReadIsNotCached:
    @pytest.mark.anyio
    async def test_a_forget_during_the_read_discards_it_and_rereads(self):
        reads = []

        async def read():
            reads.append(len(reads))
            if len(reads) == 1:
                # The revocation commits and forgets while this read is in flight.
                forget_session_version(_USER)
                return 1, frozenset()
            return 2, frozenset()

        assert await fill_session_version(_USER, read) == (2, frozenset())
        assert len(reads) == 2
        assert peek_session_version(_USER) == 2

    @pytest.mark.anyio
    async def test_a_cache_clear_during_the_read_also_discards_it(self):
        calls = 0

        async def read():
            nonlocal calls
            calls += 1
            clear_session_version_cache()
            return calls, frozenset()

        # Every read is raced, so the last one answers this request uncached.
        assert await fill_session_version(_USER, read) == (3, frozenset())
        assert peek_session_version(_USER) is None


class TestConcurrentMissesShareOneRead:
    @pytest.mark.anyio
    async def test_five_waiters_one_read(self):
        reads = 0
        release = asyncio.Event()

        async def read():
            nonlocal reads
            reads += 1
            await release.wait()
            return 4, frozenset({"retired"})

        waiters = [asyncio.create_task(fill_session_version(_USER, read)) for _ in range(5)]
        await asyncio.sleep(0)
        release.set()
        results = await asyncio.gather(*waiters)

        assert reads == 1
        assert results == [(4, frozenset({"retired"}))] * 5


class TestAFailedReadIsNotCached:
    @pytest.mark.anyio
    async def test_the_error_propagates_and_the_next_fill_reads_again(self):
        async def broken():
            raise ConnectionError("database unavailable")

        with pytest.raises(ConnectionError):
            await fill_session_version(_USER, broken)
        assert peek_session_version(_USER) is None

        async def read():
            return 5, frozenset()

        assert await fill_session_version(_USER, read) == (5, frozenset())
