"""Tests for the Permissions module: service, API, module hook."""

from __future__ import annotations

import uuid

import httpx
import pytest
from fastapi import FastAPI
from permissions.constants import PERM_MANAGE, PERM_VIEW, PERMISSION_GROUP
from permissions.module import PermissionsModule
from permissions.service import PermissionService
from simple_module_core.permissions import PermissionRegistry
from sqlalchemy.ext.asyncio import AsyncSession

# ── register_permissions hook ──────────────────────────────────


class TestModuleHook:
    def test_declares_view_and_manage(self):
        reg = PermissionRegistry()
        PermissionsModule().register_permissions(reg)
        assert PERM_VIEW in reg.all_permissions
        assert PERM_MANAGE in reg.all_permissions


# ── PermissionService ──────────────────────────────────────────


@pytest.fixture
def registry() -> PermissionRegistry:
    reg = PermissionRegistry()
    reg.add_group("Products", ["products.view", "products.create"])
    reg.add_group(PERMISSION_GROUP, [PERM_VIEW, PERM_MANAGE])
    return reg


async def _seed_role(db: AsyncSession, *, name: str = "user") -> uuid.UUID:
    from users.constants import USER_ROLE_ID
    from users.models import Role

    role = Role(id=USER_ROLE_ID, name=name, description=f"{name} role")
    db.add(role)
    await db.flush()
    return role.id


async def _seed_user(
    db: AsyncSession,
    *,
    email: str = "alice@test",
    roles: list[uuid.UUID] | None = None,
) -> uuid.UUID:
    from users.models import User, UserRole

    user_id = uuid.uuid4()
    db.add(
        User(
            id=user_id,
            email=email,
            hashed_password="x",
            is_active=True,
            is_superuser=False,
            is_verified=True,
        )
    )
    await db.flush()
    for rid in roles or []:
        db.add(UserRole(user_id=user_id, role_id=rid))
    await db.flush()
    return user_id


class TestRoleService:
    async def test_list_registered_groups(
        self, db_session: AsyncSession, registry: PermissionRegistry
    ):
        svc = PermissionService(db_session, registry)
        names = {g.name for g in svc.list_registered_groups()}
        assert {"Products", PERMISSION_GROUP} <= names

    async def test_get_role_permissions_not_found(
        self, db_session: AsyncSession, registry: PermissionRegistry
    ):
        svc = PermissionService(db_session, registry)
        assert await svc.get_role_permissions(uuid.uuid4()) is None

    async def test_set_and_get_role_permissions(
        self, db_session: AsyncSession, registry: PermissionRegistry
    ):
        role_id = await _seed_role(db_session)
        svc = PermissionService(db_session, registry)

        updated = await svc.set_role_permissions(role_id, ["products.view", "products.create"])
        assert updated is not None
        assert updated.permissions == ["products.create", "products.view"]

        fetched = await svc.get_role_permissions(role_id)
        assert fetched is not None
        assert set(fetched.permissions) == {"products.view", "products.create"}

    async def test_set_filters_unregistered_keys(
        self, db_session: AsyncSession, registry: PermissionRegistry
    ):
        role_id = await _seed_role(db_session)
        svc = PermissionService(db_session, registry)
        updated = await svc.set_role_permissions(role_id, ["products.view", "bogus.key"])
        assert updated is not None
        assert updated.permissions == ["products.view"]

    async def test_set_is_replace_semantics(
        self, db_session: AsyncSession, registry: PermissionRegistry
    ):
        role_id = await _seed_role(db_session)
        svc = PermissionService(db_session, registry)
        await svc.set_role_permissions(role_id, ["products.view", "products.create"])
        await svc.set_role_permissions(role_id, ["products.view"])
        fetched = await svc.get_role_permissions(role_id)
        assert fetched is not None
        assert fetched.permissions == ["products.view"]

    async def test_set_updates_registry_role_map(
        self, db_session: AsyncSession, registry: PermissionRegistry
    ):
        role_id = await _seed_role(db_session)
        svc = PermissionService(db_session, registry)
        await svc.set_role_permissions(role_id, ["products.view"])
        assert "products.view" in registry.role_map.get("user", [])

    async def test_load_all_into_registry(
        self, db_session: AsyncSession, registry: PermissionRegistry
    ):
        role_id = await _seed_role(db_session)
        await PermissionService(db_session, registry).set_role_permissions(
            role_id, ["products.view"]
        )
        fresh = PermissionRegistry()
        fresh.add_group("Products", ["products.view", "products.create"])
        await PermissionService(db_session, fresh).load_all_into_registry()
        assert "products.view" in fresh.role_map.get("user", [])


