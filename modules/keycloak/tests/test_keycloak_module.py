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


class TestKeycloakLoginRedirectUrl:
    """A blanked ``login_redirect_url`` must never reach the OIDC callback.

    ``endpoints/api.py`` puts this value straight into a ``Location`` header,
    and an admin can clear it in the generic module-settings editor. This is a
    second copy of the field — ``users`` has its own — so it needs its own
    guard; the two provider modules must not import each other.
    """

    def test_blank_falls_back_to_the_default(self):
        from keycloak.settings import KeycloakSettings

        assert KeycloakSettings(login_redirect_url="").login_redirect_url == "/dashboard/"

    def test_whitespace_only_falls_back_to_the_default(self):
        from keycloak.settings import KeycloakSettings

        assert KeycloakSettings(login_redirect_url="   ").login_redirect_url == "/dashboard/"

    def test_a_real_value_is_left_alone(self):
        from keycloak.settings import KeycloakSettings

        assert KeycloakSettings(login_redirect_url="/home/").login_redirect_url == "/home/"
