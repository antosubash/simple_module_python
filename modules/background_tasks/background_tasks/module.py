"""BackgroundTasks module definition."""

from __future__ import annotations

import importlib.resources
import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter
from simple_module_core.audit_links import AuditLinkRegistry
from simple_module_core.menu import MenuItem, MenuRegistry, MenuSection
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.module_settings import register_module_settings
from simple_module_core.permissions import PermissionRegistry

from background_tasks.constants import (
    _MODULE_SETTINGS,
    API_PREFIX,
    LOGS_MENU_ICON,
    LOGS_MENU_LABEL,
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
    from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger(__name__)


async def _resolve_execution_labels(db: AsyncSession, ids: list[str]) -> dict[str, str]:
    """Name an execution row by the task it ran.

    An execution id is a uuid nobody recognises; "files.generate_thumbnail" is
    the name the whole rest of the module — tiles, filters, detail title —
    already uses for the same row.
    """
    from sqlalchemy import select

    from background_tasks.models import TaskExecution

    parsed: dict[uuid.UUID, str] = {}
    for raw in ids:
        try:
            parsed[uuid.UUID(raw)] = raw
        except (ValueError, AttributeError, TypeError):
            continue
    if not parsed:
        return {}
    rows = (
        await db.execute(
            select(TaskExecution.id, TaskExecution.task_name).where(
                TaskExecution.id.in_(list(parsed))
            )
        )
    ).all()
    return {parsed.get(row_id, str(row_id)): name for row_id, name in rows}


class BackgroundTasksModule(ModuleBase):
    """Celery + Redis task queue with an admin UI for retrying failed/stuck tasks."""

    meta = ModuleMeta(
        name=MODULE_DISPLAY_NAME,
        route_prefix=API_PREFIX,
        view_prefix=VIEW_PREFIX,
        optional_depends_on=[_MODULE_SETTINGS],
        i18n_audience="admin",
    )

    def register_settings(self, app: FastAPI) -> None:
        from background_tasks.services import BackgroundTasksServices
        from background_tasks.settings import BackgroundTasksSettings

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
            AuditLink.for_model(
                TaskExecution,
                url_template=f"{VIEW_PREFIX}/{{id}}",
                label="Task execution",
                label_key="background_tasks.audit.task_execution",
                label_resolver=_resolve_execution_labels,
            )
        )

    def register_menu_items(self, registry: MenuRegistry) -> None:
        registry.add(
            MenuItem(
                label=MENU_LABEL,
                label_key="background_tasks.nav.background_tasks",
                url=f"{VIEW_PREFIX}/",
                icon=MENU_ICON,
                order=MENU_ORDER,
                section=MenuSection.ADMIN_SIDEBAR,
                roles=["admin"],
                group="System",
                group_key="ui.nav_groups.system",
            )
        )
        registry.add(
            MenuItem(
                label=LOGS_MENU_LABEL,
                label_key="background_tasks.nav.logs",
                url=f"{VIEW_PREFIX}/logs",
                icon=LOGS_MENU_ICON,
                order=MENU_ORDER + 1,
                section=MenuSection.ADMIN_SIDEBAR,
                roles=["admin"],
                group="System",
                group_key="ui.nav_groups.system",
            )
        )

    def register_routes(self, api_router: APIRouter, view_router: APIRouter) -> None:
        from background_tasks.endpoints.api_admin import router as api_admin
        from background_tasks.endpoints.api_status import router as api_status
        from background_tasks.endpoints.logs_api import router as logs_api
        from background_tasks.endpoints.logs_views import router as logs_views
        from background_tasks.endpoints.outbox_api import router as outbox_api
        from background_tasks.endpoints.outbox_views import router as outbox_views
        from background_tasks.endpoints.views import router as views

        api_router.include_router(api_admin)
        api_router.include_router(api_status)
        api_router.include_router(outbox_api)
        api_router.include_router(logs_api)
        # Before ``views``: its ``/{execution_id}`` would otherwise swallow ``/outbox``.
        view_router.include_router(outbox_views)
        view_router.include_router(logs_views)
        view_router.include_router(views)

    def locale_dirs(self) -> dict[str, Path]:
        base = Path(str(importlib.resources.files(__package__) / "locales"))
        return {MODULE_NAME: base}

    async def on_startup(self, app: FastAPI) -> None:
        """Build the Celery app, install signal handlers, hand-off to worker."""
        from background_tasks._lifecycle import startup

        await startup(app, self.meta.name)

    async def on_shutdown(self, app: FastAPI) -> None:
        from background_tasks._lifecycle import shutdown

        await shutdown(app)

    @staticmethod
    async def _start_invalidation_transport(app: FastAPI) -> None:
        from background_tasks._lifecycle import start_invalidation_transport

        await start_invalidation_transport(app)
