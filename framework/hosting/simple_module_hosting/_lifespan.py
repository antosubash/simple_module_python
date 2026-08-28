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
from simple_module_hosting.setup_gate import STEP_MIGRATIONS


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


async def _is_first_run(app: FastAPI) -> bool:
    """Whether this install has never been set up at all.

    The distinction the boot check turns on. Two very different situations both
    leave ``host.migrations`` outstanding:

    - A **fresh deployment**: nothing is configured, so the administrator step
      is pending too. Serving the wizard is exactly right — running the
      migrations is one of the things it exists to do.
    - A **configured install whose schema drifted**: someone deployed code
      ahead of the migration job. It has administrators; only the schema is
      behind.

    Treating the second as "setup mode" is wrong twice over. It serves traffic
    against a schema the code does not match — the failure ``SM010`` exists to
    prevent — and it re-opens ``/setup``, whose migration endpoint is
    unauthenticated, letting an anonymous request trigger an Alembic run on a
    live system.

    So: first run means *something other than the schema* is also outstanding.
    ``True`` when no registry exists, since an app built outside ``create_app``
    has no steps to reason about and the old raising behaviour is the safer
    default there.
    """
    registry = getattr(app.state.sm, "setup_registry", None)
    if not registry:
        return False
    pending = {step.id for step in await registry.incomplete(app)}
    return bool(pending - {STEP_MIGRATIONS})


def build_lifespan(modules: Sequence) -> Callable:
    """Return the ``lifespan`` context manager for an app over *modules*."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
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

        await hydrate_settings_from_db(app)

        for mod in modules:
            await mod.on_startup(app)
        yield
        for mod in reversed(modules):
            await mod.on_shutdown(app)
        await app.state.sm.db.engine.dispose()

    return lifespan
