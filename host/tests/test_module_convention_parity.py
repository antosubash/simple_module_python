"""Freeze all built-in mount points, render identities and namespaces for #980."""

from pathlib import Path

from simple_module_core.discovery import discover_modules, get_module_package_name

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


def test_all_builtin_identities_and_namespaces_are_unchanged():
    modules = {get_module_package_name(m): m for m in discover_modules(strict=True)}
    assert set(modules) == set(EXPECTED)
    root = Path(__file__).resolve().parents[2]
    assert {p.name for p in (root / "modules").iterdir() if p.is_dir()} == set(EXPECTED)
    for package, expected in EXPECTED.items():
        mod = modules[package]
        meta = mod.meta
        assert (meta.name, meta.route_prefix, meta.view_prefix, meta.admin_view_prefix) == expected
        locales = (
            {}
            if package in {"mail", "site_lock"}
            else {package: root / "modules" / package / package / "locales"}
        )
        assert mod.locale_dirs() == locales
