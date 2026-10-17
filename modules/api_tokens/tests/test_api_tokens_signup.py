"""A self-registered user can reach their tokens page on a fresh install (GH #488).

``api_tokens.use`` is mapped onto the standard ``user`` role and onto tenant
roles. A fresh install is single-tenant, so there is no membership to fall
back on: signups only get the permission if registration attaches the role.
Hence ``multi_tenant`` off here — with it on, the tenant role hides the bug.
"""

from __future__ import annotations

import pytest
from _api_tokens_support import INERTIA_HEADERS
from simple_module_hosting.settings import Settings
from simple_module_test.tenant_client import session_client
from sqlalchemy import select


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"multi_tenant": False, "tenant_header": ""})


EMAIL = "signup@example.com"


async def _register(app, client) -> str:
    from users.bootstrap import ensure_user_role
    from users.models import User

    # Test schemas come from ``create_all``: seed the role the migration would.
    async with app.state.sm.db.session_factory() as session:
        await ensure_user_role(session)
        await session.commit()
    users = app.state.users
    users.settings = users.settings.model_copy(update={"allow_signup": True})
    resp = await client.post(
        "/api/users/auth/register", json={"email": EMAIL, "password": "SecurePass1!"}
    )
    assert resp.status_code == 201, resp.text
    async with app.state.sm.db.session_factory() as session:
        user = (await session.execute(select(User).where(User.email == EMAIL))).scalar_one()
        user.is_verified = True
        await session.commit()
        return str(user.id)


async def test_registration_attaches_the_user_role(app, client):
    from users.constants import USER_ROLE_NAME
    from users.models import Role, UserRole

    user_id = await _register(app, client)
    async with app.state.sm.db.session_factory() as session:
        names = (
            await session.execute(
                select(Role.name).join(UserRole).where(UserRole.user_id == user_id)
            )
        ).scalars()
        assert list(names) == [USER_ROLE_NAME]


async def test_registered_user_can_open_the_tokens_page(app, client):
    from api_tokens.constants import USER_URL

    user_id = await _register(app, client)
    async with session_client(app, {"user_id": user_id}) as c:
        resp = await c.get(USER_URL, headers=INERTIA_HEADERS)
    assert resp.status_code == 200, resp.text


async def test_admin_created_user_gets_only_the_roles_picked(app, authenticated_client):
    """The admin flow calls ``create()`` with no request: no role picked, no role."""
    from users.models import User, UserRole

    resp = await authenticated_client.post(
        "/api/users/admin",
        json={"email": "picked@example.com", "password": "SecurePass1!", "role_names": []},
    )
    assert resp.status_code == 201, resp.text
    async with app.state.sm.db.session_factory() as session:
        roles = (
            await session.execute(
                select(UserRole).join(User).where(User.email == "picked@example.com")
            )
        ).all()
    assert roles == []
