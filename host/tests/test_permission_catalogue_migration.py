"""Stored permission grants and role-editor entries survive #1037 unchanged."""

from __future__ import annotations

import importlib

import pytest
from simple_module_core.access.permissions import PermissionCatalogue, PermissionRegistry
from simple_module_hosting.boot.app_builder import create_app

# Keys and registration snapshots captured before migration from origin/main
# 7af3935aa79211a5ffe3817ce9de7fe5b192bd61, using git show on each module's
# core/constants.py and module.py. Keep literals: stored grants reference them.
_BEFORE = {
    "audit_log": ("AuditLogModule", "AuditLog", ["audit_log.view"], {"admin": ["*"]}),
    "background_tasks": (
        "BackgroundTasksModule",
        "Background tasks",
        ["background_tasks.view", "background_tasks.manage"],
        {"admin": ["*"]},
    ),
    "branding": (
        "BrandingModule",
        "Branding",
        ["branding.view", "branding.manage"],
        {"admin": ["*"]},
    ),
    "dashboard": ("DashboardModule", "Dashboard", ["dashboard.view"], {"admin": ["*"]}),
    "feature_flags": (
        "FeatureFlagsModule",
        "Feature flags",
        ["feature_flags.view", "feature_flags.manage"],
        {"admin": ["*"]},
    ),
    "file_storage": (
        "FileStorageModule",
        "Files",
        [
            "file_storage.upload",
            "file_storage.download",
            "file_storage.delete",
            "file_storage.manage",
        ],
        {
            "admin": ["*"],
            "user": ["file_storage.download", "file_storage.upload"],
            "tenant:member": ["file_storage.download", "file_storage.upload"],
            "tenant:admin": [
                "file_storage.delete",
                "file_storage.download",
                "file_storage.manage",
                "file_storage.upload",
            ],
            "tenant:owner": [
                "file_storage.delete",
                "file_storage.download",
                "file_storage.manage",
                "file_storage.upload",
            ],
        },
    ),
    "permissions": (
        "PermissionsModule",
        "Permissions",
        ["permissions.view", "permissions.manage"],
        {"admin": ["*"]},
    ),
    "settings": (
        "SettingsModule",
        "Settings",
        [
            "settings.view",
            "settings.create",
            "settings.edit",
            "settings.delete",
            "settings.tenant.edit",
        ],
        {
            "admin": ["*"],
            "tenant:owner": ["settings.tenant.edit"],
            "tenant:admin": ["settings.tenant.edit"],
        },
    ),
    "sharing": (
        "SharingModule",
        "Sharing",
        ["sharing.share", "sharing.view", "sharing.manage", "sharing.directory_search"],
        {
            "admin": ["*"],
            "user": ["sharing.share"],
            "tenant:owner": ["sharing.share"],
            "tenant:admin": ["sharing.share"],
            "tenant:member": ["sharing.share"],
        },
    ),
    "tenants": (
        "TenantsModule",
        "Tenants",
        [
            "tenants.members.view",
            "tenants.members.manage",
            "tenants.platform.view",
            "tenants.platform.manage",
        ],
        {
            "admin": ["*"],
            "tenant:owner": ["tenants.members.manage", "tenants.members.view"],
            "tenant:admin": ["tenants.members.manage", "tenants.members.view"],
            "tenant:member": ["tenants.members.view"],
        },
    ),
    "users": (
        "UsersModule",
        "Users",
        ["users.manage", "users.self.profile"],
        {"admin": ["*"], "user": ["users.self.profile"]},
    ),
}


@pytest.mark.parametrize("package", _BEFORE)
def test_catalogue_preserves_stored_permission_keys(package: str) -> None:
    class_name, _, old_keys, _ = _BEFORE[package]
    module = getattr(importlib.import_module(f"{package}.module"), class_name)()
    catalogue = module.permissions
    assert catalogue is not None
    assert issubclass(catalogue, PermissionCatalogue)
    assert [member.value for member in catalogue] == old_keys


