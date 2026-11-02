"""Per-module settings classes: the registry and ``register_module_settings``.

A module calls :func:`register_module_settings` from its ``register_settings``
hook. Two things happen:

1. The class is recorded in the app's :class:`ModuleSettingsRegistry`, so the
   hosting lifespan can hydrate it from the settings table (env → DB →
   default) before any module ``on_startup`` hook runs.
2. A fresh instance (defaults only) is passed to ``services_factory`` and the
   result is mounted at ``app.state.<package>``.

The registry is created lazily on ``app.state`` by whoever asks for it first,
so registration does not depend on the ``settings`` plugin having run — or on
it being enabled at all (#500). The ``settings`` plugin's admin screens read
the same registry object through ``SettingsServices.module_registry``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Final

from fastapi import FastAPI
from pydantic_settings import BaseSettings

from simple_module_core.secret_fields import register_typed_secrets

__all__ = [
    "MODULE_SETTINGS_STATE_ATTR",
    "ModuleSettingsRegistry",
    "get_module_settings_registry",
    "module_settings_registry",
    "register_module_settings",
]

MODULE_SETTINGS_STATE_ATTR: Final = "module_settings_registry"
"""``app.state`` attribute holding the app's :class:`ModuleSettingsRegistry`."""


@dataclass(slots=True)
class ModuleSettingsRegistry:
    """In-memory map of ``package`` → ``BaseSettings`` subclass."""

    _classes: dict[str, type[BaseSettings]] = field(default_factory=dict)
    _manage_urls: dict[str, str] = field(default_factory=dict)

    def register(
        self,
        package: str,
        cls: type[BaseSettings],
        manage_url: str | None = None,
    ) -> None:
        if package in self._classes:
            raise ValueError(f"{package!r} already registered")
        self._classes[package] = cls
        register_typed_secrets(package, cls)
        if manage_url:
            self._manage_urls[package] = manage_url

    def manage_url(self, package: str) -> str | None:
        """URL of the module's own management page, if it declared one.

        Modules with a purpose-built settings screen (e.g. Branding) declare it
        so the generic module-settings editor links there instead of offering a
        second, raw editor for the same fields.
        """
        return self._manage_urls.get(package)

    def get(self, package: str) -> type[BaseSettings] | None:
        return self._classes.get(package)

    def all_packages(self) -> list[str]:
        return sorted(self._classes)

    def items(self) -> list[tuple[str, type[BaseSettings]]]:
        return sorted(self._classes.items())


def get_module_settings_registry(app: FastAPI) -> ModuleSettingsRegistry | None:
    """The app's registry, or ``None`` when nothing has registered yet."""
    return getattr(app.state, MODULE_SETTINGS_STATE_ATTR, None)


def module_settings_registry(app: FastAPI) -> ModuleSettingsRegistry:
    """The app's registry, created on first use."""
    registry = get_module_settings_registry(app)
    if registry is None:
        registry = ModuleSettingsRegistry()
        setattr(app.state, MODULE_SETTINGS_STATE_ATTR, registry)
    return registry


def register_module_settings[T: BaseSettings](
    app: FastAPI,
    package: str,
    settings_cls: type[T],
    services_factory: Callable[[T], Any],
    manage_url: str | None = None,
) -> None:
    """Register a module's settings class and mount its services on ``app.state``.

    ``manage_url`` points at the module's own management page when it has one;
    the generic module-settings editor then links there instead of rendering a
    second editor for the same fields.
    """
    module_settings_registry(app).register(package, settings_cls, manage_url=manage_url)
    setattr(app.state, package, services_factory(settings_cls()))
