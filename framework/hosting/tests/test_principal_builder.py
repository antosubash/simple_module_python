"""HTTP and headless callers use one builder, including credential restrictions."""

from contextlib import asynccontextmanager
from types import SimpleNamespace

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
        yield SimpleNamespace(info=self.kw["info"])


def request_for(registry, tenant="own", **credential):
    app = SimpleNamespace(
        state=SimpleNamespace(
            sm=SimpleNamespace(db=SimpleNamespace(session_factory=Factory(registry)))
        )
    )
    user = SimpleNamespace(id="u1", roles=["admin"], **credential)
    return Request(
        {"type": "http", "app": app, "headers": [], "state": {"user": user, "tenant_id": tenant}}
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
        raise AssertionError("the session counterpart must be shared by both paths")

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


async def test_inactive_user_and_nonmember_are_not_resource_principals():
    registry = registry_for()
    registry.directory.active = False
    request = request_for(registry)
    assert await resolve_request_permissions(request, registry.permissions) == set()
    assert request.state.user is None
    assert await resource_principal(request) == ResourcePrincipal(None)
    registry.directory.active = True
    request = request_for(registry, tenant="other")
    assert await resolve_request_permissions(request, registry.permissions) == set()
    assert await resource_principal(request) == ResourcePrincipal(None)


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
    assert await resource_principal(request) == ResourcePrincipal(None)
