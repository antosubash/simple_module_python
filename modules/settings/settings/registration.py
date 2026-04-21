"""Helper modules call from ``register_settings`` to install their BaseSettings.

Two things happen:
1. A fresh ``BaseSettings`` (pydantic defaults only) is constructed.
2. The class is recorded in ``app.state.settings.module_registry`` so the
   hosting lifespan can hydrate it from the DB before module ``on_startup``
   hooks run.

The module's services dataclass is built from the default settings object and
attached at ``app.state.<package>``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from pydantic_settings import BaseSettings

from settings.constants import MODULE_PACKAGE


def register_module_settings(
    app: FastAPI,
    package: str,
    settings_cls: type[BaseSettings],
    services_factory: Callable[[BaseSettings], Any],
) -> None:
    """Register a module's BaseSettings class and mount its services on app.state."""
    registry = getattr(app.state, MODULE_PACKAGE).module_registry
    registry.register(package, settings_cls)
    defaults = settings_cls()
    setattr(app.state, package, services_factory(defaults))
