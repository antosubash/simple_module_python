"""file_storage module — pluggable object storage with filesystem + S3 backends."""

from __future__ import annotations

import importlib.resources
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter
from simple_module_core.events import EventBus
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
        # Needs Settings to run first so register_module_settings can reach
        # app.state.settings.module_registry during register_settings.
        depends_on=[constants._MODULE_SETTINGS],
    )

    def register_settings(self, app: FastAPI) -> None:
        import importlib

        from file_storage.services import FileStorageServices
        from file_storage.settings import FileStorageSettings

        # SM009 is AST-based: a static `from settings.registration import ...`
        # from a module helper is fine (plugin→plugin), but we resolve via
        # importlib here to match the convention used framework-side and to
        # keep the dependency direction one-way explicit.
        register_module_settings = importlib.import_module(
            "settings.registration"
        ).register_module_settings

        register_module_settings(
            app,
            "file_storage",
            FileStorageSettings,
            lambda s: FileStorageServices(settings=s),
        )

    def register_event_handlers(self, bus: EventBus, app: FastAPI | None = None) -> None:
        """Rebuild the storage backend when file_storage settings reload.

        The backend is a singleton built once in ``on_startup`` from the
        settings of that moment. Without this, editing the bucket, endpoint, or
        credentials in the settings UI would swap ``services.settings`` while
        every upload kept talking to the old provider until the next restart —
        the config would appear to save and silently do nothing.

        ``key_prefix`` needs no rebuild (the service reads it per request), but
        rebuilding on any change keeps the rule simple and construction is cheap.
        """
        if app is None:
            return

        import importlib

        settings_reloaded = importlib.import_module("settings.contracts.events").SettingsReloaded
        from file_storage.backends import build_backend

        async def _rebuild_backend(event: settings_reloaded) -> None:
            if event.package != constants.MODULE_NAME:
                return
            services = app.state.file_storage
            services.backend = build_backend(services.settings)
            logger.info(
                "file_storage backend rebuilt after settings change: %s",
                ", ".join(event.changed),
            )

        bus.subscribe(settings_reloaded, _rebuild_backend)

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
                url=f"{constants.ROUTE_PREFIX_VIEW}/",
                icon=constants.MENU_ICON,
                order=constants.MENU_ORDER,
                section=MenuSection.SIDEBAR,
                roles=list(constants.MENU_ROLES),
                group="Content",
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
        """Build the storage backend and probe its backing resource.

        Backend construction is deferred to ``on_startup`` so settings
        hydrated from the DB (between ``register_settings`` and here) are
        picked up — constructing in ``register_settings`` would bake in
        the pydantic defaults instead of the DB overrides.
        """
        from file_storage.backends import build_backend

        services = app.state.file_storage
        settings = services.settings
        services.backend = build_backend(settings)
        if settings.backend == constants.BackendId.FILESYSTEM:
            root = settings.resolved_fs_root()
            root.mkdir(parents=True, exist_ok=True)
            logger.info("file_storage filesystem backend ready at %s", root)
        elif settings.backend == constants.BackendId.S3:
            logger.info(
                "file_storage S3 backend configured for bucket=%s region=%s "
                "endpoint=%s addressing=%s prefix=%s",
                settings.s3_bucket,
                settings.s3_region,
                settings.s3_endpoint_url or "(default)",
                settings.s3_addressing_style,
                settings.key_prefix or "(bucket root)",
            )
