"""Admin presentation defaults preserve explicit choices and permission guards."""

from types import SimpleNamespace

import pytest
from simple_module_core import AdminSurface, ModuleMeta
from simple_module_core.web.menu import MenuItem, MenuRegistry, MenuSection


def test_surface_sets_legacy_prefix_and_rejects_conflicts():
    surface = AdminSurface(prefix="/admin/orders", menu_group="Access")
    assert ModuleMeta(name="Orders", admin=surface).admin_view_prefix == "/admin/orders"
    with pytest.raises(ValueError):
        ModuleMeta(name="Orders", admin=surface, admin_view_prefix="/admin/other")
    assert ModuleMeta(name="Old", admin_view_prefix="/admin/old").admin is None


@pytest.mark.parametrize("prefix", ["", "/", "admin/orders", "/admin/orders/"])
def test_surface_rejects_invalid_prefix(prefix):
    with pytest.raises(ValueError):
        AdminSurface(prefix=prefix)


def test_menu_defaults_are_scoped_by_module_and_path_and_keep_explicit_values():
    registry = MenuRegistry()
    surface = AdminSurface(
        prefix="/admin/orders", menu_group="Access", menu_group_key="ui.nav_groups.access"
    )
    with registry.admin_surface(surface):
        registry.add(
            MenuItem(label="Orders", url="/admin/orders/?a=1", permissions=["orders.view"])
        )
        registry.add_many(
            [
                MenuItem(label="Public", url="/orders"),
                MenuItem(label="Other", url="/admin/orders-extra"),
                MenuItem(
                    label="Explicit",
                    url="/admin/orders/edit",
                    section=MenuSection.SIDEBAR,
                    group="Custom",
                    group_key="custom",
                ),
            ]
        )
    registry.add(MenuItem(label="Unrelated", url="/admin/orders/"))
    items = registry.all_items
    assert items[0].section == MenuSection.ADMIN_SIDEBAR
    assert (items[0].group, items[0].group_key) == ("Access", "ui.nav_groups.access")
    assert items[0].permissions == ["orders.view"]
    assert [i.section for i in items[1:]] == [MenuSection.SIDEBAR] * 4
    assert (items[3].group, items[3].group_key) == ("Custom", "custom")
    visible = registry.get_for_user(is_authenticated=True, permissions=[])
    assert visible["adminSidebar"] == []


async def test_provider_keeps_its_surface_after_registration():
    registry = MenuRegistry()
    with registry.admin_surface(AdminSurface(prefix="/admin/orders", menu_group="Access")):
        registry.add_provider(lambda request: [MenuItem(label="Dynamic", url="/admin/orders/")])
    items = await registry.collect_provider_items(SimpleNamespace())
    assert items[0].section == MenuSection.ADMIN_SIDEBAR
    assert items[0].group == "Access"


def test_default_router_target_and_explicit_hook_override(monkeypatch):
    import sys
    from types import ModuleType

    from fastapi import APIRouter
    from fastapi.routing import iter_route_contexts
    from simple_module_core import ModuleBase

    endpoints = ModuleType("orders.web.endpoints.admin")
    endpoints.router = APIRouter()

    @endpoints.router.get("/probe")
    async def probe():
        pass

    monkeypatch.setitem(sys.modules, "orders.web.endpoints.admin", endpoints)

    class OrdersModule(ModuleBase):
        __module__ = "orders.module"
        meta = ModuleMeta(name="Orders", admin=AdminSurface(prefix="/admin/orders"))

    router = APIRouter()
    OrdersModule().register_admin_routes(router)
    assert "/probe" in {ctx.path for ctx in iter_route_contexts(router.routes)}

    class Custom(OrdersModule):
        def register_admin_routes(self, admin_router):
            admin_router.include_router(endpoints.router, prefix="/custom")

    router = APIRouter()
    Custom().register_admin_routes(router)
    assert "/custom/probe" in {ctx.path for ctx in iter_route_contexts(router.routes)}

    class Legacy(ModuleBase):
        meta = ModuleMeta(name="Legacy", admin_view_prefix="/admin/legacy")

    empty = APIRouter()
    Legacy().register_admin_routes(empty)
    assert not empty.routes
