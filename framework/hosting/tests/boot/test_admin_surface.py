"""An admin surface mounts a router without adding authorization."""

import sys
from types import ModuleType

import httpx
from fastapi import APIRouter, Depends, FastAPI
from simple_module_core import AdminSurface, ModuleBase, ModuleMeta
from simple_module_hosting.auth.permissions import RequiresPermission
from simple_module_hosting.boot._module_routes import wire_module_routes


async def test_declared_router_keeps_explicit_guards_and_has_no_implicit_permission(monkeypatch):
    endpoints = ModuleType("surface_endpoints")
    endpoints.router = APIRouter()

    @endpoints.router.get("/open")
    async def open_page():
        return {"ok": True}

    @endpoints.router.get("/guarded", dependencies=[Depends(RequiresPermission("orders.view"))])
    async def guarded_page():
        return {"ok": True}

    monkeypatch.setitem(sys.modules, "surface_endpoints", endpoints)

    class OrdersModule(ModuleBase):
        meta = ModuleMeta(
            name="Orders",
            admin=AdminSurface(prefix="/admin/orders", routes="surface_endpoints:router"),
        )

        def register_routes(self, api_router, view_router):
            pass

    app = FastAPI()
    wire_module_routes(app, OrdersModule())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        assert (await c.get("/admin/orders/open")).status_code == 200
        assert (await c.get("/admin/orders/guarded")).status_code in {401, 403}


def test_manifest_exports_layout_and_prefix_without_changing_legacy_manifest(tmp_path):
    from simple_module_hosting.frontend.manifest import write_module_pages_manifest

    class OrdersModule(ModuleBase):
        meta = ModuleMeta(name="Orders", admin=AdminSurface(prefix="/admin/orders"))

    result = write_module_pages_manifest([OrdersModule()], tmp_path)
    generated = result["generated"].read_text()
    assert '"Orders": { prefix: "/admin/orders", layout: AdminSurfaceLayout0 }' in generated
    assert "@simple-module-py/ui/layouts/AdminLayout" in generated


def test_registration_scopes_defaults_and_preserves_existing_module_menus():
    from unittest.mock import MagicMock

    from api_tokens.module import ApiTokensModule
    from dashboard.module import DashboardModule
    from simple_module_core.web.menu import MenuRegistry, MenuSection
    from simple_module_hosting.boot._registrations import (
        RequestRegistries,
        run_module_registrations,
    )
    from tenants.module import TenantsModule
    from users.module import UsersModule

    registry = MenuRegistry()
    unrelated = MagicMock()
    run_module_registrations(
        [ApiTokensModule(), DashboardModule(), TenantsModule(), UsersModule()],
        app=unrelated,
        event_bus=unrelated,
        invalidation_bus=unrelated,
        menu_registry=registry,
        perm_registry=unrelated,
        ff_registry=unrelated,
        health_registry=unrelated,
        public_route_registry=unrelated,
        setup_registry=unrelated,
        design_pack_registry=unrelated,
        audit_link_registry=unrelated,
        csp_registry=unrelated,
        request_registries=RequestRegistries(),
    )
    admin_items = [i for i in registry.all_items if i.section == MenuSection.ADMIN_SIDEBAR]
    assert [(i.url, i.group, i.group_key, i.permissions, i.roles) for i in admin_items] == [
        ("/admin/users/", "Access", "ui.nav_groups.access", [], ["admin"]),
        ("/admin/tenants/", "Access", "ui.nav_groups.access", ["tenants.platform.view"], []),
        ("/admin/api-tokens/", "Access", "ui.nav_groups.access", ["api_tokens.manage"], []),
        ("/admin/doctor/", "System", "", [], ["admin"]),
    ]
    assert registry._admin_surface is None
