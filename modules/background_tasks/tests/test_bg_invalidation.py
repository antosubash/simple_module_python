"""The Redis transport: it publishes, it listens, and it survives an outage.

No real Redis. The client is replaced with a fake, because what needs pinning
down is this file's own behaviour — that an unreachable broker degrades the app
to per-process caching instead of failing a boot or a request, and that the
listener reconnects rather than dying on the first error. A test against a live
Redis would cover the parts redis-py already tests and none of that.
"""

from __future__ import annotations

import asyncio

import pytest
from background_tasks import invalidation as bg_invalidation
from background_tasks.invalidation import RedisInvalidationTransport
from background_tasks.settings import BackgroundTasksSettings
from simple_module_core.invalidation import Invalidation, InvalidationBus


class _FakePubSub:
    """Yields a scripted sequence of pub/sub frames, then blocks forever."""

    def __init__(self, frames, subscribe_error=None) -> None:
        self._frames = frames
        self._subscribe_error = subscribe_error
        self.subscribed: list[str] = []
        self.closed = False

    async def subscribe(self, channel: str) -> None:
        if self._subscribe_error is not None:
            error, self._subscribe_error = self._subscribe_error, None
            raise error
        self.subscribed.append(channel)

    async def listen(self):
        for frame in self._frames:
            yield frame
        await asyncio.Event().wait()  # a real subscription never ends on its own

    async def aclose(self) -> None:
        self.closed = True


class _FakeRedis:
    def __init__(
        self, frames=(), subscribe_error=None, publish_error=None, publish_hangs=False
    ) -> None:
        self.published: list[tuple[str, str]] = []
        self.pubsubs: list[_FakePubSub] = []
        self._frames = frames
        self._subscribe_error = subscribe_error
        self._publish_error = publish_error
        self._publish_hangs = publish_hangs
        self.closed = False

    def pubsub(self) -> _FakePubSub:
        ps = _FakePubSub(self._frames, self._subscribe_error)
        self._subscribe_error = None
        self.pubsubs.append(ps)
        return ps

    async def publish(self, channel: str, message: str) -> None:
        if self._publish_hangs:
            await asyncio.Event().wait()
        if self._publish_error is not None:
            raise self._publish_error
        self.published.append((channel, message))

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def patched_redis(monkeypatch):
    """Swap ``redis.asyncio.from_url`` for a factory returning our fake."""
    import redis.asyncio as aioredis

    made: list[_FakeRedis] = []

    def install(**kwargs) -> _FakeRedis:
        fake = _FakeRedis(**kwargs)
        monkeypatch.setattr(aioredis, "from_url", lambda *a, **kw: fake)
        made.append(fake)
        return fake

    yield install


async def _settle() -> None:
    """Let the listener task run up to its next await."""
    for _ in range(10):
        await asyncio.sleep(0)


class TestPublishing:
    async def test_a_published_invalidation_reaches_the_channel(self, patched_redis):
        fake = patched_redis()
        bus = InvalidationBus()
        transport = RedisInvalidationTransport(bus, "redis://x/0", "chan")
        await transport.start()
        bus.set_transport(transport)
        try:
            await bus.publish("users.session_version", key="u1")
        finally:
            await transport.stop()

        assert len(fake.published) == 1
        channel, message = fake.published[0]
        assert channel == "chan"
        decoded = Invalidation.from_wire(message)
        assert decoded is not None
        assert (decoded.channel, decoded.key) == ("users.session_version", "u1")

    async def test_publish_before_start_is_a_clear_error(self):
        transport = RedisInvalidationTransport(InvalidationBus(), "redis://x/0", "chan")
        with pytest.raises(RuntimeError, match="start"):
            await transport.publish("{}")

    async def test_a_hung_broker_does_not_hang_the_request(self, patched_redis, monkeypatch):
        """redis-py has no socket timeout by default; this runs in the response cycle."""
        patched_redis(publish_hangs=True)
        monkeypatch.setattr(bg_invalidation, "PUBLISH_TIMEOUT_SECONDS", 0.01)
        bus = InvalidationBus()
        seen: list[Invalidation] = []
        bus.subscribe("c", seen.append)
        transport = RedisInvalidationTransport(bus, "redis://x/0", "chan")
        await transport.start()
        bus.set_transport(transport)
        try:
            await asyncio.wait_for(bus.publish("c", key="k"), timeout=2)
        finally:
            await transport.stop()

        assert len(seen) == 1, "the local eviction must still have happened"

    async def test_a_failing_publish_does_not_reach_the_caller(self, patched_redis):
        """The write is already committed; a dead broker must not 500 the request."""
        patched_redis(publish_error=ConnectionError("down"))
        bus = InvalidationBus()
        seen: list[Invalidation] = []
        bus.subscribe("c", seen.append)
        transport = RedisInvalidationTransport(bus, "redis://x/0", "chan")
        await transport.start()
        bus.set_transport(transport)
        try:
            await bus.publish("c", key="k")
        finally:
            await transport.stop()

        assert len(seen) == 1, "the local eviction must still have happened"


