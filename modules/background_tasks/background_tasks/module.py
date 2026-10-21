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
        import asyncio

        from background_tasks.celery_app import build_celery
        from background_tasks.log_sink import install_log_sink
        from background_tasks.signals import bind_event_bus
        from background_tasks.sync_db import set_database_url
        from background_tasks.tenant_context import set_default_tenant

        services = app.state.background_tasks
        # Pin the sync engine to the same URL the host's async settings
        # resolved — pydantic-settings reads ``.env`` but never propagates
        # to ``os.environ``, so signals would otherwise fall back to the
        # SQLite default and silently drop ``TaskExecution`` rows.
        host = app.state.sm.settings
        multi = bool(getattr(host, "multi_tenant", False))
        default_tenant = None if multi else getattr(host, "default_tenant", "") or None
        set_database_url(host.database_url, tenant_strict=multi, default_tenant=default_tenant)
        set_default_tenant(default_tenant)
        # build_celery imports `signals` for side effects and runs
        # `autodiscover_tasks` across every installed module.
        services.celery = build_celery(services.settings)
        # Let signal handlers hop onto the API loop to publish events.
        # In a standalone worker process this bind never runs, so signals
        # stay a silent no-op — that's the documented cross-process limit.
        bind_event_bus(app.state.sm.event_bus, asyncio.get_running_loop())
        self._install_durable_transport(app)
        install_log_sink(services.settings)
        logger.info(
            "BackgroundTasks: Celery app ready (broker=%s, queue=%s)",
            services.settings.broker_url,
            services.settings.task_default_queue,
        )

        await self._start_invalidation_transport(app)

        # Registered here, not in register_health_checks: the Celery app does
        # not exist until this hook builds it, and the check must follow later
        # settings changes rather than pinning the boot-time instance.
        from simple_module_core.health import HealthCheck

        from background_tasks.health import CHECK_REDIS, build_redis_check

        app.state.sm.health_registry.add(
            HealthCheck(
                name=CHECK_REDIS,
                check=build_redis_check(app),
                module=self.meta.name,
                # On demand only, like the mailer and storage checks. An
                # earlier version had this on the readiness probe, reasoning
                # that Redis is infrastructure this app owns rather than a
                # third party. That conflates two different questions: whether
                # this process can serve requests, and whether the system is
                # fully functional. Failing readiness pulls the web tier out of
                # the load balancer, turning "background jobs are backed up"
                # into "the site is down" — and it made /health/ready report
                # unhealthy on every deployment without Redis, which CI caught.
                # The wizard's connection step and the settings screen's "Test
                # connection" both run it explicitly, which is what it is for.
                probe=False,
            )
        )

    @staticmethod
    def _install_durable_transport(app: FastAPI) -> None:
        """Make ``bus.publish_durable`` write to this module's outbox (GH #459)."""
        from background_tasks.outbox_transport import OutboxTransport
        from background_tasks.outbox_worker import use_bus

        bus = app.state.sm.event_bus
        bus.durable_transport = OutboxTransport(
            services=app.state.background_tasks, bus=bus, db_state=app.state.sm.db
        )
        # An eager in-process dispatch delivers with the app's bus, which already
        # carries every module's durable subscriptions.
        use_bus(bus)

    @staticmethod
    async def _start_invalidation_transport(app: FastAPI) -> None:
        """Hand the framework bus the Redis connection this module configures.

        The transport is installed here rather than in a registration hook
        because it needs a running event loop for its listener task, and it is
        installed by *this* module because it owns the Redis URL — a cache-owning
        module opening its own connection is the duplication GH #318 exists to
        avoid.

        A worker process that runs Celery without the FastAPI app never reaches
        this, so it publishes nothing and hears nothing. That is the same
        documented cross-process limit as ``bind_event_bus`` above: a task that
        invalidates a cache should do it through an API call or accept the TTL.
        """
        from background_tasks.invalidation import RedisInvalidationTransport

        services = app.state.background_tasks
        s = services.settings
        if not s.broadcast_invalidations:
            logger.info(
                "BackgroundTasks: cross-worker cache invalidation disabled "
                "(broadcast_invalidations=false) — per-process caches expire on their own TTL"
            )
            return

        bus = app.state.sm.invalidation
        transport = RedisInvalidationTransport(bus, s.broker_url, s.invalidation_channel)
        await transport.start()
        bus.set_transport(transport)
        services.invalidation_transport = transport
        logger.info(
            "BackgroundTasks: invalidation transport on %r for channel(s) %s",
            s.invalidation_channel,
            ", ".join(bus.channels) or "(none subscribed)",
        )

    async def on_shutdown(self, app: FastAPI) -> None:
        from background_tasks.log_sink import uninstall_log_sink
        from background_tasks.outbox_worker import reset_worker_state
        from background_tasks.signals import unbind_event_bus
        from background_tasks.sync_db import dispose_sync_engine

        bus = getattr(app.state.sm, "event_bus", None)
        if bus is not None:
            drain = getattr(bus.durable_transport, "drain", None)
            if drain is not None:
                # Eager deliveries still running on this loop.
                await drain()
            bus.durable_transport = None
        reset_worker_state()
        services = app.state.background_tasks
        if services.invalidation_transport is not None:
            app.state.sm.invalidation.clear_transport()
            await services.invalidation_transport.stop()
            services.invalidation_transport = None
        if services.celery is not None:
            services.celery.close()
        unbind_event_bus()
        # Before the engine goes: the final flush still needs it.
        uninstall_log_sink()
        dispose_sync_engine()
