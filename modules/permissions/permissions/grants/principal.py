"""Session-owned grant reads shared by request and headless principals."""

from collections.abc import Collection
from typing import Any

from sqlalchemy import select

from permissions.grants.source import _user_uuid
from permissions.models import RolePermission, UserPermission


async def direct_grants_for(db: Any, user: Any) -> frozenset[str]:
    user_id = _user_uuid(getattr(user, "id", None))
    if user_id is None:
        return frozenset()
    result = await db.execute(
        select(UserPermission.permission_key).where(UserPermission.user_id == user_id)
    )
    return frozenset(result.scalars())


async def role_overlays(db: Any, roles: Collection[str] | None = None) -> dict[str, list[str]]:
    stmt = select(RolePermission.role_name, RolePermission.permission_key)
    if roles is not None:
        if not roles:
            return {}
        stmt = stmt.where(RolePermission.role_name.in_(roles))
    result = await db.execute(stmt)
    overlays: dict[str, list[str]] = {}
    for role, key in result:
        overlays.setdefault(role, []).append(key)
    return overlays
