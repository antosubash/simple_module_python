"""Datasets module definition.

Depends on ``FileStorage`` for bytes storage. ``register_settings`` here
runs after file_storage's, so by the time any dataset endpoint fires,
``app.state.file_storage.backend`` is guaranteed to be initialised.
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path

from fastapi import APIRouter, FastAPI
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.permissions import PermissionRegistry


class DatasetsModule(ModuleBase):
    meta = ModuleMeta(
        name="Datasets",
        route_prefix="/api/datasets",
        view_prefix="/datasets",
        # ``FileStorage`` owns the byte-storage backend; ``BackgroundTasks``
        # owns the Celery app the upload endpoint enqueues into. Both must
        # have finished ``on_startup`` before any Datasets request fires.
        depends_on=["FileStorage", "BackgroundTasks"],
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
                label="Datasets",
                url="/datasets",
                icon="layers",
                order=40,
                section=MenuSection.SIDEBAR,
            )
        )

    def register_permissions(self, registry: PermissionRegistry) -> None:
        registry.add_group(
            "Datasets",
            [
                "datasets.view",
                "datasets.upload",
                "datasets.edit",
                "datasets.delete",
            ],
        )

    def locale_dirs(self) -> dict[str, Path]:
        base = Path(str(importlib.resources.files(__package__) / "locales"))
        return {"datasets": base}
