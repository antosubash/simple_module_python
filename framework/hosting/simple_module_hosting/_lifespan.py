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
from collections.abc import AsyncGenerator, Callable, Sequence
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from simple_module_core.diagnostics._migration import MIGRATION_DRIFT_CODE
from simple_module_core.leases import get_leases
from simple_module_core.module import ModuleBase

from simple_module_hosting._deferred_startup import hydrate_settings_from_db
from simple_module_hosting._dev_boot import print_boot_diagnostics
from simple_module_hosting._fallback_routes import finalize_fallback_routes
from simple_module_hosting._route_guard import guard_included_routers
from simple_module_hosting._table_coverage import add_table_coverage
from simple_module_hosting.data_compatibility import check_data_compatibility
from simple_module_hosting.migrations import migration_problem, migration_status
from simple_module_hosting.setup_gate import is_first_run

logger = logging.getLogger(__name__)


async def _shutdown_modules(app: FastAPI, started: list[ModuleBase]) -> None:
    async with AsyncExitStack() as cleanup:
        for mod in started:
            cleanup.push_async_callback(mod.on_shutdown, app)


async def _close_resource(resource: object) -> None:
    close = getattr(resource, "aclose", None)
    if close is not None:
        try:
            await close()
        except Exception as exc:
            logger.warning("Could not close %s (%s)", type(resource).__name__, type(exc).__name__)


def build_lifespan(modules: Sequence, *, dispose_database: bool = True) -> Callable:
    """Return the ``lifespan`` context manager for an app over *modules*."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        async with AsyncExitStack() as cleanup:
            if dispose_database:
                cleanup.push_async_callback(app.state.sm.db.engine.dispose)
            cleanup.push_async_callback(_close_resource, get_leases())
            cleanup.push_async_callback(
                _close_resource, getattr(app.state.sm, "rate_limit_store", None)
            )
            started: list[ModuleBase] = []
            app.state.started_modules = started
            cleanup.push_async_callback(_shutdown_modules, app, started)
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
