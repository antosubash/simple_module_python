"""Datasets module definition.

Depends on ``FileStorage`` for bytes storage and ``BackgroundTasks`` for
the Celery pipeline the upload endpoint enqueues into. ``register_settings``
here runs after both of theirs, so by the time any Datasets request fires,
``app.state.file_storage.backend`` and ``app.state.background_tasks.celery``
are both populated.
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path

from fastapi import APIRouter, FastAPI
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.permissions import PermissionRegistry

from datasets import constants


class DatasetsModule(ModuleBase):
    meta = ModuleMeta(
        name=constants.MODULE_PASCAL,
        route_prefix=constants.ROUTE_PREFIX_API,
        view_prefix=constants.ROUTE_PREFIX_VIEW,
        depends_on=[constants.MODULE_FILE_STORAGE, constants.MODULE_BACKGROUND_TASKS],
    )

    def register_settings(self, app: FastAPI) -> None:
        from datasets.services import DatasetsServices
        from datasets.settings import DatasetsSettings

        app.state.datasets = DatasetsServices(settings=DatasetsSettings())

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from datasets.endpoints.api import router as api
        from datasets.endpoints.views import router as views

        api_router.include_router(api)
        view_router.include_router(views)

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label=constants.MENU_LABEL,
                url=constants.ROUTE_PREFIX_VIEW,
                icon=constants.MENU_ICON,
                order=constants.MENU_ORDER,
                section=MenuSection.SIDEBAR,
            )
        )

    def register_permissions(self, registry: PermissionRegistry) -> None:
        registry.add_group(
            constants.PERMISSION_GROUP,
            list(constants.ALL_PERMISSIONS),
        )

    def locale_dirs(self) -> dict[str, Path]:
        base = Path(str(importlib.resources.files(__package__) / "locales"))
        return {constants.LOCALE_NAMESPACE: base}
