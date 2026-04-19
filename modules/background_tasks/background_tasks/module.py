"""BackgroundTasks module definition."""

from __future__ import annotations

import importlib.resources
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.permissions import PermissionRegistry

from background_tasks.constants import (
    API_PREFIX,
    MENU_ICON,
    MENU_LABEL,
    MENU_ORDER,
    MODULE_DISPLAY_NAME,
    MODULE_NAME,
    PERM_GROUP,
    PERM_MANAGE,
    PERM_VIEW,
    VIEW_PREFIX,
)

if TYPE_CHECKING:
    from fastapi import FastAPI


logger = logging.getLogger(__name__)


class BackgroundTasksModule(ModuleBase):
    """Celery + Redis task queue with an admin UI for retrying failed/stuck tasks."""

    meta = ModuleMeta(
        name=MODULE_DISPLAY_NAME,
        route_prefix=API_PREFIX,
        view_prefix=VIEW_PREFIX,
        depends_on=["Users"],
    )

    def register_settings(self, app: FastAPI) -> None:
        from background_tasks.services import BackgroundTasksServices
        from background_tasks.settings import BackgroundTasksSettings

        services = BackgroundTasksServices(settings=BackgroundTasksSettings())
        app.state.background_tasks = services

    def register_permissions(self, registry: PermissionRegistry) -> None:
        registry.add_group(PERM_GROUP, [PERM_VIEW, PERM_MANAGE])

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label=MENU_LABEL,
                url=VIEW_PREFIX,
                icon=MENU_ICON,
                order=MENU_ORDER,
                section=MenuSection.SIDEBAR,
                roles=["admin"],
            )
        )

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from background_tasks.endpoints.api_admin import router as api_admin
        from background_tasks.endpoints.views import router as views

        api_router.include_router(api_admin)
        view_router.include_router(views)

    def locale_dirs(self) -> dict[str, Path]:
        base = Path(str(importlib.resources.files(__package__) / "locales"))
        return {MODULE_NAME: base}

    async def on_startup(self, app: FastAPI) -> None:
        """Build the Celery app, install signal handlers, hand-off to worker."""
        import asyncio

        from background_tasks.celery_app import build_celery
        from background_tasks.signals import bind_event_bus

        services = app.state.background_tasks
        # build_celery imports `signals` for side effects and runs
        # `autodiscover_tasks` across every installed module.
        services.celery = build_celery(services.settings)
        # Let signal handlers hop onto the API loop to publish events.
        # In a standalone worker process this bind never runs, so signals
        # stay a silent no-op — that's the documented cross-process limit.
        bind_event_bus(app.state.sm.event_bus, asyncio.get_running_loop())
        logger.info(
            "BackgroundTasks: Celery app ready (broker=%s, queue=%s)",
            services.settings.broker_url,
            services.settings.task_default_queue,
        )

    async def on_shutdown(self, app: FastAPI) -> None:
        from background_tasks.signals import unbind_event_bus
        from background_tasks.sync_db import dispose_sync_engine

        services = app.state.background_tasks
        if services.celery is not None:
            services.celery.close()
        unbind_event_bus()
        dispose_sync_engine()
