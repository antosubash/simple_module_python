"""Delegated permission writes cannot escalate access (#687)."""

import uuid
from types import SimpleNamespace

import httpx
import pytest
from auth.contracts.schemas import UserContext
from fastapi import FastAPI, Request
from permissions.deps import get_permission_service
from permissions.endpoints.api import router as api_router
from permissions.endpoints.views import router as view_router
from permissions.models import RolePermission, UserPermission
from simple_module_core.permissions import PermissionRegistry
from simple_module_core.user_directory import DirectoryUser, NullUserDirectory
from sqlalchemy import select
from starlette.middleware.sessions import SessionMiddleware
from users.models import Role


class _Directory(NullUserDirectory):
    def __init__(self, users):
        self.users = {user.id: user for user in users}

    async def get_many(self, db, ids, *, with_roles=False):
        return {key: self.users[key] for key in ids if key in self.users}


@pytest.fixture
async def writes(db_session):
    actor = UserContext(id=str(uuid.uuid4()), email="manager@test", name="Manager")
    target = DirectoryUser(id=str(uuid.uuid4()), email="target@test", roles=())
    directory = _Directory([DirectoryUser(id=actor.id, email=actor.email, roles=()), target])
    registry = PermissionRegistry()
    registry.add_group("Test", ["permissions.manage", "test.held", "test.unheld"])
    registry.map_role("admin", ["*"])
    actor.permissions = ["permissions.manage", "test.held"]
    role = Role(id=uuid.uuid4(), name="user")
    db_session.add(role)
    await db_session.flush()

    async def direct_grants(request, user):
        result = await db_session.execute(
            select(UserPermission.permission_key).where(
                UserPermission.user_id == uuid.UUID(user.id)
            )
        )
        return set(result.scalars())

    registry.add_grant_source(direct_grants)
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-only")
    app.state.sm = SimpleNamespace(permissions=registry)
    app.state.user_directory = directory

    @app.middleware("http")
    async def authenticate(request, call_next):
        request.state.user = actor
        return await call_next(request)

    # Keep the real dependency's request binding, directory, and safety context.
    async def service(request: Request):
        return await get_permission_service(request, db_session, registry)

    app.dependency_overrides[get_permission_service] = service
    app.include_router(api_router, prefix="/api/permissions")
    app.include_router(view_router, prefix="/admin/permissions")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        yield SimpleNamespace(
            client=client,
            actor=actor,
            target=target,
            directory=directory,
            role=role,
            registry=registry,
            db=db_session,
        )


@pytest.mark.parametrize("prefix", ["/api/permissions", "/admin/permissions"])
@pytest.mark.parametrize("kind", ["roles", "users"])
@pytest.mark.parametrize("key, allowed", [("test.unheld", False), ("test.held", True)])
async def test_added_grants_must_be_held(writes, prefix, kind, key, allowed):
    target_id = writes.role.id if kind == "roles" else writes.actor.id
    response = await writes.client.put(f"{prefix}/{kind}/{target_id}", json={"permissions": [key]})
    api = prefix.startswith("/api")
    if allowed:
        assert response.status_code == (200 if api else 303)
    elif api:
        assert response.status_code == 403
        assert response.json()["detail"]
    else:
        # The edit page gets the reason back as a form error, not an error page.
        assert response.status_code in (302, 303)
    model = RolePermission if kind == "roles" else UserPermission
    rows = (await writes.db.execute(select(model.permission_key))).scalars().all()
    assert rows == ([key] if allowed else [])


@pytest.mark.parametrize("privilege", ["admin", "role", "direct", "source", "unknown"])
async def test_cannot_edit_more_privileged_user(writes, privilege):
    roles = ()
    if privilege in {"admin", "role"}:
        roles = ("admin" if privilege == "admin" else "powerful",)
        writes.registry.map_role("powerful", ["test.unheld"])
    elif privilege == "direct":
        writes.db.add(
            UserPermission(user_id=uuid.UUID(writes.target.id), permission_key="test.unheld")
        )
        await writes.db.flush()
    elif privilege == "unknown":
        roles = None
    else:

        async def extra_source(request, user):
            return {"test.unheld"} if user.id == writes.target.id else set()

        writes.registry.add_grant_source(extra_source)
    writes.directory.users[writes.target.id] = DirectoryUser(
        id=writes.target.id, email=writes.target.email, roles=roles
    )
    response = await writes.client.put(
        f"/api/permissions/users/{writes.target.id}", json={"permissions": []}
    )
    assert response.status_code == 403
    assert response.json()["detail"]


@pytest.mark.parametrize("kind", ["roles", "users"])
async def test_scoped_admin_cannot_grant_outside_scope(writes, kind):
    writes.actor.roles = ["admin"]
    writes.actor.scopes = ["permissions.manage"]
    target_id = writes.role.id if kind == "roles" else writes.target.id
    response = await writes.client.put(
        f"/api/permissions/{kind}/{target_id}", json={"permissions": ["test.unheld"]}
    )
    assert response.status_code == 403


@pytest.mark.parametrize("kind", ["roles", "users"])
async def test_unscoped_admin_can_grant_any_registered_key(writes, kind):
    writes.actor.roles = ["admin"]
    target_id = writes.role.id if kind == "roles" else writes.target.id
    response = await writes.client.put(
        f"/api/permissions/{kind}/{target_id}", json={"permissions": ["test.unheld"]}
    )
    assert response.status_code == 200


async def test_actor_direct_grant_can_be_delegated(writes):
    writes.actor.permissions = ["permissions.manage"]
    writes.db.add(UserPermission(user_id=uuid.UUID(writes.actor.id), permission_key="test.held"))
    await writes.db.flush()
    response = await writes.client.put(
        f"/api/permissions/users/{writes.target.id}", json={"permissions": ["test.held"]}
    )
    assert response.status_code == 200


@pytest.mark.parametrize("kept", [["test.unheld", "test.held"], ["test.held"]])
async def test_cannot_edit_role_holding_unheld_grant(writes, kept):
    """Retaining or stripping a key the actor lacks are both refused."""
    writes.db.add(RolePermission(role_name="user", permission_key="test.unheld"))
    await writes.db.flush()
    response = await writes.client.put(
        f"/api/permissions/roles/{writes.role.id}", json={"permissions": kept}
    )
    assert response.status_code == 403
    keys = await writes.db.execute(
        select(RolePermission.permission_key).where(RolePermission.role_name == "user")
    )
    assert set(keys.scalars()) == {"test.unheld"}


async def test_cannot_edit_admin_role(writes):
    admin = Role(id=uuid.uuid4(), name="admin")
    writes.db.add(admin)
    await writes.db.flush()
    response = await writes.client.put(
        f"/api/permissions/roles/{admin.id}", json={"permissions": ["test.held"]}
    )
    assert response.status_code == 403
