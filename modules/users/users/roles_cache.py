"""Cached list of roles for admin-page rendering.

Roles are seed data: migrations seed ``user`` and ``create_admin`` adds
``admin`` the first time an administrator is created (the setup wizard).
Caching on ``app.state`` lets admin views build Inertia payloads without a
per-request ``SELECT * FROM users_role``.

The cache stores detached :class:`RoleSummary` values (not ORM objects, which
would blow up on attribute access after their session closes). Each view is
responsible for shaping them into whatever the page needs.

Refresh entry points:

* ``UsersModule.on_startup`` — initial population.
* ``publish_roles_changed(app)`` — announces on :data:`CHANNEL` that the role
  set changed (the setup wizard's first-administrator action, since
  ``create_admin`` may create the admin role). Every worker, the publisher
  included, empties its cache and the next read repopulates it lazily.
* ``refresh_roles_cache(app)`` — reload now in this process.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from simple_module_core.app_state import get_services
from sqlalchemy import select

from users.models import Role

if TYPE_CHECKING:
    from fastapi import FastAPI
    from simple_module_core.invalidation import InvalidationBus

logger = logging.getLogger(__name__)

CHANNEL = "users.roles"


@dataclass(frozen=True, slots=True)
class RoleSummary:
    """Minimal role projection safe to hold across request boundaries."""

    id: str
    name: str


async def refresh_roles_cache(app: FastAPI) -> list[RoleSummary]:
    """Reload the roles list from the DB into ``app.state.users.roles_cache``."""
    async with app.state.sm.db.session_factory() as db:
        result = await db.execute(select(Role).order_by(Role.name))
        cached = [RoleSummary(id=str(r.id), name=r.name) for r in result.scalars().all()]
    app.state.users.roles_cache = cached
    return cached


async def get_roles_cache(app: FastAPI) -> list[RoleSummary]:
    """Return the cached roles list, populating it from the DB on first miss.

    The cache is pre-warmed in ``UsersModule.on_startup``. The lazy fallback
    covers scenarios where startup ran before the ``users_role`` table had any
    rows. Once populated, subsequent calls are O(1) attribute reads.
    """
    cached = app.state.users.roles_cache
    if cached:
        return cached
    return await refresh_roles_cache(app)


def forget_roles_cache(app: FastAPI) -> None:
    """Empty this process's cache; :func:`get_roles_cache` refills it on next read."""
    app.state.users.roles_cache = []


def subscribe(bus: InvalidationBus, app: FastAPI) -> None:
    """Wire :data:`CHANNEL` to :func:`forget_roles_cache` for *app*."""
    bus.subscribe(CHANNEL, lambda _invalidation: forget_roles_cache(app))


async def publish_roles_changed(app: FastAPI) -> None:
    """Tell every worker the role set changed. Call after the change committed.

    Falls back to a local eviction when the app has no bus (single-module test
    harnesses), so the change is never silently ignored.
    """
    bus = getattr(get_services(app), "invalidation", None)
    if bus is None:
        forget_roles_cache(app)
        return
    await bus.publish(CHANNEL)
