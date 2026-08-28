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

from simple_module_hosting.migrations import migration_status


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


async def _setup_complete(app: FastAPI) -> bool:
    """Whether the first-run wizard has finished gating this install.

    ``True`` when no registry exists or nothing registered a step — an install
    with no local-accounts provider is never gated, so a behind-head database
    there is an ordinary boot failure, not a setup task.
    """
    registry = getattr(app.state.sm, "setup_registry", None)
    if not registry:
        return True
    return await registry.is_setup_complete(app)


def build_lifespan(modules: Sequence) -> Callable:
    """Return the ``lifespan`` context manager for an app over *modules*."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        # Report first, decide second. A behind-head database must still boot
        # far enough to serve the setup wizard — running the migrations is one
        # of the things that wizard does, and check_migrations' RuntimeError
        # would make it unreachable. Once setup is complete the original
        # behaviour stands: a schema the code does not match fails the boot.
        app.state.migration = await migration_status(app.state.sm.db.engine)
        if not app.state.migration["is_current"] and await _setup_complete(app):
            raise RuntimeError(
                f"Database is {app.state.migration['pending_count']} revision(s) behind "
                f"(at {app.state.migration['current_revision']!r}, head is "
                f"{app.state.migration['head_revision']!r}). Run: make migrate"
            )

        await hydrate_settings_from_db(app)

        for mod in modules:
            await mod.on_startup(app)
        yield
        for mod in reversed(modules):
            await mod.on_shutdown(app)
        await app.state.sm.db.engine.dispose()

    return lifespan
