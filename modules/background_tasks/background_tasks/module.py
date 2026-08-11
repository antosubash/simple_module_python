"""BackgroundTasks module definition."""

from __future__ import annotations

import importlib.resources
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter
from simple_module_core.audit_links import AuditLinkRegistry
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.permissions import PermissionRegistry

from background_tasks.constants import (
    _MODULE_SETTINGS,
    _MODULE_USERS,
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
        depends_on=[_MODULE_USERS, _MODULE_SETTINGS],
        i18n_audience="admin",
    )

    def register_settings(self, app: FastAPI) -> None:
        import importlib

        from background_tasks.services import BackgroundTasksServices
        from background_tasks.settings import BackgroundTasksSettings

        # SM009 is AST-based: a static `from settings.registration import ...`
        # from a module helper is fine (plugin→plugin), but we resolve via
        # importlib here to match the convention used framework-side and to
        # keep the dependency direction one-way explicit.
        register_module_settings = importlib.import_module(
            "settings.registration"
        ).register_module_settings

        register_module_settings(
            app,
            "background_tasks",
            BackgroundTasksSettings,
            lambda s: BackgroundTasksServices(settings=s),
        )

    def register_permissions(self, registry: PermissionRegistry) -> None:
        registry.add_group(PERM_GROUP, [PERM_VIEW, PERM_MANAGE])

    def register_audit_links(self, registry: AuditLinkRegistry) -> None:
        from simple_module_core.audit_links import AuditLink

        from background_tasks.models import TaskExecution

        registry.register(
            AuditLink(
                # Class name, not __tablename__ — see AuditLink.entity_type.
                entity_type=TaskExecution.__name__,
                url_template=f"{VIEW_PREFIX}/{{id}}",
                label="Task execution",
            )
        )

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label=MENU_LABEL,
                url=f"{VIEW_PREFIX}/",
                icon=MENU_ICON,
                order=MENU_ORDER,
                section=MenuSection.SIDEBAR,
                roles=["admin"],
                group="Administration",
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
        from background_tasks.sync_db import set_database_url

        services = app.state.background_tasks
        # Pin the sync engine to the same URL the host's async settings
        # resolved — pydantic-settings reads ``.env`` but never propagates
        # to ``os.environ``, so signals would otherwise fall back to the
        # SQLite default and silently drop ``TaskExecution`` rows.
        set_database_url(app.state.sm.settings.database_url)
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
