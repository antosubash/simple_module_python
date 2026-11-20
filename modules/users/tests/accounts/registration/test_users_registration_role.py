"""Role selection for local and OAuth registration."""

import pytest
from users.accounts.registration import registration_role
from users.core.settings import UsersSettings


@pytest.mark.parametrize(("configured", "expected"), [(" labeller ", "labeller"), ("", None)])
def test_local_registration_uses_the_configured_role(configured, expected):
    settings = UsersSettings(signup_default_role=configured)
    assert registration_role(settings, None) == expected


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
