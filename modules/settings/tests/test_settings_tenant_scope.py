"""Settings scopes on a multi-tenant host (GH #368).

The routes used to check ``settings.*`` only, so anyone holding them could
write the host-wide system scope and any tenant's or user's scope by naming it
in the URL. Now the system scope, the cross-scope admin tooling and every
scope other than the caller's own need a *platform* settings admin.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager

import httpx
import pytest
from settings.constants import ALL_PERMISSIONS, API_PREFIX, PERM_SYSTEM
from simple_module_test.session_cookie import forge_session_cookie
from sqlalchemy import select
from tenants.resolver import forget

_SETTINGS_PERMS = ["settings.view", "settings.create", "settings.edit", "settings.delete"]


def _url(path: str = "") -> str:
    return f"{API_PREFIX}/{path.lstrip('/')}" if path else f"{API_PREFIX}/"


@pytest.fixture(autouse=True)
def _fresh_membership_cache():
    forget(None)
    yield
    forget(None)


@pytest.fixture
def client_for(app) -> Callable:
    """``async with client_for("a@x.io", role="admin") as (c, uid)``."""

    @asynccontextmanager
    async def factory(
        email: str, *, role: str = "user"
    ) -> AsyncGenerator[tuple[httpx.AsyncClient, str], None]:
        from users.models import Role, User, UserRole

        async with app.state.sm.db.session_factory() as session:
            user = User(
                id=uuid.uuid4(),
                email=email,
                hashed_password="x",
                is_active=True,
                is_verified=True,
            )
            session.add(user)
            await session.flush()
            row = (
                await session.execute(select(Role).where(Role.name == role))
            ).scalar_one_or_none()
            if row is not None:  # only ``admin`` is seeded; a plain user needs no row
                session.add(UserRole(user_id=user.id, role_id=row.id))
            await session.commit()
            user_id = str(user.id)

        cookie = forge_session_cookie(app.state.sm.settings.secret_key, {"user_id": user_id})
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            cookies={"session": cookie},
        ) as client:
            yield client, user_id

    return factory


def test_system_permission_is_registered(app):
    assert PERM_SYSTEM in ALL_PERMISSIONS
    assert PERM_SYSTEM in app.state.sm.permissions.all_permissions


# Tenant roles now come from memberships, not the removed User.tenant_id column.


@pytest.fixture
def owners_edit_settings(app):
    """An org owner with the older scoped settings permissions as well as self-service."""
    app.state.sm.permissions.map_role("tenant:owner", _SETTINGS_PERMS)
    return app


async def _org(client: httpx.AsyncClient, name: str) -> str:
    resp = await client.post("/api/tenants/", json={"name": name})
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


async def test_tenant_owner_cannot_write_the_system_scope(owners_edit_settings, client_for):
    async with client_for("acme-admin@x.io") as (c, _):
        await _org(c, "Acme")
        resp = await c.put(_url("system/records.flag"), json={"value": "true"})
        assert resp.status_code == 403, resp.text
        assert PERM_SYSTEM in resp.json()["detail"]
        assert (await c.get(_url("system/records.flag"))).status_code == 403
        assert (await c.delete(_url("system/records.flag"))).status_code == 403


async def test_tenant_owner_cannot_write_another_tenant(owners_edit_settings, client_for):
    async with client_for("acme-admin@x.io") as (c, _), client_for("globex@x.io") as (other, _):
        await _org(c, "Acme")
        globex = await _org(other, "Globex")
        assert (await c.put(_url(f"tenant/{globex}/k"), json={"value": "x"})).status_code == 403
        assert (await c.get(_url(f"tenant/{globex}/k"))).status_code == 403
        assert (await c.delete(_url(f"tenant/{globex}/k"))).status_code == 403


async def test_tenant_owner_manages_its_own_tenant(owners_edit_settings, client_for):
    async with client_for("acme-admin@x.io") as (c, _):
        acme = await _org(c, "Acme")
        assert (await c.put(_url(f"tenant/{acme}/k"), json={"value": "x"})).status_code == 200
        assert (await c.get(_url(f"tenant/{acme}/k"))).json()["value"] == "x"
        listed = await c.get(_url(), params={"scope": "tenant", "scope_id": acme})
        assert [r["scope_id"] for r in listed.json()] == [acme]
        assert (await c.delete(_url(f"tenant/{acme}/k"))).status_code == 204


async def test_user_scope_is_limited_to_the_caller(owners_edit_settings, client_for):
    async with client_for("acme-admin@x.io") as (c, uid):
        await _org(c, "Acme")
        assert (await c.put(_url(f"user/{uid}/k"), json={"value": "me"})).status_code == 200
        other = str(uuid.uuid4())
        assert (await c.put(_url(f"user/{other}/k"), json={"value": "x"})).status_code == 403
        assert (await c.get(_url(f"user/{other}/k"))).status_code == 403


async def test_resolve_only_for_own_tenant_and_user(owners_edit_settings, client_for):
    async with client_for("acme-admin@x.io") as (c, uid), client_for("globex@x.io") as (b, _):
        acme = await _org(c, "Acme")
        globex = await _org(b, "Globex")
        await c.put(_url(f"tenant/{acme}/k"), json={"value": "ten"})
        own = await c.get(_url("resolve/k"), params={"tenant_id": acme, "user_id": uid})
        assert own.json()["value"] == "ten"
        other = await c.get(_url("resolve/k"), params={"tenant_id": globex})
        assert other.status_code == 403


@pytest.mark.parametrize(
    ("method", "path", "params"),
    [
        ("GET", "", None),
        ("GET", "", {"scope": "system"}),
        ("GET", "", {"scope": "tenant", "scope_id": "globex"}),
        ("POST", "", None),
        ("GET", "1", None),
        ("PUT", "1", None),
        ("DELETE", "1", None),
        ("GET", "modules", None),
    ],
)
async def test_cross_scope_tooling_is_platform_only(
    owners_edit_settings, client_for, method, path, params
):
    body = {"key": "k", "value": "x"} if method in ("POST", "PUT") else None
    async with client_for("acme-admin@x.io") as (c, _):
        await _org(c, "Acme")
        resp = await c.request(method, _url(path), params=params, json=body)
        assert resp.status_code == 403, resp.text


@pytest.mark.parametrize("path", ["/admin/settings/", "/admin/settings/store"])
async def test_settings_screens_are_platform_only(owners_edit_settings, client_for, path):
    async with client_for("acme-admin@x.io") as (c, _):
        await _org(c, "Acme")
        assert (await c.get(path, follow_redirects=False)).status_code == 403


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/admin/settings/store"),
        ("PUT", "/admin/settings/1"),
        ("DELETE", "/admin/settings/1"),
        ("POST", "/admin/settings/test-connection/settings"),
        ("PUT", "/api/settings/modules/settings"),
        ("DELETE", "/api/settings/modules/settings/some_field"),
    ],
)
async def test_settings_writes_outside_the_scoped_api_are_platform_only(
    owners_edit_settings, client_for, method, path
):
    """The screens' actions and the module-settings API write the system scope."""
    async with client_for("acme-admin@x.io") as (c, _):
        await _org(c, "Acme")
        body = {"key": "k", "value": "x", "scope": "system"} if method != "DELETE" else None
        resp = await c.request(method, path, json=body, follow_redirects=False)
        assert resp.status_code == 403, resp.text
        assert PERM_SYSTEM in resp.text


