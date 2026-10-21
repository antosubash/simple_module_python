"""What the outbox Celery tasks need in a worker process: an async DB and a bus.

**Database.** Durable handlers take an ``AsyncSession`` (``ctx.db``), the same
kind request code uses, so module service code runs unchanged. Celery tasks are
synchronous, so each dispatch runs on the calling thread's long-lived outbox
event loop (:mod:`.outbox_loop`), and the engine — built once per loop from the
URL :mod:`.sync_db` was pinned to — keeps a small connection pool on that loop.
Under the ``threads`` pool every Celery thread therefore has its own loop and
engine, with its own configurable worker pool per thread.
Its session class gets the framework's entity listeners and the host's tenancy
policy, like the sync engine's.

**Bus.** A worker never builds the app, so it builds its own ``EventBus`` once
per process by calling every installed module's
``register_event_handlers(bus, None)``. That is where durable subscriptions
come from. It carries a :class:`~.outbox_transport.WorkerOutboxTransport`, so
a durable handler can itself ``publish_durable`` through ``ctx.db``. In the web
process ``on_startup`` hands over the app's own bus instead, which already has
both.
"""

from __future__ import annotations

import inspect
import logging
import threading
from typing import Any

from simple_module_core.events import EventBus
from simple_module_db import init_db
from simple_module_db.listeners import attach_session_listeners
from simple_module_db.query_filter import bind_engine_policy
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from background_tasks import sync_db
from background_tasks.constants import MODULE_NAME
from background_tasks.outbox_claim import OutboxPolicy
from background_tasks.outbox_dispatch import dispatch
from background_tasks.outbox_loop import run_on_worker_loop, stop_worker_loop, worker_loop_cache
from background_tasks.outbox_transport import WorkerOutboxTransport
from background_tasks.settings import BackgroundTasksSettings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_ENGINE_KEY = "outbox_worker_engine"
_bus: EventBus | None = None
_bus_override: EventBus | None = None


def worker_session_factory() -> async_sessionmaker[Any]:
    """The calling thread's async session factory on the worker's database.

    Cached on the thread's outbox loop: its pooled connections can only be
    used there, and :func:`run_dispatch` runs on that same loop.
    """
    url = sync_db.async_database_url()
    policy = sync_db.engine_tenancy()
    options = sync_db.database_options()
    key = (url, policy.tenant_strict, policy.default_tenant_id, tuple(sorted(options.items())))
    cache = worker_loop_cache()
    cached: tuple[Any, async_sessionmaker[Any], AsyncEngine] | None = cache.get(_ENGINE_KEY)
    if cached is not None and cached[0] == key:
        return cached[1]
    if cached is not None:
        _dispose_soon(cached[2])
    # Each outbox thread uses the same configured pool limits as sync workers.
    state = init_db(url, **({"pool_size": 2, "max_overflow": 3} | options))
    attach_session_listeners(state.sync_session_class)
    bind_engine_policy(state.engine.sync_engine, policy)
    cache[_ENGINE_KEY] = (key, state.session_factory, state.engine)
    return state.session_factory


def _dispose_soon(engine: AsyncEngine) -> None:
    try:
        run_on_worker_loop(engine.dispose)
    except Exception:
        logger.warning("outbox: disposing a reconfigured worker engine failed", exc_info=True)


async def _dispose_cached(cache: dict[str, Any]) -> None:
    cached = cache.pop(_ENGINE_KEY, None)
    if cached is not None:
        await cached[2].dispose()


def use_bus(bus: EventBus | None) -> None:
    """Dispatch with *bus* (the web app's own) instead of building one; ``None`` clears."""
    global _bus_override
    _bus_override = bus


def _register(module: Any, bus: EventBus) -> None:
    hook = module.register_event_handlers
    params = inspect.signature(hook).parameters
    accepts_app = "app" in params or any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()
    )
    if accepts_app:
        hook(bus, app=None)
    else:
        hook(bus)


def build_worker_bus() -> EventBus:
    """An ``EventBus`` carrying every installed module's subscriptions."""
    from simple_module_core.discovery import discover_modules, topological_sort

    bus = EventBus()
    bus.durable_transport = WorkerOutboxTransport()
    # Lenient on purpose: the worker delivers whatever is installed, and a
    # module set the web process refuses is reported there, not here.
    for module in topological_sort(discover_modules()):
        try:
            _register(module, bus)
        except Exception:
            # One module's handler wiring needing the app must not stop every
            # other module's durable events from being delivered. Logged once
            # per worker process (the bus is built once).
            logger.exception(
                "outbox.worker_bus: %s.register_event_handlers failed without an app; "
                "durable handlers it subscribes after that point are unknown to this "
                "worker, and their events will retry until they go dead. Subscribe "
                "durable handlers before anything that needs the app.",
                module.meta.name,
            )
    logger.info("outbox.worker_bus: %d durable subscription(s)", len(bus.durable))
    return bus


def worker_bus() -> EventBus:
    global _bus
    if _bus_override is not None:
        return _bus_override
    with _lock:
        if _bus is None:
            _bus = build_worker_bus()
        return _bus


def reset_worker_state() -> None:
    """Forget the cached engines, bus and loops (tests, or after reconfiguring sync_db)."""
    global _bus, _bus_override
    with _lock:
        _bus = None
        _bus_override = None
    stop_worker_loop(_dispose_cached)


def load_policy() -> OutboxPolicy:
    """Outbox limits from DB-hydrated settings, env/defaults if the DB can't say."""
    from background_tasks.worker_settings import settings_for

    try:
        settings = settings_for(BackgroundTasksSettings, MODULE_NAME)
    except Exception:
        logger.warning("outbox: settings unreadable from the DB; using env/defaults")
        settings = BackgroundTasksSettings()
    return OutboxPolicy(
        max_attempts=settings.outbox_max_attempts,
        lease_seconds=settings.outbox_lease_seconds,
        handler_timeout_seconds=settings.outbox_handler_timeout_seconds,
    )


def run_dispatch(ids: list[str] | None) -> dict[str, int]:
    """Body of the ``dispatch_outbox`` (``ids``) and ``sweep_outbox`` (``None``) tasks."""
    policy = load_policy()
    factory = worker_session_factory()
    bus = worker_bus()
    result = run_on_worker_loop(lambda: dispatch(factory, bus, policy, ids=ids))
    summary = result.as_dict()
    if any(summary.values()):
        logger.info("outbox.dispatch %s", summary)
    return summary
