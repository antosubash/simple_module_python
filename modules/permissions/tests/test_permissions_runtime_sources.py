"""Runtime permission sources reach the role editor and are grantable/enforced (GH #334)."""

from __future__ import annotations

import httpx
from fastapi import FastAPI


async def test_source_permission_listed_grantable_and_invalidated(
    authenticated_client: httpx.AsyncClient, app: FastAPI
):
    from users.constants import USER_ROLE_ID, USER_ROLE_NAME
    from users.models import Role

    registry = app.state.sm.permissions
    types = ["product"]
    registry.add_source("records", lambda: [(f"records.{t}.edit", f"Edit {t}") for t in types])

    async with app.state.sm.db.session_factory() as db:
        if await db.get(Role, USER_ROLE_ID) is None:
            db.add(Role(id=USER_ROLE_ID, name=USER_ROLE_NAME, description="Standard user"))
            await db.commit()

    groups = (await authenticated_client.get("/api/permissions/")).json()
    records = next(g for g in groups if g["name"] == "records")
    assert records["permissions"] == ["records.product.edit"]
    assert records["labels"] == {"records.product.edit": "Edit product"}
    # Labels stay inside their own group: static groups carry none.
    assert all(g["labels"] == {} for g in groups if g["name"] != "records")

    put = await authenticated_client.put(
        f"/api/permissions/roles/{USER_ROLE_ID}", json={"permissions": ["records.product.edit"]}
    )
    assert put.status_code == 200
    assert put.json()["permissions"] == ["records.product.edit"]
    assert "records.product.edit" in registry.role_map[USER_ROLE_NAME]

    # A new runtime resource becomes grantable after invalidate_source.
    types.append("faq")
    registry.invalidate_source("records")
    groups = (await authenticated_client.get("/api/permissions/")).json()
    records = next(g for g in groups if g["name"] == "records")
    assert "records.faq.edit" in records["permissions"]


async def test_source_permission_enforced_by_requires_permission(app: FastAPI):
    from simple_module_hosting.permissions import resolved_permissions_for
    from starlette.requests import Request

    registry = app.state.sm.permissions
    registry.add_source("records", lambda: ["records.product.edit"])
    registry.map_role("editor", ["records.product.edit"])

    scope = {"type": "http", "app": app, "headers": [], "state": {}}
    request = Request(scope)
    request.state.user = type("U", (), {"roles": ["editor"]})()
    assert "records.product.edit" in resolved_permissions_for(request)

    # Admin's implicit grant covers source permissions.
    assert "records.product.edit" in registry.get_permissions_for_roles(["admin"])


async def test_saving_role_keeps_grants_of_currently_unregistered_source_keys(
    authenticated_client: httpx.AsyncClient, app: FastAPI
):
    from permissions.service import PermissionService
    from users.constants import USER_ROLE_ID, USER_ROLE_NAME
    from users.models import Role

    registry = app.state.sm.permissions
    registry.add_source("records", lambda: ["records.product.edit"])
    async with app.state.sm.db.session_factory() as db:
        if await db.get(Role, USER_ROLE_ID) is None:
            db.add(Role(id=USER_ROLE_ID, name=USER_ROLE_NAME, description="Standard user"))
            await db.commit()
    url = f"/api/permissions/roles/{USER_ROLE_ID}"
    await authenticated_client.put(url, json={"permissions": ["records.product.edit"]})

    # The source goes empty (e.g. restart before its cache warms); an unrelated save
    # must not prune the stored grant.
    registry.add_source("records", lambda: [])
    await authenticated_client.put(url, json={"permissions": []})

    async with app.state.sm.db.session_factory() as db:
        keys = await PermissionService(db, registry)._get_role_keys(USER_ROLE_NAME)
    assert keys == ["records.product.edit"]
