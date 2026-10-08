"""Direct per-user grants as a framework grant source, cached per process.

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

from cachetools import TTLCache
from sqlalchemy import select

from permissions.models import UserPermission

if TYPE_CHECKING:
    from fastapi import FastAPI, Request
    from simple_module_core.invalidation import Invalidation, InvalidationBus

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

_GRANTS: TTLCache = TTLCache(maxsize=10_000, ttl=GRANTS_TTL_SECONDS)
_MISS = object()


def clear_grants_cache() -> None:
    """Empty the cache — for tests that need a cold read."""
    _GRANTS.clear()


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
    # One ``get``, not ``in`` then ``[]``: a TTLCache entry can expire between.
    cached = _GRANTS.get(user_id, _MISS)
    if cached is not _MISS:
        return cached
    session_factory = request.app.state.sm.db.session_factory
    async with session_factory() as db:
        result = await db.execute(
            select(UserPermission.permission_key).where(UserPermission.user_id == user_id)
        )
        keys = frozenset(result.scalars().all())
    _GRANTS[user_id] = keys
    return keys


def apply_invalidation(invalidation: Invalidation) -> None:
    """Drop the cached grants named by *invalidation*. The bus handler."""
    if invalidation.key is None:
        _GRANTS.clear()
        return
    user_id = _user_uuid(invalidation.key)
    if user_id is not None:
        _GRANTS.pop(user_id, None)


def subscribe(bus: InvalidationBus) -> None:
    bus.subscribe(CHANNEL, apply_invalidation)


async def publish_grants_changed(app: FastAPI, user_id: uuid.UUID) -> None:
    """Announce that *user_id*'s direct grants changed.

    Call it from a ``db.on_commit`` callback: evicting before the rows are
    durable lets the next read re-cache the old grants, and a rolled-back
    change must not be broadcast. Falls back to a local eviction when the app
    has no bus (a single-module test harness), so a change never looks inert.
    """
    bus = getattr(getattr(app.state, "sm", None), "invalidation", None)
    if bus is None:
        logger.debug("No invalidation bus on this app; dropping %s locally", user_id)
        _GRANTS.pop(user_id, None)
        return
    await bus.publish(CHANNEL, key=str(user_id))
