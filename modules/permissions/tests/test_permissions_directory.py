"""The user side of the permissions screens reads the user directory (GH #501)."""

from __future__ import annotations

import uuid

from permissions.service import PermissionService
from simple_module_core.permissions import ADMIN_ROLE, PermissionRegistry
from simple_module_core.user_directory import DirectoryUser, NullUserDirectory
from sqlalchemy.ext.asyncio import AsyncSession

_UID = uuid.uuid4()


class _IdpDirectory(NullUserDirectory):
    """An IdP-backed directory: knows the user, not their roles."""

    def __init__(self) -> None:
        self.searches: list[tuple[str | None, int]] = []

    async def get_many(self, db, ids, *, with_roles=False):
        user = DirectoryUser(id=str(_UID), email="idp@example.com", full_name="Ida")
        return {str(_UID): user} if str(_UID) in ids else {}

    async def search(self, db, term, *, limit):
        self.searches.append((term, limit))
        return [DirectoryUser(id=str(_UID), email="idp@example.com")]


def _registry() -> PermissionRegistry:
    reg = PermissionRegistry()
    reg.add_group("Products", ["products.view", "products.create"])
    reg.map_role("editor", ["products.view"])
    return reg


async def test_direct_grants_work_when_roles_are_unknown(db_session: AsyncSession):
    svc = PermissionService(db_session, _registry(), _IdpDirectory())
    updated = await svc.set_user_permissions(_UID, ["products.create"])
    assert updated is not None
    assert updated.user.email == "idp@example.com"
    # Unknown roles are not read as roles held: nothing is inherited.
    assert (updated.roles, updated.inherited) == ([], [])
    assert await svc.resolve_effective_permissions(_UID) == {"products.create"}


async def test_list_users_searches_the_directory(db_session: AsyncSession):
    directory = _IdpDirectory()
    rows = await PermissionService(db_session, _registry(), directory).list_users_with_counts(
        search="idp", limit=5
    )
    assert [(u.email, n) for u, n in rows] == [("idp@example.com", 0)]
    assert directory.searches == [("idp", 5)]


async def test_without_a_directory_nobody_is_found(db_session: AsyncSession):
    svc = PermissionService(db_session, _registry())
    assert await svc.get_user_permissions(_UID) is None
    assert await svc.list_users_with_counts() == []


def test_admin_role_name_comes_from_core():
    """The admin sync keys on core's ``ADMIN_ROLE``, not ``users.constants``."""
    from users.constants import ADMIN_ROLE_NAME

    assert ADMIN_ROLE == ADMIN_ROLE_NAME