@pytest.mark.parametrize("package", _BEFORE)
def test_permission_registration_matches_before_migration(package: str) -> None:
    class_name, group_name, old_keys, roles = _BEFORE[package]
    module = getattr(importlib.import_module(f"{package}.module"), class_name)()
    registry = PermissionRegistry()
    module.register_permissions(registry)

    (group,) = registry.groups
    assert (group.name, group.permissions, group.label_key) == (
        group_name,
        old_keys,
        f"{package}.permission_group",
    )
    # No member labels/descriptions were registered before migration.
    assert registry.source_labels(group_name) == {}
    assert {r: sorted(keys) for r, keys in registry.role_map.items()} == roles


def test_app_permission_registry_matches_before_migration(settings) -> None:
    # Build the actual app without a lifespan/server or database IO.
    app = create_app(settings)
    registry = app.state.sm.permissions
    groups = {g.name: g for g in registry.groups}
    for package, (_, group_name, old_keys, _) in _BEFORE.items():
        group = groups[group_name]
        assert group.permissions == old_keys
        assert group.label_key == f"{package}.permission_group"
        assert registry.source_labels(group_name) == {}
    assert {r: sorted(keys) for r, keys in registry.role_map.items()} == {
        "admin": ["*"],
        "tenant:owner": [
            "api_tokens.use",
            "file_storage.delete",
            "file_storage.download",
            "file_storage.manage",
            "file_storage.upload",
            "settings.tenant.edit",
            "sharing.share",
            "tenants.members.manage",
            "tenants.members.view",
        ],
        "tenant:admin": [
            "api_tokens.use",
            "file_storage.delete",
            "file_storage.download",
            "file_storage.manage",
            "file_storage.upload",
            "settings.tenant.edit",
            "sharing.share",
            "tenants.members.manage",
            "tenants.members.view",
        ],
        "user": [
            "api_tokens.use",
            "file_storage.download",
            "file_storage.upload",
            "sharing.share",
            "users.self.profile",
        ],
        "tenant:member": [
            "api_tokens.use",
            "file_storage.download",
            "file_storage.upload",
            "sharing.share",
            "tenants.members.view",
        ],
    }


# Imports still used by other modules/tests remain compatible until 0.0.50.
_ALIASES = {
    "audit_log": {"PERM_VIEW": "VIEW"},
    "background_tasks": {"PERM_VIEW": "VIEW", "PERM_MANAGE": "MANAGE"},
    "branding": {"PERM_VIEW": "VIEW"},
    "dashboard": {"PERM_VIEW": "VIEW"},
    "feature_flags": {"PERM_FEATURE_FLAGS_VIEW": "VIEW", "PERM_FEATURE_FLAGS_MANAGE": "MANAGE"},
    "permissions": {"PERM_VIEW": "VIEW", "PERM_MANAGE": "MANAGE"},
    "settings": {
        "PERM_VIEW": "VIEW",
        "PERM_CREATE": "CREATE",
        "PERM_EDIT": "EDIT",
        "PERM_DELETE": "DELETE",
        "PERM_TENANT_EDIT": "TENANT_EDIT",
    },
    "sharing": {"PERM_SHARE": "SHARE", "PERM_MANAGE": "MANAGE"},
    "users": {"PERM_USERS_MANAGE": "MANAGE"},
}


@pytest.mark.parametrize("package", _ALIASES)
def test_deprecated_permission_aliases_keep_their_keys_and_removal_release(package: str) -> None:
    from simple_module_core.runtime.deprecation import registered_deprecations

    constants = importlib.import_module(f"{package}.core.constants")
    for old_name, member_name in _ALIASES[package].items():
        assert getattr(constants, old_name) is getattr(constants.Permissions, member_name)
    deprecation = next(
        d for d in registered_deprecations() if d.name == f"{package} PERM_* constants"
    )
    assert deprecation.remove_in == "0.0.50"
    assert deprecation.use == f"{package}.core.constants.Permissions"
