"""Registry of per-module pydantic BaseSettings classes.

Populated during each module's ``register_settings`` via
``register_module_settings``. The hosting lifespan reads this at startup
to hydrate every module's effective settings from the DB.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic_settings import BaseSettings


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
