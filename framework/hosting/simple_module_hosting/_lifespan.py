"""The app's startup and shutdown sequence.

Split out of ``app_builder`` so that file stays focused on *wiring* — which
modules load, what middleware is installed, where routes mount — while this
one owns *when things happen* at run time.

Ordering here is load-bearing. Settings hydrate from the database before any
module's ``on_startup`` runs, so startup code reads DB-backed values rather
than pydantic defaults. Shutdown runs in reverse module order, mirroring
dependency direction, and disposes the engine last so a module's shutdown hook
can still reach the database.
"""

from __future__ import annotations

import logging
import os
import threading
import weakref
from collections.abc import AsyncGenerator, Callable, Sequence
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from simple_module_core.diagnostics._migration import MIGRATION_DRIFT_CODE
from simple_module_core.modules.module import ModuleBase
from simple_module_core.runtime.leases import (
    _add_lease_listener,
    _remove_lease_listener,
    get_leases,
)

from simple_module_hosting._deferred_startup import hydrate_settings_from_db
from simple_module_hosting._dev_boot import print_boot_diagnostics
from simple_module_hosting._fallback_routes import finalize_fallback_routes
from simple_module_hosting._route_guard import guard_included_routers
from simple_module_hosting._table_coverage import add_table_coverage
from simple_module_hosting.data_compatibility import check_data_compatibility
from simple_module_hosting.migrations import migration_problem, migration_status
from simple_module_hosting.setup_gate import is_first_run

logger = logging.getLogger(__name__)


_TRACKERS: set[weakref.ref[_LeaseTracker]] = set()
_LEASE_OWNERS: dict[int, int] = {}
_LEASE_OWNERS_LOCK = threading.Lock()


class _LeaseTracker:
    """Owns one reference per observed backend, shared across app lifespans."""

    def __init__(self, initial: object) -> None:
        self.lock = threading.Lock()
        self.tracked: list[object] = []
        self.seen: set[int] = set()
        _TRACKERS.add(weakref.ref(self, _TRACKERS.discard))
        self.track(initial)

    def track(self, backend: object) -> None:
        with self.lock:
            if id(backend) not in self.seen:
                self.tracked.append(backend)
                self.seen.add(id(backend))
                with _LEASE_OWNERS_LOCK:
                    _LEASE_OWNERS[id(backend)] = _LEASE_OWNERS.get(id(backend), 0) + 1

    def release(self) -> list[object]:
        """Return only backends whose final lifespan owner has exited."""
        with self.lock, _LEASE_OWNERS_LOCK:
            unowned = []
            for backend in self.tracked:
                remaining = _LEASE_OWNERS[id(backend)] - 1
                if remaining:
                    _LEASE_OWNERS[id(backend)] = remaining
                else:
                    del _LEASE_OWNERS[id(backend)]
                    unowned.append(backend)
            self.tracked.clear()
            self.seen.clear()
            return unowned

    def reset_after_fork(self) -> None:
        self.lock = threading.Lock()
        self.seen = {id(item) for item in self.tracked}


def _reset_forked_trackers() -> None:
    global _LEASE_OWNERS_LOCK
    _LEASE_OWNERS_LOCK = threading.Lock()
    # A vanished thread may have appended a backend before incrementing its count.
    _LEASE_OWNERS.clear()
    for ref in tuple(_TRACKERS):
        tracker = ref()
        if tracker is not None:
            tracker.reset_after_fork()
            for backend in tracker.tracked:
                _LEASE_OWNERS[id(backend)] = _LEASE_OWNERS.get(id(backend), 0) + 1


if hasattr(os, "register_at_fork"):
    os.register_at_fork(after_in_child=_reset_forked_trackers)


async def _shutdown_modules(
    app: FastAPI, modules: Sequence[ModuleBase], started: list[ModuleBase]
) -> None:
    started_ids = {id(mod) for mod in started}
    ordered = [mod for mod in modules if id(mod) in started_ids]
    async with AsyncExitStack() as cleanup:
        for mod in ordered:
            cleanup.push_async_callback(mod.on_shutdown, app)


