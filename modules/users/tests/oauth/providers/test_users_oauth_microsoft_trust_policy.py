"""The Microsoft UPN trust policy applies only to a single pinned tenant (#873)."""

import logging

import pytest
from users.core.settings import UsersSettings
from users.oauth.providers import build_client_map

_GUID = "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b"


def _settings(tenant: str, trust: bool) -> UsersSettings:
    return UsersSettings(
        oauth_microsoft_client_id="ms-id",
        oauth_microsoft_client_secret="ms-secret",
        oauth_microsoft_tenant=tenant,
        oauth_microsoft_trust_tenant_upn=trust,
    )


def test_trust_is_off_by_default():
    assert UsersSettings().oauth_microsoft_trust_tenant_upn is False
    settings = UsersSettings(
        oauth_microsoft_client_id="ms-id",
        oauth_microsoft_client_secret="ms-secret",
        oauth_microsoft_tenant=_GUID,
    )
    assert build_client_map(settings)["microsoft"].trust_email is False


def test_trust_applies_to_a_tenant_guid():
    assert build_client_map(_settings(_GUID, True))["microsoft"].trust_email is True
    assert build_client_map(_settings(_GUID.upper(), True))["microsoft"].trust_email is True


@pytest.mark.parametrize(
    "tenant", ["common", "organizations", "consumers", "corp.onmicrosoft.com", ""]
)
def test_trust_is_ignored_without_a_single_tenant(tenant, caplog):
    with caplog.at_level(logging.WARNING, logger="users.settings"):
        settings = _settings(tenant, True)
    assert build_client_map(settings)["microsoft"].trust_email is False
    assert "users.oauth.microsoft_trust_ignored" in caplog.text


def test_no_warning_when_trust_is_effective_or_off(caplog):
    with caplog.at_level(logging.WARNING, logger="users.settings"):
        _settings(_GUID, True)
        _settings("common", False)
    assert "microsoft_trust_ignored" not in caplog.text


def test_other_providers_never_carry_trust():
    settings = _settings(_GUID, True).model_copy(
        update={"oauth_google_client_id": "g", "oauth_google_client_secret": "g"}
    )
    assert build_client_map(settings)["google"].trust_email is False
