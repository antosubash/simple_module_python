"""Datasets module definition.

Depends on ``FileStorage`` for bytes storage, ``BackgroundTasks`` for
the Celery pipeline the upload endpoint enqueues into, ``Permissions``
for the permission system, ``FeatureFlags`` for runtime toggles, and
``Settings`` for admin-configurable limits. ``register_settings`` here
runs after those, so every ``app.state.*`` slot is populated before any
Datasets request fires.
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, FastAPI
from simple_module_core.feature_flags import FeatureFlagDefinition, FeatureFlagRegistry
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.permissions import PermissionRegistry

from datasets import constants

if TYPE_CHECKING:
    from settings.contracts.registry import SettingDefinition


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
        # Plain users can browse the catalog and upload their own datasets;
        # edit/delete stay admin-only via the framework wildcard.
        registry.map_role(
            constants.ROLE_USER,
            list(constants.USER_ROLE_PERMISSIONS),
        )

    def register_feature_flags(self, registry: FeatureFlagRegistry) -> None:
        registry.add(
            FeatureFlagDefinition(
                name=constants.FLAG_AUTO_EXTRACT,
                description=(
                    "Enqueue the Celery metadata-extraction task on upload. "
                    "Turn off to skip the worker hop and leave rows as "
                    "``extraction_status=pending`` for manual review."
                ),
                default_enabled=True,
            )
        )
        registry.add(
            FeatureFlagDefinition(
                name=constants.FLAG_ALLOW_RASTER_UPLOADS,
                description=(
                    "Accept raster (GeoTIFF) uploads. Disable on instances "
                    "without ``rasterio`` installed to give users a clear "
                    "422 instead of a silent failed extraction."
                ),
                default_enabled=True,
            )
        )

    def locale_dirs(self) -> dict[str, Path]:
        base = Path(str(importlib.resources.files(__package__) / "locales"))
        return {constants.LOCALE_NAMESPACE: base}

    async def on_startup(self, app: FastAPI) -> None:
        """Register runtime-tunable settings with the ``settings`` module.

        Registered as ``on_startup`` (not in ``register_settings``) because
        the settings module's ``app.state.settings`` slot is only populated
        once its own ``register_settings`` has run — ``on_startup`` fires
        after every module's registration is done.
        """
        # The settings module may not be installed in every deployment —
        # treat its absence as a warn, not a crash.
        registry = getattr(getattr(app.state, "settings", None), "registry", None)
        if registry is None:
            return
        for definition in _setting_definitions():
            if definition.key in registry:
                continue
            registry.add(definition)


def _setting_definitions() -> list[SettingDefinition]:
    """Deferred import so the module still loads if ``settings`` is absent."""
    from settings.contracts.registry import SettingDefinition
    from settings.contracts.schemas import SettingValueType

    return [
        SettingDefinition(
            key=constants.SETTING_MAX_UPLOAD_MB,
            default=str(constants.DEFAULT_MAX_UPLOAD_MB),
            description=(
                "Per-dataset upload size cap in megabytes. Overrides the "
                "``SM_DATASETS_MAX_UPLOAD_MB`` env default at runtime."
            ),
            value_type=SettingValueType.INT,
        ),
        SettingDefinition(
            key=constants.SETTING_DEFAULT_KIND,
            default=constants.DatasetKind.OTHER,
            description=(
                "Dataset kind assigned when filename-based detection comes "
                "back as ``other``. Useful for instances that know they only "
                "ingest one kind (e.g. always ``vector_geojson``)."
            ),
        ),
    ]
