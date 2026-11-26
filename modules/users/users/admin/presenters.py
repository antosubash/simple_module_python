"""Shapes shared by the admin Inertia views and the admin REST API."""

from __future__ import annotations

from users.core.roles_cache import get_roles_cache


async def roles_payload(app) -> list[dict[str, str]]:
    """Shape roles-cache entries (``id``, ``name``) for props and JSON."""
    return [{"id": r.id, "name": r.name} for r in await get_roles_cache(app)]
