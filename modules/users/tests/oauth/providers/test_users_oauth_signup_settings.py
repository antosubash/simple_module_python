"""Provider-scoped SSO provisioning settings (#874)."""

import pytest
from pydantic import ValidationError
from users.core.settings import UsersSettings


def test_provisioning_is_off_by_default():
    settings = UsersSettings()
    assert settings.oauth_signup_providers == []
    assert settings.oauth_signup_default_role == ""


def test_known_providers_are_accepted():
    settings = UsersSettings(oauth_signup_providers=["microsoft", "oidc"])
    assert settings.oauth_signup_providers == ["microsoft", "oidc"]


def test_unknown_provider_is_rejected():
    with pytest.raises(ValidationError) as exc:
        UsersSettings(oauth_signup_providers=["microsoft", "facebook"])
    assert exc.value.errors()[0]["loc"] == ("oauth_signup_providers",)


@pytest.mark.parametrize("role", ["admin", " Admin "])
def test_admin_is_never_the_provisioning_role(role):
    with pytest.raises(ValidationError) as exc:
        UsersSettings(oauth_signup_default_role=role)
    assert exc.value.errors()[0]["loc"] == ("oauth_signup_default_role",)


def test_a_role_name_is_stored_trimmed():
    assert UsersSettings(oauth_signup_default_role=" staff ").oauth_signup_default_role == "staff"
