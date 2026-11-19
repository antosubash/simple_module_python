"""Versioned invalidation messages, compatible with legacy publishers (#986)."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)
_decode_failure_warned = False

WIRE_VERSION = 1
"""Bumped for incompatible wire changes; version 1 accepts additive fields.

A message carrying any other version is dropped rather than guessed at, so a
rolling deploy in which half the workers run new code degrades to "no
cross-process invalidation between the two halves" instead of to a decode
exception in the listener loop.
"""


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
    #: back in (see ``users.accounts.session_revocation``).
    key: str | None = None
    #: The publishing process's :attr:`InvalidationBus.origin`. Lets a bus
    #: ignore its own broadcast coming back off the transport, which it has
    #: already applied locally.
    origin: str = ""
    #: Optional for compatibility with pre-bridge publishers on wire version 1.
    message_id: str | None = None

    def to_wire(self) -> str:
        """JSON, because a transport is free to be anything that moves text."""
        return json.dumps(
            {
                "v": WIRE_VERSION,
                "channel": self.channel,
                "key": self.key,
                "origin": self.origin,
                "id": self.message_id,
            }
        )

    @classmethod
    def from_wire(cls, message: str | bytes) -> Invalidation | None:
        """Parse a wire message, or ``None`` when it isn't one of ours.

        Returns rather than raises on anything unexpected. A Redis database is
        routinely shared — with another app, with a stray ``redis-cli publish``,
        with the previous version of this code — and a listener loop that dies
        on one malformed payload takes cross-process invalidation down for the
        life of the process. Decode exceptions warn once per process with a
        traceback; unsupported shapes remain ordinary shared-database traffic.
        """
        try:
            data = json.loads(message)
            if not isinstance(data, dict) or data.get("v") != WIRE_VERSION:
                logger.debug("Ignoring invalidation message with unknown shape: %r", message)
                return None
            channel = data["channel"]
            key = data.get("key")
            message_id = data.get("id")
            if (
                not isinstance(channel, str)
                or not isinstance(key, str | None)
                or not isinstance(message_id, str | None)
            ):
                logger.debug("Ignoring invalidation message with bad field types: %r", message)
                return None
            return cls(channel, key, str(data.get("origin") or ""), message_id)
        except Exception:
            global _decode_failure_warned
            if not _decode_failure_warned:
                _decode_failure_warned = True
                logger.warning("Ignoring undecodable invalidation message", exc_info=True)
            return None
