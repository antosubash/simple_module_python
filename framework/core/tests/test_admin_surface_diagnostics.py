"""Admin-only pages must remain discoverable after adopting AdminSurface (#988)."""

import pytest
from simple_module_core import AdminSurface, ModuleBase, ModuleMeta
from simple_module_core.diagnostics import ModuleDiagnostics
from simple_module_core.diagnostics._types import DiagnosticLevel
from simple_module_core.permissions import PermissionCatalogue


@pytest.mark.parametrize("routes", ["", "orders.admin.views:router"])
def test_admin_surface_without_menu_or_permissions_warns(routes):
    class Orders(ModuleBase):
        meta = ModuleMeta(name="Orders", admin=AdminSurface(prefix="/admin/orders", routes=routes))

    results = ModuleDiagnostics()._check_views_without_menu([Orders()])
    assert len(results) == 1
    assert results[0].code == "SM019"
    assert results[0].level == DiagnosticLevel.WARNING
    assert "/admin/orders" in results[0].message


def test_legacy_admin_hook_without_menu_or_permissions_warns():
    class Orders(ModuleBase):
        meta = ModuleMeta(name="Orders", admin_view_prefix="/admin/orders")

        def register_admin_routes(self, admin_router):
            pass

    results = ModuleDiagnostics()._check_views_without_menu([Orders()])
    assert [result.code for result in results] == ["SM019"]
    assert "/admin/orders" in results[0].message


def test_legacy_admin_prefix_without_routes_stays_silent():
    class Orders(ModuleBase):
        meta = ModuleMeta(name="Orders", admin_view_prefix="/admin/orders")

    assert ModuleDiagnostics()._check_views_without_menu([Orders()]) == []


@pytest.mark.parametrize("visibility", ["menu", "permission_hook", "catalogue"])
def test_discoverable_admin_surface_stays_silent(visibility):
    class Permissions(PermissionCatalogue, group="Orders"):
        VIEW = "orders.view"

    class Orders(ModuleBase):
        meta = ModuleMeta(name="Orders", admin=AdminSurface(prefix="/admin/orders"))

    if visibility == "menu":
        Orders.register_menu_items = lambda self, registry: None
    elif visibility == "permission_hook":
        Orders.register_permissions = lambda self, registry: None
    else:
        Orders.permissions = Permissions

    assert ModuleDiagnostics()._check_views_without_menu([Orders()]) == []
