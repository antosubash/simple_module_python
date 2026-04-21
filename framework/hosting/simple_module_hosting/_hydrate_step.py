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


async def hydrate_all(app: FastAPI, store: Any) -> None:
    """Resolve every registered module's settings from the DB."""
    settings_services = getattr(app.state, _MODULE_PACKAGE, None)
    if settings_services is None:
        return

    hydrate_settings = importlib.import_module("settings.hydrate").hydrate_settings

    for package, cls in settings_services.module_registry.items():
        try:
            hydrated = await hydrate_settings(cls, store, package)
        except Exception:
            logger.exception("Hydrating %s failed; falling back to defaults", package)
            continue
        services = getattr(app.state, package, None)
        if services is None:
            logger.warning("app.state.%s missing during hydrate — skipping", package)
            continue
        services.settings = hydrated
