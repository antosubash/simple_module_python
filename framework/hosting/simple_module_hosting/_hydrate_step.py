"""Hydrate every registered module's settings from the DB at lifespan start.

Runs before any module ``on_startup`` hook so startup code sees DB-backed
values. Everything it needs lives in the framework (#500): the registry in
``simple_module_core.module_settings``, the hydrator in
``simple_module_core.settings_hydrate``; the caller supplies the override
source, so this works with the ``settings`` plugin disabled.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI
from simple_module_core.module_settings import get_module_settings_registry
from simple_module_core.settings_hydrate import OverrideSource, hydrate_settings

logger = logging.getLogger(__name__)


async def hydrate_all(app: FastAPI, store: OverrideSource, session: Any = None) -> None:
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
    registry = get_module_settings_registry(app)
    if registry is None:
        return

    for package, cls in registry.items():
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
