"""Integration tests for pluggable auth — verifying both providers work."""

from __future__ import annotations

from auth.contracts.provider import AuthProvider


def test_users_module_is_auth_provider():
    from users.module import UsersModule

    assert UsersModule._is_auth_provider is True


def test_keycloak_module_is_auth_provider():
    from keycloak.module import KeycloakModule

    assert KeycloakModule._is_auth_provider is True


def test_sm020_fires_with_both_modules():
    from keycloak.module import KeycloakModule
    from simple_module_core.diagnostics._module import ModuleDiagnostics
    from users.module import UsersModule

    diags = ModuleDiagnostics()
    results = diags._check_auth_provider_conflict([UsersModule(), KeycloakModule()])
    assert any(d.code == "SM020" for d in results)


def test_sm021_fires_with_neither():
    from simple_module_core.diagnostics._module import ModuleDiagnostics
    from simple_module_core.module import ModuleBase, ModuleMeta

    class StubModule(ModuleBase):
        meta = ModuleMeta(name="Stub")

    diags = ModuleDiagnostics()
    results = diags._check_auth_provider_conflict([StubModule()])
    assert any(d.code == "SM021" for d in results)


def test_auth_provider_protocol_satisfied_by_users():
    from users.provider import UsersAuthProvider

    assert isinstance(UsersAuthProvider(), AuthProvider)


def test_auth_provider_protocol_satisfied_by_keycloak():
    from keycloak.provider import KeycloakAuthProvider
    from keycloak.settings import KeycloakSettings

    settings = KeycloakSettings(
        server_url="https://example.com",
        realm="test",
        client_id="app",
        client_secret="secret",
    )
    assert isinstance(KeycloakAuthProvider(settings), AuthProvider)
