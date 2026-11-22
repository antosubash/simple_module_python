"""Scaffolded packages use the same identity conventions as installed modules."""

import importlib
import sys

import pytest
from simple_module_cli.scaffold.scaffolding import create_module
from simple_module_core.menu import MenuRegistry
from simple_module_core.permissions import PermissionRegistry


@pytest.mark.parametrize("with_settings", [False, True])
def test_scaffold_defaults_match_its_menu_locales_and_api(tmp_path, monkeypatch, with_settings):
    dest = create_module(
        tmp_path / "parcel_registry", "parcel_registry", with_settings=with_settings
    )
    monkeypatch.syspath_prepend(str(dest))
    try:
        cls = importlib.import_module("parcel_registry.module").ParcelRegistryModule
        mod = cls()
        assert mod.meta.route_prefix == "/api/parcel-registry"
        assert mod.meta.view_prefix == "/parcel-registry"
        assert mod.locale_dirs() == {"parcel_registry": dest / "parcel_registry" / "locales"}
        permissions = PermissionRegistry()
        mod.register_permissions(permissions)
        assert permissions.all_permissions == [
            "parcel_registry.create",
            "parcel_registry.delete",
            "parcel_registry.edit",
            "parcel_registry.view",
        ]
        assert permissions.groups[0].name == "ParcelRegistry"
        assert mod.permissions.VIEW == "parcel_registry.view"
        menu = MenuRegistry()
        mod.register_menu_items(menu)
        assert menu.all_items[0].url == "/parcel-registry/"
        assert cls.meta.requires_framework == ">=1.0,<2.0"
        assert (
            '"/api/parcel-registry/"'
            in (dest / "parcel_registry" / "pages" / "api.generated.ts").read_text()
        )
    finally:
        for name in list(sys.modules):
            if name == "parcel_registry" or name.startswith("parcel_registry."):
                sys.modules.pop(name, None)
