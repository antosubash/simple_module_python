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


async def _seed_user_role(db: AsyncSession) -> uuid.UUID:
    """Insert a 'user' role and return its id."""
    from users.constants import USER_ROLE_ID
    from users.models import Role

    role = Role(id=USER_ROLE_ID, name="user", description="Standard user")
    db.add(role)
    await db.flush()
    return role.id


class TestPermissionService:
    async def test_list_registered_groups(
        self, db_session: AsyncSession, registry: PermissionRegistry
    ):
        svc = PermissionService(db_session, registry)
        groups = svc.list_registered_groups()
        names = {g.name for g in groups}
        assert {"Products", "Permissions"} <= names

    async def test_get_role_permissions_not_found(
        self, db_session: AsyncSession, registry: PermissionRegistry
    ):
        svc = PermissionService(db_session, registry)
        result = await svc.get_role_permissions(uuid.uuid4())
        assert result is None

    async def test_set_and_get_role_permissions(
        self, db_session: AsyncSession, registry: PermissionRegistry
    ):
        role_id = await _seed_user_role(db_session)
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
        role_id = await _seed_user_role(db_session)
        svc = PermissionService(db_session, registry)

        updated = await svc.set_role_permissions(role_id, ["products.view", "bogus.key"])
        assert updated is not None
        assert updated.permissions == ["products.view"]

    async def test_set_is_replace_semantics(
        self, db_session: AsyncSession, registry: PermissionRegistry
    ):
        role_id = await _seed_user_role(db_session)
        svc = PermissionService(db_session, registry)

        await svc.set_role_permissions(role_id, ["products.view", "products.create"])
        await svc.set_role_permissions(role_id, ["products.view"])

        fetched = await svc.get_role_permissions(role_id)
        assert fetched is not None
        assert fetched.permissions == ["products.view"]

    async def test_set_updates_registry_role_map(
        self, db_session: AsyncSession, registry: PermissionRegistry
    ):
        role_id = await _seed_user_role(db_session)
        svc = PermissionService(db_session, registry)

        await svc.set_role_permissions(role_id, ["products.view"])
        assert "products.view" in registry.role_map.get("user", [])

    async def test_set_returns_none_for_missing_role(
        self, db_session: AsyncSession, registry: PermissionRegistry
    ):
        svc = PermissionService(db_session, registry)
        result = await svc.set_role_permissions(uuid.uuid4(), ["products.view"])
        assert result is None

    async def test_list_roles_with_counts(
        self, db_session: AsyncSession, registry: PermissionRegistry
    ):
        role_id = await _seed_user_role(db_session)
        svc = PermissionService(db_session, registry)
        await svc.set_role_permissions(role_id, ["products.view", "products.create"])

        rows = await svc.list_roles_with_counts()
        counts = {row.name: count for row, count in rows}
        assert counts.get("user") == 2

    async def test_load_all_into_registry(
        self, db_session: AsyncSession, registry: PermissionRegistry
    ):
        role_id = await _seed_user_role(db_session)
        await PermissionService(db_session, registry).set_role_permissions(
            role_id, ["products.view"]
        )

        # Fresh registry — load should re-populate it from DB.
        fresh = PermissionRegistry()
        fresh.add_group("Products", ["products.view", "products.create"])
        await PermissionService(db_session, fresh).load_all_into_registry()
        assert "products.view" in fresh.role_map.get("user", [])


# ── API endpoints (admin-authenticated) ─────────────────────────


class TestPermissionsAPI:
    async def test_list_registered(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get("/api/permissions/")
        assert resp.status_code == 200
        groups = {g["name"] for g in resp.json()}
        assert PERMISSION_GROUP in groups

    async def test_get_role_permissions_not_found(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.get(f"/api/permissions/roles/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_put_and_get_role_permissions(
        self, authenticated_client: httpx.AsyncClient, app: FastAPI
    ):
        from users.constants import ADMIN_ROLE_ID

        resp = await authenticated_client.put(
            f"/api/permissions/roles/{ADMIN_ROLE_ID}",
            json={"permissions": [PERM_VIEW]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["permissions"] == [PERM_VIEW]
        assert data["role"]["name"] == "admin"

        fetch = await authenticated_client.get(f"/api/permissions/roles/{ADMIN_ROLE_ID}")
        assert fetch.status_code == 200
        assert fetch.json()["permissions"] == [PERM_VIEW]

    async def test_put_missing_role_returns_404(self, authenticated_client: httpx.AsyncClient):
        resp = await authenticated_client.put(
            f"/api/permissions/roles/{uuid.uuid4()}",
            json={"permissions": []},
        )
        assert resp.status_code == 404

    async def test_list_requires_auth(self, client: httpx.AsyncClient):
        # Unauthenticated API requests are redirected to the login page
        # by the auth middleware before ever reaching RequiresPermission.
        resp = await client.get("/api/permissions/")
        assert resp.status_code in (302, 401, 403)
