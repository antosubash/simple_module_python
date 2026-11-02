"""Startup/shutdown wiring for the BackgroundTasks module.

``BackgroundTasksModule`` keeps the ``on_startup`` / ``on_shutdown`` hooks and
delegates here, so the module file stays a declaration of what the module
contributes and this file owns the order things are installed and torn down.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)


async def startup(app: FastAPI, module_name: str) -> None:
    """Build the Celery app, install signal handlers, hand-off to worker."""
    import asyncio

    from simple_module_hosting.log_sinks import redact

    from background_tasks.celery_app import build_celery
    from background_tasks.db_settings import worker_database_options
    from background_tasks.log_sink import install_log_sink
    from background_tasks.signals import bind_event_bus
    from background_tasks.sync_db import configure_database, set_database_url
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
    configure_database(worker_database_options(host, services.settings))
    set_default_tenant(default_tenant)
    # build_celery imports `signals` for side effects and runs
    # `autodiscover_tasks` across every installed module.
    services.celery = build_celery(services.settings)
    # Let signal handlers hop onto the API loop to publish events.
    # In a standalone worker process this bind never runs, so signals
    # stay a silent no-op — that's the documented cross-process limit.
    bind_event_bus(app.state.sm.event_bus, asyncio.get_running_loop())
    install_durable_transport(app)
    install_log_sink(services.settings)
    logger.info(
        "BackgroundTasks: Celery app ready (broker=%s, queue=%s)",
        redact(services.settings.broker_url),
        services.settings.task_default_queue,
    )

    await start_invalidation_transport(app)

    # Registered here, not in register_health_checks: the Celery app does
    # not exist until this hook builds it, and the check must follow later
    # settings changes rather than pinning the boot-time instance.
    from simple_module_core.health import HealthCheck

    from background_tasks.health import CHECK_REDIS, build_redis_check

    app.state.sm.health_registry.add(
        HealthCheck(
            name=CHECK_REDIS,
            check=build_redis_check(app),
            module=module_name,
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


def install_durable_transport(app: FastAPI) -> None:
    """Make ``bus.publish_durable`` write to this module's outbox (GH #459)."""
    from background_tasks.constants import OutboxMode
    from background_tasks.outbox_sweep import start_sweep
    from background_tasks.outbox_transport import OutboxTransport
    from background_tasks.outbox_worker import use_bus

    bus = app.state.sm.event_bus
    services = app.state.background_tasks
    mode = (
        OutboxMode.INPROCESS
        if services.celery.conf.task_always_eager
        else OutboxMode(services.settings.outbox_mode)
    )
    transport = OutboxTransport(services=services, bus=bus, db_state=app.state.sm.db, mode=mode)
    bus.durable_transport = transport
    if mode == OutboxMode.INPROCESS:
        start_sweep(services, app.state.sm.db.session_factory, bus, transport.policy)
    # An eager in-process dispatch delivers with the app's bus, which already
    # carries every module's durable subscriptions.
    use_bus(bus)


async def start_invalidation_transport(app: FastAPI) -> None:
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


async def shutdown(app: FastAPI) -> None:
    from background_tasks.log_sink import uninstall_log_sink
    from background_tasks.outbox_sweep import stop_sweep
    from background_tasks.outbox_worker import reset_worker_state
    from background_tasks.signals import unbind_event_bus
    from background_tasks.sync_db import dispose_sync_engine

    await stop_sweep(app.state.background_tasks)
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