async def _close_resource(resource: object) -> None:
    close = getattr(resource, "aclose", None)
    if close is not None:
        try:
            await close()
        except Exception as exc:
            logger.warning("Could not close %s (%s)", type(resource).__name__, type(exc).__name__)


async def _close_unless_reowned(backend: object) -> None:
    # Closing is async, so another lifespan may have started on this backend
    # after release(); it is then that lifespan's to close.
    with _LEASE_OWNERS_LOCK:
        if id(backend) in _LEASE_OWNERS:
            return
    await _close_resource(backend)


def build_lifespan(modules: Sequence, *, dispose_database: bool = True) -> Callable:
    """Return the ``lifespan`` context manager for an app over *modules*."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        async with AsyncExitStack() as cleanup:
            if dispose_database:
                cleanup.push_async_callback(app.state.sm.db.engine.dispose)
            tracker = _LeaseTracker(getattr(app.state, "_lease_backend", get_leases()))
            track = tracker.track

            async def close_backends() -> None:
                _remove_lease_listener(track)
                track(get_leases())
                async with AsyncExitStack() as resource_cleanup:
                    for backend in tracker.release():
                        resource_cleanup.push_async_callback(_close_unless_reowned, backend)
                    resource_cleanup.push_async_callback(
                        _close_resource, getattr(app.state.sm, "rate_limit_store", None)
                    )

            _add_lease_listener(track)
            track(get_leases())
            cleanup.push_async_callback(close_backends)
            started: list[ModuleBase] = []
            app.state.started_modules = started
            cleanup.push_async_callback(_shutdown_modules, app, modules, started)
            # Report first, decide second. On a genuinely fresh install a
            # behind-head database must still boot far enough to serve the wizard —
            # running the migrations is one of the things that wizard does, and
            # check_migrations' RuntimeError would make it unreachable. Anywhere
            # else the original behaviour stands: a schema the code does not match
            # fails the boot. See is_first_run for how the two are told apart.
            settings = getattr(app.state.sm, "settings", None)
            environment = getattr(settings, "environment", None)
            diagnostics = getattr(app.state.sm, "diagnostics", None)
            if environment == "development" and diagnostics is not None and diagnostics.results:
                await print_boot_diagnostics(diagnostics.results)
            migration = app.state.migration = await migration_status(app.state.sm.db.engine)
            if migration["is_current"] is None and environment == "development":
                logger.warning("%s: %s", MIGRATION_DRIFT_CODE, migration_problem(migration))
            elif not migration["is_current"] and not await is_first_run(app, migration):
                raise RuntimeError(migration_problem(migration))

            # Compatibility checks need the current schema. The setup gate
            # runs deferred checks once the schema is current.
            if migration["is_current"] and migration.get("current_revision") is not None:
                await check_data_compatibility(app, modules)
                await add_table_coverage(app, modules)
            else:
                app.state.deferred_data_compatibility = list(modules)

            await hydrate_settings_from_db(app)

            # Behind head on a first run the tables a module's on_startup reads do
            # not exist yet. Boot must still reach the wizard, so a hook that fails
            # here is deferred and replayed once the wizard has applied the
            # migrations (run_deferred_startup) rather than aborting the process.
            app.state.deferred_startup = []
            app.state.deferred_startup_complete = False
            tolerate = not migration["is_current"]
            for mod in modules:
                try:
                    await mod.on_startup(app)
                except Exception:
                    if not tolerate:
                        raise
                    logger.warning(
                        "on_startup of %s failed on an unmigrated database; "
                        "deferring it until the setup wizard has run the migrations",
                        mod.meta.name,
                        exc_info=True,
                    )
                    app.state.deferred_startup.append(mod)
                else:
                    started.append(mod)
            # Here rather than in create_app: the host includes its own routers
            # after create_app returns, and those should be guarded too.
            finalize_fallback_routes(app)
            guard_included_routers(app, warm=environment != "testing")
            yield

    return lifespan
