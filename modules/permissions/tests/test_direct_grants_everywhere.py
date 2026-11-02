"""A direct grant opens routes guarded by the framework's RequiresPermission (GH #337).

The reproduction from the issue: a user with no roles is granted a module's
``view`` permission on the permissions screen. Before the fix the grant was
stored and returned 200, and the user still got 403 on every route of a module
that imported ``simple_module_hosting.permissions.RequiresPermission``.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from fastapi import FastAPI
from feature_flags.constants import PERM_FEATURE_FLAGS_VIEW, VIEW_PREFIX
from permissions.deps import RequiresPermission as ModuleRequiresPermission
from permissions.grants import clear_grants_cache
from simple_module_hosting.permissions import RequiresPermission
from simple_module_test import forge_session_cookie

_GUARDED = "/api/feature_flags/"


@pytest.fixture(autouse=True)
def _cold_cache():
    clear_grants_cache()
    yield
    clear_grants_cache()


async def _seed_roleless_user(app: FastAPI) -> uuid.UUID:
    from users.models import User

    user_id = uuid.uuid4()
    async with app.state.sm.db.session_factory() as db:
        db.add(
            User(
                id=user_id,
                email=f"{user_id.hex[:8]}@test",
                hashed_password="x",
                is_active=True,
                is_superuser=False,
                is_verified=True,
            )
        )
        await db.commit()
    return user_id


def _client_for(app: FastAPI, user_id: uuid.UUID) -> httpx.AsyncClient:
    cookie = forge_session_cookie(app.state.sm.settings.secret_key, {"user_id": str(user_id)})
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        cookies={"session": cookie},
    )


def test_module_class_is_the_framework_class():
    assert ModuleRequiresPermission is RequiresPermission


async def test_grant_and_revoke_take_effect_on_framework_guarded_route(
    app: FastAPI, authenticated_client: httpx.AsyncClient
):
    user_id = await _seed_roleless_user(app)
    async with _client_for(app, user_id) as user:
        # Also warms the cache with "no grants" — the grant below must evict it.
        assert (await user.get(_GUARDED)).status_code == 403

        granted = await authenticated_client.put(
            f"/api/permissions/users/{user_id}", json={"permissions": [PERM_FEATURE_FLAGS_VIEW]}
        )
        assert granted.status_code == 200
        assert (await user.get(_GUARDED)).status_code == 200

        revoked = await authenticated_client.put(
            f"/api/permissions/users/{user_id}", json={"permissions": []}
        )
        assert revoked.status_code == 200
        assert (await user.get(_GUARDED)).status_code == 403


async def test_grant_reaches_inertia_auth_permissions(
    app: FastAPI, authenticated_client: httpx.AsyncClient
):
    user_id = await _seed_roleless_user(app)
    await authenticated_client.put(
        f"/api/permissions/users/{user_id}", json={"permissions": [PERM_FEATURE_FLAGS_VIEW]}
    )
    async with _client_for(app, user_id) as user:
        resp = await user.get(f"{VIEW_PREFIX}/", headers={"X-Inertia": "true"})
    assert resp.status_code == 200
    assert PERM_FEATURE_FLAGS_VIEW in resp.json()["props"]["auth"]["permissions"]
