"""Tests for KeycloakModule lifecycle."""

from __future__ import annotations

from auth.contracts.provider import AuthProvider


def test_keycloak_module_meta():
    from keycloak.module import KeycloakModule

    mod = KeycloakModule()
    assert mod.meta.name == "Keycloak"
    assert mod.meta.depends_on == ["Auth"]
    assert mod.meta.optional_depends_on == ["Settings"]
    assert mod.meta.provides_auth is True


def test_keycloak_provider_satisfies_protocol():
    from keycloak.identity.provider import KeycloakAuthProvider

    provider = KeycloakAuthProvider()
    assert isinstance(provider, AuthProvider)
    assert provider.name == "keycloak"


def test_keycloak_registers_no_setup_steps():
    """Opt-out: a Keycloak install's local users table is empty forever, so any
    required step (e.g. "create a superuser") would lock it out of the app."""
    from keycloak.module import KeycloakModule
    from simple_module_core.web.setup_steps import SetupRegistry

    registry = SetupRegistry()
    KeycloakModule().register_setup_steps(registry)
    assert not registry
    assert registry.required_steps == []
