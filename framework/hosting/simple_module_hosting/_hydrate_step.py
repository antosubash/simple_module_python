"""Hydrate every registered module's settings from the DB at lifespan start.

Runs before any module ``on_startup`` hook so startup code sees DB-backed
values. ``importlib`` is used to resolve plugin names lazily so the
framework→plugin AST check (SM009) stays clean.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

from fastapi import FastAPI

logger = logging.getLogger(__name__)

_MODULE_PACKAGE = "settings"


async def hydrate_all(app: FastAPI, store: Any, session: Any = None) -> None:
    """Resolve every registered module's settings from the DB.

    ``hydrate_settings`` is already lenient per field: a stored value that no
    longer validates is dropped and the module keeps its other overrides. What
    still raises here is a failed *read*, or a cross-field rule that names no
    stored field (declare ``RELATED_FIELDS_CTX`` to make it droppable); that
    module keeps the settings object it had and the loop carries on.

    ``session`` is the one ``store`` reads through. A failed query leaves a
    Postgres transaction aborted, and every later module's read on the same
    session would then fail too, so it is rolled back before moving on.
    """
    settings_services = getattr(app.state, _MODULE_PACKAGE, None)
    if settings_services is None:
        return

    hydrate_settings = importlib.import_module("settings.hydrate").hydrate_settings

    for package, cls in settings_services.module_registry.items():
        try:
            hydrated = await hydrate_settings(cls, store, package, lenient=True)
        except Exception:
            logger.exception("Hydrating %s failed; keeping its current settings", package)
            if session is not None:
                await session.rollback()
            continue
        services = getattr(app.state, package, None)
        if services is None:
            logger.warning("app.state.%s missing during hydrate — skipping", package)
            continue
        services.settings = hydrated
