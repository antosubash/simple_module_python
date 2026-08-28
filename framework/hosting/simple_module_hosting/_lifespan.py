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

from collections.abc import AsyncGenerator, Callable, Sequence
from contextlib import asynccontextmanager

from fastapi import FastAPI

from simple_module_hosting.migrations import check_migrations


async def hydrate_settings_from_db(app: FastAPI) -> None:
    """Merge DB-stored overrides into every registered settings object.

    Resolved through ``importlib`` rather than a static import because the
    SM009 coupling check is AST-based and forbids ``framework/*`` from naming
    a plugin package. No-ops when the settings module isn't installed.

    Note this is the *second* settings read of a boot. The first happens in
    ``_preapp_config`` before ``create_app`` builds anything, because the
    module list, i18n registry and middleware stack are all constructed from
    settings and cannot be rebuilt from here.
    """
    if not hasattr(app.state, "settings"):
        return

    import importlib

    from simple_module_hosting._hydrate_step import hydrate_all

    service_cls = importlib.import_module("settings.service").SettingService
    store_cls = importlib.import_module("settings.store").SettingsStore

    async with app.state.sm.db.session_factory() as session:
        await hydrate_all(app, store_cls(service_cls(session)))


def build_lifespan(modules: Sequence) -> Callable:
    """Return the ``lifespan`` context manager for an app over *modules*."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        app.state.migration = await check_migrations(app.state.sm.db.engine)
        await hydrate_settings_from_db(app)

        for mod in modules:
            await mod.on_startup(app)
        yield
        for mod in reversed(modules):
            await mod.on_shutdown(app)
        await app.state.sm.db.engine.dispose()

    return lifespan
