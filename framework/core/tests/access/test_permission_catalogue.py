"""Catalogue declarations feed guards and registration with identical keys."""

import json

from simple_module_core import ModuleBase, ModuleMeta
from simple_module_core.access.permissions import PermissionCatalogue, PermissionRegistry


class Orders(PermissionCatalogue, group="Orders", label_key="orders.permissions"):
    VIEW = "orders.view", "View orders"
    EDIT = "orders.edit"


class OrdersModule(ModuleBase):
    meta = ModuleMeta(name="Orders")
    permissions = Orders


def test_default_hook_registers_catalogue_without_granting_roles():
    registry = PermissionRegistry()
    OrdersModule().register_permissions(registry)
    assert registry.all_permissions == ["orders.edit", "orders.view"]
    assert registry.groups[0].name == "Orders"
    assert registry.groups[0].label_key == "orders.permissions"
    assert registry.source_labels("Orders") == {"orders.view": "View orders"}
    assert json.dumps([Orders.VIEW]) == '["orders.view"]'
    assert registry.get_permissions_for_roles([]) == set()


def test_custom_hook_can_extend_catalogue_and_legacy_modules_stay_empty():
    class Custom(OrdersModule):
        def register_permissions(self, registry):
            super().register_permissions(registry)
            registry.map_role("editor", [Orders.EDIT])

    registry = PermissionRegistry()
    Custom().register_permissions(registry)
    assert registry.get_permissions_for_roles(["editor"], registry.role_map) == {"orders.edit"}
    before = registry.all_permissions
    ModuleBase().register_permissions(registry)
    assert registry.all_permissions == before


def test_catalogue_is_visible_to_doctor_without_a_custom_registration_hook():
    from simple_module_core.diagnostics._module import ModuleDiagnostics

    class Visible(OrdersModule):
        meta = ModuleMeta(name="Orders", view_prefix="/orders")

        def register_routes(self, api_router, view_router):
            pass

    assert ModuleDiagnostics()._check_views_without_menu([Visible()]) == []


def test_runtime_labels_extend_catalogue_labels_without_mutating_them():
    registry = PermissionRegistry()
    registry.add_catalogue(Orders)
    registry.add_source("Orders", lambda: [("orders.edit", "Edit orders")])
    labels = registry.source_labels("Orders")
    assert labels == {"orders.view": "View orders", "orders.edit": "Edit orders"}
    labels.clear()
    assert registry.source_labels("Orders")["orders.view"] == "View orders"
