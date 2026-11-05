"""Direct per-user grants as a framework grant source, cached per application.

Registered on the :class:`~simple_module_core.permissions.PermissionRegistry`
so the framework's one permission resolution — the door (``RequiresPermission``),
the menu filter and the frontend's ``auth.permissions`` — honours a grant made
on the permissions screen. Before this, only ``permissions.deps`` read the
table, so the same grant was a 200 on this module's routes and a 403 on every
other module's (GH #337).

The source runs on every authenticated request, so it caches the same way
``users.session_version_cache`` does: a bounded TTL as the floor, and an
``InvalidationBus`` message so a change made in one worker drops the entry in
every worker that has a transport. The worker that made the change always
drops its own entry, because it is a local subscriber like any other.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any
from weakref import WeakKeyDictionary

from cachetools import TTLCache
from simple_module_core.app_state import get_services
from simple_module_core.invalidation import Invalidation
from simple_module_core.singleflight import MISS, SingleFlight, fill
from sqlalchemy import select

from permissions.models import UserPermission

if TYPE_CHECKING:
    from fastapi import FastAPI, Request
    from simple_module_core.invalidation import InvalidationBus

logger = logging.getLogger(__name__)

__all__ = [
    "CHANNEL",
    "GRANTS_TTL_SECONDS",
    "apply_invalidation",
    "clear_grants_cache",
    "direct_grant_source",
    "publish_grants_changed",
    "subscribe",
]

CHANNEL = "permissions.user_grants"
"""Carries one user id, or ``None`` for "forget every user"."""

GRANTS_TTL_SECONDS = 30
"""How long one user's direct grants are reused without re-reading.

The window only matters for a revocation made in *another* worker with no
invalidation transport installed; see the module docstring.
"""

_CACHES: WeakKeyDictionary = WeakKeyDictionary()
_FLIGHTS: WeakKeyDictionary[FastAPI, SingleFlight] = WeakKeyDictionary()
# Bumped by every invalidation so a read started earlier never caches stale grants.
_epoch = 0


def _cache(app: FastAPI) -> TTLCache:
    cache = _CACHES.get(app)
    if cache is None:
        cache = TTLCache(maxsize=10_000, ttl=GRANTS_TTL_SECONDS)
        _CACHES[app] = cache
    return cache


def clear_grants_cache() -> None:
    """Empty the cache — for tests that need a cold read."""
    apply_invalidation(Invalidation(CHANNEL))


def _user_uuid(raw: Any) -> uuid.UUID | None:
    """The user id as the table stores it, or ``None`` for a non-UUID principal.

    A principal resolver may authenticate something that is not a ``users``
    row (an API key, a service account); it holds no direct grants rather
    than turning every one of its requests into a logged exception.
    """
    try:
        return uuid.UUID(str(raw))
    except (ValueError, TypeError, AttributeError):
        return None


async def direct_grant_source(request: Request, user: Any) -> frozenset[str]:
    """The keys granted directly to *user*. A ``GrantSource``."""
    user_id = _user_uuid(getattr(user, "id", None))
    if user_id is None:
        return frozenset()
    grants = _cache(request.app)
    # One ``get``, not ``in`` then ``[]``: a TTLCache entry can expire between.
    cached = grants.get(user_id, MISS)
    if cached is not MISS:
        return cached
    if (flight := _FLIGHTS.get(request.app)) is None:
        flight = _FLIGHTS[request.app] = SingleFlight()
    async with flight.hold(user_id):

        async def read() -> frozenset[str]:
            async with request.app.state.sm.db.session_factory() as db:
                result = await db.execute(
                    select(UserPermission.permission_key).where(UserPermission.user_id == user_id)
                )
                return frozenset(result.scalars().all())

        def store(keys: frozenset[str]) -> None:
            grants[user_id] = keys

        return await fill(
            read, epoch=lambda: _epoch, store=store, cached=lambda: grants.get(user_id, MISS)
        )


def apply_invalidation(invalidation: Invalidation, app: FastAPI | None = None) -> None:
    """Drop grants for this app; app-less maintenance callers forget all caches."""
    global _epoch
    _epoch += 1
    if app is None:
        caches = list(_CACHES.values())
    else:
        # ``get``, not ``_cache``: an invalidation must not allocate a cache.
        caches = [cache] if (cache := _CACHES.get(app)) is not None else []
    for cache in caches:
        if invalidation.key is None:
            cache.clear()
        else:
            user_id = _user_uuid(invalidation.key)
            if user_id is not None:
                cache.pop(user_id, None)


def subscribe(bus: InvalidationBus, app: FastAPI) -> None:
    bus.subscribe(CHANNEL, lambda message: apply_invalidation(message, app))


async def publish_grants_changed(app: FastAPI, user_id: uuid.UUID) -> None:
    """Announce that *user_id*'s direct grants changed.

    Call it from a ``db.on_commit`` callback: evicting before the rows are
    durable lets the next read re-cache the old grants, and a rolled-back
    change must not be broadcast. Falls back to a local eviction when the app
    has no bus (a single-module test harness), so a change never looks inert.
    """
    bus = getattr(get_services(app), "invalidation", None)
    if bus is None:
        logger.debug("No invalidation bus on this app; dropping %s locally", user_id)
        apply_invalidation(Invalidation(CHANNEL, key=str(user_id)), app)
        return
    await bus.publish(CHANNEL, key=str(user_id))