async def test_platform_admin_keeps_every_scope(authenticated_client):
    c = authenticated_client
    globex = await _org(c, "Globex")
    assert (await c.put(_url("system/k"), json={"value": "s"})).status_code == 200
    assert (await c.put(_url(f"tenant/{globex}/k"), json={"value": "t"})).status_code == 200
    assert (await c.put(_url(f"user/{uuid.uuid4()}/k"), json={"value": "u"})).status_code == 200
    assert (await c.get(_url())).status_code == 200
    assert (await c.get("/admin/settings/", follow_redirects=False)).status_code == 200


async def test_single_tenant_host_is_unchanged(app, client_for):
    app.state.sm.settings.multi_tenant = False
    async with client_for("acme-admin@x.io", role="admin") as (c, _):
        globex = await _org(c, "Globex")
        assert (await c.put(_url("system/k"), json={"value": "s"})).status_code == 200
        assert (await c.put(_url(f"tenant/{globex}/k"), json={"value": "t"})).status_code == 200


# ── tenants module: membership roles mapped onto settings permissions ──


async def test_org_owner_is_confined_to_its_org(owners_edit_settings, client_for):
    async with client_for("a@x.io") as (a, _), client_for("b@x.io") as (b, _):
        alpha = await _org(a, "Alpha")
        beta = await _org(b, "Beta")
        assert (await a.put(_url(f"tenant/{alpha}/k"), json={"value": "a"})).status_code == 200
        assert (await a.put(_url(f"tenant/{beta}/k"), json={"value": "x"})).status_code == 403
        assert (await a.put(_url("system/k"), json={"value": "x"})).status_code == 403
        assert (await a.get(_url("resolve/k"), params={"tenant_id": beta})).status_code == 403


async def test_platform_admin_inside_an_org_stays_platform(owners_edit_settings, client_for):
    """With the resolver, ``admin`` is a platform role even while in an org."""
    async with client_for("root@x.io", role="admin") as (c, _):
        await _org(c, "Mine")
        assert (await c.put(_url("system/k"), json={"value": "s"})).status_code == 200
        async with client_for("elsewhere@x.io") as (other, _):
            elsewhere = await _org(other, "Elsewhere")
        assert (await c.put(_url(f"tenant/{elsewhere}/k"), json={"value": "t"})).status_code == 200
