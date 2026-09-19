"""Cache-invalidation fan-out: in-process by default, cross-process when a
transport is installed.

Several modules keep a per-process cache of a row that is cheap to read and
expensive to read *often* — ``users`` caches ``User.session_version`` (the
revocation counter checked on nearly every authenticated request),
``file_storage`` caches its aggregate size, ``settings`` hot-swaps a settings
object in the worker that handled the save. All three share one failure shape:
the worker that performed the write drops its own entry immediately, and
**every other worker keeps serving the stale value until its own entry
expires**.

The obvious fix — publish the write on Redis pub/sub so every worker drops its
entry at once — was not reachable from any of those modules. Redis belongs to
the ``background_tasks`` plugin, so ``users`` would have to open a second
connection with its own settings that can disagree with it; :class:`EventBus`
is deliberately in-process; and ``SM009`` makes a ``framework`` → plugin import
an error, so the framework cannot borrow the plugin's client either (GH #318).

This module is the missing middle. The framework owns the *bus* — the channel
registry, the wire format and the origin filtering — and knows nothing about
how a message reaches another process. Whoever owns a shared backend installs
an :class:`InvalidationTransport` on it; ``background_tasks`` does exactly that
with the Redis connection it already configures. With no transport installed
the bus is honest in-process pub/sub, which is precisely today's behaviour: the
publishing worker sees the invalidation, the others wait out their TTL.

What this is *not*: a message queue. There is no persistence, no retry, no
delivery guarantee. A dropped message costs staleness for the rest of a cache's
TTL, never correctness of the cache's contents — so every consumer must keep a
TTL as its floor and treat the bus as an accelerator. Anything that needs
delivery guarantees wants a Celery task, not this.
"""

from __future__ import annotations

import inspect
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)

__all__ = [
    "WIRE_VERSION",
    "Invalidation",
    "InvalidationBus",
    "InvalidationHandler",
    "InvalidationTransport",
]

WIRE_VERSION = 1
"""Bumped when :meth:`Invalidation.to_wire` changes shape.

A message carrying any other version is dropped rather than guessed at, so a
rolling deploy in which half the workers run new code degrades to "no
cross-process invalidation between the two halves" instead of to a decode
exception in the listener loop.
"""

type InvalidationHandler = Callable[["Invalidation"], Awaitable[None] | None]
"""Sync or async. The caches this exists for are plain dicts, so demanding
``async def`` for a one-line ``pop`` would be ceremony."""


@dataclass(frozen=True, slots=True)
class Invalidation:
    """One "this cached thing changed" notice.

    Deliberately not a :class:`~simple_module_core.events.Event`: a domain event
    describes something that happened in the business ("an order was placed")
    and its handlers may do anything, while this describes something that
    stopped being true in a *cache* and its handlers may only forget. Sharing
    the type would invite a handler that writes to the database on a message
    that carries no delivery guarantee.
    """

    #: Who cares. Convention is ``<module>.<cache>`` — ``users.session_version``.
    channel: str
    #: Which entry, or ``None`` for "the whole channel". A string because it has
    #: to survive JSON; a consumer keyed by something else converts on the way
    #: back in (see ``users.session_revocation``).
    key: str | None = None
    #: The publishing process's :attr:`InvalidationBus.origin`. Lets a bus
    #: ignore its own broadcast coming back off the transport, which it has
    #: already applied locally.
    origin: str = ""

    def to_wire(self) -> str:
        """JSON, because a transport is free to be anything that moves text."""
        return json.dumps(
            {"v": WIRE_VERSION, "channel": self.channel, "key": self.key, "origin": self.origin}
        )

    @classmethod
    def from_wire(cls, message: str | bytes) -> Invalidation | None:
        """Parse a wire message, or ``None`` when it isn't one of ours.

        Returns rather than raises on anything unexpected. A Redis database is
        routinely shared — with another app, with a stray ``redis-cli publish``,
        with the previous version of this code — and a listener loop that dies
        on one malformed payload takes cross-process invalidation down for the
        life of the process. Logged at debug: on a shared database this is
        normal traffic, not a fault.
        """
        try:
            data = json.loads(message)
            if not isinstance(data, dict) or data.get("v") != WIRE_VERSION:
                logger.debug("Ignoring invalidation message with unknown shape: %r", message)
                return None
            channel = data["channel"]
            key = data.get("key")
            if not isinstance(channel, str) or not isinstance(key, str | None):
                logger.debug("Ignoring invalidation message with bad field types: %r", message)
                return None
            return cls(channel=channel, key=key, origin=str(data.get("origin") or ""))
        except Exception:
            logger.debug("Ignoring undecodable invalidation message: %r", message)
            return None


