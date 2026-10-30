"""Settings hydration and deferred startup replay, independent of setup gates."""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI
from simple_module_core.app_state import get_deferred_startup, get_deferred_startup_lock
from simple_module_core.module_settings import get_module_settings_registry
from simple_module_db.stored_settings import SessionOverrideSource, settings_table_exists

from simple_module_hosting._hydrate_step import hydrate_all

logger = logging.getLogger(__name__)


async def hydrate_settings_from_db(app: FastAPI) -> None:
    """Merge DB-stored overrides into every registered settings object.

    Reads the settings table directly (``simple_module_db.stored_settings``),
    so it works whether or not the ``settings`` plugin is enabled (#500). A
    missing table is a fresh install: nothing is stored yet, so there is
    nothing to merge.

    Note this is the *second* settings read of a boot. The first happens in
    ``_preapp_config`` before ``create_app`` builds anything, because the
    module list, i18n registry and middleware stack are all constructed from
    settings and cannot be rebuilt from here.
    """
    if get_module_settings_registry(app) is None:
        return

    async with app.state.sm.db.session_factory() as session:
        if not await settings_table_exists(session):
            return
        await hydrate_all(app, SessionOverrideSource(session), session)


async def run_deferred_startup(app: FastAPI) -> None:
    """Replay the ``on_startup`` hooks that could not run on an unmigrated DB.

    Called from the wizard's migrations action and from the setup gate's
    schema re-check, so a worker that did not itself run the migrations (or an
    operator's out-of-band ``make migrate``) still finishes starting its
    modules. Serialised per app; a hook that fails again is logged and dropped
    rather than raised, because this runs after the migrations have already
    committed. Compatibility checks run first and still raise: an incompatible
    security state must keep the setup gate closed.
    """
    pending_checks = getattr(app.state, "deferred_data_compatibility", None)
    if pending_checks:
        from simple_module_hosting.data_compatibility import check_data_compatibility

        await check_data_compatibility(app, pending_checks)
        app.state.deferred_data_compatibility = []
    deferred = get_deferred_startup(app)
    if not deferred:
        return
    lock = get_deferred_startup_lock(app)
    if lock is None:  # no await between check and set, so this cannot race
        lock = app.state.deferred_startup_lock = asyncio.Lock()
    async with lock:
        if not deferred:
            return
        await hydrate_settings_from_db(app)
        while deferred:
            mod = deferred.pop(0)
            try:
                await mod.on_startup(app)
            except Exception:
                logger.exception("Deferred on_startup of %s failed after migrations", mod.meta.name)
