"""file_storage module — pluggable object storage with filesystem + S3 backends."""

from __future__ import annotations

import importlib.resources
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter
from simple_module_core.feature_flags import FeatureFlagDefinition, FeatureFlagRegistry
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.permissions import PermissionRegistry

from file_storage import constants

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)


class FileStorageModule(ModuleBase):
    meta = ModuleMeta(
        name=constants.MODULE_PASCAL,
        route_prefix=constants.ROUTE_PREFIX_API,
        view_prefix=constants.ROUTE_PREFIX_VIEW,
    )

    def register_settings(self, app: FastAPI) -> None:
        from file_storage.backends import build_backend
        from file_storage.services import FileStorageServices
        from file_storage.settings import FileStorageSettings

        settings = FileStorageSettings()
        backend = build_backend(settings)
        app.state.file_storage = FileStorageServices(settings=settings, backend=backend)

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from file_storage.endpoints.api import router as api
        from file_storage.endpoints.views import router as views

        api_router.include_router(api)
        view_router.include_router(views)

    def register_permissions(self, registry: PermissionRegistry) -> None:
        registry.add_group(
            constants.MODULE_DISPLAY_NAME,
            [
                constants.Permission.UPLOAD,
                constants.Permission.DOWNLOAD,
                constants.Permission.DELETE,
                constants.Permission.MANAGE,
            ],
        )
        registry.map_role(
            constants.USER_ROLE,
            [
                constants.Permission.UPLOAD,
                constants.Permission.DOWNLOAD,
                constants.Permission.DELETE,
            ],
        )

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label=constants.MODULE_DISPLAY_NAME,
                url=constants.ROUTE_PREFIX_VIEW,
                icon=constants.MENU_ICON,
                order=constants.MENU_ORDER,
                section=MenuSection.SIDEBAR,
                roles=list(constants.MENU_ROLES),
            )
        )

    def register_feature_flags(self, registry: FeatureFlagRegistry) -> None:
        registry.add(
            FeatureFlagDefinition(
                name=constants.FeatureFlag.PUBLIC_UPLOADS,
                description="Allow unauthenticated uploads (future).",
                default_enabled=False,
            )
        )

    def locale_dirs(self) -> dict[str, Path]:
        base = Path(str(importlib.resources.files(__package__) / "locales"))
        return {constants.LOCALE_NAMESPACE: base}

    async def on_startup(self, app: FastAPI) -> None:
        """Ensure the filesystem backend's root exists; probe S3 bucket reachability."""
        services = app.state.file_storage
        settings = services.settings
        if settings.backend == constants.BackendId.FILESYSTEM:
            root = settings.resolved_fs_root()
            root.mkdir(parents=True, exist_ok=True)
            logger.info("file_storage filesystem backend ready at %s", root)
        elif settings.backend == constants.BackendId.S3:
            logger.info(
                "file_storage S3 backend configured for bucket=%s region=%s endpoint=%s",
                settings.s3_bucket,
                settings.s3_region,
                settings.s3_endpoint_url or "(default)",
            )
