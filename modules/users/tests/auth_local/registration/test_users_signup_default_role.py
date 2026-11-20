"""Local self-signup assigns the configured existing role (#1055)."""

import pytest
from _users_oauth_support import find_user, set_users_settings
from pydantic import ValidationError
from sqlalchemy import select
from users.accounts.registration import registration_role
from users.core.settings import UsersSettings
from users.models import Role, UserRole


@pytest.mark.parametrize(("configured", "expected"), [(" labeller ", "labeller"), ("", None)])
def test_local_registration_uses_the_configured_role(configured, expected):
    settings = UsersSettings(signup_default_role=configured)
    assert registration_role(settings, None) == expected


@pytest.mark.parametrize("role", ["admin", " Admin "])
def test_local_signup_cannot_grant_admin(role):
    with pytest.raises(ValidationError) as exc:
        UsersSettings(signup_default_role=role)
    assert exc.value.errors()[0]["loc"] == ("signup_default_role",)


@pytest.mark.parametrize(
    ("provider", "allow_signup", "expected"),
    [
        ("oidc", True, "staff"),
        ("oidc", False, "staff"),
        ("google", True, "user"),
        ("google", False, None),
    ],
)
def test_local_role_setting_does_not_change_oauth_roles(provider, allow_signup, expected):
    settings = UsersSettings(
        allow_signup=allow_signup,
        signup_default_role="labeller",
        oauth_signup_providers=["oidc"],
        oauth_signup_default_role="staff",
    )
    assert registration_role(settings, provider) == expected


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
