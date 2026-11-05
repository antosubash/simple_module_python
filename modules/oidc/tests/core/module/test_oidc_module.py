"""Tests for OidcModule lifecycle."""

from __future__ import annotations

from auth.contracts.provider import AuthProvider


def test_oidc_module_meta():
    from oidc.module import OidcModule

    mod = OidcModule()
    assert mod.meta.name == "Oidc"
    assert mod.meta.depends_on == ["Auth"]
    assert mod.meta.optional_depends_on == ["Settings"]
    assert mod._is_auth_provider is True


def test_oidc_provider_satisfies_protocol():
    from oidc.identity.provider import OidcAuthProvider

    provider = OidcAuthProvider()
    assert isinstance(provider, AuthProvider)
    assert provider.name == "oidc"


def test_public_routes():
    from oidc.module import OidcModule
    from simple_module_core.public_routes import PublicRouteRegistry

    registry = PublicRouteRegistry()
    OidcModule().register_public_routes(registry)
    for path in (
        "/oidc/login",
        "/oidc/logged-out",
        "/api/oidc/auth/login",
        "/api/oidc/auth/callback",
    ):
        assert registry.matches("GET", path)
    assert not registry.matches("GET", "/api/oidc/private")
