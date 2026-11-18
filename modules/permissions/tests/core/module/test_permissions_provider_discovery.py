"""Selecting an external provider preserves Permissions without SM030 (#953)."""

import pytest
from auth.module import AuthModule
from keycloak.module import KeycloakModule
from oidc.module import OidcModule
from permissions.module import PermissionsModule
from simple_module_core.diagnostics import ModuleDiagnostics
from simple_module_core.discovery import (
    missing_dependencies,
    select_auth_provider,
    topological_sort,
)
from users.module import UsersModule


@pytest.mark.parametrize("provider", ["keycloak", "oidc"])
def test_external_provider_keeps_permissions(provider):
    selected = select_auth_provider(
        [AuthModule(), UsersModule(), KeycloakModule(), OidcModule(), PermissionsModule()],
        provider,
        strict=True,
    )
    assert missing_dependencies(selected) == []
    assert "Permissions" in [m.meta.name for m in topological_sort(selected, strict=True)]
    assert "Users" not in [m.meta.name for m in selected]
    assert not [d for d in ModuleDiagnostics().run(selected) if d.code == "SM030"]
