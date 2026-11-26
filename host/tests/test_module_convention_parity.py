"""Freeze all built-in mount points, render identities and namespaces for #980."""

from pathlib import Path

from fastapi import FastAPI
from simple_module_core import ModuleBase
from simple_module_core.modules.discovery import discover_modules, get_module_package_name
from simple_module_hosting.boot._module_routes import wire_module_routes
from simple_module_hosting.pipeline._route_paths import app_route_paths

# Captured before replacing built-in overrides with the package defaults.
EXPECTED = {
    "api_tokens": ("ApiTokens", "/api/api_tokens", "/api-tokens", "/admin/api-tokens"),
    "audit_log": ("AuditLog", "/api/audit_log", "/admin/audit-log", ""),
    "auth": ("Auth", "/auth", "", ""),
    "background_tasks": ("BackgroundTasks", "/api/background_tasks", "/admin/background-tasks", ""),
    "branding": ("Branding", "/api/branding", "/admin/branding", ""),
    "dashboard": ("Dashboard", "/api/dashboard", "/dashboard", "/admin/doctor"),
    "feature_flags": ("FeatureFlags", "/api/feature_flags", "/admin/feature-flags", ""),
    "file_storage": ("FileStorage", "/api/file-storage", "/file-storage", ""),
    "keycloak": ("Keycloak", "/api/keycloak", "/keycloak", ""),
    "mail": ("Mail", "", "", ""),
    "oidc": ("Oidc", "/api/oidc", "/oidc", ""),
    "permissions": ("Permissions", "/api/permissions", "/admin/permissions", ""),
    "settings": ("Settings", "/api/settings", "/admin/settings", ""),
    "sharing": ("Sharing", "/api/sharing", "/admin/sharing", ""),
    "site_lock": ("SiteLock", "", "", ""),
    "tenants": ("Tenants", "/api/tenants", "/tenants", "/admin/tenants"),
    "users": ("Users", "/api/users", "/users", "/admin/users"),
}

# Paths served by the conventional routers before their overrides were removed.
CONVENTIONAL_PATHS = {
    "audit_log": ("/api/audit_log/", "/admin/audit-log/"),
    "dashboard": ("/api/dashboard/stats", "/dashboard/"),
    "feature_flags": ("/api/feature_flags/", "/admin/feature-flags/"),
    "keycloak": ("/api/keycloak/auth/login", "/keycloak/login"),
    "oidc": ("/api/oidc/auth/login", "/oidc/login"),
    "permissions": ("/api/permissions/", "/admin/permissions/"),
    "sharing": ("/api/sharing/shares", "/admin/sharing/"),
}


def test_all_builtin_identities_and_namespaces_are_unchanged():
    modules = {get_module_package_name(m): m for m in discover_modules(strict=True)}
    assert set(modules) == set(EXPECTED)
    root = Path(__file__).resolve().parents[2]
    assert {p.name for p in (root / "modules").iterdir() if p.is_dir()} == set(EXPECTED)
    for package, expected in EXPECTED.items():
        mod = modules[package]
        meta = mod.meta
        assert (meta.name, meta.route_prefix, meta.view_prefix, meta.admin_view_prefix) == expected
        assert type(meta.version) is str
        # Every built-in ships a catalog: mail and site_lock gained theirs
        # for the settings editor's ``settings_form`` labels.
        locales = {package: root / "modules" / package / package / "locales"}
        assert mod.locale_dirs() == locales
        if package in CONVENTIONAL_PATHS:
            assert type(mod).register_routes is ModuleBase.register_routes
            app = FastAPI()
            wire_module_routes(app, mod)
            paths = app_route_paths(app)
            for path in CONVENTIONAL_PATHS[package]:
                assert path in paths
