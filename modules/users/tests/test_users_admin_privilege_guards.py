"""Delegated user management must not grant access to stronger accounts (#624)."""

import httpx
import pytest
from fastapi import FastAPI
from simple_module_test import forge_session_cookie
from sqlalchemy import select
from test_api_admin import _make_user
from test_service_admin import _build_service
from users.errors import install_exception_handlers
from users.exceptions import AdminAccountSafetyError, AdminPermissionError
from users.models import Role, User, UserRole

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    "error, status", [(AdminPermissionError, 403), (AdminAccountSafetyError, 400)]
)
async def test_admin_guard_http_status(error, status):
    app = FastAPI()
    install_exception_handlers(app)

    @app.post("/guarded")
    async def guarded():
        raise error("Refused")

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.post("/guarded")
    assert response.status_code == status
    assert response.json() == {"detail": "Refused"}


@pytest.fixture
async def delegated_client(users_app, users_db):
    users_db.add(Role(name="manager"))
    users_db.add(Role(name="powerful"))
    await users_db.commit()
    users_app.state.sm.permissions.map_role("manager", ["users.manage"])
    users_app.state.sm.permissions.map_role("powerful", ["files.delete"])
    actor = await _make_user(users_db, "manager@example.com", role_names=["manager", "user"])
    cookie = forge_session_cookie(
        str(users_app.state.sm.settings.secret_key), {"user_id": str(actor.id)}
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=users_app),
        base_url="http://testserver",
        cookies={"session": cookie},
    ) as client:
        yield client, actor.id


@pytest.mark.parametrize("role", ["admin", "powerful"])
@pytest.mark.parametrize("operation", ["roles", "create", "invite", "bulk"])
async def test_delegate_cannot_grant_unheld_role(delegated_client, users_db, operation, role):
    client, actor_id = delegated_client
    data = {"role_names": [role]}
    if operation == "roles":
        response = await client.put(f"/api/users/admin/{actor_id}/roles", json=data)
    else:
        data.update(email="escalated@example.com", password="SecurePass1!")
        path = {"create": "", "invite": "/invite", "bulk": "/invite/bulk"}[operation]
        if operation == "bulk":
            data["emails"] = [data.pop("email")]
        response = await client.post(f"/api/users/admin{path}", json=data)
    assert response.status_code == 403
    assert (
        await users_db.execute(select(User).where(User.email == "escalated@example.com"))
    ).scalar_one_or_none() is None
    roles = (
        (
            await users_db.execute(
                select(Role.name).join(UserRole).where(UserRole.user_id == actor_id)
            )
        )
        .scalars()
        .all()
    )
    assert set(roles) == {"manager", "user"}


@pytest.mark.parametrize("kind", ["admin", "superuser", "powerful"])
@pytest.mark.parametrize("operation", ["reset", "roles", "disable", "email", "delete"])
async def test_delegate_cannot_control_privileged_target(
    delegated_client, users_db, kind, operation
):
    client, _ = delegated_client
    target = await _make_user(
        users_db, "protected@example.com", role_names=[] if kind == "superuser" else [kind]
    )
    if kind == "superuser":
        target.is_superuser = True
        await users_db.commit()
    url = f"/api/users/admin/{target.id}"
    if operation == "reset":
        response = await client.post(f"{url}/reset-password-link")
    elif operation == "roles":
        response = await client.put(f"{url}/roles", json={"role_names": ["user"]})
    elif operation == "disable":
        response = await client.patch(f"{url}/disable")
    elif operation == "email":
        response = await client.patch(url, json={"email": "stolen@example.com"})
    else:
        response = await client.delete(url)
    assert response.status_code == 403
    await users_db.refresh(target)
    assert target.email == "protected@example.com"
    assert target.is_active is True


async def test_delegate_can_manage_ordinary_user(delegated_client, users_db):
    client, _ = delegated_client
    target = await _make_user(users_db, "ordinary@example.com", role_names=["user"])
    url = f"/api/users/admin/{target.id}"
    response = await client.put(f"{url}/roles", json={"role_names": ["user"]})
    assert response.status_code == 200
    response = await client.post(f"{url}/reset-password-link")
    assert response.status_code == 200
    assert "token=" in response.json()["link"]
    response = await client.patch(f"{url}/disable")
    assert response.status_code == 200


@pytest.mark.parametrize("operation", ["disable", "roles"])
async def test_admin_cannot_disable_or_demote_self(admin_client, users_db, operation):
    admin = (
        await users_db.execute(select(User).where(User.email == "admin@example.com"))
    ).scalar_one()
    # Self-protection also applies when another administrator exists.
    await _make_user(users_db, "other-admin@example.com", role_names=["admin"])
    url = f"/api/users/admin/{admin.id}/{operation}"
    if operation == "roles":
        response = await admin_client.put(url, json={"role_names": ["user"]})
    else:
        response = await admin_client.patch(url)
    assert response.status_code == 400
    await users_db.refresh(admin)
    assert admin.is_active is True
    assert (
        await users_db.execute(select(Role.name).join(UserRole).where(UserRole.user_id == admin.id))
    ).scalars().all() == ["admin"]


@pytest.mark.parametrize("operation", ["disable", "roles", "delete"])
async def test_service_preserves_last_active_admin(users_app, users_db, operation):
    admin = (
        await users_db.execute(select(User).where(User.email == "admin@example.com"))
    ).scalar_one()
    inactive = await _make_user(users_db, "inactive-admin@example.com", role_names=["admin"])
    inactive.is_active = False
    await users_db.commit()
    # The legacy superuser flag alone grants no framework admin permissions.
    roleless = await _make_user(users_db, "roleless-superuser@example.com")
    roleless.is_superuser = True
    await users_db.commit()
    service = _build_service(users_db, users_app)
    with pytest.raises(AdminAccountSafetyError):
        if operation == "roles":
            await service.set_roles(admin.id, ["user"])
        elif operation == "delete":
            await service.delete_user(admin.id)
        else:
            await service.disable(admin.id)
    await users_db.refresh(admin)
    assert admin.is_active is True
