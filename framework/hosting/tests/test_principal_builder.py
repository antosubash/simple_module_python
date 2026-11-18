"""Cached HTTP and session loaders share principal composition and credential caps."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from simple_module_core.principals import PRINCIPALS_KEY, PrincipalRegistry
from simple_module_core.resources import ResourcePrincipal
from simple_module_core.user_directory import DirectoryUser, NullUserDirectory
from simple_module_db.principals import principal_for
from simple_module_hosting.permissions import resolve_request_permissions
from simple_module_hosting.resource_deps import resource_principal
from starlette.requests import Request


class Directory(NullUserDirectory):
    def __init__(self, active=True):
        self.active = active

    async def get_many(self, db, ids, *, with_roles=False):
        return {
            "u1": DirectoryUser("u1", "a@example.com", is_active=self.active, roles=("reader",))
        }


class Factory:
    def __init__(self, registry):
        self.kw = {"info": {PRINCIPALS_KEY: registry}}

    @asynccontextmanager
    async def __call__(self):
        yield SimpleNamespace(info=self.kw["info"], flush=AsyncMock())


def request_for(registry, tenant="own", **credential):
    app = SimpleNamespace(
        state=SimpleNamespace(
            sm=SimpleNamespace(db=SimpleNamespace(session_factory=Factory(registry)))
        )
    )
    roles = ["reader"]
    if registry.multi_tenant and tenant == "own":
        roles.append("tenant:member")
    user = SimpleNamespace(id="u1", roles=roles, tenant_id=None, **credential)
    return Request(
        {
            "type": "http",
            "app": app,
            "headers": [],
            "state": {
                "user": user,
                "tenant_id": tenant,
                "tenant_role": "member" if registry.multi_tenant and tenant == "own" else None,
            },
        }
    )


def registry_for(*, multi=True):
    registry = PrincipalRegistry(directory=Directory(), multi_tenant=multi)
    registry.permissions.map_role("reader", ["test.role"])
    registry.permissions.map_role("tenant:member", ["test.member"])

    async def membership(db, uid, tenant):
        return "member" if tenant == "own" else None

    async def direct(db, user):
        return ["test.direct"]

    async def legacy(request, user):
        return ["test.direct"]

    registry.membership_role = membership
    registry.permissions.add_grant_source(legacy, session_source=direct)
    return registry


@pytest.mark.parametrize("multi", [False, True])
async def test_request_and_headless_principals_are_identical(multi):
    registry = registry_for(multi=multi)
    request = request_for(registry)
    permissions = await resolve_request_permissions(request, registry.permissions)
    from_request = await resource_principal(request)
    assert from_request is request.state.resource_principal
    async with request.app.state.sm.db.session_factory() as db:
        from_worker = await principal_for(db, "u1", "own")
    assert from_request == from_worker
    assert permissions == from_worker.permissions
    assert from_worker.permissions == {"test.role", "test.direct"} | (
        {"test.member"} if multi else set()
    )


async def test_request_scopes_and_required_permission_remain_enforced():
    registry = registry_for()
    request = request_for(registry, scopes=["test.direct"])
    assert await resolve_request_permissions(request, registry.permissions) == {"test.direct"}
    assert (await resource_principal(request)).permissions == {"test.direct"}
    request = request_for(registry, required_permission="test.revoked")
    assert await resolve_request_permissions(request, registry.permissions) == set()
    assert request.state.user is None


async def test_platform_permissions_do_not_create_an_unscoped_resource_principal():
    registry = registry_for()
    request = request_for(registry, tenant=None)
    assert await resolve_request_permissions(request, registry.permissions) == {
        "test.role",
        "test.direct",
    }
    assert request.state.user.id == "u1"
    assert await resource_principal(request) == ResourcePrincipal(None)


@pytest.mark.parametrize("auth_kind", ["session", "bearer", "pat", "service"])
@pytest.mark.parametrize("cached", [False, True])
async def test_bound_tenant_without_membership_only_identifies_service_credentials(
    auth_kind, cached
):
    registry = registry_for()
    request = request_for(registry, tenant="public", auth_kind=auth_kind)
    assert await resolve_request_permissions(request, registry.permissions) == {
        "test.role",
        "test.direct",
    }
    assert request.state.user.id == "u1"
    expected = (
        ResourcePrincipal("u1", frozenset({"test.role", "test.direct"}))
        if auth_kind == "service"
        else ResourcePrincipal(None)
    )
    assert request.state.resource_principal == expected
    if not cached:
        del request.state.resource_principal
    assert await resource_principal(request) == expected


@pytest.mark.parametrize("cached", [False, True])
@pytest.mark.parametrize("tenant", [None, "public"])
@pytest.mark.parametrize("scopes", [None, ["test.direct", "*"]])
async def test_nonmember_admin_bypass_requires_a_bound_tenant_and_uncapped_wildcard(
    cached, tenant, scopes
):
    registry = registry_for()
    request = request_for(registry, tenant=tenant, scopes=scopes)
    request.state.user.roles = ["admin"]
    permissions = {"*"} if scopes is None else {"test.direct"}
    assert await resolve_request_permissions(request, registry.permissions) == permissions
    expected = (
        ResourcePrincipal("u1", frozenset({"*"}))
        if tenant is not None and scopes is None
        else ResourcePrincipal(None)
    )
    assert request.state.resource_principal == expected
    if not cached:
        del request.state.resource_principal
    assert await resource_principal(request) == expected


async def test_fixed_tenant_grant_sources_receive_effective_tenant_without_mutating_user():
    registry = registry_for(multi=False)
    registry.default_tenant = "single"

    async def request_grants(request, user):
        return ["test.single"] if user.tenant_id == "single" else []

    async def session_grants(db, user):
        return ["test.single"] if user.tenant_id == "single" else []

    registry.permissions.add_grant_source(request_grants, session_source=session_grants)
    request = request_for(registry, tenant="single")
    permissions = await resolve_request_permissions(request, registry.permissions)
    assert "test.single" in permissions
    async with request.app.state.sm.db.session_factory() as db:
        worker = await principal_for(db, "u1", "single")
    assert await resource_principal(request) == worker
    assert request.state.user.tenant_id is None
