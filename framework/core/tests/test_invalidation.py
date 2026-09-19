"""The invalidation bus: local fan-out, the wire, and the origin filter.

The properties worth pinning down are the ones a consumer's correctness rests
on. A revocation that reaches the publishing worker but silently skips the
others is the bug GH #318 is about, and a listener that dies on one malformed
payload reintroduces it for the life of the process.
"""

from __future__ import annotations

import pytest
from simple_module_core.invalidation import WIRE_VERSION, Invalidation, InvalidationBus


class _RecordingTransport:
    """Captures what would have gone on the wire."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def publish(self, message: str) -> None:
        self.sent.append(message)


class _BrokenTransport:
    async def publish(self, message: str) -> None:
        raise ConnectionError("redis is down")


class TestLocalFanOut:
    async def test_publish_runs_subscribers_on_the_channel(self):
        bus = InvalidationBus()
        seen: list[Invalidation] = []
        bus.subscribe("users.session_version", seen.append)

        await bus.publish("users.session_version", key="abc")

        assert [(i.channel, i.key) for i in seen] == [("users.session_version", "abc")]

    async def test_other_channels_are_untouched(self):
        bus = InvalidationBus()
        calls: list[str] = []
        bus.subscribe("a", lambda inv: calls.append("a"))
        bus.subscribe("b", lambda inv: calls.append("b"))

        await bus.publish("a")

        assert calls == ["a"]

    async def test_async_and_sync_handlers_both_run(self):
        bus = InvalidationBus()
        calls: list[str] = []

        async def async_handler(inv):
            calls.append("async")

        bus.subscribe("c", async_handler)
        bus.subscribe("c", lambda inv: calls.append("sync"))

        await bus.publish("c")

        assert sorted(calls) == ["async", "sync"]

    async def test_one_failing_handler_does_not_starve_the_others(self):
        """One module's broken eviction must not leave another's cache stale."""
        bus = InvalidationBus()
        calls: list[str] = []

        def boom(inv):
            raise RuntimeError("bad handler")

        bus.subscribe("c", boom)
        bus.subscribe("c", lambda inv: calls.append("ran"))

        await bus.publish("c")

        assert calls == ["ran"]

    async def test_publish_with_no_subscribers_is_a_no_op(self):
        await InvalidationBus().publish("nobody.listening")

    def test_channels_reports_what_has_subscribers(self):
        bus = InvalidationBus()
        bus.subscribe("z", lambda inv: None)
        bus.subscribe("a", lambda inv: None)
        assert bus.channels == ("a", "z")


class TestTransport:
    async def test_publish_forwards_the_encoded_invalidation(self):
        bus = InvalidationBus()
        transport = _RecordingTransport()
        bus.set_transport(transport)

        await bus.publish("users.session_version", key="u1")

        assert len(transport.sent) == 1
        decoded = Invalidation.from_wire(transport.sent[0])
        assert decoded is not None
        assert (decoded.channel, decoded.key, decoded.origin) == (
            "users.session_version",
            "u1",
            bus.origin,
        )

    async def test_no_transport_means_local_only(self):
        bus = InvalidationBus()
        assert bus.has_transport is False
        seen: list[Invalidation] = []
        bus.subscribe("c", seen.append)
        await bus.publish("c")
        assert len(seen) == 1

    async def test_a_broken_transport_still_applies_locally(self):
        """The caller has already committed the write; a dead Redis is not a 500."""
        bus = InvalidationBus()
        bus.set_transport(_BrokenTransport())
        seen: list[Invalidation] = []
        bus.subscribe("c", seen.append)

        await bus.publish("c", key="k")

        assert len(seen) == 1

    async def test_clear_transport_drops_back_to_in_process(self):
        bus = InvalidationBus()
        transport = _RecordingTransport()
        bus.set_transport(transport)
        bus.clear_transport()

        await bus.publish("c")

        assert transport.sent == []
        assert bus.has_transport is False


class TestDeliver:
    async def test_a_remote_message_runs_the_handlers(self):
        publisher = InvalidationBus()
        subscriber = InvalidationBus()
        seen: list[Invalidation] = []
        subscriber.subscribe("users.session_version", seen.append)

        transport = _RecordingTransport()
        publisher.set_transport(transport)
        await publisher.publish("users.session_version", key="u9")
        await subscriber.deliver(transport.sent[0])

        assert [i.key for i in seen] == ["u9"]

    async def test_a_bus_ignores_its_own_broadcast_coming_back(self):
        """Publish already ran the handlers; the echo must not run them twice."""
        bus = InvalidationBus()
        transport = _RecordingTransport()
        bus.set_transport(transport)
        seen: list[Invalidation] = []
        bus.subscribe("c", seen.append)

        await bus.publish("c", key="k")
        await bus.deliver(transport.sent[0])

        assert len(seen) == 1

    async def test_bytes_are_accepted(self):
        """redis-py yields bytes unless the client decodes responses."""
        bus = InvalidationBus()
        seen: list[Invalidation] = []
        bus.subscribe("c", seen.append)

        await bus.deliver(Invalidation(channel="c", key="k", origin="elsewhere").to_wire().encode())

        assert [i.key for i in seen] == ["k"]

    @pytest.mark.parametrize(
        "message",
        [
            b"not json at all",
            b"[]",
            b'{"v": 999, "channel": "c", "key": "k"}',
            b'{"channel": "c"}',
            b'{"v": 1, "channel": 7, "key": "k"}',
            b'{"v": 1, "channel": "c", "key": 7}',
        ],
    )
    async def test_junk_is_dropped_rather_than_raised(self, message):
        """A shared Redis database carries other people's traffic."""
        bus = InvalidationBus()
        seen: list[Invalidation] = []
        bus.subscribe("c", seen.append)

        await bus.deliver(message)

        assert seen == []

    async def test_a_key_less_message_survives_the_round_trip(self):
        """``key=None`` means "forget the whole channel" and must stay None."""
        bus = InvalidationBus()
        seen: list[Invalidation] = []
        bus.subscribe("c", seen.append)

        await bus.deliver(Invalidation(channel="c", origin="elsewhere").to_wire())

        assert [i.key for i in seen] == [None]


class TestOrigin:
    def test_two_buses_do_not_share_an_origin(self):
        """A shared origin would make each ignore the other — silently."""
        assert InvalidationBus().origin != InvalidationBus().origin

    def test_wire_carries_the_current_version(self):
        import json

        assert json.loads(Invalidation(channel="c").to_wire())["v"] == WIRE_VERSION