@runtime_checkable
class InvalidationTransport(Protocol):
    """Moves an encoded :class:`Invalidation` to the other processes.

    One method, because the inbound direction is the transport's own business:
    it decides how it listens (a pub/sub subscription, a poll, a test double
    calling straight through) and hands whatever it receives to
    :meth:`InvalidationBus.deliver`, which owns decoding and the origin filter.
    """

    async def publish(self, message: str) -> None:
        """Broadcast *message* to every other process. May raise."""
        ...


class InvalidationBus:
    """Channel registry plus fan-out. One per process, on ``app.state.sm``.

    Subscribers register in ``ModuleBase.register_invalidations``; a transport is
    installed later, in whichever module owns the shared backend, during its
    ``on_startup``. The two are independent on purpose — subscriptions are what
    make the bus useful in a single process, and the transport only widens their
    reach.
    """

    def __init__(self, origin: str | None = None) -> None:
        #: Identifies this process for the lifetime of the process. Random
        #: rather than the pid: pids repeat across containers, and two workers
        #: that believe they share an origin would each ignore the other's
        #: broadcasts — the exact bug this class exists to fix, but silent.
        self.origin = origin or uuid.uuid4().hex
        self._handlers: dict[str, list[InvalidationHandler]] = {}
        self._transport: InvalidationTransport | None = None

    # ── subscription ───────────────────────────────────────

    def subscribe(self, channel: str, handler: InvalidationHandler) -> None:
        """Run *handler* for every invalidation on *channel*, local or remote."""
        self._handlers.setdefault(channel, []).append(handler)
        logger.debug(
            "Subscribed %s to invalidation channel %r",
            getattr(handler, "__qualname__", repr(handler)),
            channel,
        )

    @property
    def channels(self) -> tuple[str, ...]:
        """Channels with at least one subscriber, for diagnostics and tests."""
        return tuple(sorted(self._handlers))

    # ── transport ──────────────────────────────────────────

    def set_transport(self, transport: InvalidationTransport) -> None:
        """Install the shared backend. Replaces any previous one."""
        self._transport = transport
        logger.info("Invalidation transport installed: %s", type(transport).__name__)

    def clear_transport(self) -> None:
        """Drop back to in-process only — the owning module's ``on_shutdown``."""
        self._transport = None

    @property
    def has_transport(self) -> bool:
        """Whether invalidations currently reach other processes."""
        return self._transport is not None

    # ── publishing ─────────────────────────────────────────

    async def publish(self, channel: str, key: str | None = None) -> None:
        """Apply locally, then broadcast.

        Local first, and a transport failure never propagates: the caller is
        typically finishing a write it has already committed — a password change
        that bumped ``session_version`` — and turning "Redis is unreachable"
        into a 500 on that request would trade a bounded staleness window for an
        outright failure. Logged at error, because the operator needs to know
        the fan-out is silently degraded to per-process.
        """
        invalidation = Invalidation(channel=channel, key=key, origin=self.origin)
        await self._dispatch(invalidation)
        transport = self._transport
        if transport is None:
            return
        try:
            await transport.publish(invalidation.to_wire())
        except Exception:
            logger.exception(
                "Invalidation broadcast failed for channel %r; other workers keep "
                "their cached value until it expires",
                channel,
            )

    async def deliver(self, message: str | bytes) -> None:
        """Apply a message that arrived from another process.

        Called by the transport. Messages this process published are dropped —
        :meth:`publish` already ran the handlers, and running them twice would
        be harmless for a ``pop`` but is not a property a handler should have to
        have.
        """
        invalidation = Invalidation.from_wire(message)
        if invalidation is None:
            return
        if invalidation.origin and invalidation.origin == self.origin:
            return
        await self._dispatch(invalidation)

    async def _dispatch(self, invalidation: Invalidation) -> None:
        """Run every handler on the channel, isolating failures.

        Sequential rather than ``gather``: handlers are microsecond-scale cache
        evictions, and a channel with enough of them for concurrency to matter
        would be a design smell. A failing handler must not stop the others —
        one module's broken eviction is not a reason for another's cache to stay
        stale.
        """
        for handler in self._handlers.get(invalidation.channel, ()):
            try:
                result = handler(invalidation)
                if inspect.isawaitable(result):
                    await result
            except Exception:
                logger.exception(
                    "Invalidation handler %s failed for channel %r",
                    getattr(handler, "__qualname__", repr(handler)),
                    invalidation.channel,
                )
