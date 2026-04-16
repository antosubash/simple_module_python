"""Cached list of roles for admin-page rendering.

Roles are seed data — created by the ``e3ce9754e6dc_seed_users_roles``
migration and only mutated by hand. Caching on ``app.state`` lets admin views
build Inertia payloads without a per-request ``SELECT * FROM users_role``.

The cache stores detached :class:`RoleSummary` values (not ORM objects, which
would blow up on attribute access after their session closes). Each view is
responsible for shaping them into whatever the page needs.

Refresh entry points:

* ``UsersModule.on_startup`` — initial population.
* ``refresh_roles_cache(app)`` — callable after any future role-management
  code paths that add/remove roles.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select

from users.models import Role

if TYPE_CHECKING:
    from fastapi import FastAPI

_ROLES_CACHE_KEY = "users_roles_cache"


@dataclass(frozen=True, slots=True)
class RoleSummary:
    """Minimal role projection safe to hold across request boundaries."""

    id: str
    name: str


async def refresh_roles_cache(app: FastAPI) -> list[RoleSummary]:
    """Reload the roles list from the DB into ``app.state.users_roles_cache``."""
    async with app.state.db.session_factory() as db:
        result = await db.execute(select(Role).order_by(Role.name))
        cached = [RoleSummary(id=str(r.id), name=r.name) for r in result.scalars().all()]
    setattr(app.state, _ROLES_CACHE_KEY, cached)
    return cached


async def get_roles_cache(app: FastAPI) -> list[RoleSummary]:
    """Return the cached roles list, populating it from the DB on first miss.

    The cache is pre-warmed in ``UsersModule.on_startup``. The lazy fallback
    covers scenarios where startup ran before the ``users_role`` table had any
    rows (e.g. tests that use ``metadata.create_all`` instead of running the
    seed migration, or staged deployments that seed roles separately). Once
    populated, subsequent calls are O(1) attribute reads.
    """
    cached = getattr(app.state, _ROLES_CACHE_KEY, None)
    if cached:
        return cached
    return await refresh_roles_cache(app)
