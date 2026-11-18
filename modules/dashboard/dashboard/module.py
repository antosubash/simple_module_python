"""Dashboard module definition."""

from __future__ import annotations

from simple_module_core import AdminSurface
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta

from dashboard.core.constants import Permissions

_URL_DASHBOARD = "/dashboard/"
_URL_DOCTOR = "/admin/doctor/"
_ICON_DASHBOARD = "home"
_ICON_DOCTOR = "stethoscope"


class DashboardModule(ModuleBase):
    # Administrative data: only admin (wildcard) or explicit grants; never
    # map user/tenant roles here, including single-tenant installs (#464).
    permissions = Permissions

    meta = ModuleMeta(
        name="Dashboard",
        route_prefix="/api/dashboard",
        view_prefix="/dashboard",
        # The dashboard itself is an app screen; Doctor is an admin one.
        admin=AdminSurface(
            prefix="/admin/doctor",
            routes="dashboard.web.endpoints.views:admin_router",
            menu_group="System",
        ),
        i18n_audience="admin",
    )

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label="Dashboard",
                label_key="dashboard.nav.dashboard",
                url=_URL_DASHBOARD,
                icon=_ICON_DASHBOARD,
                order=10,
                section=MenuSection.SIDEBAR,
            )
        )
        registry.add(
            MenuItem(
                label="Doctor",
                label_key="dashboard.nav.doctor",
                url=_URL_DOCTOR,
                icon=_ICON_DOCTOR,
                order=220,
                # Mirrors the view route's admin-only guard — without it the
                # entry shows for every signed-in account and 403s on click.
                roles=["admin"],
            )
        )
