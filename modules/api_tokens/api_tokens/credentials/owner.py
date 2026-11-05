"""The one definition of an owner a personal token can act for."""

from __future__ import annotations

from typing import Any

from simple_module_core.user_directory import DirectoryUser, UserDirectory


async def usable_owner(directory: UserDirectory, db: Any, owner_id: str) -> DirectoryUser | None:
    """The directory entry for *owner_id*, or ``None`` when it cannot back a token.

    Usable means found, active **and** with roles known: under a provider that
    keeps roles in the IdP (Keycloak) a token would be dead on arrival, since
    the roles are what its scopes are intersected with and "none" is not what
    the owner holds.
    """
    user = (await directory.get_many(db, [owner_id], with_roles=True)).get(owner_id)
    if user is None or not user.is_active or user.roles is None:
        return None
    return user
