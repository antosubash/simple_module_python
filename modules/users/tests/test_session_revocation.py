"""A revocation in one worker reaches the other workers' caches.

``session_version`` is cached per process, so before GH #318 the worker that
performed a revocation dropped its own entry and every *other* worker kept
admitting the revoked sessions until its entry expired. These tests stand in for
the second worker with a second :class:`InvalidationBus`, which is exactly what
the Redis transport connects.

The unglamorous one is
:meth:`TestWireKey.test_wire_key_evicts_a_uuid_keyed_entry`: the cache is keyed
by ``uuid.UUID`` and the wire carries strings, so a handler that popped the
string would find nothing and the whole mechanism would be a silent no-op that
every other test here would still pass.
"""

from __future__ import annotations

import uuid

import pytest
from simple_module_core.invalidation import InvalidationBus
from users.session_revocation import CHANNEL, publish_revocation, subscribe
from users.session_version_cache import (
    clear_session_version_cache,
    peek_session_version,
    read_session_version,
    store_session_version,
)


@pytest.fixture(autouse=True)
def _empty_cache():
    clear_session_version_cache()
    yield
    clear_session_version_cache()


class _RecordingTransport:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def publish(self, message: str) -> None:
        self.sent.append(message)


class _FakeApp:
    """Minimal stand-in for the bits of ``request.app`` that are read."""

    def __init__(self, bus: InvalidationBus | None) -> None:
        class _Sm:
            invalidation = bus

        class _State:
            pass

        self.state = _State()
        if bus is not None:
            self.state.sm = _Sm()


class TestWireKey:
    async def test_wire_key_evicts_a_uuid_keyed_entry(self):
        """The cache key is a UUID; the wire key is a string. They must meet."""
        bus = InvalidationBus()
        subscribe(bus)
        user_id = uuid.uuid4()
        store_session_version(user_id, 3)

        # Arrives as if from another process: a string key, a foreign origin.
        await bus.deliver(
            f'{{"v": 1, "channel": "{CHANNEL}", "key": "{user_id}", "origin": "other-worker"}}'
        )

        assert read_session_version(user_id) == (False, None)

    async def test_a_non_uuid_key_does_not_raise(self):
        """An install with a different id type loses the fan-out, not the request."""
        bus = InvalidationBus()
        subscribe(bus)
        store_session_version("plain-string-id", 1)

        await bus.deliver(
            f'{{"v": 1, "channel": "{CHANNEL}", "key": "plain-string-id", "origin": "other"}}'
        )

        assert peek_session_version("plain-string-id") is None

    async def test_a_key_less_message_clears_the_whole_cache(self):
        bus = InvalidationBus()
        subscribe(bus)
        first, second = uuid.uuid4(), uuid.uuid4()
        store_session_version(first, 1)
        store_session_version(second, 2)

        await bus.deliver(f'{{"v": 1, "channel": "{CHANNEL}", "key": null, "origin": "other"}}')

        assert read_session_version(first) == (False, None)
        assert read_session_version(second) == (False, None)


class TestPublish:
    async def test_the_revoking_worker_drops_its_own_entry(self):
        """The property that already held, and must keep holding."""
        bus = InvalidationBus()
        subscribe(bus)
        user_id = uuid.uuid4()
        store_session_version(user_id, 4)

        await publish_revocation(_FakeApp(bus), user_id)

        assert read_session_version(user_id) == (False, None)

    async def test_another_worker_is_told(self):
        """One bus publishes, a second bus applies — the point of the exercise.

        Both buses share this process's one module-level cache, so the eviction
        cannot be attributed to the *second* worker's own dict. What is asserted
        instead is the link the second worker depends on: the publishing bus put
        a message on the transport, and feeding that message to a bus that never
        published anything runs the eviction. In production the two buses are in
        different processes with a Redis channel between them.
        """
        publisher = InvalidationBus()
        subscribe(publisher)
        transport = _RecordingTransport()
        publisher.set_transport(transport)

        other_worker = InvalidationBus()
        subscribe(other_worker)

        user_id = uuid.uuid4()
        await publish_revocation(_FakeApp(publisher), user_id)
        assert transport.sent, "the revocation was never broadcast"

        store_session_version(user_id, 7)
        await other_worker.deliver(transport.sent[0])

        assert read_session_version(user_id) == (False, None)

    async def test_no_bus_falls_back_to_a_local_eviction(self):
        """``build_test_app`` has no ``app.state.sm``; a revocation still works."""
        user_id = uuid.uuid4()
        store_session_version(user_id, 2)

        await publish_revocation(_FakeApp(None), user_id)

        assert read_session_version(user_id) == (False, None)


class TestModuleWiring:
    def test_the_users_module_subscribes_the_channel(self):
        """``register_invalidations`` is what connects the cache to the bus.

        Asserted through the hook rather than the helper: dropping the hook from
        the module (or from the boot phase that calls it) is the refactor that
        would silently restore the original bug.
        """
        from users.module import UsersModule

        bus = InvalidationBus()
        UsersModule().register_invalidations(bus, app=None)  # type: ignore[arg-type]

        assert CHANNEL in bus.channels

    async def test_the_boot_phase_calls_the_hook(self, app):
        """The real app's bus has the channel wired by ``create_app``."""
        assert CHANNEL in app.state.sm.invalidation.channels
