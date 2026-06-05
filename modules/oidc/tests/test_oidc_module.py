"""Tests for OidcModule lifecycle."""

from __future__ import annotations

from auth.contracts.provider import AuthProvider


def test_oidc_module_meta():
    from oidc.module import OidcModule

    mod = OidcModule()
    assert mod.meta.name == "Oidc"
    assert mod.meta.depends_on == ["Auth", "Settings"]
    assert mod._is_auth_provider is True


def test_oidc_provider_satisfies_protocol():
    from oidc.provider import OidcAuthProvider

    provider = OidcAuthProvider()
    assert isinstance(provider, AuthProvider)
    assert provider.name == "oidc"