class TestUserService:
    async def test_get_user_permissions_not_found(
        self, db_session: AsyncSession, registry: PermissionRegistry
    ):
        svc = PermissionService(db_session, registry)
        assert await svc.get_user_permissions(uuid.uuid4()) is None

    async def test_set_and_get_user_permissions(
        self, db_session: AsyncSession, registry: PermissionRegistry
    ):
        user_id = await _seed_user(db_session)
        svc = PermissionService(db_session, registry)

        updated = await svc.set_user_permissions(user_id, ["products.view"])
        assert updated is not None
        assert updated.direct == ["products.view"]
        assert updated.inherited == []

        fetched = await svc.get_user_permissions(user_id)
        assert fetched is not None
        assert fetched.direct == ["products.view"]

    async def test_set_filters_unregistered_keys_for_user(
        self, db_session: AsyncSession, registry: PermissionRegistry
    ):
        user_id = await _seed_user(db_session)
        svc = PermissionService(db_session, registry)
        updated = await svc.set_user_permissions(user_id, ["products.view", "bogus"])
        assert updated is not None
        assert updated.direct == ["products.view"]

    async def test_inherited_deduplicated_from_direct(
        self, db_session: AsyncSession, registry: PermissionRegistry
    ):
        role_id = await _seed_role(db_session)
        user_id = await _seed_user(db_session, roles=[role_id])
        svc = PermissionService(db_session, registry)

        await svc.set_role_permissions(role_id, ["products.view"])
        await svc.set_user_permissions(user_id, ["products.view", "products.create"])

        fetched = await svc.get_user_permissions(user_id)
        assert fetched is not None
        assert fetched.direct == ["products.create", "products.view"]
        # products.view is held both directly and via the role → should NOT
        # also appear in `inherited` (that surface should only list keys the
        # user gets *only* from their roles).
        assert fetched.inherited == []

    async def test_resolve_effective_permissions_union(
        self, db_session: AsyncSession, registry: PermissionRegistry
    ):
        role_id = await _seed_role(db_session)
        user_id = await _seed_user(db_session, roles=[role_id])
        svc = PermissionService(db_session, registry)

        await svc.set_role_permissions(role_id, ["products.view"])
        await svc.set_user_permissions(user_id, ["products.create"])

        effective = await svc.resolve_effective_permissions(user_id)
        assert effective == {"products.view", "products.create"}

    async def test_resolve_effective_permissions_missing_user(
        self, db_session: AsyncSession, registry: PermissionRegistry
    ):
        svc = PermissionService(db_session, registry)
        assert await svc.resolve_effective_permissions(uuid.uuid4()) == set()


# ── API endpoints (admin-authenticated) ─────────────────────────


class TestPermissionsAPI:
    async def test_list_registered(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get("/api/permissions/")
        assert resp.status_code == 200
        assert PERMISSION_GROUP in {g["name"] for g in resp.json()}

    async def test_get_role_permissions_not_found(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get(f"/api/permissions/roles/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_put_and_get_role_permissions(
        self, authenticated_client: httpx.AsyncClient, app: FastAPI
    ):
        from users.constants import USER_ROLE_ID, USER_ROLE_NAME
        from users.models import Role

        async with app.state.sm.db.session_factory() as db:
            if await db.get(Role, USER_ROLE_ID) is None:
                db.add(Role(id=USER_ROLE_ID, name=USER_ROLE_NAME, description="Standard user"))
                await db.commit()

        resp = await authenticated_client.put(
            f"/api/permissions/roles/{USER_ROLE_ID}",
            json={"permissions": [PERM_VIEW]},
        )
        assert resp.status_code == 200
        assert resp.json()["permissions"] == [PERM_VIEW]
        assert resp.json()["role"]["name"] == "user"

        fetch = await authenticated_client.get(f"/api/permissions/roles/{USER_ROLE_ID}")
        assert fetch.status_code == 200
        assert fetch.json()["permissions"] == [PERM_VIEW]

    async def test_put_requires_permissions_field(
        self, authenticated_client: httpx.AsyncClient, app: FastAPI
    ):
        from users.constants import USER_ROLE_ID, USER_ROLE_NAME
        from users.models import Role

        async with app.state.sm.db.session_factory() as db:
            if await db.get(Role, USER_ROLE_ID) is None:
                db.add(Role(id=USER_ROLE_ID, name=USER_ROLE_NAME, description="Standard user"))
                await db.commit()

        seeded = await authenticated_client.put(
            f"/api/permissions/roles/{USER_ROLE_ID}",
            json={"permissions": [PERM_VIEW]},
        )
        assert seeded.status_code == 200

        missing = await authenticated_client.put(f"/api/permissions/roles/{USER_ROLE_ID}", json={})
        assert missing.status_code == 422

        unchanged = await authenticated_client.get(f"/api/permissions/roles/{USER_ROLE_ID}")
        assert unchanged.status_code == 200
        assert unchanged.json()["permissions"] == [PERM_VIEW]

        cleared = await authenticated_client.put(
            f"/api/permissions/roles/{USER_ROLE_ID}",
            json={"permissions": []},
        )
        assert cleared.status_code == 200
        assert cleared.json()["permissions"] == []

    async def test_put_missing_role_returns_404(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.put(
            f"/api/permissions/roles/{uuid.uuid4()}",
            json={"permissions": []},
        )
        assert resp.status_code == 404

    async def test_get_user_permissions_not_found(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get(f"/api/permissions/users/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_put_and_get_user_permissions(
        self, authenticated_client: httpx.AsyncClient, app: FastAPI
    ):
        # The authenticated_client fixture seeded admin@test — grant a direct
        # permission to that user and round-trip it through the API.
        async with app.state.sm.db.session_factory() as db:
            from sqlalchemy import select
            from users.models import User

            user_id = (
                await db.execute(select(User.id).where(User.email == "admin@test"))
            ).scalar_one()

        resp = await authenticated_client.put(
            f"/api/permissions/users/{user_id}",
            json={"permissions": [PERM_VIEW]},
        )
        assert resp.status_code == 200
        assert resp.json()["direct"] == [PERM_VIEW]

        fetch = await authenticated_client.get(f"/api/permissions/users/{user_id}")
        assert fetch.status_code == 200
        assert fetch.json()["direct"] == [PERM_VIEW]

    async def test_list_requires_auth(self, client: httpx.AsyncClient):
        # Unauthenticated API requests are redirected to the login page
        # by the auth middleware before ever reaching RequiresPermission.
        resp = await client.get("/api/permissions/")
        assert resp.status_code in (302, 401, 403)
