"""Schema-only installs must get a usable signup role at startup (GH #600)."""

from __future__ import annotations

import uuid

import httpx
import pytest
from _users_app_builders import _make_admin_user, _seed_users_settings, _setup_app_db
from simple_module_hosting.app_builder import create_app
from simple_module_hosting.settings import Settings
from sqlalchemy import select
from users.constants import USER_ROLE_ID
from users.models import Role, User, UserRole
from users.module import UsersModule


@pytest.mark.parametrize("existing_role", [False, True], ids=["schema-only", "custom-role"])
async def test_startup_ensures_signup_role_without_overwriting_existing_role(existing_role):
    app = create_app(
        Settings(
            database_url="sqlite+aiosqlite:///:memory:",
            environment="testing",
            secret_key="test-secret-key",
            multi_tenant=False,
            redis_url=None,
        )
    )
    await _setup_app_db(app)
    await _seed_users_settings(app, allow_signup=True)
    role_id = uuid.uuid4() if existing_role else USER_ROLE_ID
    description = "Operator's custom role" if existing_role else "Standard user"
    async with app.state.sm.db.session_factory() as db:
        assert (await db.execute(select(Role))).scalars().all() == []
        if existing_role:
            db.add(Role(id=role_id, name="user", description=description))
            await db.commit()

    async with app.router.lifespan_context(app):
        assert any(role.id == str(role_id) for role in app.state.users.roles_cache)
        # A scaffolded app completes admin setup before public signup is usable.
        await _make_admin_user(app)
        # Re-running startup must preserve the role and avoid duplicate inserts.
        await UsersModule().on_startup(app)
        assert any(role.id == str(role_id) for role in app.state.users.roles_cache)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            response = await client.post(
                "/api/users/auth/register",
                json={"email": "fresh@example.com", "password": "StrongPass1!"},
            )
        assert response.status_code == 201, response.text
        async with app.state.sm.db.session_factory() as db:
            roles = (await db.execute(select(Role).where(Role.name == "user"))).scalars().all()
            assert len(roles) == 1
            assert (roles[0].id, roles[0].description) == (role_id, description)
            assigned = (
                (
                    await db.execute(
                        select(Role.name)
                        .join(UserRole, UserRole.role_id == Role.id)
                        .join(User, User.id == UserRole.user_id)
                        .where(User.email == "fresh@example.com")
                    )
                )
                .scalars()
                .all()
            )
            assert assigned == ["user"]
