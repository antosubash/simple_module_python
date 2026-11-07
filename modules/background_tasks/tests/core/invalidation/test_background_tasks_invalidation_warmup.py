"""The listener warms the connection a publish will use (GH #880).

``publish`` runs under a 1 s budget in the request's response cycle, and the
client's command connection opens lazily. Without a warm-up the first publish
after boot, or after an outage, paid the TCP connect inside that second and lost
the message under load. The listener PINGs the command client after every
successful SUBSCRIBE, off the request path, so that connection is already open.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from background_tasks.core import invalidation as bg_invalidation
from background_tasks.core.invalidation import RedisInvalidationTransport
from simple_module_core.invalidation import Invalidation, InvalidationBus
from simple_module_test import wait_for

_CHANNEL = "sm.invalidation.warmup"


class _PubSub:
    def __init__(self, frames, subscribe_error) -> None:
        self._frames = list(frames)
        self._subscribe_error = subscribe_error
        self.subscribed = False

    async def subscribe(self, channel: str) -> None:
        if self._subscribe_error is not None:
            raise self._subscribe_error
        self.subscribed = True

    async def get_message(self, ignore_subscribe_messages: bool = False, timeout=None):
        if self._frames:
            return self._frames.pop(0)
        await asyncio.sleep(timeout or 0)  # intentional-sleep: fake idle-channel poll interval
        return None

    async def aclose(self) -> None: ...


class _Redis:
    """Records PINGs; the first ``fail_subscribes`` subscriptions raise."""

    def __init__(self, frames=(), fail_subscribes=0, ping_error=None, ping_hangs=False) -> None:
        self.pings = 0
        self.pubsubs: list[_PubSub] = []
        self._frames = frames
        self._fail_subscribes = fail_subscribes
        self._ping_error = ping_error
        self._ping_hangs = ping_hangs

    def pubsub(self) -> _PubSub:
        error = None
        if self._fail_subscribes:
            self._fail_subscribes -= 1
            error = ConnectionError("redis down")
        ps = _PubSub(self._frames, error)
        self.pubsubs.append(ps)
        return ps

    async def ping(self) -> bool:
        self.pings += 1
        if self._ping_hangs:
            await asyncio.Event().wait()
        if self._ping_error is not None:
            raise self._ping_error
        return True

    async def aclose(self) -> None: ...


@pytest.fixture
def fake_redis(monkeypatch):
    import redis.asyncio as aioredis

    def install(**kwargs) -> _Redis:
        fake = _Redis(**kwargs)
        monkeypatch.setattr(aioredis, "from_url", lambda *a, **kw: fake)
        return fake

    monkeypatch.setattr(bg_invalidation, "INITIAL_BACKOFF_SECONDS", 0.01)
    monkeypatch.setattr(bg_invalidation, "LISTEN_POLL_SECONDS", 0.01)
    return install


def _frame(key: str) -> dict:
    wire = Invalidation(channel=_CHANNEL, key=key, origin="elsewhere").to_wire()
    return {"type": "message", "data": wire.encode()}


class TestWarmUp:
    async def test_the_listener_pings_once_it_has_subscribed(self, fake_redis):
        fake = fake_redis()
        transport = RedisInvalidationTransport(InvalidationBus(), "redis://fake", _CHANNEL)
        await transport.start()
        try:
            await wait_for(lambda: fake.pings == 1)
            assert fake.pubsubs[0].subscribed
        finally:
            await transport.stop()

    async def test_a_reconnect_warms_again(self, fake_redis):
        """A Redis restart drops both connections; the resubscribe re-warms."""
        fake = fake_redis(fail_subscribes=1)
        transport = RedisInvalidationTransport(InvalidationBus(), "redis://fake", _CHANNEL)
        await transport.start()
        try:
            await wait_for(lambda: fake.pings == 1)
            assert [ps.subscribed for ps in fake.pubsubs] == [False, True]
        finally:
            await transport.stop()

    async def test_no_ping_before_a_subscribe_succeeds(self, fake_redis):
        fake = fake_redis(fail_subscribes=10**6)
        transport = RedisInvalidationTransport(InvalidationBus(), "redis://fake", _CHANNEL)
        await transport.start()
        try:
            await wait_for(lambda: len(fake.pubsubs) >= 3)
            assert fake.pings == 0
        finally:
            await transport.stop()


class TestAFailedWarmUpIsHarmless:
    @pytest.mark.parametrize("ping", ["raises", "hangs"])
    async def test_the_listener_still_delivers(self, fake_redis, monkeypatch, ping):
        monkeypatch.setattr(bg_invalidation, "SUBSCRIBE_TIMEOUT_SECONDS", 0.05)
        if ping == "raises":
            fake = fake_redis(frames=[_frame("k")], ping_error=ConnectionError("no"))
        else:
            fake = fake_redis(frames=[_frame("k")], ping_hangs=True)
        bus = InvalidationBus()
        seen: list[Invalidation] = []
        bus.subscribe(_CHANNEL, seen.append)
        transport = RedisInvalidationTransport(bus, "redis://fake", _CHANNEL)
        await transport.start()
        try:
            await wait_for(lambda: bool(seen))
        finally:
            await transport.stop()

        assert [i.key for i in seen] == ["k"]
        assert len(fake.pubsubs) == 1, "a failed warm-up must not restart the listener"


class TestAgainstARealServer:
    async def test_a_publish_reuses_the_warmed_connection(self, redis_server):
        """The server sees the PING'd connection, and the publish arrives on it.

        Clients are found by a per-test ``client_name`` (parsed from the URL by
        redis-py): under xdist every worker shares one Redis, so counting all of
        the server's clients would race the other workers.
        """
        import redis.asyncio as aioredis

        name = f"sm-warmup-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        sep = "&" if "?" in redis_server else "?"
        transport = RedisInvalidationTransport(
            InvalidationBus(), f"{redis_server}{sep}client_name={name}", _CHANNEL
        )
        probe = aioredis.from_url(redis_server)

        async def ours() -> list[dict]:
            return [c for c in await probe.client_list() if c.get("name") == name]

        async def warmed() -> list[dict]:
            clients = await ours()
            return clients if any(c["cmd"] == "ping" for c in clients) else []

        await transport.start()
        try:
            before = await wait_for(warmed, timeout=5.0)
            await transport.publish(
                Invalidation(channel=_CHANNEL, key="k", origin="elsewhere").to_wire()
            )
            after = await ours()
        finally:
            await transport.stop()
            await probe.aclose()

        assert len(before) == 2, "expected the subscription plus one warmed command connection"
        warmed_id = next(c["id"] for c in before if c["cmd"] == "ping")
        assert {c["id"] for c in after} == {c["id"] for c in before}, (
            "publish opened a new connection"
        )
        assert next(c["cmd"] for c in after if c["id"] == warmed_id) == "publish"
