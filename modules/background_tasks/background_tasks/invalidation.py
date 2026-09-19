"""Redis pub/sub transport for the framework's :class:`InvalidationBus`.

This module owns the app's Redis connection already — one URL, one set of
settings, one health check. Cross-process cache invalidation needs exactly that
connection and nothing else, so it is installed from here rather than opened a
second time inside whichever module happens to keep a cache (GH #318). A module
→ framework import is fine; the reverse is what ``SM009`` forbids, which is why
the bus itself knows nothing about Redis.

Every framework channel shares one Redis channel. The volume is a handful of
messages per revocation or settings save, and ``Invalidation.channel`` routes
inside the receiving process, so one subscription is less machinery for the same
result — and it means a module that adds a channel after boot needs no
resubscribe.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simple_module_core.invalidation import InvalidationBus

logger = logging.getLogger(__name__)

__all__ = ["RedisInvalidationTransport"]

INITIAL_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 30.0

PUBLISH_TIMEOUT_SECONDS = 1.0
"""Ceiling on how long a publish may hold up the request that triggered it.

``publish`` is awaited inside the response cycle — a password change's
``db.on_commit`` callback runs before the response is sent — and redis-py
defaults to *no* socket timeout, so a Redis that accepts connections but stops
answering would hang that request indefinitely rather than degrade the fan-out.
One second is far more than a local round trip needs and far less than a user
waits. Exceeding it raises, which the bus logs and swallows: the local eviction
has already happened, so the cost of the timeout is the same staleness window
that existed before this transport.
"""


class RedisInvalidationTransport:
    """Publishes to, and listens on, one Redis pub/sub channel.

    Satisfies ``simple_module_core.invalidation.InvalidationTransport``
    structurally — no import of the Protocol at runtime, so this file costs
    nothing when the bus is unused.
    """

    def __init__(self, bus: InvalidationBus, url: str, channel: str) -> None:
        self._bus = bus
        self._url = url
        self._channel = channel
        self._client = None
        self._listener: asyncio.Task | None = None
        self._warned = False

    async def start(self) -> None:
        """Open the client and start the listener task.

        Does **not** wait for a successful connection, and does not raise if
        Redis is down. Invalidation is an accelerator over a TTL that already
        bounds staleness, so an unreachable broker must degrade the app to
        per-process caching — its behaviour before this existed — rather than
        fail the boot of a web worker that can otherwise serve every request.
        ``/health`` already reports Redis; this logs a warning naming the
        consequence so the two agree.
        """
        import redis.asyncio as aioredis

        # A connect timeout as well as the per-call one below: without it a host
        # that swallows SYN packets blocks the listener's first attempt forever
        # instead of failing into the reconnect loop.
        self._client = aioredis.from_url(
            self._url,
            socket_connect_timeout=PUBLISH_TIMEOUT_SECONDS,
        )
        self._listener = asyncio.create_task(self._listen(), name="sm-invalidation-listener")

    async def publish(self, message: str) -> None:
        """Broadcast one encoded invalidation. Raises — the bus logs it.

        Bounded by :data:`PUBLISH_TIMEOUT_SECONDS`, because this runs inside the
        response cycle of the request that made the write.
        """
        if self._client is None:
            raise RuntimeError("RedisInvalidationTransport.start() was not called")
        async with asyncio.timeout(PUBLISH_TIMEOUT_SECONDS):
            await self._client.publish(self._channel, message)

    async def stop(self) -> None:
        """Cancel the listener and close the client."""
        if self._listener is not None:
            self._listener.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._listener
            self._listener = None
        if self._client is not None:
            with contextlib.suppress(Exception):
                await self._client.aclose()
            self._client = None

    async def _listen(self) -> None:
        """Subscribe and hand every message to the bus, reconnecting forever.

        Reconnects rather than giving up after the first failure: a Redis that
        is briefly unreachable during a deploy would otherwise leave this worker
        with cross-process invalidation permanently off, which is the original
        bug wearing a warning message. Backoff is capped so a long outage does
        not turn into a reconnect storm when it ends.

        Only the *first* failure of a run logs at warning. A worker that
        outlives an hour of downtime should not have written an hour of
        identical lines, but the state still has to be visible once.
        """
        backoff = INITIAL_BACKOFF_SECONDS
        while True:
            pubsub = None
            try:
                pubsub = self._client.pubsub()
                await pubsub.subscribe(self._channel)
                if self._warned:
                    logger.info("Invalidation listener reconnected to %r", self._channel)
                self._warned = False
                backoff = INITIAL_BACKOFF_SECONDS
                async for raw in pubsub.listen():
                    if raw.get("type") != "message":
                        continue
                    await self._bus.deliver(raw["data"])
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._log_failure(exc)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
            finally:
                if pubsub is not None:
                    with contextlib.suppress(Exception):
                        await pubsub.aclose()

    def _log_failure(self, exc: Exception) -> None:
        """Warn once per outage, then stay quiet about the same outage."""
        if self._warned:
            logger.debug("Invalidation listener still down: %s", exc)
            return
        self._warned = True
        logger.warning(
            "Invalidation listener lost Redis (%s); other workers keep cached "
            "values until they expire. Retrying.",
            exc,
        )
