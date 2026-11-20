"""Local self-signup assigns the configured existing role (#1055)."""

import pytest
from _users_oauth_support import find_user, set_users_settings
from sqlalchemy import select
from users.models import Role, UserRole


@pytest.mark.parametrize("role_exists", [True, False])
async def test_self_signup_looks_up_the_role_without_creating_it(
    users_app_signup, anon_client_signup, caplog, role_exists
):
    set_users_settings(users_app_signup, signup_default_role="labeller", require_verification=False)
    factory = users_app_signup.state.sm.db.session_factory
    async with factory() as session:
        role = Role(name="labeller") if role_exists else None
        if role is not None:
            session.add(role)
            await session.commit()

    response = await anon_client_signup.post(
        "/api/users/auth/register",
        json={"email": "signup-role@example.com", "password": "SecurePass1!"},
    )

    assert response.status_code == 201, response.text
    user = await find_user(users_app_signup, "signup-role@example.com")
    async with factory() as session:
        roles = (
            (await session.execute(select(UserRole.role_id).where(UserRole.user_id == user.id)))
            .scalars()
            .all()
        )
        assert roles == ([role.id] if role_exists else [])
        if not role_exists:
            assert (
                await session.execute(select(Role).where(Role.name == "labeller"))
            ).scalar_one_or_none() is None
            assert "No 'labeller' role exists" in caplog.text
