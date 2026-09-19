"""Broadcasting a ``session_version`` bump to the other worker processes.

``session_version_cache`` is the cache; this is its invalidation. Kept apart so
the cache file stays a cache — no framework imports, no notion of other
processes — and so the one security-relevant question ("who else still honours
the sessions this revocation was meant to strand?") is answered in one place.

Before the framework grew an :class:`~simple_module_core.invalidation.InvalidationBus`,
a revocation dropped the cached counter in the worker that performed it and
nowhere else: every other worker kept admitting the revoked sessions until its
own entry expired (GH #318). Publishing on the bus closes that window wherever a
transport is installed, and degrades to exactly the old behaviour where one is
not — the publishing worker still sees its own invalidation, because it is a
local subscriber like any other.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from users.session_version_cache import clear_session_version_cache, forget_session_version

if TYPE_CHECKING:
    from fastapi import FastAPI
    from simple_module_core.invalidation import Invalidation, InvalidationBus

logger = logging.getLogger(__name__)

__all__ = ["CHANNEL", "apply_invalidation", "publish_revocation", "subscribe"]

CHANNEL = "users.session_version"
"""Carries one account's user id, or ``None`` for "forget every account"."""


def _cache_key(key: str):
    """Turn a wire key back into what the cache is keyed by.

    The cache is keyed by ``User.id``, a :class:`uuid.UUID`, while the wire
    carries strings — so a remote message that popped the *string* would find
    nothing and the whole mechanism would be a silent no-op. That is the failure
    this function exists to prevent, and what
    ``test_session_revocation.py::test_wire_key_evicts_a_uuid_keyed_entry``
    pins down.

    Falls back to the raw string for an id that is not a UUID, so an install
    with a different user-id type loses cross-process invalidation rather than
    raising inside a handler.
    """
    try:
        return uuid.UUID(key)
    except (ValueError, AttributeError, TypeError):
        return key


def apply_invalidation(invalidation: Invalidation) -> None:
    """Drop the cached counter named by *invalidation*. The bus handler."""
    if invalidation.key is None:
        clear_session_version_cache()
        return
    forget_session_version(_cache_key(invalidation.key))


def subscribe(bus: InvalidationBus) -> None:
    """Wire :func:`apply_invalidation` to :data:`CHANNEL`."""
    bus.subscribe(CHANNEL, apply_invalidation)


async def publish_revocation(app: FastAPI, user_id) -> None:
    """Announce that this account's ``session_version`` changed.

    Call it from a ``db.on_commit`` callback, never inline. Clearing the cache
    before the row is durable means a failed commit leaves the cache empty and
    the counter unchanged, so the next read repopulates the *old* value and
    quietly re-admits everything the revocation was meant to end — and a
    broadcast of an invalidation that then rolled back would spread that to
    every other worker.

    Falls back to a local eviction when there is no bus, which is the case in a
    single-module test harness (``build_test_app``) rather than in any real app.
    Silently doing nothing there would make a revocation look like it worked.
    """
    bus = getattr(getattr(app.state, "sm", None), "invalidation", None)
    if bus is None:
        logger.debug("No invalidation bus on this app; dropping %s locally", user_id)
        forget_session_version(user_id)
        return
    await bus.publish(CHANNEL, key=str(user_id))
