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
from simple_module_core.app_state import get_migration_status

from simple_module_hosting._deferred_startup import hydrate_settings_from_db
from simple_module_hosting._route_guard import guard_included_routers
from simple_module_hosting.data_compatibility import check_data_compatibility
from simple_module_hosting.migrations import migration_status

logger = logging.getLogger(__name__)


async def _is_first_run(app: FastAPI) -> bool:
    """True only when a registered setup flow has a never-migrated database.

    A pending administrator or other setup step on an installation with
    migration history is not evidence of a fresh install. Missing migration
    status also supplies no such evidence. A never-migrated database qualifies
    even when migrations are the only step, or another step would raise
    because its tables do not exist yet.
    """
    registry = getattr(app.state.sm, "setup_registry", None)
    migration = get_migration_status(app)
    return (
        bool(registry)
        and migration is not None
        and "current_revision" in migration
        and migration["current_revision"] is None
    )


def build_lifespan(modules: Sequence) -> Callable:
    """Return the ``lifespan`` context manager for an app over *modules*."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        async with AsyncExitStack() as cleanup:
            cleanup.push_async_callback(app.state.sm.db.engine.dispose)
            # Report first, decide second. On a genuinely fresh install a
            # behind-head database must still boot far enough to serve the wizard —
            # running the migrations is one of the things that wizard does, and
            # check_migrations' RuntimeError would make it unreachable. Anywhere
            # else the original behaviour stands: a schema the code does not match
            # fails the boot. See _is_first_run for why those two cases cannot be
            # told apart by "is setup complete".
            app.state.migration = await migration_status(app.state.sm.db.engine)
            if not app.state.migration["is_current"] and not await _is_first_run(app):
                raise RuntimeError(
                    f"Database is {app.state.migration['pending_count']} revision(s) behind "
                    f"(at {app.state.migration['current_revision']!r}, head is "
                    f"{app.state.migration['head_revision']!r}). Run: make migrate"
                )

            # Only a schema at head can be judged: a first run that stopped part-way
            # still has pre-upgrade columns, and refusing it would hide the wizard
            # that finishes the migration. The setup gate runs deferred checks
            # once the schema is current.
            migration = app.state.migration
            if migration["is_current"] and migration.get("current_revision") is not None:
                await check_data_compatibility(app, modules)
            else:
                app.state.deferred_data_compatibility = list(modules)

            await hydrate_settings_from_db(app)

            # Behind head on a first run the tables a module's on_startup reads do
            # not exist yet. Boot must still reach the wizard, so a hook that fails
            # here is deferred and replayed once the wizard has applied the
            # migrations (run_deferred_startup) rather than aborting the process.
            app.state.deferred_startup = []
            tolerate = not app.state.migration["is_current"]
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
                cleanup.push_async_callback(mod.on_shutdown, app)
            # Here rather than in create_app: the host includes its own routers
            # after create_app returns, and those should be guarded too.
            settings = getattr(app.state.sm, "settings", None)
            guard_included_routers(app, warm=getattr(settings, "environment", None) != "testing")
            yield

    return lifespan
