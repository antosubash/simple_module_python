"""Delegated management compares effective permissions (#624): direct grants and token scopes."""

import httpx
import pytest
from api_tokens.constants import TokenKind
from api_tokens.service import ApiTokenService
from simple_module_test import forge_session_cookie
from sqlalchemy import select
from test_api_admin import _make_user
from users.models import Role, User

pytestmark = pytest.mark.anyio


async def _client(app, headers=None, cookies=None):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        headers=headers,
        cookies=cookies,
    )


async def test_delegate_cannot_manage_user_with_unheld_direct_grant(users_app, users_db):
    users_db.add(Role(name="manager"))
    await users_db.commit()
    users_app.state.sm.permissions.map_role("manager", ["users.manage"])
    actor = await _make_user(users_db, "manager@example.com", role_names=["manager", "user"])
    target = await _make_user(users_db, "granted@example.com", role_names=["user"])
    ordinary = await _make_user(users_db, "plain@example.com", role_names=["user"])

    async def direct_grants(request, user):
        return {"files.delete"} if user.id == str(target.id) else set()

    users_app.state.sm.permissions.add_grant_source(direct_grants)
    cookie = forge_session_cookie(
        str(users_app.state.sm.settings.secret_key), {"user_id": str(actor.id)}
    )
    async with await _client(users_app, cookies={"session": cookie}) as client:
        denied = await client.patch(f"/api/users/admin/{target.id}/disable")
        allowed = await client.patch(f"/api/users/admin/{ordinary.id}/disable")
    assert denied.status_code == 403
    assert allowed.status_code == 200
    await users_db.refresh(target)
    assert target.is_active is True


async def test_admin_pat_cannot_grant_role_beyond_its_scopes(users_app, users_db):
    users_db.add(Role(name="deleter"))
    await users_db.commit()
    users_app.state.sm.permissions.map_role("deleter", ["files.delete"])
    admin = (
        await users_db.execute(select(User).where(User.email == "admin@example.com"))
    ).scalar_one()
    target = await _make_user(users_db, "target@example.com", role_names=[])
    _, pat = await ApiTokenService(users_db).create(
        kind=TokenKind.PERSONAL,
        name="scoped admin",
        scopes=["users.manage", "api_tokens.use"],
        expires_in_days=1,
        max_lifetime_days=30,
        owner_user_id=admin.id,
    )
    await users_db.commit()
    async with await _client(users_app, headers={"Authorization": f"Bearer {pat}"}) as client:
        url = f"/api/users/admin/{target.id}/roles"
        beyond = await client.put(url, json={"role_names": ["deleter"]})
        assert beyond.status_code == 403
        within = await client.put(url, json={"role_names": []})
        assert within.status_code == 200
