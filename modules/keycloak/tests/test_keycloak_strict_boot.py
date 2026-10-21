"""A Keycloak app boots with its directory, and refuses modules that need Users.

Selecting ``keycloak`` drops ``Users``. Outside development the host sorts
modules strictly, so ``permissions`` and ``api_tokens`` (which still depend on
``Users``) fail the boot in one error naming both, instead of booting against
empty ``users_*`` tables (GH #501).
"""

from __future__ import annotations

import pytest
from keycloak.directory import KeycloakDirectory
from keycloak_test_modules import keycloak_modules_enabled
from simple_module_core.exceptions import MissingDependencyError
from simple_module_core.user_directory import get_user_directory
from simple_module_hosting.app_builder import create_app
from simple_module_hosting.settings import Settings


def _settings(environment: str, modules_enabled: list[str] | None = None) -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        environment=environment,
        secret_key="test-secret-key",
        multi_tenant=False,
        auth_provider="keycloak",
        modules_enabled=modules_enabled,
    )


def test_non_development_refuses_every_module_that_needs_users():
    with pytest.raises(MissingDependencyError) as exc:
        create_app(_settings("testing"))
    assert ("Permissions", "Users") in exc.value.missing
    assert ("ApiTokens", "Users") in exc.value.missing
    assert {dep for _name, dep in exc.value.missing} == {"Users"}


def test_without_them_the_app_boots_with_the_keycloak_directory():
    app = create_app(_settings("testing", keycloak_modules_enabled()))
    assert isinstance(get_user_directory(app), KeycloakDirectory)
    names = {m.meta.name for m in app.state.sm.modules}
    assert {"AuditLog", "Dashboard", "FileStorage"} <= names
    assert not names & {"Users", "Permissions", "ApiTokens"}


def test_development_only_warns(monkeypatch, caplog):
    # The dev-boot pass writes the frontend's generated files into the source
    # tree; with this module set that would clobber the workspace's copies.
    import simple_module_hosting.app_builder as app_builder

    monkeypatch.setattr(app_builder, "run_dev_boot", lambda *a, **kw: None)
    app = create_app(_settings("development"))
    names = {m.meta.name for m in app.state.sm.modules}
    assert "Permissions" in names
    assert any("'Permissions' depends on 'Users'" in r.getMessage() for r in caplog.records)
