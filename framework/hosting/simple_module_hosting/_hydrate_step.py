"""Framework-level hydration step run at start of the FastAPI lifespan.

Walks every registered module (including ``host``), hydrates its BaseSettings
from the DB, and reassigns ``app.state.<package>.settings``. Runs before any
module ``on_startup`` hook so startup code sees DB-backed values.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

from fastapi import FastAPI

logger = logging.getLogger(__name__)

_MODULE_PACKAGE = "settings"  # hardcoded to avoid importing settings.constants at module scope


async def hydrate_all(app: FastAPI, store: Any) -> None:
    """Resolve every registered module's settings from the DB.

    ``store`` is a ``settings.store.SettingsStore`` — typed as ``Any`` to avoid a
    framework→plugin import at module-load time (SM009). Use ``importlib`` to
    resolve ``hydrate_settings`` lazily.
    """
    settings_services = getattr(app.state, _MODULE_PACKAGE, None)
    if settings_services is None:
        return  # Settings module not installed in this boot — nothing to hydrate.

    hydrate_mod = importlib.import_module("settings.hydrate")
    hydrate_settings = hydrate_mod.hydrate_settings

    registry = settings_services.module_registry
    for package, cls in registry.items():
        try:
            hydrated = await hydrate_settings(cls, store, package)
        except Exception:
            logger.exception(
                "Hydrating %s failed; falling back to defaults", package
            )
            continue
        services = getattr(app.state, package, None)
        if services is None:
            logger.warning("app.state.%s missing during hydrate — skipping", package)
            continue
        services.settings = hydrated
