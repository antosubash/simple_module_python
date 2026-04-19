"""Datasets module definition."""

from __future__ import annotations

import importlib.resources
from pathlib import Path

from fastapi import APIRouter, FastAPI
from simple_module_core.health import HealthCheck, HealthCheckResult, HealthRegistry, HealthStatus
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.permissions import PermissionRegistry

from datasets.storage import LocalDatasetStorage


class DatasetsModule(ModuleBase):
    meta = ModuleMeta(
        name="Datasets",
        route_prefix="/api/datasets",
        view_prefix="/datasets",
    )

    def __init__(self) -> None:
        self._storage: LocalDatasetStorage | None = None

    def register_settings(self, app: FastAPI) -> None:
        from datasets.services import DatasetsServices
        from datasets.settings import DatasetsSettings

        settings = DatasetsSettings()
        storage = LocalDatasetStorage(Path(settings.storage_dir))
        app.state.datasets = DatasetsServices(settings=settings, storage=storage)
        self._storage = storage

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

    def register_health_checks(self, registry: HealthRegistry) -> None:
        storage = self._storage

        async def check_storage() -> HealthCheckResult:
            if storage is None:
                return HealthCheckResult(
                    status=HealthStatus.UNHEALTHY,
                    detail="Storage backend not initialised",
                )
            if not storage.is_writable():
                return HealthCheckResult(
                    status=HealthStatus.UNHEALTHY,
                    detail=f"Storage directory not writable: {storage.root}",
                )
            return HealthCheckResult(status=HealthStatus.HEALTHY)

        registry.add(HealthCheck(name="datasets.storage", check=check_storage))

    def locale_dirs(self) -> dict[str, Path]:
        base = Path(str(importlib.resources.files(__package__) / "locales"))
        return {"datasets": base}

    async def on_startup(self, app: FastAPI) -> None:
        # Make sure the storage directory exists once the app is fully booted
        # so the health check has a writable target on first request.
        app.state.datasets.storage.ensure_root()
