"""A Keycloak app boots strictly with every module, Permissions included (#953).

Selecting ``keycloak`` drops ``Users``. Since #953 ``permissions`` reads roles
through the role-directory contract and depends only on ``Auth``, so a strict
(non-development) boot no longer refuses it. The user and role directories both
come from Keycloak.
"""

from __future__ import annotations

from keycloak.identity.directory import KeycloakDirectory
from simple_module_core.access.role_directory import MappedRoleDirectory, get_role_directory
from simple_module_core.access.user_directory import get_user_directory
from simple_module_hosting.boot.app_builder import create_app
from simple_module_hosting.config.settings import Settings


def _settings(environment: str, modules_enabled: list[str] | None = None) -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        environment=environment,
        secret_key="test-secret-key",
        multi_tenant=False,
        auth_provider="keycloak",
        modules_enabled=modules_enabled,
    )


def test_non_development_boots_every_module_without_users():
    app = create_app(_settings("testing"))
    names = {m.meta.name for m in app.state.sm.modules}
    assert "Users" not in names
    assert {"Permissions", "ApiTokens", "AuditLog", "Dashboard", "FileStorage"} <= names


def test_directories_come_from_keycloak():
    app = create_app(_settings("testing"))
    assert isinstance(get_user_directory(app), KeycloakDirectory)
    assert isinstance(get_role_directory(app), MappedRoleDirectory)


def test_development_does_not_warn_about_permissions(monkeypatch, caplog):
    # The dev-boot pass writes the frontend's generated files into the source
    # tree; with this module set that would clobber the workspace's copies.
    import simple_module_hosting.boot.app_builder as app_builder

    monkeypatch.setattr(app_builder, "run_dev_boot", lambda *a, **kw: None)
    app = create_app(_settings("development"))
    names = {m.meta.name for m in app.state.sm.modules}
    assert "Permissions" in names
    assert not any("depends on 'Users'" in r.getMessage() for r in caplog.records)