class TestListening:
    async def test_an_inbound_message_is_delivered_to_the_bus(self, patched_redis):
        wire = Invalidation(channel="c", key="k", origin="another-worker").to_wire()
        patched_redis(frames=[{"type": "subscribe"}, {"type": "message", "data": wire.encode()}])
        bus = InvalidationBus()
        seen: list[Invalidation] = []
        bus.subscribe("c", seen.append)

        transport = RedisInvalidationTransport(bus, "redis://x/0", "chan")
        await transport.start()
        try:
            await _settle()
        finally:
            await transport.stop()

        assert [i.key for i in seen] == ["k"]

    async def test_non_message_frames_are_ignored(self, patched_redis):
        patched_redis(frames=[{"type": "subscribe", "data": 1}, {"type": "psubscribe"}])
        bus = InvalidationBus()
        seen: list[Invalidation] = []
        bus.subscribe("c", seen.append)

        transport = RedisInvalidationTransport(bus, "redis://x/0", "chan")
        await transport.start()
        try:
            await _settle()
        finally:
            await transport.stop()

        assert seen == []

    async def test_the_listener_reconnects_after_a_failure(
        self, patched_redis, caplog, monkeypatch
    ):
        """A broker that blinks during a deploy must not disable this for good."""
        wire = Invalidation(channel="c", key="k", origin="another-worker").to_wire()
        patched_redis(
            frames=[{"type": "message", "data": wire}],
            subscribe_error=ConnectionError("redis is down"),
        )
        bus = InvalidationBus()
        seen: list[Invalidation] = []
        bus.subscribe("c", seen.append)

        # Collapse the backoff so the retry lands inside the test.
        monkeypatch.setattr(bg_invalidation, "INITIAL_BACKOFF_SECONDS", 0.0)
        transport = RedisInvalidationTransport(bus, "redis://x/0", "chan")
        await transport.start()
        try:
            for _ in range(50):
                await asyncio.sleep(0)
                if seen:
                    break
        finally:
            await transport.stop()

        assert [i.key for i in seen] == ["k"], "the second attempt should have subscribed"
        assert any("keep cached values until they expire" in r.message for r in caplog.records)

    async def test_stop_cancels_the_listener_and_closes_the_client(self, patched_redis):
        fake = patched_redis()
        transport = RedisInvalidationTransport(InvalidationBus(), "redis://x/0", "chan")
        await transport.start()
        await _settle()
        await transport.stop()

        assert fake.closed is True
        assert all(ps.closed for ps in fake.pubsubs)
        # Idempotent: shutdown can run after a failed startup.
        await transport.stop()


class TestSettings:
    def test_broadcast_is_on_by_default(self, monkeypatch):
        monkeypatch.delenv("SM_BG_TASKS_BROADCAST_INVALIDATIONS", raising=False)
        assert BackgroundTasksSettings().broadcast_invalidations is True

    def test_an_operator_can_turn_it_off(self, monkeypatch):
        monkeypatch.setenv("SM_BG_TASKS_BROADCAST_INVALIDATIONS", "false")
        assert BackgroundTasksSettings().broadcast_invalidations is False

    def test_the_channel_is_namespaced_and_overridable(self, monkeypatch):
        monkeypatch.delenv("SM_BG_TASKS_INVALIDATION_CHANNEL", raising=False)
        assert BackgroundTasksSettings().invalidation_channel == "simple_module.invalidation"
        monkeypatch.setenv("SM_BG_TASKS_INVALIDATION_CHANNEL", "app-two.invalidation")
        assert BackgroundTasksSettings().invalidation_channel == "app-two.invalidation"


class TestModuleGate:
    async def test_no_transport_is_installed_when_broadcast_is_off(self):
        """What the test suite relies on: no Redis listener per app fixture."""
        from background_tasks.module import BackgroundTasksModule

        bus = InvalidationBus()
        app = _StubApp(bus, BackgroundTasksSettings(broadcast_invalidations=False))
        await BackgroundTasksModule._start_invalidation_transport(app)

        assert bus.has_transport is False
        assert app.state.background_tasks.invalidation_transport is None

    async def test_the_transport_is_installed_when_broadcast_is_on(self, patched_redis):
        from background_tasks.module import BackgroundTasksModule

        patched_redis()
        bus = InvalidationBus()
        app = _StubApp(bus, BackgroundTasksSettings(broadcast_invalidations=True))
        await BackgroundTasksModule._start_invalidation_transport(app)
        try:
            assert bus.has_transport is True
        finally:
            await app.state.background_tasks.invalidation_transport.stop()


class _StubApp:
    def __init__(self, bus: InvalidationBus, settings: BackgroundTasksSettings) -> None:
        from background_tasks.services import BackgroundTasksServices

        class _Sm:
            invalidation = bus

        class _State:
            pass

        self.state = _State()
        self.state.sm = _Sm()
        self.state.background_tasks = BackgroundTasksServices(settings=settings)
