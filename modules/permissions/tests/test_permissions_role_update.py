"""Regression tests for role permission update payloads."""

from __future__ import annotations

import httpx
from fastapi import FastAPI
from permissions.constants import PERM_VIEW


class TestRolePermissionsAPI:
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
