"""Saving a role in the editor keeps code-registered grants effective (#396)."""

from __future__ import annotations

import httpx
from fastapi import FastAPI
from permissions.constants import PERM_VIEW
from simple_module_core.permissions import PermissionRegistry


def test_overlay_replace_keeps_code_mapping_and_drops_removed_db_keys():
    reg = PermissionRegistry()
    reg.map_role("user", ["a.code"])
    reg.set_role_overlay("user", ["a.db", "b.db"])
    assert set(reg.role_map["user"]) == {"a.code", "a.db", "b.db"}
    reg.set_role_overlay("user", ["b.db"])
    assert set(reg.role_map["user"]) == {"a.code", "b.db"}
    reg.set_role_overlay("user", [])
    assert set(reg.role_map["user"]) == {"a.code"}


async def test_saving_a_role_keeps_its_code_mapped_grants(
    authenticated_client: httpx.AsyncClient, app: FastAPI
):
    from users.constants import USER_ROLE_ID, USER_ROLE_NAME
    from users.models import Role

    registry = app.state.sm.permissions
    registry.add("zz_demo.code_granted")
    registry.map_role(USER_ROLE_NAME, ["zz_demo.code_granted"])
    async with app.state.sm.db.session_factory() as db:
        if await db.get(Role, USER_ROLE_ID) is None:
            db.add(Role(id=USER_ROLE_ID, name=USER_ROLE_NAME, description="Standard user"))
            await db.commit()

    for keys in ([PERM_VIEW], []):
        resp = await authenticated_client.put(
            f"/api/permissions/roles/{USER_ROLE_ID}", json={"permissions": keys}
        )
        assert resp.status_code == 200
        granted = set(registry.role_map[USER_ROLE_NAME])
        assert "zz_demo.code_granted" in granted
        assert (PERM_VIEW in granted) == bool(keys)
