"""``oauth_trusted_email_domains`` and ``oauth_sync_profile`` settings (#877, #878)."""

import logging

import pytest
from pydantic import ValidationError
from users.core.settings import UsersSettings

_GUID = "6f1c2a3b-4d5e-4f60-8a7b-9c0d1e2f3a4b"


def test_defaults_trust_nothing_and_do_not_sync():
    settings = UsersSettings()
    assert settings.oauth_trusted_email_domains == {}
    assert settings.oauth_sync_profile is False
    assert settings.trusted_domains("oidc") == frozenset()


def test_domains_are_normalised_per_provider():
    settings = UsersSettings(
        oauth_trusted_email_domains={" OIDC ": ["IIASA.ac.at", "bücher.example"]}
    )
    assert settings.oauth_trusted_email_domains == {
        "oidc": ["iiasa.ac.at", "xn--bcher-kva.example"]
    }
    assert settings.trusted_domains("oidc") == {"iiasa.ac.at", "xn--bcher-kva.example"}
    assert settings.trusted_domains("google") == frozenset()


@pytest.mark.parametrize(
    "value",
    [
        {"facebook": ["a.org"]},
        # Anyone can add an unverified address on any domain to these accounts.
        {"github": ["a.org"]},
        {"google": ["a.org"]},
        {"oidc": ["*.a.org"]},
        {"oidc": [".a.org"]},
    ],
)
def test_bad_entries_are_rejected(value):
    with pytest.raises(ValidationError) as exc:
        UsersSettings(oauth_trusted_email_domains=value)
    assert exc.value.errors()[0]["loc"][0] == "oauth_trusted_email_domains"


def test_microsoft_domains_need_a_pinned_tenant(caplog):
    with caplog.at_level(logging.WARNING, logger="users.settings"):
        common = UsersSettings(oauth_trusted_email_domains={"microsoft": ["iiasa.ac.at"]})
    assert "users.oauth.trusted_domains_ignored" in caplog.text
    assert common.trusted_domains("microsoft") == frozenset()
    pinned = UsersSettings(
        oauth_microsoft_tenant=_GUID, oauth_trusted_email_domains={"microsoft": ["iiasa.ac.at"]}
    )
    assert pinned.trusted_domains("microsoft") == {"iiasa.ac.at"}
