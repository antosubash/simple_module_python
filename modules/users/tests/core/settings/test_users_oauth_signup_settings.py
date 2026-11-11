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


def test_signup_provider_names_match_the_buildable_providers():
    from users.core.oauth_settings import OAUTH_PROVIDER_NAMES
    from users.oauth.providers import build_client_map

    configured = UsersSettings(
        oauth_google_client_id="g",
        oauth_google_client_secret="g",
        oauth_github_client_id="h",
        oauth_github_client_secret="h",
        oauth_microsoft_client_id="m",
        oauth_microsoft_client_secret="m",
    )
    # OIDC needs a reachable discovery URL to build, so it is checked by name.
    assert set(build_client_map(configured)) | {"oidc"} == OAUTH_PROVIDER_NAMES


def test_oauth_fields_follow_the_core_fields():
    """The settings editor groups by first appearance; the split keeps the old order."""
    fields = list(UsersSettings.model_fields)
    assert fields[0] == "allow_signup"
    assert fields.index("bootstrap_user_password") < fields.index("oauth_google_client_id")
    first_oauth = fields.index("oauth_google_client_id")
    assert all(name.startswith("oauth_") for name in fields[first_oauth:])
