"""Tests for KeycloakModule lifecycle."""

from __future__ import annotations

from auth.contracts.provider import AuthProvider


def test_keycloak_module_meta():
    from keycloak.module import KeycloakModule

    mod = KeycloakModule()
    assert mod.meta.name == "Keycloak"
    assert mod.meta.depends_on == ["Auth", "Settings"]
    assert mod._is_auth_provider is True


def test_keycloak_provider_satisfies_protocol():
    from keycloak.provider import KeycloakAuthProvider

    provider = KeycloakAuthProvider()
    assert isinstance(provider, AuthProvider)
    assert provider.name == "keycloak"
