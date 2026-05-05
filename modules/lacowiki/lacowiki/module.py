"""LacoWiki module — migration wireframes for the LacoWiki rewrite."""

from __future__ import annotations

import importlib.resources
from pathlib import Path

from fastapi import APIRouter
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta

_MODULE_USERS = "Users"
_ICON_DEFAULT = "layout-grid"


class LacoWikiModule(ModuleBase):
    meta = ModuleMeta(
        name="LacoWiki",
        route_prefix="/api/lacowiki",
        view_prefix="/lacowiki",
        depends_on=[_MODULE_USERS],
    )

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from lacowiki.endpoints.views import router as views

        view_router.include_router(views)

    def register_menu_items(self, registry: MenuRegistry) -> None:
        items = [
            ("Datasets", "/lacowiki/datasets", 20),
            ("Legends", "/lacowiki/legends", 21),
            ("Sampling", "/lacowiki/sampling", 22),
            ("Validation", "/lacowiki/validation", 23),
            ("Reports", "/lacowiki/reports", 24),
            ("LacoWiki", "/lacowiki/", 19),
        ]
        for label, url, order in items:
            registry.add(
                MenuItem(
                    label=label,
                    url=url,
                    icon=_ICON_DEFAULT,
                    order=order,
                    section=MenuSection.SIDEBAR,
                )
            )

    def locale_dirs(self) -> dict[str, Path]:
        return {"lacowiki": Path(str(importlib.resources.files(__package__) / "locales"))}
